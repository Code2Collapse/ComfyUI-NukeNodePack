// _nukemax_theme.js — one place this pack gets its colours from.
//
// The pack had none: 111 literal hexes spread across seven widget files, so
// nothing followed the theme and nothing matched the other packs. Everything
// here resolves through a CHAIN instead, most specific first:
//
//   1. --c2c-*            published on :root by CustomNodePacks' theme, which
//                         owns the house palette and its variants
//   2. a ComfyUI core var so a NukeMax-only install still follows whatever
//      palette the user picked in ComfyUI itself
//   3. a literal, which is the colour this pack already shipped
//
// Nothing is imported from another pack. A cross-pack import would 404 the
// moment someone installed NukeMax on its own, and a 404 on a module import
// is not contained - it fails the whole graph of pack modules with it.
//
// Two forms on purpose:
//
//   cssVar("panel")  ->  "var(--c2c-panelBg, var(--comfy-menu-bg, #2a2a2a))"
//                        for a style string, so it re-resolves live when the
//                        palette changes without anything repainting
//   color("panel")   ->  "#1e1f47", an actual colour, because a canvas cannot
//                        parse var(): assigning one to fillStyle leaves the
//                        shape BLACK and throws nothing. That has bitten this
//                        workspace before - a whole progress bar painted black
//                        because a var() reached a 2D context.

const CHAIN = {
  bg:       ["--c2c-bg", "--bg-color", "#1a1a1a"],
  panel:    ["--c2c-panelBg", "--comfy-menu-bg", "#2a2a2a"],
  inputBg:  ["--c2c-surface0", "--comfy-input-bg", "#222222"],
  border:   ["--c2c-border", "--border-color", "#4a4a4a"],
  fg:       ["--c2c-fg", "--fg-color", "#dddddd"],
  text:     ["--c2c-fg", "--input-text", "#dddddd"],
  dim:      ["--c2c-dim", "--descrip-text", "#999999"],
  accent:   ["--c2c-mauve", "--p-primary-color", "#4cc3ff"],
  ok:       ["--c2c-ok", null, "#7ee0a8"],
  warn:     ["--c2c-warn", null, "#ffd166"],
  danger:   ["--c2c-danger", null, "#e06c6c"],
  grid:     ["--c2c-surface1", null, "#333333"],
  // A drawing ground INSIDE a widget - the roto canvas, a plot area. Distinct
  // from `inputBg` (a form control) and from `grid` (hairlines), which happen
  // to sit at neighbouring tiers; naming them apart keeps a later tweak to one
  // from silently moving the other two.
  well:     ["--c2c-surface1", "--comfy-input-bg", "#222222"],
  onAccent: ["--c2c-scrimDark", null, "#111111"],
};

// The family badge hues, as PALETTE keys rather than hexes, so the badges move
// with the variant instead of being twenty-six fixed colours that clash with
// whatever ground is behind them. The literal is what this pack shipped, kept
// as the standalone fallback.
const FAMILY = {
  Color:      ["peach",  "#c8894a"],
  Filter:     ["blue",   "#5a8fc8"],
  Merge:      ["green",  "#7db35a"],
  Keying:     ["teal",   "#4fb3a5"],
  Transform:  ["mauve",  "#a07cc8"],
  Deep:       ["maroon", "#c85a7d"],
  Mocha:      ["yellow", "#d1a33a"],
  OCIO:       ["peach",  "#c8894a"],
  IO:         ["overlay2", "#8a8a8a"],
  Roto:       ["red",    "#d16a6a"],
  Flow:       ["sky",    "#5aa8c8"],
  Relight:    ["yellow", "#d1a33a"],
  Generate:   ["overlay2", "#8a8a8a"],
  Channel:    ["green",  "#7db35a"],
  FFT:        ["sky",    "#5aa8c8"],
  Edges:      ["teal",   "#4fb3a5"],
  Lens:       ["mauve",  "#a07cc8"],
  Audio:      ["maroon", "#c85a7d"],
  Time:       ["overlay2", "#8a8a8a"],
  NkScript:   ["overlay2", "#8a8a8a"],
  HDR:        ["peach",  "#e0a24a"],
  Viewer:     ["sapphire", "#6fa8d1"],
  Geometry:   ["mauve",  "#a07cc8"],
  Metadata:   ["overlay2", "#8a8a8a"],
  PlateTools: ["green",  "#7db35a"],
  Render:     ["maroon", "#c85a7d"],
  Utils:      ["overlay2", "#8a8a8a"],
};

/** A style-string value that keeps re-resolving as the palette changes. */
export function cssVar(name) {
  const c = CHAIN[name];
  if (!c) return "";
  const [ours, core, lit] = c;
  return core ? `var(${ours}, var(${core}, ${lit}))` : `var(${ours}, ${lit})`;
}

// getComputedStyle is not free and these are read inside paint loops, so the
// resolved values are cached and dropped when the palette actually changes.
let _cache = new Map();

function readVar(prop) {
  if (typeof document === "undefined") return "";
  try {
    return getComputedStyle(document.documentElement)
      .getPropertyValue(prop).trim();
  } catch {
    return "";
  }
}

/** A real colour, for canvas. Never returns a var() string. */
export function color(name) {
  if (_cache.has(name)) return _cache.get(name);
  const c = CHAIN[name];
  if (!c) return "";
  const [ours, core, lit] = c;
  const v = readVar(ours) || (core ? readVar(core) : "") || lit;
  _cache.set(name, v);
  return v;
}

/** The badge colour for a node family, as a real colour. */
export function familyColor(family) {
  const entry = FAMILY[family];
  if (!entry) return color("dim");
  const key = "family:" + family;
  if (_cache.has(key)) return _cache.get(key);
  const v = readVar("--c2c-" + entry[0]) || entry[1];
  _cache.set(key, v);
  return v;
}

export function familyNames() {
  return Object.keys(FAMILY);
}

/** Text that sits ON a badge. The badge hues are light, so this stays dark. */
export function onBadge() {
  return color("onAccent");
}

function flush() {
  _cache = new Map();
}

if (typeof window !== "undefined") {
  // CustomNodePacks fires this when the user switches variant; ComfyUI fires
  // its own when the core palette changes. Either invalidates every cached
  // colour - without this the pack keeps painting the previous theme until
  // the page is reloaded.
  window.addEventListener("c2c:theme-changed", flush);
  document.addEventListener?.("comfy:palette-changed", flush);
}

export { flush as invalidateThemeCache };
