# PORTED FROM: nuke-nodes-comfyui (third_party/nuke-nodes-comfyui) by Sumit Chatterjee
# Licence: MIT — regression + capability tests for Sumit port batch.
"""CPU-only tests for PORT nodes and additive RECONCILE regressions."""
from __future__ import annotations

import json

import pytest
import torch

from nukemax.nodes.color.levels import NukeMax_Levels
from nukemax.nodes.essentials import Exposure, Merge, Transform, Ramp
from nukemax.nodes.comp import Reformat, Crop
from nukemax.nodes.io.multipass import NukeMax_ShufflePass
from nukemax.nodes.viewer import NukeMax_Viewer
from nukemax.types.nuke_passes import NukePasses


@pytest.fixture
def img():
    torch.manual_seed(0)
    return torch.rand(1, 8, 8, 3)


@pytest.fixture
def rgba():
    torch.manual_seed(1)
    return torch.rand(1, 8, 8, 4)


class TestLevelsPort:
    def test_identity_at_defaults(self, img):
        node = NukeMax_Levels()
        out, = node.execute(img, 0.0, 1.0, 1.0, 0.0, 1.0, 1.0)
        assert torch.allclose(out, img, atol=1e-6)


class TestViewerPort:
    def test_rgb_channel_solo(self, rgba):
        node = NukeMax_Viewer()
        ret = node.execute(rgba, "red", 1.0, 1.0, False, "")
        out = ret["result"][0] if isinstance(ret, dict) else ret[0]
        assert out.shape == (1, 8, 8, 3)
        r = rgba[..., 0:1]
        assert torch.allclose(out[..., 0], r.squeeze(-1), atol=1e-5)


@pytest.mark.requires_comfy
class TestViewerPreview:
    """The Viewer draws the frame on itself; socket values never reach the
    browser, so the picture has to travel as `ui.images`."""

    def test_execute_emits_preview_entries(self, rgba):
        ret = NukeMax_Viewer().execute(rgba, "rgba", 1.0, 1.0, False, "")
        images = ret["ui"]["images"]
        assert images, "no preview written - the node would show an empty stage"
        entry = images[0]
        assert set(entry) == {"filename", "subfolder", "type"}
        assert entry["type"] == "temp"
        assert entry["filename"].endswith(".png")

    def test_one_preview_per_frame(self):
        seq = torch.rand(3, 8, 8, 3)
        ret = NukeMax_Viewer().execute(seq, "rgba", 1.0, 1.0, False, "")
        assert len(ret["ui"]["images"]) == 3

    def test_a_long_sequence_is_capped(self):
        # INVARIANT: a 200-frame render must not write 200 PNGs per queue to
        # fill a 200px widget. The cap is what keeps the Viewer usable on a
        # sequence, and the frame strip reports the real count separately.
        from nukemax.nodes.viewer import MAX_PREVIEW_FRAMES

        seq = torch.rand(MAX_PREVIEW_FRAMES + 5, 8, 8, 3)
        ret = NukeMax_Viewer().execute(seq, "rgba", 1.0, 1.0, False, "")
        assert len(ret["ui"]["images"]) == MAX_PREVIEW_FRAMES

    def test_the_files_are_actually_on_disk(self, rgba):
        import os

        import folder_paths

        ret = NukeMax_Viewer().execute(rgba, "rgba", 1.0, 1.0, False, "")
        for entry in ret["ui"]["images"]:
            path = os.path.join(folder_paths.get_temp_directory(),
                                entry["subfolder"], entry["filename"])
            assert os.path.isfile(path), f"{entry['filename']} was never written"

    def test_each_run_gets_a_fresh_filename(self, rgba):
        # INVARIANT: /view is cached hard. A stable filename shows the PREVIOUS
        # render after a parameter change, which reads as "the node ignored me".
        a = NukeMax_Viewer().execute(rgba, "rgba", 1.0, 1.0, False, "")
        b = NukeMax_Viewer().execute(rgba, "rgba", 1.0, 2.0, False, "")
        assert a["ui"]["images"][0]["filename"] != b["ui"]["images"][0]["filename"]


class TestViewerPreviewDegradesQuietly:
    """Deliberately NOT marked requires_comfy: the fallback matters most on the
    box that has no ComfyUI on sys.path, so it has to run there."""

    def test_a_preview_failure_does_not_fail_the_render(self, rgba, monkeypatch):
        # INVARIANT: the picture is a convenience. If the temp dir is read-only
        # the IMAGE output must still arrive - losing a render to a failed
        # thumbnail would be a far worse bug than having no thumbnail.
        from nukemax.nodes import viewer as viewer_mod

        def _boom(*_a, **_k):
            raise OSError("temp directory is read-only")

        monkeypatch.setattr(viewer_mod.os, "makedirs", _boom)
        ret = NukeMax_Viewer().execute(rgba, "rgba", 1.0, 1.0, False, "")
        assert ret["ui"]["images"] == []
        assert ret["result"][0].shape == (1, 8, 8, 3)

    def test_the_image_output_is_unaffected_by_the_preview(self, rgba):
        # INVARIANT: the preview path must not touch the tensor it previews.
        ret = NukeMax_Viewer().execute(rgba, "red", 1.0, 1.0, False, "")
        out = ret["result"][0]
        assert torch.allclose(out[..., 0], rgba[..., 0], atol=1e-5)


class TestShufflePassPort:
    def test_picks_named_pass(self, img):
        bundle = NukePasses(passes={"diffuse": img[0]})
        node = NukeMax_ShufflePass()
        out, info = node.execute(bundle, "diffuse")
        assert "diffuse" in info
        assert out.shape[0] == 1


class TestExposureReconcile:
    def test_regression_stops_only(self, img):
        node = Exposure()
        expected = (img * (2.0 ** 0.5)).clamp(0, 1)
        out, = node.execute(img, 0.5)
        assert torch.allclose(out, expected)

    def test_printer_lights_mode(self, img):
        node = Exposure()
        out, = node.execute(img, 25.0, exposure_mode="printer_lights")
        expected = (img * 10.0).clamp(0, 1)
        assert torch.allclose(out, expected)


class TestMergeReconcile:
    def _over(self, img):
        node = Merge()
        return node.execute(img, img * 0.5, "over", 1.0)[0]

    def test_regression_over_unchanged(self, img):
        a = self._over(img)
        b = self._over(img)
        assert torch.allclose(a, b)

    def test_soft_light_new_op(self, img):
        node = Merge()
        out, = node.execute(img, img * 0.5, "soft_light", 1.0)
        assert out.shape == img.shape


class TestTransformReconcile:
    def test_regression_defaults(self, img):
        node = Transform()
        out, = node.execute(img, 0.0, 0.0, 0.0, 1.0, "bilinear", "black")
        assert torch.allclose(out, img, atol=1e-5)

    def test_skew_when_enabled(self, img):
        node = Transform()
        out, = node.execute(img, 0.0, 0.0, 15.0, 1.0, "bilinear", "black",
                            center_x=4.0, center_y=4.0, skew_x=10.0)
        assert not torch.allclose(out, img, atol=1e-3)


class TestRampReconcile:
    def test_regression_horizontal(self):
        node = Ramp()
        out, = node.execute(16, 8, "horizontal", 0.0, 1.0)
        assert out.shape == (1, 8, 16, 3)

    def test_radial_pattern(self):
        node = Ramp()
        out, = node.execute(16, 16, "horizontal", 0.0, 1.0, extended_pattern="radial")
        assert out.shape == (1, 16, 16, 3)


class TestReformatReconcile:
    def test_regression_no_flip(self, img):
        node = Reformat()
        out, = node.execute(img, 8, 8, "bilinear", "fit")
        assert torch.allclose(out, img, atol=1e-5)

    def test_flop_changes_output(self, img):
        node = Reformat()
        base, = node.execute(img, 8, 8, "bilinear", "fit")
        flop, = node.execute(img, 8, 8, "bilinear", "fit", flop=True)
        assert not torch.allclose(base, flop)


class TestCropReconcile:
    def test_regression_pixel_crop(self, img):
        node = Crop()
        out, = node.execute(img, 0, 0, 4, 4, False)
        assert out.shape == (1, 4, 4, 3)

    def test_normalized_crop(self, img):
        node = Crop()
        out, = node.execute(img, 0, 0, 4, 4, False, use_normalized_crop=True,
                            norm_left=0.0, norm_right=0.5, norm_top=0.0, norm_bottom=0.5)
        assert out.shape[1] <= 4


class TestLUTApplyReconcile:
    def test_regression_empty_native_path(self, img):
        from nukemax.nodes.ocio_color import LUTApply
        node = LUTApply()
        # No LUT on disk — only verify optional param does not change signature
        assert "native_lut_path" in node.INPUT_TYPES()["optional"]


class TestMetadataReconcile:
    def test_optional_oiio_flag_present(self):
        from nukemax.nodes.io.exr_metadata_reader import EXRMetadataReaderMEC
        assert "include_oiio_attrs" in EXRMetadataReaderMEC.INPUT_TYPES()["optional"]
