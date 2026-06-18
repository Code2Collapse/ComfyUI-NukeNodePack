// Mocha drag-drop / paste / upload widget.
//
// Adds 3 input methods to every Mocha import node:
//   1. 📁 Upload .nk button — file picker
//   2. Drag-and-drop — drop the .nk/.txt/.mocha file anywhere on the node
//   3. Clipboard paste — select the node and press Ctrl+V, accepts EITHER
//        a) a file copied in Explorer / Finder
//        b) the .nk text content copied from a text editor
//
// On successful upload:
//   - For *Paste nodes: writes filename to `uploaded_file`, clears `nk_text`
//   - For path-only nodes: writes `mocha/<name>` into `file_path`
//
// All transports POST to /nukemax/mocha/upload (existing endpoint).

import { app } from "../../../../scripts/app.js";

// Every Mocha import node, including the original file_path variants.
const ALL_MOCHA_IMPORT_NODES = new Set([
    "NukeMax_MochaImportShapesAsMaskPaste",
    "NukeMax_MochaImportCornerPinPaste",
    "NukeMax_MochaImportTransformPaste",
    "NukeMax_MochaImportCornerPin",
    "NukeMax_MochaImportTransform",
    "NukeMax_MochaImportShapesAsMask",
    "NukeMax_MochaImportLens",
    "NukeMax_MochaImportProject",
]);

const PASTE_NODES = new Set([
    "NukeMax_MochaImportShapesAsMaskPaste",
    "NukeMax_MochaImportCornerPinPaste",
    "NukeMax_MochaImportTransformPaste",
]);

const ACCEPT_EXT = /\.(nk|txt|mocha|json)$/i;

function _toast(msg, severity = "info") {
    try {
        app.extensionManager?.toast?.add({
            severity, summary: "Mocha", detail: msg, life: 3500,
        });
    } catch (_) { console.log("[Mocha]", msg); }
}

function _findWidget(node, name) {
    return (node.widgets || []).find((w) => w.name === name);
}

function _writeFilename(node, name) {
    const wFile = _findWidget(node, "uploaded_file");
    const wText = _findWidget(node, "nk_text");
    const wPath = _findWidget(node, "file_path");
    if (wFile) wFile.value = name;
    if (wText) wText.value = "";
    if (wPath) wPath.value = `mocha/${name}`;  // _resolve_path() handles this
    node.setDirtyCanvas?.(true, true);
}

async function _uploadFile(file, node) {
    if (!file) return;
    if (file.size > 50 * 1024 * 1024) {
        _toast(`Refusing upload — file > 50 MB (${(file.size / 1e6).toFixed(1)} MB)`, "error");
        return;
    }
    const fd = new FormData();
    fd.append("file", file, file.name);
    try {
        const r = await fetch("/nukemax/mocha/upload", { method: "POST", body: fd });
        const j = await r.json();
        if (!j.ok) throw new Error(j.error || "upload failed");
        _writeFilename(node, j.name);
        _toast(`Uploaded ${j.name} (${(j.bytes / 1024).toFixed(1)} KB)`, "success");
    } catch (e) {
        _toast(`Upload failed: ${e.message || e}`, "error");
    }
}

async function _uploadText(text, suggestedName, node) {
    const blob = new Blob([text], { type: "text/plain" });
    const name = suggestedName || `pasted_${Date.now()}.nk`;
    const file = new File([blob], name, { type: "text/plain" });
    await _uploadFile(file, node);
    // For *Paste nodes also populate nk_text for visibility.
    if (PASTE_NODES.has(node.comfyClass || node.type)) {
        const wText = _findWidget(node, "nk_text");
        if (wText) {
            wText.value = text;
            node.setDirtyCanvas?.(true, true);
        }
    }
}

function _installCanvasDropOnce() {
    const canvas = app.canvas?.canvas || document.getElementById("graph-canvas");
    if (!canvas || canvas.__mochaDropHooked) return;
    canvas.__mochaDropHooked = true;

    const findNodeUnder = (clientX, clientY) => {
        const r = canvas.getBoundingClientRect();
        const ds = app.canvas.ds;
        const gx = (clientX - r.left - ds.offset[0]) / ds.scale;
        const gy = (clientY - r.top - ds.offset[1]) / ds.scale;
        for (const n of app.graph._nodes) {
            if (!ALL_MOCHA_IMPORT_NODES.has(n.comfyClass || n.type)) continue;
            const [nx, ny] = n.pos;
            const [nw, nh] = n.size;
            if (gx >= nx && gx <= nx + nw && gy >= ny - 24 && gy <= ny + nh) return n;
        }
        return null;
    };

    canvas.addEventListener("dragover", (e) => {
        const types = e.dataTransfer?.types || [];
        if (!types.includes("Files") && !types.includes("text/plain")) return;
        const n = findNodeUnder(e.clientX, e.clientY);
        if (n) {
            e.preventDefault();
            e.dataTransfer.dropEffect = "copy";
        }
    });

    canvas.addEventListener("drop", async (e) => {
        const n = findNodeUnder(e.clientX, e.clientY);
        if (!n) return;
        e.preventDefault();
        e.stopPropagation();
        const dt = e.dataTransfer;
        if (dt.files?.length) {
            const f = dt.files[0];
            if (!ACCEPT_EXT.test(f.name)) {
                _toast(`Skipping ${f.name} — expected .nk/.txt/.mocha/.json`, "warn");
                return;
            }
            await _uploadFile(f, n);
            return;
        }
        const text = dt.getData("text/plain");
        if (text && text.length > 4) {
            await _uploadText(text, "dropped.nk", n);
        }
    });
}

function _installGlobalPasteOnce() {
    if (document.__mochaPasteHooked) return;
    document.__mochaPasteHooked = true;
    document.addEventListener("paste", async (e) => {
        const sel = app.canvas?.selected_nodes;
        if (!sel) return;
        const ids = Object.keys(sel);
        if (ids.length !== 1) return;
        const node = sel[ids[0]];
        if (!ALL_MOCHA_IMPORT_NODES.has(node.comfyClass || node.type)) return;

        const files = e.clipboardData?.files;
        if (files && files.length) {
            const f = files[0];
            if (ACCEPT_EXT.test(f.name)) {
                e.preventDefault();
                await _uploadFile(f, node);
                return;
            }
        }
        const text = e.clipboardData?.getData("text/plain") || "";
        if (text.length > 16 && /(Tracker4|CornerPin|Transform|MochaPro|set knob|input0)/i.test(text)) {
            e.preventDefault();
            await _uploadText(text, "pasted.nk", node);
        }
    });
}

function _addWidgets(node) {
    if (node.__mochaWidgetsAdded) return;
    node.__mochaWidgetsAdded = true;

    node.addWidget("button", "📁 Upload .nk / .txt", "upload", () => {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = ".nk,.txt,.mocha,.json,text/plain";
        input.style.display = "none";
        input.onchange = async (ev) => {
            const f = ev.target.files?.[0];
            if (f) await _uploadFile(f, node);
            input.remove();
        };
        document.body.appendChild(input);
        input.click();
    });

    node.addWidget("button", "💡 or drag-drop / Ctrl+V on this node", "hint", () => {
        _toast(
            "Drag a .nk/.txt file onto this node, or select the node and press Ctrl+V to paste a copied file or .nk text.",
            "info",
        );
    });
}

app.registerExtension({
    name: "NukeMax.MochaUpload",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (!ALL_MOCHA_IMPORT_NODES.has(nodeData.name)) return;
        const orig = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = orig?.apply(this, arguments);
            try {
                _addWidgets(this);
                _installCanvasDropOnce();
                _installGlobalPasteOnce();
            } catch (e) { console.error("[Mocha] init", e); }
            return r;
        };
    },
});
