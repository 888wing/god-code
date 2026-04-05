from pathlib import Path

from PIL import Image

from godot_agent.runtime.design_memory import AssetSpec
from godot_agent.tools.sprite_qa import analyze_sprite, qa_sprite_file


def _write_image(path: Path, size: tuple[int, int], color: tuple[int, int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, color).save(path, "PNG")


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
