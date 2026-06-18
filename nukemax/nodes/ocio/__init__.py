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


def _list_configs() -> List[str]:
    """Return discoverable OCIO config display names (filename or folder)."""
    out: List[str] = []
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
    return OCIO.Config.CreateFromFile(path)


@lru_cache(maxsize=4)
def _colorspaces_for(path: str) -> Tuple[str, ...]:
    cfg = _load_config(path)
    return tuple(cs.getName() for cs in cfg.getColorSpaces())


def _apply_processor(image: torch.Tensor, processor) -> torch.Tensor:
    """Apply an OCIO Processor (cpu) to (B,H,W,3) float32 IMAGE."""
    cpu = processor.getDefaultCPUProcessor()
    arr = image.detach().cpu().contiguous().float().numpy()
    out = np.empty_like(arr)
    for b in range(arr.shape[0]):
        buf = np.ascontiguousarray(arr[b])  # (H,W,3)
        cpu.applyRGB(buf)
        out[b] = buf
    return torch.from_numpy(out).to(image.device)


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


NODE_CLASS_MAPPINGS = {"NukeMax_OCIOColorTransform": OCIOColorTransform}
NODE_DISPLAY_NAME_MAPPINGS = {"NukeMax_OCIOColorTransform": "OCIO Color Transform"}
