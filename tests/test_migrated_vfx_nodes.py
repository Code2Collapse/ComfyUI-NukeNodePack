"""VFX nodes migrated from ComfyUI-CustomNodePacks — regression cover.

PORTED FROM: ComfyUI-CustomNodePacks :: tests/test_phase4_nodes.py

These six modules (color_science, render_pass, plate_tools, geometry_nodes,
metadata_nodes, exr_metadata_reader) were migrated here in Apr 2026, then
accidentally RE-REGISTERED in CustomNodePacks by a 2026-05 "restore" whose check
("no replacement in the current pack") only looked inside CNP. That produced 18
duplicate node ids resolved by unsorted os.listdir order — see
tests/test_cross_pack_no_duplicate_ids.py.

Coverage moves with the code: NukeMaxNodes had ZERO tests for any of these seven
modules while CNP had 74. These run against the NukeMax implementations BEFORE
CNP's copies are deleted, so a CNP-only fix would surface as a failure here
rather than as a silent regression.

exr_io is deliberately NOT covered here: CustomNodePacks keeps it, because its
OpenImageIO path is the only EXR backend that works in this environment.
"""
from __future__ import annotations

import json
import os
import struct
from pathlib import Path

import numpy as np
import pytest
import torch

from nukemax.nodes.color.color_science import (
    ColorSpaceConvertMEC, ExposureGradeMEC, LUTApplyMEC,
    parse_cube_lut,
)
from nukemax.nodes.passes.render_pass import DepthOfFieldMaskMEC, MergeRenderPassesMEC
from nukemax.nodes.plate.plate_tools import (
    CleanPlateExtractorMEC, DifferenceMatteMEC, GrainMatchMEC, PlateStabilizerMEC,
)
from nukemax.nodes.geometry_ext.geometry_nodes import (
    DepthWarpMEC, NormalToCurvatureMEC, PositionPassSplitterMEC,
)
from nukemax.nodes.metadata.metadata_nodes import (
    FrameRangeRouterMEC, MetadataWriterMEC, ShotMetadataNodeMEC,
)


# ──────────────────────────────────────────────────────────────────────
#  Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def small_image():
    torch.manual_seed(0)
    return torch.rand(1, 16, 24, 3)


@pytest.fixture
def video_batch():
    torch.manual_seed(1)
    return torch.rand(4, 16, 16, 3)


# ──────────────────────────────────────────────────────────────────────
#  Color science
# ──────────────────────────────────────────────────────────────────────

class TestColorSpaceConvert:
    def test_round_trip_srgb_linear(self, small_image):
        node = ColorSpaceConvertMEC()
        lin, = node.convert(small_image, "srgb", "linear")
        rt, = node.convert(lin, "linear", "srgb")
        assert torch.allclose(rt, small_image, atol=1e-4)

    def test_acescg_round_trip(self, small_image):
        node = ColorSpaceConvertMEC()
        ac, = node.convert(small_image, "srgb", "acescg")
        rt, = node.convert(ac, "acescg", "srgb")
        assert torch.allclose(rt, small_image, atol=5e-3)

    def test_identity(self, small_image):
        node = ColorSpaceConvertMEC()
        out, = node.convert(small_image, "linear", "linear")
        assert torch.equal(out, small_image)


class TestLUTApply:
    def _write_identity_3d_cube(self, path: Path, size: int = 4) -> Path:
        lines = [f"LUT_3D_SIZE {size}"]
        for b in range(size):
            for g in range(size):
                for r in range(size):
                    lines.append(f"{r/(size-1):.6f} {g/(size-1):.6f} {b/(size-1):.6f}")
        path.write_text("\n".join(lines))
        return path

    def _write_invert_3d_cube(self, path: Path, size: int = 4) -> Path:
        lines = [f"LUT_3D_SIZE {size}"]
        for b in range(size):
            for g in range(size):
                for r in range(size):
                    lines.append(
                        f"{1-r/(size-1):.6f} {1-g/(size-1):.6f} {1-b/(size-1):.6f}",
                    )
        path.write_text("\n".join(lines))
        return path

    def test_identity_lut(self, tmp_path, small_image):
        lut_path = self._write_identity_3d_cube(tmp_path / "id.cube", size=8)
        info = parse_cube_lut(str(lut_path))
        assert info["dim"] == 3 and info["size"] == 8
        node = LUTApplyMEC()
        out, info_json = node.apply(small_image, str(lut_path), strength=1.0)
        # Identity LUT should be near-identity (small interp error)
        assert torch.allclose(out, small_image, atol=0.05)
        assert json.loads(info_json)["dim"] == 3

    def test_invert_lut_strength_zero(self, tmp_path, small_image):
        lut_path = self._write_invert_3d_cube(tmp_path / "inv.cube", size=8)
        node = LUTApplyMEC()
        out, _ = node.apply(small_image, str(lut_path), strength=0.0)
        assert torch.allclose(out, small_image, atol=1e-6)

    def test_missing_file(self, small_image):
        node = LUTApplyMEC()
        with pytest.raises(FileNotFoundError):
            node.apply(small_image, "/no/such/file.cube", 1.0)


class TestExposureGrade:
    def test_exposure_doubles_at_one_stop(self, small_image):
        node = ExposureGradeMEC()
        out, = node.grade(small_image, 1.0, 0.0, 0.0, 1.0, 0.18, operate_in_linear=False)
        # In display-referred mode, +1 stop = ×2 directly, clamped.
        expected = (small_image * 2.0).clamp(0.0, 1.0)
        assert torch.allclose(out, expected, atol=1e-5)

    def test_zero_settings_passthrough(self, small_image):
        node = ExposureGradeMEC()
        out, = node.grade(small_image, 0.0, 0.0, 0.0, 1.0, 0.18, operate_in_linear=False)
        assert torch.allclose(out, small_image, atol=1e-6)


# ──────────────────────────────────────────────────────────────────────
#  EXR I/O — only run when at least one backend is available
# ──────────────────────────────────────────────────────────────────────

def _has_exr_backend() -> bool:
    try:
        import OpenEXR  # noqa: F401
        import Imath  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import imageio.v3 as iio  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _has_exr_backend(), reason="No EXR backend installed")
class TestMergeRenderPasses:
    def test_beauty_only_passthrough(self, small_image):
        node = MergeRenderPassesMEC()
        out, = node.merge(small_image)
        assert torch.allclose(out, small_image, atol=1e-6)

    def test_ao_multiplier(self, small_image):
        node = MergeRenderPassesMEC()
        ao = torch.full((1, 16, 24, 1), 0.5)
        out, = node.merge(small_image, ao=ao, ao_strength=1.0)
        assert torch.allclose(out, small_image * 0.5, atol=1e-6)

    def test_emission_added(self, small_image):
        node = MergeRenderPassesMEC()
        em = torch.full_like(small_image, 0.1)
        out, = node.merge(small_image, emission=em, emission_gain=1.0)
        assert torch.allclose(out, (small_image + 0.1), atol=1e-6)


class TestDepthOfFieldMask:
    def test_in_focus_at_focus_distance(self):
        depth = torch.full((1, 8, 8, 1), 0.5)
        coc, focus = DepthOfFieldMaskMEC().compute(depth, 0.5, 0.1, False, "R")
        assert torch.allclose(coc, torch.zeros_like(coc))
        assert torch.allclose(focus, torch.ones_like(focus))

    def test_full_defocus_far_from_focus(self):
        depth = torch.full((1, 8, 8, 1), 1.0)
        coc, _ = DepthOfFieldMaskMEC().compute(depth, 0.0, 0.1, False, "R")
        assert torch.allclose(coc, torch.ones_like(coc))


# ──────────────────────────────────────────────────────────────────────
#  Plate tools
# ──────────────────────────────────────────────────────────────────────

class TestGrainMatch:
    def test_zero_intensity_passthrough(self, small_image):
        out, _ = GrainMatchMEC().match(small_image, small_image, 0.0, 5, 0)
        assert torch.allclose(out, small_image, atol=1e-6)

    def test_grain_added(self, small_image):
        ref = small_image + 0.1 * torch.randn_like(small_image)
        ref = ref.clamp(0.0, 1.0)
        out, info = GrainMatchMEC().match(ref, small_image, 1.0, 5, 0)
        assert out.shape == small_image.shape
        d = json.loads(info)
        assert d["grain_std"] > 0


class TestPlateStabilizer:
    def test_single_frame_noop(self):
        img = torch.rand(1, 8, 8, 3)
        out, info = PlateStabilizerMEC().stabilize(img)
        assert torch.equal(out, img)
        assert json.loads(info)["backend"] == "noop"

    def test_translation_recovery_fft(self):
        # Create frame 0, then frame 1 = frame 0 shifted by (2, 3) px
        torch.manual_seed(7)
        a = torch.rand(1, 32, 32, 3)
        # Build shifted copy by rolling — emulates a real translation.
        shifted = torch.roll(a, shifts=(2, 3), dims=(1, 2))
        batch = torch.cat([a, shifted], dim=0)
        # Force fft backend
        from nukemax.nodes.plate import plate_tools as pt
        out, info = pt.PlateStabilizerMEC()._stabilize_fft(batch)
        # After stabilization, frame 1 should be much closer to frame 0
        before = (batch[1] - a[0]).abs().mean().item()
        after = (out[1] - a[0]).abs().mean().item()
        assert after < before


class TestCleanPlate:
    def test_median_no_mask(self):
        # 5 frames of constant 0.5 with one outlier should yield ~0.5
        b = torch.full((5, 8, 8, 3), 0.5)
        b[2] = 1.0
        out, = CleanPlateExtractorMEC().extract(b)
        assert out.shape == (1, 8, 8, 3)
        assert torch.allclose(out, torch.full_like(out, 0.5))

    def test_mask_excludes_pixels(self):
        b = torch.zeros(3, 4, 4, 3)
        b[0] = 1.0  # frame 0 is bad
        m = torch.zeros(3, 4, 4)
        m[0] = 1.0  # exclude frame 0
        out, = CleanPlateExtractorMEC().extract(b, exclude_mask=m)
        assert torch.allclose(out, torch.zeros_like(out))


class TestDifferenceMatte:
    def test_identical_inputs_zero(self, small_image):
        m, = DifferenceMatteMEC().compute(small_image, small_image, "l2", 0.05, 0.0)
        assert torch.allclose(m, torch.zeros_like(m))

    def test_changed_pixel_high(self):
        a = torch.zeros(1, 4, 4, 3)
        b = torch.ones(1, 4, 4, 3)
        m, = DifferenceMatteMEC().compute(a, b, "l1", 0.5, 0.0)
        assert torch.allclose(m, torch.ones_like(m))


# ──────────────────────────────────────────────────────────────────────
#  Geometry
# ──────────────────────────────────────────────────────────────────────

class TestDepthWarp:
    def test_zero_shift_identity(self, small_image):
        d = torch.full((1, 16, 24, 1), 0.5)
        out, = DepthWarpMEC().warp(small_image, d, 0.0, 0.5)
        assert torch.allclose(out, small_image, atol=1e-4)


class TestNormalToCurvature:
    def test_flat_normal_zero_curvature(self):
        # Tangent-space "up" normal → (0.5, 0.5, 1.0) in [0,1]
        n = torch.zeros(1, 8, 8, 3)
        n[..., 0] = 0.5
        n[..., 1] = 0.5
        n[..., 2] = 1.0
        c, = NormalToCurvatureMEC().compute(n, 1.0)
        assert torch.allclose(c, torch.full_like(c, 0.5), atol=1e-5)


class TestPositionPassSplitter:
    def test_auto_normalizes_each_axis(self):
        p = torch.zeros(1, 4, 4, 3)
        p[..., 0] = torch.linspace(0.0, 1.0, 4).repeat(4, 1)
        x, y, z = PositionPassSplitterMEC().split(p, auto_normalize=True)
        assert x.shape == (1, 4, 4)
        assert float(x.amin()) == 0.0 and float(x.amax()) == 1.0


# ──────────────────────────────────────────────────────────────────────
#  Metadata
# ──────────────────────────────────────────────────────────────────────

class TestMetadataWriter:
    def test_writes_sidecar(self, tmp_path, small_image):
        sc = tmp_path / "out.json"
        node = MetadataWriterMEC()
        _, written = node.write(small_image, str(sc), '{"a": 1}')
        assert sc.exists()
        with open(sc) as fh:
            assert json.load(fh) == {"a": 1}
        assert "/" in written  # forward-slashed

    def test_merge_existing(self, tmp_path, small_image):
        sc = tmp_path / "merge.json"
        sc.write_text('{"keep": true}')
        node = MetadataWriterMEC()
        node.write(small_image, str(sc), '{"new": 2}', merge_existing=True)
        with open(sc) as fh:
            data = json.load(fh)
        assert data == {"keep": True, "new": 2}

    def test_invalid_json_raises(self, tmp_path, small_image):
        sc = tmp_path / "x.json"
        with pytest.raises(ValueError):
            MetadataWriterMEC().write(small_image, str(sc), "{not json")


class TestFrameRangeRouter:
    def test_basic_slice(self, video_batch):
        out, _, n = FrameRangeRouterMEC().route(video_batch, 1, 3, 1)
        assert out.shape[0] == 2 and n == 2

    def test_step(self, video_batch):
        out, _, n = FrameRangeRouterMEC().route(video_batch, 0, 4, 2)
        assert out.shape[0] == 2 and n == 2

    def test_negative_end_means_full(self, video_batch):
        out, _, n = FrameRangeRouterMEC().route(video_batch, 0, -1, 1)
        assert out.shape[0] == video_batch.shape[0]


class TestShotMetadata:
    def test_reads_fields(self, tmp_path):
        p = tmp_path / "shot.json"
        p.write_text(json.dumps({
            "show": "S1", "shot": "010", "task": "comp",
            "frame_in": 1001, "frame_out": 1100, "fps": 23.976,
        }))
        out = ShotMetadataNodeMEC().read(str(p))
        assert out[0] == "S1" and out[1] == "010" and out[2] == "comp"
        assert out[3] == 1001 and out[4] == 1100
        assert abs(out[5] - 23.976) < 1e-6

    def test_missing_raises(self):
        with pytest.raises(FileNotFoundError):
            ShotMetadataNodeMEC().read("/nope/shot.json")


# ──────────────────────────────────────────────────────────────────────
#  Model analysis
# ──────────────────────────────────────────────────────────────────────

class _FakeVAE:
    def __init__(self, sd):
        self._sd = sd
    def state_dict(self):
        return self._sd

