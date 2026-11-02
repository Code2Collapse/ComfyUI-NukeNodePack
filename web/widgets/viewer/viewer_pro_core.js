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
    // 7c: an OCIO display / view (the OCIO Player) baked to a LUT behind a log2 shaper, applied to r g b together
    const lut = o.display === "ocio" && o.lut ? o.lut : null;
    const tmp = [0, 0, 0];
    const gam8 = (x) => ((ig !== 1 && x > 0) ? Math.pow(x, ig) : x) * 255 + 0.5;
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
            if (lut) {
                lutApply(lut, r, g, b, tmp);
                dst[p] = gam8(tmp[0]); dst[p + 1] = gam8(tmp[1]); dst[p + 2] = gam8(tmp[2]); dst[p + 3] = 255;
                continue;
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

// ---- 7b: measurements (scopes, statistics, false colour, zebra, focus peaking) --------------------------------------
// All of them read the proxy and the view settings; none writes the source.

/** What the eye sees: linear x gain x 2^exposure -> display transform -> viewer gamma, as 0..1 (not clipped above). */
export function encode(v, o) {
    const k = (o.gain ?? 1) * Math.pow(2, o.exposure ?? 0);
    let x = (o.display === "raw") ? Math.max(0, v * k) : srgbEncode(v * k);
    const g = Math.max(0.01, o.gamma ?? 1);
    if (g !== 1 && x > 0) x = Math.pow(x, 1 / g);
    return x;
}

/** False-colour bands, in stops from 18 % grey (scene-linear luma): [upper bound, rgb, label]. */
export const FALSE_BANDS = [
    [-6, [80, 0, 120], "below -6 stops"], [-4, [40, 70, 210], "-6 to -4"], [-2, [0, 150, 170], "-4 to -2"],
    [-0.5, [100, 120, 100], "-2 to -0.5"], [0.5, [60, 200, 70], "18 % grey ±0.5"], [2, [200, 200, 200], "+0.5 to +2"],
    [3, [240, 225, 60], "+2 to +3"], [4, [250, 140, 30], "+3 to +4"], [Infinity, [235, 40, 40], "above +4 stops"],
];

export function stopsOf(l) {
    return l > 0 ? Math.log2(l / 0.18) : -Infinity;
}

export function falseColour(l) {
    const s = stopsOf(l);
    for (const [hi, rgb] of FALSE_BANDS) if (s < hi) return rgb;
    return FALSE_BANDS[FALSE_BANDS.length - 1][1];
}

/**
 * One pass over the frame: histograms of the DISPLAYED values (r g b luma, 256 bins), the scene-linear luma in stops
 * (-8 .. +8 around 18 % grey, 0.5-stop bins: the exposure distribution) and raw statistics of the DATA (no view
 * adjustment): min / max / mean per channel, peak luma and its stops, pixels above 1.0 and below 0.
 */
export function measure(src, w, h, o) {
    const n = w * h;
    const hist = { r: new Uint32Array(256), g: new Uint32Array(256), b: new Uint32Array(256), l: new Uint32Array(256) };
    const stops = new Uint32Array(33);
    const min = [Infinity, Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity, -Infinity];
    const sum = [0, 0, 0, 0];
    let peak = -Infinity, above1 = 0, negative = 0;
    const bin = (v) => Math.max(0, Math.min(255, Math.round(v * 255)));
    for (let i = 0, p = 0; i < n; i++, p += 4) {
        const r = src[p], g = src[p + 1], b = src[p + 2], a = src[p + 3];
        const vals = [r, g, b, a];
        for (let c = 0; c < 4; c++) {
            const v = vals[c];
            if (v < min[c]) min[c] = v;
            if (v > max[c]) max[c] = v;
            sum[c] += v;
        }
        if (r > 1 || g > 1 || b > 1) above1++;
        if (r < 0 || g < 0 || b < 0) negative++;
        const l = LUMA[0] * r + LUMA[1] * g + LUMA[2] * b;
        if (l > peak) peak = l;
        hist.r[bin(encode(r, o))]++; hist.g[bin(encode(g, o))]++; hist.b[bin(encode(b, o))]++; hist.l[bin(encode(l, o))]++;
        const s = stopsOf(l);
        stops[Number.isFinite(s) ? Math.max(0, Math.min(32, Math.round((s + 8) * 2))) : 0]++;
    }
    return {
        hist, stops, pixels: n,
        stats: { min, max, mean: sum.map((x) => x / Math.max(1, n)), peakLuma: peak, peakStops: stopsOf(peak),
                 above1, negative },
    };
}

/** Waveform image (W x H RGBA): luma, or an RGB parade (three side-by-side waveforms). */
export function waveform(src, w, h, o, W, H, mode = "luma") {
    const acc = new Float32Array(W * H * 3);
    const parade = mode === "parade";
    const colW = parade ? Math.floor(W / 3) : W;
    for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
            const p = (y * w + x) * 4;
            if (parade) {
                for (let c = 0; c < 3; c++) {
                    const X = c * colW + Math.min(colW - 1, Math.floor(x * colW / w));
                    const Y = H - 1 - Math.max(0, Math.min(H - 1, Math.round(Math.min(1, encode(src[p + c], o)) * (H - 1))));
                    acc[(Y * W + X) * 3 + c] += 1;
                }
            } else {
                const l = LUMA[0] * src[p] + LUMA[1] * src[p + 1] + LUMA[2] * src[p + 2];
                const X = Math.min(W - 1, Math.floor(x * W / w));
                const Y = H - 1 - Math.max(0, Math.min(H - 1, Math.round(Math.min(1, encode(l, o)) * (H - 1))));
                const q = (Y * W + X) * 3;
                acc[q] += 1; acc[q + 1] += 1; acc[q + 2] += 1;
            }
        }
    }
    return glow(acc, W, H, h);
}

/** Vectorscope image (S x S RGBA): Rec.709 Cb / Cr of the displayed colour, 75 % of the radius = full saturation. */
export function vectorscope(src, w, h, o, S) {
    const acc = new Float32Array(S * S * 3);
    const c0 = S / 2, rad = S * 0.45;
    for (let i = 0, p = 0; i < w * h; i++, p += 4) {
        const r = Math.min(1, encode(src[p], o)), g = Math.min(1, encode(src[p + 1], o)), b = Math.min(1, encode(src[p + 2], o));
        const y = LUMA[0] * r + LUMA[1] * g + LUMA[2] * b;
        const cb = (b - y) / 1.8556, cr = (r - y) / 1.5748;
        const X = Math.round(c0 + cb * 2 * rad), Y = Math.round(c0 - cr * 2 * rad);
        if (X < 0 || Y < 0 || X >= S || Y >= S) continue;
        const q = (Y * S + X) * 3;
        acc[q] += r; acc[q + 1] += g; acc[q + 2] += b;
    }
    return glow(acc, S, S, Math.sqrt(w * h) / 4);
}

function glow(acc, W, H, norm) {
    const out = new Uint8ClampedArray(W * H * 4);
    const k = 255 / Math.max(1, Math.log1p(norm));
    for (let i = 0; i < W * H; i++) {
        out[i * 4] = Math.log1p(acc[i * 3]) * k;
        out[i * 4 + 1] = Math.log1p(acc[i * 3 + 1]) * k;
        out[i * 4 + 2] = Math.log1p(acc[i * 3 + 2]) * k;
        out[i * 4 + 3] = 255;
    }
    return out;
}

/**
 * Overlays on the DISPLAYED buffer ``dst`` (in place - the source is untouched):
 *  falseColour: every pixel in its stops band; zebra: diagonal stripes where the displayed value reaches o.zebra
 *  (default 0.95); peaking: green where the displayed luma's Sobel edge is above o.peaking (default 0.15).
 */
export function overlays(src, w, h, o, dst) {
    if (o.falseColour) {
        for (let i = 0, p = 0; i < w * h; i++, p += 4) {
            const c = falseColour(LUMA[0] * src[p] + LUMA[1] * src[p + 1] + LUMA[2] * src[p + 2]);
            dst[p] = c[0]; dst[p + 1] = c[1]; dst[p + 2] = c[2];
        }
    }
    if (o.zebraOn) {
        const t = o.zebra ?? 0.95;
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                const p = (y * w + x) * 4;
                const m = Math.max(encode(src[p], o), encode(src[p + 1], o), encode(src[p + 2], o));
                if (m >= t && ((x + y) >> 2) & 1) { dst[p] = 255; dst[p + 1] = 0; dst[p + 2] = 255; }
            }
        }
    }
    if (o.peakingOn) {
        const t = o.peaking ?? 0.15;
        const L = new Float32Array(w * h);
        for (let i = 0, p = 0; i < w * h; i++, p += 4) L[i] = Math.min(1, encode(LUMA[0] * src[p] + LUMA[1] * src[p + 1] + LUMA[2] * src[p + 2], o));
        // o.peakingWidth (>= 0): marks are widened by that many proxy pixels, so a one-pixel edge survives a view drawn
        // below 100 % (a smoothed downscale blended it away - L9.80 slice 7b, live)
        const rad = Math.max(0, Math.round(o.peakingWidth || 0));
        const mark = new Uint8Array(w * h);
        for (let y = 1; y < h - 1; y++) {
            for (let x = 1; x < w - 1; x++) {
                const i = y * w + x;
                const gx = -L[i - w - 1] - 2 * L[i - 1] - L[i + w - 1] + L[i - w + 1] + 2 * L[i + 1] + L[i + w + 1];
                const gy = -L[i - w - 1] - 2 * L[i - w] - L[i - w + 1] + L[i + w - 1] + 2 * L[i + w] + L[i + w + 1];
                if (Math.hypot(gx, gy) / 4 > t) {
                    for (let dy = -rad; dy <= rad; dy++) {
                        const yy = y + dy;
                        if (yy < 0 || yy >= h) continue;
                        for (let dx = -rad; dx <= rad; dx++) {
                            const xx = x + dx;
                            if (xx >= 0 && xx < w) mark[yy * w + xx] = 1;
                        }
                    }
                }
            }
        }
        for (let i = 0; i < w * h; i++) if (mark[i]) { const p = i * 4; dst[p] = 40; dst[p + 1] = 255; dst[p + 2] = 60; }
    }
    return dst;
}


// ---- 7c: compare and the OCIO Player --------------------------------------------------------------------------------
/** A display / view LUT ({size, lo, hi, data: Float32Array size^3 x 3, r major}) applied to linear r g b. */
export function lutApply(lut, r, g, b, out = [0, 0, 0]) {
    const n = lut.size, d = lut.data, span = lut.hi - lut.lo;
    const coord = (v) => {
        const st = v > 0 ? Math.log2(v / 0.18) : lut.lo;
        return Math.max(0, Math.min(1, (st - lut.lo) / span)) * (n - 1);
    };
    const fr = coord(r), fg = coord(g), fb = coord(b);
    const r0 = Math.min(n - 2, Math.floor(fr)), g0 = Math.min(n - 2, Math.floor(fg)), b0 = Math.min(n - 2, Math.floor(fb));
    const tr = fr - r0, tg = fg - g0, tb = fb - b0;
    for (let c = 0; c < 3; c++) {
        const at = (i, j, k) => d[((i * n + j) * n + k) * 3 + c];
        const c00 = at(r0, g0, b0) * (1 - tb) + at(r0, g0, b0 + 1) * tb;
        const c01 = at(r0, g0 + 1, b0) * (1 - tb) + at(r0, g0 + 1, b0 + 1) * tb;
        const c10 = at(r0 + 1, g0, b0) * (1 - tb) + at(r0 + 1, g0, b0 + 1) * tb;
        const c11 = at(r0 + 1, g0 + 1, b0) * (1 - tb) + at(r0 + 1, g0 + 1, b0 + 1) * tb;
        out[c] = (c00 * (1 - tg) + c01 * tg) * (1 - tr) + (c10 * (1 - tg) + c11 * tg) * tr;
    }
    return out;
}

/** |A - B| per channel (alpha 1), as linear data to view like an image. B is sampled to A's size. */
export function difference(a, b, w, h, bw, bh) {
    const out = new Float32Array(w * h * 4);
    for (let y = 0; y < h; y++) {
        const by = Math.min(bh - 1, Math.floor(y * bh / h));
        for (let x = 0; x < w; x++) {
            const bx = Math.min(bw - 1, Math.floor(x * bw / w));
            const p = (y * w + x) * 4, q = (by * bw + bx) * 4;
            out[p] = Math.abs(a[p] - b[q]); out[p + 1] = Math.abs(a[p + 1] - b[q + 1]); out[p + 2] = Math.abs(a[p + 2] - b[q + 2]);
            out[p + 3] = 1;
        }
    }
    return out;
}

/** The difference as a heatmap: luma of |A - B| over its own maximum, black -> blue -> green -> yellow -> red. */
export function heatmap(diff, w, h, out) {
    let top = 1e-9;
    const n = w * h;
    const L = new Float32Array(n);
    for (let i = 0, p = 0; i < n; i++, p += 4) { L[i] = LUMA[0] * diff[p] + LUMA[1] * diff[p + 1] + LUMA[2] * diff[p + 2]; if (L[i] > top) top = L[i]; }
    const stops = [[0, 0, 0], [0, 60, 255], [0, 220, 90], [255, 230, 0], [255, 30, 30]];
    const dst = out || new Uint8ClampedArray(n * 4);
    for (let i = 0; i < n; i++) {
        const t = Math.min(1, L[i] / top) * (stops.length - 1);
        const k = Math.min(stops.length - 2, Math.floor(t)), f = t - k;
        for (let c = 0; c < 3; c++) dst[i * 4 + c] = stops[k][c] * (1 - f) + stops[k + 1][c] * f;
        dst[i * 4 + 3] = 255;
    }
    return { image: dst, max: top };
}

/** Split: columns left of ``at`` (0..1 of the width) from A's display buffer, the rest from B's. */
export function split(aBuf, bBuf, w, h, at, out) {
    const dst = out || new Uint8ClampedArray(w * h * 4);
    const cut = Math.round(Math.max(0, Math.min(1, at)) * w);
    for (let y = 0; y < h; y++) {
        const row = y * w * 4;
        dst.set(aBuf.subarray(row, row + cut * 4), row);
        dst.set(bBuf.subarray(row + cut * 4, row + w * 4), row + cut * 4);
    }
    return dst;
}
