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
// Plain ES module, no Vue, addDOMWidget so it renders on both frontends.

import { app } from "../../../scripts/app.js";

const ST = "_nmViewer";
const NODE_NAME = "NukeMax_Viewer";
const VIEW_H = 190;

const CHANNELS = [
  { key: "rgb", label: "RGB", hint: "all channels" },
  { key: "red", label: "R", hint: "red only" },
  { key: "green", label: "G", hint: "green only" },
  { key: "blue", label: "B", hint: "blue only" },
  { key: "alpha", label: "A", hint: "alpha only" },
  { key: "luminance", label: "L", hint: "luminance" },
];

// ── DOM ─────────────────────────────────────────────────────────────────────

function css(el, s) { Object.assign(el.style, s); }

function build() {
  const root = document.createElement("div");
  css(root, {
    width: "100%", boxSizing: "border-box", padding: "2px",
    font: "10px system-ui,sans-serif", color: "var(--input-text,#ddd)",
    display: "flex", flexDirection: "column", gap: "3px",
  });

  const bar = document.createElement("div");
  css(bar, { display: "flex", alignItems: "center", gap: "3px", flexWrap: "wrap" });

  const chips = {};
  for (const c of CHANNELS) {
    const b = document.createElement("button");
    b.textContent = c.label;
    b.title = `${c.hint} — press ${c.label[0]}`;
    css(b, {
      flex: "0 0 auto", padding: "1px 6px", borderRadius: "3px",
      border: "1px solid var(--border-color,#444)", cursor: "pointer",
      background: "transparent", color: "inherit", font: "inherit",
    });
    bar.append(b);
    chips[c.key] = b;
  }

  const spacer = document.createElement("div");
  css(spacer, { flex: "1 1 auto" });

  const exposure = document.createElement("span");
  exposure.title = "view exposure in stops — , and . to step, / to reset";
  css(exposure, { flex: "0 0 auto", opacity: ".8", fontVariantNumeric: "tabular-nums" });

  const bake = document.createElement("button");
  bake.textContent = "bake";
  bake.title = "write this view into the node's gain and gamma widgets";
  css(bake, {
    flex: "0 0 auto", padding: "1px 6px", borderRadius: "3px",
    border: "1px solid var(--border-color,#444)", cursor: "pointer",
    background: "transparent", color: "inherit", font: "inherit",
  });

  bar.append(spacer, exposure, bake);

  const stage = document.createElement("div");
  css(stage, {
    position: "relative", width: "100%", height: `${VIEW_H}px`,
    display: "flex", alignItems: "center", justifyContent: "center",
    background: "#161616", borderRadius: "3px", overflow: "hidden",
  });

  const canvas = document.createElement("canvas");
  css(canvas, { maxWidth: "100%", maxHeight: "100%", display: "block",
                imageRendering: "auto", cursor: "crosshair" });

  const empty = document.createElement("div");
  empty.textContent = "run the graph to see the frame";
  css(empty, { position: "absolute", opacity: ".55" });

  stage.append(canvas, empty);

  const strip = document.createElement("div");
  css(strip, { display: "flex", gap: "8px", padding: "0 2px", opacity: ".75",
               fontVariantNumeric: "tabular-nums", minHeight: "13px" });

  const probe = document.createElement("span");
  const frameLabel = document.createElement("span");
  css(frameLabel, { marginLeft: "auto" });
  strip.append(probe, frameLabel);

  root.append(bar, stage, strip);
  return { root, bar, chips, exposure, bake, stage, canvas, empty, probe, frameLabel };
}

// ── pixel pipeline ──────────────────────────────────────────────────────────

/** Isolate a channel and apply view exposure/gamma to one RGBA byte buffer. */
function shade(src, dst, channel, gain, gamma) {
  const invG = 1.0 / Math.max(gamma, 0.01);
  // A 256-entry LUT: the same eight arithmetic ops per pixel would cost ~2M
  // Math.pow calls on a 1080p frame and drop the probe to a crawl.
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
        // Rec.601, matching the node's own luminance branch.
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

// ── widget ──────────────────────────────────────────────────────────────────

function attach(node) {
  if (node[ST]) return node[ST];
  const ui = build();
  const st = {
    ui, channel: "rgb", stops: 0, gamma: 1.0,
    frames: [], index: 0, src: null, raf: 0, dead: false,
  };
  node[ST] = st;

  const widget = node.addDOMWidget("nukemax_viewer", "div", ui.root, {
    serialize: false,
  });
  widget.computeSize = (width) => [width, VIEW_H + 40];

  const ctx = ui.canvas.getContext("2d", { willReadFrequently: true });

  function paintChips() {
    for (const c of CHANNELS) {
      const on = st.channel === c.key;
      const b = ui.chips[c.key];
      b.style.background = on ? "var(--input-text,#ddd)" : "transparent";
      b.style.color = on ? "#111" : "inherit";
      b.style.opacity = on ? "1" : ".7";
    }
    const gain = Math.pow(2, st.stops);
    ui.exposure.textContent =
      `${st.stops >= 0 ? "+" : ""}${st.stops.toFixed(2)} stop` +
      (Math.abs(st.stops) === 1 ? "" : "s") +
      `  ·  x${gain.toFixed(2)}`;
  }

  function render() {
    st.raf = 0;
    if (st.dead || !st.src) return;
    const { w, h, data } = st.src;
    if (ui.canvas.width !== w || ui.canvas.height !== h) {
      ui.canvas.width = w;
      ui.canvas.height = h;
    }
    const out = ctx.createImageData(w, h);
    shade(data, out.data, st.channel, Math.pow(2, st.stops), st.gamma);
    ctx.putImageData(out, 0, 0);
    st.shaded = out.data;
    paintChips();
  }

  st.invalidate = () => {
    if (st.dead || st.raf) return;
    st.raf = requestAnimationFrame(render);
  };

  /** Pull one preview frame into an offscreen buffer we can re-shade. */
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
      ui.empty.style.display = "none";
      ui.frameLabel.textContent = st.frames.length > 1
        ? `${off.width}x${off.height}  ·  frame ${i + 1}/${st.frames.length}`
        : `${off.width}x${off.height}`;
      st.invalidate();
      node.setDirtyCanvas(true, true);
    };
    img.onerror = () => {
      if (st.dead) return;
      // The temp file is gone (server restart, temp cleared). Say so rather
      // than leaving the last render up as if it were current.
      st.src = null;
      ui.empty.textContent = "preview expired — run the graph again";
      ui.empty.style.display = "block";
    };
    img.src = url;
  }

  // ── interaction ───────────────────────────────────────────────────────────

  for (const c of CHANNELS) {
    ui.chips[c.key].onclick = () => {
      st.channel = st.channel === c.key && c.key !== "rgb" ? "rgb" : c.key;
      st.invalidate();
    };
  }

  ui.bake.onclick = () => {
    // View -> node. The node's own gain/gamma are what the next render uses.
    const gain = node.widgets?.find((w) => w.name === "gain");
    const gamma = node.widgets?.find((w) => w.name === "gamma");
    const channel = node.widgets?.find((w) => w.name === "channel");
    if (gain) gain.value = Math.min(5, Math.max(0.1, Math.pow(2, st.stops)));
    if (gamma) gamma.value = Math.min(3, Math.max(0.1, st.gamma));
    if (channel && st.channel !== "rgb") channel.value = st.channel;
    st.stops = 0;
    st.gamma = 1.0;
    st.invalidate();
    node.setDirtyCanvas(true, true);
  };

  ui.stage.onpointermove = (e) => {
    if (!st.src || !st.shaded) return;
    const r = ui.canvas.getBoundingClientRect();
    const x = Math.floor(((e.clientX - r.left) / r.width) * st.src.w);
    const y = Math.floor(((e.clientY - r.top) / r.height) * st.src.h);
    if (x < 0 || y < 0 || x >= st.src.w || y >= st.src.h) {
      ui.probe.textContent = "";
      return;
    }
    const o = (y * st.src.w + x) * 4;
    const f = (v) => (v / 255).toFixed(3);
    ui.probe.textContent =
      `${x},${y}   ${f(st.shaded[o])} ${f(st.shaded[o + 1])} ${f(st.shaded[o + 2])}`;
  };
  ui.stage.onpointerleave = () => { ui.probe.textContent = ""; };

  // Scrub frames by dragging across the stage with the button held.
  ui.stage.onpointerdown = (e) => {
    if (st.frames.length < 2) return;
    ui.stage.setPointerCapture(e.pointerId);
    const r = ui.stage.getBoundingClientRect();
    const pick = (ev) => {
      const t = (ev.clientX - r.left) / Math.max(1, r.width);
      const i = Math.min(st.frames.length - 1,
                         Math.max(0, Math.round(t * (st.frames.length - 1))));
      if (i !== st.index) loadFrame(i);
    };
    pick(e);
    ui.stage.onpointermove = pick;
    const up = () => {
      ui.stage.releasePointerCapture(e.pointerId);
      ui.stage.onpointermove = null;
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointerup", up);
  };

  // Keyboard, but ONLY while this node is the selected one - a global R/G/B
  // binding would fight the graph's own shortcuts.
  st.onKey = (e) => {
    if (st.dead || e.ctrlKey || e.metaKey || e.altKey) return;
    if (!app.canvas?.selected_nodes?.[node.id]) return;
    const tag = document.activeElement?.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA") return;
    const k = e.key.toLowerCase();
    const map = { r: "red", g: "green", b: "blue", a: "alpha", l: "luminance" };
    if (map[k]) {
      st.channel = st.channel === map[k] ? "rgb" : map[k];
    } else if (k === ",") {
      st.stops = Math.max(-8, st.stops - 0.25);
    } else if (k === ".") {
      st.stops = Math.min(8, st.stops + 0.25);
    } else if (k === "/") {
      st.stops = 0; st.gamma = 1.0; st.channel = "rgb";
    } else {
      return;
    }
    e.preventDefault();
    st.invalidate();
  };
  window.addEventListener("keydown", st.onKey);

  const onRemoved = node.onRemoved;
  node.onRemoved = function (...args) {
    st.dead = true;
    if (st.raf) cancelAnimationFrame(st.raf);
    window.removeEventListener("keydown", st.onKey);
    return onRemoved?.apply(this, args);
  };

  st.loadFrame = loadFrame;
  paintChips();
  return st;
}

app.registerExtension({
  name: "NukeMax.ViewerPanel",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (String(nodeData?.name || "") !== NODE_NAME) return;

    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = onCreated?.apply(this, arguments);
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
        st.ui.empty.textContent =
          "no preview written — check the log for a Pillow or temp-dir problem";
        st.ui.empty.style.display = "block";
      }
      return r;
    };
  },
});
