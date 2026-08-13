"""Colour tier — camera log curves, gamut matrices, LUTs, and the OCIO
transforms the existing `nodes/ocio` module did not cover.

Sources (batch 2 of the VFX IO / Colour / Comp program, see PROCESS_PLATE.md):

* `third_party/ComfyUI-OCIO` — MIT, Copyright (c) 2026 Slava Sexton. The log
  curve library and the CDL / File / Look transform nodes are ported from it
  with the spec citations intact.
* `third_party/radiance` — GPL-3.0, therefore **read but never copied**. Its
  gamut matrices were also found to be wrong (they target ACES AP0 while
  claiming ACEScg); `_primaries.py` derives correct ones from the published
  chromaticities instead. Its LUT node likewise inspired but did not supply
  `_cube.py`.

DESIGN CONTRACT (PROCESS_PLATE.md section 3) — enforced here:

1. Nothing in this module clamps to 0..1. Scene-linear negatives (out-of-gamut
   colour) and above-white speculars pass through every node intact.
2. No silent fallback. A missing config, colourspace, LUT file, display, view
   or look raises, naming what was missing and every directory that was
   searched.
3. What cannot be represented is surfaced. The LUT node reports the fraction
   of samples that fell outside the LUT domain; the gamut node reports the
   matrix and its published source; the config node reports everything the
   config holds.
4. `IS_CHANGED` hashes real inputs via `hash_args_and_kwargs`, never NaN.
"""
from __future__ import annotations

import json
import logging
import os
from typing import List, Optional, Tuple

import numpy as np
import torch

import folder_paths  # type: ignore[import-not-found]

from ..._is_changed_util import hash_args_and_kwargs
from ..._tensor_util import require_image_bhwc
from ...utils.resilience import resilient
from . import _cube
from ._curves import CURVE_NAMES, CURVES, LEGACY_CURVE_KEYS, resolve_curve
from ._primaries import GAMUT_NAMES, gamut_matrix, matrix_source

log = logging.getLogger("NukeMax.Color")

_LUT_FOLDER_KEY = "luts"
_LUT_EXTS = {".cube"}
# OCIO's FileTransform reads far more than .cube.
_OCIO_LUT_EXTS = {".cube", ".3dl", ".spi1d", ".spi3d", ".csp", ".ccc", ".cdl",
                  ".clf", ".ctf", ".lut", ".look", ".vf", ".icc", ".icm"}


# ── shared plumbing ──────────────────────────────────────────────────────

def _register_lut_folder() -> None:
    """Register `ComfyUI/models/luts/` so users can drop .cube files there."""
    try:
        if folder_paths.get_folder_paths(_LUT_FOLDER_KEY):
            return
    except Exception:
        pass
    try:
        folder_paths.add_model_folder_path(
            _LUT_FOLDER_KEY, os.path.join(folder_paths.models_dir, "luts"), is_default=True
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("Could not register luts folder: %s", exc)


_register_lut_folder()


def _lut_search_dirs() -> List[str]:
    """Every directory a LUT may live in, in priority order."""
    dirs: List[str] = []
    try:
        dirs.extend(folder_paths.get_folder_paths(_LUT_FOLDER_KEY) or [])
    except Exception:
        pass
    for getter in ("get_input_directory", "get_output_directory"):
        try:
            d = getattr(folder_paths, getter)()
            if d and d not in dirs:
                dirs.append(d)
        except Exception:
            pass
    return dirs


def _scan_luts(exts) -> List[str]:
    found: List[str] = []
    for root_dir in _lut_search_dirs():
        if not os.path.isdir(root_dir):
            continue
        for root, _dirs, files in os.walk(root_dir):
            for f in files:
                if os.path.splitext(f)[1].lower() in exts:
                    rel = os.path.relpath(os.path.join(root, f), root_dir)
                    found.append(rel.replace("\\", "/"))
    return sorted(set(found))


def _lut_choices(exts) -> list:
    found = _scan_luts(exts)
    return found if found else ["(no LUT files found — see tooltip)"]


def _resolve_lut(choice: str, exts) -> str:
    """Choice -> absolute path, or raise naming every directory searched."""
    if choice and os.path.isabs(choice) and os.path.isfile(choice):
        return choice
    dirs = _lut_search_dirs()
    for d in dirs:
        cand = os.path.join(d, choice)
        if os.path.isfile(cand):
            return cand
    raise FileNotFoundError(
        f"LUT file {choice!r} not found. Searched, in order: "
        + (" ; ".join(dirs) if dirs else "(no LUT directories are registered)")
        + f". Drop a {'/'.join(sorted(exts))} file into ComfyUI/models/luts/ "
        "or the ComfyUI input folder, then refresh the node list."
    )


def _split_rgb(image: torch.Tensor) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
    """RGB and the untouched trailing channels (alpha, AOV extras)."""
    if image.shape[-1] < 3:
        raise ValueError(
            f"image needs at least 3 channels for a colour transform, got {image.shape[-1]}"
        )
    return image[..., :3], (image[..., 3:] if image.shape[-1] > 3 else None)


def _join_rgb(rgb: torch.Tensor, rest: Optional[torch.Tensor]) -> torch.Tensor:
    return rgb if rest is None else torch.cat([rgb, rest], dim=-1)


def _mix(orig: torch.Tensor, new: torch.Tensor, amount: float) -> torch.Tensor:
    """Blend without clipping. amount is already validated to 0..1."""
    if amount >= 1.0:
        return new
    if amount <= 0.0:
        return orig
    return orig * (1.0 - amount) + new * amount


_MIX_INPUT = ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01,
                        "tooltip": "Blend with the original: 1.0 = full effect, 0.0 = bypass."})


def _require_ocio():
    try:
        import PyOpenColorIO as OCIO  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "This node needs PyOpenColorIO. Install it into the ComfyUI python with "
            "`python -m pip install opencolorio`. Verified working here: PyOpenColorIO 2.5.2."
        ) from exc
    return OCIO


def _apply_ocio(image: torch.Tensor, processor) -> torch.Tensor:
    """Run an OCIO Processor over an [B,H,W,C] IMAGE. RGB only, no clipping.

    Two traps, both measured in this environment and both load-bearing:

    * `CPUProcessor.applyRGB(ndarray)` silently no-ops on PyOpenColorIO 2.5.2 —
      it transforms a converted copy, not the caller's buffer. `PackedImageDesc`
      + `apply()` mutates in place reliably.
    * The buffer handed to `PackedImageDesc` MUST be a numpy-owned copy.
      `np.ascontiguousarray()` on an already-contiguous array returns the SAME
      object, so OCIO then writes through into the caller's tensor storage.
      Under `torch.inference_mode()` (the `@resilient` wrapper) that produced
      identity output or garbage. `copy=True` is not optional.
    """
    OCIO = _require_ocio()
    cpu = processor.getDefaultCPUProcessor()
    rgb, rest = _split_rgb(image)
    arr = np.array(rgb.detach().cpu().float().numpy(), dtype=np.float32, copy=True)
    b, h, w, _ = arr.shape
    for i in range(b):
        frame = np.ascontiguousarray(arr[i])
        cpu.apply(OCIO.PackedImageDesc(frame, w, h, 3))
        arr[i] = frame
    out = torch.from_numpy(arr).to(image.device)
    return _join_rgb(out, rest)


# ── OCIO config discovery (shared with nodes/ocio) ───────────────────────

_BUILTIN_CONFIGS = {
    "builtin: ACES Studio (LogC3/C4, camera spaces)": "ocio://studio-config-latest",
    "builtin: ACES CG": "ocio://cg-config-latest",
    "builtin: OCIO default (ACES)": "ocio://default",
}
_CONFIG_FOLDER_KEY = "ocio_configs"


def _config_search_dirs() -> List[str]:
    try:
        return list(folder_paths.get_folder_paths(_CONFIG_FOLDER_KEY) or [])
    except Exception:
        return []


def _list_configs() -> List[str]:
    out: List[str] = []
    try:
        import PyOpenColorIO as OCIO  # noqa: F401
        out.extend(_BUILTIN_CONFIGS.keys())
    except Exception:
        pass
    env = os.environ.get("OCIO")
    if env and os.path.isfile(env):
        out.append(f"$OCIO:{os.path.basename(os.path.dirname(env)) or 'env'}")
    for r in _config_search_dirs():
        if not os.path.isdir(r):
            continue
        for name in sorted(os.listdir(r)):
            full = os.path.join(r, name)
            if os.path.isdir(full) and os.path.isfile(os.path.join(full, "config.ocio")):
                out.append(name)
            elif name.lower().endswith(".ocio"):
                out.append(name)
    if not out:
        out.append("(install PyOpenColorIO + drop a config in models/ocio_configs)")
    return out


def _resolve_config_path(choice: str) -> str:
    """Choice -> a config path or `ocio://` URI, or raise naming the search."""
    if choice in _BUILTIN_CONFIGS:
        return _BUILTIN_CONFIGS[choice]
    if choice.startswith("$OCIO:"):
        env = os.environ.get("OCIO")
        if env and os.path.isfile(env):
            return env
        raise FileNotFoundError(
            f"config {choice!r} points at the $OCIO environment variable, but "
            f"$OCIO is {'unset' if not env else 'set to ' + env + ' which does not exist'}."
        )
    dirs = _config_search_dirs()
    for r in dirs:
        for cand in (os.path.join(r, choice, "config.ocio"), os.path.join(r, choice)):
            if os.path.isfile(cand):
                return cand
    raise FileNotFoundError(
        f"OCIO config {choice!r} not found. Searched: "
        + (" ; ".join(dirs) if dirs else "(no ocio_configs directories are registered)")
        + ". Drop a config folder under ComfyUI/models/ocio_configs/, set the $OCIO "
        "environment variable, or pick one of the built-in ACES configs."
    )


_CONFIG_CACHE: dict = {}


def _load_config(path: str):
    """Load and cache a config, keyed on (path, mtime, size) for real files."""
    OCIO = _require_ocio()
    if path.startswith("ocio://"):
        key = ("builtin", path)
    else:
        st = os.stat(path)
        key = ("file", path, st.st_mtime_ns, st.st_size)
    if key in _CONFIG_CACHE:
        return _CONFIG_CACHE[key]
    cfg = (OCIO.Config.CreateFromBuiltinConfig(path) if path.startswith("ocio://")
           else OCIO.Config.CreateFromFile(path))
    if len(_CONFIG_CACHE) > 8:
        _CONFIG_CACHE.clear()
    _CONFIG_CACHE[key] = cfg
    return cfg


def _colorspace_names(cfg) -> List[str]:
    return [cs.getName() for cs in cfg.getColorSpaces()]


def _check_colorspace(cfg, name: str, label: str, config_path: str) -> str:
    """Verify a colourspace exists, or raise naming it and the near misses."""
    names = _colorspace_names(cfg)
    if name in names:
        return name
    lowered = {n.lower(): n for n in names}
    if name.strip().lower() in lowered:
        return lowered[name.strip().lower()]
    near = [n for n in names if name.strip().lower() in n.lower()][:8]
    raise ValueError(
        f"{label} colourspace {name!r} is not in the OCIO config at {config_path}. "
        + (f"Did you mean one of: {', '.join(near)}? " if near else "")
        + f"The config defines {len(names)} colourspaces; run the "
        "'OCIO Config Info' node to list them all."
    )


# ── nodes ────────────────────────────────────────────────────────────────

@resilient
class CameraLogConvert:
    """Camera-native log <-> scene-linear, without PyOpenColorIO."""

    DESCRIPTION = (
        "Decode or encode a camera log transfer curve: Cineon, ACEScct, ACEScc, "
        "ARRI LogC3/LogC4, Sony S-Log3, Panasonic V-Log, Canon Log 3, RED Log3G10, "
        "Blackmagic DaVinci Intermediate. Curve ONLY — the plate keeps its camera "
        "primaries, so follow 'Log to Linear' with a Camera Gamut Convert step. "
        "No OCIO needed. HDR-safe: nothing is clipped in either direction."
    )
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "info")
    OUTPUT_TOOLTIPS = ("Image with the curve applied.",
                       "The curve applied, its direction, the gamut you should pair it with, "
                       "and the input/output ranges.")

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "operation": (("Log to Linear", "Linear to Log"), {"default": "Log to Linear"}),
            "curve": (list(CURVE_NAMES), {
                "default": "ARRI LogC3",
                "tooltip": "Transfer curve only. Pair 'Log to Linear' with the matching "
                           "camera gamut in Camera Gamut Convert — do NOT also use the OCIO "
                           "config's same-named colourspace, that applies the gamut twice."}),
            "mix": _MIX_INPUT,
        }}

    @classmethod
    def VALIDATE_INPUTS(cls, curve=None, operation=None):
        # Saved graphs may hold the source pack's lower-case machine keys.
        if curve is not None and curve not in CURVES and curve not in LEGACY_CURVE_KEYS:
            return f"'{curve}' is not a known log curve. Known: {', '.join(CURVE_NAMES)}"
        return True

    def execute(self, image, operation, curve, mix=1.0):
        require_image_bhwc(image)
        lin2log, log2lin, pair_gamut = resolve_curve(curve)
        fn = lin2log if operation == "Linear to Log" else log2lin

        rgb, rest = _split_rgb(image)
        src = rgb.detach().cpu().float().numpy()
        converted = torch.from_numpy(np.ascontiguousarray(fn(src))).to(image.device)
        out = _join_rgb(_mix(rgb, converted, float(mix)), rest)

        info = {
            "curve": LEGACY_CURVE_KEYS.get(curve, curve),
            "operation": operation,
            "mix": float(mix),
            "pair_with_gamut": pair_gamut or "(Cineon is a generic film log — no camera gamut)",
            "input_range": [float(src.min()), float(src.max())],
            "output_range": [float(out[..., :3].min()), float(out[..., :3].max())],
            "clipped": False,
            "note": "Transfer curve only. Primaries are unchanged by this node.",
        }
        return (out, json.dumps(info, indent=2))


@resilient
class CameraGamutConvert:
    """Convert between camera / display primaries with a derived 3x3 matrix."""

    DESCRIPTION = (
        "Convert scene-linear RGB between gamuts (ARRI Wide Gamut 3/4, Sony S-Gamut3(.Cine), "
        "Panasonic V-Gamut, Canon Cinema Gamut, RED Wide Gamut RGB, DaVinci Wide Gamut, "
        "Blackmagic Gen5, ACES AP0/AP1, Rec.709, Rec.2020, P3, AdobeRGB). Matrices are derived "
        "at import from the vendors' published chromaticities with a Bradford adaptation — not "
        "copied from a reference pack. Input must already be LINEAR: decode the log curve first. "
        "Negatives and values above 1.0 are preserved; out-of-gamut colour is reported, not clipped."
    )
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "info")
    OUTPUT_TOOLTIPS = ("Image in the destination gamut.",
                       "The 3x3 matrix used, its published source, and the fraction of pixels "
                       "that landed out of gamut (negative) in the destination.")

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {"tooltip": "Scene-LINEAR image. Decode any log curve first."}),
            "from_gamut": (list(GAMUT_NAMES), {"default": "ARRI Wide Gamut 3"}),
            "to_gamut": (list(GAMUT_NAMES), {"default": "ACEScg (AP1)"}),
            "mix": _MIX_INPUT,
        }}

    def execute(self, image, from_gamut, to_gamut, mix=1.0):
        require_image_bhwc(image)
        m = gamut_matrix(from_gamut, to_gamut)          # raises, naming the unknown gamut
        rgb, rest = _split_rgb(image)
        mat = torch.tensor(m, dtype=torch.float32, device=image.device)
        converted = torch.matmul(rgb, mat.T)            # no clamp, by contract
        out = _join_rgb(_mix(rgb, converted, float(mix)), rest)

        neg = float((converted < 0).any(dim=-1).float().mean().item())
        info = {
            "from_gamut": from_gamut,
            "to_gamut": to_gamut,
            "matrix": [[round(float(v), 8) for v in row] for row in m],
            "source_primaries": matrix_source(from_gamut),
            "target_primaries": matrix_source(to_gamut),
            "adaptation": "Bradford",
            "out_of_gamut_pixel_fraction": round(neg, 6),
            "out_of_gamut_note": (
                "Pixels with a negative channel are outside the destination gamut. They are "
                "PRESERVED, not clipped — add a gamut compression step if you need them inside."),
            "output_range": [float(out[..., :3].min()), float(out[..., :3].max())],
        }
        return (out, json.dumps(info, indent=2))


@resilient
class ColorMatrix:
    """Nuke's ColorMatrix: an arbitrary 3x3 / 4x4 matrix plus offset."""

    DESCRIPTION = (
        "Apply a custom 3x3 (RGB) or 4x4 (RGBA) colour matrix with an optional offset. "
        "Presets for Identity, Sepia, Luminance (Rec.709) and Invert. Rows are typed as "
        "comma or space separated floats. Never clamps — this is a linear operator."
    )
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "info")

    PRESETS = {
        "Custom": None,
        "Identity": ((1, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 0)),
        "Sepia": ((0.393, 0.769, 0.189), (0.349, 0.686, 0.168),
                  (0.272, 0.534, 0.131), (0, 0, 0)),
        "Luminance (Rec.709)": ((0.2126, 0.7152, 0.0722), (0.2126, 0.7152, 0.0722),
                                (0.2126, 0.7152, 0.0722), (0, 0, 0)),
        "Invert": ((-1, 0, 0), (0, -1, 0), (0, 0, -1), (1, 1, 1)),
    }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "preset": (list(cls.PRESETS.keys()), {"default": "Custom"}),
            "matrix_type": (("RGB (3x3)", "RGBA (4x4)"), {"default": "RGB (3x3)"}),
            "r_row": ("STRING", {"default": "1.0, 0.0, 0.0"}),
            "g_row": ("STRING", {"default": "0.0, 1.0, 0.0"}),
            "b_row": ("STRING", {"default": "0.0, 0.0, 1.0"}),
            "mix": _MIX_INPUT,
        }, "optional": {
            "a_row": ("STRING", {"default": "0.0, 0.0, 0.0, 1.0",
                                 "tooltip": "Only used by RGBA (4x4)."}),
            "offset": ("STRING", {"default": "0.0, 0.0, 0.0"}),
        }}

    @staticmethod
    def _parse_row(text: str, width: int, label: str) -> List[float]:
        parts = [p for p in text.replace(",", " ").split() if p]
        if not parts:
            raise ValueError(f"{label} is empty; expected {width} numbers, e.g. '1.0, 0.0, 0.0'")
        try:
            vals = [float(p) for p in parts]
        except ValueError as exc:
            raise ValueError(f"{label} contains a non-number: {text!r}") from exc
        if len(vals) > width:
            raise ValueError(f"{label} has {len(vals)} numbers, expected at most {width}: {text!r}")
        return vals + [0.0] * (width - len(vals))

    def execute(self, image, preset, matrix_type, r_row, g_row, b_row, mix=1.0,
                a_row="0.0, 0.0, 0.0, 1.0", offset="0.0, 0.0, 0.0"):
        require_image_bhwc(image)
        four = matrix_type == "RGBA (4x4)"

        if preset != "Custom":
            r, g, b, off = self.PRESETS[preset]
            rows = [list(r), list(g), list(b)]
            off = list(off)
            a = [0.0, 0.0, 0.0, 1.0]
        else:
            rows = [self._parse_row(r_row, 3, "r_row"),
                    self._parse_row(g_row, 3, "g_row"),
                    self._parse_row(b_row, 3, "b_row")]
            off = self._parse_row(offset, 4 if four else 3, "offset")
            a = self._parse_row(a_row, 4, "a_row")

        rgb, rest = _split_rgb(image)
        dev = image.device

        if four:
            alpha = (rest[..., :1] if rest is not None
                     else torch.ones(*rgb.shape[:-1], 1, dtype=rgb.dtype, device=dev))
            rgba = torch.cat([rgb, alpha], dim=-1)
            mat = torch.tensor([rows[0] + [0.0], rows[1] + [0.0], rows[2] + [0.0], a],
                               dtype=torch.float32, device=dev)
            res = torch.matmul(rgba, mat.T)
            off4 = (off + [0.0] * 4)[:4]
            res = res + torch.tensor(off4, dtype=torch.float32, device=dev)
            new_rgb, new_a = res[..., :3], res[..., 3:]
            new_rest = new_a if rest is None else torch.cat([new_a, rest[..., 1:]], dim=-1)
        else:
            mat = torch.tensor(rows, dtype=torch.float32, device=dev)
            new_rgb = torch.matmul(rgb, mat.T) + torch.tensor(
                off[:3], dtype=torch.float32, device=dev)
            new_rest = rest

        out = _join_rgb(_mix(rgb, new_rgb, float(mix)), new_rest)
        info = {
            "preset": preset,
            "matrix_type": matrix_type,
            "matrix": rows if not four else [rows[0] + [0.0], rows[1] + [0.0], rows[2] + [0.0], a],
            "offset": off,
            "clipped": False,
            "output_range": [float(out[..., :3].min()), float(out[..., :3].max())],
        }
        return (out, json.dumps(info, indent=2))


@resilient
class LUTApply:
    """3D / 1D `.cube` LUT with tetrahedral interpolation, HDR-aware."""

    DESCRIPTION = (
        "Apply an Iridas/Adobe .cube LUT (1D or 3D) with tetrahedral or trilinear "
        "interpolation. A LUT is only defined over its domain (normally 0-1); rather than "
        "silently crushing every highlight to the LUT's white corner, this node lets you "
        "extrapolate along the LUT's own edge gradient (default), clamp (Nuke Vectorfield "
        "behaviour), or pass out-of-domain pixels through. The fraction of samples that "
        "fell outside the domain is always reported in `info`."
    )
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "info")
    OUTPUT_TOOLTIPS = ("Image with the LUT applied.",
                       "LUT title, size, domain, interpolation, and the fraction of samples "
                       "outside the LUT domain.")

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "lut_file": (_lut_choices(_LUT_EXTS), {
                "tooltip": "A .cube file from ComfyUI/models/luts/ or the input folder."}),
            "interpolation": (list(_cube.INTERPOLATIONS), {
                "default": "tetrahedral",
                "tooltip": "Tetrahedral matches Nuke/Resolve and is more accurate on the "
                           "neutral axis. Trilinear is the cheaper classic."}),
            "above_domain": (list(_cube.DOMAIN_POLICIES), {
                "default": "extrapolate",
                "tooltip": "extrapolate = continue along the LUT's edge gradient (HDR survives). "
                           "clamp = Nuke Vectorfield behaviour, crushes highlights. "
                           "passthrough = out-of-domain pixels keep their input value."}),
            "mix": _MIX_INPUT,
        }}

    def execute(self, image, lut_file, interpolation="tetrahedral",
                above_domain="extrapolate", mix=1.0):
        require_image_bhwc(image)
        path = _resolve_lut(lut_file, _LUT_EXTS)   # raises naming every dir searched
        cube = _cube.load_cube(path)

        rgb, rest = _split_rgb(image)
        result, out_frac = _cube.sample(cube, rgb, interpolation, above_domain)
        out = _join_rgb(_mix(rgb, result, float(mix)), rest)

        info = {
            "lut": os.path.basename(path),
            "lut_path": path,
            "title": cube.title,
            "dimensions": f"{cube.dim}D",
            "size": cube.size,
            "domain_min": list(cube.domain_min),
            "domain_max": list(cube.domain_max),
            "interpolation": interpolation,
            "above_domain_policy": above_domain,
            "out_of_domain_pixel_fraction": round(out_frac, 6),
            "input_range": [float(rgb.min()), float(rgb.max())],
            "output_range": [float(out[..., :3].min()), float(out[..., :3].max())],
        }
        if out_frac > 0.0 and above_domain == "clamp":
            info["warning"] = (
                f"{out_frac * 100:.2f}% of pixels fell outside the LUT domain and were "
                "CLAMPED to the domain edge — highlight detail in those pixels is gone. "
                "Switch above_domain to 'extrapolate' to keep it.")
        return (out, json.dumps(info, indent=2))


@resilient
class OCIOCDLTransform:
    """ASC CDL — slope, offset, power, saturation (Nuke OCIOCDLTransform)."""

    DESCRIPTION = (
        "ASC CDL grade through OpenColorIO: per-channel slope / offset / power plus "
        "saturation, forward or inverse. This is the exchange format grading houses send "
        "back as a .cdl/.ccc. Scene-linear safe — no clipping."
    )
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "info")

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        def f(d, lo=-10.0, hi=10.0):
            return ("FLOAT", {"default": d, "min": lo, "max": hi, "step": 0.001})
        return {"required": {
            "image": ("IMAGE", {}),
            "slope_r": f(1.0), "slope_g": f(1.0), "slope_b": f(1.0),
            "offset_r": f(0.0), "offset_g": f(0.0), "offset_b": f(0.0),
            "power_r": f(1.0, 0.001, 10.0), "power_g": f(1.0, 0.001, 10.0),
            "power_b": f(1.0, 0.001, 10.0),
            "saturation": f(1.0, 0.0, 4.0),
            "direction": (("forward", "inverse"), {"default": "forward"}),
            "mix": _MIX_INPUT,
        }}

    def execute(self, image, slope_r, slope_g, slope_b, offset_r, offset_g, offset_b,
                power_r, power_g, power_b, saturation, direction="forward", mix=1.0):
        require_image_bhwc(image)
        OCIO = _require_ocio()
        for name, v in (("power_r", power_r), ("power_g", power_g), ("power_b", power_b)):
            if v <= 0.0:
                raise ValueError(f"{name} must be greater than 0 (ASC CDL power), got {v}")

        cfg = OCIO.Config.CreateRaw()   # CDL is config-independent maths
        t = OCIO.CDLTransform()
        t.setSlope([slope_r, slope_g, slope_b])
        t.setOffset([offset_r, offset_g, offset_b])
        t.setPower([power_r, power_g, power_b])
        t.setSat(saturation)
        t.setDirection(OCIO.TRANSFORM_DIR_FORWARD if direction == "forward"
                       else OCIO.TRANSFORM_DIR_INVERSE)

        rgb, _rest = _split_rgb(image)
        converted = _apply_ocio(image, cfg.getProcessor(t))
        out = _join_rgb(_mix(rgb, converted[..., :3], float(mix)),
                        image[..., 3:] if image.shape[-1] > 3 else None)
        info = {
            "transform": "ASC CDL",
            "slope": [slope_r, slope_g, slope_b],
            "offset": [offset_r, offset_g, offset_b],
            "power": [power_r, power_g, power_b],
            "saturation": saturation,
            "direction": direction,
            "note": ("ASC CDL power is only defined for non-negative input; OCIO passes "
                     "negatives through the slope/offset stage unchanged rather than "
                     "producing NaN. Check output_range if your plate has below-black."),
            "output_range": [float(out[..., :3].min()), float(out[..., :3].max())],
        }
        return (out, json.dumps(info, indent=2))


@resilient
class OCIOFileTransform:
    """Any LUT / CDL / CLF file OCIO can read (Nuke OCIOFileTransform)."""

    DESCRIPTION = (
        "Apply a LUT or grade file through OpenColorIO: .cube, .3dl, .spi1d, .spi3d, .csp, "
        ".ccc, .cdl, .clf, .ctf and more. Forward or inverse (inverse needs an invertible "
        "file — OCIO will say so if it is not). Use the LUT Apply node instead when you want "
        "explicit control over out-of-domain HDR behaviour."
    )
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "info")

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "file": (_lut_choices(_OCIO_LUT_EXTS), {
                "tooltip": "A LUT/CDL/CLF file from ComfyUI/models/luts/ or the input folder."}),
            "interpolation": (("linear", "nearest", "tetrahedral", "best"),
                              {"default": "linear"}),
            "direction": (("forward", "inverse"), {"default": "forward"}),
            "mix": _MIX_INPUT,
        }}

    def execute(self, image, file, interpolation="linear", direction="forward", mix=1.0):
        require_image_bhwc(image)
        OCIO = _require_ocio()
        path = _resolve_lut(file, _OCIO_LUT_EXTS)
        interp = {"linear": OCIO.INTERP_LINEAR, "nearest": OCIO.INTERP_NEAREST,
                  "tetrahedral": OCIO.INTERP_TETRAHEDRAL, "best": OCIO.INTERP_BEST}[interpolation]
        cfg = OCIO.Config.CreateRaw()
        t = OCIO.FileTransform(src=path, interpolation=interp)
        t.setDirection(OCIO.TRANSFORM_DIR_FORWARD if direction == "forward"
                       else OCIO.TRANSFORM_DIR_INVERSE)
        try:
            proc = cfg.getProcessor(t)
        except Exception as exc:
            raise ValueError(
                f"OCIO could not build a {direction} transform from {path}: {exc}. "
                + ("An inverse needs an invertible LUT — a 3D LUT usually is not. "
                   if direction == "inverse" else "")
                + f"Interpolation was {interpolation!r}."
            ) from exc

        rgb, _rest = _split_rgb(image)
        converted = _apply_ocio(image, proc)
        out = _join_rgb(_mix(rgb, converted[..., :3], float(mix)),
                        image[..., 3:] if image.shape[-1] > 3 else None)
        info = {
            "file": os.path.basename(path),
            "file_path": path,
            "interpolation": interpolation,
            "direction": direction,
            "note": ("OCIO clamps to the LUT domain internally. If this plate has values "
                     "above 1.0, use the 'LUT Apply' node's extrapolate policy instead."),
            "input_range": [float(rgb.min()), float(rgb.max())],
            "output_range": [float(out[..., :3].min()), float(out[..., :3].max())],
        }
        return (out, json.dumps(info, indent=2))


@resilient
class OCIOLookTransform:
    """Apply a named OCIO look (Nuke OCIOLookTransform)."""

    DESCRIPTION = (
        "Apply a creative look defined by the OCIO config (e.g. 'ACES 1.3 Reference Gamut "
        "Compression'), converting from an input to an output colourspace. Forward or "
        "inverse. Raises if the look, or either colourspace, is not in the config."
    )
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "info")

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "config": (_list_configs(), {}),
            "in_colorspace": ("STRING", {"default": "ACEScg"}),
            "out_colorspace": ("STRING", {"default": "ACEScg"}),
            "look": ("STRING", {"default": "",
                                "tooltip": "Look name from the config. Blank = no look "
                                           "(a plain colourspace conversion). Run 'OCIO Config "
                                           "Info' to list the looks this config defines."}),
            "direction": (("forward", "inverse"), {"default": "forward"}),
            "mix": _MIX_INPUT,
        }}

    def execute(self, image, config, in_colorspace, out_colorspace, look="",
                direction="forward", mix=1.0):
        require_image_bhwc(image)
        OCIO = _require_ocio()
        path = _resolve_config_path(config)
        cfg = _load_config(path)

        src = _check_colorspace(cfg, in_colorspace, "in_colorspace", path)
        dst = _check_colorspace(cfg, out_colorspace, "out_colorspace", path)

        looks = look.strip()
        if looks:
            available = [l.getName() for l in cfg.getLooks()]
            # A look may be prefixed with +/- for direction, per the OCIO spec.
            bare = looks.lstrip("+-")
            if bare not in available:
                raise ValueError(
                    f"look {looks!r} is not defined in the OCIO config at {path}. "
                    f"Looks this config defines: {available if available else '(none)'}."
                )

        t = OCIO.LookTransform(src=src, dst=dst, looks=looks)
        t.setDirection(OCIO.TRANSFORM_DIR_FORWARD if direction == "forward"
                       else OCIO.TRANSFORM_DIR_INVERSE)
        try:
            proc = cfg.getProcessor(t)
        except Exception as exc:
            raise ValueError(
                f"OCIO could not build the look transform {src!r} -> {dst!r} "
                f"(look={looks!r}, direction={direction}) from {path}: {exc}"
            ) from exc

        rgb, _rest = _split_rgb(image)
        converted = _apply_ocio(image, proc)
        out = _join_rgb(_mix(rgb, converted[..., :3], float(mix)),
                        image[..., 3:] if image.shape[-1] > 3 else None)
        info = {
            "config": path,
            "in_colorspace": src,
            "out_colorspace": dst,
            "look": looks or "(none)",
            "direction": direction,
            "output_range": [float(out[..., :3].min()), float(out[..., :3].max())],
        }
        return (out, json.dumps(info, indent=2))


@resilient
class OCIOConfigInfo:
    """List everything an OCIO config defines — the 'what can I type here' node."""

    DESCRIPTION = (
        "Introspect an OCIO config: colourspaces, roles, displays, views, looks and "
        "named transforms. Every other OCIO node in this pack raises with the exact name it "
        "could not find — this node tells you what the valid names are. No image input; "
        "it reads the config only."
    )
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("colorspaces", "displays_views", "looks_and_roles", "info")
    OUTPUT_TOOLTIPS = ("Newline-separated colourspace names.",
                       "Each display and the views valid for it.",
                       "Look names and role -> colourspace bindings.",
                       "JSON summary: config path, OCIO version, counts, search paths.")

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"config": (_list_configs(), {})}}

    def execute(self, config):
        OCIO = _require_ocio()
        path = _resolve_config_path(config)
        cfg = _load_config(path)

        spaces = _colorspace_names(cfg)
        displays = list(cfg.getDisplays())
        dv_lines, dv_map = [], {}
        for d in displays:
            views = list(cfg.getViews(d))
            dv_map[d] = views
            dv_lines.append(f"{d}:")
            dv_lines.extend(f"    {v}" for v in views)

        looks = [l.getName() for l in cfg.getLooks()]
        roles = {}
        for r in cfg.getRoleNames():
            try:
                roles[r] = cfg.getRoleColorSpace(r)
            except Exception:
                roles[r] = "(unresolved)"

        lr_lines = ["LOOKS:"] + [f"    {l}" for l in (looks or ["(none)"])]
        lr_lines += ["", "ROLES:"] + [f"    {k} -> {v}" for k, v in sorted(roles.items())]

        try:
            named = [nt.getName() for nt in cfg.getNamedTransforms()]
        except Exception:
            named = []

        info = {
            "config": path,
            "ocio_version": OCIO.GetVersion(),
            "counts": {"colorspaces": len(spaces), "displays": len(displays),
                       "views_total": sum(len(v) for v in dv_map.values()),
                       "looks": len(looks), "roles": len(roles),
                       "named_transforms": len(named)},
            "default_display": cfg.getDefaultDisplay(),
            "default_view": cfg.getDefaultView(cfg.getDefaultDisplay()) if displays else "",
            "named_transforms": named,
            "config_search_paths": _config_search_dirs(),
            "lut_search_paths": _lut_search_dirs(),
        }
        return ("\n".join(spaces), "\n".join(dv_lines), "\n".join(lr_lines),
                json.dumps(info, indent=2))


NODE_CLASS_MAPPINGS = {
    "NukeMax_CameraLogConvert": CameraLogConvert,
    "NukeMax_CameraGamutConvert": CameraGamutConvert,
    "NukeMax_ColorMatrix": ColorMatrix,
    "NukeMax_LUTApply": LUTApply,
    "NukeMax_OCIOCDLTransform": OCIOCDLTransform,
    "NukeMax_OCIOFileTransform": OCIOFileTransform,
    "NukeMax_OCIOLookTransform": OCIOLookTransform,
    "NukeMax_OCIOConfigInfo": OCIOConfigInfo,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_CameraLogConvert": "Camera Log Convert",
    "NukeMax_CameraGamutConvert": "Camera Gamut Convert",
    "NukeMax_ColorMatrix": "Color Matrix (Nuke)",
    "NukeMax_LUTApply": "LUT Apply (.cube)",
    "NukeMax_OCIOCDLTransform": "OCIO CDLTransform (Nuke)",
    "NukeMax_OCIOFileTransform": "OCIO FileTransform (Nuke)",
    "NukeMax_OCIOLookTransform": "OCIO LookTransform (Nuke)",
    "NukeMax_OCIOConfigInfo": "OCIO Config Info",
}
