// 2D light placement for ReLight 2D — drag the lights on the frame.
//
// WHY THIS IS NOT the hemisphere placer next door. That one drives
// NukeMax_LightRigBuilder: a 3D DIRECTIONAL rig, where a light is an angle on
// a sphere and distance is meaningless. This node is the other kind — lights
// PAINTED ON THE PLATE at a position in the frame, with an inner and outer
// radius. Same word, different geometry, so the same widget cannot serve both:
// dragging a dot on a sphere and dragging a dot on a picture are not the same
// gesture and do not produce the same numbers.
//
// WHAT IT REPLACES. ReLight 2D shipped its lights as six numeric widgets —
// light_position_x, light_position_y, and the same again for lights 2 and 3,
// plus four radii. Every one of them is a place on the picture, and a place on
// a picture is something you point at. Typing 0.7 / 0.3 and re-rendering to
// see where that landed is the slowest possible way to place a key light.
//
// It writes the SAME widgets the node already reads. There is no new backend
// field and no hidden state: drag a dot and the numeric widget moves, type in
// the numeric widget and the dot moves. mountPanel always passes serialize:false
// — the numeric widgets ARE the saved state.
//
// The radius rings are drawn to scale against the frame's SHORT edge, matching
// how the backend builds its falloff mask. A ring drawn against the long edge
// would look right on a square and lie on a 16:9 plate.

import { app } from "../../../../scripts/app.js";
import {
  mountPanel,
  statusLine,
  section,
} from "../../c2c_ui/index.js";

const NODE_NAME = "NukeMax_ReLight2D";
const STATE = "_nmxLight2D";
const PANEL_MIN = 210;
const NODE_MIN_W = 380;

const LIGHTS = [
  {
    n: 1, colour: "#ffd479",
    x: "light_position_x", y: "light_position_y",
    inner: "inner_circle_radius", outer: "outer_circle_radius",
  },
  {
    n: 2, colour: "#79c0ff",
    x: "light2_position_x", y: "light2_position_y",
    inner: "light2_inner_radius", outer: "light2_outer_radius",
  },
  {
    n: 3, colour: "#7ee787",
    x: "light3_position_x", y: "light3_position_y",
    inner: "light3_inner_radius", outer: "light3_outer_radius",
  },
];

function chainOnRemoved(node, cleanup) {
  const orig = node.onRemoved;
  node.onRemoved = function (...a) {
    try { cleanup?.(); } catch (_e) { /* ignore */ }
    return orig?.apply(this, a);
  };
}

const clamp01 = (v) => Math.max(0, Math.min(1, v));

function theme() {
  const cs = getComputedStyle(document.documentElement);
  const g = (v, fb) => cs.getPropertyValue(v).trim() || fb;
  return {
    sunken: g("--cu-sunken", "#0c0d23"),
    edge: g("--cu-edge", "#2a2a57"),
    ink: g("--cu-ink", "#e8e6f7"),
    dim: g("--cu-ink-dim", "#6f6d9b"),
    onAccent: g("--cu-on-accent", "#07081a"),
  };
}

function build(node) {
  const root = document.createElement("div");
  root.style.display = "flex";
  root.style.flexDirection = "column";
  root.style.width = "100%";
  root.style.height = "100%";

  const stage = document.createElement("div");
  stage.style.position = "relative";
  stage.style.width = "100%";
  stage.style.cursor = "crosshair";
  stage.style.touchAction = "none";
  stage.style.overflow = "hidden";
  stage.style.borderRadius = "6px";

  const grid = document.createElement("div");
  grid.style.position = "absolute";
  grid.style.inset = "0";
  grid.style.pointerEvents = "none";
  stage.appendChild(grid);

  for (const [k, v] of [["left", "33.333%"], ["left", "66.667%"],
    ["top", "33.333%"], ["top", "66.667%"]]) {
    const g = document.createElement("div");
    g.style.position = "absolute";
    g.style.background = "#ffffff1f";
    g.style.pointerEvents = "none";
    if (k === "left") {
      g.style.left = v; g.style.top = "0"; g.style.bottom = "0"; g.style.width = "1px";
    } else {
      g.style.top = v; g.style.left = "0"; g.style.right = "0"; g.style.height = "1px";
    }
    stage.appendChild(g);
  }

  const hintLine = statusLine();
  const readoutLine = statusLine();
  readoutLine.el.style.fontVariantNumeric = "tabular-nums";

  const foot = document.createElement("div");
  foot.style.display = "flex";
  foot.style.justifyContent = "space-between";
  foot.style.gap = "8px";
  foot.style.flexWrap = "wrap";
  foot.style.marginTop = "5px";
  foot.append(hintLine.el, readoutLine.el);

  const body = document.createElement("div");
  body.append(stage, foot);
  root.appendChild(section("Light placement", body));

  const st = { stage, hintLine, readoutLine, dots: [], rings: [], dragging: null, grid };
  node[STATE] = st;

  const W = (name) => node.widgets?.find((w) => w.name === name);

  const activeCount = () => {
    const w = W("num_light_sources");
    const n = Number(w?.value);
    return Number.isFinite(n) ? Math.max(1, Math.min(3, n)) : 1;
  };

  const aspect = () => {
    const img = node.imgs?.[0];
    if (img?.naturalWidth && img?.naturalHeight) return img.naturalWidth / img.naturalHeight;
    return 16 / 9;
  };

  for (const L of LIGHTS) {
    const outer = document.createElement("div");
    outer.className = "nmx-l2-ring";
    const inner = document.createElement("div");
    inner.className = "nmx-l2-ring";
    const dot = document.createElement("div");
    dot.style.position = "absolute";
    dot.style.width = "13px";
    dot.style.height = "13px";
    dot.style.borderRadius = "50%";
    dot.style.transform = "translate(-50%,-50%)";
    dot.style.border = "2px solid #10121599";
    dot.style.cursor = "grab";
    dot.style.boxShadow = "0 0 0 1px #0006, 0 1px 4px #0008";
    dot.style.background = L.colour;
    dot.title = `Light ${L.n} — drag to place`;
    const tag = document.createElement("div");
    tag.style.position = "absolute";
    tag.style.transform = "translate(-50%,-50%)";
    tag.style.pointerEvents = "none";
    tag.style.font = "600 9px ui-monospace,monospace";
    tag.textContent = String(L.n);
    stage.append(outer, inner, dot, tag);
    st.rings.push({ L, outer, inner });
    st.dots.push({ L, dot, tag });

    dot.addEventListener("pointerdown", (ev) => {
      if (L.n > activeCount()) return;
      st.dragging = L;
      dot.style.cursor = "grabbing";
      dot.style.transform = "translate(-50%,-50%) scale(1.18)";
      dot.setPointerCapture?.(ev.pointerId);
      ev.stopPropagation();
      ev.preventDefault();
    });
  }

  const place = (ev) => {
    if (!st.dragging) return;
    const r = stage.getBoundingClientRect();
    if (!r.width || !r.height) return;
    const L = st.dragging;
    const wx = W(L.x), wy = W(L.y);
    if (wx) { wx.value = clamp01((ev.clientX - r.left) / r.width); wx.callback?.(wx.value); }
    if (wy) { wy.value = clamp01((ev.clientY - r.top) / r.height); wy.callback?.(wy.value); }
    render();
    node.setDirtyCanvas(true, true);
    ev.preventDefault();
  };

  const end = (ev) => {
    if (!st.dragging) return;
    const d = st.dots.find((x) => x.L === st.dragging);
    if (d) {
      d.dot.style.cursor = "grab";
      d.dot.style.transform = "translate(-50%,-50%)";
    }
    st.dragging = null;
    node.graph?.setDirtyCanvas?.(true, true);
    ev?.preventDefault?.();
  };

  window.addEventListener("pointermove", place);
  window.addEventListener("pointerup", end);
  window.addEventListener("pointercancel", end);
  st._detach = () => {
    window.removeEventListener("pointermove", place);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("pointercancel", end);
  };

  stage.addEventListener("pointerdown", (ev) => {
    if (ev.target !== stage && ev.target !== grid) return;
    const r = stage.getBoundingClientRect();
    const px = (ev.clientX - r.left) / r.width;
    const py = (ev.clientY - r.top) / r.height;
    let best = null, bestD = Infinity;
    for (const L of LIGHTS.slice(0, activeCount())) {
      const x = Number(W(L.x)?.value ?? 0.5);
      const y = Number(W(L.y)?.value ?? 0.5);
      const d = (x - px) ** 2 + (y - py) ** 2;
      if (d < bestD) { bestD = d; best = L; }
    }
    if (!best) return;
    st.dragging = best;
    place(ev);
    end(ev);
  });

  function render() {
    const t = theme();
    stage.style.background = t.sunken;
    stage.style.border = `1px solid ${t.edge}`;
    hintLine.el.style.color = t.dim;
    readoutLine.el.style.color = t.ink;

    const r = stage.getBoundingClientRect();
    const w = r.width || 320;
    stage.style.aspectRatio = String(aspect());
    const h = w / aspect();
    grid.style.backgroundImage =
      "linear-gradient(#ffffff0d 1px,transparent 1px),linear-gradient(90deg,#ffffff0d 1px,transparent 1px)";
    grid.style.backgroundSize = `${w / 8}px ${h / 8}px`;

    const active = activeCount();
    const shortEdge = Math.min(w, h);

    for (const { L, outer, inner } of st.rings) {
      const on = L.n <= active;
      const x = Number(W(L.x)?.value ?? 0.5) * 100;
      const y = Number(W(L.y)?.value ?? 0.5) * 100;
      const ri = Number(W(L.inner)?.value ?? 0.3);
      const ro = Number(W(L.outer)?.value ?? 0.6);
      for (const [el, rad, style, alpha] of [
        [outer, ro, "dashed", on ? 0.5 : 0.15],
        [inner, ri, "solid", on ? 0.85 : 0.2],
      ]) {
        const d = Math.max(0, rad) * shortEdge * 2;
        el.style.position = "absolute";
        el.style.borderRadius = "50%";
        el.style.transform = "translate(-50%,-50%)";
        el.style.pointerEvents = "none";
        el.style.left = `${x}%`;
        el.style.top = `${y}%`;
        el.style.width = `${d}px`;
        el.style.height = `${d}px`;
        el.style.borderWidth = "1px";
        el.style.borderStyle = style;
        el.style.borderColor = L.colour;
        el.style.opacity = String(alpha);
      }
    }
    for (const { L, dot, tag } of st.dots) {
      const on = L.n <= active;
      const x = Number(W(L.x)?.value ?? 0.5) * 100;
      const y = Number(W(L.y)?.value ?? 0.5) * 100;
      dot.style.left = `${x}%`;
      dot.style.top = `${y}%`;
      tag.style.left = `${x}%`;
      tag.style.top = `${y}%`;
      dot.style.opacity = on ? "1" : "0.28";
      tag.style.opacity = on ? "1" : "0.3";
      tag.style.color = t.onAccent;
    }

    hintLine.setText(active === 1
      ? "Drag the light, or click anywhere to move it."
      : `Drag any of ${active} lights. Click moves the nearest.`);
    const L1 = LIGHTS[0];
    readoutLine.setText(
      `${Number(W(L1.x)?.value ?? 0.5).toFixed(2)}, ${Number(W(L1.y)?.value ?? 0.5).toFixed(2)}`,
    );
  }
  st.render = render;

  for (const L of LIGHTS) {
    for (const nm of [L.x, L.y, L.inner, L.outer]) {
      const w = W(nm);
      if (!w) continue;
      const prev = w.callback;
      w.callback = function (...a) { const out = prev?.apply(this, a); render(); return out; };
    }
  }
  const nw = W("num_light_sources");
  if (nw) {
    const prev = nw.callback;
    nw.callback = function (...a) { const out = prev?.apply(this, a); render(); return out; };
  }

  mountPanel(node, "nmx_light_2d", root, { minHeight: PANEL_MIN });

  if (node.size[0] < NODE_MIN_W) node.size[0] = NODE_MIN_W;

  const ro = new ResizeObserver(() => render());
  ro.observe(stage);

  chainOnRemoved(node, () => {
    try { st._detach?.(); } catch (_e) { /* ignore */ }
    try { ro.disconnect(); } catch (_e) { /* ignore */ }
    delete node[STATE];
  });

  render();
}

if (!(app.extensions || []).some((e) => e?.name === "NukeMax.ReLight2D.Placer")) {
  app.registerExtension({
    name: "NukeMax.ReLight2D.Placer",
    async beforeRegisterNodeDef(nodeType, nodeData) {
      if (nodeData.name !== NODE_NAME) return;
      const onCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function () {
        onCreated?.apply(this, arguments);
        try { build(this); }
        catch (e) { console.error("[NukeMax] ReLight 2D placer failed", e); }
      };
      const onConfigure = nodeType.prototype.onConfigure;
      nodeType.prototype.onConfigure = function (...a) {
        const out = onConfigure?.apply(this, a);
        this[STATE]?.render?.();
        return out;
      };
    },
  });
}
