# AI Studio Forge Neo parity nodes

This node pack is bundled with AI Studio Pro and installed into the selected
ComfyUI `custom_nodes` directory. It is the execution layer used by the app's
default ComfyUI workflow compiler; no workflow JSON is required for normal
T2I, I2I, inpaint, upscale, ADetailer, or SAM3 jobs.

## Node groups

- Generation: native checkpoint/split-model loading support, LoRA block weight,
  latent input, CNS sampling, hires fix, Anima VAE 2x, character reference,
  ADetailer, and metadata-aware image saving.
- Guidance: NegPiP, DAVE, modulation guidance, Skim CFG, PAG/SEG/SLG,
  APG/CWM/SMC/DCW/RDC, adaptive guidance, and Detail Daemon compatibility.
- SAM3: text/manual mask composition, mask-only output, sequential inpaint,
  independent-result Refine, Comfy masked-region repair, ControlNet hand-off,
  face restore, overlays, and artifacts.

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
