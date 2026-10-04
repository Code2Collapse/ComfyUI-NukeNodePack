// viewer_panel.js — the picture on the Viewer node.
//
// The node is called Viewer and shipped with no picture on it: to see what your
// own viewer was showing you had to wire a Preview Image to its output. That is
// the complaint this file exists to close.
//
// What it is, beyond a thumbnail. A Nuke viewer's defining trait is that the
// channel keys and the exposure wheel are INSTANT - you hold a key, look, and
// let go. Round-tripping that through a queue is not the same tool. So the
// channel isolation, the exposure and the gamma here run client-side on a
// canvas, at the speed of a keypress:
//
//   R G B A L   isolate a channel        (M mattes the alpha over the picture)
//   , / .       exposure down / up in stops
//   /           back to unity
//   hover       pixel probe - the values under the cursor
//
// Those are VIEW settings: they change what you see, never what the node
// outputs. "Bake" writes the current view back into the node's own widgets, so
// the next run produces what you were looking at. That distinction is the whole
// reason a viewer is a separate thing from a grade, and the strip says which
// mode you are in.
//
// The preview is display-referred 8-bit (the node clamps before it returns), so
// pulling exposure up recovers nothing that was clipped upstream. The probe
// reports what is actually in the preview rather than pretending otherwise.
//
// Plain ES module, no Vue, mountPanel so it renders on both frontends.

import { app } from "../../../../scripts/app.js";
import {
  mountPanel,
  pillBar,
  button,
  stage,
  statusLine,
  installZoomRepaint,
  canvasBackingScale,
} from "../../c2c_ui/index.js";

const ST = "_nmViewer";
const NODE_NAME = "NukeMax_Viewer";
const PANEL_MIN = 240;
const NODE_MIN_W = 380;
const PREVIEW_H = 160;

const CHANNELS = [
  { key: "rgb", label: "RGB", hint: "all channels" },
  { key: "red", label: "R", hint: "red only" },
  { key: "green", label: "G", hint: "green only" },
  { key: "blue", label: "B", hint: "blue only" },
  { key: "alpha", label: "A", hint: "alpha only" },
  { key: "luminance", label: "L", hint: "luminance" },
];

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

/** Isolate a channel and apply view exposure/gamma to one RGBA byte buffer. */
function shade(src, dst, channel, gain, gamma) {
  const invG = 1.0 / Math.max(gamma, 0.01);
  const lut = new Uint8ClampedArray(256);
  for (let i = 0; i < 256; i++) {
    const v = Math.pow(Math.min(1, Math.max(0, (i / 255) * gain)), invG);
    lut[i] = Math.round(v * 255);
  }
  for (let i = 0; i < src.length; i += 4) {
    const r = src[i], g = src[i + 1], b = src[i + 2], a = src[i + 3];
    let o0, o1, o2;
    switch (channel) {
      case "red":   o0 = o1 = o2 = r; break;
      case "green": o0 = o1 = o2 = g; break;
      case "blue":  o0 = o1 = o2 = b; break;
      case "alpha": o0 = o1 = o2 = a; break;
      case "luminance": {
        const l = 0.299 * r + 0.587 * g + 0.114 * b;
        o0 = o1 = o2 = l;
        break;
      }
      default: o0 = r; o1 = g; o2 = b;
    }
    dst[i] = lut[o0 | 0];
    dst[i + 1] = lut[o1 | 0];
    dst[i + 2] = lut[o2 | 0];
    dst[i + 3] = 255;
  }
}

function setupCanvas(canvas, cssW, cssH) {
  const scale = canvasBackingScale(cssW, cssH);
  const bw = Math.max(1, Math.round(cssW * scale));
  const bh = Math.max(1, Math.round(cssH * scale));
  if (canvas.width !== bw || canvas.height !== bh) {
    canvas.width = bw;
    canvas.height = bh;
  }
  canvas.style.width = `${cssW}px`;
  canvas.style.height = `${cssH}px`;
  return canvas.getContext("2d", { willReadFrequently: true });
}

function attach(node) {
  if (node[ST]) return node[ST];

  const root = document.createElement("div");
  root.style.display = "flex";
  root.style.flexDirection = "column";
  root.style.gap = "4px";
  root.style.width = "100%";
  root.style.height = "100%";

  const bar = document.createElement("div");
  bar.style.display = "flex";
  bar.style.alignItems = "center";
  bar.style.gap = "4px";
  bar.style.flexWrap = "wrap";

  const pills = pillBar(
    CHANNELS.map((c) => ({ value: c.key, label: c.label })),
    {
      value: "rgb",
      onChange: (v) => {
        st.channel = v;
        st.repaint();
      },
    },
  );
  for (const c of CHANNELS) {
    const btn = pills.querySelector(`[data-value="${c.key}"]`);
    if (btn) btn.title = `${c.hint} — press ${c.label[0]}`;
  }

  const spacer = document.createElement("div");
  spacer.style.flex = "1 1 auto";

  const exposureLine = statusLine();
  exposureLine.el.style.flex = "0 0 auto";
  exposureLine.el.style.fontVariantNumeric = "tabular-nums";

  const bakeBtn = button("Bake", {
    onClick: () => {
      const gain = widgetByName(node, "gain");
      const gamma = widgetByName(node, "gamma");
      const channel = widgetByName(node, "channel");
      if (gain) gain.value = Math.min(5, Math.max(0.1, Math.pow(2, st.stops)));
      if (gamma) gamma.value = Math.min(3, Math.max(0.1, st.gamma));
      if (channel && st.channel !== "rgb") channel.value = st.channel;
      st.stops = 0;
      st.gamma = 1.0;
      st.repaint();
      node.setDirtyCanvas?.(true, true);
    },
  });
  bakeBtn.title = "write this view into the node's gain and gamma widgets";

  bar.append(pills, spacer, exposureLine.el, bakeBtn);

  const previewCanvas = document.createElement("canvas");
  previewCanvas.style.display = "block";
  previewCanvas.style.cursor = "crosshair";
  previewCanvas.style.maxWidth = "100%";
  previewCanvas.style.maxHeight = "100%";

  const stageApi = stage({
    aspect: 16 / 9,
    empty: {
      title: "Viewer",
      hint: "Run the graph to see the frame",
    },
  });

  const probeLine = statusLine();
  const frameLine = statusLine();
  frameLine.el.style.marginLeft = "auto";
  frameLine.el.style.textAlign = "right";

  const strip = document.createElement("div");
  strip.style.display = "flex";
  strip.style.gap = "8px";
  strip.style.flexWrap = "wrap";
  strip.style.alignItems = "flex-start";
  strip.append(probeLine.el, frameLine.el);

  root.append(bar, stageApi.el, strip);

  const st = {
    channel: "rgb",
    stops: 0,
    gamma: 1.0,
    frames: [],
    index: 0,
    src: null,
    shaded: null,
    dead: false,
    previewCanvas,
    stageApi,
    exposureLine,
    probeLine,
    frameLine,
    pills,
    zoomOff: null,
    resizeObs: null,
  };
  node[ST] = st;

  const panelWidget = mountPanel(node, "nukemax_viewer", root, { minHeight: PANEL_MIN });
  panelWidget.onPanelResize = () => st.repaint();

  st.repaint = () => {
    if (st.dead) return;
    const viewport = stageApi.el.querySelector(".c2c-ui-stage__viewport");
    const cssW = Math.max(1, viewport?.clientWidth || node.size?.[0] - 40 || 300);
    const cssH = PREVIEW_H;

    if (!st.src) {
      stageApi.setEmpty({
        title: "Viewer",
        hint: st.emptyMsg || "Run the graph to see the frame",
      });
      updateExposureReadout(st);
      return;
    }

    const { w, h, data } = st.src;
    const ctx = setupCanvas(previewCanvas, cssW, cssH);
    const out = ctx.createImageData(w, h);
    shade(data, out.data, st.channel, Math.pow(2, st.stops), st.gamma);
    ctx.putImageData(out, 0, 0);
    st.shaded = out.data;
    stageApi.setCanvas(previewCanvas);
    const frameTxt = st.frames.length > 1
      ? `${w}×${h} · frame ${st.index + 1}/${st.frames.length}`
      : `${w}×${h}`;
    stageApi.setFooter(frameTxt);
    frameLine.setText(frameTxt);
    updateExposureReadout(st);
  };

  function updateExposureReadout(st) {
    const gain = Math.pow(2, st.stops);
    exposureLine.setText(
      `${st.stops >= 0 ? "+" : ""}${st.stops.toFixed(2)} stop` +
      (Math.abs(st.stops) === 1 ? "" : "s") +
      ` · x${gain.toFixed(2)}`,
    );
  }

  function loadFrame(i) {
    const entry = st.frames[i];
    if (!entry) return;
    st.index = i;
    const url = `/view?filename=${encodeURIComponent(entry.filename)}` +
      `&subfolder=${encodeURIComponent(entry.subfolder || "")}` +
      `&type=${encodeURIComponent(entry.type || "temp")}`;
    const img = new Image();
    img.onload = () => {
      if (st.dead) return;
      const off = document.createElement("canvas");
      off.width = img.naturalWidth;
      off.height = img.naturalHeight;
      const octx = off.getContext("2d", { willReadFrequently: true });
      octx.drawImage(img, 0, 0);
      const d = octx.getImageData(0, 0, off.width, off.height);
      st.src = { w: off.width, h: off.height, data: d.data };
      st.emptyMsg = "";
      st.repaint();
      node.setDirtyCanvas?.(true, true);
    };
    img.onerror = () => {
      if (st.dead) return;
      st.src = null;
      st.emptyMsg = "Preview expired — run the graph again";
      st.repaint();
    };
    img.src = url;
  }
  st.loadFrame = loadFrame;

  previewCanvas.addEventListener("pointermove", (e) => {
    if (!st.src || !st.shaded) return;
    const r = previewCanvas.getBoundingClientRect();
    const x = Math.floor(((e.clientX - r.left) / r.width) * st.src.w);
    const y = Math.floor(((e.clientY - r.top) / r.height) * st.src.h);
    if (x < 0 || y < 0 || x >= st.src.w || y >= st.src.h) {
      probeLine.setText("");
      return;
    }
    const o = (y * st.src.w + x) * 4;
    const f = (v) => (v / 255).toFixed(3);
    probeLine.setText(
      `${x},${y}   ${f(st.shaded[o])} ${f(st.shaded[o + 1])} ${f(st.shaded[o + 2])}`,
    );
  });
  previewCanvas.addEventListener("pointerleave", () => probeLine.setText(""));

  const viewport = stageApi.el.querySelector(".c2c-ui-stage__viewport");
  viewport.addEventListener("pointerdown", (e) => {
    if (st.frames.length < 2) return;
    viewport.setPointerCapture(e.pointerId);
    const r = viewport.getBoundingClientRect();
    const pick = (ev) => {
      const t = (ev.clientX - r.left) / Math.max(1, r.width);
      const i = Math.min(st.frames.length - 1,
        Math.max(0, Math.round(t * (st.frames.length - 1))));
      if (i !== st.index) loadFrame(i);
    };
    pick(e);
    const onMove = (ev) => pick(ev);
    viewport.addEventListener("pointermove", onMove);
    const up = () => {
      viewport.releasePointerCapture(e.pointerId);
      viewport.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointerup", up);
  });

  st.onKey = (e) => {
    if (st.dead || e.ctrlKey || e.metaKey || e.altKey) return;
    if (!app.canvas?.selected_nodes?.[node.id]) return;
    const tag = document.activeElement?.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA") return;
    const k = e.key.toLowerCase();
    const map = { r: "red", g: "green", b: "blue", a: "alpha", l: "luminance" };
    if (map[k]) {
      st.channel = st.channel === map[k] ? "rgb" : map[k];
      const pillBtn = pills.querySelector(`[data-value="${st.channel}"]`);
      pillBtn?.click();
    } else if (k === ",") {
      st.stops = Math.max(-8, st.stops - 0.25);
      st.repaint();
    } else if (k === ".") {
      st.stops = Math.min(8, st.stops + 0.25);
      st.repaint();
    } else if (k === "/") {
      st.stops = 0;
      st.gamma = 1.0;
      st.channel = "rgb";
      pills.querySelector('[data-value="rgb"]')?.click();
      st.repaint();
    } else {
      return;
    }
    e.preventDefault();
  };
  window.addEventListener("keydown", st.onKey);

  st.zoomOff = installZoomRepaint(node, () => st.repaint(), "_c2cNmViewerZoom");
  if (typeof ResizeObserver !== "undefined") {
    st.resizeObs = new ResizeObserver(() => st.repaint());
    st.resizeObs.observe(stageApi.el);
  }

  chainOnRemoved(node, () => {
    st.dead = true;
    try { st.zoomOff?.(); } catch (_e) { /* ignore */ }
    try { st.resizeObs?.disconnect(); } catch (_e) { /* ignore */ }
    window.removeEventListener("keydown", st.onKey);
    delete node[ST];
  });

  st.repaint();
  return st;
}

app.registerExtension({
  name: "NukeMax.ViewerPanel",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (String(nodeData?.name || "") !== NODE_NAME) return;

    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = onCreated?.apply(this, arguments);
      if (this.size[0] < NODE_MIN_W) this.size[0] = NODE_MIN_W;
      try { attach(this); } catch (_e) { /* never break the node */ }
      return r;
    };

    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (output) {
      const r = onExecuted?.apply(this, arguments);
      const st = this[ST];
      const images = output?.images;
      if (st && Array.isArray(images) && images.length) {
        st.frames = images;
        st.loadFrame(0);
      } else if (st) {
        st.src = null;
        st.emptyMsg = "No preview written — check the log for a Pillow or temp-dir problem";
        st.repaint();
      }
      return r;
    };
  },
});
