"""Shared sprite post-processing utilities."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, asdict
from pathlib import Path

from PIL import Image


@dataclass
class FrameSlice:
    index: int
    path: str
    source_rect: tuple[int, int, int, int]
    width: int
    height: int


@dataclass
class SpriteSheetManifest:
    source_path: str
    frame_width: int
    frame_height: int
    columns: int
    rows: int
    frame_count: int
    frames: list[FrameSlice]

    def to_dict(self) -> dict:
        return {
            "source_path": self.source_path,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "columns": self.columns,
            "rows": self.rows,
            "frame_count": self.frame_count,
            "frames": [asdict(frame) for frame in self.frames],
        }


def parse_hex_color(value: str) -> tuple[int, int, int]:
    cleaned = value.strip().lstrip("#")
    if len(cleaned) != 6:
        raise ValueError(f"Expected #RRGGBB color, got: {value}")
    return tuple(int(cleaned[index:index + 2], 16) for index in (0, 2, 4))


def chroma_key_to_transparent(
    img: Image.Image,
    *,
    chroma_key: tuple[int, int, int] = (0, 255, 0),
    tolerance: int = 60,
) -> Image.Image:
    img = img.convert("RGBA")
    pixels = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = pixels[x, y]
            if (
                abs(r - chroma_key[0]) <= tolerance
                and abs(g - chroma_key[1]) <= tolerance
                and abs(b - chroma_key[2]) <= tolerance
            ):
                pixels[x, y] = (0, 0, 0, 0)
    return img


def auto_crop(img: Image.Image, *, margin: int = 2) -> Image.Image:
    bbox = img.getbbox()
    if bbox is None:
        return img
    x1, y1, x2, y2 = bbox
    x1 = max(0, x1 - margin)
    y1 = max(0, y1 - margin)
    x2 = min(img.width, x2 + margin)
    y2 = min(img.height, y2 + margin)
    return img.crop((x1, y1, x2, y2))


def resize_pixel_art(img: Image.Image, target_size: int) -> Image.Image:
    max_dim = max(img.width, img.height)
    if img.width != img.height:
        square = Image.new("RGBA", (max_dim, max_dim), (0, 0, 0, 0))
        offset_x = (max_dim - img.width) // 2
        offset_y = (max_dim - img.height) // 2
        square.paste(img, (offset_x, offset_y))
        img = square
    return img.resize((target_size, target_size), Image.Resampling.NEAREST)


def post_process_sprite(
    raw_bytes: bytes,
    *,
    target_size: int,
    chroma_key: tuple[int, int, int] = (0, 255, 0),
    tolerance: int = 60,
) -> Image.Image:
    img = Image.open(io.BytesIO(raw_bytes))
    img = chroma_key_to_transparent(img, chroma_key=chroma_key, tolerance=tolerance)
    img = auto_crop(img)
    img = resize_pixel_art(img, target_size)
    return img


def slice_sprite_sheet(
    *,
    source_path: Path,
    output_dir: Path,
    frame_width: int,
    frame_height: int,
    columns: int = 0,
    rows: int = 0,
    prefix: str = "frame",
    chroma_key: tuple[int, int, int] | None = None,
    tolerance: int = 60,
    trim: bool = False,
) -> SpriteSheetManifest:
    with Image.open(source_path) as raw_image:
        image = raw_image.convert("RGBA")
    if chroma_key is not None:
        image = chroma_key_to_transparent(image, chroma_key=chroma_key, tolerance=tolerance)

    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("frame_width and frame_height must be positive")
    columns = columns or image.width // frame_width
    rows = rows or image.height // frame_height
    if columns <= 0 or rows <= 0:
        raise ValueError("Unable to infer rows/columns from the source image size")

    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[FrameSlice] = []
    index = 0
    for row in range(rows):
        for col in range(columns):
            left = col * frame_width
            top = row * frame_height
            rect = (left, top, left + frame_width, top + frame_height)
            frame = image.crop(rect)
            if trim:
                frame = auto_crop(frame, margin=0)
            frame_path = output_dir / f"{prefix}_{index:03d}.png"
            frame.save(frame_path, "PNG")
            frames.append(
                FrameSlice(
                    index=index,
                    path=str(frame_path),
                    source_rect=(left, top, frame_width, frame_height),
                    width=frame.width,
                    height=frame.height,
                )
            )
            index += 1

    return SpriteSheetManifest(
        source_path=str(source_path),
        frame_width=frame_width,
        frame_height=frame_height,
        columns=columns,
        rows=rows,
        frame_count=len(frames),
        frames=frames,
    )


def save_manifest(manifest: SpriteSheetManifest, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
    return path
