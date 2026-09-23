"""Decoding a generated image as log, and catching it when that is a lie.

The failure this guards against is the quietest one in the whole HDR path: run
an inverse log curve over a model that was trained on ordinary sRGB and you get
values above 1.0, a valid EXR, and no error anywhere. It simply is not HDR -
the highlights were clipped during training and are still clipped - and the
only way to find out is to grade it and discover there is nothing there.

The check is arithmetic, not statistics. Every log curve maps linear zero to a
POSITIVE code value, so a pixel below that decodes to negative light, which
does not exist. These tests pin that a real log image has none of those and a
display-referred image has ~9% of them.

CPU-only, torch only, no weights.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import torch

PACK = Path(__file__).resolve().parents[1]
if str(PACK) not in sys.path:
    sys.path.insert(0, str(PACK))

ghdr = pytest.importorskip(
    "nukemax.nodes.hdr.generated_hdr",
    reason="needs the ocio_color transfer curves")

GENERATED_CURVES = ghdr.GENERATED_CURVES
GeneratedHDRDecode = ghdr.GeneratedHDRDecode


def as_image(flat: torch.Tensor, h=32, w=32) -> torch.Tensor:
    return flat.reshape(1, h, w, 1).repeat(1, 1, 1, 3).float()


def log_encoded(curve: str, h=32, w=32, peak=40.0) -> torch.Tensor:
    """A genuinely log-encoded image: real linear light, put through the
    curve's own forward transform."""
    from nukemax.nodes.ocio_color._curves import resolve_curve
    fwd, _, _ = resolve_curve(curve)
    g = torch.Generator().manual_seed(0)
    linear = torch.rand(h * w, generator=g) * peak
    return as_image(torch.as_tensor(np.asarray(fwd(linear))), h, w)


def display_referred(h=32, w=32) -> torch.Tensor:
    """An ordinary display image - what an sRGB-trained model emits."""
    g = torch.Generator().manual_seed(1)
    return as_image(torch.rand(h * w, generator=g), h, w)


# ── the curve constants ─────────────────────────────────────────────────────

def test_every_offered_curve_resolves():
    for name in GENERATED_CURVES:
        assert ghdr.encoded_black(name) > 0.0
        assert ghdr.ceiling(name) > 1.0


@pytest.mark.parametrize("curve,black,cap", [
    ("ARRI LogC3", 0.0928, 55.08),
    ("ARRI LogC4", 0.0929, 469.80),
    ("ACEScct", 0.0729, 222.86),
])
def test_the_published_constants_are_what_the_curves_give(curve, black, cap):
    """Pinned against the specs: if a curve is ever edited, this says so
    rather than letting every decoded EXR quietly change scale."""
    assert ghdr.encoded_black(curve) == pytest.approx(black, abs=5e-4)
    assert ghdr.ceiling(curve) == pytest.approx(cap, rel=0.01)


def test_linear_zero_always_lands_above_zero_in_code():
    """The property the whole check rests on - the encoding reserves footroom
    below linear zero for negative sensor noise."""
    for name in GENERATED_CURVES:
        assert ghdr.encoded_black(name) > 0.0, name


def test_mid_grey_lands_where_a_log_curve_puts_it():
    assert ghdr.mid_grey("ARRI LogC3") == pytest.approx(0.391, abs=0.01)
    assert ghdr.mid_grey("ACEScct") == pytest.approx(0.414, abs=0.01)


# ── the check ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("curve", ["ARRI LogC3", "ARRI LogC4", "ACEScct"])
def test_a_genuinely_encoded_image_has_no_impossible_pixels(curve):
    assert ghdr.impossible_fraction(log_encoded(curve), curve) == \
        pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("curve", ["ARRI LogC3", "ARRI LogC4", "ACEScct"])
def test_a_display_referred_image_is_caught(curve):
    """THE case. About 9% of an ordinary image sits below the curve's black
    point, and every one of those decodes to negative light."""
    frac = ghdr.impossible_fraction(display_referred(), curve)
    assert frac > 0.05, f"only {frac:.3f} flagged - the check is too loose"


def test_the_two_cases_are_far_apart():
    """The threshold has to separate them without sitting on top of either."""
    real = ghdr.impossible_fraction(log_encoded("ARRI LogC3"), "ARRI LogC3")
    fake = ghdr.impossible_fraction(display_referred(), "ARRI LogC3")
    assert real < ghdr.IMPOSSIBLE_FRACTION_LIMIT < fake
    assert fake > real * 50


def test_the_impossible_pixels_really_do_decode_negative():
    """Not a proxy for the problem - the problem itself."""
    img = display_referred()
    lin = ghdr.decode(img, "ARRI LogC3", clamp_negative=False)
    assert float(lin.min()) < 0.0
    assert float((lin < 0).float().mean()) == pytest.approx(
        ghdr.impossible_fraction(img, "ARRI LogC3"), abs=1e-6)


# ── decoding ────────────────────────────────────────────────────────────────

def test_decoding_recovers_the_linear_values_it_came_from():
    """A round trip: real linear light, encoded, decoded, back where it was."""
    from nukemax.nodes.ocio_color._curves import resolve_curve
    fwd, _, _ = resolve_curve("ARRI LogC3")
    linear = torch.linspace(0.0, 50.0, 1024)
    enc = as_image(torch.as_tensor(np.asarray(fwd(linear))), 32, 32)
    back = ghdr.decode(enc, "ARRI LogC3").reshape(-1, 3)[:, 0]
    assert torch.allclose(back, linear, atol=0.02, rtol=0.01)


def test_decoding_produces_values_above_one():
    """The point of the exercise. A decode that stays inside [0,1] has not
    recovered any range."""
    lin = ghdr.decode(log_encoded("ARRI LogC3", peak=40.0), "ARRI LogC3")
    assert float(lin.max()) > 10.0


def test_negatives_are_clamped_by_default():
    lin = ghdr.decode(display_referred(), "ARRI LogC3", clamp_negative=True)
    assert float(lin.min()) >= 0.0


def test_the_preview_is_viewable():
    """Scene-linear cannot be shown directly, and a plain clamp would hide
    exactly the highlights this node is about."""
    lin = ghdr.decode(log_encoded("ARRI LogC3"), "ARRI LogC3")
    prev = ghdr.reinhard(lin)
    assert float(prev.max()) <= 1.0 and float(prev.min()) >= 0.0
    # and it is monotonic - brighter linear is still brighter on screen
    a = ghdr.reinhard(torch.tensor([1.0, 10.0, 100.0]))
    assert float(a[0]) < float(a[1]) < float(a[2])


# ── the node ────────────────────────────────────────────────────────────────

def test_a_real_log_image_decodes_and_reports_clean():
    out = GeneratedHDRDecode().execute(
        image=log_encoded("ARRI LogC3", peak=40.0), log_curve="ARRI LogC3")
    hdr, preview, is_encoded, peak, report = out
    assert is_encoded is True
    assert peak > 10.0
    assert "checks out" in report
    assert preview.shape == hdr.shape


def test_a_display_referred_image_is_refused_with_the_reason():
    """Refused, not silently decoded: the output would be a valid EXR that is
    not HDR, and nothing downstream would ever say so."""
    with pytest.raises(ValueError) as e:
        GeneratedHDRDecode().execute(image=display_referred(),
                                     log_curve="ARRI LogC3")
    msg = str(e.value)
    assert "not ARRI LogC3-encoded" in msg
    assert "negative light" in msg
    assert "assume_encoded" in msg, "the way forward is not offered"


def test_assume_encoded_proceeds_but_says_what_it_did():
    hdr, _, is_encoded, _, report = GeneratedHDRDecode().execute(
        image=display_referred(), log_curve="ARRI LogC3",
        assume_encoded=True)
    assert is_encoded is False
    assert "expansion, not a reconstruction" in report
    assert "do not ship it as HDR" in report
    assert float(hdr.min()) >= 0.0


def test_the_report_explains_what_a_bad_decode_actually_costs():
    _, _, _, _, report = GeneratedHDRDecode().execute(
        image=display_referred(), log_curve="ARRI LogC3", assume_encoded=True)
    assert "clipped during training" in report
    assert "LoRA" in report, "the actual fix is not named"


def test_the_report_states_the_ceiling_and_mid_grey():
    _, _, _, _, report = GeneratedHDRDecode().execute(
        image=log_encoded("ACEScct"), log_curve="ACEScct")
    assert "222" in report
    assert "mid grey" in report


def test_a_log_image_with_no_highlights_is_pointed_out():
    """The encoding is right but there is no range in the picture - worth
    saying, or the user concludes the node did nothing."""
    from nukemax.nodes.ocio_color._curves import resolve_curve
    fwd, _, _ = resolve_curve("ARRI LogC3")
    dim = torch.rand(1024, generator=torch.Generator().manual_seed(3)) * 0.2
    img = as_image(torch.as_tensor(np.asarray(fwd(dim))), 32, 32)
    _, _, ok, _, report = GeneratedHDRDecode().execute(
        image=img, log_curve="ARRI LogC3")
    assert ok is True
    assert "no highlight range" in report


# ── the pack contract ───────────────────────────────────────────────────────

def test_the_node_follows_the_pack_conventions():
    cls = GeneratedHDRDecode
    assert cls.CATEGORY.startswith("NukeMax/")
    assert not isinstance(cls.RETURN_TYPES, str)
    assert len(cls.RETURN_TYPES) == len(cls.RETURN_NAMES)
    assert len(cls.OUTPUT_TOOLTIPS) == len(cls.RETURN_TYPES)
    assert hasattr(cls, cls.FUNCTION)
    assert cls.DESCRIPTION


def test_it_is_registered_in_the_hdr_package():
    from nukemax.nodes.hdr import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

    assert "NukeMax_GeneratedHDRDecode" in NODE_CLASS_MAPPINGS
    assert "NukeMax_GeneratedHDRDecode" in NODE_DISPLAY_NAME_MAPPINGS


def test_the_math_only_hdr_nodes_survive_if_this_one_cannot_import():
    """It reaches into ocio_color for the curves; the nine nodes that do not
    must not be taken down with it."""
    src = (PACK / "nukemax" / "nodes" / "hdr" / "__init__.py").read_text(
        encoding="utf-8")
    assert "try:" in src and "_GENHDR_MAPPINGS" in src
    assert "except Exception" in src


# ── curves the check cannot work on ─────────────────────────────────────────

def test_a_curve_with_no_footroom_is_refused_rather_than_silently_passing():
    """DaVinci Intermediate puts linear zero at exactly 0.0 and ACEScc puts it
    at -0.36, so no code value could ever prove an image is NOT in them. The
    check would pass everything, which is worse than no check at all - the
    node would be asserting something it never tested."""
    for curve in ("DaVinci Intermediate", "ACEScc"):
        with pytest.raises(ValueError, match="no footroom"):
            ghdr.encoded_black(curve)


def test_the_footroom_free_curves_are_not_offered():
    assert "DaVinci Intermediate" not in GENERATED_CURVES
    assert "ACEScc" not in GENERATED_CURVES


def test_the_refusal_points_at_a_curve_that_does_work():
    try:
        ghdr.encoded_black("DaVinci Intermediate")
    except ValueError as e:
        assert "ARRI LogC3" in str(e), "no usable alternative was named"
        assert "Camera Log Convert" in str(e), "the way to still get there"
    else:
        pytest.fail("a footroom-free curve was accepted")


def test_every_offered_curve_has_real_footroom():
    """The list and the guard must not drift apart."""
    for name in GENERATED_CURVES:
        assert ghdr.encoded_black(name) > ghdr.MIN_FOOTROOM, name
