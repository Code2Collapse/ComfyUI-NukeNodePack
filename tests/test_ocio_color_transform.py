"""OCIO Color Transform runs with its own defaults on OCIO 2 configs (L7.87, 2026-10-12).

The default dst "Output - sRGB" is an ACES 1.x output space; OCIO 2's built-in ACES 2.0 configs have no such
colorspace (display + view instead), so the node failed out of the box on every built-in config.
"""
from __future__ import annotations

import json

import pytest
import torch

OCIO = pytest.importorskip("PyOpenColorIO")

from nukemax.nodes.ocio import OCIOColorTransform, _list_configs  # noqa: E402


def _builtin():
    names = [c for c in _list_configs() if not c.startswith("(")]
    if not names:
        pytest.skip("no OCIO config discoverable")
    return names[0]


def test_defaults_run_and_say_what_the_aces1_name_became():
    spec = OCIOColorTransform.INPUT_TYPES()["required"]
    src, dst = spec["src_colorspace"][1]["default"], spec["dst_colorspace"][1]["default"]
    img = torch.full((2, 4, 4, 3), 0.18)
    out, info = OCIOColorTransform().execute(img, _builtin(), src, dst)
    meta = json.loads(info)
    assert out.shape == img.shape and torch.isfinite(out).all()
    assert 0.25 < float(out.mean()) < 0.45                     # 18% grey through an SDR output transform
    if dst.startswith("Output - ") and meta["dst_resolved"] != dst:
        assert "ACES 1.x" in meta["note"]


def test_an_unknown_name_still_names_the_choices():
    with pytest.raises(ValueError, match="Available"):
        OCIOColorTransform().execute(torch.zeros(1, 2, 2, 3), _builtin(), "ACES - ACES2065-1", "No Such Space")
