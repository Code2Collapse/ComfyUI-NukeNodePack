# PORTED FROM: ComfyUI-ACES-IO + ComfyUI-OCIO — regression/capability tests for batch 2.
"""CPU-only tests for ACES-IO / OCIO port batch."""
from __future__ import annotations

import json

import pytest
import torch

from nukemax.nodes.io.exr_sequence import EXRSequenceLoad, EXRSequenceSave, ProResSave
from nukemax.nodes.io.video_sequence import NukeMax_VideoSequenceLoad
from nukemax.nodes.ocio_color.ocio_grade import (
    NukeMax_OCIOApplyGrade,
    NukeMax_OCIOGrade,
    NukeMax_OCIOGradeMatch,
)


@pytest.fixture
def img():
    torch.manual_seed(2)
    return torch.rand(1, 8, 8, 3)


class TestEXRLoadReconcile:
    def test_regression_no_ocio_params(self, img):
        # Synthetic: execute path with empty path would fail; verify optional keys exist
        spec = EXRSequenceLoad.INPUT_TYPES()["optional"]
        assert spec["ocio_input_colorspace"][1]["default"] == ""
        assert spec["ocio_output_colorspace"][1]["default"] == ""


class TestEXRSaveReconcile:
    def test_regression_optional_defaults(self):
        spec = EXRSequenceSave.INPUT_TYPES()["optional"]
        assert spec["colorspace_in_filename"][1]["default"] is False


class TestProResSaveReconcile:
    def test_regression_format_indices_unchanged(self):
        assert ProResSave.FORMATS[0] == "MOV ProRes 4444"
        assert ProResSave.FORMATS[4] == "MP4 (H.264)"

    def test_webp_gif_appended(self):
        assert ProResSave.FORMATS[-2:] == ["Animated WebP", "Animated GIF"]


class TestOCIOGradePort:
    def test_identity_grade(self, img):
        node = NukeMax_OCIOGrade()
        out, info = node.execute(
            img,
            0, 0, 0,
            1, 1, 1,
            1, 1, 1,
            0, 0, 0,
            1.0, 0.18, 1.0,
            1.0, False,
        )
        assert torch.allclose(out, img, atol=1e-6)
        assert json.loads(info)["type"] == "ocio_grade"

    def test_grade_match_same_ref(self, img):
        node = NukeMax_OCIOGradeMatch()
        out, info, note = node.execute(img, img, 1.0, 1.0, False)
        assert out.shape == img.shape
        assert "grade_info" in info or info.startswith("{")

    def test_apply_grade_empty_string(self, img):
        node = NukeMax_OCIOApplyGrade()
        out, = node.execute(img, "", 1.0, 1.0, False)
        assert torch.allclose(out, img)


class TestVideoLoadPort:
    def test_contract(self):
        spec = NukeMax_VideoSequenceLoad.INPUT_TYPES()
        assert "file_path" in spec["required"]
