// Mocha Paste/Upload widget — adds an "Upload .nk" button to the three
// MochaImport*Paste nodes. Uploads the chosen file to ComfyUI/input/mocha/
// via POST /nukemax/mocha/upload, then writes the returned filename into
// the node's `uploaded_file` widget. Also clears `nk_text` so the paste
// path takes the uploaded file (paste wins if both are set).

import { app } from "../../../../scripts/app.js";

const PASTE_NODES = new Set([
    "NukeMax_MochaImportShapesAsMaskPaste",
    "NukeMax_MochaImportCornerPinPaste",
    "NukeMax_MochaImportTransformPaste",
]);

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

async function _uploadFile(file, node) {
    const fd = new FormData();
    fd.append("file", file, file.name);
    try {
        const r = await fetch("/nukemax/mocha/upload", { method: "POST", body: fd });
        const j = await r.json();
        if (!j.ok) throw new Error(j.error || "upload failed");
        const wFile = _findWidget(node, "uploaded_file");
        const wText = _findWidget(node, "nk_text");
        if (wFile) wFile.value = j.name;
        if (wText) wText.value = "";  // prefer uploaded file
        node.setDirtyCanvas?.(true, true);
        _toast(`Uploaded ${j.name} (${j.bytes} bytes)`, "success");
    } catch (e) {
        _toast(`Upload failed: ${e.message || e}`, "error");
    }
}

function _addUploadButton(node) {
    if (node.__mochaUploadAdded) return;
    node.__mochaUploadAdded = true;
    node.addWidget("button", "📁 Upload .nk", "upload", () => {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = ".nk,.txt,.mocha,text/plain";
        input.style.display = "none";
        input.onchange = async (ev) => {
            const f = ev.target.files?.[0];
            if (f) await _uploadFile(f, node);
            input.remove();
        };
        document.body.appendChild(input);
        input.click();
    });
    // Helpful hint widget (read-only label-ish).
    node.addWidget("button", "📋 Paste .nk text into nk_text above (or use Upload)", "hint", () => {
        _toast("Paste the Mocha .nk export contents into the nk_text box, or click Upload .nk.", "info");
    });
}

app.registerExtension({
    name: "NukeMax.MochaUpload",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (!PASTE_NODES.has(nodeData.name)) return;
        const orig = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = orig?.apply(this, arguments);
            try { _addUploadButton(this); } catch (e) { console.error("[Mocha] addUploadButton", e); }
            return r;
        };
    },
});
