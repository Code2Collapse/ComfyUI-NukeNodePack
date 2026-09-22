// hdr_curves.js — the transfer functions of the NukeMax/HDR family, in JS.
//
// WHY THIS FILE EXISTS SEPARATELY: the on-node curve plot is only worth having
// if it is the curve the node ACTUALLY applies. A plot drawn from a
// hand-waved approximation is worse than no plot - it tells the compositor a
// confident lie about where their highlights are going.
//
// So this module mirrors nukemax/nodes/hdr/nodes.py line for line, and
// tests/test_hdr_curves.py drives THIS file through node and compares it
// against the Python on a ramp. If the two drift, that test fails.
//
// It deliberately imports nothing from ComfyUI, which is what makes that
// possible. Keep it that way.

// ── tone map operators (mirrors _TonemapOps.apply_torch) ────────────────────

function uncharted2Curve(v) {
  const a = 0.15, b = 0.5, c = 0.1, d = 0.2, e = 0.02, f = 0.3;
  return (v * (a * v + c * b) + d * e) / (v * (a * v + b) + d * f) - e / f;
}

export function toneMapOperator(x, operator, whitePoint) {
  const wp = whitePoint;
  switch (operator) {
    case "reinhard":
      return x / (1.0 + x);
    case "reinhard_extended": {
      const wsq = wp * wp;
      return (x * (1.0 + x / wsq)) / (1.0 + x);
    }
    case "reinhard_luminance": {
      // On a neutral ramp the Rec.709 weights sum to 1, so the luminance form
      // reduces to the scalar one. (This is only ever plotted on a ramp.)
      const luma = Math.max(x, 1e-6);
      const wsq = wp * wp;
      const tm = (luma * (1.0 + luma / wsq)) / (1.0 + luma);
      return x * (tm / luma);
    }
    case "filmic_aces": {
      const a = 2.51, b = 0.03, c = 2.43, d = 0.59, e = 0.14;
      const s = x / (wp + 1e-8);
      return Math.min(1, Math.max(0, (s * (a * s + b)) / (s * (c * s + d) + e)));
    }
    case "filmic_uncharted2":
      return uncharted2Curve(x) * (1.0 / uncharted2Curve(wp));
    case "agx": {
      let v = Math.max(x, 1e-10);
      v = Math.log2(v) / 16.0 + 0.5;
      v = Math.min(1, Math.max(0, v));
      return v * v * (3.0 - 2.0 * v);
    }
    case "linear_clamp":
      return Math.min(1, Math.max(0, x / wp));
    default:                       // "exposure_only" and anything unknown
      return Math.min(1, Math.max(0, x));
  }
}

/** Presets, mirroring HDRToneMap.PRESETS. */
export const TONEMAP_PRESETS = {
  "Cinematic Film": {
    operator: "filmic_aces", exposure: 0.0, gamma: 2.2, white_point: 1.0,
    contrast: 1.1, saturation: 0.95, highlight_compression: 0.8, shadow_lift: 0.02,
  },
  "HDR Display": {
    operator: "agx", exposure: 0.3, gamma: 2.2, white_point: 2.0,
    contrast: 1.0, saturation: 1.1, highlight_compression: 0.5, shadow_lift: 0.0,
  },
  "Web / Social": {
    operator: "filmic_aces", exposure: 0.2, gamma: 2.2, white_point: 1.0,
    contrast: 1.15, saturation: 1.1, highlight_compression: 0.9, shadow_lift: 0.01,
  },
};

/**
 * The WHOLE node response for one neutral input value, not just the operator:
 * exposure, highlight compression, shadow lift, operator, contrast, clamp and
 * the output gamma, in the order HDRToneMap.execute applies them. Saturation
 * is a no-op on a neutral ramp and is skipped.
 */
export function toneMapResponse(x, p) {
  const cfg = (p.preset && p.preset !== "None (Custom)" && TONEMAP_PRESETS[p.preset])
    ? { ...p, ...TONEMAP_PRESETS[p.preset] }
    : p;

  let v = x * Math.pow(2.0, cfg.exposure ?? 0);

  const hc = cfg.highlight_compression ?? 0;
  if (hc > 0) {
    const t = 1.0 - hc * 0.5;
    if (v > t) v = t + (v - t) / (1.0 + (v - t) * hc * 2);
  }

  const sl = cfg.shadow_lift ?? 0;
  if (sl > 0) v = v + sl * (1.0 - v);

  v = toneMapOperator(v, cfg.operator ?? "filmic_aces", cfg.white_point ?? 1.0);

  const contrast = cfg.contrast ?? 1.0;
  if (contrast !== 1.0) v = (v - 0.5) * contrast + 0.5;

  v = Math.min(1, Math.max(0, v));
  return Math.pow(v, 1.0 / (cfg.gamma ?? 2.2));
}

// ── highlight expansion (mirrors HDRExpandDynamicRange.execute) ─────────────

/** sRGB / power decode, mirroring tensor_srgb_to_linear. */
export function srgbToLinear(x, gamma) {
  if (Math.abs(gamma - 1.0) < 0.01) return x;
  const sign = Math.sign(x);
  const a = Math.abs(x);
  let lin;
  if (Math.abs(gamma - 2.2) < 0.1) {
    lin = a <= 0.04045 ? a / 12.92 : Math.pow((a + 0.055) / 1.055, 2.4);
  } else {
    lin = Math.pow(a, gamma);
  }
  return sign * lin;
}

/**
 * Code value in -> scene-linear out, for a neutral input. Returns the value the
 * node produces, which is why the plot's y-axis has to be logarithmic: at the
 * default 14 stops a clipped white lands at 64.0, not 1.0.
 */
export function expandResponse(x, p) {
  const gamma = p.source_gamma ?? 2.2;
  const recovery = p.highlight_recovery ?? 1.0;
  const blackPoint = p.black_point ?? 0.0;
  const stops = p.target_stops ?? 14.0;
  const rolloff = p.highlight_rolloff ?? 1.5;

  let lin = srgbToLinear(x, gamma) - blackPoint;
  if (lin < 0) lin = 0;

  const targetPeak = Math.pow(2.0, stops - 8.0);
  const t = Math.max(0.5, Math.min(0.95, 1.0 - (rolloff - 1.0) * 0.2));
  if (!(targetPeak > 1.0 && recovery > 0)) return lin;

  const luma = lin;                        // neutral ramp: luma === the value
  const a = (targetPeak - 1.0) / Math.pow(1.0 - t, 2);
  const clamped = Math.min(luma, 1.0);
  let expanded = luma > t
    ? clamped + a * Math.pow(clamped - t, 2)
    : luma;
  if (luma > 1.0) {
    const slopeAt1 = 1.0 + 2 * a * (1.0 - t);
    expanded = targetPeak + (luma - 1.0) * slopeAt1;
  }
  const finalLuma = expanded * recovery + luma * (1.0 - recovery);
  const ratio = finalLuma / (luma + 1e-8);
  return lin * ratio;
}

/** Where the highlight knee sits, in code values — worth marking on the plot. */
export function expansionKnee(p) {
  const rolloff = p.highlight_rolloff ?? 1.5;
  return Math.max(0.5, Math.min(0.95, 1.0 - (rolloff - 1.0) * 0.2));
}

/** Sample a response across [0, xMax] into {x, y} arrays for plotting. */
export function sampleCurve(fn, params, xMax, samples) {
  const xs = new Float64Array(samples);
  const ys = new Float64Array(samples);
  for (let i = 0; i < samples; i++) {
    const x = (i / (samples - 1)) * xMax;
    xs[i] = x;
    ys[i] = fn(x, params);
  }
  return { xs, ys };
}
