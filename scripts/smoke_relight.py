"""CPU-only synthetic visual smoke test; never opens or edits user images.

Run from the checkout with its Python environment. Every invocation creates a
new directory in the system temporary folder and writes files exclusively.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from comfy_custom_nodes.ai_studio_forge_parity.relight import relight_image


def synthetic_scene(size=384):
    """A colored sphere above a flat surface, with known white-near depth."""
    yy, xx = np.mgrid[:size, :size].astype(np.float32)
    nx = (xx - size * .5) / (size * .27)
    ny = (yy - size * .43) / (size * .27)
    inside = nx * nx + ny * ny <= 1
    sphere_z = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
    depth = np.full((size, size), .08, dtype=np.float32)
    depth[inside] = .22 + .65 * sphere_z[inside]
    floor = .93 + .035 * np.cos(xx / 20) * np.cos(yy / 20)
    source = floor[..., None] * np.array([.64, .69, .74], dtype=np.float32)
    pigment = .95 + .04 * np.sin(ny * 16) * np.cos(nx * 13)
    source[inside] = pigment[inside, None] * np.array([.70, .40, .26], dtype=np.float32)
    return source.astype(np.float32), depth


def image_from_array(array):
    pixels = np.rint(np.clip(array, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(pixels).convert("RGB")


def save_png_exclusive(image, path):
    with path.open("xb") as stream:
        image.save(stream, format="PNG")


def run():
    source, depth = synthetic_scene()
    source_before, depth_before = source.copy(), depth.copy()
    settings = {
        "elevation": 28., "strength": .95, "ambient": .18, "depth_scale": 2.,
        "shadow_strength": .7, "shadow_length": 80., "shadow_softness": 4.,
        "shadow_cleanup": 0.,
    }
    left = relight_image(source, depth=depth, settings={**settings, "azimuth": -60.})
    right = relight_image(source, depth=depth, settings={**settings, "azimuth": 60.})
    zero = relight_image(source, depth=depth, settings={**settings, "azimuth": -60., "strength": 0.})
    difference = np.abs(left["image"] - right["image"])
    expected_shape = source.shape
    all_arrays = [source, depth, *(left[key] for key in ("image", "light", "normals", "shadow")),
                  *(right[key] for key in ("image", "light", "normals", "shadow"))]
    checks = {
        "source_unchanged": bool(np.array_equal(source, source_before)),
        "depth_unchanged": bool(np.array_equal(depth, depth_before)),
        "zero_strength_pixel_identical": bool(np.array_equal(zero["image"], source)),
        "left_right_are_different": bool(float(difference.max()) > .01 and float(difference.mean()) > .001),
        "original_resolution_preserved": bool(left["image"].shape == right["image"].shape == expected_shape),
        "diagnostic_shapes_match": bool(all(value.shape[:2] == expected_shape[:2] for value in all_arrays)),
        "all_values_finite": bool(all(np.isfinite(value).all() for value in all_arrays)),
        "all_values_in_zero_one": bool(all((value >= 0).all() and (value <= 1).all() for value in all_arrays)),
        "supplied_depth_used": left["geometry"] == right["geometry"] == "depth",
        "cast_shadow_nonzero": bool(np.count_nonzero(left["shadow"]) > 0),
    }
    target = Path(tempfile.mkdtemp(prefix="ai-studio-relight-smoke-"))
    tiles = [
        ("original", "Original synthetic RGB", source),
        ("left_light", "Left light: azimuth -60", left["image"]),
        ("right_light", "Right light: azimuth +60", right["image"]),
        ("depth", "Known depth (white = near)", depth),
        ("light_map", "Left diffuse light map", left["light"]),
        ("normal_map", "Normal map (+Y up, +Z camera)", left["normals"]),
        ("shadow_map", "Left cast shadow", left["shadow"]),
    ]
    font = ImageFont.load_default(size=14)
    tile_size, label_height, gap = 384, 32, 12
    contact = Image.new("RGB", (3 * tile_size + 4 * gap, 3 * (tile_size + label_height) + 4 * gap), "#19232b")
    draw = ImageDraw.Draw(contact)
    output_files = {}
    for index, (name, label, array) in enumerate(tiles):
        image = image_from_array(array)
        path = target / f"{name}.png"
        save_png_exclusive(image, path)
        output_files[name] = str(path)
        x = gap + index % 3 * (tile_size + gap)
        y = gap + index // 3 * (tile_size + label_height + gap)
        draw.text((x + 8, y + 8), label, font=font, fill="#eff4f7")
        contact.paste(image, (x, y + label_height))
    x, y = tile_size + 2 * gap, 2 * (tile_size + label_height) + 3 * gap
    summary = ["CPU synthetic smoke test", "No model / GPU / user files", "", *[
        f"{'PASS' if passed else 'FAIL'}  {name}" for name, passed in checks.items()
    ], "", f"Max L/R difference: {float(difference.max()):.6f}",
        f"Mean L/R difference: {float(difference.mean()):.6f}"]
    for index, line in enumerate(summary):
        draw.text((x + 8, y + 8 + index * 22), line, font=font,
                  fill="#f5b8ab" if line.startswith("FAIL") else "#d0e1d3")
    contact_path = target / "contact.png"
    save_png_exclusive(contact, contact_path)
    output_files["contact"] = str(contact_path)
    report = {
        "ok": all(checks.values()), "checks": checks, "shape": list(expected_shape),
        "source_sha256": hashlib.sha256(source.tobytes()).hexdigest(),
        "depth_sha256": hashlib.sha256(depth.tobytes()).hexdigest(),
        "left_right_max_difference": float(difference.max()),
        "left_right_mean_difference": float(difference.mean()),
        "settings": settings, "azimuths": [-60., 60.], "files": output_files,
        "scope": "Synthetic geometry only; this does not validate natural image relighting quality.",
    }
    report_path = target / "verification.json"
    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": report["ok"], "directory": str(target), "contact": str(contact_path),
                      "verification": str(report_path), "checks": checks}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(run())
