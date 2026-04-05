from pathlib import Path

from PIL import Image

from godot_agent.runtime.visual_regression import compare_image_files, resolve_baseline_path


def _write_png(path: Path, color: tuple[int, int, int, int], size: tuple[int, int] = (8, 8)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, color).save(path, "PNG")


def test_compare_image_files_matches_identical_images(tmp_path):
    actual = tmp_path / "actual.png"
    baseline = resolve_baseline_path(tmp_path, "ui/hud")
    _write_png(actual, (255, 0, 0, 255))
    _write_png(baseline, (255, 0, 0, 255))

    result = compare_image_files(
        project_root=tmp_path,
        actual_path=actual,
        baseline_path=baseline,
    )

    assert result.matched is True
    assert result.pixel_diff_count == 0


def test_compare_image_files_can_create_missing_baseline(tmp_path):
    actual = tmp_path / "actual.png"
    baseline = resolve_baseline_path(tmp_path, "ui/new_panel")
    _write_png(actual, (0, 255, 0, 255))

    result = compare_image_files(
        project_root=tmp_path,
        actual_path=actual,
        baseline_path=baseline,
        create_baseline=True,
    )

    assert result.matched is True
    assert result.baseline_created is True
    assert baseline.exists()


def test_different_images_report_pixel_diff(tmp_path):
    """Completely different images should report all pixels as differing."""
    actual = tmp_path / "actual.png"
    baseline = tmp_path / "baseline.png"
    _write_png(actual, (255, 0, 0, 255), size=(64, 64))
    _write_png(baseline, (0, 255, 0, 255), size=(64, 64))

    result = compare_image_files(
        project_root=tmp_path,
        actual_path=actual,
        baseline_path=baseline,
    )

    assert result.matched is False
    assert result.pixel_diff_count > 0
    # Every pixel differs: 64 * 64 = 4096
    assert result.pixel_diff_count == 64 * 64


def test_tolerance_allows_near_match(tmp_path):
    """Small per-channel deltas within tolerance should count as matching."""
    actual = tmp_path / "actual.png"
    baseline = tmp_path / "baseline.png"
    _write_png(actual, (255, 0, 0, 255), size=(64, 64))
    _write_png(baseline, (254, 1, 0, 255), size=(64, 64))

    result = compare_image_files(
        project_root=tmp_path,
        actual_path=actual,
        baseline_path=baseline,
        tolerance=5,
    )

    assert result.matched is True
    assert result.pixel_diff_count == 0


def test_tolerance_does_not_hide_large_diff(tmp_path):
    """Diffs beyond tolerance should still be counted."""
    actual = tmp_path / "actual.png"
    baseline = tmp_path / "baseline.png"
    _write_png(actual, (255, 0, 0, 255), size=(8, 8))
    _write_png(baseline, (200, 0, 0, 255), size=(8, 8))

    result = compare_image_files(
        project_root=tmp_path,
        actual_path=actual,
        baseline_path=baseline,
        tolerance=5,
    )

    assert result.matched is False
    assert result.pixel_diff_count == 8 * 8
    assert result.max_channel_delta == 55


def test_identical_images_zero_tolerance(tmp_path):
    """Identical 64x64 images with zero tolerance should match perfectly."""
    actual = tmp_path / "actual.png"
    baseline = tmp_path / "baseline.png"
    _write_png(actual, (255, 0, 0, 255), size=(64, 64))
    _write_png(baseline, (255, 0, 0, 255), size=(64, 64))

    result = compare_image_files(
        project_root=tmp_path,
        actual_path=actual,
        baseline_path=baseline,
        tolerance=0,
    )

    assert result.matched is True
    assert result.pixel_diff_count == 0
    assert result.max_channel_delta == 0
