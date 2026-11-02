// nukemax_read_exr_pro.js — the file side of NukeMax Read EXR Pro (owner Rev 3 Part 19.3; ledger L9.80), and the
// result boxes of EXR Metadata Reader Pro (19.5) and Write EXR Pro (19.7).
//
// The browser's image picker does not take .exr, so the node gets its own buttons:
//   Upload EXR…   one file, or every frame of a sequence (multi-select); each goes to POST /nukemax/media/upload, which
//                 checks the content (EXR magic number), cleans the name and stores it in input/nukemax_exr/ - an
//                 identical file is reused, a different one with the same name is kept beside it (never overwritten);
//   Refresh list  re-reads the input folder's EXRs (GET /nukemax/media/exr_files).
// The workflow saves the input-relative name, never a path from the user's computer. Status is shown on the node.

import { app } from "../../../../scripts/app.js";
import { ComfyWidgets } from "../../../../scripts/widgets.js";

const TYPE = "NukeMax_ReadEXRPro";

async function refresh(node, pick) {
    const w = node.widgets?.find((x) => x.name === "file");
    if (!w) return;
    try {
        const r = await fetch("/nukemax/media/exr_files");
        const files = (await r.json()).files || [];
        w.options.values = files.length ? files : [""];
        if (pick && files.includes(pick)) w.value = pick;
        else if (!files.includes(w.value)) w.value = w.options.values[0];
        w.callback?.(w.value);
    } catch (e) {
        setStatus(node, `Could not read the input folder: ${e?.message || e}`);
    }
    node.setDirtyCanvas?.(true, true);
}

function setStatus(node, text) {
    const s = node.widgets?.find((x) => x.name === "upload status");
    if (s) s.value = text;
    node.setDirtyCanvas?.(true, true);
}

async function upload(node) {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".exr";
    input.multiple = true;
    input.onchange = async () => {
        const files = [...(input.files || [])].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
        if (!files.length) return;
        // ONE request for the whole selection: the server versions a re-uploaded sequence as a whole (shot_1.1001.exr ...)
        setStatus(node, `Uploading ${files.length} file(s)…`);
        const body = new FormData();
        for (const f of files) body.append("file", f, f.name);
        let first = null, done = 0;
        const notes = [];
        try {
            const r = await fetch("/nukemax/media/upload", { method: "POST", body });
            const j = await r.json();
            if (!r.ok) notes.push(j.error || `refused (${r.status})`);
            else { first = j.name; done = (j.names || []).length; if (j.status) notes.push(j.status); }
        } catch (e) {
            notes.push(String(e?.message || e));
        }
        await refresh(node, first);
        setStatus(node, `${done} of ${files.length} uploaded` + (notes.length ? ` - ${notes.join("; ")}` : ""));
        if (files.length > 1) {
            const m = node.widgets?.find((x) => x.name === "mode");
            if (m && m.value === "file (input folder)") { m.value = "sequence (input folder)"; m.callback?.(m.value); }
        }
    };
    input.click();
}

app.registerExtension({
    name: "NukeMax.ReadEXRPro",
    nodeCreated(node) {
        const BOXES = {
            // Part 19.5's header inspector: the node's summary (sizes, windows, parts, channels, layers) on the node
            NukeMax_EXRMetadataReaderPro: "header summary",
            // Part 19.7: "the node must confirm exactly which files it wrote" - the confirmed list, on the node
            NukeMax_WriteEXRPro: "written files",
        };
        if (BOXES[node.comfyClass]) {
            // a real read-only textarea (ComfyUI's multiline STRING widget): a LiteGraph "text" widget is one line and,
            // disabled, draws no value at all - the list was set but invisible (L9.80 slice 3 screenshot)
            const box = ComfyWidgets.STRING(node, BOXES[node.comfyClass], ["STRING", { multiline: true }], app)?.widget;
            if (box) {
                box.serialize = false;                      // display only: never in widgets_values (see L9.102)
                box.value = "(run the node)";
                const el = box.inputEl || box.element;
                if (el) { el.readOnly = true; el.style.fontSize = "11px"; el.style.opacity = "0.9"; }
                // about six lines visible (the summary, then the files); the rest scrolls inside the box
                box.options = box.options || {};
                box.options.getMinHeight = () => 96;
                node.setSize?.([node.size[0], Math.max(node.size[1], node.computeSize()[1])]);
            }
            const prev = node.onExecuted;
            node.onExecuted = function (message) {
                prev?.apply(this, arguments);
                const t = message?.text;
                if (box && t) { box.value = Array.isArray(t) ? t.join("\n") : String(t); node.setDirtyCanvas?.(true, true); }
            };
            return;
        }
        if (node.comfyClass !== TYPE) return;
        // none of these is saved: values are restored by POSITION on fe 1.53, so an extra saved widget would shift them
        const b1 = node.addWidget("button", "Upload EXR…", null, () => upload(node), { serialize: false });
        const b2 = node.addWidget("button", "Refresh list", null, () => refresh(node), { serialize: false });
        const s = node.addWidget("text", "upload status", "", () => {}, { serialize: false });
        for (const w of [b1, b2, s]) if (w) w.serialize = false;
        if (s) s.disabled = true;
    },
});
