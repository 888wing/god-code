"""Persistent screenshot artifacts and image comparison helpers."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

ARTIFACT_ROOT_NAME = ".god-code-artifacts"
DEFAULT_BASELINE_ROOT = "tests/baselines"


@dataclass
class ImageComparison:
    matched: bool
    actual_path: str
    baseline_path: str
    diff_path: str = ""
    pixel_diff_count: int = 0
    max_channel_delta: int = 0
    diff_bbox: tuple[int, int, int, int] | None = None
    width: int = 0
    height: int = 0
    reason: str = ""
    baseline_created: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def artifact_root(project_root: Path) -> Path:
    root = project_root.resolve() / ARTIFACT_ROOT_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def artifact_dir(project_root: Path, category: str) -> Path:
    target = artifact_root(project_root) / category
    target.mkdir(parents=True, exist_ok=True)
    return target


def slugify_artifact_name(value: str, fallback: str = "artifact") -> str:
    candidate = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    return candidate or fallback


def build_artifact_path(
    project_root: Path,
    *,
    category: str,
    name: str,
    suffix: str = ".png",
) -> Path:
    safe_name = slugify_artifact_name(name)
    return artifact_dir(project_root, category) / f"{safe_name}{suffix}"


def baseline_root(project_root: Path) -> Path:
    preferred = project_root.resolve() / DEFAULT_BASELINE_ROOT
    if preferred.exists():
        preferred.mkdir(parents=True, exist_ok=True)
        return preferred
    fallback = project_root.resolve() / ".god-code" / "baselines"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def resolve_baseline_path(project_root: Path, baseline_id: str) -> Path:
    relative = Path(baseline_id)
    if relative.suffix.lower() != ".png":
        relative = relative.with_suffix(".png")
    path = baseline_root(project_root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def copy_to_artifact(src_path: Path, dest_path: Path) -> Path:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src_path, dest_path)
    return dest_path


def _normalize_region(region: list[int] | tuple[int, int, int, int] | None) -> tuple[int, int, int, int] | None:
    if not region:
        return None
    if len(region) != 4:
        raise ValueError("Region must have exactly 4 integers: [x, y, width, height]")
    x, y, width, height = (int(value) for value in region)
    if width <= 0 or height <= 0:
        raise ValueError("Region width and height must be positive")
    return (x, y, x + width, y + height)


def _crop_region(image: Image.Image, region: tuple[int, int, int, int] | None) -> Image.Image:
    return image.crop(region) if region else image


def _difference_metrics(diff: Image.Image, tolerance: int) -> tuple[int, int]:
    pixel_diff_count = 0
    max_channel_delta = 0
    pixels = diff.load()
    for y in range(diff.height):
        for x in range(diff.width):
            pixel = pixels[x, y]
            if isinstance(pixel, int):
                channels = (pixel,)
            else:
                channels = tuple(int(channel) for channel in pixel)
            local_max = max(channels)
            max_channel_delta = max(max_channel_delta, local_max)
            if local_max > tolerance:
                pixel_diff_count += 1
    return pixel_diff_count, max_channel_delta


def compare_image_files(
    *,
    project_root: Path,
    actual_path: Path,
    baseline_path: Path,
    tolerance: int = 0,
    region: list[int] | tuple[int, int, int, int] | None = None,
    diff_path: Path | None = None,
    create_baseline: bool = False,
) -> ImageComparison:
    if not actual_path.exists():
        return ImageComparison(
            matched=False,
            actual_path=str(actual_path),
            baseline_path=str(baseline_path),
            reason="actual_missing",
        )

    if not baseline_path.exists():
        if create_baseline:
            copy_to_artifact(actual_path, baseline_path)
            return ImageComparison(
                matched=True,
                actual_path=str(actual_path),
                baseline_path=str(baseline_path),
                baseline_created=True,
                reason="baseline_created",
            )
        return ImageComparison(
            matched=False,
            actual_path=str(actual_path),
            baseline_path=str(baseline_path),
            reason="missing_baseline",
        )

    normalized_region = _normalize_region(region)
    with Image.open(actual_path) as actual_raw, Image.open(baseline_path) as baseline_raw:
        actual = _crop_region(actual_raw.convert("RGBA"), normalized_region)
        baseline = _crop_region(baseline_raw.convert("RGBA"), normalized_region)

        if actual.size != baseline.size:
            size_diff_path = diff_path or build_artifact_path(
                project_root,
                category="diffs",
                name=f"{actual_path.stem}-size-mismatch",
            )
            width = max(actual.width, baseline.width)
            height = max(actual.height, baseline.height)
            actual_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            baseline_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            actual_canvas.paste(actual, (0, 0))
            baseline_canvas.paste(baseline, (0, 0))
            diff = ImageChops.difference(actual_canvas, baseline_canvas)
            diff.save(size_diff_path)
            bbox = diff.getbbox()
            pixel_diff_count, max_channel_delta = _difference_metrics(diff, tolerance=0)
            return ImageComparison(
                matched=False,
                actual_path=str(actual_path),
                baseline_path=str(baseline_path),
                diff_path=str(size_diff_path),
                pixel_diff_count=pixel_diff_count,
                max_channel_delta=max_channel_delta,
                diff_bbox=bbox,
                width=width,
                height=height,
                reason="size_mismatch",
            )

        diff = ImageChops.difference(actual, baseline)
        pixel_diff_count, max_channel_delta = _difference_metrics(diff, tolerance=tolerance)
        bbox = diff.getbbox()
        matched = pixel_diff_count == 0

        diff_output = diff_path or build_artifact_path(
            project_root,
            category="diffs",
            name=f"{actual_path.stem}-vs-{baseline_path.stem}",
        )
        if not matched or diff_output.exists():
            diff.save(diff_output)

        return ImageComparison(
            matched=matched,
            actual_path=str(actual_path),
            baseline_path=str(baseline_path),
            diff_path=str(diff_output) if diff_output.exists() else "",
            pixel_diff_count=pixel_diff_count,
            max_channel_delta=max_channel_delta,
            diff_bbox=bbox,
            width=actual.width,
            height=actual.height,
        )


def write_failure_bundle(project_root: Path, *, test_id: str, payload: dict[str, Any]) -> Path:
    bundle_path = build_artifact_path(
        project_root,
        category="failures",
        name=test_id,
        suffix=".json",
    )
    bundle_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return bundle_path
