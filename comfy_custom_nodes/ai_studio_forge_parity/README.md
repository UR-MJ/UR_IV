# AI Studio Forge Neo parity nodes

This node pack is bundled with AI Studio Pro and installed into the selected
ComfyUI `custom_nodes` directory. It is the execution layer used by the app's
default ComfyUI workflow compiler; no workflow JSON is required for normal
T2I, I2I, inpaint, upscale, ADetailer, or SAM3 jobs.

## Node groups

- Generation: native checkpoint/split-model loading support, ANIMA-aware LoRA
  loading and block weight, latent input, CNS sampling, hires fix, Anima VAE
  2x, character reference, ADetailer, and metadata-aware image saving. Forge's
  `ER SDE` label maps to Comfy's native `er_sde`; `Beta57 (RES4LYF)` is
  registered as the exact beta schedule with alpha 0.5 and beta 0.7 rather
  than being approximated by Comfy's stock 0.6/0.6 `beta` schedule. Flow-shift
  patching preserves the loaded model's timestep multiplier (1.0 for Anima)
  instead of resetting it to SD3's 1000-unit scale.
- Guidance: NegPiP, DAVE, modulation guidance, Skim CFG, PAG/SEG/SLG,
  APG/CWM/SMC/DCW/RDC, adaptive guidance, and Detail Daemon compatibility.
- SAM3: text/manual mask composition, mask-only output, sequential inpaint,
  independent-result Refine, Comfy masked-region repair, ControlNet hand-off,
  face restore, overlays, and artifacts.
- Anima 3.8B: Qwen3.5 4B loading, progressive-cross v1 conditioning,
  bundled Semantic Connector v2 loading and timestep-aware conditioning. The
  28/40/52-block LoRA adapter is shared by normal, model-only Character
  Reference, and block-weight paths. ANIMA block weighting uses one value per
  active DiT block (28, 40, or 52), with an optional leading base value for
  non-block model and text-encoder keys; other architectures retain Inspire
  Pack's native vector behavior.

## Optional provider nodes

The pack resolves installed ComfyUI providers at execution time. A feature that
needs a provider fails with an explicit node/dependency message instead of being
silently ignored. Depending on the enabled options, providers include Easy SAM3,
Impact Pack/Subpack, ControlNet auxiliary preprocessors, Spectrum, Inspire Pack,
and CLIPNegPip.

SAM3 model weights and all other model/LoRA files are deliberately excluded.
They continue to come from the model directories configured in AI Studio.

The SAM3 behavior is ported from the user's Forge extension
`forge_sam3_extension` (0.21.x lineage). Some Forge-only hook mechanics are
translated to ComfyUI model/conditioning patches; the node report JSON records
fallbacks or semantic adaptations made at runtime.

Forge's vendored Anima/PiD/LLLite Tile Repair stack is not presented as the
same feature: `SAM3 Region Repair (Comfy)` handles the portable masked-region
subset, while Forge-only Tile Repair settings fail with an explicit dependency
message instead of silently running a different pipeline.

## Anima 3.8B provenance

The Anima 3.8B Comfy runtime is pinned from
`GumGum10/comfyui-anima-3-8B` commit
`381c13af328b958febf86c155d2f4b007cd0f55b`. Model, text-encoder, adapter,
LoRA, and VAE weights are not bundled; they are resolved from the model paths
configured in AI Studio. The exact copied-file boundary and upstream hashes
are recorded in `vendor/comfyui_anima_3_8b/UPSTREAM.md`.

The runtime code is MIT-licensed and the unmodified Qwen3.5 tokenizer assets
are Apache-2.0. Full license texts and attribution are included under
`LICENSES/` and `THIRD_PARTY_NOTICES.md`.

The 28-to-40 LoRA block lineage is derived from Anima-2.9B's published
`expand_manifest.json`; the 40-to-52 lineage is derived from the Anima 3.8B
checkpoint metadata. The node pack stores only those integer layout facts and
locally derives expansion, contraction, and composed mappings in every
direction. See `THIRD_PARTY_NOTICES.md` for the pinned metadata provenance.
