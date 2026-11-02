// viewer_pro_core.js — the pure logic of NukeMax Viewer Pro (owner Rev 3 Part 19.12; ledger L9.80 slice 7a).
// No DOM, no ComfyUI import: tested under node (tests/test_viewer_pro.py).
//
// VIEW maths only: nothing here changes the image the graph carries.
// PORTED FROM: the C2C Custom Node Packs player core, js/_c2c_player_core.js timecode() (Code2Collapse, Apache-2.0;
// same author). Named without its folder: this pack must never reference a sibling pack (test_web_wiring R10).

// ---- half floats (the proxies are RGBA float16) ------------------------------------------------------------------
const HALF = (() => {
    const t = new Float32Array(65536);
    for (let h = 0; h < 65536; h++) {
        const s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 0x1f, m = h & 0x3ff;
        t[h] = e === 0 ? s * 2 ** -14 * (m / 1024) : e === 31 ? (m ? NaN : s * Infinity) : s * 2 ** (e - 15) * (1 + m / 1024);
    }
    return t;
})();

export function halfToFloat(u16) {
    const out = new Float32Array(u16.length);
    for (let i = 0; i < u16.length; i++) out[i] = HALF[u16[i]];
    return out;
}

// ---- display ------------------------------------------------------------------------------------------------------
export const CHANNELS = ["rgb", "r", "g", "b", "a", "luma"];
export const LUMA = [0.2126, 0.7152, 0.0722];

export function srgbEncode(v) {
    if (!(v > 0)) return 0;
    return v <= 0.0031308 ? 12.92 * v : 1.055 * Math.pow(v, 1 / 2.4) - 0.055;
}

export function defaults() {
    return { channel: "rgb", exposure: 0, gamma: 1, gain: 1, checker: true, display: "sRGB" };
}

/**
 * Proxy RGBA float32 -> display RGBA 8-bit (a NEW buffer; the source is never written).
 * Order, as in Nuke's viewer: gain x 2^exposure (linear) -> channel -> display transform -> viewer gamma.
 * Alpha over a checkerboard assumes premultiplied colour (EXR's convention): shown = rgb + (1 - a) * board.
 */
export function renderView(src, w, h, o, out) {
    const k = (o.gain ?? 1) * Math.pow(2, o.exposure ?? 0);
    const ig = 1 / Math.max(0.01, o.gamma ?? 1);
    const enc = o.display === "raw" ? (v) => (v > 0 ? v : 0) : srgbEncode;
    const ch = o.channel || "rgb";
    const board = ch === "rgb" && o.checker;
    const cell = Math.max(4, Math.round(Math.max(w, h) / 48));
    const dst = out || new Uint8ClampedArray(w * h * 4);
    const to8 = (v) => {
        let x = enc(v);
        if (ig !== 1 && x > 0) x = Math.pow(x, ig);
        return x * 255 + 0.5;
    };
    for (let y = 0, p = 0; y < h; y++) {
        for (let x = 0; x < w; x++, p += 4) {
            let r = src[p] * k, g = src[p + 1] * k, b = src[p + 2] * k;
            const a = src[p + 3];
            if (ch === "r") g = b = r;
            else if (ch === "g") r = b = g;
            else if (ch === "b") r = g = b;
            else if (ch === "a") r = g = b = a;
            else if (ch === "luma") r = g = b = LUMA[0] * r + LUMA[1] * g + LUMA[2] * b;
            else if (board && a < 1) {
                const bg = ((Math.floor(x / cell) + Math.floor(y / cell)) & 1) ? 0.35 : 0.18;
                const t = (1 - (a > 0 ? a : 0)) * bg;
                r += t; g += t; b += t;
            }
            dst[p] = to8(r); dst[p + 1] = to8(g); dst[p + 2] = to8(b); dst[p + 3] = 255;
        }
    }
    return dst;
}

// ---- view geometry ------------------------------------------------------------------------------------------------
/** The view that fits the image in the box, centred. */
export function fit(boxW, boxH, imgW, imgH) {
    const s = Math.min(boxW / imgW, boxH / imgH);
    return { scale: s, x: (boxW - imgW * s) / 2, y: (boxH - imgH * s) / 2 };
}

/** 1:1 (one SOURCE pixel per screen pixel), centred. ``proxyScale`` = proxy width / source width. */
export function actual(boxW, boxH, imgW, imgH, proxyScale = 1) {
    const s = 1 / proxyScale;
    return { scale: s, x: (boxW - imgW * s) / 2, y: (boxH - imgH * s) / 2 };
}

/** Zoom by ``factor`` keeping the point under (px, py) still. */
export function zoomAt(v, factor, px, py) {
    const s = Math.min(64, Math.max(0.02, v.scale * factor));
    const f = s / v.scale;
    return { scale: s, x: px - (px - v.x) * f, y: py - (py - v.y) * f };
}

/** Screen point -> proxy pixel (may lie outside the image). */
export function toImage(v, px, py) {
    return [(px - v.x) / v.scale, (py - v.y) / v.scale];
}

// ---- time ---------------------------------------------------------------------------------------------------------
/** hh:mm:ss:ff from a frame index (ff counts frames inside the second). */
export function timecode(frame, fps) {
    if (!(fps > 0)) return "";
    const f = Math.max(0, Math.round(frame));
    const whole = Math.max(1, Math.round(fps));
    const ff = f % whole;
    const total = Math.floor(f / whole);
    const s = total % 60, m = Math.floor(total / 60) % 60, h = Math.floor(total / 3600);
    const p = (n) => String(n).padStart(2, "0");
    return `${p(h)}:${p(m)}:${p(s)}:${p(ff)}`;
}

/** A value for the probe: 4 significant digits, HDR-friendly. */
export function fmt(v) {
    if (!Number.isFinite(v)) return String(v);
    const a = Math.abs(v);
    return a >= 1000 ? v.toFixed(0) : a >= 10 ? v.toFixed(2) : v.toFixed(4);
}

// ---- a bounded cache ----------------------------------------------------------------------------------------------
export class LRU {
    constructor(capacity = 64) { this.cap = capacity; this.map = new Map(); }
    get(k) {
        if (!this.map.has(k)) return undefined;
        const v = this.map.get(k);
        this.map.delete(k); this.map.set(k, v);
        return v;
    }
    set(k, v) {
        this.map.delete(k); this.map.set(k, v);
        while (this.map.size > this.cap) this.map.delete(this.map.keys().next().value);
    }
    get size() { return this.map.size; }
    clear() { this.map.clear(); }
}
