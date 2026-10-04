"""The Nodes 2.0 canvas adapter draws on demand, not every frame.

web/widgets/_vue_canvas.js mounts a <canvas> for the roto editor and the
waveform preview when Nodes 2.0 is on. It used to repaint 60 times a second for
every such node, forever, with a forced layout read each time: a steady CPU
cost for a picture that had not changed. These tests run the real module in
node with a fake DOM and count the draws.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

PACK = Path(__file__).resolve().parents[1]
ADAPTER = PACK / "web" / "widgets" / "_vue_canvas.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

PRELUDE = r"""
globalThis.window = globalThis;
let frameQ = [], now = 0;
globalThis.requestAnimationFrame = (f) => { frameQ.push(f); return frameQ.length; };
globalThis.cancelAnimationFrame = () => {};
const frames = (n) => { for (let i = 0; i < n; i++) { now += 16; const q = frameQ; frameQ = [];
  q.forEach((f) => f(now)); } };
let timers = [];
globalThis.setInterval = (f, ms) => { timers.push({ f, ms, live: true }); return timers.length; };
globalThis.clearInterval = (id) => { if (timers[id - 1]) timers[id - 1].live = false; };
const tickTimers = () => timers.forEach((t) => t.live && t.f());
globalThis.document = { hidden: false, createElement: (tag) => {
  const el = { tag, style: {}, children: [], clientWidth: 300, width: 0, height: 0,
    appendChild(c) { this.children.push(c); }, addEventListener() {}, remove() {}, focus() {},
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 150, height: 48 }),
    getContext: () => ({ setTransform() {}, clearRect() {} }) };
  return el; } };
let io = null;
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
globalThis.IntersectionObserver = class { constructor(cb) { this.cb = cb; io = this; }
  observe() {} disconnect() { this.dead = true; } };
globalThis.app = { ui: { settings: { getSettingValue: (id) => id === "Comfy.VueNodes.Enabled" } } };
let draws = 0, lastArgs = null;
const node = { graph: {}, widgets: [], dirtyCalls: 0,
  addCustomWidget(w) { this.widgets.push(w); },
  addDOMWidget(name, type, el, opts) { return { name, el, opts }; },
  setDirtyCanvas() { this.dirtyCalls++; } };
const widget = { name: "roto", draw(ctx, n, w, y, h) { draws++; lastArgs = [w, h]; } };
// the driver lives in another module: hand it the harness
globalThis.H = { node, widget, frames, tickTimers, get draws() { return draws; },
  get lastArgs() { return lastArgs; }, get io() { return io; }, get timers() { return timers; } };
"""

BODY = r"""
import { installCanvasWidget } from "./adapter.mjs";
const { node, widget, frames, tickTimers } = H;
installCanvasWidget(node, widget, 96);
frames(3);
const first = H.draws;
frames(120);                                   // two idle seconds of frames
const idle = H.draws - first;
node.setDirtyCanvas(true, true);               // the widget says it changed
frames(2);
const afterDirty = H.draws - first - idle;
const passedThrough = node.dirtyCalls;
H.io.cb([{ isIntersecting: false }]);            // scrolled off screen
const offBefore = H.draws; tickTimers(); frames(5);
const offscreen = H.draws - offBefore;
H.io.cb([{ isIntersecting: true }]); frames(1);
const back = H.draws - offBefore - offscreen;
const hbBefore = H.draws; tickTimers(); frames(1);
const heartbeat = H.draws - hbBefore;
node.graph = null; node.onRemoved();
const remBefore = H.draws; tickTimers(); node.setDirtyCanvas(); frames(5);
process.stdout.write(JSON.stringify({ first, idle, afterDirty, passedThrough, offscreen, back,
  heartbeat, afterRemove: H.draws - remBefore, lastArgs: H.lastArgs, ioDead: !!H.io.dead,
  timersLive: H.timers.filter((t) => t.live).length }));
"""


def _run() -> dict:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "adapter.mjs").write_text(PRELUDE + ADAPTER.read_text(encoding="utf-8"), encoding="utf-8")
        (tmp / "run.mjs").write_text(BODY, encoding="utf-8")
        r = subprocess.run([NODE, str(tmp / "run.mjs")], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr[:800]
        return json.loads(r.stdout)


def test_an_idle_node_is_not_redrawn_every_frame():
    out = _run()
    assert out["first"] == 1, "the widget must be drawn once when it appears"
    assert out["idle"] == 0, f"{out['idle']} redraws in 120 idle frames (was 120 before the fix)"


def test_set_dirty_canvas_still_reaches_litegraph_and_triggers_one_draw():
    out = _run()
    assert out["afterDirty"] == 1
    assert out["passedThrough"] == 1, "the node's own setDirtyCanvas must still run"


def test_offscreen_nodes_do_not_draw_and_resume_when_visible():
    out = _run()
    assert out["offscreen"] == 0
    assert out["back"] == 1


def test_the_safety_heartbeat_redraws_a_visible_node():
    assert _run()["heartbeat"] == 1


def test_removal_stops_everything():
    out = _run()
    assert out["afterRemove"] == 0
    assert out["ioDead"] is True
    assert out["timersLive"] == 0


def test_draw_uses_unzoomed_node_pixels():
    """The screen rect is zoomed (150 px on screen for a 300 px canvas at 0.5).
    Drawing with that width and the unzoomed height stretched the picture."""
    assert _run()["lastArgs"] == [300, 96]
