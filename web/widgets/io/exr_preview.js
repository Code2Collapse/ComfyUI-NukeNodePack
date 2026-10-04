// On-node EXR preview for the Nuke Read nodes.
//
// WHY A SERVER-RENDERED <img>: the browser cannot decode OpenEXR, and a
// scene-linear EXR shown without a display transform reads as almost black --
// which is the most common "my Read node is broken" report. So the server
// renders the frame (OpenImageIO) through an OCIO display/view and hands back
// PNG. See nukemax/nodes/io/exr_preview_server.py.
//
// WHY mountPanel: it renders on the Vue frontend AND the legacy canvas one.
// node.imgs / raw canvas draws do not render on Vue.

import { app } from "../../../../scripts/app.js";
import {
  mountPanel,
  button,
  selectRow,
  sliderRow,
  stage,
  statusLine,
} from "../../c2c_ui/index.js";

const TARGETS = new Set(["NukeMax_EXRSequenceLoad", "NukeMax_EXRChannelRouter"]);
const PATH_WIDGETS = ["path", "file_path", "filename", "exr_path"];
const PANEL_MIN = 200;
const HEADER_H = 92;
const NODE_MIN_W = 380;

function chainOnRemoved(node, cleanup) {
  const orig = node.onRemoved;
  node.onRemoved = function (...a) {
    try { cleanup?.(); } catch (_e) { /* ignore */ }
    return orig?.apply(this, a);
  };
}

function findPathWidget(node) {
  for (const name of PATH_WIDGETS) {
    const w = (node.widgets || []).find((x) => x.name === name);
    if (w) return w;
  }
  return null;
}

function attach(node) {
  if (node._nmExr) return node._nmExr;

  const state = {
    collapsed: false,
    info: null,
    seq: false,
    timer: 0,
    displaySel: null,
    viewSel: null,
    channelSel: null,
    expSlider: null,
    frameSlider: null,
  };
  node._nmExr = state;

  const root = document.createElement("div");
  root.style.display = "flex";
  root.style.flexDirection = "column";
  root.style.gap = "6px";
  root.style.width = "100%";
  root.style.height = "100%";

  const row1 = document.createElement("div");
  row1.style.display = "flex";
  row1.style.alignItems = "center";
  row1.style.gap = "6px";
  row1.style.flexWrap = "wrap";

  const titleLine = statusLine();
  titleLine.el.style.flex = "1 1 120px";
  titleLine.setText("no file");

  const collapseBtn = button("Hide", {
    onClick: () => {
      state.collapsed = !state.collapsed;
      const lbl = collapseBtn.querySelector("span:last-child") || collapseBtn;
      lbl.textContent = state.collapsed ? "Show" : "Hide";
      controlsRow.style.display = state.collapsed ? "none" : "flex";
      expRow.style.display = state.collapsed ? "none" : "flex";
      frameRow.style.display = (state.collapsed || !state.seq) ? "none" : "flex";
      stageApi.el.style.display = state.collapsed ? "none" : "";
      panelWidget.computeSize = computePanelSize;
      node.setSize?.(node.computeSize());
      node.setDirtyCanvas?.(true, true);
    },
  });
  collapseBtn.title = "Collapse the viewer. The node keeps working; this only frees canvas space.";

  row1.append(titleLine.el, collapseBtn);

  const controlsRow = document.createElement("div");
  controlsRow.style.display = "flex";
  controlsRow.style.flexDirection = "column";
  controlsRow.style.gap = "4px";

  const displayRow = document.createElement("div");
  displayRow.style.display = "flex";
  displayRow.style.gap = "4px";
  displayRow.style.flexWrap = "wrap";

  const viewRow = document.createElement("div");
  viewRow.style.display = "flex";
  viewRow.style.gap = "4px";
  viewRow.style.flexWrap = "wrap";

  const channelRowWrap = document.createElement("div");
  channelRowWrap.style.display = "flex";
  channelRowWrap.style.gap = "4px";
  channelRowWrap.style.flexWrap = "wrap";

  controlsRow.append(displayRow, viewRow, channelRowWrap);

  const expRow = document.createElement("div");
  expRow.style.display = "flex";
  expRow.style.alignItems = "center";
  expRow.style.gap = "6px";
  expRow.style.flexWrap = "wrap";

  let expSlider;
  const uploadBtn = button("Upload…", { onClick: () => openUpload(node, state) });
  uploadBtn.title =
    "Copy an EXR into ComfyUI's input folder and point this node at it. " +
    "Use this when the plate lives somewhere the server is not allowed to read.";
  expRow.append(uploadBtn);

  const frameRow = document.createElement("div");
  frameRow.style.display = "none";
  frameRow.style.alignItems = "center";
  frameRow.style.gap = "6px";
  frameRow.style.flexWrap = "wrap";

  const frameLabel = statusLine();
  frameLabel.el.style.flex = "0 0 auto";
  frameLabel.el.style.minWidth = "62px";
  let frameSlider;

  const msgLine = statusLine();

  const stageApi = stage({
    aspect: 16 / 9,
    empty: { title: "EXR preview", hint: "Set a path to preview" },
  });

  root.append(row1, controlsRow, expRow, frameRow, stageApi.el, msgLine.el);

  function computePanelSize(width) {
    if (state.collapsed) return [width, 30];
    const w = Math.max(120, (width || node.size?.[0] || 320) - 20);
    const ar = state.info?.width
      ? state.info.height / state.info.width : 9 / 16;
    return [width, Math.max(PANEL_MIN, HEADER_H + Math.round(w * ar))];
  }

  const panelWidget = mountPanel(node, "exr_preview", root, { minHeight: PANEL_MIN });
  panelWidget.computeSize = computePanelSize;

  const setMsg = (t) => {
    if (t) {
      // said once, in the stage - the line below repeated it word for word
      msgLine.setText("");
      msgLine.el.style.display = "none";
      stageApi.setEmpty({ title: "EXR preview", hint: t });
    } else {
      msgLine.setText("");
      msgLine.el.style.display = "none";
    }
  };

  const refresh = () => {
    const pw = findPathWidget(node);
    const p = (pw && pw.value ? String(pw.value) : "").trim();
    if (!p) { setMsg("Set a path to preview"); return; }
    const q = new URLSearchParams({
      path: p,
      frame: state.seq ? String(state.frameSlider?.querySelector("input")?.value ?? "0") : "-1",
      w: String(Math.max(160, Math.round((node.size?.[0] || 320) * 1.5))),
      display: state.displaySel?.querySelector("select")?.value || "",
      view: state.viewSel?.querySelector("select")?.value || "",
      exposure: state.expSlider?.querySelector("input[type=range]")?.value || "0",
      channel: state.channelSel?.querySelector("select")?.value || "",
    });
    const url = "/nukemax/exr/thumb?" + q.toString();
    const probe = new Image();
    probe.onload = () => {
      stageApi.setImage(url, state.info?.width || 0, state.info?.height || 0);
      setMsg("");
      node.setDirtyCanvas?.(true, true);
    };
    probe.onerror = async () => {
      try {
        const r = await fetch(url);
        const j = await r.json().catch(() => null);
        setMsg(j?.error || "Could not render this file.");
      } catch (_e) {
        setMsg("Could not reach the preview service.");
      }
    };
    probe.src = url;
  };

  const debounced = () => {
    if (state.timer) clearTimeout(state.timer);
    state.timer = setTimeout(refresh, 200);
  };

  const fillSelect = (rowEl, label, options, value, onChange, title) => {
    rowEl.innerHTML = "";
    const row = selectRow(label, {
      options: options.length ? options : [{ value: "", label: "—" }],
      value: value || "",
      onChange,
    });
    const sel = row.querySelector("select");
    if (sel && title) sel.title = title;
    rowEl.appendChild(row);
    return row;
  };

  const loadInfo = async () => {
    const pw = findPathWidget(node);
    const p = (pw && pw.value ? String(pw.value) : "").trim();
    if (!p) {
      setMsg("Set a path to preview");
      titleLine.setText("no file");
      return;
    }
    try {
      const r = await fetch("/nukemax/exr/info?path=" + encodeURIComponent(p));
      const j = await r.json();
      if (!j.ok) {
        setMsg(j.error || "Could not read that file.");
        return;
      }
      state.info = j;

      const bits = [j.name, j.width + "x" + j.height];
      if (j.compression) bits.push(j.compression);
      if (j.is_sequence) bits.push(j.first + "-" + j.last + " (" + j.count + "f)");
      titleLine.setText(bits.join("  ·  "));

      const groups = j.groups || ["rgba"];
      state.channelSel = fillSelect(
        channelRowWrap,
        "Channel",
        groups.map((g) => ({ value: g, label: g })),
        groups[0],
        refresh,
        "Which AOV to look at. Multilayer EXRs carry depth / normal / position / " +
        "cryptomatte beside the beauty pass; this previews one without re-rendering.",
      );

      const o = j.ocio || {};
      displayRow.innerHTML = "";
      viewRow.innerHTML = "";
      const fillViews = () => {
        const disp = state.displaySel?.querySelector("select")?.value || "";
        state.viewSel = fillSelect(
          viewRow,
          "View",
          (o.views[disp] || []).map((v) => ({ value: v, label: v })),
          o.default_view && (o.views[disp] || []).includes(o.default_view)
            ? o.default_view : (o.views[disp] || [])[0] || "",
          refresh,
          "OCIO view transform. This is the tonemap applied on top of the display — " +
          "'ACES 1.0 SDR-video' vs 'Un-tone-mapped' is the difference between a graded " +
          "look and raw linear values.",
        );
      };
      if (o.available) {
        state.displaySel = fillSelect(
          displayRow,
          "Display",
          o.displays.map((d) => ({ value: d, label: d })),
          o.default_display || o.displays[0] || "",
          () => { fillViews(); refresh(); },
          "OCIO display device. A scene-linear EXR has no built-in look; the display " +
          "says what monitor you are grading for (sRGB, Rec.709, P3...).",
        );
        fillViews();
      } else {
        state.displaySel = fillSelect(displayRow, "Display", [{ value: "", label: "no OCIO config" }], "");
        state.viewSel = fillSelect(viewRow, "View", [{ value: "", label: "no OCIO config" }], "");
        const dSel = state.displaySel.querySelector("select");
        const vSel = state.viewSel.querySelector("select");
        if (dSel) dSel.disabled = true;
        if (vSel) vSel.disabled = true;
      }

      if (!expSlider) {
        expSlider = sliderRow("EV", {
          min: -8, max: 8, step: 0.25, value: 0,
          format: (v) => `EV ${v.toFixed(1)}`,
          onChange: debounced,
        });
        const range = expSlider.querySelector("input[type=range]");
        if (range) {
          range.title =
            "Exposure in stops, applied in linear before the display transform — the same " +
            "thing you would do on a Nuke viewer to find detail hiding in the blacks or " +
            "check what is really clipped in the highlights.";
        }
        expRow.insertBefore(expSlider, uploadBtn);
        state.expSlider = expSlider;
      }

      state.seq = !!j.is_sequence;
      frameRow.style.display = state.seq ? "flex" : "none";
      if (state.seq) {
        if (!frameSlider) {
          frameSlider = sliderRow("Frame", {
            min: j.first, max: j.last, step: 1, value: j.first,
            format: (v) => `frame ${Math.round(v)}`,
            onChange: (v) => {
              frameLabel.setText(`frame ${Math.round(v)}`);
              debounced();
            },
          });
          const fr = frameSlider.querySelector("input[type=range]");
          if (fr) {
            fr.title = "Scrub the detected sequence. This previews frames only; it does not " +
              "change which frames the node loads (use start_frame / end_frame).";
          }
          frameRow.append(frameLabel.el, frameSlider);
          state.frameSlider = frameSlider;
        } else {
          const range = frameSlider.querySelector("input[type=range]");
          const num = frameSlider.querySelector("input[type=number]");
          if (range) { range.min = String(j.first); range.max = String(j.last); range.value = String(j.first); }
          if (num) { num.min = String(j.first); num.max = String(j.last); num.value = String(j.first); }
          frameLabel.setText("frame " + j.first);
        }
      }

      node.setSize?.(node.computeSize());
      refresh();
    } catch (_e) {
      setMsg("Could not reach the preview service.");
    }
  };

  state.refresh = refresh;
  state.loadInfo = loadInfo;

  const pw = findPathWidget(node);
  if (pw) {
    const orig = pw.callback;
    pw.callback = function (...a) {
      const r = orig ? orig.apply(this, a) : undefined;
      loadInfo();
      return r;
    };
  }

  chainOnRemoved(node, () => {
    if (state.timer) clearTimeout(state.timer);
    delete node._nmExr;
  });

  if (node.size[0] < NODE_MIN_W) node.size[0] = NODE_MIN_W;
  setTimeout(loadInfo, 50);
  return state;
}

function openUpload(node, state) {
  const inp = document.createElement("input");
  inp.type = "file";
  inp.accept = ".exr,.png,.jpg,.jpeg,.tif,.tiff,.hdr,.dpx";
    inp.onchange = async () => {
    const f = inp.files && inp.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f, f.name);
    try {
      const r = await fetch("/nukemax/exr/upload", { method: "POST", body: fd });
      const j = await r.json();
      if (!j.ok) return;
      const pw = findPathWidget(node);
      if (pw) { pw.value = j.path; pw.callback?.(j.path); }
      state.loadInfo?.();
    } catch (_e) { /* upload failed */ }
  };
  inp.click();
}

app.registerExtension({
  name: "NukeMax.EXRPreview",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!TARGETS.has(nodeData.name)) return;
    const orig = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = orig?.apply(this, arguments);
      try { attach(this); } catch (e) { console.error("[NukeMax] EXR preview:", e); }
      return r;
    };
  },
});
