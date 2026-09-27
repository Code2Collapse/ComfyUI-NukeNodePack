// _nukemax_kit.js — the house UI layer applied to EVERY NukeMax node.
//
// WHY A SHARED LAYER: this pack has 179 nodes and seven widget files. Writing a
// bespoke UI per node does not finish, and most of these are single-op
// compositing nodes where a bespoke UI would be noise anyway. What every node
// DOES need is the same three things:
//
//   1. Errors in plain English. ComfyUI surfaces a raw Python traceback, which
//      tells a compositor nothing. CLAUDE.md's visual check lists this
//      explicitly: "Are error messages in plain English - no raw Python
//      tracebacks?" The translation table below is that rule, implemented once.
//   2. A family badge. 179 nodes across Color / Filter / Merge / Keying / Deep /
//      Mocha / OCIO read as an undifferentiated wall without one.
//   3. Run status - did this node actually execute, and how long did it take.
//      Nuke shows it; ComfyUI does not.
//
// Node-specific widgets (roto editor, EXR preview, mocha upload...) sit ON TOP
// of this and are unaffected: this only adds a strip, never replaces anything.
//
// Plain ES module, no Vue. Nothing touches `window` at import time, so a
// queue-only / headless run is unaffected.

import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

const PREFIX = "NukeMax_";
const ST = "_nmKit";

import { humaniseError } from "./_nukemax_errors.js";
export { humaniseError };

// The badge hues used to be twenty-six literals here. They live in
// _nukemax_theme.js now, as PALETTE keys, so they move with the theme rather
// than clashing with whichever ground is behind them.
import { cssVar, familyColor, familyNames, onBadge } from "./_nukemax_theme.js";

function familyOf(nodeData) {
  const cat = String(nodeData?.category || "");
  const tail = cat.split("/").pop() || "";
  const names = familyNames();
  if (names.includes(tail)) return tail;
  for (const k of names) if (cat.includes(k)) return k;
  return "";
}

// ── the strip ───────────────────────────────────────────────────────────────

function buildStrip(family) {
  const el = document.createElement("div");
  el.style.cssText =
    "display:flex;align-items:center;gap:6px;width:100%;" +
    `font:10px system-ui,sans-serif;color:${cssVar("text")};` +
    "padding:1px 2px;box-sizing:border-box;min-height:14px;";

  const badge = document.createElement("span");
  if (family) {
    badge.textContent = family;
    badge.style.cssText =
      `flex:0 0 auto;padding:0 5px;border-radius:7px;font-size:9px;` +
      `letter-spacing:.3px;background:${familyColor(family)};` +
      `color:${onBadge()};opacity:.9;`;
  }

  const status = document.createElement("span");
  status.style.cssText =
    "flex:1 1 auto;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;opacity:.7;";

  el.append(badge, status);
  return { el, badge, status };
}

function setStatus(st, text, tone) {
  st.status.textContent = text || "";
  st.status.style.color =
    tone === "error" ? cssVar("danger") : tone === "ok" ? cssVar("text") : "";
  st.status.style.opacity = tone === "error" ? "1" : ".7";
  st.status.title = st.fullError || "";
}

export function attachKit(node, nodeData) {
  if (node[ST]) return node[ST];
  const family = familyOf(nodeData);
  const ui = buildStrip(family);
  const st = { ui, t0: 0, fullError: "" };
  node[ST] = st;
  st.status = ui.status;

  const w = node.addDOMWidget("nukemax_status", "div", ui.el, { serialize: false, margin: 2 });
  // One compact row. It must never push the node taller than it needs.
  // ComfyUI insets a DOM widget by `margin` on every side (default 10), so a
  // 15px slot left the 14px strip -5px of room: it hung ~9px past the node's
  // bottom edge. A 2px margin in an 18px slot fits it exactly.
  w.computeSize = (width) => [width, 18];

  setStatus(st, "", "");
  return st;
}

// ── extension ───────────────────────────────────────────────────────────────

app.registerExtension({
  name: "NukeMax.HouseKit",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!String(nodeData?.name || "").startsWith(PREFIX)) return;

    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = onCreated?.apply(this, arguments);
      try { attachKit(this, nodeData); } catch (e) { /* never break the node */ }
      return r;
    };

    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (output) {
      const r = onExecuted?.apply(this, arguments);
      const st = this[ST];
      if (st) {
        const ms = st.t0 ? Date.now() - st.t0 : 0;
        st.fullError = "";
        setStatus(st, ms ? `ran in ${(ms / 1000).toFixed(2)}s` : "ran", "ok");
      }
      return r;
    };
  },

  async setup() {
    // Execution start: stamp the node that is running.
    api.addEventListener("executing", ({ detail }) => {
      const id = detail;
      if (id == null) return;
      const node = app.graph?.getNodeById?.(Number(id));
      const st = node && node[ST];
      if (st) { st.t0 = Date.now(); st.fullError = ""; setStatus(st, "running…", ""); }
    });

    // Execution error: this is the whole point of the kit.
    api.addEventListener("execution_error", ({ detail }) => {
      const node = app.graph?.getNodeById?.(Number(detail?.node_id));
      const st = node && node[ST];
      if (!st) return;
      const raw = [detail?.exception_message, ...(detail?.traceback || [])]
        .filter(Boolean).join("\n");
      st.fullError = raw;                       // full text on hover, for a report
      setStatus(st, humaniseError(raw), "error");
      node.setDirtyCanvas(true, true);
    });

    api.addEventListener("execution_interrupted", () => {
      for (const n of app.graph?._nodes || []) {
        const st = n[ST];
        if (st && st.t0) setStatus(st, "cancelled", "");
      }
    });
  },
});
