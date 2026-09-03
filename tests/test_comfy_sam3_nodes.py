from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch

from comfy_custom_nodes.ai_studio_forge_parity import mask_ops
from comfy_custom_nodes.ai_studio_forge_parity import sam3_nodes


def _image(batch=1, height=12, width=14, value=0.0):
    return torch.full((batch, height, width, 3), value, dtype=torch.float32)


class _FakeModel:
    def __init__(self):
        self.targets = []

    def to(self, target):
        self.targets.append(str(target))
        return self


class _FakeSegmenter:
    calls = []

    @classmethod
    def execute(cls, sam3_model, images, prompt, threshold=0.3,
                keep_model_loaded=False, add_background="none", detection_limit=-1,
                coordinates_positive=None, coordinates_negative=None, bboxes=None,
                mask=None):
        cls.calls.append((prompt, threshold, detection_limit, keep_model_loaded))
        output = torch.zeros((images.shape[0], images.shape[1], images.shape[2]))
        locations = {"face": (1, 1), "eyes": (2, 2), "hand": (7, 7), "protect": (1, 1)}
        y, x = locations[prompt]
        output[:, y:y + 2, x:x + 2] = 1
        return output, images, output[:, None], [[[x, y, x + 2, y + 2]]], [[0.9]]


class TestComfySam3Nodes(unittest.TestCase):
    def test_prompt_grammar_preserves_or_and_sequential_groups(self):
        self.assertEqual(
            mask_ops.split_prompt_groups(" face, eyes | hair / hand; fingers\narm "),
            [["face", "eyes", "hair"], ["hand", "fingers", "arm"]],
        )
        self.assertEqual(mask_ops.split_prompt_groups(" / , ; \n"), [])

    def test_ensure_mask_resizes_and_broadcasts_without_batch_guessing(self):
        source = torch.tensor([[0.0, 1.0], [1.0, 0.0]])
        result = mask_ops.ensure_mask(source, height=4, width=6, batch=2)
        self.assertEqual(result.shape, (2, 4, 6))
        self.assertTrue(torch.equal(result[0], result[1]))
        with self.assertRaisesRegex(ValueError, "does not match IMAGE batch"):
            mask_ops.ensure_mask(torch.zeros((3, 4, 6)), batch=2)

    def test_refine_order_matches_forge_extension(self):
        calls = []

        def stage(name):
            def apply(value, *args, **kwargs):
                calls.append(name)
                return value
            return apply

        with (
            mock.patch.object(mask_ops, "convex_hull", side_effect=stage("hull")),
            mock.patch.object(mask_ops, "edge_aware_outline", side_effect=stage("outline")),
            mock.patch.object(mask_ops, "dilate", side_effect=stage("dilation")),
        ):
            mask_ops.refine_generated_mask(
                torch.zeros((1, 4, 4)), _image(height=4, width=4),
                use_convex_hull=True, outline_pixels=2, dilation_pixels=3,
            )
        self.assertEqual(calls, ["hull", "outline", "dilation"])

    def test_real_convex_hull_dilation_and_blur_preserve_shape(self):
        source = torch.zeros((1, 9, 9))
        source[0, 2, 2:7] = 1
        source[0, 2:7, 2] = 1
        hull = mask_ops.convex_hull(source)
        expanded = mask_ops.dilate(hull, 1)
        blurred = mask_ops.gaussian_blur(expanded, 2)
        self.assertEqual(blurred.shape, source.shape)
        self.assertGreater(hull.sum().item(), source.sum().item())
        self.assertGreater(expanded.sum().item(), hull.sum().item())
        self.assertGreater(blurred[0, 0, 0].item(), 0.0)
        self.assertLessEqual(blurred.max().item(), 1.0)

    def test_intersection_falls_back_to_manual_per_image(self):
        generated = torch.zeros((2, 6, 6))
        generated[0, 1:4, 1:4] = 1
        manual = torch.zeros((2, 6, 6))
        manual[0, 2:5, 2:5] = 1
        manual[1, 4:6, 4:6] = 1
        selected = mask_ops.select_mask_groups(
            [generated], manual, "intersection",
            reference=_image(batch=2, height=6, width=6),
        )[0]
        self.assertEqual(selected[0].sum().item(), 4)
        self.assertTrue(torch.equal(selected[1], manual[1]))

    def test_exclusion_then_invert_keeps_combined_semantics(self):
        first = torch.zeros((1, 5, 5))
        second = torch.zeros((1, 5, 5))
        protected = torch.zeros((1, 5, 5))
        first[:, 1:3, 1:3] = 1
        second[:, 3:5, 3:5] = 1
        protected[:, 1, 1] = 1
        groups = mask_ops.subtract_exclusion([first, second], protected)
        combined, individual = mask_ops.finish_masks(
            groups, _image(height=5, width=5), blur_pixels=0, invert=True
        )
        self.assertEqual(individual.shape, (2, 5, 5))
        self.assertEqual(combined[0, 1, 1].item(), 1)
        self.assertEqual(combined[0, 2, 2].item(), 0)
        self.assertEqual(combined[0, 4, 4].item(), 0)

    def test_empty_detection_is_not_inverted_into_a_full_image_mask(self):
        source = _image(height=5, width=7)
        combined, individual = mask_ops.finish_masks(
            [], source, blur_pixels=0, invert=True
        )
        self.assertEqual(combined.sum().item(), 0)
        self.assertEqual(individual.sum().item(), 0)

        combined, individual = mask_ops.finish_masks(
            [torch.zeros((1, 5, 7))], source, blur_pixels=0, invert=True
        )
        self.assertEqual(combined.sum().item(), 0)
        self.assertEqual(individual.sum().item(), 0)

    def test_mask_node_runs_or_groups_sequential_groups_and_exclusion(self):
        _FakeSegmenter.calls = []
        with mock.patch.object(sam3_nodes, "_resolve_easy_node", return_value=_FakeSegmenter):
            result = sam3_nodes.ForgeNeoSAM3Mask().segment(
                _image(height=10, width=10), prompt="face, eyes / hand",
                exclude_prompt="protect", mask_mode="Individual",
                mask_source="generated", threshold=0.55, detection_limit=3,
                mask_blur=0, save_artifacts=False, unload_after=False,
                sam3_model={"model": _FakeModel(), "device": "cpu", "segmentor": "image"},
            )
        selected, combined, individual, overlay, boxes, scores, report_json = result
        self.assertEqual([call[0] for call in _FakeSegmenter.calls], ["face", "eyes", "hand", "protect"])
        self.assertTrue(all(call[1:3] == (0.55, 3) for call in _FakeSegmenter.calls))
        self.assertEqual(selected.shape, individual.shape)
        self.assertEqual(selected.shape, (2, 10, 10))
        self.assertEqual(combined.shape, (1, 10, 10))
        self.assertEqual(combined[0, 1, 1].item(), 0)
        self.assertEqual(combined[0, 3, 3].item(), 1)
        self.assertEqual(overlay.shape, (1, 10, 10, 3))
        self.assertEqual(boxes, [[1.0, 1.0, 3.0, 3.0], [2.0, 2.0, 4.0, 4.0], [7.0, 7.0, 9.0, 9.0]])
        self.assertEqual(scores, [0.9, 0.9, 0.9])
        self.assertEqual(json.loads(report_json)["prompt_groups"], [["face", "eyes"], ["hand"]])

    def test_easy_sam3_adapter_invokes_each_batch_image_independently(self):
        class UnevenProvider:
            calls = []

            @classmethod
            def execute(cls, sam3_model, images, prompt, **kwargs):
                cls.calls.append(tuple(images.shape))
                self_mask = torch.zeros((1, images.shape[1], images.shape[2]))
                if float(images.mean()) > 0.5:
                    self_mask[:, 2:4, 3:6] = 1
                    boxes, scores = [[[[3, 2, 6, 4]]]], [[[0.75]]]
                else:
                    # Current Easy-SAM3 no-detection sentinel.
                    boxes, scores = [[[[0, 0, 0, 0]]]], [[[0.0]]]
                return self_mask, images, self_mask[:, None], boxes, scores

        batch = torch.cat([
            _image(height=8, width=9, value=0.0),
            _image(height=8, width=9, value=1.0),
        ])
        detected, boxes, scores = sam3_nodes._detect_token(
            UnevenProvider, object(), batch, "face", 0.4, -1
        )
        self.assertEqual(UnevenProvider.calls, [(1, 8, 9, 3), (1, 8, 9, 3)])
        self.assertEqual(tuple(detected.shape), (2, 8, 9))
        self.assertEqual(detected[0].sum().item(), 0)
        self.assertEqual(detected[1].sum().item(), 6)
        self.assertEqual(boxes, [[3.0, 2.0, 6.0, 4.0]])
        self.assertEqual(scores, [0.75])

    def test_manual_mask_mode_does_not_require_easy_sam3(self):
        manual = torch.zeros((1, 8, 8))
        manual[:, 2:6, 2:6] = 1
        with mock.patch.object(
            sam3_nodes, "_resolve_easy_node", side_effect=AssertionError("provider should not load")
        ):
            result = sam3_nodes.ForgeNeoSAM3Mask().segment(
                _image(height=8, width=8), prompt="", mask_source="manual",
                manual_mask=manual, mask_blur=0, save_artifacts=False,
            )
        self.assertTrue(torch.equal(result[0], manual))
        self.assertEqual(json.loads(result[-1])["mask_source"], "manual")

    def test_enabled_detection_fails_clearly_without_easy_provider(self):
        with mock.patch.object(sam3_nodes, "_node_mappings", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "Easy SAM3.*not installed/loaded"):
                sam3_nodes._resolve_easy_node(
                    sam3_nodes._EASY_SEGMENTATION_KEYS, "image segmentation"
                )

    def test_unknown_controlnet_module_and_unknown_settings_fail_fast(self):
        with self.assertRaisesRegex(ValueError, "Unknown ControlNet module"):
            sam3_nodes._prepare_control_hint(
                _image(), torch.ones((1, 12, 14)), "not_a_real_module", 512, -1, -1
            )
        with self.assertRaisesRegex(ValueError, "Unknown controlnet_settings_json keys"):
            sam3_nodes._settings_object(
                '{"typo": true}', sam3_nodes._CONTROLNET_EXTRA_DEFAULTS,
                "controlnet_settings_json",
            )

    def test_override_external_control_copies_and_strips_metadata(self):
        tensor = object()
        source = [[tensor, {"control": "old", "control_apply_to_uncond": True, "pooled_output": "keep"}]]
        result = sam3_nodes._without_existing_control(source)
        self.assertIs(result[0][0], tensor)
        self.assertEqual(result[0][1], {"pooled_output": "keep"})
        self.assertIn("control", source[0][1])

    def test_controlnet_control_priority_uses_advanced_provider_and_keeps_negative_uncontrolled(self):
        calls = []

        class FakeApply:
            @classmethod
            def apply_controlnet(cls, **kwargs):
                calls.append(kwargs)
                return "conditioned-positive", "conditioned-negative"

        with mock.patch.object(
            sam3_nodes, "_node_mappings",
            return_value={"ControlNetApplyAdvanced": FakeApply},
        ):
            positive, negative, report = sam3_nodes._apply_controlnet(
                "positive", "negative", object(), _image(), 1.0, 0.1, 0.9,
                object(), "ControlNet is more important",
            )
        self.assertEqual(positive, "conditioned-positive")
        self.assertEqual(negative, "negative")
        self.assertEqual(calls[0]["negative"], [])
        self.assertEqual(calls[0]["strength"], 0.825)
        self.assertEqual(report["translation"], "forge_positive_soft_negative_zero")

    def test_zero_controlnet_strength_is_a_provider_free_no_op(self):
        with mock.patch.object(
            sam3_nodes, "_node_mappings", side_effect=AssertionError("provider must not load")
        ):
            positive, negative, report = sam3_nodes._apply_controlnet(
                "positive", "negative", object(), _image(), 0.0, 0.0, 1.0,
                object(), "Balanced",
            )
        self.assertEqual((positive, negative), ("positive", "negative"))
        self.assertEqual(report["translation"], "disabled_zero_strength")
        self.assertEqual(report["effective_strength"], 0.0)

    def test_missing_or_semantically_different_control_preprocessor_fails_fast(self):
        with mock.patch.object(sam3_nodes, "_node_mappings", return_value={}):
            with self.assertRaisesRegex(RuntimeError, "refusing to substitute"):
                sam3_nodes._prepare_control_hint(
                    _image(), torch.ones((1, 12, 14)), "canny", 512, -1, -1
                )
        with self.assertRaisesRegex(RuntimeError, "tile_colorfix.*unsupported"):
            sam3_nodes._prepare_control_hint(
                _image(), torch.ones((1, 12, 14)), "tile_colorfix", 512, -1, -1
            )

    def test_vae_padding_uses_reported_ratio_and_unpads_exactly(self):
        class RatioVAE:
            @staticmethod
            def spacial_compression_encode():
                return 8

        source = torch.linspace(0.0, 1.0, 7 * 13 * 3).reshape(1, 7, 13, 3)
        mask = torch.zeros((1, 7, 13))
        mask[:, 1:6, 2:11] = 1
        padded, padded_mask, padding = sam3_nodes._pad_for_vae(
            source, mask, RatioVAE()
        )
        self.assertEqual(tuple(padded.shape), (1, 8, 16, 3))
        self.assertEqual(tuple(padded_mask.shape), (1, 8, 16))
        self.assertEqual(padding, (1, 2, 0, 1))
        self.assertTrue(torch.equal(sam3_nodes._unpad_image(padded, padding), source))
        self.assertEqual(padded_mask.sum().item(), mask.sum().item())

    def test_four_fill_modes_keep_distinct_latent_semantics(self):
        class IdentityVAE:
            @staticmethod
            def encode(pixels):
                return pixels.movedim(-1, 1).clone()

        image = torch.linspace(0.0, 1.0, 8 * 8 * 3).reshape(1, 8, 8, 3)
        mask = torch.zeros((1, 8, 8))
        mask[:, 2:6, 2:6] = 1
        values = {
            mode: sam3_nodes._vae_encode_for_inpaint(
                IdentityVAE(), image, mask, 0, fill_mode=mode, seed=123
            )["samples"]
            for mode in ("fill", "original", "latent noise", "latent nothing")
        }
        latent_mask = mask.unsqueeze(1).bool()
        self.assertFalse(torch.equal(values["fill"], values["original"]))
        self.assertTrue(torch.equal(
            values["latent nothing"].masked_select(latent_mask.expand_as(values["latent nothing"])),
            torch.zeros_like(values["latent nothing"].masked_select(latent_mask.expand_as(values["latent nothing"]))),
        ))
        self.assertFalse(torch.equal(values["latent noise"], values["latent nothing"]))
        repeated = sam3_nodes._vae_encode_for_inpaint(
            IdentityVAE(), image, mask, 0, fill_mode="latent noise", seed=123
        )["samples"]
        self.assertTrue(torch.equal(values["latent noise"], repeated))

    def test_artifact_output_writes_all_declared_files(self):
        combined = torch.zeros((1, 5, 6))
        combined[:, 1:4, 2:5] = 1
        individuals = torch.cat([combined, torch.zeros_like(combined)], dim=0)
        with tempfile.TemporaryDirectory() as temp_dir:
            result = mask_ops.save_mask_artifacts(
                temp_dir, combined=combined, individuals=individuals,
                overlay=mask_ops.make_overlay(_image(height=5, width=6), combined),
                prompt="face / hand", seed=17, metadata={"device": "cpu"},
            )
            paths = [result["combined_mask"], result["overlay"], result["metadata"], *result["individual_masks"]]
            self.assertEqual(len(paths), 5)
            self.assertTrue(all(Path(path).is_file() for path in paths))

    def test_detailer_sequentially_inpaints_individual_masks(self):
        encoded_shapes = []
        sampled = []

        def fake_encode(vae, pixels, mask, grow_mask_by, **kwargs):
            encoded_shapes.append((pixels.shape, mask.shape, grow_mask_by))
            return {
                "samples": torch.zeros((pixels.shape[0], 4, pixels.shape[1] // 8, pixels.shape[2] // 8)),
                "test_image_shape": tuple(pixels.shape),
            }

        def fake_sample(model, seed, steps, cfg, sampler_name, scheduler,
                        positive, negative, latent, denoise, noise_multiplier):
            sampled.append((seed, steps, cfg, sampler_name, scheduler, denoise, noise_multiplier))
            return latent

        def fake_decode(vae, latent):
            return torch.ones(latent["test_image_shape"])

        masks = torch.zeros((2, 16, 16))
        masks[0, 2:5, 2:5] = 1
        masks[1, 10:13, 10:13] = 1
        with (
            mock.patch.object(sam3_nodes, "_vae_encode_for_inpaint", side_effect=fake_encode),
            mock.patch.object(sam3_nodes, "_sample_latent", side_effect=fake_sample),
            mock.patch.object(sam3_nodes, "_vae_decode", side_effect=fake_decode),
            mock.patch.object(sam3_nodes, "_encode_prompt", side_effect=lambda clip, text: ("encoded", text)),
        ):
            output, applied, report_json = sam3_nodes.ForgeNeoSAM3Detailer().detail(
                _image(height=16, width=16), masks, object(), object(), object(),
                "positive-conditioning", "negative-conditioning",
                inpaint_prompt="detail prompt", negative_prompt="",
                mask_mode="Individual", seed=100, steps=9, cfg=4.5,
                sampler_name="euler", scheduler="normal", denoise=0.35,
                noise_multiplier=1.2, fill_mode="original", only_masked=True,
                mask_padding=1, use_custom_size=False, grow_mask_by=4,
            )
        self.assertEqual(len(encoded_shapes), 2)
        self.assertEqual(len(sampled), 2)
        self.assertEqual([item[0] for item in sampled], [100, 100])
        self.assertTrue(all(item[-1] == 1.2 for item in sampled))
        self.assertTrue(output[0, 3, 3].eq(1).all())
        self.assertTrue(output[0, 11, 11].eq(1).all())
        self.assertTrue(output[0, 0, 0].eq(0).all())
        self.assertEqual(applied.sum().item(), 18)
        self.assertEqual(
            [item["status"] for item in json.loads(report_json)["passes"]],
            ["sampled", "sampled"],
        )

    def test_detailer_pads_odd_full_frame_for_vae_then_unpads_output(self):
        class RatioVAE:
            encoded_shape = None

            @staticmethod
            def spacial_compression_encode():
                return 8

            def encode(self, pixels):
                self.encoded_shape = tuple(pixels.shape)
                return torch.zeros((pixels.shape[0], 4, pixels.shape[1] // 8, pixels.shape[2] // 8))

        vae = RatioVAE()
        source = _image(height=7, width=13)
        mask = torch.ones((1, 7, 13))
        with (
            mock.patch.object(sam3_nodes, "_sample_latent", side_effect=lambda *args: args[8]),
            mock.patch.object(
                sam3_nodes, "_vae_decode",
                side_effect=lambda _vae, latent: torch.ones((1, 8, 16, 3)),
            ),
        ):
            output, _, report_json = sam3_nodes.ForgeNeoSAM3Detailer().detail(
                source, mask, object(), object(), vae, object(), object(),
                only_masked=False, grow_mask_by=0,
            )
        self.assertEqual(vae.encoded_shape, (1, 8, 16, 3))
        self.assertEqual(tuple(output.shape), (1, 7, 13, 3))
        pass_report = json.loads(report_json)["passes"][0]
        self.assertEqual(pass_report["sample_size"], [13, 7])
        self.assertEqual(pass_report["vae_sample_size"], [16, 8])
        self.assertEqual(pass_report["vae_padding"], [1, 2, 0, 1])

    def test_detailer_executes_controlnet_and_restore_adapters(self):
        sampled_conditioning = []

        def fake_encode(vae, pixels, mask, grow_mask_by, **kwargs):
            return {"samples": torch.zeros((1, 4, 1, 1)), "shape": tuple(pixels.shape)}

        def fake_sample(model, seed, steps, cfg, sampler_name, scheduler,
                        positive, negative, latent, denoise, noise_multiplier):
            sampled_conditioning.append((positive, negative))
            return latent

        mask = torch.zeros((1, 16, 16))
        mask[:, 4:12, 4:12] = 1
        restore_result = (_image(height=16, width=16, value=0.25), mask, {"provider": "fake-face"})
        with (
            mock.patch.object(sam3_nodes, "_load_controlnet", return_value=(object(), "cn.safetensors")),
            mock.patch.object(sam3_nodes, "_prepare_control_hint", return_value=(_image(height=8, width=8), "inpaint_hint")),
            mock.patch.object(sam3_nodes, "_apply_controlnet", return_value=("cn-positive", "cn-negative", {"mode": "Balanced"})),
            mock.patch.object(sam3_nodes, "_vae_encode_for_inpaint", side_effect=fake_encode),
            mock.patch.object(sam3_nodes, "_sample_latent", side_effect=fake_sample),
            mock.patch.object(sam3_nodes, "_vae_decode", side_effect=lambda vae, latent: torch.ones(latent["shape"])),
            mock.patch.object(sam3_nodes, "_restore_faces", return_value=restore_result) as restore_mock,
        ):
            output, _, report_json = sam3_nodes.ForgeNeoSAM3Detailer().detail(
                _image(height=16, width=16), mask, object(), object(), object(),
                "positive", "negative", mask_padding=0,
                controlnet_enable=True, controlnet_model_name="cn.safetensors",
                controlnet_settings_json=json.dumps(sam3_nodes._CONTROLNET_EXTRA_DEFAULTS),
                restore_face=True,
                restore_face_settings_json=json.dumps(sam3_nodes._RESTORE_FACE_DEFAULTS),
            )
        self.assertEqual(sampled_conditioning, [("cn-positive", "cn-negative")])
        restore_mock.assert_called_once()
        self.assertTrue(torch.allclose(output, torch.full_like(output, 0.25)))
        report = json.loads(report_json)
        self.assertTrue(report["controlnet_enabled"])
        self.assertEqual(report["restore_face"]["provider"], "fake-face")

    def test_zero_denoise_skips_prompt_vae_sampler_and_controlnet(self):
        source = _image(height=9, width=11, value=0.2)
        mask = torch.zeros((1, 9, 11))
        mask[:, 2:7, 3:8] = 1
        with (
            mock.patch.object(
                sam3_nodes, "_encode_prompt", side_effect=AssertionError("prompt must not encode")
            ),
            mock.patch.object(
                sam3_nodes, "_load_controlnet", side_effect=AssertionError("ControlNet must not load")
            ),
            mock.patch.object(
                sam3_nodes, "_vae_encode_for_inpaint", side_effect=AssertionError("VAE must not encode")
            ),
            mock.patch.object(
                sam3_nodes, "_sample_latent", side_effect=AssertionError("sampler must not run")
            ),
        ):
            output, applied, report_json = sam3_nodes.ForgeNeoSAM3Detailer().detail(
                source, mask, object(), object(), object(), object(), object(),
                inpaint_prompt="unused", negative_prompt="unused", denoise=0.0,
                controlnet_enable=True, controlnet_strength=1.0,
            )
        self.assertTrue(torch.equal(output, source))
        self.assertTrue(torch.equal(applied, mask))
        report = json.loads(report_json)
        self.assertEqual(report["status"], "no_op_zero_denoise")
        self.assertFalse(report["controlnet_enabled"])
        self.assertEqual(report["controlnet_disabled_reason"], "zero_denoise")
        self.assertEqual(report["passes"][0]["status"], "no_op_zero_denoise")

    def test_zero_control_strength_skips_model_loading_but_still_inpaints(self):
        mask = torch.zeros((1, 8, 8))
        mask[:, 2:6, 2:6] = 1

        def fake_encode(vae, pixels, mask, grow_mask_by, **kwargs):
            return {"samples": torch.zeros((1, 4, 1, 1)), "shape": tuple(pixels.shape)}

        with (
            mock.patch.object(
                sam3_nodes, "_load_controlnet", side_effect=AssertionError("ControlNet must not load")
            ),
            mock.patch.object(sam3_nodes, "_vae_encode_for_inpaint", side_effect=fake_encode),
            mock.patch.object(sam3_nodes, "_sample_latent", side_effect=lambda *args: args[8]),
            mock.patch.object(
                sam3_nodes, "_vae_decode",
                side_effect=lambda vae, latent: torch.ones(latent["shape"]),
            ),
        ):
            output, _, report_json = sam3_nodes.ForgeNeoSAM3Detailer().detail(
                _image(height=8, width=8), mask, object(), object(), object(),
                object(), object(), mask_padding=0, controlnet_enable=True,
                controlnet_strength=0.0,
            )
        self.assertTrue(output[0, 3, 3].eq(1).all())
        report = json.loads(report_json)
        self.assertFalse(report["controlnet_enabled"])
        self.assertEqual(report["controlnet_disabled_reason"], "zero_strength")

    def test_implicit_control_source_tracks_current_sequential_result(self):
        control_means = []
        decode_values = iter((0.25, 0.75))

        def fake_encode(vae, pixels, mask, grow_mask_by, **kwargs):
            return {"samples": torch.zeros((1, 4, 2, 2)), "shape": tuple(pixels.shape)}

        def fake_control_hint(image, mask, *args):
            control_means.append(float(image.mean()))
            return image, "raw-test"

        def fake_decode(vae, latent):
            return torch.full(latent["shape"], next(decode_values))

        masks = torch.zeros((2, 16, 16))
        masks[0, 1:5, 1:5] = 1
        masks[1, 10:14, 10:14] = 1
        with (
            mock.patch.object(sam3_nodes, "_load_controlnet", return_value=(object(), "test-cn")),
            mock.patch.object(sam3_nodes, "_prepare_control_hint", side_effect=fake_control_hint),
            mock.patch.object(
                sam3_nodes, "_apply_controlnet",
                side_effect=lambda positive, negative, *args: (positive, negative, {"mode": "Balanced"}),
            ),
            mock.patch.object(sam3_nodes, "_vae_encode_for_inpaint", side_effect=fake_encode),
            mock.patch.object(sam3_nodes, "_sample_latent", side_effect=lambda *args: args[8]),
            mock.patch.object(sam3_nodes, "_vae_decode", side_effect=fake_decode),
        ):
            output, _, _ = sam3_nodes.ForgeNeoSAM3Detailer().detail(
                _image(height=16, width=16), masks, object(), object(), object(),
                object(), object(), mask_mode="Individual", only_masked=False,
                controlnet_enable=True,
                controlnet_settings_json=json.dumps(sam3_nodes._CONTROLNET_EXTRA_DEFAULTS),
            )
        self.assertEqual(len(control_means), 2)
        self.assertEqual(control_means[0], 0.0)
        self.assertGreater(control_means[1], 0.0)
        self.assertTrue(output[0, 2, 2].eq(0.25).all())
        self.assertTrue(output[0, 11, 11].eq(0.75).all())

    def test_restore_face_uses_impact_provider_contract(self):
        detector = object()
        calls = []

        class FakeDetectorProvider:
            FUNCTION = "doit"

            @classmethod
            def doit(cls, model_name):
                return detector, object()

        class FakeFaceDetailer:
            FUNCTION = "doit"

            @classmethod
            def doit(cls, **kwargs):
                calls.append(kwargs)
                return kwargs["image"] + 0.1, [], [], torch.ones((1, 8, 8)), object(), []

        settings = dict(sam3_nodes._RESTORE_FACE_DEFAULTS)
        with mock.patch.object(
            sam3_nodes,
            "_node_mappings",
            return_value={
                "UltralyticsDetectorProvider": FakeDetectorProvider,
                "FaceDetailer": FakeFaceDetailer,
            },
        ):
            output, face_mask, report = sam3_nodes._restore_faces(
                _image(height=8, width=8), model=object(), clip=object(), vae=object(),
                positive=object(), negative=object(), sampler_name="euler",
                scheduler="normal", seed=4, steps=8, cfg=5.0,
                settings_json=json.dumps(settings),
            )
        self.assertAlmostEqual(output.mean().item(), 0.1, places=5)
        self.assertEqual(face_mask.sum().item(), 64)
        self.assertIs(calls[0]["bbox_detector"], detector)
        self.assertEqual(report["provider"], "Impact FaceDetailer")

    def test_detailer_reports_empty_detection_without_sampling(self):
        source = _image(height=8, width=8)
        output, applied, report_json = sam3_nodes.ForgeNeoSAM3Detailer().detail(
            source, torch.zeros((1, 8, 8)),
            object(), object(), object(), object(), object(),
        )
        self.assertTrue(torch.equal(output, source))
        self.assertEqual(applied.sum().item(), 0)
        self.assertEqual(json.loads(report_json)["status"], "no_detection")

    def test_node_contracts_are_stable_for_workflow_compiler(self):
        self.assertEqual(
            sam3_nodes.ForgeNeoSAM3Mask.RETURN_NAMES,
            ("selected_mask", "combined_mask", "individual_masks", "overlay", "boxes", "scores", "artifacts_json"),
        )
        self.assertEqual(
            sam3_nodes.ForgeNeoSAM3Detailer.RETURN_NAMES,
            ("image", "applied_mask", "report_json"),
        )
        self.assertTrue(
            {"sam3_model", "manual_mask"}
            <= set(sam3_nodes.ForgeNeoSAM3Mask.INPUT_TYPES()["optional"])
        )
        self.assertTrue(
            {
                "model", "clip", "vae", "positive", "negative", "inpaint_prompt",
                "controlnet_enable", "controlnet_override_external",
                "controlnet_settings_json", "restore_face", "restore_face_settings_json",
            }
            <= set(sam3_nodes.ForgeNeoSAM3Detailer.INPUT_TYPES()["required"])
        )
        self.assertTrue(
            {"control_net", "control_image", "face_detector"}
            <= set(sam3_nodes.ForgeNeoSAM3Detailer.INPUT_TYPES()["optional"])
        )

    def test_refine_and_tile_repair_are_real_paths(self):
        self.assertTrue(issubclass(sam3_nodes.ForgeNeoSAM3Refine, sam3_nodes.ForgeNeoSAM3Detailer))
        self.assertEqual(sam3_nodes.ForgeNeoSAM3Refine.FUNCTION, "detail")
        self.assertEqual(sam3_nodes.ForgeNeoSAM3TileRepair.FUNCTION, "tile_repair")
        with self.assertRaisesRegex(ValueError, "Invalid SAM3 tile settings_json"):
            sam3_nodes.ForgeNeoSAM3TileRepair().tile_repair(
                _image(), torch.ones((1, 12, 14)), object(), object(), object(),
                object(), object(), settings_json="{bad json",
            )

    def test_refine_outputs_each_mask_from_the_unmodified_source(self):
        decode_values = iter((0.25, 0.75))

        def fake_encode(vae, pixels, mask, grow_mask_by, **kwargs):
            return {"samples": torch.zeros((1, 4, 1, 1)), "shape": tuple(pixels.shape)}

        masks = torch.zeros((2, 8, 8))
        masks[0, 1:4, 1:4] = 1
        masks[1, 5:7, 5:7] = 1
        with (
            mock.patch.object(sam3_nodes, "_vae_encode_for_inpaint", side_effect=fake_encode),
            mock.patch.object(sam3_nodes, "_sample_latent", side_effect=lambda *args: args[8]),
            mock.patch.object(
                sam3_nodes, "_vae_decode",
                side_effect=lambda vae, latent: torch.full(
                    latent["shape"], next(decode_values)
                ),
            ),
        ):
            output, applied, report_json = sam3_nodes.ForgeNeoSAM3Refine().detail(
                _image(height=8, width=8), masks, object(), object(), object(),
                object(), object(), mask_mode="Individual", mask_padding=0,
            )
        self.assertEqual(tuple(output.shape), (2, 8, 8, 3))
        self.assertTrue(output[0, 2, 2].eq(0.25).all())
        self.assertTrue(output[0, 5, 5].eq(0.0).all())
        self.assertTrue(output[1, 2, 2].eq(0.0).all())
        self.assertTrue(output[1, 5, 5].eq(0.75).all())
        self.assertEqual(applied.sum().item(), 13)
        report = json.loads(report_json)
        self.assertEqual(report["processing"], "independent_from_original")
        self.assertEqual(report["result_count"], 2)

    def test_tile_repair_rejects_forge_anima_options_instead_of_masquerading(self):
        with self.assertRaisesRegex(RuntimeError, "Anima Tile-Repair/PiD.*lllite_model"):
            sam3_nodes.ForgeNeoSAM3TileRepair().tile_repair(
                _image(), torch.ones((1, 12, 14)), object(), object(), object(),
                object(), object(), settings_json='{"lllite_model": "anima.safetensors"}',
            )


if __name__ == "__main__":
    unittest.main()
