"""Sprite acceptance gate utilities."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image, ImageChops

from godot_agent.runtime.design_memory import AssetSpec
from godot_agent.runtime.visual_regression import artifact_dir, slugify_artifact_name
from godot_agent.tools.sprite_pipeline import parse_hex_color


@dataclass
class SpriteQAReport:
    valid: bool
    width: int
    height: int
    expected_size: tuple[int, int] | None = None
    alpha_present: bool = False
    transparent_pixels: int = 0
    remaining_key_pixels: int = 0
    palette_size: int = 0
    soft_alpha_pixels: int = 0
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def target_dimensions(spec: AssetSpec, fallback_size: int | tuple[int, int] | None = None) -> tuple[int, int] | None:
    if spec.target_size:
        if len(spec.target_size) == 1:
            return (spec.target_size[0], spec.target_size[0])
        return (spec.target_size[0], spec.target_size[1])
    if fallback_size is None:
        return None
    if isinstance(fallback_size, tuple):
        return fallback_size
    return (fallback_size, fallback_size)


def _count_remaining_key_pixels(image: Image.Image, key: tuple[int, int, int], tolerance: int) -> int:
    rgba = image.convert("RGBA")
    # Per-channel absolute difference against the key colour
    key_img = Image.new("RGB", rgba.size, key)
    diff = ImageChops.difference(rgba.convert("RGB"), key_img)
    # Each channel: 255 if within tolerance, else 0
    r_ok, g_ok, b_ok = [
        ch.point(lambda p, t=tolerance: 255 if p <= t else 0) for ch in diff.split()
    ]
    # AND: pixel is key-coloured when all three channels match
    # multiply(255, 255) / 255 == 255; multiply(255, 0) / 255 == 0
    rgb_match = ImageChops.multiply(ImageChops.multiply(r_ok, g_ok), b_ok)
    # Exclude fully-transparent pixels (alpha == 0)
    opaque_mask = rgba.getchannel("A").point(lambda p: 255 if p > 0 else 0)
    result = ImageChops.multiply(rgb_match, opaque_mask)
    # Count pixels with value 255 (index 255 in the histogram)
    return result.histogram()[255]


def _count_alpha_pixels(image: Image.Image) -> tuple[bool, int, int]:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    hist = alpha.histogram()
    # transparent = pixels with alpha < 255 (indices 0..254)
    transparent = sum(hist[:255])
    # soft = pixels with 0 < alpha < 255 (indices 1..254)
    soft = sum(hist[1:255])
    return transparent > 0, transparent, soft


def _palette_size(image: Image.Image) -> int:
    colors = image.convert("RGBA").getcolors(maxcolors=16384)
    return len(colors) if colors is not None else 16385


def _mask_remaining_key(image: Image.Image, key: tuple[int, int, int], tolerance: int) -> Image.Image:
    rgba = image.convert("RGBA")
    mask = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    source = rgba.load()
    target = mask.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, a = source[x, y]
            if a == 0:
                continue
            if (
                abs(r - key[0]) <= tolerance
                and abs(g - key[1]) <= tolerance
                and abs(b - key[2]) <= tolerance
            ):
                target[x, y] = (255, 0, 255, 255)
    return mask


def analyze_sprite(image_path: Path, spec: AssetSpec, *, tolerance: int = 8) -> SpriteQAReport:
    with Image.open(image_path) as image:
        rgba = image.convert("RGBA")
        expected = target_dimensions(spec)
        alpha_present, transparent_pixels, soft_alpha_pixels = _count_alpha_pixels(rgba)
        remaining_key_pixels = 0
        if spec.background_key:
            key = parse_hex_color(spec.background_key)
            remaining_key_pixels = _count_remaining_key_pixels(rgba, key, tolerance)
        palette_size = _palette_size(rgba)

    issues: list[str] = []
    warnings: list[str] = []

    if expected is not None and (rgba.width, rgba.height) != expected:
        issues.append(f"Expected sprite size {expected[0]}x{expected[1]}, got {rgba.width}x{rgba.height}.")
    if spec.alpha_required and not alpha_present:
        issues.append("Sprite does not contain transparent pixels even though alpha is required.")
    if remaining_key_pixels:
        issues.append(f"Sprite still contains {remaining_key_pixels} chroma-key pixels near {spec.background_key}.")
    if spec.style == "pixel_art":
        if spec.palette_mode == "restricted" and palette_size > 256:
            warnings.append(f"Pixel-art sprite uses a large palette ({palette_size} colors).")
        if soft_alpha_pixels > max(4, (rgba.width * rgba.height) // 100):
            warnings.append(f"Sprite has {soft_alpha_pixels} soft-alpha pixels, which may indicate blurry edges.")

    return SpriteQAReport(
        valid=not issues,
        width=rgba.width,
        height=rgba.height,
        expected_size=expected,
        alpha_present=alpha_present,
        transparent_pixels=transparent_pixels,
        remaining_key_pixels=remaining_key_pixels,
        palette_size=palette_size,
        soft_alpha_pixels=soft_alpha_pixels,
        issues=issues,
        warnings=warnings,
    )


def write_sprite_qa_artifacts(
    *,
    project_root: Path,
    image_path: Path,
    spec: AssetSpec,
    report: SpriteQAReport,
    original_path: Path | None = None,
    artifact_name: str | None = None,
    tolerance: int = 8,
) -> SpriteQAReport:
    qa_dir = artifact_dir(project_root, "sprite-qa")
    stem = slugify_artifact_name(artifact_name or image_path.stem or "sprite")
    target_dir = qa_dir / stem
    target_dir.mkdir(parents=True, exist_ok=True)

    final_path = target_dir / "final.png"
    shutil.copyfile(image_path, final_path)
    report.artifacts["final"] = str(final_path)

    keyed_path = target_dir / "keyed.png"
    shutil.copyfile(image_path, keyed_path)
    report.artifacts["keyed"] = str(keyed_path)

    if original_path and original_path.exists():
        copied_original = target_dir / "original.png"
        shutil.copyfile(original_path, copied_original)
        report.artifacts["original"] = str(copied_original)

    with Image.open(image_path) as image:
        if spec.background_key:
            mask = _mask_remaining_key(image, parse_hex_color(spec.background_key), tolerance)
        else:
            mask = Image.new("RGBA", image.size, (0, 0, 0, 0))
    mask_path = target_dir / "mask.png"
    mask.save(mask_path, "PNG")
    report.artifacts["mask"] = str(mask_path)

    qa_path = target_dir / "qa.json"
    qa_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    report.artifacts["qa"] = str(qa_path)
    return report


def qa_sprite_file(
    *,
    project_root: Path,
    image_path: Path,
    spec: AssetSpec,
    original_path: Path | None = None,
    artifact_name: str | None = None,
    tolerance: int = 8,
) -> SpriteQAReport:
    report = analyze_sprite(image_path, spec, tolerance=tolerance)
    return write_sprite_qa_artifacts(
        project_root=project_root,
        image_path=image_path,
        spec=spec,
        report=report,
        original_path=original_path,
        artifact_name=artifact_name,
        tolerance=tolerance,
    )
