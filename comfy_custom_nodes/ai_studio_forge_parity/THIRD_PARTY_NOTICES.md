# Third-party notices

AI Studio Pro includes an unmodified, pinned copy of the Python runtime from
[`GumGum10/comfyui-anima-3-8B`](https://github.com/GumGum10/comfyui-anima-3-8B)
at commit `381c13af328b958febf86c155d2f4b007cd0f55b`. The copied runtime is under
`vendor/comfyui_anima_3_8b/` and is licensed under the MIT License. The full
license text is included at `LICENSES/comfyui-anima-3-8B-MIT.txt`.

The following two files within that runtime are unmodified copies from
[`Qwen/Qwen3.5-4B`](https://huggingface.co/Qwen/Qwen3.5-4B), revision
`851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`:

- `vendor/comfyui_anima_3_8b/qwen35_tokenizer/tokenizer.json`
- `vendor/comfyui_anima_3_8b/qwen35_tokenizer/tokenizer_config.json`

The Qwen upstream repository identifies these files under Apache-2.0. The full
license text is included at `LICENSES/Qwen3.5-Apache-2.0.txt`.

## Anima block-lineage metadata

The adjacent-generation LoRA mapping in `anima_lora.py` is locally authored
from published model-layout metadata; it does not copy Forge's loader code.
The 28-to-40 insertion positions come from
[`Gazingstars123/Anima-2.9B`](https://huggingface.co/Gazingstars123/Anima-2.9B/blob/9f9cb502dbae7a616c3cc5a530633427fe735665/expand_manifest.json).
The 40-to-52 positions are read from the `insertion_positions` and
`inserted_to_source` metadata published in the user-supplied
`Anima-3.8B-v1.1.safetensors` checkpoint. Only the integer layout facts are
encoded here; the expansion, contraction, composition, collision checks, and
LoRA key handling are local implementation code. No manifest or model weight
from either model repository is redistributed in this node pack.

AI Studio's `anima38_nodes.py` wrapper, its Forge Neo node names, and the
surrounding `vendor/__init__.py` namespace file are local integration code.
`anima38_nodes.py` includes a small integration copy of the 52-block detection
algorithm from upstream `patches.py`; it keeps the upstream compatibility
marker while avoiding eager ML-library imports. It is identified as local glue,
not as a byte-identical upstream file, and the upstream MIT notice is retained.
`anima38_cache.py` is a local integration shim that ties registered semantic
conditioning runs to Comfy cache ownership; it patches runtime entrypoints in
memory without modifying the pinned upstream source files.
No model checkpoint, text-encoder weight, VAE weight, LoRA, GGUF, or other model
binary is redistributed with this node pack. Those files must be supplied
separately by the user and remain subject to their own licenses.

See `vendor/comfyui_anima_3_8b/UPSTREAM.md` for the complete copied-file list,
SHA-256 values, omitted upstream files, dependencies, and local modification
boundary. These notices do not replace or modify either upstream license.
