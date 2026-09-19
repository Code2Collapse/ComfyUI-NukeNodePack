# Tests for the Radiance HDR port. See nukemax/nodes/hdr/nodes.py for provenance.
"""CPU-only, weight-free tests for the NukeMax/HDR family.

These replace a first pass that mostly asserted shapes ("out.shape == in.shape")
and one assertion that was simply wrong about what the node does. Shape tests
pass happily while a node returns frame 0 of a 24-frame sequence, or writes into
its caller's tensor - both of which this family actually did. What is pinned
here is BEHAVIOUR, with the specific regressions named.
"""
from __future__ import annotations

import json

import numpy as np
import pytest
import torch

from nukemax.nodes.hdr.nodes import (
    HDRExposureBlend,
    HDRExpandDynamicRange,
    HDRFloat32ColorCorrect,
    HDRHighlightSynthesis,
    HDRHistogram,
    HDRImageToFloat32,
    HDRShadowHighlightRecovery,
    HDRToneMap,
    HDR360Generate,
)
from nukemax.utils.hdr_linear import rec709_luminance_torch, tensor_srgb_to_linear


@pytest.fixture
def sdr_img():
    torch.manual_seed(3)
    return torch.rand(1, 16, 16, 3) * 0.8 + 0.1


@pytest.fixture
def hdr_img():
    torch.manual_seed(4)
    return torch.rand(1, 16, 16, 3) * 4.0


@pytest.fixture
def sequence():
    """Four frames of DIFFERENT brightness - a batch drop is invisible in a
    sequence whose frames are all alike."""
    torch.manual_seed(5)
    base = torch.rand(1, 12, 12, 3) * 0.5 + 0.2
    return torch.cat([base * s for s in (1.0, 1.4, 1.8, 0.6)], dim=0)


# ── HDRImageToFloat32 ───────────────────────────────────────────────────────

class TestHDRImageToFloat32:
    def test_identity_linear(self, sdr_img):
        out, = HDRImageToFloat32().execute(sdr_img, normalize=False, source_gamma=1.0)
        assert torch.allclose(out, sdr_img.float())

    def test_normalize_does_not_write_into_the_callers_tensor(self):
        # REGRESSION: `.float()` is a no-op on a float32 tensor, so the ported
        # `img[i] = img[i] / frame_max` rewrote the UPSTREAM node's cached
        # output. Every other node reading that same wire would silently get
        # normalised pixels it never asked for.
        src = torch.full((1, 4, 4, 3), 4.0)
        before = src.clone()
        HDRImageToFloat32().execute(src, normalize=True, source_gamma=1.0)
        assert torch.equal(src, before), "node mutated its input IMAGE in place"

    def test_normalize_is_per_frame_not_per_batch(self, ):
        # INVARIANT: normalising a sequence against the batch peak makes every
        # frame but the brightest darker than it should be - it reads as a
        # flicker. Each frame gets its own scale.
        img = torch.stack([
            torch.full((4, 4, 3), 4.0),
            torch.full((4, 4, 3), 2.0),
        ])
        out, = HDRImageToFloat32().execute(img, normalize=True, source_gamma=1.0)
        assert out[0].max().item() == pytest.approx(1.0)
        assert out[1].max().item() == pytest.approx(1.0)

    def test_normalize_leaves_an_already_in_range_frame_alone(self):
        # INVARIANT: normalize means "pull super-whites down", not "stretch to
        # white". A 0.5 plate must not be pushed to 1.0.
        img = torch.full((1, 4, 4, 3), 0.5)
        out, = HDRImageToFloat32().execute(img, normalize=True, source_gamma=1.0)
        assert out.max().item() == pytest.approx(0.5)

    def test_source_gamma_decodes_toward_linear(self):
        # INVARIANT: a 0.5 code value is ~0.22 in linear, not 0.5. Getting the
        # direction wrong doubles the error in every downstream light maths.
        img = torch.full((1, 4, 4, 3), 0.5)
        out, = HDRImageToFloat32().execute(img, normalize=False, source_gamma=2.2)
        assert out.max().item() < 0.5


# ── HDRFloat32ColorCorrect ──────────────────────────────────────────────────

class TestHDRFloat32ColorCorrect:
    def test_defaults_passthrough(self, hdr_img):
        out, = HDRFloat32ColorCorrect().execute(
            hdr_img, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 1, "Rec.709 / sRGB", False
        )
        assert torch.allclose(out, hdr_img.float())

    def test_exposure_is_stops_not_a_multiplier(self, hdr_img):
        # INVARIANT: +1 stop is exactly 2x. A compositor matching a plate works
        # in stops; "roughly brighter" is not usable.
        out, = HDRFloat32ColorCorrect().execute(
            hdr_img, 1.0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 1, "Rec.709 / sRGB", False
        )
        assert torch.allclose(out, hdr_img.float() * 2.0, atol=1e-5)

    def test_super_whites_survive_when_clamp_is_off(self, hdr_img):
        # INVARIANT: THE reason this node exists. Clamping here would throw away
        # the highlight information the rest of the family works on.
        assert hdr_img.max() > 1.0
        out, = HDRFloat32ColorCorrect().execute(
            hdr_img, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 1, "Rec.709 / sRGB", False
        )
        assert out.max() > 1.0

    def test_clamp_output_bounds_the_result(self, hdr_img):
        out, = HDRFloat32ColorCorrect().execute(
            hdr_img, 0, 1, 0, 1, 1, 0, 0, 0, 1, 1, 1, "Rec.709 / sRGB", True
        )
        assert out.max() <= 1.0 and out.min() >= 0.0

    def test_zero_saturation_keeps_luminance(self, hdr_img):
        # INVARIANT: desaturating must not change brightness. If it does, the
        # luma weights are wrong for the declared colour space.
        out, = HDRFloat32ColorCorrect().execute(
            hdr_img, 0, 1, 0, 0.0, 1, 0, 0, 0, 1, 1, 1, "Rec.709 / sRGB", False
        )
        assert torch.allclose(out[..., 0], out[..., 1], atol=1e-5)
        assert torch.allclose(
            rec709_luminance_torch(out), rec709_luminance_torch(hdr_img.float()),
            atol=1e-4,
        )


# ── HDRExpandDynamicRange ───────────────────────────────────────────────────

class TestHDRExpand:
    def test_clipped_white_reaches_the_requested_peak(self):
        # INVARIANT: the node's whole job. A blown region at code 1.0 must come
        # back at 2^(stops-8) so that a 14-stop target really is 14 stops.
        white = torch.ones(1, 8, 8, 3)
        out, = HDRExpandDynamicRange().execute(white, 2.2, 1.0, 0.0, 14.0, 1.5)
        assert out.max().item() == pytest.approx(2.0 ** (14.0 - 8.0), rel=1e-3)

    def test_target_stops_moves_the_peak(self):
        white = torch.ones(1, 8, 8, 3)
        low, = HDRExpandDynamicRange().execute(white, 2.2, 1.0, 0.0, 10.0, 1.5)
        high, = HDRExpandDynamicRange().execute(white, 2.2, 1.0, 0.0, 16.0, 1.5)
        assert high.max() > low.max() > 1.0

    def test_below_the_knee_it_is_pure_linearisation(self, sdr_img):
        # THIS REPLACES a test that asserted out.max() > in.max() on random
        # noise. It cannot be true: de-gamma DARKENS code values below 1.0, and
        # nothing in a 0.1-0.9 noise field is near the highlight knee. The real
        # invariant is that mid-tones are passed through the transfer function
        # untouched - recovery must not grade the picture.
        assert sdr_img.max() < 0.95
        out, = HDRExpandDynamicRange().execute(sdr_img, 2.2, 1.0, 0.0, 14.0, 1.5)
        assert torch.allclose(out, tensor_srgb_to_linear(sdr_img, 2.2), atol=1e-5)

    def test_recovery_amount_zero_is_a_no_op_on_highlights(self):
        white = torch.ones(1, 8, 8, 3)
        out, = HDRExpandDynamicRange().execute(white, 2.2, 0.0, 0.0, 14.0, 1.5)
        assert out.max().item() == pytest.approx(1.0, rel=1e-4)

    def test_expansion_preserves_hue(self):
        # INVARIANT: expansion scales LUMA and applies the ratio to all three
        # channels. A per-channel expansion would shift a blown warm highlight
        # toward the channel that clipped hardest.
        img = torch.ones(1, 4, 4, 3)
        img[..., 2] = 0.8                      # a warm clipped highlight
        out, = HDRExpandDynamicRange().execute(img, 1.0, 1.0, 0.0, 14.0, 1.5)
        ratio_in = (img[..., 0] / img[..., 2])
        ratio_out = (out[..., 0] / out[..., 2])
        assert torch.allclose(ratio_in, ratio_out, atol=1e-4)


# ── HDRToneMap ──────────────────────────────────────────────────────────────

class TestHDRToneMap:
    @pytest.mark.parametrize("operator", HDRToneMap.OPERATORS)
    def test_every_operator_lands_in_display_range(self, hdr_img, operator):
        # INVARIANT: a tone map that returns >1.0 has not tone mapped. Each
        # operator is checked, because only one was before.
        out, = HDRToneMap().execute(
            hdr_img, "None (Custom)", operator, 0.0, 2.2, 1.0, 1.0, 1.0, 0.5, 0.0
        )
        assert torch.isfinite(out).all(), f"{operator} produced NaN/Inf"
        assert out.min() >= 0.0 and out.max() <= 1.0

    def test_reinhard_is_monotonic(self):
        # INVARIANT: brighter in must not come out darker, or highlight detail
        # inverts against the midtones.
        ramp = torch.linspace(0, 8, 64).view(1, 1, 64, 1).repeat(1, 1, 1, 3)
        out, = HDRToneMap().execute(
            ramp, "None (Custom)", "reinhard", 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0
        )
        row = out[0, 0, :, 0]
        assert torch.all(row[1:] >= row[:-1] - 1e-6)

    def test_a_preset_overrides_the_loose_widgets(self, hdr_img):
        # INVARIANT: presets are the point of the dropdown. If the widgets won,
        # picking a preset would do nothing and look like a broken control.
        preset, = HDRToneMap().execute(
            hdr_img, "HDR Display", "reinhard", 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0
        )
        manual, = HDRToneMap().execute(
            hdr_img, "None (Custom)", "reinhard", 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0
        )
        assert not torch.allclose(preset, manual)


# ── HDRHistogram ────────────────────────────────────────────────────────────

class TestHDRHistogram:
    @staticmethod
    def _run(image, mode="luminance", show_clipping=True, stops=14):
        out = HDRHistogram().execute(image, mode, show_clipping, stops)
        hist, stats = out["result"]
        scope = json.loads(out["ui"]["nukemax_hdr_scope"][0])
        return hist, stats, scope

    def test_returns_stats_and_a_real_plot(self, hdr_img):
        hist, stats, _scope = self._run(hdr_img)
        assert hist.ndim == 4 and hist.shape[-1] == 3
        assert hist.max() > 0.0, "histogram rendered as an empty black frame"
        assert "Dynamic range" in stats

    def test_a_blown_later_frame_shows_up_in_the_stats(self, sequence):
        # REGRESSION: the ported scope measured frame 0 only, so a sequence
        # whose LAST frame clips read as perfectly in range - the exact case a
        # scope exists to catch.
        blown = sequence.clone()
        blown[-1] = 9.0
        _hist, _stats, scope = self._run(blown)
        assert scope["max"] == pytest.approx(9.0), "whole-batch max not reported"

    def test_stats_say_how_many_frames_were_measured(self, sequence):
        _hist, stats, scope = self._run(sequence)
        assert "4 frames" in stats
        assert scope["frames"] == 4

    def test_the_ui_payload_carries_what_the_on_node_scope_draws(self, hdr_img):
        # INVARIANT: socket values NEVER reach the browser - only `ui` does. If
        # this payload loses a field the on-node scope goes blank while the
        # node still reports success.
        _hist, _stats, scope = self._run(hdr_img)
        for key in ("bins", "range", "min", "max", "mean", "stops",
                    "clip_low", "clip_high", "frames", "mode"):
            assert key in scope, f"scope payload is missing {key!r}"
        assert len(scope["bins"]) == 128
        assert sum(scope["bins"]) > 0
        assert scope["range"][1] >= 1.0

    def test_the_ui_payload_is_json_serialisable_as_sent(self, hdr_img):
        # INVARIANT: ComfyUI sends `ui` over the websocket. A numpy scalar in
        # there raises during send, AFTER the node has "succeeded" - which
        # surfaces as a node that runs but never updates.
        out = HDRHistogram().execute(hdr_img, "luminance", True, 14)
        json.dumps(out["ui"])


# ── HDRExposureBlend ────────────────────────────────────────────────────────

class TestHDRExposureBlend:
    def test_mertens(self, sdr_img):
        dark = sdr_img * 0.3
        bright = sdr_img * 1.8
        out, mask, info = HDRExposureBlend().execute(dark, bright, "Mertens Fusion")
        assert out.shape == sdr_img.shape
        assert mask.shape == sdr_img.shape
        assert "Mertens" in info

    @pytest.mark.parametrize("method", HDRExposureBlend.METHODS)
    def test_every_method_keeps_the_whole_sequence(self, sequence, method):
        # REGRESSION: `if low_np.ndim == 4: low_np = low_np[0]` fired on every
        # call, because require_image_bhwc GUARANTEES 4-D. A 4-frame bracket
        # came back as one frame, silently.
        if method == "Laplacian Pyramid":
            pytest.importorskip("scipy")
        out, mask, info = HDRExposureBlend().execute(
            sequence * 0.4, sequence * 1.6, method
        )
        assert out.shape[0] == sequence.shape[0], f"{method} dropped frames"
        assert mask.shape[0] == sequence.shape[0]
        assert torch.isfinite(out).all()
        assert out.min() >= 0.0
        assert "4 frames" in info

    def test_a_still_broadcasts_against_a_sequence(self, sequence):
        # INVARIANT: holding one clean bracket against a moving plate is a real
        # setup; it must not raise or truncate to one frame.
        still = sequence[:1] * 0.4
        out, _mask, _info = HDRExposureBlend().execute(
            still, sequence * 1.6, "Luminance Weighted"
        )
        assert out.shape[0] == sequence.shape[0]

    def test_frames_differ_from_each_other(self, sequence):
        # INVARIANT: the counter-test to "keeps the whole sequence" - stacking
        # the SAME frame four times would also pass a shape check.
        out, _m, _i = HDRExposureBlend().execute(
            sequence * 0.4, sequence * 1.6, "Luminance Weighted"
        )
        assert not torch.allclose(out[0], out[1])


# ── HDRShadowHighlightRecovery ──────────────────────────────────────────────

class TestHDRShadowHighlight:
    def test_keeps_the_whole_sequence(self, sequence):
        # REGRESSION: same frame-0 drop as the blend node.
        out, = HDRShadowHighlightRecovery().execute(sequence, 0.5, 0.5)
        assert out.shape == sequence.shape
        assert not torch.allclose(out[0], out[3])

    def test_shadows_actually_lift(self):
        # INVARIANT: the control has to move the picture in the named direction.
        dark = torch.full((1, 8, 8, 3), 0.02)
        none, = HDRShadowHighlightRecovery().execute(dark, 0.0, 0.0)
        lifted, = HDRShadowHighlightRecovery().execute(dark, 2.0, 0.0)
        assert lifted.mean() > none.mean()

    def test_highlights_come_down(self):
        hot = torch.full((1, 8, 8, 3), 4.0)
        none, = HDRShadowHighlightRecovery().execute(hot, 0.0, 0.0)
        tamed, = HDRShadowHighlightRecovery().execute(hot, 0.0, 2.0)
        assert tamed.mean() < none.mean()

    def test_local_contrast_does_not_blur_across_frames(self, sequence):
        # INVARIANT: the local-contrast blur is 2-D per frame. A 3-D blur would
        # bleed one frame's luminance into the next and read as ghosting.
        pytest.importorskip("scipy")
        full, = HDRShadowHighlightRecovery().execute(
            sequence, 0.5, 0.5, 0.25, 0.75, 0.5, 0.5
        )
        alone, = HDRShadowHighlightRecovery().execute(
            sequence[1:2], 0.5, 0.5, 0.25, 0.75, 0.5, 0.5
        )
        assert torch.allclose(full[1], alone[0], atol=1e-5)


# ── HDRHighlightSynthesis ───────────────────────────────────────────────────

class TestHDRHighlightSynthesis:
    def test_add_mode(self, sdr_img):
        hot = sdr_img.clone()
        hot[..., :] = 1.0
        out, = HDRHighlightSynthesis().execute(hot, 0.9, 1.5, 0.1, 1.0, "Add", 7)
        assert out.shape == hot.shape

    def test_pixels_below_threshold_are_untouched(self):
        # INVARIANT: highlight synthesis invents detail. If it leaks below the
        # threshold it is inventing detail in the part of the frame the camera
        # actually recorded.
        img = torch.full((1, 8, 8, 3), 0.3)
        img[:, :2, :2, :] = 1.0                      # one blown corner
        out, = HDRHighlightSynthesis().execute(img, 0.9, 2.0, 0.5, 1.0, "Add", 7)
        assert torch.allclose(out[:, 4:, 4:, :], img[:, 4:, 4:, :], atol=1e-6)
        assert out[:, :2, :2, :].max() > 1.0

    def test_seed_is_deterministic(self):
        img = torch.full((1, 8, 8, 3), 1.0)
        a, = HDRHighlightSynthesis().execute(img, 0.9, 1.5, 0.4, 1.0, "Add", 11)
        b, = HDRHighlightSynthesis().execute(img, 0.9, 1.5, 0.4, 1.0, "Add", 11)
        c, = HDRHighlightSynthesis().execute(img, 0.9, 1.5, 0.4, 1.0, "Add", 12)
        assert torch.equal(a, b)
        assert not torch.equal(a, c)

    def test_every_frame_gets_its_own_grain(self):
        # INVARIANT: identical grain on every frame is a frozen texture stuck to
        # the lens, which is immediately visible in motion.
        img = torch.full((3, 8, 8, 3), 1.0)
        out, = HDRHighlightSynthesis().execute(img, 0.9, 1.5, 0.4, 1.0, "Add", 7)
        assert not torch.equal(out[0], out[1])


# ── HDR360Generate ──────────────────────────────────────────────────────────

class TestHDR360:
    def test_equirect_small(self, sdr_img):
        pano, uv = HDR360Generate().execute(
            sdr_img, "Equirectangular", 128, 64, 360.0, 180.0, 0.0, "Bilinear", "Mirror", 0.0
        )
        assert pano.shape == (1, 64, 128, 3)
        assert uv.shape == (1, 64, 128, 3)

    def test_keeps_the_whole_sequence(self, sequence):
        # REGRESSION: a latlong is often built from a moving plate; the ported
        # code projected frame 0 and dropped the rest.
        pano, uv = HDR360Generate().execute(
            sequence, "Equirectangular", 64, 32, 360.0, 180.0, 0.0, "Bilinear", "Mirror", 0.0
        )
        assert pano.shape == (4, 32, 64, 3)
        assert uv.shape[0] == 4
        assert not torch.allclose(pano[0], pano[1])

    @pytest.mark.parametrize("projection", HDR360Generate.PROJECTIONS)
    def test_every_projection_produces_a_finite_panorama(self, sdr_img, projection):
        pano, _uv = HDR360Generate().execute(
            sdr_img, projection, 64, 32, 360.0, 180.0, 0.0, "Bilinear", "Mirror", 0.0
        )
        assert pano.shape == (1, 32, 64, 3)
        assert torch.isfinite(pano).all(), f"{projection} produced NaN/Inf"

    def test_exposure_adjust_is_stops(self, sdr_img):
        base, _ = HDR360Generate().execute(
            sdr_img, "Equirectangular", 64, 32, 360.0, 180.0, 0.0, "Nearest", "Mirror", 0.0
        )
        up, _ = HDR360Generate().execute(
            sdr_img, "Equirectangular", 64, 32, 360.0, 180.0, 0.0, "Nearest", "Mirror", 1.0
        )
        assert torch.allclose(up, base * 2.0, atol=1e-5)

    def test_black_fill_marks_the_uncovered_region(self):
        # INVARIANT: a 60-degree source cannot cover a 360 sphere. "Black" says
        # so in the uv map's third channel; without it the user cannot tell
        # invented pixels from photographed ones.
        img = torch.rand(1, 16, 16, 3)
        _pano, uv = HDR360Generate().execute(
            img, "Equirectangular", 64, 32, 60.0, 40.0, 0.0, "Nearest", "Black", 0.0
        )
        coverage = uv[..., 2]
        assert coverage.min() == 0.0 and coverage.max() == 1.0
