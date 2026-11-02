// nukemax_read_exr_pro.js — the file side of NukeMax Read EXR Pro (owner Rev 3 Part 19.3; ledger L9.80).
//
// The browser's image picker does not take .exr, so the node gets its own buttons:
//   Upload EXR…   one file, or every frame of a sequence (multi-select); each goes to POST /nukemax/media/upload, which
//                 checks the content (EXR magic number), cleans the name and stores it in input/nukemax_exr/ - an
//                 identical file is reused, a different one with the same name is kept beside it (never overwritten);
//   Refresh list  re-reads the input folder's EXRs (GET /nukemax/media/exr_files).
// The workflow saves the input-relative name, never a path from the user's computer. Status is shown on the node.

import { app } from "../../scripts/app.js";

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
        let first = null, done = 0;
        const notes = [];
        for (const f of files) {
            setStatus(node, `Uploading ${done + 1} of ${files.length}: ${f.name}`);
            const body = new FormData();
            body.append("file", f, f.name);
            try {
                const r = await fetch("/nukemax/media/upload", { method: "POST", body });
                const j = await r.json();
                if (!r.ok) { notes.push(j.error || `${f.name}: refused (${r.status})`); continue; }
                first = first ?? j.name;
                done += 1;
                if (j.status !== "uploaded") notes.push(`${f.name}: ${j.status}`);
            } catch (e) {
                notes.push(`${f.name}: ${e?.message || e}`);
            }
        }
        await refresh(node, first);
        setStatus(node, `${done} of ${files.length} uploaded` + (notes.length ? ` - ${notes.slice(0, 3).join("; ")}` : ""));
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
        if (node.comfyClass !== TYPE) return;
        // none of these is saved: values are restored by POSITION on fe 1.53, so an extra saved widget would shift them
        const b1 = node.addWidget("button", "Upload EXR…", null, () => upload(node), { serialize: false });
        const b2 = node.addWidget("button", "Refresh list", null, () => refresh(node), { serialize: false });
        const s = node.addWidget("text", "upload status", "", () => {}, { serialize: false });
        for (const w of [b1, b2, s]) if (w) w.serialize = false;
        if (s) s.disabled = true;
    },
});
