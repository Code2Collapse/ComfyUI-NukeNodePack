"""OCIO Color Transform — OpenColorIO v2 integration.

Wraps PyOpenColorIO so any colorspace pair from a chosen config can be
applied to an IMAGE. Industry-standard configs (ACES Studio, Filmic,
spi-anim) work out of the box if shipped at:

  $OCIO env var (highest priority)
  ComfyUI/models/ocio_configs/<config-name>/config.ocio
  built-in fallback: identity (raises a clear error)

Float32 throughout — OCIO operates on float32 buffers natively.

If PyOpenColorIO is not installed, the node raises ImportError with a
clear install hint. We never silently fall back to a fixed matrix.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import List, Optional, Tuple

import numpy as np
import torch

import folder_paths  # type: ignore[import-not-found]

from ...utils.resilience import resilient
from ..._tensor_util import require_image_bhwc
from ..._is_changed_util import hash_args_and_kwargs


log = logging.getLogger("NukeMax.OCIO")

_FOLDER_KEY = "ocio_configs"


def _register_folder() -> None:
    """Register `ComfyUI/models/ocio_configs/` so users can drop configs there."""
    try:
        existing = folder_paths.get_folder_paths(_FOLDER_KEY)
        if existing:
            return
    except Exception:
        pass
    try:
        root = folder_paths.models_dir  # type: ignore[attr-defined]
        target = os.path.join(root, "ocio_configs")
        folder_paths.add_model_folder_path(_FOLDER_KEY, target, is_default=True)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        log.debug("Could not register ocio_configs folder: %s", exc)


_register_folder()


# OCIO 2.2+ ships built-in ACES configs (no download): the studio config
# includes ARRI LogC3 (EI800) + LogC4, camera log spaces, and full
# display/view pipelines. Listed first so the nodes work out of the box.
_BUILTIN_CONFIGS = {
    "builtin: ACES Studio (LogC3/C4, camera spaces)": "ocio://studio-config-latest",
    "builtin: ACES CG": "ocio://cg-config-latest",
    "builtin: OCIO default (ACES)": "ocio://default",
}


def _builtin_available() -> bool:
    try:
        import PyOpenColorIO as OCIO  # noqa: F401
        return hasattr(OCIO.Config, "CreateFromBuiltinConfig")
    except Exception:
        return False


def _list_configs() -> List[str]:
    """Return discoverable OCIO config display names (filename or folder)."""
    out: List[str] = []
    if _builtin_available():
        out.extend(_BUILTIN_CONFIGS.keys())
    # 1. $OCIO env var
    env = os.environ.get("OCIO")
    if env and os.path.isfile(env):
        out.append(f"$OCIO:{os.path.basename(os.path.dirname(env)) or 'env'}")
    # 2. ComfyUI/models/ocio_configs/<name>/config.ocio  (or *.ocio direct)
    try:
        roots = folder_paths.get_folder_paths(_FOLDER_KEY) or []
    except Exception:
        roots = []
    for r in roots:
        if not os.path.isdir(r):
            continue
        for name in sorted(os.listdir(r)):
            full = os.path.join(r, name)
            if os.path.isdir(full) and os.path.isfile(os.path.join(full, "config.ocio")):
                out.append(name)
            elif name.lower().endswith(".ocio"):
                out.append(name)
    if not out:
        out.append("(install PyOpenColorIO + drop config in models/ocio_configs)")
    return out


def _resolve_config_path(choice: str) -> Optional[str]:
    if choice in _BUILTIN_CONFIGS:
        return _BUILTIN_CONFIGS[choice]
    if choice.startswith("$OCIO:"):
        return os.environ.get("OCIO")
    try:
        roots = folder_paths.get_folder_paths(_FOLDER_KEY) or []
    except Exception:
        roots = []
    for r in roots:
        cand = os.path.join(r, choice, "config.ocio")
        if os.path.isfile(cand):
            return cand
        cand = os.path.join(r, choice)
        if os.path.isfile(cand):
            return cand
    return None


@lru_cache(maxsize=8)
def _load_config(path: str):
    import PyOpenColorIO as OCIO  # type: ignore[import-not-found]
    if path.startswith("ocio://"):
        return OCIO.Config.CreateFromBuiltinConfig(path)
    return OCIO.Config.CreateFromFile(path)


@lru_cache(maxsize=4)
def _colorspaces_for(path: str) -> Tuple[str, ...]:
    cfg = _load_config(path)
    return tuple(cs.getName() for cs in cfg.getColorSpaces())


def _apply_processor(image: torch.Tensor, processor) -> torch.Tensor:
    """Apply an OCIO Processor (cpu) to (B,H,W,C) float32 IMAGE.

    Uses PackedImageDesc + apply(): CPUProcessor.applyRGB(ndarray) silently
    no-ops on some PyOpenColorIO builds (observed on 2.5.2 — it transforms a
    converted copy, not the caller's buffer), which made this node an
    identity transform. PackedImageDesc mutates the frame in place reliably.
    """
    import PyOpenColorIO as OCIO  # type: ignore[import-not-found]
    cpu = processor.getDefaultCPUProcessor()
    # copy=True is load-bearing: PackedImageDesc keeps a raw pointer into the
    # buffer, and a torch-shared buffer under inference_mode (the @resilient
    # wrapper) is not stable — observed as identity output or garbage values.
    # A numpy-owned copy is safe for OCIO to mutate in place.
    arr = np.array(image.detach().cpu().float().numpy(), dtype=np.float32, copy=True)
    B, H, W, C = arr.shape
    for b in range(B):
        frame = np.ascontiguousarray(arr[b])
        cpu.apply(OCIO.PackedImageDesc(frame, W, H, C))
        arr[b] = frame
    return torch.from_numpy(arr).to(image.device)


@resilient
class OCIOColorTransform:
    """Convert IMAGE between any two colorspaces of a chosen OCIO config."""

    DESCRIPTION = (
        "Industry-standard OpenColorIO v2 color transform. Drop config "
        "folders in ComfyUI/models/ocio_configs/ (or set $OCIO env var). "
        "Requires PyOpenColorIO. Float32 scene-linear preserved."
    )
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "info_json")
    OUTPUT_TOOLTIPS = ("Transformed IMAGE.", "JSON with config path and applied transform.")


    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "Source image."}),
                "config": (_list_configs(), {"tooltip": "OCIO config (drop in models/ocio_configs/ or set $OCIO)."}),
                "src_colorspace": ("STRING", {"default": "ACES - ACES2065-1",
                                              "tooltip": "Source colorspace name (must match config exactly)."}),
                "dst_colorspace": ("STRING", {"default": "Output - sRGB",
                                              "tooltip": "Destination colorspace name."}),
            },
            "optional": {
                "list_spaces": ("BOOLEAN", {"default": False,
                                             "tooltip": "If true, emit the available colorspaces in info_json and pass image through unchanged."}),
            },
        }

    def execute(self, image: torch.Tensor, config: str, src_colorspace: str,
                dst_colorspace: str, list_spaces: bool = False):
        require_image_bhwc(image)
        import json as _json
        try:
            import PyOpenColorIO as OCIO  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "OCIOColorTransform requires PyOpenColorIO. Install via "
                "`pip install opencolorio` (Linux/macOS) or pip wheel for Windows."
            ) from exc

        path = _resolve_config_path(config)
        if not path:
            raise FileNotFoundError(
                f"OCIO config not found for choice {config!r}. "
                "Drop a config folder under ComfyUI/models/ocio_configs/ or set $OCIO."
            )

        if list_spaces:
            spaces = _colorspaces_for(path)
            info = {"config": path, "colorspaces": list(spaces)}
            return (image, _json.dumps(info, indent=2))

        cfg = _load_config(path)
        try:
            processor = cfg.getProcessor(src_colorspace, dst_colorspace)
        except Exception as exc:
            spaces = _colorspaces_for(path)
            raise ValueError(
                f"OCIO transform {src_colorspace!r} -> {dst_colorspace!r} failed: {exc}. "
                f"Available: {spaces[:10]}{'...' if len(spaces) > 10 else ''}"
            ) from exc

        out = _apply_processor(image, processor)
        info = {
            "config": path,
            "src": src_colorspace,
            "dst": dst_colorspace,
            "ocio_version": OCIO.GetVersion(),
        }
        return (out, _json.dumps(info, indent=2))


# ── OCIOLogConvert + OCIODisplay ─────────────────────────────────────
# Adapted from ComfyUI-ACES-IO — Copyright (c) 2025 Bishoy Samaan, MIT
# License, https://github.com/BISAM20/ComfyUI-ACES-IO — reworked onto this
# module's config discovery (models/ocio_configs + $OCIO), house IS_CHANGED
# (never nan), and @resilient registration.


@resilient
class OCIOLogConvert:
    """Scene-linear ↔ compositing-log via the config's roles (Nuke OCIOLogConvert)."""

    DESCRIPTION = (
        "Convert between the config's scene_linear and compositing_log roles "
        "(ACES: ACEScg ↔ ACEScct) — mirrors Nuke's OCIOLogConvert."
    )
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "config": (_list_configs(), {}),
            "operation": (("log_to_linear", "linear_to_log"), {"default": "log_to_linear"}),
        }}

    def execute(self, image: torch.Tensor, config: str, operation: str):
        require_image_bhwc(image)
        import PyOpenColorIO as OCIO  # type: ignore[import-not-found]
        path = _resolve_config_path(config)
        if not path:
            raise FileNotFoundError(f"OCIO config not found for choice {config!r}.")
        cfg = _load_config(path)
        try:
            lin = cfg.getRoleColorSpace(OCIO.ROLE_SCENE_LINEAR)
            lg = cfg.getRoleColorSpace(OCIO.ROLE_COMPOSITING_LOG)
        except Exception as exc:
            raise ValueError(
                "This config does not define the scene_linear and/or compositing_log "
                f"roles needed by OCIOLogConvert: {exc}"
            ) from exc
        src, dst = (lg, lin) if operation == "log_to_linear" else (lin, lg)
        return (_apply_processor(image, cfg.getProcessor(src, dst)),)


@resilient
class OCIODisplay:
    """Bake a display+view transform into the image (Nuke OCIODisplay)."""

    DESCRIPTION = (
        "Apply the config's display/view pipeline (e.g. sRGB / ACES SDR video) "
        "to a scene-referred image and bake it in — mirrors Nuke's OCIODisplay. "
        "Set list_options to see the available displays and views."
    )
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "info_json")

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "config": (_list_configs(), {}),
            "input_colorspace": ("STRING", {"default": "ACEScg"}),
            "display": ("STRING", {"default": "", "tooltip": "Blank = config default display."}),
            "view": ("STRING", {"default": "", "tooltip": "Blank = default view for the display."}),
        }, "optional": {
            "invert": ("BOOLEAN", {"default": False,
                       "tooltip": "Display-referred back to input colorspace (roundtrips)."}),
            "list_options": ("BOOLEAN", {"default": False,
                             "tooltip": "Pass image through; emit displays/views in info_json."}),
        }}

    def execute(self, image: torch.Tensor, config: str, input_colorspace: str,
                display: str, view: str, invert: bool = False, list_options: bool = False):
        require_image_bhwc(image)
        import json as _json
        import PyOpenColorIO as OCIO  # type: ignore[import-not-found]
        path = _resolve_config_path(config)
        if not path:
            raise FileNotFoundError(f"OCIO config not found for choice {config!r}.")
        cfg = _load_config(path)
        displays = list(cfg.getDisplays())
        if list_options:
            info = {d: list(cfg.getViews(d)) for d in displays}
            return (image, _json.dumps({"config": path, "displays": info}, indent=2))
        # Tolerate stale widget values across config swaps (ACES-IO behaviour):
        # fall back to the config defaults rather than erroring.
        d = display.strip() if display.strip() in displays else cfg.getDefaultDisplay()
        views = list(cfg.getViews(d))
        v = view.strip() if view.strip() in views else cfg.getDefaultView(d)
        dv = OCIO.DisplayViewTransform()
        dv.setSrc(input_colorspace.strip())
        dv.setDisplay(d)
        dv.setView(v)
        if invert:
            dv.setDirection(OCIO.TransformDirection.TRANSFORM_DIR_INVERSE)
        try:
            proc = cfg.getProcessor(dv)
        except Exception as exc:
            raise ValueError(
                f"OCIODisplay failed (src={input_colorspace!r}, display={d!r}, "
                f"view={v!r}, invert={invert}): {exc}. Available displays: {displays}"
            ) from exc
        out = _apply_processor(image, proc)
        info = {"config": path, "display": d, "view": v, "invert": invert}
        return (out, _json.dumps(info, indent=2))


NODE_CLASS_MAPPINGS = {
    "NukeMax_OCIOColorTransform": OCIOColorTransform,
    "NukeMax_OCIOLogConvert": OCIOLogConvert,
    "NukeMax_OCIODisplay": OCIODisplay,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_OCIOColorTransform": "OCIO Color Transform",
    "NukeMax_OCIOLogConvert": "OCIO Log Convert (Nuke)",
    "NukeMax_OCIODisplay": "OCIO Display (Nuke)",
}