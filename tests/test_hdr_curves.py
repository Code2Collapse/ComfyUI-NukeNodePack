"""The on-node HDR curve plot must be the curve the node actually applies.

web/widgets/hdr/hdr_curves.js mirrors nukemax/nodes/hdr/nodes.py so the plot on
the node is the real response and not a decorative approximation. Two
implementations of the same maths drift; the only way to know they have not is
to RUN both and compare, which is what this does - the JS through node, the
Python through the node classes, on the same ramp.

hdr_curves.js imports nothing from ComfyUI, which is what makes it executable
outside a browser. If that ever changes, the first test here says so.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import torch

PACK = Path(__file__).resolve().parents[1]
CURVES_JS = PACK / "web" / "widgets" / "hdr" / "hdr_curves.js"
NODE = shutil.which("node")

from nukemax.nodes.hdr.nodes import HDRExpandDynamicRange, HDRToneMap  # noqa: E402

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _run_js(body: str, payload: dict) -> list:
    """Execute `body` against hdr_curves.js and return its JSON result."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "hdr_curves.mjs").write_bytes(CURVES_JS.read_bytes())
        driver = tmp / "run.mjs"
        driver.write_text(
            'import * as C from "./hdr_curves.mjs";\n'
            "const p = JSON.parse(process.argv[2]);\n"
            f"{body}\n",
            encoding="utf-8",
        )
        r = subprocess.run([NODE, str(driver), json.dumps(payload)],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout.strip())


def _ramp(values) -> torch.Tensor:
    """A neutral ramp as a [1,1,N,3] IMAGE."""
    t = torch.tensor(values, dtype=torch.float32)
    return t.view(1, 1, -1, 1).repeat(1, 1, 1, 3)


# ── the module contract ─────────────────────────────────────────────────────

def test_curves_module_stays_free_of_comfyui_imports():
    # INVARIANT: one ComfyUI import here and this whole cross-check silently
    # stops running - the plot could then drift from the node forever.
    src = CURVES_JS.read_text(encoding="utf-8")
    assert "scripts/app.js" not in src
    assert "scripts/api.js" not in src
    assert "litegraph" not in src.lower()


def test_the_js_preset_table_matches_the_python_one():
    # INVARIANT: picking "Cinematic Film" must plot Cinematic Film. A preset
    # that exists only on one side plots someone else's curve.
    js = _run_js("console.log(JSON.stringify(C.TONEMAP_PRESETS));", {})
    assert set(js) == set(HDRToneMap.PRESETS)
    for name, cfg in HDRToneMap.PRESETS.items():
        assert js[name] == cfg, f"preset {name} differs between JS and Python"


def test_every_python_operator_is_plottable():
    # INVARIANT: an operator in the dropdown with no JS branch falls through to
    # a clamp and plots a straight line - which reads as "this operator does
    # nothing".
    src = CURVES_JS.read_text(encoding="utf-8")
    for op in HDRToneMap.OPERATORS:
        if op == "exposure_only":
            continue                      # handled by the default branch
        assert f'"{op}"' in src, f"{op} has no branch in hdr_curves.js"


# ── tone map: JS plot vs Python node ────────────────────────────────────────

RAMP = [0.0, 0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 4.0, 8.0]


@pytest.mark.parametrize("operator", HDRToneMap.OPERATORS)
def test_tonemap_plot_matches_the_node(operator):
    params = {
        "preset": "None (Custom)", "operator": operator, "exposure": 0.0,
        "gamma": 2.2, "white_point": 1.0, "contrast": 1.0, "saturation": 1.0,
        "highlight_compression": 0.5, "shadow_lift": 0.0,
    }
    js = _run_js(
        "console.log(JSON.stringify(p.ramp.map((x) => C.toneMapResponse(x, p.cfg))));",
        {"ramp": RAMP, "cfg": params},
    )
    out, = HDRToneMap().execute(
        _ramp(RAMP), params["preset"], operator, params["exposure"],
        params["gamma"], params["white_point"], params["contrast"],
        params["saturation"], params["highlight_compression"],
        params["shadow_lift"],
    )
    py = out[0, 0, :, 0].tolist()
    for x, a, b in zip(RAMP, js, py):
        assert a == pytest.approx(b, abs=2e-4), (
            f"{operator} at input {x}: plot says {a:.6f}, node produced {b:.6f}"
        )


@pytest.mark.parametrize("preset", list(HDRToneMap.PRESETS))
def test_tonemap_plot_matches_the_node_under_a_preset(preset):
    # INVARIANT: the preset path overrides the loose widgets on BOTH sides, or
    # the plot shows the widgets while the node runs the preset.
    params = {
        "preset": preset, "operator": "reinhard", "exposure": 0.0, "gamma": 1.0,
        "white_point": 1.0, "contrast": 1.0, "saturation": 1.0,
        "highlight_compression": 0.0, "shadow_lift": 0.0,
    }
    js = _run_js(
        "console.log(JSON.stringify(p.ramp.map((x) => C.toneMapResponse(x, p.cfg))));",
        {"ramp": RAMP, "cfg": params},
    )
    out, = HDRToneMap().execute(
        _ramp(RAMP), preset, params["operator"], params["exposure"],
        params["gamma"], params["white_point"], params["contrast"],
        params["saturation"], params["highlight_compression"],
        params["shadow_lift"],
    )
    py = out[0, 0, :, 0].tolist()
    for x, a, b in zip(RAMP, js, py):
        assert a == pytest.approx(b, abs=2e-4), (
            f"preset {preset} at input {x}: plot {a:.6f} vs node {b:.6f}"
        )


def test_tonemap_plot_follows_exposure_and_gamma():
    params = {
        "preset": "None (Custom)", "operator": "reinhard", "exposure": 1.5,
        "gamma": 2.4, "white_point": 3.0, "contrast": 1.2, "saturation": 1.0,
        "highlight_compression": 0.7, "shadow_lift": 0.05,
    }
    js = _run_js(
        "console.log(JSON.stringify(p.ramp.map((x) => C.toneMapResponse(x, p.cfg))));",
        {"ramp": RAMP, "cfg": params},
    )
    out, = HDRToneMap().execute(
        _ramp(RAMP), params["preset"], params["operator"], params["exposure"],
        params["gamma"], params["white_point"], params["contrast"],
        params["saturation"], params["highlight_compression"],
        params["shadow_lift"],
    )
    py = out[0, 0, :, 0].tolist()
    for x, a, b in zip(RAMP, js, py):
        assert a == pytest.approx(b, abs=2e-4), f"at {x}: plot {a} vs node {b}"


# ── expansion: JS plot vs Python node ───────────────────────────────────────

CODE_RAMP = [0.0, 0.1, 0.3, 0.5, 0.7, 0.85, 0.9, 0.95, 0.98, 1.0]


@pytest.mark.parametrize(
    "cfg",
    [
        {"source_gamma": 2.2, "highlight_recovery": 1.0, "black_point": 0.0,
         "target_stops": 14.0, "highlight_rolloff": 1.5},
        {"source_gamma": 2.2, "highlight_recovery": 0.5, "black_point": 0.01,
         "target_stops": 10.0, "highlight_rolloff": 2.5},
        {"source_gamma": 1.8, "highlight_recovery": 1.0, "black_point": 0.0,
         "target_stops": 18.0, "highlight_rolloff": 1.0},
    ],
    ids=["defaults", "half-recovery", "gamma1.8-18stops"],
)
def test_expansion_plot_matches_the_node(cfg):
    js = _run_js(
        "console.log(JSON.stringify(p.ramp.map((x) => C.expandResponse(x, p.cfg))));",
        {"ramp": CODE_RAMP, "cfg": cfg},
    )
    out, = HDRExpandDynamicRange().execute(
        _ramp(CODE_RAMP), cfg["source_gamma"], cfg["highlight_recovery"],
        cfg["black_point"], cfg["target_stops"], cfg["highlight_rolloff"],
    )
    py = out[0, 0, :, 0].tolist()
    for x, a, b in zip(CODE_RAMP, js, py):
        assert a == pytest.approx(b, abs=1e-3, rel=1e-3), (
            f"code value {x}: plot says {a:.6f}, node produced {b:.6f}"
        )


def test_the_marked_knee_is_where_the_curve_actually_bends():
    # INVARIANT: the plot draws a knee marker. If it is not where the response
    # leaves the linearisation line it is pointing at the wrong place.
    cfg = {"source_gamma": 1.0, "highlight_recovery": 1.0, "black_point": 0.0,
           "target_stops": 14.0, "highlight_rolloff": 1.5}
    res = _run_js(
        "const k = C.expansionKnee(p.cfg);\n"
        "console.log(JSON.stringify([k, C.expandResponse(k - 0.02, p.cfg),"
        " k - 0.02, C.expandResponse(k + 0.02, p.cfg), k + 0.02]));",
        {"cfg": cfg},
    )
    knee, below_y, below_x, above_y, above_x = res
    assert 0.5 <= knee <= 0.95
    assert below_y == pytest.approx(below_x, abs=1e-6), "expanding below the knee"
    assert above_y > above_x * 1.01, "not expanding above the knee"


def test_sample_curve_spans_the_requested_range():
    xs, ys = _run_js(
        "const c = C.sampleCurve(C.expandResponse, p.cfg, p.xMax, p.n);\n"
        "console.log(JSON.stringify([Array.from(c.xs), Array.from(c.ys)]));",
        {"cfg": {"source_gamma": 1.0, "highlight_recovery": 0.0,
                 "black_point": 0.0, "target_stops": 14.0,
                 "highlight_rolloff": 1.5},
         "xMax": 1.0, "n": 33},
    )
    assert len(xs) == 33 and xs[0] == 0.0 and xs[-1] == pytest.approx(1.0)
    assert ys[-1] >= ys[0]
