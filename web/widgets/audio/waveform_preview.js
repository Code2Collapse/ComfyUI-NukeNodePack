// Audio waveform / spectrogram preview widget.
// Attaches a read-only waveform display to nodes named
// "NukeMax_AudioLoadAnalyze". Reads the file path from the node's
// `path` widget and renders a stylized stripe plus BPM/duration
// readout. The actual audio analysis happens server-side; this is a
// preview helper so the user can confirm the file is loaded.

import { app } from "../../../../scripts/app.js";
import {
  mountPanel,
  statusLine,
  section,
  installZoomRepaint,
  canvasBackingScale,
} from "../../c2c_ui/index.js";

const NODE_NAME = "NukeMax_AudioLoadAnalyze";
const ST = "_nmWaveform";
const PANEL_MIN = 120;
const NODE_MIN_W = 380;
const STRIP_H = 96;

function chainOnRemoved(node, cleanup) {
  const orig = node.onRemoved;
  node.onRemoved = function (...a) {
    try { cleanup?.(); } catch (_e) { /* ignore */ }
    return orig?.apply(this, a);
  };
}

function widgetByName(node, name) {
  return (node.widgets || []).find((w) => w.name === name);
}

function plotColours() {
  const cs = getComputedStyle(document.documentElement);
  const g = (v, fb) => cs.getPropertyValue(v).trim() || fb;
  return {
    bg: g("--cu-sunken", "#0c0d23"),
    grid: g("--cu-edge", "#2a2a57"),
    accent: g("--cu-accent", "#b494ff"),
    dim: g("--cu-ink-dim", "#6f6d9b"),
    panel: g("--cu-panel", "#1e1f47"),
    ink: g("--cu-ink-soft", "#bab7db"),
  };
}

function createWaveformWidget(node) {
  if (node[ST]) return node[ST];

  const state = {
    path: "",
    loaded: false,
    bpm: null,
    duration: 0,
    bars: new Array(96).fill(0),
    dead: false,
    zoomOff: null,
    resizeObs: null,
  };

  const root = document.createElement("div");
  root.style.display = "flex";
  root.style.flexDirection = "column";
  root.style.gap = "4px";
  root.style.width = "100%";

  const canvas = document.createElement("canvas");
  canvas.style.display = "block";
  canvas.style.width = "100%";

  const readout = statusLine();
  readout.el.style.fontVariantNumeric = "tabular-nums";

  const body = document.createElement("div");
  body.append(canvas, readout.el);
  root.appendChild(section("Waveform", body));

  node[ST] = state;

  const pathWidget = widgetByName(node, "path");

  function loadPreview() {
    if (!pathWidget?.value || pathWidget.value === state.path) return;
    state.path = pathWidget.value;
    try {
      const url = `/view?filename=${encodeURIComponent(state.path)}`;
      fetch(url).then((r) => r.arrayBuffer()).then((buf) => {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return;
        const ctx = new Ctx();
        ctx.decodeAudioData(buf, (decoded) => {
          if (state.dead) return;
          const ch0 = decoded.getChannelData(0);
          const N = state.bars.length;
          const step = Math.max(1, (ch0.length / N) | 0);
          for (let i = 0; i < N; i++) {
            let peak = 0;
            const start = i * step;
            const end = Math.min(ch0.length, start + step);
            for (let j = start; j < end; j++) {
              const v = Math.abs(ch0[j]);
              if (v > peak) peak = v;
            }
            state.bars[i] = peak;
          }
          state.duration = decoded.duration;
          state.loaded = true;
          repaint();
        }, () => { state.loaded = false; repaint(); });
      }).catch(() => { state.loaded = false; repaint(); });
    } catch (_e) { /* preview is best-effort */ }
  }

  function formatReadout() {
    const name = state.path ? state.path.split(/[\\/]/).pop() : "";
    const dur = state.loaded ? `${state.duration.toFixed(2)}s` : "—";
    const bpm = state.bpm != null ? `${state.bpm.toFixed(1)} BPM` : "BPM —";
    // the canvas already carries the hint; the readout only adds what it lacks
    if (!state.path) return "";
    if (!state.loaded) return name || state.path;
    return `${name} · ${dur} · ${bpm}`;
  }

  function repaint() {
    if (state.dead) return;
    const cssW = Math.max(1, canvas.parentElement?.clientWidth || node.size?.[0] - 40 || 300);
    const cssH = STRIP_H;
    const scale = canvasBackingScale(cssW, cssH);
    const bw = Math.max(1, Math.round(cssW * scale));
    const bh = Math.max(1, Math.round(cssH * scale));
    if (canvas.width !== bw || canvas.height !== bh) {
      canvas.width = bw;
      canvas.height = bh;
    }
    canvas.style.width = `${cssW}px`;
    canvas.style.height = `${cssH}px`;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    const t = plotColours();
    const w = cssW;
    const height = cssH;

    ctx.fillStyle = t.bg;
    ctx.fillRect(0, 0, w, height);

    if (!state.loaded) {
      // placeholder baseline sits BELOW the text (it ran through the title)
      ctx.strokeStyle = t.panel;
      ctx.beginPath();
      ctx.moveTo(0, height - 14);
      ctx.lineTo(w, height - 14);
      ctx.stroke();
      ctx.fillStyle = t.panel;
      for (let i = 0; i < 48; i++) {
        const bx = (i + 0.5) * (w / 48);
        ctx.fillRect(bx - 1, height - 17, 2, 6);
      }
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = t.ink;
      ctx.font = "600 12px system-ui,sans-serif";
      ctx.fillText("Audio waveform preview", w / 2, height / 2 - 8);
      ctx.fillStyle = t.dim;
      ctx.font = "11px system-ui,sans-serif";
      const hint = state.path
        ? "preview unavailable (server-side load only)"
        : "set the path field to preview the waveform";
      ctx.fillText(hint, w / 2, height / 2 + 12);
      ctx.textAlign = "left";
      ctx.textBaseline = "alphabetic";
      readout.setText(formatReadout());
      loadPreview();
      return;
    }

    ctx.strokeStyle = t.grid;
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    ctx.lineTo(w, height / 2);
    ctx.stroke();

    const N = state.bars.length;
    const barW = w / N;
    ctx.fillStyle = t.accent;
    for (let i = 0; i < N; i++) {
      const v = state.bars[i];
      const bh2 = Math.max(1, v * (height - 8));
      ctx.fillRect(i * barW + 1, (height - bh2) / 2, barW - 2, bh2);
    }
    readout.setText(formatReadout());
  }

  state.repaint = repaint;

  const panelWidget = mountPanel(node, "audio_waveform", root, { minHeight: PANEL_MIN });
  panelWidget.onPanelResize = repaint;
  state.zoomOff = installZoomRepaint(node, repaint, "_c2cNmWaveZoom");

  if (pathWidget) {
    const prev = pathWidget.callback;
    pathWidget.callback = function (...a) {
      const r = prev?.apply(this, a);
      state.path = "";
      state.loaded = false;
      loadPreview();
      return r;
    };
  }

  if (typeof ResizeObserver !== "undefined") {
    state.resizeObs = new ResizeObserver(repaint);
    state.resizeObs.observe(root);
  }

  chainOnRemoved(node, () => {
    state.dead = true;
    try { state.zoomOff?.(); } catch (_e) { /* ignore */ }
    try { state.resizeObs?.disconnect(); } catch (_e) { /* ignore */ }
    delete node[ST];
  });

  if (node.size[0] < NODE_MIN_W) node.size[0] = NODE_MIN_W;

  setTimeout(loadPreview, 100);
  repaint();
  return state;
}

app.registerExtension({
  name: "NukeMax.Audio",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;
    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onCreated?.apply(this, arguments);
      try { createWaveformWidget(this); } catch (e) {
        console.error("[NukeMax] waveform widget failed", e);
      }
    };
    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (output) {
      const r = onExecuted?.apply(this, arguments);
      const st = this[ST];
      if (st && output?.bpm != null) {
        const b = Array.isArray(output.bpm) ? output.bpm[0] : output.bpm;
        if (Number.isFinite(Number(b))) {
          st.bpm = Number(b);
          st.repaint?.();
        }
      }
      return r;
    };
  },
});
