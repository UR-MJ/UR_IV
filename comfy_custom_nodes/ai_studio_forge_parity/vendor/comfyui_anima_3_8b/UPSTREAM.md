# Pinned upstream manifest

## Source

- Repository: `https://github.com/GumGum10/comfyui-anima-3-8B.git`
- Pinned commit: `381c13af328b958febf86c155d2f4b007cd0f55b`
- Commit subject: `Add bundled Semantic Connector v2 workflow`
- Upstream package version at that commit: `0.2.0`
- Source-code license: MIT

The files in the table below were copied byte-for-byte from that detached Git
revision. They have not been reformatted, renamed internally, or patched.
SHA-256 is computed over the copied file bytes.

| Vendored path | SHA-256 |
| --- | --- |
| `__init__.py` | `d4509cbd4a3eb386ca5997c7f894a96184330791e10c327790a0c97dd623bc93` |
| `bundle_v2.py` | `e870b6de094f01a1699c8418b92cf120ece767a8d7d5ec1e549d9288a890e8ae` |
| `loader.py` | `d3edaa86f3139fcedb85b2bbd6f6bda46b492c47b86301e19c492f8bdb9dbe26` |
| `patches.py` | `bae67382cfc91ae70d6f9168f4f8677aece66819933ef1d2c089fa9a276105f1` |
| `progressive_cross_adapter.py` | `aa35354ede00ee0ac7873c4b61568cac01bfe65282f21c4602dd7981ec71a57d` |
| `prompt.py` | `bb93e602d2311af2271d5780f1012b048ea3224e0fca398e55df0121f7d57d86` |
| `semantic_connector_v2.py` | `2647ea4e480ae1be8ac33344f2337de5c3ac4b420f65bfa03a563e2e2c64bda3` |
| `semantic_v2_runtime.py` | `548561f961351b0cc49d2b326f078c4e8d8565b3134e6c2888ef53b73403d89d` |
| `v2.py` | `edba33618664dfaa15005efa8b6be00cbc21a0cbbb4197bc20babf6fef5b5120` |
| `text_encoder/__init__.py` | `17f6136fde1806350597640006c2eac35a43e964f817bacf6fbbb86ea22630b0` |
| `text_encoder/clip.py` | `64ccb9d6cd5590a23c22b96b1bdb123feb66940a9c57d3a5d62e797d2419101c` |
| `text_encoder/layers.py` | `dd8977bce23d9ef95b5c835da52735551f1e7ca513281f21c2c861b4359bfdb4` |
| `text_encoder/model.py` | `210005c6f17d55f32211c6436c466a1afde3e8965dd3cf4815687771b91d2f50` |
| `text_encoder/tokenizer.py` | `b3d6c74c100e4734c363fa0055bfc932749928d5f1a3f67e6940af2e002d2e9e` |
| `qwen35_tokenizer/tokenizer.json` | `5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42` |
| `qwen35_tokenizer/tokenizer_config.json` | `316230d6a809701f4db5ea8f8fc862bc3a6f3229c937c174e674ff3ca0a64ac8` |

The tokenizer hashes were also checked directly against
`Qwen/Qwen3.5-4B@851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`, not only against the
intermediate ComfyUI repository copy.

## Local integration boundary

`UPSTREAM.md` is the only locally authored file in this directory. AI Studio
does not edit the copied runtime. Its integration lives one level above in
`anima38_nodes.py`, which exposes four Forge Neo-named lazy wrappers and a
small equivalent of upstream's MIT-licensed 52-block detection hook. Keeping
that hook in the wrapper allows model detection to be ready at node-pack import
without importing optional ML dependencies; the complete upstream runtime and
timestep hook still load lazily from the unchanged vendor copy. The
separate `vendor/__init__.py` file only establishes the local vendor namespace.
`vendor/.gitattributes` pins LF checkout for the byte-identical upstream files
on Windows; it does not alter runtime behavior.

The following upstream repository files were intentionally not copied because
they are repository metadata, duplicated documentation, package-install
metadata, or a sample workflow rather than imported runtime code:

- `.gitattributes`
- `.gitignore`
- `README.md`
- `THIRD_PARTY_NOTICES.md`
- `LICENSE`
- `pyproject.toml`
- `requirements.txt`
- `examples/api_workflow.json`

The upstream MIT license and tokenizer notice are represented by the node-pack
level `LICENSES/` files and `THIRD_PARTY_NOTICES.md`.

## Runtime prerequisites and excluded artifacts

The pinned upstream metadata requires Python 3.10 or newer,
`transformers>=4.51.0`, and `safetensors>=0.4.0`. ComfyUI must provide native
Anima support (`comfy.ldm.anima`), diffusion-state loading, model patching, and
the normal `folder_paths` model registries. Because upstream does not publish a
numeric minimum ComfyUI version, these capabilities are the compatibility
boundary.

No `.safetensors`, `.ckpt`, `.pt`, `.pth`, `.bin`, `.gguf`, or other model
weight is included. In particular, users must separately provide the Anima v2
bundle, Qwen3.5 4B encoder, native Qwen3 0.6B encoder, and Qwen Image VAE in the
appropriate ComfyUI model directories.
