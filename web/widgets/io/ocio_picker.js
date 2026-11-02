// ocio_picker.js — "Pick colour space…" for NukeMax's OCIO-aware nodes (owner Rev 3 Part 19.10; ledger L9.80 slice 5a).
//
// The colour fields stay STRING inputs, so saved workflows keep their values and a show-config name is never refused
// by a list built from another config. The lists come from the node's OWN config, never from a hard-coded table:
//   the node's `config` choice, or the NukeMax OCIO Config Manager wired to its `ocio_config` socket, or its
//   `ocio_config` path text (Read / Write), else $OCIO / the built-in ACES studio config.
// GET /nukemax/ocio/lists?config=... answers roles, colour spaces by family, displays -> views and looks.
// The Config Manager node also gets "Reload config" (POST /nukemax/ocio/reload).

import { app } from "../../../../scripts/app.js";

const FIELDS = {
    NukeMax_OCIOColorTransform: ["src_colorspace", "dst_colorspace"],
    NukeMax_OCIODisplay: ["input_colorspace", "display", "view"],
    NukeMax_OCIOLookTransform: ["in_colorspace", "out_colorspace", "look"],
    NukeMax_Read: ["colour_space", "convert_to"],
    NukeMax_Write: ["convert_from", "colour_space"],
    NukeMax_WriteEXRPro: ["convert_from", "colour_space"],
    NukeMax_OCIORead: ["source_space", "working_space"],
    NukeMax_OCIOWrite: ["input_space", "output_space"],
};

let lastPointer = { clientX: 200, clientY: 200 };
window.addEventListener("pointerdown", (e) => { lastPointer = { clientX: e.clientX, clientY: e.clientY }; }, true);

function widget(node, name) {
    return (node.widgets || []).find((w) => w.name === name);
}

/** The config this node's lists come from. */
function configOf(node) {
    const slot = (node.inputs || []).findIndex((i) => i.name === "ocio_config");
    if (slot >= 0) {
        const link = node.getInputLink?.(slot) ?? (node.inputs[slot].link != null ? node.graph?.links?.[node.inputs[slot].link] : null);
        const src = link ? node.graph?.getNodeById?.(link.origin_id) : null;
        if (src) {
            const file = widget(src, "config_file")?.value;
            if (file) return String(file);
            const c = widget(src, "config")?.value;
            if (c) return String(c);
        }
    }
    const own = widget(node, "config")?.value ?? widget(node, "ocio_config")?.value;
    return own ? String(own) : "";
}

async function fetchLists(node) {
    const r = await fetch(`/nukemax/ocio/lists?config=${encodeURIComponent(configOf(node))}`);
    const j = await r.json();
    if (!r.ok || j.error) throw new Error(j.error || `the server answered ${r.status}`);
    return j;
}

function setValue(node, field, value) {
    const w = widget(node, field);
    if (!w) return;
    w.value = value;
    w.callback?.(value);
    node.setDirtyCanvas?.(true, true);
}

function groupsFor(field, lists, node) {
    if (field === "display") return [["Displays", Object.keys(lists.displays || {})]];
    if (field === "view") {
        const d = widget(node, "display")?.value || Object.keys(lists.displays || {})[0] || "";
        return [[`Views of ${d || "the default display"}`, (lists.displays || {})[d] || []]];
    }
    if (field === "look") return [["Looks", lists.looks || []]];
    const roles = Object.keys(lists.roles || {}).map((r) => `${r}`);
    return [["Roles", roles], ...Object.entries(lists.families || {}).sort(([a], [b]) => a.localeCompare(b))];
}

function openMenu(node, lists) {
    const fields = (FIELDS[node.comfyClass] || []).filter((f) => widget(node, f));
    const title = `${lists.config} (${lists.source})${lists.missing_luts ? ` - ${lists.missing_luts} missing LUT(s)` : ""}`;
    const options = fields.map((field) => ({
        content: field,
        has_submenu: true,
        submenu: {
            options: groupsFor(field, lists, node).filter(([, names]) => names.length).map(([group, names]) => ({
                content: `${group} (${names.length})`,
                has_submenu: true,
                submenu: { options: names, callback: (v) => setValue(node, field, typeof v === "string" ? v : v?.content) },
            })),
        },
    }));
    if (!options.length) return;
    new LiteGraph.ContextMenu(options, { event: lastPointer, title });
}

async function pick(node) {
    try {
        openMenu(node, await fetchLists(node));
    } catch (e) {
        const st = widget(node, "nukemax_status");
        if (st?.element) st.element.textContent = `OCIO lists unavailable: ${e?.message || e}`;
    }
}

app.registerExtension({
    name: "NukeMax.OCIOPicker",
    nodeCreated(node) {
        if (node.comfyClass === "NukeMax_OCIOConfigManager") {
            const b = node.addWidget("button", "Reload config", null, async () => {
                await fetch("/nukemax/ocio/reload", { method: "POST" });
                const st = widget(node, "nukemax_status");
                if (st?.element) st.element.textContent = "Config reloaded - the next run reads it again.";
            }, { serialize: false });
            if (b) b.serialize = false;
            return;
        }
        if (!FIELDS[node.comfyClass]) return;
        // not saved: an extra saved widget would shift restored values (L9.102)
        const b = node.addWidget("button", "Pick colour space…", null, () => pick(node), { serialize: false });
        if (b) b.serialize = false;
        // a connected Config Manager wins over the node's own config choice: say so on that widget
        const cfgW = widget(node, "config");
        const slot = (node.inputs || []).findIndex((i) => i.name === "ocio_config");
        if (cfgW && slot >= 0) {
            const plain = cfgW.label || cfgW.name;
            const mark = () => {
                const linked = node.inputs?.[slot]?.link != null;
                cfgW.label = linked ? "config (from Config Manager)" : plain;
                cfgW.disabled = linked;
                node.setDirtyCanvas?.(true, true);
            };
            const prev = node.onConnectionsChange;
            node.onConnectionsChange = function () {
                const r = prev?.apply(this, arguments);
                mark();
                return r;
            };
            requestAnimationFrame(mark);
        }
    },
});

// for the live check: the same menu, opened for a node
window.__nukemaxOcioPick = pick;
