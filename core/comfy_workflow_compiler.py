"""Compile Forge-style generation payloads into ComfyUI API graphs.

The desktop UI intentionally owns one generation payload contract.  Forge can
consume that contract directly, while ComfyUI needs an explicit graph.  This
module is the narrow translation boundary: it is pure (no HTTP/Qt), never
mutates caller data, and rejects enabled features that the connected ComfyUI
cannot execute instead of silently dropping them.
"""
from __future__ import annotations

import copy
import json
import os
import random
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence


class WorkflowCompileError(RuntimeError):
    """A Forge request cannot be represented by the target ComfyUI runtime."""


@dataclass(frozen=True)
class LoraSpec:
    name: str
    strength_model: float
    strength_clip: float


_LORA_RE = re.compile(
    r"<lora\s*:\s*([^:>]+?)\s*(?::\s*([^:>]+?))?\s*(?::\s*([^>]+?))?\s*>",
    re.IGNORECASE,
)
_SAMPLERS = {
    "KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced",
    "ForgeNeoKSamplerCNS",
}
_SAVE_NODES = {"SaveImage", "PreviewImage", "ForgeNeoSaveImage"}


def _float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed == parsed and parsed not in (float("inf"), float("-inf")) else default


def _int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().casefold() not in {"", "0", "false", "no", "off", "none"}


def _clean_prompt_after_loras(text: str) -> str:
    text = _LORA_RE.sub("", text)
    text = re.sub(r"(?:\s*,\s*){2,}", ", ", text)
    return text.strip(" \t\r\n,")


def parse_lora_tags(*prompts: str) -> tuple[list[LoraSpec], list[str]]:
    """Return ordered LoRA requests and prompts with loader syntax removed."""
    loras: list[LoraSpec] = []
    cleaned: list[str] = []
    for prompt in prompts:
        text = str(prompt or "")
        for match in _LORA_RE.finditer(text):
            name = match.group(1).strip()
            if not name:
                continue
            model_strength = _float(match.group(2), 1.0)
            clip_strength = _float(match.group(3), model_strength)
            loras.append(LoraSpec(name, model_strength, clip_strength))
        cleaned.append(_clean_prompt_after_loras(text))
    return loras, cleaned


def _is_link(value: Any) -> bool:
    return isinstance(value, list) and len(value) >= 2


def _filename(value: Any) -> str:
    return os.path.basename(str(value or "").replace("\\", "/")).strip()


class _Graph:
    def __init__(self, initial: Optional[Mapping[str, Any]] = None):
        self.nodes: dict[str, dict] = copy.deepcopy(dict(initial or {}))
        numeric = [int(str(key)) for key in self.nodes if str(key).isdigit()]
        self._next = max(numeric, default=0) + 1

    def add(self, class_type: str, inputs: Mapping[str, Any], title: str = "") -> str:
        while str(self._next) in self.nodes:
            self._next += 1
        node_id = str(self._next)
        self._next += 1
        node = {"class_type": class_type, "inputs": copy.deepcopy(dict(inputs))}
        if title:
            node["_meta"] = {"title": title}
        self.nodes[node_id] = node
        return node_id


class ComfyWorkflowCompiler:
    """Compile a canonical app payload for one concrete ComfyUI capability set."""

    def __init__(self, object_info: Optional[Mapping[str, Any]] = None):
        self.object_info = None if object_info is None else dict(object_info)

    # ---- public ---------------------------------------------------------

    def compile(
        self,
        mode: str,
        model_name: str,
        payload: Mapping[str, Any],
        *,
        workflow: Optional[Mapping[str, Any]] = None,
        uploaded_image: str = "",
        uploaded_mask: str = "",
    ) -> dict:
        normalized = {
            "t2i": "txt2img", "txt2img": "txt2img",
            "i2i": "img2img", "img2img": "img2img",
            "inpaint": "inpaint",
        }.get(str(mode or "").strip().casefold())
        if normalized is None:
            raise WorkflowCompileError(f"지원하지 않는 ComfyUI 생성 모드입니다: {mode!r}")
        if not isinstance(payload, Mapping):
            raise WorkflowCompileError("생성 payload는 객체여야 합니다.")

        local_payload = copy.deepcopy(dict(payload))
        if normalized != "txt2img":
            local_payload.setdefault("denoising_strength", 0.75)
        loras, prompts = parse_lora_tags(
            str(local_payload.get("prompt", "") or ""),
            str(local_payload.get("negative_prompt", "") or ""),
        )
        local_payload["prompt"], local_payload["negative_prompt"] = prompts

        if workflow is None:
            graph = self._compile_default(
                normalized, model_name, local_payload, loras,
                uploaded_image=uploaded_image, uploaded_mask=uploaded_mask,
            )
        else:
            graph = self._compile_custom(
                normalized, model_name, local_payload, loras, workflow,
                uploaded_image=uploaded_image, uploaded_mask=uploaded_mask,
            )
        self.validate(graph)
        return graph

    def compile_upscale(self, uploaded_image: str, settings: Mapping[str, Any]) -> dict:
        if not uploaded_image:
            raise WorkflowCompileError("업스케일 입력 이미지가 업로드되지 않았습니다.")
        graph = _Graph()
        load = graph.add("LoadImage", {"image": uploaded_image}, "Upscale source")
        method = str(settings.get("upscaler_name") or "Lanczos").strip()
        mode = str(settings.get("scale_mode") or "factor").strip().casefold()
        builtin = {
            "lanczos": "lanczos", "nearest": "nearest-exact", "nearest-exact": "nearest-exact",
            "bilinear": "bilinear", "bicubic": "bicubic", "area": "area",
        }.get(method.casefold())
        if builtin is not None:
            if mode == "size":
                image = graph.add("ImageScale", {
                    "image": [load, 0], "upscale_method": builtin,
                    "width": max(1, _int(settings.get("target_width"), 1024)),
                    "height": max(1, _int(settings.get("target_height"), 1024)),
                    "crop": "disabled",
                }, "Exact-size upscale")
            else:
                image = graph.add("ImageScaleBy", {
                    "image": [load, 0], "upscale_method": builtin,
                    "scale_by": max(0.01, _float(settings.get("scale_factor"), 2.0)),
                }, "Factor upscale")
        else:
            model_name = self._resolve_choice("UpscaleModelLoader", "model_name", method)
            loader = graph.add("UpscaleModelLoader", {"model_name": model_name}, "Upscale model")
            image = graph.add("ImageUpscaleWithModel", {
                "upscale_model": [loader, 0], "image": [load, 0],
            }, "Model upscale")
            if mode == "size":
                image = graph.add("ImageScale", {
                    "image": [image, 0], "upscale_method": "lanczos",
                    "width": max(1, _int(settings.get("target_width"), 1024)),
                    "height": max(1, _int(settings.get("target_height"), 1024)),
                    "crop": "disabled",
                }, "Final exact size")
        graph.add("SaveImage", {"images": [image, 0], "filename_prefix": "AIStudio/upscale"}, "Save")
        self.validate(graph.nodes)
        return graph.nodes

    def compile_postprocess(
        self,
        model_name: str,
        payload: Mapping[str, Any],
        *,
        uploaded_image: str,
        sam3_detailer_class: str = "ForgeNeoSAM3Detailer",
    ) -> dict:
        """Compile ADetailer/SAM3 directly on an image without a no-op base sample."""
        if not uploaded_image:
            raise WorkflowCompileError("후처리 입력 이미지가 업로드되지 않았습니다.")
        if sam3_detailer_class not in {
            "ForgeNeoSAM3Detailer", "ForgeNeoSAM3Refine",
        }:
            raise WorkflowCompileError(
                f"지원하지 않는 SAM3 후처리 노드입니다: {sam3_detailer_class}"
            )
        local_payload = copy.deepcopy(dict(payload))
        if not self._has_image_scripts(local_payload):
            raise WorkflowCompileError("ADetailer 또는 SAM3 후처리 설정이 없습니다.")
        loras, prompts = parse_lora_tags(
            str(local_payload.get("prompt", "") or ""),
            str(local_payload.get("negative_prompt", "") or ""),
        )
        local_payload["prompt"], local_payload["negative_prompt"] = prompts
        graph = _Graph()
        model, clip, vae = self._add_loaders(graph, model_name, local_payload)
        shift = _float(local_payload.get("distilled_cfg_scale"), 0.0)
        if shift > 0:
            node = graph.add("ModelSamplingSD3", {"model": model, "shift": shift}, "Forge distilled CFG shift")
            model = [node, 0]
        model, clip = self._add_loras(graph, model, clip, loras)
        model, clip = self._add_negpip(graph, model, clip, local_payload)
        pos = graph.add("CLIPTextEncode", {
            "clip": clip, "text": str(local_payload.get("prompt") or ""),
        }, "Positive")
        neg = graph.add("CLIPTextEncode", {
            "clip": clip, "text": str(local_payload.get("negative_prompt") or ""),
        }, "Negative")
        positive, negative = [pos, 0], [neg, 0]
        model, _sampler_options = self._add_anima_guidance(
            graph, model, clip, positive, negative, local_payload,
        )
        source = graph.add("LoadImage", {"image": uploaded_image}, "Postprocess source")
        image = self._add_image_extensions(
            graph, [source, 0], model, clip, vae, positive, negative, local_payload,
            sam3_detailer_class=sam3_detailer_class,
        )
        graph.add("SaveImage", {
            "images": image,
            "filename_prefix": str(local_payload.get("filename_prefix") or "AIStudio/postprocess"),
        }, "Save postprocessed image")
        self.validate(graph.nodes)
        return graph.nodes

    def compile_sam3_mask_only(
        self, payload: Mapping[str, Any], *, uploaded_image: str,
    ) -> dict:
        """Compile SAM3 segmentation/artifact output without loading diffusion models."""
        if not uploaded_image:
            raise WorkflowCompileError("SAM3 입력 이미지가 업로드되지 않았습니다.")
        state = self._sam3_state(payload)
        if state is None:
            raise WorkflowCompileError("활성화된 SAM3 Mask 설정이 없습니다.")
        local_payload = copy.deepcopy(dict(payload))
        local_scripts = copy.deepcopy(dict(local_payload.get("alwayson_scripts") or {}))
        for name in list(local_scripts):
            if str(name).casefold() == "sam3 mask":
                local_scripts[name]["args"][0]["sam3_mode"] = "Mask only"
            else:
                del local_scripts[name]
        local_payload["alwayson_scripts"] = local_scripts
        graph = _Graph()
        source = graph.add("LoadImage", {"image": uploaded_image}, "SAM3 source")
        image = self._add_image_extensions(
            graph, [source, 0], [], [], [], [], [], local_payload,
        )
        graph.add("SaveImage", {
            "images": image,
            "filename_prefix": str(local_payload.get("filename_prefix") or "AIStudio/sam3-mask"),
        }, "Save SAM3 mask")
        self.validate(graph.nodes)
        return graph.nodes

    def validate(self, workflow: Mapping[str, Any]) -> None:
        """Validate every executable class when a /object_info document exists."""
        if self.object_info is None:
            return
        used = {
            str(node.get("class_type") or "")
            for node in workflow.values()
            if isinstance(node, Mapping) and node.get("class_type")
        }
        missing = sorted(name for name in used if name not in self.object_info)
        if missing:
            forge_nodes = [name for name in missing if name.startswith("ForgeNeo")]
            hint = (
                " ComfyUI를 재시작하고 AI Studio Forge Parity custom node pack 연결을 확인하세요."
                if forge_nodes else " 대상 ComfyUI의 custom nodes/버전을 확인하세요."
            )
            raise WorkflowCompileError(
                "ComfyUI에 필요한 노드가 없습니다: " + ", ".join(missing) + "." + hint
            )

        # A stale copy of the bundled pack can expose the class name while
        # still having an older input contract.  Catch that before /prompt so
        # enabled Forge features never disappear behind Comfy's node errors.
        for node_id, node in workflow.items():
            if not isinstance(node, Mapping):
                continue
            class_type = str(node.get("class_type") or "")
            schema = self.object_info.get(class_type, {})
            input_schema = schema.get("input", {}) if isinstance(schema, Mapping) else {}
            required = input_schema.get("required", {}) if isinstance(input_schema, Mapping) else {}
            optional = input_schema.get("optional", {}) if isinstance(input_schema, Mapping) else {}
            if not isinstance(required, Mapping) or not isinstance(optional, Mapping):
                continue
            known = set(required) | set(optional)
            if class_type.startswith("ForgeNeo") and not known:
                # Some lightweight capability probes publish class names only.
                continue
            supplied = node.get("inputs", {})
            supplied = supplied if isinstance(supplied, Mapping) else {}
            unexpected = sorted(set(supplied) - known) if class_type.startswith("ForgeNeo") else []
            absent = sorted(set(required) - set(supplied)) if class_type.startswith("ForgeNeo") else []
            invalid_choices: list[str] = []
            for name, value in supplied.items():
                if _is_link(value):
                    continue
                spec = required.get(name, optional.get(name))
                choices = (
                    list(spec[0])
                    if isinstance(spec, (list, tuple)) and spec
                    and isinstance(spec[0], (list, tuple))
                    else []
                )
                if choices and value not in choices:
                    invalid_choices.append(f"{name}={value!r}")
            if unexpected or absent or invalid_choices:
                details = []
                if absent:
                    details.append("누락=" + ",".join(absent))
                if unexpected:
                    details.append("미지원=" + ",".join(unexpected))
                if invalid_choices:
                    details.append("허용되지 않은 선택=" + ",".join(invalid_choices))
                raise WorkflowCompileError(
                    f"ComfyUI {class_type} 노드 계약이 앱과 다릅니다 "
                    f"(node {node_id}; {'; '.join(details)}). "
                    "번들 노드 팩을 갱신하고 ComfyUI를 재시작하세요."
                )

    # ---- default graph -------------------------------------------------

    def _compile_default(
        self,
        mode: str,
        model_name: str,
        payload: dict,
        loras: Sequence[LoraSpec],
        *,
        uploaded_image: str,
        uploaded_mask: str,
    ) -> dict:
        graph = _Graph()
        model, clip, vae = self._add_loaders(graph, model_name, payload)

        shift = _float(payload.get("distilled_cfg_scale"), 0.0)
        if shift > 0:
            shift_node = graph.add("ModelSamplingSD3", {
                "model": model, "shift": shift,
            }, "Forge distilled CFG shift")
            model = [shift_node, 0]

        model, clip = self._add_loras(graph, model, clip, loras)
        model, clip = self._add_negpip(graph, model, clip, payload)

        positive = graph.add("CLIPTextEncode", {
            "clip": clip, "text": str(payload.get("prompt", "") or ""),
        }, "Positive")
        negative = graph.add("CLIPTextEncode", {
            "clip": clip, "text": str(payload.get("negative_prompt", "") or ""),
        }, "Negative")
        positive_ref, negative_ref = [positive, 0], [negative, 0]

        model, sampler_options = self._add_anima_guidance(
            graph, model, clip, positive_ref, negative_ref, payload,
        )
        latent = self._add_latent(
            graph, mode, vae, payload,
            uploaded_image=uploaded_image, uploaded_mask=uploaded_mask,
        )
        sampler = self._add_sampler(
            graph, model, positive_ref, negative_ref, latent, payload, sampler_options,
            mode=mode,
        )
        samples, decode_vae = [sampler, 0], vae
        if _bool(payload.get("enable_hr")):
            samples, decode_vae = self._add_hires(
                graph, model, clip, vae, positive_ref, negative_ref, samples, payload,
                sampler_options=sampler_options,
            )
        decode = graph.add("VAEDecode", {"samples": samples, "vae": decode_vae}, "Decode")
        image = [decode, 0]
        image = self._add_image_extensions(
            graph, image, model, clip, vae, positive_ref, negative_ref, payload,
        )
        graph.add("SaveImage", {
            "images": image, "filename_prefix": str(payload.get("filename_prefix") or "AIStudio/generated"),
        }, "Save generated image")
        return graph.nodes

    def _add_loaders(self, graph: _Graph, model_name: str, payload: Mapping[str, Any]):
        modules = self._module_names(payload)
        checkpoint_choices = self._choices("CheckpointLoaderSimple", "ckpt_name")
        unet_choices = self._choices("UNETLoader", "unet_name")
        checkpoint = self._match_choice(model_name, checkpoint_choices)
        unet = self._match_choice(model_name, unet_choices)
        use_split = unet is not None and checkpoint is None
        if self.object_info is None and modules:
            # Offline compilation cannot disambiguate a checkpoint from a bare
            # diffusion model.  Forge additional modules conventionally means
            # the latter; a live backend always resolves from /object_info.
            use_split = True

        if not use_split:
            selected = self._resolve_choice("CheckpointLoaderSimple", "ckpt_name", model_name)
            node = graph.add("CheckpointLoaderSimple", {"ckpt_name": selected}, "Checkpoint")
            model, clip, vae = [node, 0], [node, 1], [node, 2]
            if not modules:
                return model, clip, vae
            clip_modules, vae_modules, unknown = self._classify_modules(modules)
            if unknown:
                raise WorkflowCompileError(
                    "forge_additional_modules를 ComfyUI 로더에 매핑할 수 없습니다: "
                    + ", ".join(unknown)
                )
            if clip_modules:
                clip = self._add_clip_loader(graph, clip_modules, payload)
            if len(vae_modules) > 1:
                raise WorkflowCompileError("forge_additional_modules의 VAE는 한 개만 지정할 수 있습니다.")
            if vae_modules:
                vae_name = self._resolve_choice("VAELoader", "vae_name", vae_modules[0])
                vae_node = graph.add("VAELoader", {"vae_name": vae_name}, "VAE override")
                vae = [vae_node, 0]
            return model, clip, vae

        selected_unet = self._resolve_choice("UNETLoader", "unet_name", model_name)
        unet_node = graph.add("UNETLoader", {
            "unet_name": selected_unet,
            "weight_dtype": str(payload.get("weight_dtype") or "default"),
        }, "Diffusion model")
        clip_modules, vae_modules, unknown = self._classify_modules(modules)
        if unknown:
            raise WorkflowCompileError(
                "forge_additional_modules를 ComfyUI 로더에 매핑할 수 없습니다: "
                + ", ".join(unknown)
            )
        if not clip_modules:
            explicit = payload.get("text_encoder_name") or payload.get("clip_name")
            if explicit:
                clip_modules = [str(explicit)]
        if not vae_modules and payload.get("vae_name"):
            vae_modules = [str(payload["vae_name"])]
        if not clip_modules:
            raise WorkflowCompileError(
                "분리 UNET에는 text encoder가 필요합니다. 설정의 TE 또는 "
                "forge_additional_modules를 지정하세요."
            )
        if len(vae_modules) != 1:
            raise WorkflowCompileError(
                "분리 UNET에는 VAE 한 개가 필요합니다. "
                f"현재 매핑된 VAE: {len(vae_modules)}개"
            )
        clip = self._add_clip_loader(graph, clip_modules, payload)
        vae_name = self._resolve_choice("VAELoader", "vae_name", vae_modules[0])
        vae_node = graph.add("VAELoader", {"vae_name": vae_name}, "VAE")
        return [unet_node, 0], clip, [vae_node, 0]

    def _add_clip_loader(self, graph: _Graph, names: Sequence[str], payload: Mapping[str, Any]):
        resolved = [self._resolve_choice("CLIPLoader", "clip_name", item) for item in names]
        if len(resolved) == 1:
            node = graph.add("CLIPLoader", {
                "clip_name": resolved[0],
                "type": str(payload.get("comfy_clip_type") or payload.get("clip_type") or "stable_diffusion"),
                "device": str(payload.get("clip_device") or "default"),
            }, "Text encoder")
        elif len(resolved) == 2:
            node = graph.add("DualCLIPLoader", {
                "clip_name1": resolved[0], "clip_name2": resolved[1],
                "type": str(payload.get("comfy_dual_clip_type") or "sd3"),
                "device": str(payload.get("clip_device") or "default"),
            }, "Dual text encoder")
        elif len(resolved) == 3:
            node = graph.add("TripleCLIPLoader", {
                "clip_name1": resolved[0], "clip_name2": resolved[1], "clip_name3": resolved[2],
            }, "Triple text encoder")
        else:
            raise WorkflowCompileError(
                f"ComfyUI 기본 그래프는 text encoder 1~3개를 지원합니다: {len(resolved)}개 요청됨"
            )
        return [node, 0]

    def _add_latent(
        self, graph: _Graph, mode: str, vae: list, payload: Mapping[str, Any],
        *, uploaded_image: str, uploaded_mask: str,
    ) -> list:
        if mode != "txt2img" and not uploaded_image:
            raise WorkflowCompileError(f"{mode} 입력 이미지가 업로드되지 않았습니다.")
        image_node = graph.add("LoadImage", {"image": uploaded_image}, "Input image") if uploaded_image else None
        mask_node = graph.add("LoadImage", {"image": uploaded_mask}, "Input mask") if uploaded_mask else None
        if mode == "inpaint" and not (uploaded_mask or payload.get("use_image_alpha_as_mask")):
            raise WorkflowCompileError("inpaint에는 마스크 이미지 또는 알파 마스크가 필요합니다.")
        batch = max(1, _int(payload.get("batch_size"), 1)) * max(
            1, _int(payload.get("n_iter", payload.get("batch_count", 1)), 1)
        )
        inputs: dict[str, Any] = {
            "vae": vae,
            "mode": mode,
            "width": max(64, _int(payload.get("width"), 512)),
            "height": max(64, _int(payload.get("height"), 512)),
            "batch_size": batch,
            "fit": self._fit_mode(payload.get("resize_mode")),
            "mask_invert": _bool(payload.get("inpainting_mask_invert", payload.get("mask_invert"))),
            "mask_blur": max(0, _int(payload.get("mask_blur"), 4)),
            "grow_mask_by": max(0, _int(payload.get("mask_dilation", payload.get("grow_mask_by", 6)), 6)),
            "reference_enabled": False,
            "reference_layout": "reference_left",
            "reference_fraction": 0.5,
            "reference_gap": 0,
            "reference_background": 0.0,
            "reference_fit": "contain",
        }
        if mode == "img2img":
            inputs["img2img_image"] = [image_node, 0]
        elif mode == "inpaint":
            inputs["inpaint_image"] = [image_node, 0]
            if mask_node:
                inputs["inpaint_mask_image"] = [mask_node, 0]
            else:
                inputs["inpaint_mask"] = [image_node, 1]
        node = graph.add("ForgeNeoLatentInput", inputs, f"{mode} latent")
        return [node, 0]

    def _add_sampler(
        self, graph: _Graph, model: list, positive: list, negative: list, latent: list,
        payload: Mapping[str, Any], options: Mapping[str, Any], *, mode: str,
    ) -> str:
        seed = _int(payload.get("seed"), -1)
        if seed < 0:
            seed = random.randint(0, 2**32 - 1)
        sampler_name, scheduler = self._runtime_sampler_values(
            payload.get("sampler_name") or "euler",
            payload.get("scheduler") or "normal",
        )
        inputs = {
            "model": model, "positive": positive, "negative": negative,
            "latent_image": latent, "seed": seed,
            "steps": max(1, _int(payload.get("steps"), 20)),
            "cfg": _float(payload.get("cfg_scale"), 7.0),
            "sampler_name": sampler_name,
            "scheduler": scheduler,
            "denoise": (
                1.0 if mode == "txt2img" else
                max(0.0, min(1.0, _float(payload.get("denoising_strength"), 0.75)))
            ),
            "cns_enabled": _bool(options.get("cns_enabled")),
            "cns_strength": _float(options.get("cns_strength"), 1.0),
            "cns_gamma_power": _float(options.get("cns_gamma_power"), 0.5),
            "cns_gamma_scale": _float(options.get("cns_gamma_scale"), 3.0),
            "spectrum_enabled": _bool(payload.get("spectrum_enabled")),
            "spectrum_window_size": _float(payload.get("spectrum_window_size"), 2.0),
            "spectrum_flex_window": _float(payload.get("spectrum_flex_window"), 0.25),
            "spectrum_warmup_steps": _int(payload.get("spectrum_warmup_steps"), 6),
            "spectrum_tail_actual_steps": _int(payload.get("spectrum_tail_actual_steps"), 3),
            "spectrum_blend_w": _float(payload.get("spectrum_blend_w"), 0.3),
            "spectrum_cheby_degree": _int(payload.get("spectrum_cheby_degree"), 3),
            "spectrum_ridge_lambda": _float(payload.get("spectrum_ridge_lambda"), 0.1),
            "spectrum_history_size": _int(payload.get("spectrum_history_size"), 100),
            "spectrum_one_sampler_only": _bool(payload.get("spectrum_one_sampler_only")),
            "spectrum_verbose": _bool(payload.get("spectrum_verbose")),
            "speed_enabled": _bool(payload.get("speed_enabled")),
            "speed_split_mode": str(payload.get("speed_split_mode") or "single"),
            "speed_spd_scale": _float(payload.get("speed_spd_scale"), 0.5),
            "speed_spd_sigma": _float(payload.get("speed_spd_sigma"), 0.7),
            "speed_adaptive_smc_alpha": _float(payload.get("speed_adaptive_smc_alpha"), 0.0),
        }
        return graph.add("ForgeNeoKSamplerCNS", inputs, "Forge-compatible sampler")

    # ---- graph stages --------------------------------------------------

    def _add_loras(self, graph: _Graph, model: list, clip: list, loras: Sequence[LoraSpec]):
        for spec in loras:
            name = self._resolve_choice("LoraLoader", "lora_name", spec.name)
            node = graph.add("LoraLoader", {
                "model": model, "clip": clip, "lora_name": name,
                "strength_model": spec.strength_model, "strength_clip": spec.strength_clip,
            }, f"LoRA: {name}")
            model, clip = [node, 0], [node, 1]
        return model, clip

    def _add_negpip(self, graph: _Graph, model: list, clip: list, payload: Mapping[str, Any]):
        block = self._script(payload, "NegPiP")
        if block is None:
            return model, clip
        args = block.get("args", []) if isinstance(block, Mapping) else []
        enabled = _bool(args[0] if args else True, True)
        if not enabled:
            return model, clip
        node = graph.add("ForgeNeoNegPip", {
            "model": model, "clip": clip, "enabled": True,
        }, "NegPiP")
        return [node, 0], [node, 1]

    def _add_anima_guidance(
        self, graph: _Graph, model: list, clip: list, positive: list, negative: list,
        payload: Mapping[str, Any],
    ) -> tuple[list, dict[str, Any]]:
        from core import anima_guidance

        sampler_options: dict[str, Any] = {}
        perturb = self._script(payload, anima_guidance.SCRIPT_PERTURBATION)
        if perturb is not None:
            settings = self._script_settings(perturb, anima_guidance.PERTURBATION_SPEC)
            active_keys = (
                "guid_enabled", "guid_slg_on", "guid_apg_enabled", "guid_adg_enabled",
                "guid_smc_enabled", "guid_smc_master_enabled", "guid_cwm_enabled",
                "guid_dcw_enabled", "guid_rdc_enabled", "guid_dave_enabled",
                "guid_cns_enabled", "guid_mod_enabled", "guid_experimental_stack",
            )
            if any(_bool(settings.get(key)) for key in active_keys):
                self._validate_anima_guidance_settings(settings)
                suite_settings = dict(settings)
                suite_settings["cfg_scale"] = _float(payload.get("cfg_scale"), 7.0)
                node = graph.add("ForgeNeoAnimaGuidanceSuite", {
                    "model": model, "clip": clip, "positive": positive, "negative": negative,
                    "enabled": True,
                    "settings_json": json.dumps(
                        suite_settings, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    ),
                }, "Anima guidance suite")
                model = [node, 0]
            sampler_options.update({
                "cns_enabled": _bool(settings.get("guid_cns_enabled")),
                "cns_strength": _float(settings.get("guid_cns_strength"), 1.0),
                "cns_gamma_power": _float(settings.get("guid_cns_gamma_power"), 0.5),
                "cns_gamma_scale": _float(settings.get("guid_cns_gamma_scale"), 3.0),
            })

        skim = self._script(payload, anima_guidance.SCRIPT_SKIMMED_CFG)
        if skim is not None:
            settings = self._script_settings(skim, anima_guidance.SKIMMED_SPEC)
            if _bool(settings.get("skim_enabled")):
                node = graph.add("ForgeNeoSkimmedCFG", {
                    "model": model, "enabled": True,
                    "skimming_cfg": _float(settings.get("skim_skimming_cfg"), 7.0),
                    "full_skim_negative": _bool(settings.get("skim_full_skim_negative")),
                    "disable_flipping_filter": _bool(settings.get("skim_disable_flipping_filter")),
                    "start_percent": _float(settings.get("skim_start_percent"), 0.0),
                    "end_percent": _float(settings.get("skim_end_percent"), 1.0),
                    "flip_percent": _float(settings.get("skim_flip_at"), 0.0),
                }, "Anima skimmed CFG")
                model = [node, 0]

        daemon = self._script(payload, anima_guidance.SCRIPT_DETAIL_DAEMON)
        if daemon is not None:
            settings = self._script_settings(daemon, anima_guidance.DETAIL_DAEMON_SPEC)
            if _bool(settings.get("dd_enabled")):
                daemon_settings = dict(settings)
                daemon_settings["cfg_scale"] = _float(payload.get("cfg_scale"), 7.0)
                node = graph.add("ForgeNeoAnimaDetailDaemon", {
                    "model": model, "enabled": True,
                    "settings_json": json.dumps(
                        daemon_settings, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    ),
                }, "Anima detail daemon")
                model = [node, 0]
        return model, sampler_options

    def _add_hires(
        self, graph: _Graph, model: list, clip: list, vae: list,
        positive: list, negative: list, samples: list, payload: Mapping[str, Any],
        *, sampler_options: Optional[Mapping[str, Any]] = None,
    ) -> tuple[list, list]:
        sampler_options = sampler_options or {}
        upscaler = str(payload.get("hr_upscaler") or "latent:bislerp")
        upscaler_map = {
            "none": "latent:bislerp", "latent": "latent:bislerp",
            "latent (nearest)": "latent:nearest-exact",
            "latent (nearest-exact)": "latent:nearest-exact",
            "latent (bilinear)": "latent:bilinear", "latent (bicubic)": "latent:bicubic",
            "latent (bislerp)": "latent:bislerp",
        }
        method = upscaler_map.get(upscaler.casefold(), upscaler)
        method = self._resolve_when_enumerated(
            "ForgeNeoHiresFix", "upscale_method", method,
        )
        hires_sampler, hires_scheduler = self._runtime_sampler_values(
            payload.get("hr_sampler_name") or payload.get("sampler_name") or "euler",
            payload.get("hr_scheduler") or payload.get("scheduler") or "normal",
        )
        base_sampler, base_scheduler = self._runtime_sampler_values(
            payload.get("sampler_name") or "euler",
            payload.get("scheduler") or "normal",
        )
        inputs = {
            "model": model, "positive": positive, "negative": negative, "samples": samples,
            "seed": _int(payload.get("seed"), -1), "enabled": True,
            "scale_by": max(1.0, _float(payload.get("hr_scale"), 2.0)),
            "upscale_method": method,
            "steps": max(0, _int(payload.get("hr_second_pass_steps"), 0)),
            "cfg": _float(payload.get("hr_cfg"), _float(payload.get("cfg_scale"), 7.0)),
            "sampler_name": hires_sampler,
            "scheduler": hires_scheduler,
            "denoise": max(0.0, min(1.0, _float(payload.get("denoising_strength"), 0.5))),
            "seed_delta": _int(payload.get("hr_seed_delta"), 0),
            "cns_enabled": _bool(sampler_options.get("cns_enabled")),
            "cns_strength": _float(sampler_options.get("cns_strength"), 1.0),
            "cns_gamma_power": _float(sampler_options.get("cns_gamma_power"), 0.5),
            "cns_gamma_scale": _float(sampler_options.get("cns_gamma_scale"), 2.0),
            "base_vae": vae, "base_clip": clip,
            "base_steps": max(1, _int(payload.get("steps"), 20)),
            "base_sampler_name": base_sampler,
            "base_scheduler": base_scheduler,
            "resize_width": max(0, _int(payload.get("hr_resize_x"), 0)),
            "resize_height": max(0, _int(payload.get("hr_resize_y"), 0)),
            "shift": max(0.0, _float(payload.get("distilled_cfg_scale"), 0.0)),
            "checkpoint_name": self._resolve_when_enumerated(
                "ForgeNeoHiresFix", "checkpoint_name",
                payload.get("hr_checkpoint_name") or "Use same checkpoint",
            ),
            "checkpoint_weight_dtype": str(payload.get("hr_weight_dtype") or "default"),
            "text_encoder_name": self._hr_module(payload, "clip"),
            "vae_name": self._hr_module(payload, "vae"),
            "positive_text": str(payload.get("hr_prompt") or ""),
            "negative_text": str(payload.get("hr_negative_prompt") or ""),
            "base_positive_text": str(payload.get("prompt") or ""),
            "base_negative_text": str(payload.get("negative_prompt") or ""),
            "clip_type": str(
                payload.get("comfy_clip_type") or payload.get("clip_type")
                or "stable_diffusion"
            ),
        }
        node = graph.add("ForgeNeoHiresFix", inputs, "Forge-compatible Hires.fix")
        return [node, 0], [node, 1]

    def _add_image_extensions(
        self, graph: _Graph, image: list, model: list, clip: list, vae: list,
        positive: list, negative: list, payload: Mapping[str, Any],
        *, sam3_detailer_class: str = "ForgeNeoSAM3Detailer",
    ) -> list:
        slots = self._adetailer_slots(payload)
        for index, slot in enumerate(slots, start=1):
            self._validate_adetailer_slot(slot, index)
            normalized_slot = dict(slot)
            requested_ad_sampler = (
                str(slot.get("ad_sampler") or "euler")
                if _bool(slot.get("ad_use_sampler"))
                else str(payload.get("sampler_name") or "euler")
            )
            requested_ad_scheduler = (
                str(slot.get("ad_scheduler") or "normal")
                if _bool(slot.get("ad_use_sampler"))
                else str(payload.get("scheduler") or "normal")
            )
            ad_sampler, ad_scheduler = self._runtime_sampler_values(
                requested_ad_sampler, requested_ad_scheduler,
            )
            normalized_slot.update({
                "seed": _int(slot.get("ad_seed"), _int(payload.get("seed"), 0)),
                "steps": (
                    _int(slot.get("ad_steps"), 28)
                    if _bool(slot.get("ad_use_steps"))
                    else _int(payload.get("steps"), 28)
                ),
                "cfg": (
                    _float(slot.get("ad_cfg_scale"), 7.0)
                    if _bool(slot.get("ad_use_cfg_scale"))
                    else _float(payload.get("cfg_scale"), 7.0)
                ),
                "sampler_name": ad_sampler,
                "scheduler": ad_scheduler,
                "denoise": _float(slot.get("ad_denoising_strength"), 0.4),
                "guide_size": (
                    max(
                        _int(slot.get("ad_inpaint_width"), 512),
                        _int(slot.get("ad_inpaint_height"), 512),
                    )
                    if _bool(slot.get("ad_use_inpaint_width_height")) else 512
                ),
                "bbox_threshold": _float(slot.get("ad_confidence"), 0.3),
                "bbox_dilation": _int(slot.get("ad_dilate_erode"), 4),
                "prompt": str(slot.get("ad_prompt") or ""),
            })
            slot_negative = negative
            if str(slot.get("ad_negative_prompt") or "").strip():
                negative_node = graph.add("CLIPTextEncode", {
                    "clip": clip, "text": str(slot.get("ad_negative_prompt")),
                }, f"ADetailer slot {index} negative")
                slot_negative = [negative_node, 0]
            node = graph.add("ForgeNeoADetailer", {
                "image": image, "model": model, "clip": clip, "vae": vae,
                "positive": positive, "negative": slot_negative, "enabled": True,
                "settings_json": json.dumps(
                    normalized_slot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ),
            }, f"ADetailer slot {index}")
            image = [node, 0]

        sam_state = self._sam3_state(payload)
        if sam_state is not None:
            state = dict(sam_state)
            mask_node = graph.add("ForgeNeoSAM3Mask", {
                "image": image,
                "prompt": str(state.get("sam3_prompt") or "face"),
                "exclude_prompt": str(state.get("sam3_exclude_prompt") or ""),
                "mask_mode": str(state.get("sam3_mask_mode") or "Individual"),
                "mask_source": "generated",
                "threshold": _float(state.get("sam3_threshold"), 0.4),
                "detection_limit": max(-1, _int(state.get("sam3_detection_limit"), -1)),
                "convex_hull": _bool(state.get("sam3_mask_hull")),
                "mask_dilation": max(0, _int(state.get("sam3_mask_dilation"), 0)),
                "mask_outline_px": max(0, _int(state.get("sam3_mask_outline_px"), 0)),
                "mask_blur": max(0, _int(state.get("sam3_mask_blur"), 4)),
                "invert": False,
                "checkpoint": str(state.get("sam3_checkpoint") or "sam3.pt"),
                "device": str(state.get("sam3_device") or "cuda"),
                "precision": str(
                    state.get("sam3_precision")
                    or ("fp16" if str(state.get("sam3_device") or "cuda").casefold() == "cuda" else "fp32")
                ),
                "unload_after": _bool(state.get("sam3_unload_after"), True),
                "save_artifacts": _bool(state.get("sam3_save_artifacts"), True),
                # Empty delegates to the node's Comfy output/sam3 directory.
                # sam3_args intentionally has no artifact path field.
                "artifact_directory": str(state.get("sam3_artifact_directory") or ""),
                "seed": _int(state.get("sam3_seed"), _int(payload.get("seed"), -1)),
                "enabled": True,
            }, "SAM3 mask")
            if str(state.get("sam3_mode") or "Inpaint").casefold() == "mask only":
                if _bool(state.get("sam3_preview_overlay")):
                    image = [mask_node, 3]
                else:
                    mask_image = graph.add("MaskToImage", {"mask": [mask_node, 0]}, "SAM3 mask image")
                    image = [mask_image, 0]
            else:
                sampler = str(state.get("sam3_sampler") or payload.get("sampler_name") or "euler")
                if sampler.casefold() == "use same sampler":
                    sampler = str(payload.get("sampler_name") or "euler")
                scheduler = str(state.get("sam3_scheduler") or payload.get("scheduler") or "normal")
                if scheduler.casefold() == "use same scheduler":
                    scheduler = str(payload.get("scheduler") or "normal")
                sampler, scheduler = self._runtime_sampler_values(sampler, scheduler)
                seed = _int(state.get("sam3_seed"), -1) if _bool(state.get("sam3_use_seed")) else _int(payload.get("seed"), -1)
                if seed < 0:
                    seed = random.randint(0, 2**32 - 1)
                detail = graph.add(sam3_detailer_class, {
                    "image": image, "mask": [mask_node, 0], "model": model, "clip": clip, "vae": vae,
                    "positive": positive, "negative": negative,
                    "inpaint_prompt": str(state.get("sam3_inpaint_prompt") or ""),
                    "negative_prompt": str(state.get("sam3_negative_prompt") or ""),
                    "mask_mode": str(state.get("sam3_mask_mode") or "Individual"),
                    "seed": seed,
                    "steps": _int(state.get("sam3_steps"), _int(payload.get("steps"), 28)) if _bool(state.get("sam3_use_steps")) else _int(payload.get("steps"), 28),
                    "cfg": _float(state.get("sam3_cfg_scale"), _float(payload.get("cfg_scale"), 7.0)) if _bool(state.get("sam3_use_cfg_scale")) else _float(payload.get("cfg_scale"), 7.0),
                    "sampler_name": sampler, "scheduler": scheduler,
                    "denoise": _float(state.get("sam3_denoising_strength"), 0.4),
                    "noise_multiplier": _float(state.get("sam3_noise_multiplier"), 1.0) if _bool(state.get("sam3_use_noise_multiplier")) else 1.0,
                    "fill_mode": str(state.get("sam3_inpainting_fill") or "original"),
                    "only_masked": _bool(state.get("sam3_inpaint_only_masked"), True),
                    "mask_padding": _int(state.get("sam3_inpaint_only_masked_padding"), 32),
                    "use_custom_size": _bool(state.get("sam3_use_inpaint_width_height")),
                    "custom_width": _int(state.get("sam3_inpaint_width"), 512),
                    "custom_height": _int(state.get("sam3_inpaint_height"), 512),
                    "grow_mask_by": max(0, _int(state.get("sam3_grow_mask_by"), 6)),
                    "controlnet_enable": _bool(state.get("sam3_cn_enable")),
                    "controlnet_model_name": str(state.get("sam3_cn_model") or "None"),
                    "controlnet_module": str(state.get("sam3_cn_module") or "inpaint_only"),
                    "controlnet_override_external": _bool(state.get("sam3_cn_override_external")),
                    "controlnet_strength": _float(state.get("sam3_cn_weight"), 1.0),
                    "controlnet_start": _float(state.get("sam3_cn_guidance_start"), 0.0),
                    "controlnet_end": _float(state.get("sam3_cn_guidance_end"), 1.0),
                    "controlnet_processor_resolution": max(0, _int(state.get("sam3_cn_processor_res"), 512)),
                    "controlnet_settings_json": json.dumps({
                        "pixel_perfect": _bool(state.get("sam3_cn_pixel_perfect"), True),
                        "control_mode": str(state.get("sam3_cn_control_mode") or "Balanced"),
                        "resize_mode": str(state.get("sam3_cn_resize_mode") or "Crop and Resize"),
                        "threshold_a": _float(state.get("sam3_cn_threshold_a"), -1.0),
                        "threshold_b": _float(state.get("sam3_cn_threshold_b"), -1.0),
                        "override_external": _bool(state.get("sam3_cn_override_external")),
                    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    "restore_face": _bool(state.get("sam3_restore_face")),
                    "restore_face_settings_json": json.dumps({
                        "detector_model": str(state.get("sam3_face_detector_model") or "bbox/face_yolov8m.pt"),
                        "guide_size": _int(state.get("sam3_face_guide_size"), 512),
                        "max_size": _int(state.get("sam3_face_max_size"), 1024),
                        "bbox_threshold": _float(state.get("sam3_face_bbox_threshold"), 0.5),
                        "bbox_dilation": _int(state.get("sam3_face_bbox_dilation"), 10),
                        "bbox_crop_factor": _float(state.get("sam3_face_bbox_crop_factor"), 3.0),
                        "denoise": _float(state.get("sam3_face_denoise"), 0.4),
                        "feather": _int(state.get("sam3_face_feather"), 5),
                        "cycle": _int(state.get("sam3_face_cycle"), 1),
                    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    "enabled": True,
                }, "SAM3 detailer")
                image = [detail, 0]
        return image

    # ---- custom workflow ----------------------------------------------

    def _compile_custom(
        self, mode: str, model_name: str, payload: dict, loras: Sequence[LoraSpec],
        workflow: Mapping[str, Any], *, uploaded_image: str, uploaded_mask: str,
    ) -> dict:
        graph = _Graph(workflow)
        sampler_id = self._find_sampler(graph.nodes)
        sampler = graph.nodes[sampler_id]
        inputs = sampler.setdefault("inputs", {})
        self._map_sampler_inputs(inputs, sampler.get("class_type", ""), payload, mode=mode)
        batch = max(1, _int(payload.get("batch_size"), 1)) * max(
            1, _int(payload.get("n_iter", payload.get("batch_count", 1)), 1)
        )
        latent_ids = self._trace_classes(
            graph.nodes, inputs.get("latent_image"), {"EmptyLatentImage"},
        )
        if len(latent_ids) > 1:
            raise WorkflowCompileError(
                "custom workflow의 sampler latent 분기에 EmptyLatentImage가 여러 개입니다."
            )
        if latent_ids:
            latent_id = latent_ids[0]
            latent_inputs = graph.nodes[latent_id].setdefault("inputs", {})
            latent_inputs["width"] = max(64, _int(payload.get("width"), 512))
            latent_inputs["height"] = max(64, _int(payload.get("height"), 512))
            latent_inputs["batch_size"] = batch

        if model_name:
            loader_id = self._trace_model_loader(graph.nodes, inputs.get("model"))
            if not loader_id:
                raise WorkflowCompileError(
                    "custom workflow sampler의 upstream CheckpointLoaderSimple/UNETLoader를 찾지 못했습니다."
                )
            loader = graph.nodes[loader_id]
            loader_type = str(loader.get("class_type") or "")
            loader_input = "ckpt_name" if loader_type == "CheckpointLoaderSimple" else "unet_name"
            loader.setdefault("inputs", {})[loader_input] = self._resolve_choice(
                loader_type, loader_input, model_name,
            )

        pos_ids = self._trace_classes(
            graph.nodes, inputs.get("positive"), {"CLIPTextEncode", "CLIPTextEncodeSDXL"},
        )
        neg_ids = self._trace_classes(
            graph.nodes, inputs.get("negative"), {"CLIPTextEncode", "CLIPTextEncodeSDXL"},
        )
        if len(pos_ids) != 1 or len(neg_ids) != 1:
            raise WorkflowCompileError(
                "custom workflow의 positive/negative CLIPTextEncode 연결은 각각 하나여야 합니다."
            )
        pos_id, neg_id = pos_ids[0], neg_ids[0]
        self._set_encode_text(graph.nodes[pos_id], str(payload.get("prompt") or ""))
        self._set_encode_text(graph.nodes[neg_id], str(payload.get("negative_prompt") or ""))
        model = inputs.get("model")
        positive, negative = inputs.get("positive"), inputs.get("negative")
        if not (_is_link(model) and _is_link(positive) and _is_link(negative)):
            raise WorkflowCompileError("custom workflow sampler의 model/positive/negative 연결이 유효하지 않습니다.")
        pos_clip = graph.nodes[pos_id].get("inputs", {}).get("clip")
        neg_clip = graph.nodes[neg_id].get("inputs", {}).get("clip")
        if not (_is_link(pos_clip) and _is_link(neg_clip)):
            raise WorkflowCompileError("custom workflow CLIP 연결을 찾지 못했습니다.")
        if pos_clip != neg_clip and (loras or self._script(payload, "NegPiP")):
            raise WorkflowCompileError("서로 다른 positive/negative CLIP을 쓰는 custom workflow에는 LoRA/NegPiP를 자동 삽입할 수 없습니다.")
        clip = pos_clip

        decode_id = self._find_decode_after(graph.nodes, sampler_id)
        vae = self._find_vae_link_for_branch(
            graph.nodes, inputs.get("latent_image"), decode_id,
        ) or self._infer_vae_from_model(graph.nodes, model)
        needs_vae = (
            mode != "txt2img"
            or _bool(payload.get("enable_hr"))
            or self._has_image_scripts(payload)
        )
        if needs_vae and not _is_link(vae):
            raise WorkflowCompileError("custom workflow의 VAE 연결을 찾지 못했습니다.")
        override_vae = self._override_custom_modules(
            graph, payload, pos_id, neg_id, decode_id, inputs.get("latent_image"),
        )
        # Overrides can replace encoder/VAE links.
        clip = graph.nodes[pos_id].get("inputs", {}).get("clip", clip)
        vae = override_vae or vae or []

        shift = _float(payload.get("distilled_cfg_scale"), 0.0)
        if shift > 0:
            shift_node = graph.add("ModelSamplingSD3", {
                "model": model, "shift": shift,
            }, "Forge distilled CFG shift")
            model = [shift_node, 0]
        model, clip = self._add_loras(graph, model, clip, loras)
        model, clip = self._add_negpip(graph, model, clip, payload)
        graph.nodes[pos_id]["inputs"]["clip"] = clip
        graph.nodes[neg_id]["inputs"]["clip"] = clip
        model, sampler_options = self._add_anima_guidance(
            graph, model, clip, positive, negative, payload,
        )
        inputs["model"] = model

        if mode != "txt2img":
            if not uploaded_image:
                raise WorkflowCompileError(f"{mode} 입력 이미지가 업로드되지 않았습니다.")
            latent = self._add_latent(
                graph, mode, vae, payload,
                uploaded_image=uploaded_image, uploaded_mask=uploaded_mask,
            )
            inputs["latent_image"] = latent
        if sampler_options.get("cns_enabled") or _bool(payload.get("spectrum_enabled")) or _bool(payload.get("speed_enabled")):
            # Replace only standard KSampler; exotic custom samplers remain user-owned.
            if sampler.get("class_type") == "KSampler":
                sampler["class_type"] = "ForgeNeoKSamplerCNS"
            elif sampler.get("class_type") != "ForgeNeoKSamplerCNS":
                raise WorkflowCompileError("CNS/Spectrum/SPEED 자동 삽입은 KSampler custom workflow에서만 지원됩니다.")
            for key, default in {
                "cns_enabled": False, "cns_strength": 1.0, "cns_gamma_power": 0.5, "cns_gamma_scale": 3.0,
                "spectrum_enabled": False, "spectrum_window_size": 2.0, "spectrum_flex_window": 0.25,
                "spectrum_warmup_steps": 6, "spectrum_tail_actual_steps": 3, "spectrum_blend_w": 0.3,
                "spectrum_cheby_degree": 3, "spectrum_ridge_lambda": 0.1, "spectrum_history_size": 100,
                "spectrum_one_sampler_only": False, "spectrum_verbose": False,
                "speed_enabled": False, "speed_split_mode": "single", "speed_spd_scale": 0.5,
                "speed_spd_sigma": 0.7, "speed_adaptive_smc_alpha": 0.0,
            }.items():
                inputs[key] = sampler_options.get(key, payload.get(key, default))

        if not decode_id:
            if _bool(payload.get("enable_hr")) or self._has_image_scripts(payload):
                raise WorkflowCompileError("Hires/ADetailer/SAM3 삽입에 필요한 VAEDecode를 custom workflow에서 찾지 못했습니다.")
            return graph.nodes
        decode = graph.nodes[decode_id]
        samples = decode.get("inputs", {}).get("samples")
        if not _is_link(samples):
            raise WorkflowCompileError("custom workflow VAEDecode의 samples 연결이 유효하지 않습니다.")
        if _bool(payload.get("enable_hr")):
            samples, decode_vae = self._add_hires(
                graph, model, clip, vae, positive, negative, samples, payload,
                sampler_options=sampler_options,
            )
            decode.setdefault("inputs", {})["samples"] = samples
            decode["inputs"]["vae"] = decode_vae
        if self._has_image_scripts(payload):
            outputs = self._find_outputs_after(graph.nodes, decode_id)
            if not outputs:
                raise WorkflowCompileError(
                    "ADetailer/SAM3 삽입 대상인 custom workflow 출력 노드를 찾지 못했습니다."
                )
            source_links = {tuple(link[:2]) for _node_id, _key, link in outputs}
            if len(source_links) != 1:
                raise WorkflowCompileError(
                    "custom workflow의 선택 분기에 서로 다른 이미지 출력이 여러 개입니다. "
                    "ADetailer/SAM3 자동 삽입 대상을 하나로 줄여주세요."
                )
            image = list(next(iter(source_links)))
            post = self._add_image_extensions(
                graph, image, model, clip, vae, positive, negative, payload,
            )
            if post != image:
                for output_id, key, _source in outputs:
                    graph.nodes[output_id].setdefault("inputs", {})[key] = post
        return graph.nodes

    # ---- small helpers -------------------------------------------------

    def _map_sampler_inputs(
        self, inputs: dict, class_type: str, payload: Mapping[str, Any], *, mode: str,
    ) -> None:
        if class_type in {"SamplerCustom", "SamplerCustomAdvanced"}:
            raise WorkflowCompileError(
                f"{class_type} custom workflow는 Forge payload의 steps/CFG/denoise를 "
                "안전하게 자동 매핑할 수 없습니다. KSampler/KSamplerAdvanced를 쓰거나 "
                "완성된 그래프를 run_workflow로 실행하세요."
            )
        seed = _int(payload.get("seed"), -1)
        if seed < 0:
            seed = random.randint(0, 2**32 - 1)
        inputs["noise_seed" if class_type == "KSamplerAdvanced" else "seed"] = seed
        steps = max(1, _int(payload.get("steps"), 20))
        inputs["steps"] = steps
        inputs["cfg"] = _float(payload.get("cfg_scale"), 7.0)
        sampler, scheduler = self._runtime_sampler_values(
            payload.get("sampler_name") or "euler",
            payload.get("scheduler") or "normal",
        )
        inputs["sampler_name"] = sampler
        inputs["scheduler"] = scheduler
        denoise = (
            1.0 if mode == "txt2img" else
            max(0.0, min(1.0, _float(payload.get("denoising_strength"), 0.75)))
        )
        if class_type == "KSamplerAdvanced":
            inputs["add_noise"] = "enable"
            inputs["start_at_step"] = max(0, steps - int(steps * denoise))
            inputs["end_at_step"] = steps
            inputs["return_with_leftover_noise"] = "disable"
        else:
            inputs["denoise"] = denoise

    @staticmethod
    def _set_encode_text(node: dict, text: str) -> None:
        inputs = node.setdefault("inputs", {})
        if node.get("class_type") == "CLIPTextEncodeSDXL":
            inputs["text_g"] = text
            inputs["text_l"] = text
        else:
            inputs["text"] = text

    def _override_custom_modules(
        self,
        graph: _Graph,
        payload: Mapping[str, Any],
        pos_id: str,
        neg_id: str,
        decode_id: Optional[str],
        latent_link: Any,
    ) -> Optional[list]:
        modules = self._module_names(payload)
        if not modules:
            return None
        clips, vaes, unknown = self._classify_modules(modules)
        if unknown or not clips or len(vaes) != 1:
            details = unknown or [f"TE={len(clips)}, VAE={len(vaes)}"]
            raise WorkflowCompileError("custom workflow additional modules 매핑 실패: " + ", ".join(details))
        clip_ref = self._add_clip_loader(graph, clips, payload)
        vae_name = self._resolve_choice("VAELoader", "vae_name", vaes[0])
        vae_node = graph.add("VAELoader", {"vae_name": vae_name}, "VAE override")
        graph.nodes[pos_id].setdefault("inputs", {})["clip"] = clip_ref
        graph.nodes[neg_id].setdefault("inputs", {})["clip"] = clip_ref
        vae_ref = [vae_node, 0]
        if decode_id:
            graph.nodes[decode_id].setdefault("inputs", {})["vae"] = vae_ref
        latent_vae_id = self._trace_class(
            graph.nodes,
            latent_link,
            {"VAEEncode", "VAEEncodeForInpaint", "ForgeNeoLatentInput"},
        )
        if latent_vae_id:
            graph.nodes[latent_vae_id].setdefault("inputs", {})["vae"] = vae_ref
        return vae_ref

    def _module_names(self, payload: Mapping[str, Any]) -> list[str]:
        raw = payload.get("forge_additional_modules", [])
        if isinstance(raw, str):
            raw = [item.strip() for item in raw.split(",")]
        if not isinstance(raw, Iterable) or isinstance(raw, (bytes, bytearray, Mapping)):
            return []
        return [_filename(item) for item in raw if _filename(item) and str(item).casefold() != "use same choices"]

    def _classify_modules(self, modules: Sequence[str]) -> tuple[list[str], list[str], list[str]]:
        clip_choices = self._choices("CLIPLoader", "clip_name")
        vae_choices = self._choices("VAELoader", "vae_name")
        clips: list[str] = []
        vaes: list[str] = []
        unknown: list[str] = []
        for item in modules:
            clip = self._match_choice(item, clip_choices)
            vae = self._match_choice(item, vae_choices)
            if vae is not None and (clip is None or "vae" in item.casefold()):
                vaes.append(vae)
            elif clip is not None:
                clips.append(clip)
            elif self.object_info is None:
                (vaes if "vae" in item.casefold() else clips).append(item)
            else:
                unknown.append(item)
        return clips, vaes, unknown

    def _hr_module(self, payload: Mapping[str, Any], kind: str) -> str:
        raw = payload.get("hr_additional_modules", [])
        if isinstance(raw, str):
            raw = [item.strip() for item in raw.split(",")]
        items = [_filename(item) for item in raw if _filename(item)] if isinstance(raw, Sequence) else []
        if not items or any(item.casefold() == "use same choices" for item in items):
            return "Use same choices"
        clips, vaes, unknown = self._classify_modules(items)
        if unknown:
            raise WorkflowCompileError("Hires additional modules 매핑 실패: " + ", ".join(unknown))
        if kind == "vae":
            if len(vaes) > 1:
                raise WorkflowCompileError("Hires VAE는 한 개만 지정할 수 있습니다.")
            return vaes[0] if vaes else "Use same choices"
        if len(clips) > 1:
            raise WorkflowCompileError("ForgeNeoHiresFix text_encoder_name은 한 개만 지원합니다.")
        return clips[0] if clips else "Use same choices"

    def _choices(self, class_type: str, input_name: str) -> Optional[list[str]]:
        if self.object_info is None:
            return None
        node = self.object_info.get(class_type)
        if not isinstance(node, Mapping):
            return []
        input_doc = node.get("input", {})
        for section in ("required", "optional"):
            spec = input_doc.get(section, {}).get(input_name) if isinstance(input_doc, Mapping) else None
            if isinstance(spec, (list, tuple)) and spec and isinstance(spec[0], (list, tuple)):
                return [str(item) for item in spec[0]]
        return []

    @staticmethod
    def _match_choice(requested: Any, choices: Optional[Sequence[str]]) -> Optional[str]:
        if choices is None:
            return str(requested or "").strip() or None
        value = str(requested or "").strip()
        if not value:
            return None
        folded = value.replace("\\", "/").casefold()
        basename = _filename(value).casefold()
        stem = os.path.splitext(basename)[0]
        for choice in choices:
            normalized = str(choice).replace("\\", "/")
            choice_base = _filename(normalized).casefold()
            if (
                normalized.casefold() == folded
                or choice_base == basename
                or (stem and os.path.splitext(choice_base)[0] == stem)
            ):
                return str(choice)
        return None

    def _resolve_choice(self, class_type: str, input_name: str, requested: Any) -> str:
        value = str(requested or "").strip()
        if not value:
            raise WorkflowCompileError(f"{class_type}.{input_name} 값이 비어 있습니다.")
        choices = self._choices(class_type, input_name)
        matched = self._match_choice(value, choices)
        if matched is None:
            raise WorkflowCompileError(
                f"ComfyUI에서 {class_type}.{input_name} 리소스를 찾을 수 없습니다: {value}"
            )
        return matched

    def _resolve_when_enumerated(
        self, class_type: str, input_name: str, requested: Any,
    ) -> str:
        """Normalize a combo value when the live node publishes its choices.

        Tests and offline callers may provide a class-only capability document;
        in that case there is nothing to resolve and normal class validation is
        still useful.  A live /object_info response always carries the choices.
        """
        value = str(requested or "").strip()
        choices = self._choices(class_type, input_name)
        if not choices:
            return value
        matched = self._match_choice(value, choices)
        if matched is None:
            raise WorkflowCompileError(
                f"ComfyUI에서 {class_type}.{input_name} 값을 지원하지 않습니다: {value}"
            )
        return matched

    @staticmethod
    def _script(payload: Mapping[str, Any], wanted: str) -> Optional[Mapping[str, Any]]:
        scripts = payload.get("alwayson_scripts", {})
        if not isinstance(scripts, Mapping):
            return None
        folded = wanted.casefold()
        for name, block in scripts.items():
            if str(name).casefold() == folded and isinstance(block, Mapping):
                return block
        return None

    @staticmethod
    def _script_settings(block: Mapping[str, Any], spec: Sequence[tuple]) -> dict[str, Any]:
        args = block.get("args", []) if isinstance(block, Mapping) else []
        if isinstance(args, Mapping):
            return dict(args)
        values = list(args) if isinstance(args, (list, tuple)) else []
        return {
            item[0]: values[index] if index < len(values) else item[2]
            for index, item in enumerate(spec)
        }

    @staticmethod
    def _fit_mode(resize_mode: Any) -> str:
        raw = str(resize_mode if resize_mode is not None else "crop").strip().casefold()
        return {
            "0": "stretch", "just resize": "stretch", "stretch": "stretch",
            "1": "crop", "crop and resize": "crop", "crop": "crop",
            "2": "contain", "resize and fill": "contain", "contain": "contain",
        }.get(raw, "crop")

    @staticmethod
    def _comfy_sampler(value: Any) -> str:
        raw = str(value or "euler").strip()
        folded = re.sub(r"\s+", " ", raw).casefold()
        folded = re.sub(r"\s+karras$", "", folded)
        aliases = {
            "euler a": "euler_ancestral", "euler ancestral": "euler_ancestral",
            "dpm++ 2m": "dpmpp_2m", "dpm++ 2m sde": "dpmpp_2m_sde",
            "dpm++ sde": "dpmpp_sde", "dpm++ 3m sde": "dpmpp_3m_sde",
            "dpm2 a": "dpm_2_ancestral", "dpm2": "dpm_2",
            "heun": "heun", "lms": "lms", "ddim": "ddim", "uni_pc": "uni_pc",
        }
        return aliases.get(folded, raw)

    @staticmethod
    def _comfy_scheduler(value: Any, *, sampler_text: str = "") -> str:
        raw = str(value or "normal").strip()
        if "karras" in str(sampler_text or "").casefold():
            return "karras"
        folded = raw.casefold()
        if folded in {"use same scheduler", "automatic", "auto"}:
            return "normal"
        return {
            "karras": "karras", "exponential": "exponential", "sgm uniform": "sgm_uniform",
            "simple": "simple", "normal": "normal", "ddim uniform": "ddim_uniform",
            "beta": "beta",
        }.get(folded, raw)

    def _runtime_sampler_values(self, sampler: Any, scheduler: Any) -> tuple[str, str]:
        original_sampler = str(sampler or "euler")
        sampler_value = self._comfy_sampler(original_sampler)
        scheduler_value = self._comfy_scheduler(scheduler, sampler_text=original_sampler)
        for input_name, value in (
            ("sampler_name", sampler_value), ("scheduler", scheduler_value),
        ):
            choices = self._choices("KSampler", input_name)
            if choices:
                matched = self._match_choice(value, choices)
                if matched is None:
                    raise WorkflowCompileError(
                        f"ComfyUI KSampler.{input_name}에서 지원하지 않는 값입니다: {value}"
                    )
                if input_name == "sampler_name":
                    sampler_value = matched
                else:
                    scheduler_value = matched
        return sampler_value, scheduler_value

    @staticmethod
    def _find_sampler(workflow: Mapping[str, Any]) -> str:
        candidates = [
            str(node_id) for node_id, node in workflow.items()
            if isinstance(node, Mapping) and node.get("class_type") in _SAMPLERS
        ]
        if not candidates:
            raise WorkflowCompileError("custom workflow에서 sampler 노드를 찾지 못했습니다.")
        if len(candidates) != 1:
            raise WorkflowCompileError(
                "custom workflow에 sampler 노드가 여러 개이므로 자동 삽입 대상이 불명확합니다: "
                + ", ".join(candidates)
            )
        return candidates[0]

    @staticmethod
    def _trace_classes(
        workflow: Mapping[str, Any], link: Any, wanted: set[str],
    ) -> list[str]:
        matches: list[str] = []
        visited: set[str] = set()

        def visit(value: Any, depth: int) -> None:
            if depth > 30 or not _is_link(value):
                return
            node_id = str(value[0])
            if node_id in visited:
                return
            node = workflow.get(node_id)
            if not isinstance(node, Mapping):
                return
            visited.add(node_id)
            if node.get("class_type") in wanted:
                matches.append(node_id)
                return
            for upstream in node.get("inputs", {}).values():
                visit(upstream, depth + 1)

        visit(link, 0)
        return matches

    @staticmethod
    def _trace_class(workflow: Mapping[str, Any], link: Any, wanted: set[str], depth: int = 0) -> Optional[str]:
        if depth:
            return None
        matches = ComfyWorkflowCompiler._trace_classes(workflow, link, wanted)
        return matches[0] if matches else None

    @staticmethod
    def _trace_model_loader(workflow: Mapping[str, Any], link: Any) -> Optional[str]:
        visited: set[str] = set()
        for _depth in range(31):
            if not _is_link(link):
                return None
            node_id = str(link[0])
            if node_id in visited:
                return None
            visited.add(node_id)
            node = workflow.get(node_id)
            if not isinstance(node, Mapping):
                return None
            if node.get("class_type") in {"CheckpointLoaderSimple", "UNETLoader"}:
                return node_id
            link = node.get("inputs", {}).get("model")
        return None

    @staticmethod
    def _find_vae_link_for_branch(
        workflow: Mapping[str, Any], latent_link: Any, decode_id: Optional[str],
    ) -> Optional[list]:
        if decode_id:
            decode = workflow.get(str(decode_id))
            if isinstance(decode, Mapping):
                value = decode.get("inputs", {}).get("vae")
                if _is_link(value):
                    return list(value)
        latent_nodes = ComfyWorkflowCompiler._trace_classes(
            workflow,
            latent_link,
            {"VAEEncode", "VAEEncodeForInpaint", "ForgeNeoLatentInput"},
        )
        vae_links = []
        for node_id in latent_nodes:
            value = workflow[node_id].get("inputs", {}).get("vae")
            if _is_link(value) and tuple(value[:2]) not in {
                tuple(item[:2]) for item in vae_links
            }:
                vae_links.append(list(value))
        if len(vae_links) > 1:
            raise WorkflowCompileError(
                "custom workflow의 선택 sampler latent 분기에 VAE 연결이 여러 개입니다."
            )
        return vae_links[0] if vae_links else None

    @staticmethod
    def _infer_vae_from_model(
        workflow: Mapping[str, Any], model_link: Any, depth: int = 0,
    ) -> Optional[list]:
        if depth > 30 or not _is_link(model_link):
            return None
        node_id = str(model_link[0])
        node = workflow.get(node_id)
        if not isinstance(node, Mapping):
            return None
        if node.get("class_type") in {"CheckpointLoaderSimple", "CheckpointLoader"}:
            return [node_id, 2]
        if node.get("class_type") == "VAELoader":
            return [node_id, 0]
        upstream = node.get("inputs", {}).get("model")
        return ComfyWorkflowCompiler._infer_vae_from_model(workflow, upstream, depth + 1)

    @staticmethod
    def _find_decode_after(workflow: Mapping[str, Any], sampler_id: str) -> Optional[str]:
        decoders = [
            str(node_id)
            for node_id, node in workflow.items()
            if isinstance(node, Mapping)
            and node.get("class_type") == "VAEDecode"
            and ComfyWorkflowCompiler._link_depends_on(
                workflow, node.get("inputs", {}).get("samples"), sampler_id,
            )
        ]
        if len(decoders) > 1:
            raise WorkflowCompileError(
                "custom workflow의 sampler 출력에 연결된 VAEDecode가 여러 개입니다: "
                + ", ".join(decoders)
            )
        return decoders[0] if decoders else None

    @staticmethod
    def _link_depends_on(
        workflow: Mapping[str, Any], link: Any, ancestor_id: str,
        visited: Optional[set[str]] = None,
    ) -> bool:
        if not _is_link(link):
            return False
        node_id = str(link[0])
        if node_id == str(ancestor_id):
            return True
        node = workflow.get(node_id)
        if not isinstance(node, Mapping):
            return False
        seen = set() if visited is None else visited
        if node_id in seen:
            return False
        seen.add(node_id)
        return any(
            ComfyWorkflowCompiler._link_depends_on(
                workflow, upstream, ancestor_id, seen,
            )
            for upstream in node.get("inputs", {}).values()
        )

    @staticmethod
    def _find_outputs_after(
        workflow: Mapping[str, Any], ancestor_id: str,
    ) -> list[tuple[str, str, list]]:
        outputs: list[tuple[str, str, list]] = []
        for node_id, node in workflow.items():
            if not isinstance(node, Mapping) or node.get("class_type") not in _SAVE_NODES:
                continue
            inputs = node.get("inputs", {})
            if not isinstance(inputs, Mapping):
                continue
            key = "images" if "images" in inputs else "image" if "image" in inputs else ""
            link = inputs.get(key) if key else None
            if _is_link(link) and ComfyWorkflowCompiler._link_depends_on(
                workflow, link, ancestor_id,
            ):
                outputs.append((str(node_id), key, list(link)))
        return outputs

    @staticmethod
    def _has_image_scripts(payload: Mapping[str, Any]) -> bool:
        return bool(
            ComfyWorkflowCompiler._adetailer_slots(payload)
            or ComfyWorkflowCompiler._sam3_state(payload) is not None
        )

    @staticmethod
    def _adetailer_slots(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        block = ComfyWorkflowCompiler._script(payload, "ADetailer")
        args = block.get("args", []) if isinstance(block, Mapping) else []
        if not isinstance(args, (list, tuple)) or not args or not _bool(args[0], True):
            return []
        return [
            item for item in list(args)[2:]
            if isinstance(item, Mapping) and _bool(item.get("ad_tab_enable"), True)
        ]

    @staticmethod
    def _sam3_state(payload: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        block = ComfyWorkflowCompiler._script(payload, "SAM3 Mask")
        args = block.get("args", []) if isinstance(block, Mapping) else []
        if not isinstance(args, (list, tuple)) or not args or not isinstance(args[0], Mapping):
            return None
        state = args[0]
        enabled = state.get("sam3_enable", state.get("enabled", True))
        return state if _bool(enabled, True) else None

    @staticmethod
    def _validate_adetailer_slot(slot: Mapping[str, Any], index: int) -> None:
        unsupported: list[str] = []
        for key, label in (
            ("ad_hires_fix_only", "Hires-only"),
            ("ad_use_autotag", "autotag"),
            ("ad_copy_main_lora_triggers", "LoRA trigger copy"),
            ("ad_copy_main_lora_triggers_only", "LoRA trigger-only copy"),
            ("ad_use_checkpoint", "separate checkpoint"),
            ("ad_use_vae", "separate VAE"),
            ("ad_use_noise_multiplier", "noise multiplier"),
            ("ad_use_clip_skip", "CLIP skip"),
            ("ad_restore_face", "restore face"),
        ):
            if _bool(slot.get(key)):
                unsupported.append(label)
        if str(slot.get("ad_model_classes") or "").strip():
            unsupported.append("model class filter")
        if str(slot.get("ad_mask_filter_method") or "Area") != "Area":
            unsupported.append("mask filter")
        if _int(slot.get("ad_mask_k"), 0) != 0:
            unsupported.append("mask K")
        if _float(slot.get("ad_mask_min_ratio"), 0.0) != 0.0:
            unsupported.append("minimum mask ratio")
        if _float(slot.get("ad_mask_max_ratio"), 1.0) != 1.0:
            unsupported.append("maximum mask ratio")
        if _int(slot.get("ad_x_offset"), 0) != 0 or _int(slot.get("ad_y_offset"), 0) != 0:
            unsupported.append("mask offset")
        if str(slot.get("ad_mask_merge_invert") or "None") != "None":
            unsupported.append("mask merge/invert")
        if _float(slot.get("ad_inpaint_scale"), 1.0) != 1.0:
            unsupported.append("inpaint scale")
        control_model = str(slot.get("ad_controlnet_model") or "None").strip().casefold()
        control_module = str(slot.get("ad_controlnet_module") or "None").strip().casefold()
        if control_model not in {"", "none"} or control_module not in {"", "none"}:
            unsupported.append("ControlNet")
        if unsupported:
            raise WorkflowCompileError(
                f"ADetailer 슬롯 {index}의 설정은 현재 ComfyUI 노드로 표현할 수 없습니다: "
                + ", ".join(unsupported)
            )

    @staticmethod
    def _validate_anima_guidance_settings(settings: Mapping[str, Any]) -> None:
        if _bool(settings.get("guid_enabled")):
            method = str(settings.get("guid_attn_method") or "PAG").strip().casefold()
            if method not in {"pag", "seg", "none", "off", ""}:
                raise WorkflowCompileError(f"지원하지 않는 Anima attention 방식입니다: {method}")
            if method in {"pag", "seg"} and _bool(settings.get("guid_legacy_attn")):
                raise WorkflowCompileError(
                    "Anima legacy attention은 ComfyUI pre-projection hook으로 표현할 수 없습니다."
                )
            if method in {"pag", "seg"} and str(settings.get("guid_head_indices") or "").strip():
                raise WorkflowCompileError(
                    "Anima head-selective PAG/SEG는 ComfyUI에서 지원되지 않습니다."
                )
        cfg_mode = str(
            settings.get("guid_cfg_mode") or "Preserve incoming"
        ).strip().casefold()
        if cfg_mode not in {
            "preserve incoming", "preserve", "apg", "cwm", "smc",
            "smc + cwm", "smc+cwm",
        }:
            raise WorkflowCompileError(f"지원하지 않는 Anima CFG 방식입니다: {cfg_mode}")
        if _bool(settings.get("guid_mod_enabled")):
            adapter_mode = str(
                settings.get("guid_mod_adapter_mode") or "Auto-download official"
            ).strip().casefold()
            if adapter_mode == "local file" and not str(
                settings.get("guid_mod_adapter_path") or ""
            ).strip():
                raise WorkflowCompileError(
                    "Anima modulation Local file 모드에는 adapter path가 필요합니다."
                )
            if adapter_mode not in {"local file", "auto-download official"}:
                raise WorkflowCompileError(
                    f"지원하지 않는 Anima modulation adapter 방식입니다: {adapter_mode}"
                )


__all__ = [
    "ComfyWorkflowCompiler", "LoraSpec", "WorkflowCompileError", "parse_lora_tags",
]
