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
// Plain ES module, no Vue. mountPanel renders on both the Vue and the legacy
// frontends. Nothing touches `window` at import time.

import { app } from "../../../../scripts/app.js";
import {
  expandResponse,
  expansionKnee,
  toneMapResponse,
  TONEMAP_PRESETS,
} from "./hdr_curves.js";
import {
  lineChart,
  mountPanel,
  statusLine,
  installZoomRepaint,
  canvasBackingScale,
} from "../../c2c_ui/index.js";

const ST = "_nmHdrScope";
const PANEL_MIN = 180;
const NODE_MIN_W = 380;
const HIST_H = 132;

function chainOnRemoved(node, cleanup) {
  const orig = node.onRemoved;
  node.onRemoved = function (...a) {
    try { cleanup?.(); } catch (_e) { /* ignore */ }
    return orig?.apply(this, a);
  };
}

function widgetValues(node) {
  const out = {};
  for (const w of node.widgets || []) out[w.name] = w.value;
  return out;
}

function plotColours() {
  const cs = getComputedStyle(document.documentElement);
  const g = (v, fb) => cs.getPropertyValue(v).trim() || fb;
  return {
    bg: g("--cu-sunken", "#0c0d23"),
    grid: g("--cu-edge", "#2a2a57"),
    curve: g("--cu-warn", "#ffd166"),
    accent: g("--cu-accent", "#b494ff"),
    dim: g("--cu-ink-dim", "#6f6d9b"),
    warn: g("--cu-danger", "#f87171"),
  };
}

function setupHistCanvas(cv, cssH) {
  // Measure the PARENT: the canvas's own width is whatever we last drew at,
  // so measuring it (and pinning style.width in px) froze the plot at its
  // first size - it never grew to the panel.
  const cssW = Math.max(32, cv.parentElement?.clientWidth || cv.clientWidth || 300);
  const scale = canvasBackingScale(cssW, cssH);
  const w = Math.max(1, Math.round(cssW * scale));
  const h = Math.max(1, Math.round(cssH * scale));
  if (cv.width !== w || cv.height !== h) {
    cv.width = w;
    cv.height = h;
  }
  cv.style.width = "100%";
  cv.style.height = `${cssH}px`;
  const ctx = cv.getContext("2d");
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  return { ctx, w: cssW, h: cssH, theme: plotColours() };
}

function drawHistGrid(ctx, w, h, theme) {
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

function buildToneMapChart() {
  const caption = statusLine();
  const chart = lineChart({
    minHeight: 130,
    xLabel: "linear input",
    yLabel: "display",
    xFormat: (v) => v.toFixed(1),
    yFormat: (v) => v.toFixed(2),
    series: [
      { id: "response", label: "tone map", color: "--cu-series-2", axis: "y" },
    ],
    empty: { title: "Tone map", hint: "Adjust widgets to see the response curve." },
  });
  chart.setState("ready");
  return { chart, caption, kind: "tone" };
}

function buildExpansionChart() {
  const caption = statusLine();
  const chart = lineChart({
    minHeight: 130,
    xLabel: "code",
    yLabel: "output (log stops)",
    xFormat: (v) => v.toFixed(2),
    series: [
      { id: "expand", label: "expansion", color: "--cu-series-2", axis: "y" },
    ],
    empty: { title: "Expand dynamic range", hint: "Adjust widgets to see the knee." },
  });
  chart.setState("ready");
  return { chart, caption, kind: "expand" };
}

function buildHistogramPlot() {
  const wrap = document.createElement("div");
  wrap.style.width = "100%";
  const cv = document.createElement("canvas");
  cv.style.width = "100%";
  cv.style.display = "block";
  cv.style.borderRadius = "6px";
  cv.style.minHeight = `${HIST_H}px`;
  const caption = statusLine();
  wrap.append(cv, caption.el);
  return { wrap, cv, caption, kind: "hist" };
}

function rebuildTone(st, node) {
  const p = widgetValues(node);
  const X_MAX = 8.0;
  const N = 128;
  const xs = [];
  const ys = [];
  for (let i = 0; i < N; i++) {
    const x = (i / (N - 1)) * X_MAX;
    xs.push(x);
    ys.push(toneMapResponse(x, p));
  }
  const cfg = (p.preset && p.preset !== "None (Custom)" && TONEMAP_PRESETS[p.preset])
    ? { ...p, ...TONEMAP_PRESETS[p.preset] } : p;
  const wp = cfg.white_point ?? 1.0;
  st.chart.setThresholds(wp > 0 && wp <= X_MAX
    ? [{ axis: "x", value: wp, label: `white ${(+wp).toFixed(2)}` }]
    : []);
  st.chart.setData(xs, { response: ys });
  st.chart.setState("ready");

  const atWhite = toneMapResponse(1.0, p);
  let clipsAt = null;
  for (let x = 0; x <= X_MAX; x += 0.02) {
    if (toneMapResponse(x, p) >= 0.999) { clipsAt = x; break; }
  }
  st.caption.setText(
    `${cfg.operator} · white point ${(+wp).toFixed(2)} · ` +
    `scene 1.0 lands at ${atWhite.toFixed(3)} display` +
    (clipsAt === null ? " · no clip in range" : ` · clips from ${clipsAt.toFixed(2)}`),
  );
}

function rebuildExpand(st, node) {
  const p = widgetValues(node);
  const peak = Math.pow(2, (p.target_stops ?? 14) - 8);
  const yMaxStops = Math.max(1, Math.log2(Math.max(peak, 2)));
  const toY = (v) => {
    const stops = v <= 0 ? -yMaxStops : Math.log2(Math.max(v, 1e-6));
    const norm = (stops + yMaxStops) / (2 * yMaxStops);
    return Math.min(1, Math.max(0, norm));
  };
  const N = 128;
  const xs = [];
  const ys = [];
  for (let i = 0; i < N; i++) {
    const x = i / (N - 1);
    xs.push(x);
    ys.push(toY(expandResponse(x, p)));
  }
  const knee = expansionKnee(p);
  let kneeCode = 1.0;
  for (let x = 0; x <= 1.0; x += 0.002) {
    if (expandResponse(x, { ...p, highlight_recovery: 0 }) >= knee) {
      kneeCode = x;
      break;
    }
  }
  st.chart.setThresholds([{ axis: "x", value: kneeCode, label: `knee ${kneeCode.toFixed(2)}` }]);
  st.chart.setData(xs, { expand: ys });
  st.chart.setState("ready");
  st.caption.setText(
    `knee at code ${kneeCode.toFixed(2)} · clipped white → ` +
    `${expandResponse(1.0, p).toFixed(1)} linear · ` +
    `${(p.target_stops ?? 14).toFixed(1)} stops target · ` +
    `recovery ${(p.highlight_recovery ?? 1).toFixed(2)}`,
  );
}

function drawHistogram(st) {
  const { ctx, w, h, theme } = setupHistCanvas(st.cv, HIST_H);
  drawHistGrid(ctx, w, h, theme);
  const d = st.scope;
  if (!d) {
    ctx.fillStyle = theme.dim;
    ctx.font = "11px system-ui,sans-serif";
    ctx.fillText("run the graph to measure", 8, h / 2);
    st.caption.setText("no measurement yet");
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
  ctx.font = "10px system-ui,sans-serif";
  ctx.fillText(`${(d.stops ?? 0).toFixed(1)} stops`, 3, 11);
  const frames = d.frames === 1 ? "1 frame" : `${d.frames} frames`;
  st.caption.setText(
    `min ${(+d.min).toFixed(4)}   max ${(+d.max).toFixed(4)}   ` +
    `mean ${(+d.mean).toFixed(4)} · ` +
    `clipped ${(+d.clip_high).toFixed(2)}% high / ${(+d.clip_low).toFixed(2)}% low · ` +
    `${d.mode} · ${frames}`,
  );
}

const BUILDERS = {
  NukeMax_HDRToneMap: buildToneMapChart,
  NukeMax_HDRExpandDynamicRange: buildExpansionChart,
  NukeMax_HDRHistogram: buildHistogramPlot,
};

function attachScope(node, nodeName) {
  if (node[ST]) return node[ST];
  const build = BUILDERS[nodeName];
  if (!build) return null;

  const root = document.createElement("div");
  root.style.display = "flex";
  root.style.flexDirection = "column";
  root.style.gap = "4px";
  root.style.width = "100%";
  root.style.height = "100%";

  const ui = build();
  if (ui.chart) {
    root.append(ui.chart.el, ui.caption.el);
  } else {
    root.append(ui.wrap);
  }

  const st = { ...ui, scope: null, dead: false, zoomOff: null, resizeObs: null };
  node[ST] = st;

  const panelWidget = mountPanel(node, "nukemax_hdr_scope", root, { minHeight: PANEL_MIN });
  const repaint = () => {
    if (st.dead) return;
    if (st.kind === "tone") rebuildTone(st, node);
    else if (st.kind === "expand") rebuildExpand(st, node);
    else if (st.kind === "hist") drawHistogram(st);
  };
  st.repaint = repaint;

  if (st.chart) {
    panelWidget.onPanelResize = () => st.chart.redraw();
    st.zoomOff = installZoomRepaint(node, () => st.chart.redraw(), "_c2cNmHdrZoom");
  } else if (st.cv) {
    panelWidget.onPanelResize = repaint;
    st.zoomOff = installZoomRepaint(node, repaint, "_c2cNmHdrZoom");
    if (typeof ResizeObserver !== "undefined") {
      st.resizeObs = new ResizeObserver(repaint);
      st.resizeObs.observe(st.cv);
    }
  }

  for (const w of node.widgets || []) {
    const prev = w.callback;
    w.callback = function (...args) {
      const r = prev?.apply(this, args);
      repaint();
      return r;
    };
  }

  chainOnRemoved(node, () => {
    st.dead = true;
    try { st.zoomOff?.(); } catch (_e) { /* ignore */ }
    try { st.chart?.destroy(); } catch (_e) { /* ignore */ }
    try { st.resizeObs?.disconnect(); } catch (_e) { /* ignore */ }
    delete node[ST];
  });

  repaint();
  return st;
}

app.registerExtension({
  name: "NukeMax.HDRScope",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    const name = String(nodeData?.name || "");
    if (!BUILDERS[name]) return;

    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = onCreated?.apply(this, arguments);
      if (this.size[0] < NODE_MIN_W) this.size[0] = NODE_MIN_W;
      try { attachScope(this, name); } catch (_e) { /* never break the node */ }
      return r;
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (...args) {
      const r = onConfigure?.apply(this, args);
      this[ST]?.repaint?.();
      return r;
    };

    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (output) {
      const r = onExecuted?.apply(this, arguments);
      const st = this[ST];
      const payload = output?.nukemax_hdr_scope?.[0];
      if (st && payload) {
        try { st.scope = JSON.parse(payload); } catch (_e) { /* keep old */ }
        st.repaint?.();
      }
      return r;
    };
  },
});
