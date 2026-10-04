// Roto Spline Editor canvas widget.
// Attaches a click-to-add / drag bezier editor to nodes named
// "NukeMax_RotoSplineEditor". The widget writes its JSON state into
// the hidden `spline_state` STRING widget so the value persists in
// the workflow.

import { app } from "../../../../scripts/app.js";
import {
  mountPanel,
  stage,
  button,
  section,
  sliderRow,
  toolGrid,
  statusLine,
  openEditor,
  canvasBackingScale,
  installZoomRepaint,
} from "../../c2c_ui/index.js";

const NODE_NAME = "NukeMax_RotoSplineEditor";
const ST = "_nmRoto";
const PANEL_MIN = 200;
const NODE_MIN_W = 380;
const PREVIEW_H = 140;
const PREVIEW_MAX_H = 320;
const HIT_PX = 9;

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

function emptyState() {
  return {
    frames: [{ points: [], in: [], out: [], feather: [] }],
    closed: true,
    canvas: { h: 512, w: 512 },
    currentFrame: 0,
  };
}

function cloneState(src) {
  return JSON.parse(JSON.stringify(src));
}

function readState(text) {
  if (!text || !String(text).trim()) return emptyState();
  try {
    const data = JSON.parse(text);
    const frames = Array.isArray(data.frames) ? data.frames : [{ points: [], in: [], out: [], feather: [] }];
    return {
      frames: frames.map((f) => ({
        points: Array.isArray(f.points) ? f.points.map((p) => [+p[0], +p[1]]) : [],
        in: Array.isArray(f.in) ? f.in.map((p) => [+p[0], +p[1]]) : [],
        out: Array.isArray(f.out) ? f.out.map((p) => [+p[0], +p[1]]) : [],
        feather: Array.isArray(f.feather) ? f.feather.map((v) => +v) : [],
      })),
      closed: data.closed !== false,
      canvas: {
        h: +(data.canvas?.h ?? 512),
        w: +(data.canvas?.w ?? 512),
      },
      currentFrame: 0,
    };
  } catch (_e) {
    return emptyState();
  }
}

function writeState(state) {
  return JSON.stringify({
    frames: state.frames,
    closed: state.closed,
    canvas: state.canvas,
  });
}

function frameOf(state, i) {
  return state.frames[i] || { points: [], in: [], out: [], feather: [] };
}

function ensureFrameArrays(state, fi) {
  const f = frameOf(state, fi);
  while (f.points.length > f.in.length) {
    const p = f.points[f.in.length];
    f.in.push([p[0], p[1]]);
    f.out.push([p[0], p[1]]);
    f.feather.push(0);
  }
  while (f.in.length > f.points.length) {
    f.in.pop(); f.out.pop(); f.feather.pop();
  }
  return f;
}

function plotColours() {
  const cs = getComputedStyle(document.documentElement);
  const g = (v, fb) => cs.getPropertyValue(v).trim() || fb;
  return {
    well: g("--cu-sunken", "#0c0d23"),
    accent: g("--cu-accent", "#b494ff"),
    warn: g("--cu-warn", "#ffd166"),
    dim: g("--cu-ink-dim", "#6f6d9b"),
    grid: g("--cu-edge", "#2a2a57"),
  };
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
  const ctx = canvas.getContext("2d");
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  return ctx;
}

function drawSpline(ctx, state, frameIdx, cssW, cssH, sel, tool) {
  const t = plotColours();
  const cw = state.canvas.w || 512;
  const ch = state.canvas.h || 512;
  const sx = cssW / cw;
  const sy = cssH / ch;

  ctx.fillStyle = t.well;
  ctx.fillRect(0, 0, cssW, cssH);

  const tile = 24;
  for (let ty = 0; ty < cssH; ty += tile) {
    for (let tx = 0; tx < cssW; tx += tile) {
      ctx.fillStyle = (((tx + ty) / tile) % 2 === 0) ? "#15151d" : "#1a1a24";
      ctx.fillRect(tx, ty, Math.min(tile, cssW - tx), Math.min(tile, cssH - ty));
    }
  }

  const f = ensureFrameArrays(state, frameIdx);
  const pts = f.points;

  if (!pts.length) {
    ctx.fillStyle = "rgba(148,158,190,0.55)";
    ctx.font = "26px system-ui,sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("✎", cssW / 2, cssH / 2 - 20);
    ctx.fillStyle = "rgba(168,178,208,0.78)";
    ctx.font = "600 13px system-ui,sans-serif";
    ctx.fillText("Click to place roto points", cssW / 2, cssH / 2 + 2);
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    return { count: 0 };
  }

  ctx.strokeStyle = t.accent;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i];
    const px = p[0] * sx;
    const py = p[1] * sy;
    if (i === 0) ctx.moveTo(px, py);
    else {
      const prev = pts[i - 1];
      const o = f.out[i - 1] || prev;
      const inn = f.in[i] || p;
      ctx.bezierCurveTo(
        o[0] * sx, o[1] * sy,
        inn[0] * sx, inn[1] * sy,
        px, py,
      );
    }
  }
  if (state.closed && pts.length > 2) {
    const last = pts[pts.length - 1];
    const o = f.out[pts.length - 1] || last;
    const inn = f.in[0] || pts[0];
    ctx.bezierCurveTo(
      o[0] * sx, o[1] * sy,
      inn[0] * sx, inn[1] * sy,
      pts[0][0] * sx, pts[0][1] * sy,
    );
  }
  ctx.stroke();

  for (let i = 0; i < pts.length; i++) {
    const p = pts[i];
    const px = p[0] * sx;
    const py = p[1] * sy;
    const isSel = i === sel;
    ctx.fillStyle = isSel ? t.warn : t.accent;
    ctx.beginPath();
    ctx.arc(px, py, isSel ? 5 : 4, 0, Math.PI * 2);
    ctx.fill();
    if (isSel && tool === "select") {
      const inn = f.in[i] || p;
      const out = f.out[i] || p;
      ctx.strokeStyle = "rgba(255,212,121,0.5)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(px, py);
      ctx.lineTo(inn[0] * sx, inn[1] * sy);
      ctx.moveTo(px, py);
      ctx.lineTo(out[0] * sx, out[1] * sy);
      ctx.stroke();
      ctx.fillStyle = t.warn;
      for (const h of [inn, out]) {
        ctx.beginPath();
        ctx.arc(h[0] * sx, h[1] * sy, 3, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  return { count: pts.length };
}

function readoutText(state, frameIdx) {
  const f = frameOf(state, frameIdx);
  const n = f.points.length;
  const closed = state.closed ? "closed" : "open";
  return n ? `${n} point${n === 1 ? "" : "s"} · ${closed}` : `0 points · ${closed}`;
}

function canvasToModel(canvas, state, ev) {
  const r = canvas.getBoundingClientRect();
  const cw = state.canvas.w || 512;
  const ch = state.canvas.h || 512;
  const x = ((ev.clientX - r.left) / r.width) * cw;
  const y = ((ev.clientY - r.top) / r.height) * ch;
  return { x, y, sx: cw / r.width, sy: ch / r.height, cssW: r.width, cssH: r.height };
}

function hitTest(state, frameIdx, canvas, ev) {
  const f = frameOf(state, frameIdx);
  const { x, y, cssW, cssH } = canvasToModel(canvas, state, ev);
  let best = -1;
  let bestD = HIT_PX * HIT_PX;
  f.points.forEach((p, i) => {
    const d = (p[0] - x) ** 2 + (p[1] - y) ** 2;
    if (d < bestD) { bestD = d; best = i; }
  });
  return { idx: best, x, y, cssW, cssH };
}

function syncToWidget(node, state) {
  const w = widgetByName(node, "spline_state");
  if (w) {
    w.value = writeState(state);
    node.graph?.setDirtyCanvas?.(true, true);
  }
}

function hideStateWidget(node) {
  const stateWidget = widgetByName(node, "spline_state");
  if (!stateWidget) return;
  stateWidget.type = "hidden";
  stateWidget.computeSize = () => [0, -4];
  stateWidget.hidden = true;
  if (stateWidget.options) stateWidget.options.hidden = true;
  setTimeout(() => {
    const el = stateWidget.element || stateWidget.inputEl;
    if (el) {
      el.style.display = "none";
      const wrap = el.parentElement;
      if (wrap?.classList?.contains("dom-widget")) wrap.style.display = "none";
    }
  }, 0);
}

const PANEL_CHROME_H = 84;   // button, gaps, stage footer

function previewHeight(st, cssW) {
  const cw = st.work?.canvas?.w || 512;
  const ch = st.work?.canvas?.h || 512;
  return Math.max(80, Math.min(PREVIEW_MAX_H, Math.round(Math.max(1, cssW) * ch / cw)));
}

function paintPreview(st, node) {
  const canvas = st.previewCanvas;
  if (!canvas) return;
  const viewport = st.stageApi.el.querySelector(".c2c-ui-stage__viewport");
  const cssW = Math.max(1, viewport?.clientWidth || 300);
  // drawSpline scales x and y independently (w / canvas.w, h / canvas.h), so
  // the preview must have the roto canvas's own aspect, or a 512x512 frame
  // was squashed into a fixed 140 px band inside a square stage.
  const cw = st.work.canvas?.w || 512;
  const ch = st.work.canvas?.h || 512;
  const cssH = previewHeight(st, cssW);
  const drawW = Math.round(cssH * cw / ch);
  if (viewport) viewport.style.aspectRatio = `${cw} / ${ch}`;
  try {   // grow (never shrink) the node when the aspect needs more room
    const need = node.computeSize?.();
    // classic only: Nodes 2.0 sizes to content and treats size[1] as a minimum
    if (!globalThis.LiteGraph?.vueNodesMode && need && node.size && node.size[1] < need[1]) node.setSize([node.size[0], need[1]]);
  } catch (_e) { /* sizing is cosmetic */ }
  const ctx = setupCanvas(canvas, drawW, cssH);
  const info = drawSpline(ctx, st.work, st.work.currentFrame || 0, drawW, cssH, -1, "select");
  if (!info.count) {
    st.stageApi.setEmpty({
      title: "Roto spline",
      hint: "Open the editor to draw a spline mask",
    });
    st.readout.setText(readoutText(st.work, st.work.currentFrame || 0));
  } else {
    st.stageApi.setCanvas(canvas);
    st.stageApi.setFooter(readoutText(st.work, st.work.currentFrame || 0));
    st.readout.setText("");   // the stage footer already says it
  }
}

function openRotoEditor(node, st) {
  if (st.editorOpen) return;
  st.editorOpen = true;

  let work = cloneState(st.work);
  const original = cloneState(st.work);
  let frame = work.currentFrame || 0;
  let sel = -1;
  let tool = "select";
  let drag = null;
  const undoStack = [];
  const redoStack = [];
  let shell = null;
  let fieldUndoPending = false;

  const pushUndo = (snap) => {
    undoStack.push(snap);
    redoStack.length = 0;
    shell?.setDirty(true);
  };

  const centre = document.createElement("div");
  centre.style.cssText = "width:100%;height:100%;display:flex;align-items:center;justify-content:center;position:relative;";
  const editCanvas = document.createElement("canvas");
  editCanvas.style.cssText = "display:block;max-width:100%;max-height:100%;cursor:crosshair;touch-action:none;";
  centre.appendChild(editCanvas);

  const frameLabel = statusLine();
  const closedLine = statusLine();

  let xRow, yRow, featherRow, pointHint, pointFields;

  function syncFields() {
    const f = ensureFrameArrays(work, frame);
    const p = sel >= 0 ? f.points[sel] : null;
    if (pointHint) pointHint.style.display = p ? "none" : "";
    if (pointFields) pointFields.style.display = p ? "flex" : "none";
    const cw = work.canvas.w || 512;
    const ch = work.canvas.h || 512;
    if (xRow && p) {
      xRow.querySelector("input[type=range]").value = String(p[0]);
      xRow.querySelector("input[type=number]").value = String(Math.round(p[0] * 10) / 10);   // full precision cut off in the field
      xRow.querySelector("input[type=range]").max = String(cw);
      xRow.querySelector("input[type=number]").max = String(cw);
    }
    if (yRow && p) {
      yRow.querySelector("input[type=range]").value = String(p[1]);
      yRow.querySelector("input[type=number]").value = String(Math.round(p[1] * 10) / 10);   // full precision cut off in the field
      yRow.querySelector("input[type=range]").max = String(ch);
      yRow.querySelector("input[type=number]").max = String(ch);
    }
    if (featherRow && p) {
      const fv = f.feather[sel] ?? 0;
      featherRow.querySelector("input[type=range]").value = String(fv);
      featherRow.querySelector("input[type=number]").value = String(fv);
    }
    closedLine.setText(readoutText(work, frame));
  }

  function onField(field, val) {
    if (sel < 0) return;
    const f = ensureFrameArrays(work, frame);
    if (!fieldUndoPending) {
      pushUndo(writeState(work));
      fieldUndoPending = true;
    }
    if (field === "feather") {
      f.feather[sel] = val;
    } else {
      f.points[sel][field === "x" ? 0 : 1] = val;
      if (!f.in[sel]) f.in[sel] = [...f.points[sel]];
      if (!f.out[sel]) f.out[sel] = [...f.points[sel]];
    }
    repaint();
    syncFields();
  }

  function repaint() {
    const cssW = Math.max(320, centre.clientWidth || 640);
    const cssH = Math.max(240, centre.clientHeight || 480);
    const ctx = setupCanvas(editCanvas, cssW, cssH);
    const info = drawSpline(ctx, work, frame, cssW, cssH, sel, tool);
    frameLabel.setText(`frame ${frame + 1} / ${work.frames.length} · ${readoutText(work, frame)}`);
    if (!info.count) frameLabel.setText("No points — use Add or click the canvas");
    syncFields();
  }

  function stepFrame(d) {
    const n = work.frames.length;
    if (!n) return;
    frame = (frame + d + n) % n;
    work.currentFrame = frame;
    sel = -1;
    repaint();
  }

  pointHint = document.createElement("p");
  pointHint.className = "c2c-ui-status";
  pointHint.textContent = "Click a point to edit it";
  pointFields = document.createElement("div");
  pointFields.style.display = "none";
  pointFields.style.flexDirection = "column";
  pointFields.style.gap = "8px";
  xRow = sliderRow("x", { min: 0, max: work.canvas.w, step: 0.5, value: 0, onChange: (v) => onField("x", v) });
  yRow = sliderRow("y", { min: 0, max: work.canvas.h, step: 0.5, value: 0, onChange: (v) => onField("y", v) });
  featherRow = sliderRow("feather", { min: 0, max: 64, step: 0.5, value: 0, onChange: (v) => onField("feather", v) });
  pointFields.append(xRow, yRow, featherRow);

  const rightBody = document.createElement("div");
  rightBody.style.display = "flex";
  rightBody.style.flexDirection = "column";
  rightBody.style.gap = "8px";
  rightBody.appendChild(section("Selected point", pointHint, pointFields));
  rightBody.appendChild(closedLine.el);

  const tools = toolGrid([
    { value: "select", label: "Select", icon: "◎" },
    { value: "add", label: "Add", icon: "+" },
    { value: "delete", label: "Delete", icon: "−" },
  ], {
    value: tool,
    columns: 3,
    onChange: (v) => {
      tool = v;
      if (v === "delete" && sel >= 0) {
        pushUndo(writeState(work));
        const f = ensureFrameArrays(work, frame);
        f.points.splice(sel, 1);
        f.in.splice(sel, 1);
        f.out.splice(sel, 1);
        f.feather.splice(sel, 1);
        sel = -1;
        repaint();
      }
    },
  });

  const navRow = document.createElement("div");
  navRow.style.display = "flex";
  navRow.style.gap = "6px";
  navRow.append(
    button("‹", { onClick: () => stepFrame(-1) }),
    button("›", { onClick: () => stepFrame(1) }),
  );

  const toggleClosed = button(work.closed ? "Closed spline" : "Open spline", {
    onClick: () => {
      pushUndo(writeState(work));
      work.closed = !work.closed;
      const lbl = toggleClosed.querySelector("span:last-child") || toggleClosed;
      lbl.textContent = work.closed ? "Closed spline" : "Open spline";
      repaint();
    },
  });

  const clearFrame = button("Clear frame", {
    danger: true,
    onClick: () => {
      pushUndo(writeState(work));
      work.frames[frame] = { points: [], in: [], out: [], feather: [] };
      sel = -1;
      repaint();
    },
  });

  const leftBody = document.createElement("div");
  leftBody.style.display = "flex";
  leftBody.style.flexDirection = "column";
  leftBody.style.gap = "8px";
  leftBody.append(
    section("Tools", tools),
    section("Frame", navRow, frameLabel.el),
    toggleClosed,
    clearFrame,
  );

  const onDown = (ev) => {
    fieldUndoPending = false;
    const { idx, x, y } = hitTest(work, frame, editCanvas, ev);
    const f = ensureFrameArrays(work, frame);

    if (ev.button === 2) {
      if (idx >= 0) {
        pushUndo(writeState(work));
        f.points.splice(idx, 1);
        f.in.splice(idx, 1);
        f.out.splice(idx, 1);
        f.feather.splice(idx, 1);
        sel = -1;
        repaint();
      }
      ev.preventDefault();
      return;
    }

    if (tool === "add") {
      pushUndo(writeState(work));
      f.points.push([x, y]);
      f.in.push([x, y]);
      f.out.push([x, y]);
      f.feather.push(0);
      sel = f.points.length - 1;
      repaint();
      ev.preventDefault();
      return;
    }

    sel = idx;
    if (idx >= 0) {
      drag = { kind: "point", snap: writeState(work) };
      editCanvas.setPointerCapture?.(ev.pointerId);
    }
    repaint();
    ev.preventDefault();
  };

  const onMove = (ev) => {
    if (!drag || sel < 0) return;
    const { x, y } = hitTest(work, frame, editCanvas, ev);
    const f = ensureFrameArrays(work, frame);
    const dx = x - f.points[sel][0];
    const dy = y - f.points[sel][1];
    f.points[sel][0] = x;
    f.points[sel][1] = y;
    if (f.in[sel]) { f.in[sel][0] += dx; f.in[sel][1] += dy; }
    if (f.out[sel]) { f.out[sel][0] += dx; f.out[sel][1] += dy; }
    repaint();
    ev.preventDefault();
  };

  const onUp = () => {
    if (!drag) return;
    if (drag.snap) pushUndo(drag.snap);
    drag = null;
    repaint();
  };

  editCanvas.addEventListener("pointerdown", onDown);
  editCanvas.addEventListener("pointermove", onMove);
  editCanvas.addEventListener("pointerup", onUp);
  editCanvas.addEventListener("pointercancel", onUp);
  editCanvas.addEventListener("lostpointercapture", onUp);

  let resizeObs = null;
  if (typeof ResizeObserver !== "undefined") {
    resizeObs = new ResizeObserver(() => repaint());
    resizeObs.observe(centre);
  }

  shell = openEditor({
    title: "Roto spline editor",
    left: section("Spline", leftBody),
    right: rightBody,
    centre,
    hints: [
      "Add tool: click to place points",
      "Right-click removes the nearest point",
      "Ctrl+Z undo",
    ],
    onUndo: () => {
      if (!undoStack.length) return;
      redoStack.push(writeState(work));
      work = readState(undoStack.pop());
      frame = work.currentFrame || 0;
      sel = -1;
      repaint();
      syncFields();
    },
    onRedo: () => {
      if (!redoStack.length) return;
      undoStack.push(writeState(work));
      work = readState(redoStack.pop());
      frame = work.currentFrame || 0;
      sel = -1;
      repaint();
      syncFields();
    },
    onSave: () => {
      work.currentFrame = frame;
      st.work = cloneState(work);
      syncToWidget(node, st.work);
      paintPreview(st, node);
      return true;
    },
    onClose: () => {
      st.editorOpen = false;
      editCanvas.removeEventListener("pointerdown", onDown);
      editCanvas.removeEventListener("pointermove", onMove);
      editCanvas.removeEventListener("pointerup", onUp);
      editCanvas.removeEventListener("pointercancel", onUp);
      editCanvas.removeEventListener("lostpointercapture", onUp);
      try { resizeObs?.disconnect(); } catch (_e) { /* ignore */ }
      shell = null;
    },
  });

  requestAnimationFrame(() => repaint());
}

function createRotoWidget(node) {
  if (node[ST]) return node[ST];
  hideStateWidget(node);

  const wdg = widgetByName(node, "spline_state");
  const work = readState(wdg?.value);

  const root = document.createElement("div");
  root.style.display = "flex";
  root.style.flexDirection = "column";
  root.style.gap = "8px";
  root.style.width = "100%";

  const previewCanvas = document.createElement("canvas");
  previewCanvas.style.display = "block";

  const stageApi = stage({
    aspect: 1,
    empty: { title: "Roto spline", hint: "Open the editor to draw a spline mask" },
  });

  const readout = statusLine();

  const st = {
    work,
    previewCanvas,
    stageApi,
    readout,
    editorOpen: false,
    zoomOff: null,
    resizeObs: null,
  };
  node[ST] = st;

  const openBtn = button("Open roto editor", {
    primary: true,
    block: true,
    onClick: () => openRotoEditor(node, st),
  });

  root.append(openBtn, stageApi.el, readout.el);

  const panelWidget = mountPanel(node, "roto_canvas", root, { minHeight: PANEL_MIN });
  // The stage follows the roto canvas's aspect (see paintPreview), so the
  // panel's height must too - a fixed height squeezed the stage and the
  // canvas was stretched to fit it (classic renderer).
  panelWidget.computeSize = (w) => [w, PANEL_CHROME_H + previewHeight(st, (w || node.size[0]) - 24) + 8];
  panelWidget.onPanelResize = () => paintPreview(st, node);

  const viewport = stageApi.el.querySelector(".c2c-ui-stage__viewport");
  viewport.style.cursor = "pointer";
  viewport.addEventListener("click", () => openRotoEditor(node, st));

  st.zoomOff = installZoomRepaint(node, () => paintPreview(st, node), "_c2cNmRotoZoom");

  if (typeof ResizeObserver !== "undefined") {
    st.resizeObs = new ResizeObserver(() => paintPreview(st, node));
    st.resizeObs.observe(stageApi.el);
  }

  chainOnRemoved(node, () => {
    try { st.zoomOff?.(); } catch (_e) { /* ignore */ }
    try { st.resizeObs?.disconnect(); } catch (_e) { /* ignore */ }
    delete node[ST];
  });

  if (node.size[0] < NODE_MIN_W) node.size[0] = NODE_MIN_W;
  try {
    const sz = node.computeSize();
    node.setSize([Math.max(node.size?.[0] || 0, sz[0], NODE_MIN_W), Math.max(node.size?.[1] || 0, sz[1])]);
  } catch (_) {}

  paintPreview(st, node);
  return st;
}

app.registerExtension({
  name: "NukeMax.Roto",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_NAME) return;
    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      onCreated?.apply(this, arguments);
      try { createRotoWidget(this); } catch (e) { console.error("[NukeMax] roto widget failed", e); }
    };
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (...a) {
      const r = onConfigure?.apply(this, a);
      const st = this[ST];
      if (st) {
        const w = widgetByName(this, "spline_state");
        st.work = readState(w?.value);
        paintPreview(st, this);
      }
      return r;
    };
  },
});
