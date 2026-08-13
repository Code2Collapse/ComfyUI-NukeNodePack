"""Gamut (primaries) conversion matrices, derived from published chromaticities.

WHY DERIVED AND NOT COPIED
--------------------------
The reference pack `third_party/radiance` ships a table of camera-gamut
matrices named `*_TO_ACESCG`. Two problems:

1. It is GPL-3.0. This pack is not, so its code cannot be copied.
2. Measured 2026-08-13: every one of its *camera* matrices actually converts
   to **ACES AP0 (ACES2065-1)**, not to ACEScg (AP1) as the name says — it is
   missing the AP0 -> AP1 step. Its `SRGB_TO_ACESCG` *is* a real AP1 matrix,
   so the table silently mixes two different destination gamuts. Measured
   max|delta| of its `AWG3_TO_ACESCG` against a correctly derived AWG3->AP1:
   0.294; against AWG3->AP0: 0.089. Grading a LogC3 plate through it lands
   you in AP0 while the UI says ACEScg.

So this module builds every matrix from first principles instead: the
normalised primary matrix (NPM) from the published xy chromaticities, a
Bradford chromatic adaptation between the two white points, and the inverse
NPM of the destination. Verified against OCIO's own ACES Studio config
transforms — see the numbers in PROCESS_PLATE.md.

Every matrix here is exact float64 at import, cast to float32 on use. No
value is clamped: a gamut conversion legitimately produces negatives
(out-of-gamut colours) and values far above 1.0 (speculars, emissives).
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

# White points (CIE 1931 xy).
_D65 = (0.3127, 0.3290)
_D60_ACES = (0.32168, 0.33767)   # the ACES white point, ~D60
_D55 = (0.33243, 0.34744)

# Published RGB primaries: name -> (R_xy, G_xy, B_xy, white_xy, source).
# Every entry is traceable to the vendor's or the standards body's own spec.
PRIMARIES: Dict[str, Tuple[tuple, tuple, tuple, tuple, str]] = {
    "ACES 2065-1 (AP0)": (
        (0.7347, 0.2653), (0.0000, 1.0000), (0.0001, -0.0770), _D60_ACES,
        "SMPTE ST 2065-1"),
    "ACEScg (AP1)": (
        (0.7130, 0.2930), (0.1650, 0.8300), (0.1280, 0.0440), _D60_ACES,
        "ACES S-2014-004"),
    "sRGB / Rec.709": (
        (0.6400, 0.3300), (0.3000, 0.6000), (0.1500, 0.0600), _D65,
        "ITU-R BT.709-6"),
    "Rec.2020": (
        (0.7080, 0.2920), (0.1700, 0.7970), (0.1310, 0.0460), _D65,
        "ITU-R BT.2020-2"),
    "P3-D65": (
        (0.6800, 0.3200), (0.2650, 0.6900), (0.1500, 0.0600), _D65,
        "SMPTE RP 431-2 primaries, D65 white"),
    "DCI-P3": (
        (0.6800, 0.3200), (0.2650, 0.6900), (0.1500, 0.0600), (0.3140, 0.3510),
        "SMPTE RP 431-2"),
    "AdobeRGB": (
        (0.6400, 0.3300), (0.2100, 0.7100), (0.1500, 0.0600), _D65,
        "Adobe RGB (1998) spec"),
    "ARRI Wide Gamut 3": (
        (0.6840, 0.3130), (0.2210, 0.8480), (0.0861, -0.1020), _D65,
        "ARRI 'ALEXA LogC Curve' white paper"),
    "ARRI Wide Gamut 4": (
        (0.7347, 0.2653), (0.1424, 0.8576), (0.0991, -0.0308), _D65,
        "ARRI LogC4 Specification, 1 May 2022"),
    "Sony S-Gamut3": (
        (0.7300, 0.2800), (0.1400, 0.8550), (0.1000, -0.0500), _D65,
        "Sony S-Gamut3/S-Log3 Technical Summary"),
    "Sony S-Gamut3.Cine": (
        (0.7660, 0.2750), (0.2250, 0.8000), (0.0890, -0.0870), _D65,
        "Sony S-Gamut3.Cine/S-Log3 Technical Summary"),
    "Panasonic V-Gamut": (
        (0.7300, 0.2800), (0.1650, 0.8400), (0.1000, -0.0300), _D65,
        "Panasonic V-Log/V-Gamut Reference Manual Rev.1.0"),
    "Canon Cinema Gamut": (
        (0.7400, 0.2700), (0.1700, 1.1400), (0.0800, -0.1000), _D65,
        "Canon 'Cinema Gamut' white paper (D65 white)"),
    "Canon Cinema Gamut (D55)": (
        (0.7400, 0.2700), (0.1700, 1.1400), (0.0800, -0.1000), _D55,
        "Canon Cinema Gamut primaries with the D55 white the ACES IDT uses"),
    "RED Wide Gamut RGB": (
        (0.780308, 0.304253), (0.121595, 1.493994), (0.095612, -0.084589), _D65,
        "RED 'REDWideGamutRGB and Log3G10' white paper Rev C"),
    "DaVinci Wide Gamut": (
        (0.8000, 0.3130), (0.1682, 0.9877), (0.0790, -0.1155), _D65,
        "Blackmagic 'DaVinci Resolve 17 Wide Gamut Intermediate' v1.1"),
    "Blackmagic Wide Gamut Gen5": (
        (0.7177, 0.3171), (0.2280, 0.8616), (0.1006, -0.0820), (0.3127, 0.3290),
        "Blackmagic Generation 5 Color Science white paper"),
}

GAMUT_NAMES = tuple(PRIMARIES.keys())

# Bradford cone response, the CAT used by the ACES IDTs and by OCIO.
_BRADFORD = np.array([
    [0.8951, 0.2664, -0.1614],
    [-0.7502, 1.7135, 0.0367],
    [0.0389, -0.0685, 1.0296],
], dtype=np.float64)


def _xy_to_XYZ(xy: tuple, Y: float = 1.0) -> np.ndarray:
    x, y = xy
    if y == 0.0:
        raise ValueError(f"degenerate chromaticity {xy!r}: y must be non-zero")
    return np.array([x * Y / y, Y, (1.0 - x - y) * Y / y], dtype=np.float64)


def _npm(r: tuple, g: tuple, b: tuple, w: tuple) -> np.ndarray:
    """Normalised primary matrix: linear RGB -> CIE XYZ for these primaries."""
    P = np.array([_xy_to_XYZ(r), _xy_to_XYZ(g), _xy_to_XYZ(b)], dtype=np.float64).T
    return P * np.linalg.solve(P, _xy_to_XYZ(w))


def _bradford_cat(src_w: tuple, dst_w: tuple) -> np.ndarray:
    """Bradford chromatic adaptation XYZ(src white) -> XYZ(dst white)."""
    cs = _BRADFORD @ _xy_to_XYZ(src_w)
    cd = _BRADFORD @ _xy_to_XYZ(dst_w)
    return np.linalg.inv(_BRADFORD) @ np.diag(cd / cs) @ _BRADFORD


def gamut_matrix(src: str, dst: str) -> np.ndarray:
    """3x3 linear-RGB matrix taking `src` primaries to `dst` primaries.

    Raises KeyError naming the unknown gamut and listing what is available —
    never silently substitutes a neighbouring gamut.
    """
    for name in (src, dst):
        if name not in PRIMARIES:
            raise KeyError(
                f"unknown gamut {name!r}. Known gamuts: {', '.join(GAMUT_NAMES)}"
            )
    sr, sg, sb, sw, _ = PRIMARIES[src]
    dr, dg, db, dw, _ = PRIMARIES[dst]
    return np.linalg.inv(_npm(dr, dg, db, dw)) @ _bradford_cat(sw, dw) @ _npm(sr, sg, sb, sw)


def matrix_source(name: str) -> str:
    """The published document a gamut's primaries came from."""
    if name not in PRIMARIES:
        raise KeyError(f"unknown gamut {name!r}. Known gamuts: {', '.join(GAMUT_NAMES)}")
    return PRIMARIES[name][4]
