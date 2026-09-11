// On-node EXR preview for the Nuke Read nodes.
//
// WHY A SERVER-RENDERED <img>: the browser cannot decode OpenEXR, and a
// scene-linear EXR shown without a display transform reads as almost black --
// which is the most common "my Read node is broken" report. So the server
// renders the frame (OpenImageIO) through an OCIO display/view and hands back
// PNG. See nukemax/nodes/io/exr_preview_server.py.
//
// WHY addDOMWidget: it renders on the Vue frontend AND the legacy canvas one.
// node.imgs / raw canvas draws do not render on Vue.

import { app } from "../../../../scripts/app.js";

const TARGETS = new Set(["NukeMax_EXRSequenceLoad", "NukeMax_EXRChannelRouter"]);
const PATH_WIDGETS = ["path", "file_path", "filename", "exr_path"];
const MIN_H = 160;
const HEADER_H = 92;

const css = (el, o) => Object.assign(el.style, o);

function findPathWidget(node) {
    for (const name of PATH_WIDGETS) {
        const w = (node.widgets || []).find((x) => x.name === name);
        if (w) return w;
    }
    return null;
}

function mkBtn(label, title) {
    const b = document.createElement("button");
    b.textContent = label;
    b.title = title;
    css(b, {
        font: "11px system-ui, sans-serif", padding: "3px 8px", cursor: "pointer",
        background: "var(--comfy-input-bg, #222)", color: "var(--input-text, #ddd)",
        border: "1px solid var(--border-color, #444)", borderRadius: "4px",
    });
    return b;
}

function mkSelect(title) {
    const s = document.createElement("select");
    s.title = title;
    css(s, {
        font: "11px system-ui, sans-serif", maxWidth: "130px",
        background: "var(--comfy-input-bg, #222)", color: "var(--input-text, #ddd)",
        border: "1px solid var(--border-color, #444)", borderRadius: "4px",
    });
    return s;
}

function build(node) {
    const box = document.createElement("div");
    css(box, { display: "flex", flexDirection: "column", gap: "4px", width: "100%",
               height: "100%", overflow: "hidden",
               font: "11px system-ui, sans-serif", color: "var(--input-text, #ddd)" });

    // ---- row 1: identity + collapse ----------------------------------------
    const row1 = document.createElement("div");
    css(row1, { display: "flex", alignItems: "center", gap: "6px", flex: "0 0 auto" });
    const title = document.createElement("div");
    css(title, { flex: "1 1 auto", overflow: "hidden", textOverflow: "ellipsis",
                 whiteSpace: "nowrap", opacity: "0.85" });
    title.textContent = "no file";
    const collapse = mkBtn("Hide",
        "Collapse the viewer. The node keeps working; this only frees canvas space.");
    row1.append(title, collapse);

    // ---- row 2: display / view / channel -----------------------------------
    const row2 = document.createElement("div");
    css(row2, { display: "flex", alignItems: "center", gap: "4px", flex: "0 0 auto",
                flexWrap: "wrap" });
    const display = mkSelect(
        "OCIO display device. A scene-linear EXR has no built-in look; the display " +
        "says what monitor you are grading for (sRGB, Rec.709, P3...).");
    const view = mkSelect(
        "OCIO view transform. This is the tonemap applied on top of the display -- " +
        "'ACES 1.0 SDR-video' vs 'Un-tone-mapped' is the difference between a graded " +
        "look and raw linear values.");
    const channel = mkSelect(
        "Which AOV to look at. Multilayer EXRs carry depth / normal / position / " +
        "cryptomatte beside the beauty pass; this previews one without re-rendering.");
    row2.append(display, view, channel);

    // ---- row 3: exposure + upload ------------------------------------------
    const row3 = document.createElement("div");
    css(row3, { display: "flex", alignItems: "center", gap: "6px", flex: "0 0 auto" });
    const expLabel = document.createElement("span");
    expLabel.textContent = "EV 0.0";
    css(expLabel, { minWidth: "46px", opacity: "0.85" });
    const exposure = document.createElement("input");
    exposure.type = "range"; exposure.min = "-8"; exposure.max = "8";
    exposure.step = "0.25"; exposure.value = "0";
    exposure.title =
        "Exposure in stops, applied in linear before the display transform -- the same " +
        "thing you would do on a Nuke viewer to find detail hiding in the blacks or " +
        "check what is really clipped in the highlights.";
    css(exposure, { flex: "1 1 auto", minWidth: "60px" });
    const upload = mkBtn("Upload…",
        "Copy an EXR into ComfyUI's input folder and point this node at it. Use this " +
        "when the plate lives somewhere the server is not allowed to read.");
    row3.append(expLabel, exposure, upload);

    // ---- row 4: frame scrubber (sequences only) ----------------------------
    const row4 = document.createElement("div");
    css(row4, { display: "none", alignItems: "center", gap: "6px", flex: "0 0 auto" });
    const frameLabel = document.createElement("span");
    css(frameLabel, { minWidth: "62px", opacity: "0.85" });
    const frame = document.createElement("input");
    frame.type = "range"; frame.min = "0"; frame.max = "0"; frame.step = "1";
    frame.title = "Scrub the detected sequence. This previews frames only; it does not " +
                  "change which frames the node loads (use start_frame / end_frame).";
    css(frame, { flex: "1 1 auto", minWidth: "60px" });
    row4.append(frameLabel, frame);

    // ---- image ------------------------------------------------------------
    const imgWrap = document.createElement("div");
    css(imgWrap, { flex: "1 1 auto", minHeight: "0", display: "flex",
                   alignItems: "center", justifyContent: "center",
                   background: "var(--comfy-menu-bg, #1a1a1a)",
                   border: "1px solid var(--border-color, #444)", borderRadius: "4px",
                   overflow: "hidden" });
    const img = document.createElement("img");
    css(img, { maxWidth: "100%", maxHeight: "100%", objectFit: "contain",
               imageRendering: "auto", display: "none" });
    const msg = document.createElement("div");
    css(msg, { padding: "8px", textAlign: "center", opacity: "0.7", font:
               "11px system-ui, sans-serif" });
    msg.textContent = "Set a path to preview";
    imgWrap.append(img, msg);

    box.append(row1, row2, row3, row4, imgWrap);
    return { box, title, collapse, display, view, channel, exposure, expLabel,
             upload, frame, frameLabel, row2, row3, row4, imgWrap, img, msg };
}

function attach(node) {
    if (node._nmExr) return node._nmExr;
    const ui = build(node);
    const state = { ui, collapsed: false, info: null, seq: false, timer: 0, objUrl: "" };
    node._nmExr = state;

    const widget = node.addDOMWidget("exr_preview", "div", ui.box, { serialize: false });
    widget.computeSize = (width) => {
        if (state.collapsed) return [width, 26];
        const w = Math.max(120, (width || node.size?.[0] || 320) - 20);
        const ar = state.info && state.info.width
            ? state.info.height / state.info.width : 9 / 16;
        return [width, Math.max(MIN_H, HEADER_H + Math.round(w * ar))];
    };

    const setMsg = (t) => {
        ui.msg.textContent = t;
        ui.msg.style.display = t ? "block" : "none";
        ui.img.style.display = t ? "none" : "block";
    };

    const refresh = () => {
        const pw = findPathWidget(node);
        const p = (pw && pw.value ? String(pw.value) : "").trim();
        if (!p) { setMsg("Set a path to preview"); return; }
        const q = new URLSearchParams({
            path: p,
            frame: state.seq ? String(ui.frame.value) : "-1",
            w: String(Math.max(160, Math.round((node.size?.[0] || 320) * 1.5))),
            display: ui.display.value || "",
            view: ui.view.value || "",
            exposure: ui.exposure.value || "0",
            channel: ui.channel.value || "",
        });
        const url = "/nukemax/exr/thumb?" + q.toString();
        const probe = new Image();
        probe.onload = () => { ui.img.src = url; setMsg(""); node.setDirtyCanvas(true, true); };
        probe.onerror = async () => {
            // Surface the server's sentence, not a broken-image icon.
            try {
                const r = await fetch(url);
                const j = await r.json().catch(() => null);
                setMsg(j && j.error ? j.error : "Could not render this file.");
            } catch (e) { setMsg("Could not reach the preview service."); }
        };
        probe.src = url;
    };

    // Dragging a slider must not fire a request per pixel.
    const debounced = () => {
        if (state.timer) clearTimeout(state.timer);
        state.timer = setTimeout(refresh, 200);
    };

    const loadInfo = async () => {
        const pw = findPathWidget(node);
        const p = (pw && pw.value ? String(pw.value) : "").trim();
        if (!p) { setMsg("Set a path to preview"); ui.title.textContent = "no file"; return; }
        try {
            const r = await fetch("/nukemax/exr/info?path=" + encodeURIComponent(p));
            const j = await r.json();
            if (!j.ok) { setMsg(j.error || "Could not read that file."); return; }
            state.info = j;

            const bits = [j.name, j.width + "x" + j.height];
            if (j.compression) bits.push(j.compression);
            if (j.is_sequence) bits.push(j.first + "-" + j.last + " (" + j.count + "f)");
            ui.title.textContent = bits.join("  ·  ");

            ui.channel.innerHTML = "";
            for (const g of (j.groups || ["rgba"])) {
                const o = document.createElement("option");
                o.value = g; o.textContent = g;
                ui.channel.append(o);
            }

            const o = j.ocio || {};
            ui.display.innerHTML = ""; ui.view.innerHTML = "";
            if (o.available) {
                for (const d of o.displays) {
                    const e = document.createElement("option");
                    e.value = d; e.textContent = d;
                    ui.display.append(e);
                }
                ui.display.value = o.default_display || (o.displays[0] || "");
                const fillViews = () => {
                    ui.view.innerHTML = "";
                    for (const v of (o.views[ui.display.value] || [])) {
                        const e = document.createElement("option");
                        e.value = v; e.textContent = v;
                        ui.view.append(e);
                    }
                    if (o.default_view && (o.views[ui.display.value] || []).includes(o.default_view))
                        ui.view.value = o.default_view;
                };
                fillViews();
                ui.display.onchange = () => { fillViews(); refresh(); };
                ui.view.onchange = refresh;
            } else {
                const e = document.createElement("option");
                e.value = ""; e.textContent = "no OCIO config";
                ui.display.append(e.cloneNode(true)); ui.view.append(e);
                ui.display.disabled = ui.view.disabled = true;
            }

            state.seq = !!j.is_sequence;
            ui.row4.style.display = state.seq ? "flex" : "none";
            if (state.seq) {
                ui.frame.min = String(j.first); ui.frame.max = String(j.last);
                ui.frame.value = String(j.first);
                ui.frameLabel.textContent = "frame " + j.first;
            }
            node.setSize(node.computeSize());
            refresh();
        } catch (e) {
            setMsg("Could not reach the preview service.");
        }
    };

    ui.channel.onchange = refresh;
    ui.exposure.oninput = () => {
        ui.expLabel.textContent = "EV " + Number(ui.exposure.value).toFixed(1);
        debounced();
    };
    ui.frame.oninput = () => {
        ui.frameLabel.textContent = "frame " + ui.frame.value;
        debounced();
    };
    ui.collapse.onclick = () => {
        state.collapsed = !state.collapsed;
        ui.collapse.textContent = state.collapsed ? "Show" : "Hide";
        ui.row2.style.display = state.collapsed ? "none" : "flex";
        ui.row3.style.display = state.collapsed ? "none" : "flex";
        ui.row4.style.display = (state.collapsed || !state.seq) ? "none" : "flex";
        ui.imgWrap.style.display = state.collapsed ? "none" : "flex";
        node.setSize(node.computeSize());
        node.setDirtyCanvas(true, true);
    };
    ui.upload.onclick = () => {
        const inp = document.createElement("input");
        inp.type = "file";
        inp.accept = ".exr,.png,.jpg,.jpeg,.tif,.tiff,.hdr,.dpx";
        inp.onchange = async () => {
            const f = inp.files && inp.files[0];
            if (!f) return;
            const fd = new FormData();
            fd.append("file", f, f.name);
            setMsg("Uploading " + f.name + "…");
            try {
                const r = await fetch("/nukemax/exr/upload", { method: "POST", body: fd });
                const j = await r.json();
                if (!j.ok) { setMsg(j.error || "Upload failed."); return; }
                const pw = findPathWidget(node);
                if (pw) { pw.value = j.path; pw.callback?.(j.path); }
                loadInfo();
            } catch (e) { setMsg("Upload failed."); }
        };
        inp.click();
    };

    // Re-read when the path widget changes, without stomping an existing callback.
    const pw = findPathWidget(node);
    if (pw) {
        const orig = pw.callback;
        pw.callback = function (...a) {
            const r = orig ? orig.apply(this, a) : undefined;
            loadInfo();
            return r;
        };
    }

    node.onRemoved = ((prev) => function () {
        if (state.timer) clearTimeout(state.timer);
        if (state.objUrl) { try { URL.revokeObjectURL(state.objUrl); } catch (e) {} }
        ui.img.src = "";
        return prev && prev.apply(this, arguments);
    })(node.onRemoved);

    setTimeout(loadInfo, 50);
    return state;
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
