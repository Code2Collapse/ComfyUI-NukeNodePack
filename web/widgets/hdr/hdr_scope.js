// hdr_scope.js — on-node readouts for the NukeMax/HDR family.
//
// THE RULE THIS FOLLOWS: UI effort goes where the user genuinely cannot predict
// the result. These three qualify and the rest of the family does not:
//
//   * Tone Map        - seven operators plus three presets. Nobody can picture
//                       what `agx` at a white point of 2.0 does to their
//                       highlights. The node draws its OWN response curve.
//   * Expand Dynamic  - the knee position and the peak are pure arithmetic on
//     Range             two sliders, and the output runs to 64.0, far off the
//                       end of any preview. A log-scaled plot shows both.
//   * Histogram       - it returns a picture. Without this the user has to
//                       wire a Preview Image just to read their own scope.
//
// The curve maths lives in hdr_curves.js and is cross-checked against the
// Python node by tests/test_hdr_curves.py, so the plot is the real response.
//
// Plain ES module, no Vue. addDOMWidget renders on both the Vue and the legacy
// frontends; a raw canvas draw does not. Nothing touches `window` at import
// time, so a headless / queue-only run is unaffected.

import { app } from "../../../../scripts/app.js";
import {
  expandResponse,
  expansionKnee,
  toneMapResponse,
  TONEMAP_PRESETS,
} from "./hdr_curves.js";

const ST = "_nmHdrScope";
const PLOT_H = 132;

// ── theme ───────────────────────────────────────────────────────────────────
// A canvas fillStyle CANNOT parse `var(--x)` - it silently stays black, which
// is how a plot becomes an empty rectangle. Resolve to real colours once.
function resolveTheme(el) {
  const fallback = {
    ink: "#d6d6d6", dim: "#8a8a8a", grid: "#3a3a3a",
    curve: "#c8894a", accent: "#4fb3a5", warn: "#e06c6c", bg: "#1e1e1e",
  };
  try {
    const cs = getComputedStyle(el);
    const read = (name, def) => {
      const v = cs.getPropertyValue(name).trim();
      return v && !v.startsWith("var(") ? v : def;
    };
    return {
      ...fallback,
      ink: read("--input-text", fallback.ink),
      bg: read("--comfy-input-bg", fallback.bg),
    };
  } catch (_e) {
    return fallback;
  }
}

// ── plot frame ──────────────────────────────────────────────────────────────

function newCanvas() {
  const wrap = document.createElement("div");
  wrap.style.cssText =
    "width:100%;box-sizing:border-box;padding:2px 2px 0;" +
    "font:10px system-ui,sans-serif;";
  const cv = document.createElement("canvas");
  cv.style.cssText = "width:100%;display:block;border-radius:3px;";
  const cap = document.createElement("div");
  cap.style.cssText =
    "padding:2px 3px 0;opacity:.75;white-space:pre-line;line-height:1.35;" +
    "color:var(--input-text,#ddd);";
  wrap.append(cv, cap);
  return { wrap, cv, cap };
}

function fitBackingStore(cv) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.max(32, Math.round(cv.clientWidth * dpr));
  const h = Math.max(32, Math.round(PLOT_H * dpr));
  if (cv.width !== w || cv.height !== h) {
    cv.width = w;
    cv.height = h;
  }
  return dpr;
}

function drawFrame(ctx, w, h, theme) {
  ctx.fillStyle = theme.bg;
  ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = theme.grid;
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let i = 1; i < 4; i++) {
    const y = Math.round((h * i) / 4) + 0.5;
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
  }
  for (let i = 1; i < 8; i++) {
    const x = Math.round((w * i) / 8) + 0.5;
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
  }
  ctx.stroke();
}

// ── the three drawings ──────────────────────────────────────────────────────

function widgetValues(node) {
  const out = {};
  for (const w of node.widgets || []) out[w.name] = w.value;
  return out;
}

function drawToneMap(st, node) {
  const { ctx, w, h, theme } = st.frame;
  drawFrame(ctx, w, h, theme);
  const p = widgetValues(node);
  const X_MAX = 8.0;                       // three stops over white

  ctx.strokeStyle = theme.curve;
  ctx.lineWidth = 2;
  ctx.beginPath();
  const N = Math.max(64, Math.round(w / 2));
  for (let i = 0; i < N; i++) {
    const x = (i / (N - 1)) * X_MAX;
    const y = toneMapResponse(x, p);
    const px = (x / X_MAX) * w;
    const py = h - y * h;
    i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
  }
  ctx.stroke();

  // white point: the input value the operator is told maps to display white
  const cfg = (p.preset && p.preset !== "None (Custom)" && TONEMAP_PRESETS[p.preset])
    ? { ...p, ...TONEMAP_PRESETS[p.preset] } : p;
  const wp = cfg.white_point ?? 1.0;
  if (wp > 0 && wp <= X_MAX) {
    const px = Math.round((wp / X_MAX) * w) + 0.5;
    ctx.strokeStyle = theme.accent;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(px, 0);
    ctx.lineTo(px, h);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  ctx.fillStyle = theme.dim;
  ctx.font = `${10 * st.frame.dpr}px system-ui,sans-serif`;
  ctx.fillText("0", 3, h - 3);
  ctx.fillText(`${X_MAX} lin`, w - 42 * st.frame.dpr, h - 3);
  ctx.fillText("display 1.0", 3, 11 * st.frame.dpr);

  const atWhite = toneMapResponse(1.0, p);
  const clipsAt = (() => {
    for (let x = 0; x <= X_MAX; x += 0.02) if (toneMapResponse(x, p) >= 0.999) return x;
    return null;
  })();
  st.frame.cap.textContent =
    `${cfg.operator}  ·  white point ${(+wp).toFixed(2)}\n` +
    `scene 1.0 lands at ${atWhite.toFixed(3)} display` +
    (clipsAt === null ? "  ·  no clip in range" : `  ·  clips from ${clipsAt.toFixed(2)}`);
}

function drawExpansion(st, node) {
  const { ctx, w, h, theme } = st.frame;
  drawFrame(ctx, w, h, theme);
  const p = widgetValues(node);

  // Output runs to 2^(stops-8) - 64.0 at the default. Linear y would be a flat
  // line with one spike, so y is in STOPS above 1.0.
  const peak = Math.pow(2, (p.target_stops ?? 14) - 8);
  const yMaxStops = Math.max(1, Math.log2(Math.max(peak, 2)));
  const toY = (v) => {
    const stops = v <= 0 ? -yMaxStops : Math.log2(Math.max(v, 1e-6));
    const norm = (stops + yMaxStops) / (2 * yMaxStops);
    return h - Math.min(1, Math.max(0, norm)) * h;
  };

  ctx.strokeStyle = theme.curve;
  ctx.lineWidth = 2;
  ctx.beginPath();
  const N = Math.max(64, Math.round(w / 2));
  for (let i = 0; i < N; i++) {
    const x = i / (N - 1);
    const px = x * w;
    const py = toY(expandResponse(x, p));
    i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
  }
  ctx.stroke();

  const knee = expansionKnee(p);
  // The knee is defined on LINEAR luma; show it at the code value that reaches
  // it, which is where the curve visibly bends.
  let kneeCode = 1.0;
  for (let x = 0; x <= 1.0; x += 0.002) {
    if (expandResponse(x, { ...p, highlight_recovery: 0 }) >= knee) { kneeCode = x; break; }
  }
  const kx = Math.round(kneeCode * w) + 0.5;
  ctx.strokeStyle = theme.accent;
  ctx.setLineDash([3, 3]);
  ctx.beginPath();
  ctx.moveTo(kx, 0);
  ctx.lineTo(kx, h);
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.fillStyle = theme.dim;
  ctx.font = `${10 * st.frame.dpr}px system-ui,sans-serif`;
  ctx.fillText("code 0", 3, h - 3);
  ctx.fillText("code 1", w - 40 * st.frame.dpr, h - 3);
  ctx.fillText(`${peak.toFixed(0)}x`, 3, 11 * st.frame.dpr);

  st.frame.cap.textContent =
    `knee at code ${kneeCode.toFixed(2)}  ·  clipped white -> ` +
    `${expandResponse(1.0, p).toFixed(1)} linear\n` +
    `${(p.target_stops ?? 14).toFixed(1)} stops target  ·  ` +
    `recovery ${(p.highlight_recovery ?? 1).toFixed(2)}`;
}

function drawHistogram(st) {
  const { ctx, w, h, theme } = st.frame;
  drawFrame(ctx, w, h, theme);
  const d = st.scope;
  if (!d) {
    ctx.fillStyle = theme.dim;
    ctx.font = `${11 * st.frame.dpr}px system-ui,sans-serif`;
    ctx.fillText("run the graph to measure", 8, h / 2);
    st.frame.cap.textContent = "no measurement yet";
    return;
  }

  const bins = d.bins || [];
  const peak = Math.max(1, ...bins);
  const bw = w / Math.max(1, bins.length);
  ctx.fillStyle = theme.curve;
  for (let i = 0; i < bins.length; i++) {
    const bh = (bins[i] / peak) * (h - 4);
    ctx.fillRect(i * bw, h - bh, Math.max(1, bw - 0.5), bh);
  }

  // Where display white sits inside the measured range.
  const top = (d.range && d.range[1]) || 1;
  if (top > 1) {
    const px = Math.round((1 / top) * w) + 0.5;
    ctx.strokeStyle = theme.accent;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(px, 0);
    ctx.lineTo(px, h);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  const clipped = (d.clip_high || 0) > 0.01;
  ctx.fillStyle = clipped ? theme.warn : theme.dim;
  ctx.font = `${10 * st.frame.dpr}px system-ui,sans-serif`;
  ctx.fillText(`${(d.stops ?? 0).toFixed(1)} stops`, 3, 11 * st.frame.dpr);

  const frames = d.frames === 1 ? "1 frame" : `${d.frames} frames`;
  st.frame.cap.textContent =
    `min ${(+d.min).toFixed(4)}   max ${(+d.max).toFixed(4)}   ` +
    `mean ${(+d.mean).toFixed(4)}\n` +
    `clipped ${(+d.clip_high).toFixed(2)}% high / ${(+d.clip_low).toFixed(2)}% low` +
    `  ·  ${d.mode}  ·  ${frames}`;
}

// ── widget plumbing ─────────────────────────────────────────────────────────

const DRAW = {
  NukeMax_HDRToneMap: drawToneMap,
  NukeMax_HDRExpandDynamicRange: drawExpansion,
  NukeMax_HDRHistogram: (st) => drawHistogram(st),
};

function attachScope(node, nodeName) {
  if (node[ST]) return node[ST];
  const draw = DRAW[nodeName];
  if (!draw) return null;

  const { wrap, cv, cap } = newCanvas();
  const st = { scope: null, raf: 0, dead: false };
  node[ST] = st;

  const widget = node.addDOMWidget("nukemax_hdr_scope", "div", wrap, {
    serialize: false,
  });
  widget.computeSize = (width) => [width, PLOT_H + 30];

  const render = () => {
    st.raf = 0;
    if (st.dead || !cv.isConnected || !cv.clientWidth) return;
    const dpr = fitBackingStore(cv);
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    st.frame = {
      ctx, cap, dpr,
      w: cv.width, h: cv.height,
      theme: resolveTheme(wrap),
    };
    try {
      draw(st, node);
    } catch (e) {
      // A broken plot must never take the node down with it.
      cap.textContent = "scope unavailable";
    }
  };

  // rAF-coalesced: widget drags fire a callback per pixel of travel.
  st.invalidate = () => {
    if (st.dead || st.raf) return;
    st.raf = requestAnimationFrame(render);
  };

  // Redraw when any widget moves. The house kit's status strip has no
  // callback, so this is safe to apply to all of them.
  for (const w of node.widgets || []) {
    const prev = w.callback;
    w.callback = function (...args) {
      const r = prev?.apply(this, args);
      st.invalidate();
      return r;
    };
  }

  if (typeof ResizeObserver !== "undefined") {
    st.ro = new ResizeObserver(() => st.invalidate());
    st.ro.observe(cv);
  }

  const onRemoved = node.onRemoved;
  node.onRemoved = function (...args) {
    st.dead = true;
    if (st.raf) cancelAnimationFrame(st.raf);
    st.ro?.disconnect();
    return onRemoved?.apply(this, args);
  };

  st.invalidate();
  return st;
}

app.registerExtension({
  name: "NukeMax.HDRScope",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    const name = String(nodeData?.name || "");
    if (!DRAW[name]) return;

    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = onCreated?.apply(this, arguments);
      try { attachScope(this, name); } catch (_e) { /* never break the node */ }
      return r;
    };

    // Widget values loaded from a saved workflow arrive after onNodeCreated.
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (...args) {
      const r = onConfigure?.apply(this, args);
      this[ST]?.invalidate?.();
      return r;
    };

    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (output) {
      const r = onExecuted?.apply(this, arguments);
      const st = this[ST];
      const payload = output?.nukemax_hdr_scope?.[0];
      if (st && payload) {
        // Measurements come from the server, so treat them as data: a bad
        // parse leaves the previous reading rather than throwing.
        try { st.scope = JSON.parse(payload); } catch (_e) { /* keep the old one */ }
        st.invalidate?.();
      }
      return r;
    };
  },
});
