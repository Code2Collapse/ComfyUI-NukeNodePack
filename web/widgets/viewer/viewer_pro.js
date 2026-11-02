// viewer_pro.js — the panel of NukeMax Viewer Pro (owner Rev 3 Part 19.12; ledger L9.80 slice 7a).
//
// VIEW ONLY. Everything here changes what you SEE: the IMAGE output stays the input. The view settings live in
// node.properties (saved with the workflow, never sent to the backend, never re-run the graph). "Apply view to output"
// is the one explicit way to bake exposure / gamma / gain into the output: it copies them into the node's widgets and
// turns apply_view_adjustment on; the badge then says APPLIED.
//
// Frames come from the run's frame store (keyed routes): float16 proxies for display (a bounded cache of 64), exact
// full-resolution values on click (/nukemax/viewer/sample). Wheel = zoom at the cursor, drag = pan, double-click = fit.

import { app } from "../../../../scripts/app.js";
import { cssVar } from "../_nukemax_theme.js";
import {
    CHANNELS, FALSE_BANDS, LRU, actual, defaults, difference, fit, fmt, halfToFloat, heatmap, measure, overlays,
    renderView, timecode, toImage,
    vectorscope, waveform, zoomAt,
} from "./viewer_pro_core.js";

const TYPE = "NukeMax_ViewerPro";

/** Nodes 2.0 sizes a node from its content: an explicit setSize there only adds blank space under the widgets. */
function vueNodes() {
    try {
        return !!(app.extensionManager?.setting?.get?.("Comfy.VueNodes.Enabled") ?? app.ui?.settings?.getSettingValue?.("Comfy.VueNodes.Enabled"));
    } catch (e) {
        return false;
    }
}
const PROP = "nukemax_viewer_pro";
const STYLE_ID = "nukemax-viewer-pro-v1";
const CSS = `
.nmvp { display:flex; flex-direction:column; gap:4px; height:100%; box-sizing:border-box; padding:4px; min-width:0;
  font:11px/1.3 sans-serif; color:${cssVar("text")}; user-select:none; }
.nmvp-row { display:flex; align-items:center; gap:4px; flex-wrap:nowrap; min-width:0; flex:none; }
.nmvp button, .nmvp select { height:20px; padding:0 6px; font:inherit; color:${cssVar("text")}; cursor:pointer;
  background:${cssVar("well")}; border:1px solid ${cssVar("border")}; border-radius:4px; }
.nmvp button:hover { border-color:${cssVar("accent")}; }
.nmvp select { max-width:132px; min-width:0; flex:0 1 auto; text-overflow:ellipsis; overflow:hidden; }
.nmvp button[aria-pressed="true"] { border-color:${cssVar("accent")}; color:${cssVar("fg")};
  background:color-mix(in srgb, ${cssVar("accent")} 28%, ${cssVar("well")}); }
.nmvp-num { display:flex; align-items:center; gap:3px; min-width:0; flex:1 1 0; }
.nmvp-num input[type=range] { flex:1 1 auto; min-width:30px; height:14px; }
.nmvp-num span { min-width:34px; text-align:right; font-variant-numeric:tabular-nums; color:${cssVar("dim")}; }
.nmvp-num .nmvp-lbl { min-width:28px; text-align:left; color:${cssVar("text")}; }
.nmvp-spacer { flex:1 1 auto; }
.nmvp-view { position:relative; flex:1 1 auto; min-height:120px; overflow:hidden; border-radius:4px;
  background:${cssVar("bg")}; border:1px solid ${cssVar("border")}; cursor:crosshair; }
.nmvp-view canvas { position:absolute; inset:0; width:100%; height:100%; }
.nmvp-probe { position:absolute; left:6px; bottom:4px; font:11px/1.2 monospace; color:#e8e8e8;
  text-shadow:0 0 3px #000, 0 0 2px #000; pointer-events:none; white-space:pre; }
.nmvp-zoom { position:absolute; right:6px; top:4px; font:11px monospace; color:#e8e8e8; text-shadow:0 0 3px #000;
  pointer-events:none; }
.nmvp-empty { position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
  color:${cssVar("dim")}; text-align:center; padding:12px; }
.nmvp-time { font-variant-numeric:tabular-nums; color:${cssVar("dim")}; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; min-width:0; }
.nmvp-scrub { flex:1 1 auto; min-width:40px; }
.nmvp-badge { padding:1px 6px; border-radius:8px; font-size:10px; border:1px solid ${cssVar("border")};
  white-space:nowrap; }
.nmvp-badge.view { color:${cssVar("ok")}; } .nmvp-badge.applied { color:${cssVar("warn")};
  border-color:${cssVar("warn")}; }
.nmvp-scope { position:relative; flex:none; height:118px; border-radius:4px; overflow:hidden;
  background:#0b0b0e; border:1px solid ${cssVar("border")}; }
.nmvp-scope canvas { position:absolute; inset:0; width:100%; height:100%; }
.nmvp-legend { display:flex; gap:2px; flex-wrap:wrap; flex:none; }
.nmvp-legend span { padding:0 4px; border-radius:3px; font-size:9px; color:#111; }
.nmvp-region { position:absolute; border:1px dashed #ffd166; pointer-events:none; display:none; }
.nmvp-insp { flex:none; color:${cssVar("dim")}; }
.nmvp-insp summary { cursor:pointer; color:${cssVar("text")}; }
.nmvp-insp-body { max-height:104px; overflow:auto; }
.nmvp-insp table { border-collapse:collapse; width:100%; font:10px/1.35 monospace; }
.nmvp-insp td { padding:1px 4px; vertical-align:top; border-top:1px solid ${cssVar("border")}; word-break:break-all; }
.nmvp-insp td:first-child { color:${cssVar("text")}; white-space:nowrap; width:1%; }
.nmvp-info { color:${cssVar("dim")}; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:0;
  flex:1 1 auto; }
`;

function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const s = document.createElement("style");
    s.id = STYLE_ID;
    s.textContent = CSS;
    document.head.appendChild(s);
}

function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
}

function btn(label, title, onClick) {
    const b = el("button", "", label);
    b.title = title;
    b.addEventListener("click", (e) => { e.stopPropagation(); onClick(e); });
    return b;
}

function slider(label, min, max, step, get, set) {
    const wrap = el("label", "nmvp-num");
    const r = document.createElement("input");
    Object.assign(r, { type: "range", min, max, step });
    const v = el("span");
    wrap.append(el("span", "nmvp-lbl", label), r, v);
    const show = () => { r.value = get(); v.textContent = Number(get()).toFixed(2); };
    r.addEventListener("input", () => { set(parseFloat(r.value)); v.textContent = Number(r.value).toFixed(2); });
    r.addEventListener("pointerdown", (e) => e.stopPropagation());
    return { wrap, show };
}

class ViewerPro {
    constructor(node) {
        this.node = node;
        this.o = Object.assign(defaults(), node.properties?.[PROP] || {});
        this.cache = new LRU(64);
        this.idx = null;
        this.frame = 0;
        this.view = null;
        this.autoFit = true;          // re-fit on resize until the user zooms or pans (a hidden node measured 1 px)
        this.playing = null;
        this.loop = true;
        this.build();
    }

    save() {
        this.node.properties = this.node.properties || {};
        const { lut, ...keep } = this.o;                                 // the baked LUT is fetched, never saved
        this.node.properties[PROP] = keep;
    }

    build() {
        ensureStyle();
        const root = (this.root = el("div", "nmvp"));
        for (const ev of ["pointerdown", "wheel", "dblclick", "keydown"]) root.addEventListener(ev, (e) => e.stopPropagation());
        // row 1: view geometry + channels
        const r1 = el("div", "nmvp-row");
        r1.append(btn("Fit", "Fit the frame (double-click the view)", () => this.fitView()),
            btn("1:1", "100%: one source pixel per screen pixel", () => this.actualView()),
            btn("−", "Zoom out", () => this.zoomBy(1 / 1.25)), btn("+", "Zoom in", () => this.zoomBy(1.25)));
        this.chBtns = {};
        for (const c of CHANNELS) {
            const b = btn(c === "luma" ? "L" : c.toUpperCase(), `Show ${c === "rgb" ? "colour" : c}`, () => this.setO({ channel: c }));
            this.chBtns[c] = b;
            r1.append(b);
        }
        this.checkerBtn = btn("▦", "Alpha over a checkerboard", () => this.setO({ checker: !this.o.checker }));
        this.displaySel = el("select");
        for (const d of ["sRGB", "raw"]) this.displaySel.append(Object.assign(el("option", "", d), { value: d }));
        this.displaySel.title = "Display transform (OCIO display / view arrives with the OCIO Player)";
        this.displaySel.addEventListener("change", () => { this.pickDisplay(this.displaySel.value);
            this.displaySel.title = this.displaySel.selectedOptions[0]?.textContent || ""; });
        this.displaySel.addEventListener("pointerdown", (e) => e.stopPropagation());
        r1.append(this.checkerBtn, this.displaySel);
        // 7b: scopes and measuring overlays (all view only)
        const rt = el("div", "nmvp-row");
        this.scopeSel = el("select");
        for (const [v, t] of [["none", "no scope"], ["histogram", "histogram"], ["waveform", "luma waveform"],
            ["parade", "RGB parade"], ["vectorscope", "vectorscope"], ["stops", "exposure (stops)"]]) {
            this.scopeSel.append(Object.assign(el("option", "", t), { value: v }));
        }
        this.scopeSel.title = "Scope of the frame as displayed (exposure and display transform included)";
        this.scopeSel.addEventListener("change", () => this.setO({ scope: this.scopeSel.value }));
        this.scopeSel.addEventListener("pointerdown", (e) => e.stopPropagation());
        this.fcBtn = btn("False colour", "Scene-linear luma in stops from 18 % grey", () => this.setO({ falseColour: !this.o.falseColour }));
        this.zebraBtn = btn("Zebra", "Stripes where the displayed value reaches 95 %", () => this.setO({ zebraOn: !this.o.zebraOn }));
        this.peakBtn = btn("Peaking", "Focus peaking: displayed edges in green", () => this.setO({ peakingOn: !this.o.peakingOn }));
        rt.append(this.scopeSel, this.fcBtn, this.zebraBtn, this.peakBtn);
        // 7c: compare A / B, the EXR layer shown, sound
        const rc = (this.compareRow = el("div", "nmvp-row"));
        this.cmpSel = el("select");
        for (const [v, t] of [["a", "A"], ["b", "B"], ["split", "A | B wipe"], ["difference", "difference"],
            ["heatmap", "difference heatmap"], ["blink", "blink A / B"]]) {
            this.cmpSel.append(Object.assign(el("option", "", t), { value: v }));
        }
        this.cmpSel.title = "Compare A with B (connect image_b)";
        this.cmpSel.addEventListener("change", () => { this.setO({ compare: this.cmpSel.value }); this.show(this.frame); this.blink(); });
        this.cmpSel.addEventListener("pointerdown", (e) => e.stopPropagation());
        this.sWipe = slider("wipe", 0, 1, 0.01, () => this.o.wipe ?? 0.5, (v) => this.setO({ wipe: v }, false));
        this.layerSel = el("select");
        this.layerSel.title = "The EXR layer shown (connect Read EXR Pro's passes)";
        this.layerSel.addEventListener("change", () => { this.setO({ layer: this.layerSel.value }); this.show(this.frame); });
        this.layerSel.addEventListener("pointerdown", (e) => e.stopPropagation());
        this.muteBtn = btn("🔊", "Sound on / off (a connected video or audio)", () => { this.setO({ mute: !this.o.mute }); this.syncAudio(); });
        rc.append(this.cmpSel, this.sWipe.wrap, this.layerSel, this.muteBtn);
        // row 2: view exposure / gamma / gain (view only) + apply
        const r2 = el("div", "nmvp-row");
        this.sExp = slider("exp", -10, 10, 0.1, () => this.o.exposure, (v) => this.setO({ exposure: v }, false));
        this.sGam = slider("γ", 0.2, 3, 0.01, () => this.o.gamma, (v) => this.setO({ gamma: v }, false));
        this.sGain = slider("gain", 0, 8, 0.01, () => this.o.gain, (v) => this.setO({ gain: v }, false));
        this.badge = el("span", "nmvp-badge view", "VIEW ONLY");
        r2.append(this.sExp.wrap, this.sGam.wrap, this.sGain.wrap);
        // the one explicit way from the view to the graph, on its own row with the state it produces
        const r2b = el("div", "nmvp-row");
        r2b.append(btn("⟲ reset view", "Reset exposure / gamma / gain", () => this.setO({ exposure: 0, gamma: 1, gain: 1 })),
            el("span", "nmvp-spacer"), this.badge,
            btn("Apply view to output", "Bake this exposure / gamma / gain into the node's output (an explicit step: "
                + "the output is the input until you press this)", () => this.applyToOutput()));
        // the view
        const view = (this.viewEl = el("div", "nmvp-view"));
        // Nodes 2.0 hands the wheel to an element only when it carries data-capture-wheel (as ComfyUI's own Load3D
        // and text areas do); without it the canvas zoomed instead of the picture (L9.80 slice 7a, live)
        view.setAttribute("data-capture-wheel", "true");
        // ... and only while it CONTAINS the focused element (fe 1.53 wheelCapturedByFocusedElement): focusable, focused
        // on pointer-down, and on hover unless the user is typing somewhere else
        view.tabIndex = -1;
        view.style.outline = "none";
        view.addEventListener("pointerenter", () => {
            const a = document.activeElement;
            const typing = a && a !== document.body && (a.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName));
            if (!typing) view.focus({ preventScroll: true });
        });
        this.canvas = document.createElement("canvas");
        this.probe = el("div", "nmvp-probe");
        this.zoomLbl = el("div", "nmvp-zoom");
        this.empty = el("div", "nmvp-empty", "Run the graph to view the image.");
        this.regionEl = el("div", "nmvp-region");
        view.append(this.canvas, this.regionEl, this.probe, this.zoomLbl, this.empty);
        this.wireView();
        // transport
        const r3 = el("div", "nmvp-row");
        this.playBtn = btn("▶", "Play / pause", () => this.togglePlay());
        this.loopBtn = btn("⟳", "Loop", () => { this.loop = !this.loop; this.paint(); });
        this.scrub = Object.assign(document.createElement("input"), { type: "range", min: 0, max: 0, step: 1, value: 0 });
        this.scrub.className = "nmvp-scrub";
        this.scrub.addEventListener("input", () => this.show(parseInt(this.scrub.value, 10)));
        this.scrub.addEventListener("pointerdown", (e) => e.stopPropagation());
        r3.append(btn("⏮", "First frame", () => this.show(0)), btn("◀", "Previous frame", () => this.step(-1)),
            this.playBtn, btn("▶|", "Next frame", () => this.step(1)),
            btn("⏭", "Last frame", () => this.show((this.idx?.frames || 1) - 1)), this.loopBtn, this.scrub);
        this.time = el("div", "nmvp-time");
        this.info = el("div", "nmvp-info");
        const r4 = el("div", "nmvp-row");
        r4.append(this.time);
        const r5 = el("div", "nmvp-row");
        r5.append(this.info);
        this.scopeBox = el("div", "nmvp-scope");
        this.scopeCanvas = document.createElement("canvas");
        this.scopeBox.append(this.scopeCanvas);
        this.legend = el("div", "nmvp-legend");
        for (const [, rgb, label] of FALSE_BANDS) {
            const sp = el("span", "", label);
            sp.style.background = `rgb(${rgb.join(",")})`;
            this.legend.append(sp);
        }
        this.meas = el("div", "nmvp-info");
        const r6 = el("div", "nmvp-row");
        r6.append(this.meas);
        this.insp = el("details", "nmvp-insp");
        this.insp.append(el("summary", "", "EXR inspector"));
        this.inspBody = el("table");
        // bounded and scrolled: expanded, it takes room from the view instead of spilling past the node (classic)
        const inspWrap = el("div", "nmvp-insp-body");
        inspWrap.append(this.inspBody);
        inspWrap.addEventListener("wheel", (e) => e.stopPropagation(), { passive: true });
        inspWrap.setAttribute("data-capture-wheel", "true");
        this.insp.append(inspWrap);
        this.insp.addEventListener("toggle", () => this.node.setDirtyCanvas?.(true, true));
        root.append(r1, rt, rc, r2, r2b, view, this.legend, this.scopeBox, r3, r4, r5, r6, this.insp);
        new ResizeObserver(() => this.redraw()).observe(view);
        // Nodes 2.0 gives the widget container its min height but no explicit height, so height:100% resolved to the
        // content and left the rest empty under the panel: follow the container's real height instead
        const follow = () => {
            const par = root.parentElement;
            if (!par) return;
            const h = par.clientHeight;
            if (h > 0 && Math.abs(root.offsetHeight - h) > 2) root.style.height = `${h}px`;
        };
        new ResizeObserver(follow).observe(root);
        requestAnimationFrame(() => { if (root.parentElement) new ResizeObserver(follow).observe(root.parentElement); follow(); });
        this.paint();
    }

    wireView() {
        const v = this.viewEl;
        let drag = null;
        v.addEventListener("wheel", (e) => {
            e.preventDefault();
            e.stopPropagation();
            const r = v.getBoundingClientRect();
            this.zoomBy(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
        }, { passive: false });
        v.addEventListener("pointerdown", (e) => {
            e.stopPropagation();
            v.focus({ preventScroll: true });
            drag = { x: e.clientX, y: e.clientY, moved: false, vx: this.view?.x, vy: this.view?.y, region: e.shiftKey };
            if (!e.shiftKey) this.regionEl.style.display = "none";           // a plain click clears the region box
            v.setPointerCapture?.(e.pointerId);
        });
        v.addEventListener("pointermove", (e) => {
            const r = v.getBoundingClientRect();
            if (drag && this.view) {
                const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
                if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
                if (drag.moved && drag.region) {
                    const r0 = v.getBoundingClientRect();
                    const x0 = Math.min(drag.x, e.clientX) - r0.left, y0 = Math.min(drag.y, e.clientY) - r0.top;
                    Object.assign(this.regionEl.style, { display: "block", left: `${x0}px`, top: `${y0}px`,
                        width: `${Math.abs(dx)}px`, height: `${Math.abs(dy)}px` });
                    return;
                }
                if (drag.moved) { this.autoFit = false; this.view.x = drag.vx + dx; this.view.y = drag.vy + dy; this.redraw(); return; }
            }
            this.hover(e.clientX - r.left, e.clientY - r.top);
        });
        v.addEventListener("pointerup", (e) => {
            const r = v.getBoundingClientRect();
            if (drag && drag.region && drag.moved) {
                this.sampleRegion(drag.x - r.left, drag.y - r.top, e.clientX - r.left, e.clientY - r.top);
            } else if (drag && !drag.moved) this.sampleAt(e.clientX - r.left, e.clientY - r.top);
            drag = null;
        });
        v.addEventListener("dblclick", (e) => { e.stopPropagation(); this.fitView(); });
    }

    setO(patch, repaintButtons = true) {
        Object.assign(this.o, patch);
        this.save();
        this.redraw();
        if (repaintButtons) this.paint();
    }

    paint() {
        for (const [c, b] of Object.entries(this.chBtns)) b.setAttribute("aria-pressed", String(this.o.channel === c));
        this.checkerBtn.setAttribute("aria-pressed", String(!!this.o.checker));
        this.loopBtn.setAttribute("aria-pressed", String(this.loop));
        this.displaySel.value = this.o.display;
        this.scopeSel.value = this.o.scope || "none";
        const hasB = !!this.idx?.b;
        for (const op of this.cmpSel.options) op.disabled = op.value !== "a" && !hasB;
        this.cmpSel.value = hasB ? (this.o.compare || "a") : "a";
        this.sWipe.wrap.style.display = this.cmpSel.value === "split" ? "" : "none";
        this.sWipe.show();
        this.layerSel.style.display = (this.idx?.layers?.length) ? "" : "none";
        this.muteBtn.style.display = this.idx?.audio ? "" : "none";
        this.muteBtn.textContent = this.o.mute ? "🔇" : "🔊";
        this.compareRow.style.display = (hasB || this.idx?.layers?.length || this.idx?.audio) ? "" : "none";
        this.fcBtn.setAttribute("aria-pressed", String(!!this.o.falseColour));
        this.zebraBtn.setAttribute("aria-pressed", String(!!this.o.zebraOn));
        this.peakBtn.setAttribute("aria-pressed", String(!!this.o.peakingOn));
        const scopeOn = !!(this.o.scope && this.o.scope !== "none");
        this.scopeBox.style.display = scopeOn ? "" : "none";
        // a scope must not shrink the picture: the node grows by the scope's height when it opens
        if (scopeOn !== this.scopeWasOn) {
            this.scopeWasOn = scopeOn;
            this.scopeExtra = scopeOn ? 122 : 0;                              // read by the widget's getMinHeight
            const n = this.node;
            if (scopeOn && n?.size && !vueNodes()) requestAnimationFrame(() => n.setSize?.([n.size[0], Math.max(n.size[1], n.computeSize()[1])]));
        }
        this.legend.style.display = this.o.falseColour ? "" : "none";
        this.sExp.show(); this.sGam.show(); this.sGain.show();
        const applied = !!this.widget("apply_view_adjustment")?.value;
        this.badge.textContent = applied ? "APPLIED" : "VIEW ONLY";
        this.badge.className = `nmvp-badge ${applied ? "applied" : "view"}`;
        this.badge.title = applied ? "exposure / gamma / gain are applied to the node's output"
            : "the output is the input, untouched";
        this.playBtn.textContent = this.playing ? "⏸" : "▶";
    }

    widget(name) { return (this.node.widgets || []).find((w) => w.name === name); }

    applyToOutput() {
        const set = (n, v) => { const w = this.widget(n); if (w) { w.value = v; w.callback?.(v); } };
        set("exposure", this.o.exposure); set("gamma", this.o.gamma); set("gain", this.o.gain);
        set("apply_view_adjustment", true);
        this.paint();
        this.node.setDirtyCanvas?.(true, true);
    }

    // ---- data ---------------------------------------------------------------------------------------------------
    async load(msg) {
        this.stop();
        this.cache.clear();
        const r = await fetch(`/nukemax/viewer/index?key=${encodeURIComponent(msg.key)}`);
        const j = await r.json();
        if (!r.ok) { this.empty.textContent = j.error || "The viewer store is gone - run the node again."; this.empty.style.display = ""; return; }
        this.idx = j;
        this.empty.style.display = "none";
        this.scrub.max = String(Math.max(0, j.frames - 1));
        this.frame = Math.min(this.frame, j.frames - 1);
        this.view = null;
        this.layerSel.replaceChildren(Object.assign(el("option", "", "beauty (A)"), { value: "a" }),
            ...(j.layers || []).map((l) => Object.assign(el("option", "", `${l.key} (${l.kind || "layer"})`), { value: l.which })));
        this.layerSel.value = (j.layers || []).some((l) => l.which === this.o.layer) ? this.o.layer : "a";
        this.audioEl?.pause();
        this.audioEl = j.audio ? new Audio(`/nukemax/viewer/audio?key=${encodeURIComponent(j.key)}`) : null;
        this.fillInspector(j.inspector || {});
        this.loadOcio();
        this.paint();
        await this.show(this.frame);
    }

    async frameData(i, which = "a") {
        const ck = `${which}:${i}`;
        const hit = this.cache.get(ck);
        if (hit) return hit;
        const r = await fetch(`/nukemax/viewer/frame?key=${encodeURIComponent(this.idx.key)}&i=${i}&which=${which}`);
        if (!r.ok) throw new Error((await r.json()).error || `frame ${i}`);
        const data = halfToFloat(new Uint16Array(await r.arrayBuffer()));
        this.cache.set(ck, data);
        return data;
    }

    sideOf(which) {
        if (which === "b") return this.idx.b;
        if (which && which !== "a") return (this.idx.layers || []).find((l) => l.which === which) || this.idx.a;
        return this.idx.a;
    }

    async show(i) {
        if (!this.idx) return;
        const n = this.idx.frames;
        this.frame = Math.max(0, Math.min(n - 1, i | 0));
        this.scrub.value = String(this.frame);
        try {
            const lay = this.o.layer && (this.idx.layers || []).some((l) => l.which === this.o.layer) ? this.o.layer : "a";
            this.curWhich = lay;
            this.cur = await this.frameData(this.frame, lay);
            const needB = this.idx.b && (this.o.compare || "a") !== "a";
            this.curB = needB ? await this.frameData(Math.min(this.frame, this.idx.b.frames - 1), "b") : null;
        } catch (e) {
            this.empty.textContent = String(e.message || e);
            this.empty.style.display = "";
            return;
        }
        this.redraw();
        this.updateTime();
        if (!this.playing) this.syncAudio();
        for (let k = 1; k <= 3 && this.frame + k < n; k++) this.frameData(this.frame + k, this.curWhich || "a").catch(() => {});
    }

    step(d) {
        if (!this.idx) return;
        const n = this.idx.frames;
        let f = this.frame + d;
        if (f >= n) f = this.loop ? 0 : n - 1;
        if (f < 0) f = this.loop ? n - 1 : 0;
        this.show(f);
    }

    togglePlay() { this.playing ? this.stop() : this.play(); }

    play() {
        if (!this.idx || this.idx.frames < 2) return;
        const fps = this.idx.fps || 24;
        this.playing = setInterval(() => {
            if (!this.loop && this.frame >= this.idx.frames - 1) { this.stop(); return; }
            this.step(1);
        }, 1000 / fps);
        this.paint();
        this.syncAudio(true);
    }

    stop() {
        if (this.playing) clearInterval(this.playing);
        this.playing = null;
        this.audioEl?.pause();
        if (this.playBtn) this.paint();
    }

    updateTime() {
        const ix = this.idx;
        if (!ix) return;
        const num = ix.numbers?.[this.frame] ?? this.frame;
        const fps = ix.fps || 24;
        this.time.textContent = `frame ${num} (${this.frame + 1}/${ix.frames}) | ${timecode(this.frame, fps)} | `
            + `${+fps.toFixed(3)} fps | ${(ix.frames / fps).toFixed(2)} s`;
        const st = ix.a?.stats?.[this.frame];
        const a = ix.a || {};
        this.info.textContent = `${a.width}×${a.height} (proxy ${a.proxy?.[0]}×${a.proxy?.[1]})`
            + (st ? ` | max ${fmt(Math.max(...st.max.slice(0, 3)))} min ${fmt(Math.min(...st.min.slice(0, 3)))}`
                + (st.above_1 ? ` | ${st.above_1} px > 1.0` : "") + (st.negative ? ` | ${st.negative} px < 0` : "") : "");
    }

    // ---- view ---------------------------------------------------------------------------------------------------
    fitView() {
        if (!this.idx) return;
        this.autoFit = true;
        const [bw, bh] = [this.viewEl.clientWidth, this.viewEl.clientHeight];
        const [pw, ph] = this.idx.a.proxy;
        this.view = fit(bw, bh, pw, ph);
        this.redraw();
    }

    actualView() {
        if (!this.idx) return;
        this.autoFit = false;
        const [bw, bh] = [this.viewEl.clientWidth, this.viewEl.clientHeight];
        const [pw, ph] = this.idx.a.proxy;
        this.view = actual(bw, bh, pw, ph, pw / this.idx.a.width);
        this.redraw();
    }

    zoomBy(f, px, py) {
        if (!this.view) this.fitView();
        this.autoFit = false;
        if (!this.view) return;
        const [bw, bh] = [this.viewEl.clientWidth, this.viewEl.clientHeight];
        this.view = zoomAt(this.view, f, px ?? bw / 2, py ?? bh / 2);
        this.redraw();
    }

    redraw() {
        if (!this.cur || !this.idx) return;
        const [pw, ph] = this.idx.a.proxy;
        const bw = Math.max(1, this.viewEl.clientWidth), bh = Math.max(1, this.viewEl.clientHeight);
        if (!this.view || (this.autoFit && (bw !== this.fitBox?.[0] || bh !== this.fitBox?.[1]))) {
            this.view = fit(bw, bh, pw, ph);
            this.fitBox = [bw, bh];
        }
        if (!this.off || this.off.width !== pw || this.off.height !== ph) {
            this.off = Object.assign(document.createElement("canvas"), { width: pw, height: ph });
            this.img = this.off.getContext("2d").createImageData(pw, ph);
        }
        const mode = this.curB ? (this.o.compare === "blink" ? (this.blinkB ? "b" : "a") : (this.o.compare || "a")) : "a";
        let base = this.cur, bdim = this.sideOf("b")?.proxy || [pw, ph];
        if (mode === "difference" || mode === "heatmap") base = difference(this.cur, this.curB, pw, ph, bdim[0], bdim[1]);
        if (mode === "heatmap") this.heatMax = heatmap(base, pw, ph, this.img.data).max;
        else renderView(base, pw, ph, this.o, this.img.data);
        this.shownMode = mode;
        if (mode === "a" && (this.o.falseColour || this.o.zebraOn || this.o.peakingOn)) {
            const shown = this.view.scale * (this.idx.a.width / pw) * (pw / this.idx.a.width);   // screen px per proxy px
            overlays(this.cur, pw, ph, { ...this.o, peakingWidth: shown < 1 ? Math.ceil(1 / shown) - 1 : 0 }, this.img.data);
        }
        this.off.getContext("2d").putImageData(this.img, 0, 0);
        const c = this.canvas;
        if (c.width !== bw || c.height !== bh) { c.width = bw; c.height = bh; }
        const g = c.getContext("2d");
        g.clearRect(0, 0, bw, bh);
        g.imageSmoothingEnabled = this.view.scale * (this.idx.a.width / pw) < 1.0;
        const dw = pw * this.view.scale, dh = ph * this.view.scale;
        if (mode === "b" || mode === "split") {
            // B at its own proxy size, drawn into A's rectangle (sizes may differ); split = A left of the wipe
            if (!this.offB || this.offB.width !== bdim[0] || this.offB.height !== bdim[1]) {
                this.offB = Object.assign(document.createElement("canvas"), { width: bdim[0], height: bdim[1] });
                this.imgB = this.offB.getContext("2d").createImageData(bdim[0], bdim[1]);
            }
            renderView(this.curB, bdim[0], bdim[1], this.o, this.imgB.data);
            this.offB.getContext("2d").putImageData(this.imgB, 0, 0);
            if (mode === "b") g.drawImage(this.offB, this.view.x, this.view.y, dw, dh);
            else {
                const cut = this.view.x + dw * (this.o.wipe ?? 0.5);
                g.drawImage(this.off, this.view.x, this.view.y, dw, dh);
                g.save(); g.beginPath(); g.rect(cut, 0, bw - cut, bh); g.clip();
                g.drawImage(this.offB, this.view.x, this.view.y, dw, dh); g.restore();
                g.fillStyle = "#ffd166"; g.fillRect(Math.round(cut), this.view.y, 1, dh);
            }
        } else g.drawImage(this.off, this.view.x, this.view.y, dw, dh);
        if (mode !== "a") { g.fillStyle = "#ffd166"; g.font = "11px monospace";
            g.fillText(mode === "heatmap" ? `max |A-B| ${fmt(this.heatMax)}` : mode === "split" ? "A | B" : mode.toUpperCase(), 6, 14); }
        this.zoomLbl.textContent = `${Math.round(this.view.scale * (pw / this.idx.a.width) * 100)}%`;
        this.drawScopes(pw, ph);
    }

    hover(px, py) {
        if (!this.cur || !this.view || !this.idx) return;
        const [pw, ph] = this.idx.a.proxy;
        const [ix, iy] = toImage(this.view, px, py);
        if (ix < 0 || iy < 0 || ix >= pw || iy >= ph) { this.probe.textContent = ""; return; }
        const p = (Math.floor(iy) * pw + Math.floor(ix)) * 4;
        const sx = Math.floor(ix * this.idx.a.width / pw), sy = Math.floor(iy * this.idx.a.height / ph);
        const c = this.cur;
        this.probe.textContent = `${sx}, ${sy}  ~ R ${fmt(c[p])} G ${fmt(c[p + 1])} B ${fmt(c[p + 2])} A ${fmt(c[p + 3])}`
            + "\nclick: exact value";
    }

    drawScopes(pw, ph) {
        const m = (this.lastMeasure = measure(this.cur, pw, ph, this.o));
        const st = m.stats;
        this.meas.textContent = this.meas.title = `peak luma ${fmt(st.peakLuma)} (${Number.isFinite(st.peakStops) ? (st.peakStops >= 0 ? "+" : "") + st.peakStops.toFixed(1) : "-"} stops over 18 % grey)`
            + ` | > 1.0: ${(100 * st.above1 / m.pixels).toFixed(1)} % | < 0: ${(100 * st.negative / m.pixels).toFixed(1)} %`
            + ` | mean R ${fmt(st.mean[0])} G ${fmt(st.mean[1])} B ${fmt(st.mean[2])}`;
        const sc = this.o.scope;
        if (!sc || sc === "none") return;
        const box = this.scopeBox;
        const W = Math.max(32, box.clientWidth), H = Math.max(32, box.clientHeight);
        const c = this.scopeCanvas;
        if (c.width !== W || c.height !== H) { c.width = W; c.height = H; }
        const g = c.getContext("2d");
        g.fillStyle = "#0b0b0e"; g.fillRect(0, 0, W, H);
        g.strokeStyle = "rgba(255,255,255,0.12)"; g.lineWidth = 1;
        if (sc === "histogram" || sc === "stops") {
            const series = sc === "stops" ? [[m.stops, "#9ad"]] : [[m.hist.r, "rgba(255,80,80,0.75)"], [m.hist.g, "rgba(80,255,80,0.75)"],
                [m.hist.b, "rgba(90,140,255,0.75)"], [m.hist.l, "rgba(235,235,235,0.6)"]];
            let top = 1;
            for (const [h] of series) for (let i = 1; i < h.length - 1; i++) top = Math.max(top, h[i]);
            for (const [h, col] of series) {
                g.strokeStyle = col; g.beginPath();
                for (let i = 0; i < h.length; i++) {
                    const x = (i / (h.length - 1)) * (W - 1), y = H - 1 - Math.min(1, h[i] / top) * (H - 6);
                    i ? g.lineTo(x, y) : g.moveTo(x, y);
                }
                g.stroke();
            }
            if (sc === "stops") {
                g.fillStyle = "rgba(255,255,255,0.55)"; g.font = "9px monospace";
                for (const s of [-8, -4, 0, 4, 8]) { const x = ((s + 8) / 16) * (W - 1); g.fillRect(x, 0, 1, H); g.fillText(`${s > 0 ? "+" : ""}${s}`, Math.min(W - 16, x + 2), 10); }
            }
            return;
        }
        const img = sc === "vectorscope" ? vectorscope(this.cur, pw, ph, this.o, Math.min(W, H))
            : waveform(this.cur, pw, ph, this.o, W, H, sc === "parade" ? "parade" : "luma");
        const S = sc === "vectorscope" ? Math.min(W, H) : 0;
        const id = new ImageData(img, sc === "vectorscope" ? S : W, sc === "vectorscope" ? S : H);
        g.putImageData(id, sc === "vectorscope" ? (W - S) / 2 : 0, 0);
        g.strokeStyle = "rgba(255,255,255,0.18)";
        if (sc === "vectorscope") {
            g.beginPath(); g.arc(W / 2, S / 2, S * 0.45, 0, Math.PI * 2); g.stroke();
            g.beginPath(); g.moveTo(W / 2 - S / 2, S / 2); g.lineTo(W / 2 + S / 2, S / 2); g.moveTo(W / 2, 0); g.lineTo(W / 2, S); g.stroke();
        } else {
            for (const f of [0.25, 0.5, 0.75]) { g.beginPath(); g.moveTo(0, H * (1 - f)); g.lineTo(W, H * (1 - f)); g.stroke(); }
        }
    }

    blink() {
        clearInterval(this.blinkTimer);
        this.blinkTimer = null;
        if (this.o.compare === "blink" && this.idx?.b) {
            this.blinkTimer = setInterval(() => { this.blinkB = !this.blinkB; this.redraw(); }, 500);
        }
    }

    syncAudio(start = false) {
        const a = this.audioEl;
        if (!a || !this.idx) return;
        a.muted = !!this.o.mute;
        const t = this.frame / (this.idx.fps || 24);
        if (Math.abs((a.currentTime || 0) - t) > 0.08) { try { a.currentTime = t; } catch (e) { /* not loaded yet */ } }
        if (start) a.play().catch(() => {});
    }

    async loadOcio() {
        if (this.ocioLoaded) return;
        this.ocioLoaded = true;
        try {
            const r = await fetch("/nukemax/ocio/lists?config=");
            const j = await r.json();
            if (!r.ok) return;
            for (const [d, views] of Object.entries(j.displays || {})) {
                for (const v of views) this.displaySel.append(Object.assign(el("option", "", `OCIO ${d} / ${v}`), { value: `ocio|${d}|${v}` }));
            }
            this.displaySel.title = `Display transform; OCIO entries from ${j.config} (${j.source})`;
            if (this.o.ocioDV) this.pickDisplay(this.o.ocioDV);
        } catch (e) { /* no OCIO on this server: sRGB / raw only */ }
    }

    async pickDisplay(value) {
        if (!String(value).startsWith("ocio|")) { this.setO({ display: value, ocioDV: null, lut: null }); return; }
        const [, d, v] = value.split("|");
        const r = await fetch(`/nukemax/viewer/lut?display=${encodeURIComponent(d)}&view=${encodeURIComponent(v)}`);
        const j = await r.json();
        if (!r.ok) { this.probe.textContent = j.error || "OCIO view unavailable"; return; }
        const bin = atob(j.data);
        const bytes = new Uint8Array(bin.length);
        for (let k = 0; k < bin.length; k++) bytes[k] = bin.charCodeAt(k);
        this.setO({ display: "ocio", ocioDV: value, lut: { size: j.size, lo: j.lo, hi: j.hi, data: new Float32Array(bytes.buffer) } });
        this.displaySel.value = value;
    }

    fillInspector(f) {
        const rows = [];
        const add = (k, v) => { if (v !== undefined && v !== null && v !== "") rows.push([k, typeof v === "string" ? v : JSON.stringify(v)]); };
        add("source", f.source); add("kind", f.kind); add("size", f.size && f.size.join(" x "));
        add("data window", f.data_window); add("display window", f.display_window);
        add("compression", f.compression); add("bit depth", f.bit_depth); add("colour", f.colour); add("fps", f.fps);
        for (const l of f.layers || []) add(`layer ${l.key}`, `${(l.channels || []).join(", ")}${l.alpha ? ` + ${l.alpha}` : ""}`
            + `${l.formats?.length ? ` (${l.formats.join("/")})` : ""}${l.kind ? ` [${l.kind}]` : ""}`);
        for (const [k, v] of Object.entries(f.header || {}).slice(0, 24)) add(k, v);
        this.inspBody.replaceChildren(...rows.map(([k, v]) => { const tr = el("tr"); tr.append(el("td", "", k), el("td", "", v)); return tr; }));
        this.insp.style.display = rows.length ? "" : "none";
    }

    async sampleRegion(ax, ay, bx, by) {
        if (!this.view || !this.idx) return;
        const [pw, ph] = this.idx.a.proxy;
        const W = this.idx.a.width, H = this.idx.a.height;
        const [x0, y0] = toImage(this.view, Math.min(ax, bx), Math.min(ay, by));
        const [x1, y1] = toImage(this.view, Math.max(ax, bx), Math.max(ay, by));
        const sx = Math.max(0, Math.floor(x0 * W / pw)), sy = Math.max(0, Math.floor(y0 * H / ph));
        const ex = Math.min(W, Math.ceil(x1 * W / pw)), ey = Math.min(H, Math.ceil(y1 * H / ph));
        if (ex <= sx || ey <= sy) return;
        const r = await fetch(`/nukemax/viewer/sample?key=${encodeURIComponent(this.idx.key)}&i=${this.frame}&x=${sx}&y=${sy}&w=${ex - sx}&h=${ey - sy}`);
        const j = await r.json();
        if (!r.ok) { this.probe.textContent = j.error || "no sample"; return; }
        this.lastRegion = j;
        const mx = j.max || [], mn = j.min || [], me = j.mean || [];
        this.probe.textContent = `region ${sx},${sy} ${ex - sx}x${ey - sy}  mean R ${fmt(me[0])} G ${fmt(me[1])} B ${fmt(me[2])}`
            + `  max ${fmt(Math.max(mx[0], mx[1], mx[2]))} min ${fmt(Math.min(mn[0], mn[1], mn[2]))}  ${j.source}`;
    }

    async sampleAt(px, py) {
        if (!this.view || !this.idx) return;
        const [pw, ph] = this.idx.a.proxy;
        const [ix, iy] = toImage(this.view, px, py);
        if (ix < 0 || iy < 0 || ix >= pw || iy >= ph) return;
        const sx = Math.floor(ix * this.idx.a.width / pw), sy = Math.floor(iy * this.idx.a.height / ph);
        const r = await fetch(`/nukemax/viewer/sample?key=${encodeURIComponent(this.idx.key)}&i=${this.frame}&x=${sx}&y=${sy}`);
        const j = await r.json();
        if (!r.ok) { this.probe.textContent = j.error || "no sample"; return; }
        const v = j.rgba || [];
        this.lastSample = j;
        this.probe.textContent = `${sx}, ${sy}  R ${fmt(v[0])} G ${fmt(v[1])} B ${fmt(v[2])} A ${fmt(v[3])}\n${j.source}`;
    }
}

app.registerExtension({
    name: "NukeMax.ViewerPro",
    nodeCreated(node) {
        if (node.comfyClass !== TYPE) return;
        const vp = new ViewerPro(node);
        node.__nukemaxViewerPro = vp;                     // the live check drives it through this
        const w = node.addDOMWidget("viewer", "div", vp.root, { serialize: false, hideOnZoom: false });
        if (w) {
            w.serialize = false;                          // a display widget: never in widgets_values (L9.102)
            w.options = w.options || {};
            w.options.getMinHeight = () => 470 + (vp.scopeExtra || 0);   // compare row + inspector (7c); + an open scope (7b)
        }
        const minW = 460;
        const cs = node.computeSize;
        node.computeSize = function () { const s = cs ? cs.apply(this, arguments) : [minW, 400]; return [Math.max(minW, s[0]), s[1]]; };
        if (!vueNodes()) requestAnimationFrame(() => node.setSize?.([Math.max(minW, node.size[0]), Math.max(node.size[1], node.computeSize()[1])]));
        const prev = node.onExecuted;
        node.onExecuted = function (message) {
            prev?.apply(this, arguments);
            const m = message?.nukemax_viewer?.[0];
            if (m) vp.load(m);
        };
        const pw = node.widgets?.find((x) => x.name === "apply_view_adjustment");
        if (pw) { const cb = pw.callback; pw.callback = function () { const r = cb?.apply(this, arguments); vp.paint(); return r; }; }
        const rem = node.onRemoved;
        node.onRemoved = function () { vp.stop(); clearInterval(vp.blinkTimer); return rem?.apply(this, arguments); };
    },
});
