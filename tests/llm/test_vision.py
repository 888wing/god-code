import pytest
from pathlib import Path
from godot_agent.llm.vision import encode_image, encode_images


class TestVision:
    def test_encode_image(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        b64 = encode_image(img)
        assert isinstance(b64, str)
        assert len(b64) > 0

    def test_encode_multiple(self, tmp_path):
        for i in range(3):
            (tmp_path / f"img_{i}.png").write_bytes(b"\x89PNG" + bytes(i) * 50)
        paths = [tmp_path / f"img_{i}.png" for i in range(3)]
        results = encode_images(paths)
        assert len(results) == 3
        assert all(isinstance(r, str) for r in results)
