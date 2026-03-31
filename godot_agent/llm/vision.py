from __future__ import annotations
import base64
from pathlib import Path


def encode_image(path: str | Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("utf-8")


def encode_images(paths: list[str | Path]) -> list[str]:
    return [encode_image(p) for p in paths]
