from pathlib import Path

from PIL import Image

from godot_agent.runtime.visual_regression import compare_image_files, resolve_baseline_path


def _write_png(path: Path, color: tuple[int, int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (8, 8), color).save(path, "PNG")


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
