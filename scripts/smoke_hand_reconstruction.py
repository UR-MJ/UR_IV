"""Non-destructive synthetic hand-reconstruction smoke test.

Default is CPU-only. --live-forge URL explicitly permits ONE 512px masked
generation on an idle loopback Forge server, using its already-selected model
and modules. No downloads, model switches, interrupts, or user images.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlparse

from PIL import Image, ImageChops, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.hand_reconstruction import prepare_hand_repair, compose_hand_candidate
from ui.hand_reconstruction_actions import hand_generation_payload


def png(image):
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def url(image):
    return "data:image/png;base64," + base64.b64encode(png(image)).decode("ascii")


def fixture():
    image = Image.new("RGB", (512, 512), "#d6e1ec")
    draw = ImageDraw.Draw(image)
    draw.rectangle((208, 310, 300, 511), fill="#384f76")
    draw.rounded_rectangle((183, 213, 317, 345), radius=38, fill="#dfa883")
    # Deliberately crude six-prong illustration, not a real anatomy benchmark.
    for x, top in ((166, 188), (191, 116), (218, 88), (245, 79), (272, 107), (298, 146)):
        draw.rounded_rectangle((x, top, x + 25, 260), radius=12, fill="#dfa883")
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((152, 65, 338, 361), radius=30, fill=255)
    return image, mask


def run():
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--live-forge", default="")
    options = args.parse_args()
    source, mask = fixture()
    prepared = prepare_hand_repair({"image": url(source), "mask": url(mask),
                                    "settings": {"enabled": True, "candidates": 1, "resolution": 512}})
    model = "CPU synthetic backend"
    seed = 942817
    if options.live_forge:
        import requests
        parsed = urlparse(options.live_forge)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username:
            raise ValueError("Smoke test only permits a loopback HTTP Forge endpoint.")
        endpoint = options.live_forge.rstrip("/")
        progress = requests.get(endpoint + "/sdapi/v1/progress", params={"skip_current_image": "true"}, timeout=5)
        progress.raise_for_status()
        if progress.json().get("state", {}).get("job_count", 0) or progress.json().get("progress", 0):
            raise RuntimeError("Forge is busy; no generation was submitted.")
        current = requests.get(endpoint + "/sdapi/v1/options", timeout=5)
        current.raise_for_status()
        model = current.json().get("sd_model_checkpoint")
        if not model:
            raise RuntimeError("No already-selected Forge checkpoint.")
        values = {"prompt": "hand, open hand, palm, blue sleeve, simple background, illustration. An anatomically coherent human hand with a natural wrist connection.",
                  "negative_prompt": "extra fingers, fused fingers, malformed hands", "steps": 12,
                  "cfg_scale": 4.0, "sampler_name": "Euler", "scheduler": "Normal",
                  "forge_additional_modules": current.json().get("forge_additional_modules", [])}
        payload = hand_generation_payload(prepared, values, seed)
        # Direct API: never call the adapter's model-switch helper in this probe.
        result = requests.post(endpoint + "/sdapi/v1/img2img", json=payload, timeout=600)
        result.raise_for_status()
        images = result.json().get("images", [])
        if not images:
            raise RuntimeError("Forge returned no image.")
        generated_png = base64.b64decode(images[0].split(",")[-1], validate=True)
    else:
        generated_png = png(Image.new("RGB", prepared.working_size, "#76a2b9"))
    output_png = compose_hand_candidate(prepared, generated_png,
                                        provenance={"smoke": True, "model": model, "seed": seed, "anatomy_verified": False})
    output = Image.open(io.BytesIO(output_png)).convert("RGB")
    difference = ImageChops.difference(output, source)
    outside_diff = ImageChops.multiply(difference, ImageChops.invert(mask).convert("RGB"))
    checks = {"original_resolution": output.size == source.size,
              "outside_mask_exact": outside_diff.getbbox() is None,
              "inside_changed": difference.getbbox() is not None,
              "source_unchanged": source.tobytes() == prepared.source.tobytes(),
              "live_forge": bool(options.live_forge), "anatomy_verified": False}
    if not all(checks[key] for key in ("original_resolution", "outside_mask_exact", "inside_changed", "source_unchanged")):
        raise RuntimeError(f"Reconstruction invariant failure: {checks}")
    target = Path(tempfile.mkdtemp(prefix="ai-studio-hand-smoke-"))
    for name, data in (("source.png", png(source)), ("mask.png", png(mask)),
                       ("erased_input.png", prepared.init_png), ("candidate.png", output_png)):
        with (target / name).open("xb") as stream:
            stream.write(data)
    print(json.dumps({"directory": str(target), "working_size": prepared.working_size, "model": model, **checks}))


if __name__ == "__main__":
    run()
