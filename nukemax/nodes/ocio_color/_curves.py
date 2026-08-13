"""Camera log transfer curves — dependency-free, HDR-safe, spec-traceable.

Ported from `third_party/ComfyUI-OCIO/nodes.py` (Copyright (c) 2026 Slava
Sexton, MIT License, https://github.com/... ) with the spec citations kept
verbatim, reshaped onto this pack's helpers.

CONTRACT
--------
Every curve is the transfer CURVE ONLY. The plate keeps its camera-native
primaries, so a `log -> linear` here must be paired with a gamut step
(camera gamut -> ACEScg) from `_primaries.py`, NOT with the config's
same-named colorspace (that one also swaps primaries and you would apply the
gamut twice).

NO CLIPPING. Each encode clamps only the argument that would make a
logarithm undefined, never the input signal. Below-black scene-linear
survives through the finite linear toe every one of these curves defines;
above-white survives because nothing caps the output. Decodes are exact
inverses over the whole domain.

All maths runs in float64 and returns float32.
"""
from __future__ import annotations

from typing import Callable, Dict, Tuple

import numpy as np

# ── Cineon ───────────────────────────────────────────────────────────────
# Nuke's flat film log (OCIO nuke-default): scene-linear 0 -> code 0.0928.
_CINEON_OFF = 10.0 ** ((95.0 - 685.0) / 300.0)  # 0.0107977...


def _lin_to_cineon(x):
    # Clamp the LOG ARGUMENT, not the input: below-black scene-linear survives
    # wherever the log is still defined (arg > 0). Only floors where log10 is
    # genuinely undefined.
    x = np.asarray(x, np.float64)
    arg = np.maximum(x * (1.0 - _CINEON_OFF) + _CINEON_OFF, 1e-10)
    return ((685.0 + 300.0 * np.log10(arg)) / 1023.0).astype(np.float32)


def _cineon_to_lin(y):
    y = np.asarray(y, np.float64)
    return ((10.0 ** ((1023.0 * y - 685.0) / 300.0) - _CINEON_OFF)
            / (1.0 - _CINEON_OFF)).astype(np.float32)


# ── ACEScct / ACEScc ─────────────────────────────────────────────────────
# ACEScct: ACES S-2016-001 (log with a linear toe, black -> 0.0729).
# ACEScc:  ACES S-2014-003 (pure log).
def _lin_to_acescct(x):
    x = np.asarray(x, np.float64)
    return np.where(x <= 0.0078125, 10.5402377416545 * x + 0.0729055341958355,
                    (np.log2(np.maximum(x, 1e-10)) + 9.72) / 17.52).astype(np.float32)


def _acescct_to_lin(y):
    y = np.asarray(y, np.float64)
    return np.where(y <= 0.155251141552511, (y - 0.0729055341958355) / 10.5402377416545,
                    np.exp2(y * 17.52 - 9.72)).astype(np.float32)


def _lin_to_acescc(x):
    x = np.asarray(x, np.float64)
    return np.where(
        x <= 0.0, (np.log2(2.0 ** -16) + 9.72) / 17.52,
        np.where(x < 2.0 ** -15,
                 (np.log2(np.maximum(2.0 ** -16 + x * 0.5, 2.0 ** -16)) + 9.72) / 17.52,
                 (np.log2(np.maximum(x, 2.0 ** -16)) + 9.72) / 17.52)).astype(np.float32)


def _acescc_to_lin(y):
    y = np.asarray(y, np.float64)
    return np.where(
        y < (9.72 - 15.0) / 17.52, (np.exp2(y * 17.52 - 9.72) - 2.0 ** -16) * 2.0,
        np.where(y < (np.log2(65504.0) + 9.72) / 17.52,
                 np.exp2(y * 17.52 - 9.72), 65504.0)).astype(np.float32)


# ── ARRI LogC3 (EI 800) ──────────────────────────────────────────────────
# Published ARRI constants. Curve ONLY — pair with ARRI Wide Gamut 3.
_LC3_A, _LC3_B, _LC3_C, _LC3_D = 5.555556, 0.052272, 0.247190, 0.385537
_LC3_E, _LC3_F, _LC3_CUT = 5.367655, 0.092809, 0.010591


def _lin_to_logc3(x):
    # No maximum(x, 0): the finite linear toe (E*x + F) preserves below-black
    # scene-linear (matches ARRI); the log branch only fires for x >= CUT > 0.
    x = np.asarray(x, np.float64)
    return np.where(x >= _LC3_CUT,
                    _LC3_C * np.log10(_LC3_A * np.maximum(x, _LC3_CUT) + _LC3_B) + _LC3_D,
                    _LC3_E * x + _LC3_F).astype(np.float32)


def _logc3_to_lin(y):
    y = np.asarray(y, np.float64)
    cut_log = _LC3_E * _LC3_CUT + _LC3_F
    return np.where(y >= cut_log, (10.0 ** ((y - _LC3_D) / _LC3_C) - _LC3_B) / _LC3_A,
                    (y - _LC3_F) / _LC3_E).astype(np.float32)


# ── ARRI LogC4 ───────────────────────────────────────────────────────────
# ARRI LogC4 Specification (1 May 2022). Ceiling ~469.8 linear. Piecewise
# split at the spec point (encoded V=0): linear toe below, log above.
_LC4_A = (2.0 ** 18 - 16) / 117.45           # 2231.8263...
_LC4_B = (1023.0 - 95.0) / 1023.0            # 0.9071358...
_LC4_C = 95.0 / 1023.0                       # 0.0928641...
_LC4_S = (7.0 * np.log(2.0) * 2.0 ** (7.0 - 14.0 * _LC4_C / _LC4_B)) / (_LC4_A * _LC4_B)
_LC4_T = (2.0 ** (14.0 * (-_LC4_C / _LC4_B) + 6.0) - 64.0) / _LC4_A   # -0.018060...


def _lin_to_logc4(x):
    x = np.asarray(x, np.float64)
    xc = np.maximum(x, _LC4_T)  # guard the discarded log branch from log2(<=0)
    return np.where(x >= _LC4_T,
                    (np.log2(_LC4_A * xc + 64.0) - 6.0) / 14.0 * _LC4_B + _LC4_C,
                    (x - _LC4_T) / _LC4_S).astype(np.float32)


def _logc4_to_lin(y):
    y = np.asarray(y, np.float64)
    return np.where(y >= 0.0, (2.0 ** (14.0 * (y - _LC4_C) / _LC4_B + 6.0) - 64.0) / _LC4_A,
                    y * _LC4_S + _LC4_T).astype(np.float32)


# ── Sony S-Log3 ──────────────────────────────────────────────────────────
# Sony "Technical Summary for S-Gamut3.Cine/S-Log3", Appendix "S-Log3 Formula".
# Anchors from the same doc: 0% black -> CV 95, 18% grey -> CV 420, 90% -> ~598.
_SL3_CUT_LIN = 0.01125000
_SL3_B95, _SL3_B171 = 95.0, 171.2102946929
_SL3_CUT_LOG = _SL3_B171 / 1023.0


def _lin_to_slog3(x):
    x = np.asarray(x, np.float64)
    xc = np.maximum(x + 0.01, 1e-10)  # guard the discarded log branch
    return np.where(x >= _SL3_CUT_LIN, (420.0 + np.log10(xc / 0.19) * 261.5) / 1023.0,
                    (x * (_SL3_B171 - _SL3_B95) / _SL3_CUT_LIN + _SL3_B95) / 1023.0
                    ).astype(np.float32)


def _slog3_to_lin(y):
    y = np.asarray(y, np.float64)
    return np.where(y >= _SL3_CUT_LOG, (10.0 ** ((y * 1023.0 - 420.0) / 261.5)) * 0.19 - 0.01,
                    (y * 1023.0 - _SL3_B95) * _SL3_CUT_LIN / (_SL3_B171 - _SL3_B95)
                    ).astype(np.float32)


# ── Panasonic V-Log ──────────────────────────────────────────────────────
# Panasonic "V-Log/V-Gamut Reference Manual" Rev.1.0 (28 Nov 2014), section 3.
# Anchors: 0% black -> CV 128, 18% grey -> CV 433, 90% white -> CV 602.
_VLOG_B, _VLOG_C, _VLOG_D = 0.00873, 0.241514, 0.598206
_VLOG_CUT1 = 0.01
_VLOG_CUT2 = _VLOG_C * np.log10(_VLOG_CUT1 + _VLOG_B) + _VLOG_D  # 0.18098 (spec: 0.181)


def _lin_to_vlog(x):
    x = np.asarray(x, np.float64)
    xc = np.maximum(x + _VLOG_B, 1e-10)  # guard the discarded log branch
    return np.where(x >= _VLOG_CUT1, _VLOG_C * np.log10(xc) + _VLOG_D,
                    5.6 * x + 0.125).astype(np.float32)


def _vlog_to_lin(y):
    y = np.asarray(y, np.float64)
    return np.where(y >= _VLOG_CUT2, 10.0 ** ((y - _VLOG_D) / _VLOG_C) - _VLOG_B,
                    (y - 0.125) / 5.6).astype(np.float32)


# ── Canon Log 3 ──────────────────────────────────────────────────────────
# Canon "Canon Log Gamma Curves" white paper (1 Nov 2018), Appendix [3].
# Three pieces: negative log branch, a linear mid segment keeping the curve
# C1-continuous across both breakpoints, and a positive log branch.
_CL3_NEG_A, _CL3_NEG_S = 0.36726845, 14.98325
_CL3_NEG_OFF = 0.12783901
_CL3_MID_S, _CL3_MID_OFF = 1.9754798, 0.12512219
_CL3_POS_A, _CL3_POS_S = 0.36726845, 14.98325
_CL3_POS_OFF = 0.12240537
_CL3_LO, _CL3_HI = -0.014, 0.014


def _lin_to_canonlog3(x):
    x = np.asarray(x, np.float64)
    neg_arg = np.maximum(1.0 - _CL3_NEG_S * np.minimum(x, _CL3_LO), 1e-10)
    pos_arg = np.maximum(_CL3_POS_S * np.maximum(x, _CL3_HI) + 1.0, 1e-10)
    neg = -_CL3_NEG_A * np.log10(neg_arg) + _CL3_NEG_OFF
    mid = _CL3_MID_S * x + _CL3_MID_OFF
    pos = _CL3_POS_A * np.log10(pos_arg) + _CL3_POS_OFF
    return np.where(x < _CL3_LO, neg, np.where(x <= _CL3_HI, mid, pos)).astype(np.float32)


_CL3_Y_LO = _CL3_MID_S * _CL3_LO + _CL3_MID_OFF   # 0.097465...
_CL3_Y_HI = _CL3_MID_S * _CL3_HI + _CL3_MID_OFF   # 0.152779...


def _canonlog3_to_lin(y):
    y = np.asarray(y, np.float64)
    neg = -(10.0 ** ((_CL3_NEG_OFF - y) / _CL3_NEG_A) - 1.0) / _CL3_NEG_S
    mid = (y - _CL3_MID_OFF) / _CL3_MID_S
    pos = (10.0 ** ((y - _CL3_POS_OFF) / _CL3_POS_A) - 1.0) / _CL3_POS_S
    return np.where(y < _CL3_Y_LO, neg, np.where(y <= _CL3_Y_HI, mid, pos)).astype(np.float32)


# ── RED Log3G10 ──────────────────────────────────────────────────────────
# RED "White Paper on REDWideGamutRGB and Log3G10", Form 915-0187 Rev C.
# Anchors: linear -0.01 -> 0.0, 0.0 -> 0.091551, 0.18 -> 1/3, 184.322 -> 1.0.
_L3G10_A, _L3G10_B, _L3G10_C, _L3G10_G = 0.224282, 155.975327, 0.01, 15.1927


def _lin_to_log3g10(x):
    x = np.asarray(x, np.float64) + _L3G10_C
    xc = np.maximum(x * _L3G10_B + 1.0, 1e-10)  # guard the discarded log branch
    return np.where(x >= 0.0, _L3G10_A * np.log10(xc), x * _L3G10_G).astype(np.float32)


def _log3g10_to_lin(y):
    y = np.asarray(y, np.float64)
    return np.where(y >= 0.0, (10.0 ** (y / _L3G10_A) - 1.0) / _L3G10_B - _L3G10_C,
                    y / _L3G10_G - _L3G10_C).astype(np.float32)


# ── Blackmagic DaVinci Intermediate ──────────────────────────────────────
# Blackmagic "DaVinci Resolve 17: Wide Gamut Intermediate" v1.1 (31/07/2021).
# Anchors: linear 0 -> 0, 0.18 -> 0.336043, 1.0 -> 0.513837, 10.0 -> 0.756599.
_DI_A, _DI_B, _DI_C, _DI_M = 0.0075, 7.0, 0.07329248, 10.44426855
_DI_LIN_CUT, _DI_LOG_CUT = 0.00262409, 0.02740668


def _lin_to_davinci_intermediate(x):
    x = np.asarray(x, np.float64)
    xc = np.maximum(x + _DI_A, 1e-10)  # guard the discarded log branch
    return np.where(x > _DI_LIN_CUT, (np.log2(xc) + _DI_B) * _DI_C,
                    x * _DI_M).astype(np.float32)


def _davinci_intermediate_to_lin(y):
    y = np.asarray(y, np.float64)
    return np.where(y > _DI_LOG_CUT, 2.0 ** (y / _DI_C - _DI_B) - _DI_A,
                    y / _DI_M).astype(np.float32)


# ── registry ─────────────────────────────────────────────────────────────
# Display label -> (linear->log, log->linear, the gamut that pairs with it).
CURVES: Dict[str, Tuple[Callable, Callable, str]] = {
    "Cineon":               (_lin_to_cineon, _cineon_to_lin, ""),
    "ACEScct":              (_lin_to_acescct, _acescct_to_lin, "ACEScg (AP1)"),
    "ACEScc":               (_lin_to_acescc, _acescc_to_lin, "ACEScg (AP1)"),
    "ARRI LogC3":           (_lin_to_logc3, _logc3_to_lin, "ARRI Wide Gamut 3"),
    "ARRI LogC4":           (_lin_to_logc4, _logc4_to_lin, "ARRI Wide Gamut 4"),
    "Sony S-Log3":          (_lin_to_slog3, _slog3_to_lin, "Sony S-Gamut3.Cine"),
    "Panasonic V-Log":      (_lin_to_vlog, _vlog_to_lin, "Panasonic V-Gamut"),
    "Canon Log 3":          (_lin_to_canonlog3, _canonlog3_to_lin, "Canon Cinema Gamut"),
    "RED Log3G10":          (_lin_to_log3g10, _log3g10_to_lin, "RED Wide Gamut RGB"),
    "DaVinci Intermediate": (_lin_to_davinci_intermediate, _davinci_intermediate_to_lin,
                             "DaVinci Wide Gamut"),
}

CURVE_NAMES = tuple(CURVES.keys())

# Saved workflows from the source pack used lower-case machine keys.
LEGACY_CURVE_KEYS = {
    "cineon": "Cineon", "acescct": "ACEScct", "acescc": "ACEScc",
    "logc3": "ARRI LogC3", "logc4": "ARRI LogC4", "slog3": "Sony S-Log3",
    "vlog": "Panasonic V-Log", "canonlog3": "Canon Log 3",
    "log3g10": "RED Log3G10", "davinci_intermediate": "DaVinci Intermediate",
}


def resolve_curve(name: str) -> Tuple[Callable, Callable, str]:
    """Look up a curve by display label or legacy machine key.

    Raises KeyError naming the unknown curve and listing every known one —
    never falls back to a default curve, which would silently mis-decode a
    plate.
    """
    key = LEGACY_CURVE_KEYS.get(name, name)
    if key not in CURVES:
        raise KeyError(
            f"unknown log curve {name!r}. Known curves: {', '.join(CURVE_NAMES)}"
        )
    return CURVES[key]
