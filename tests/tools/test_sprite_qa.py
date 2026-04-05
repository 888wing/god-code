from pathlib import Path

from PIL import Image

from godot_agent.runtime.design_memory import AssetSpec
from godot_agent.tools.sprite_qa import (
    _count_alpha_pixels,
    _count_remaining_key_pixels,
    analyze_sprite,
    qa_sprite_file,
)


def _write_image(path: Path, size: tuple[int, int], color: tuple[int, int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, color).save(path, "PNG")


# ---------------------------------------------------------------------------
# _count_remaining_key_pixels tests
# ---------------------------------------------------------------------------


def test_count_key_pixels_exact_match():
    """All opaque pixels matching the key colour are counted."""
    img = Image.new("RGBA", (4, 4), (0, 255, 0, 255))
    assert _count_remaining_key_pixels(img, (0, 255, 0), tolerance=0) == 16


def test_count_key_pixels_within_tolerance():
    """Pixels close to the key (within tolerance) are counted."""
    # (5, 250, 5) is within tolerance=10 of (0, 255, 0)
    img = Image.new("RGBA", (2, 2), (5, 250, 5, 255))
    assert _count_remaining_key_pixels(img, (0, 255, 0), tolerance=10) == 4


def test_count_key_pixels_outside_tolerance():
    """Pixels beyond tolerance are not counted."""
    img = Image.new("RGBA", (2, 2), (20, 255, 0, 255))
    assert _count_remaining_key_pixels(img, (0, 255, 0), tolerance=5) == 0


def test_count_key_pixels_skips_transparent():
    """Fully-transparent pixels are not counted even if RGB matches key."""
    img = Image.new("RGBA", (3, 3), (0, 255, 0, 0))  # alpha=0
    assert _count_remaining_key_pixels(img, (0, 255, 0), tolerance=0) == 0


def test_count_key_pixels_mixed():
    """Only opaque key-colour pixels are counted in a mixed image."""
    img = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
    pixels = img.load()
    pixels[0, 0] = (0, 255, 0, 255)  # key, opaque  -> counted
    pixels[1, 0] = (0, 255, 0, 0)    # key, transparent -> skip
    pixels[0, 1] = (255, 0, 0, 255)  # non-key, opaque  -> skip
    pixels[1, 1] = (0, 255, 0, 128)  # key, semi-transparent -> counted
    assert _count_remaining_key_pixels(img, (0, 255, 0), tolerance=0) == 2


# ---------------------------------------------------------------------------
# _count_alpha_pixels tests
# ---------------------------------------------------------------------------


def test_alpha_pixels_fully_opaque():
    """No transparent or soft-alpha pixels in a fully opaque image."""
    img = Image.new("RGBA", (4, 4), (100, 100, 100, 255))
    present, transparent, soft = _count_alpha_pixels(img)
    assert present is False
    assert transparent == 0
    assert soft == 0


def test_alpha_pixels_fully_transparent():
    """All pixels transparent (alpha=0), none are soft-alpha."""
    img = Image.new("RGBA", (3, 3), (0, 0, 0, 0))
    present, transparent, soft = _count_alpha_pixels(img)
    assert present is True
    assert transparent == 9
    assert soft == 0


def test_alpha_pixels_soft_alpha():
    """Semi-transparent pixels count as both transparent and soft-alpha."""
    img = Image.new("RGBA", (2, 2), (0, 0, 0, 128))
    present, transparent, soft = _count_alpha_pixels(img)
    assert present is True
    assert transparent == 4
    assert soft == 4


def test_alpha_pixels_mixed():
    """Mixed opaque, transparent, and soft-alpha pixels."""
    img = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
    pixels = img.load()
    pixels[0, 0] = (0, 0, 0, 255)  # opaque
    pixels[1, 0] = (0, 0, 0, 0)    # fully transparent
    pixels[0, 1] = (0, 0, 0, 128)  # soft alpha
    pixels[1, 1] = (0, 0, 0, 1)    # soft alpha (barely visible)
    present, transparent, soft = _count_alpha_pixels(img)
    assert present is True
    assert transparent == 3   # 0 + 128 + 1 (all < 255)
    assert soft == 2          # 128 + 1 (both 0 < x < 255)


# ---------------------------------------------------------------------------
# Integration tests (via analyze_sprite)
# ---------------------------------------------------------------------------


def test_analyze_sprite_flags_size_and_alpha_issues(tmp_path):
    image_path = tmp_path / "sprite.png"
    _write_image(image_path, (32, 32), (255, 0, 0, 255))

    report = analyze_sprite(
        image_path,
        AssetSpec(style="pixel_art", target_size=[64, 64], alpha_required=True, background_key="#00FF00"),
    )

    assert report.valid is False
    assert any("64x64" in issue for issue in report.issues)
    assert any("transparent" in issue.lower() for issue in report.issues)


def test_qa_sprite_file_writes_artifacts(tmp_path):
    image_path = tmp_path / "sprite.png"
    original_path = tmp_path / "original.png"
    _write_image(original_path, (64, 64), (0, 255, 0, 255))
    _write_image(image_path, (64, 64), (255, 0, 0, 0))

    report = qa_sprite_file(
        project_root=tmp_path,
        image_path=image_path,
        spec=AssetSpec(style="pixel_art", target_size=[64, 64], alpha_required=False, background_key="#00FF00"),
        original_path=original_path,
        artifact_name="enemy",
    )

    assert "qa" in report.artifacts
    assert Path(report.artifacts["qa"]).exists()
    assert Path(report.artifacts["mask"]).exists()
