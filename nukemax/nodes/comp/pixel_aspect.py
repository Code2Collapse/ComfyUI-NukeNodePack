"""Pixel Aspect Ratio round-trip — Nuke-parity anamorphic handling.

Nuke shows a 4448x3840 plate as ~2:1 because its FORMAT carries PAR 1.7266;
ComfyUI (like all AI tools) assumes square pixels and sees 1.158:1, so AI
passes distort once the lens squeeze is reapplied. These two nodes implement
the standard pipeline: desqueeze to square pixels before AI (4448x3840 →
7680x3840 true 2:1), resqueeze back to the plate's exact pixel dimensions
after. par_info JSON carries the undo data so the round trip is exact.

Same wire contract as CustomNodePacks' PARDesqueezeMEC/PARResqueezeMEC —
the par_info strings are interchangeable between the packs.

Author: Code2Collapse. Apache-2.0.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Tuple

import torch
import torch.nn.functional as F

from ...utils.resilience import resilient
from ..._tensor_util import require_image_bhwc
from ..._is_changed_util import hash_args_and_kwargs

PAR_PRESETS: Dict[str, float] = {
    "custom": 0.0,
    "square 1.0": 1.0,
    "anamorphic 2x (2.0)": 2.0,
    "anamorphic 1.8x (1.8)": 1.8,
    "ARRI 4448x3840→2:1 (1.7266)": 1.7266,
    "anamorphic 1.5x (1.5)": 1.5,
    "anamorphic 1.33x (1.33)": 1.33,
    "NTSC DV (0.9091)": 0.9091,
    "PAL DV (1.0940)": 1.0940,
}


def _resize(img: torch.Tensor, w: int, h: int, filt: str) -> torch.Tensor:
    x = img.permute(0, 3, 1, 2)
    kw = {} if filt in ("nearest", "area") else {"align_corners": False}
    x = F.interpolate(x, size=(h, w), mode=filt, **kw)
    return x.permute(0, 2, 3, 1).clamp(0, 1)


def _resolve_par(preset: str, pixel_aspect: float) -> float:
    v = PAR_PRESETS.get(preset, 0.0)
    par = v if v > 0 else float(pixel_aspect)
    if par <= 0:
        raise ValueError("pixel_aspect must be > 0.")
    return par


@resilient
class PARDesqueeze:
    DESCRIPTION = ("Anamorphic plate → SQUARE pixels for AI processing (Nuke: "
                   "4448x3840 @ PAR 1.7266 → 7680x3840 at 2:1). par_info feeds "
                   "PAR Resqueeze for an exact round trip.")
    CATEGORY = "NukeMax/Transform"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "par_info")

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "par_preset": (tuple(PAR_PRESETS.keys()),
                           {"default": "ARRI 4448x3840→2:1 (1.7266)"}),
            "pixel_aspect": ("FLOAT", {"default": 1.7266, "min": 0.1, "max": 4.0,
                             "step": 0.0001,
                             "tooltip": "Used when par_preset = custom."}),
            "method": (("stretch_width", "squash_height"), {"default": "stretch_width"}),
            "filter": (("bicubic", "bilinear", "nearest", "area"), {"default": "bicubic"}),
        }}

    def execute(self, image: torch.Tensor, par_preset: str, pixel_aspect: float,
                method: str, filter: str) -> Tuple[torch.Tensor, str]:
        require_image_bhwc(image)
        if image.ndim == 3:
            image = image.unsqueeze(0)
        b, h0, w0, c = image.shape
        par = _resolve_par(par_preset, pixel_aspect)
        if abs(par - 1.0) < 1e-6:
            out, nw, nh = image, w0, h0
        elif method == "squash_height":
            nw, nh = w0, max(1, round(h0 / par))
            out = _resize(image, nw, nh, filter)
        else:
            nw, nh = max(1, round(w0 * par)), h0
            out = _resize(image, nw, nh, filter)
        info = json.dumps({
            "orig_width": w0, "orig_height": h0, "pixel_aspect": par,
            "method": method, "filter": filter,
            "square_width": nw, "square_height": nh,
            "display_aspect": round((w0 * par) / h0, 4),
        })
        return (out, info)


@resilient
class PARResqueeze:
    DESCRIPTION = ("Square-pixel AI output → the plate's original pixel dimensions "
                   "(reapply PAR in Nuke's format). Exact W×H restore, even if the "
                   "AI changed resolution.")
    CATEGORY = "NukeMax/Transform"
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
            "par_info": ("STRING", {"default": "", "forceInput": True}),
            "filter": (("bicubic", "bilinear", "nearest", "area"), {"default": "bicubic"}),
        }}

    def execute(self, image: torch.Tensor, par_info: str, filter: str) -> Tuple[torch.Tensor, str]:
        require_image_bhwc(image)
        if image.ndim == 3:
            image = image.unsqueeze(0)
        try:
            meta: Dict[str, Any] = json.loads(par_info or "{}")
            w = int(meta["orig_width"])
            h = int(meta["orig_height"])
        except Exception as exc:
            raise ValueError(
                "par_info is not valid PAR Desqueeze output — wire that node's "
                f"par_info here ({exc})."
            ) from exc
        out = image if (image.shape[2] == w and image.shape[1] == h) \
            else _resize(image, w, h, filter)
        return (out, json.dumps({"restored_width": w, "restored_height": h,
                                 "pixel_aspect": meta.get("pixel_aspect", 1.0)}))


NODE_CLASS_MAPPINGS = {
    "NukeMax_PARDesqueeze": PARDesqueeze,
    "NukeMax_PARResqueeze": PARResqueeze,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_PARDesqueeze": "PAR Desqueeze (anamorphic → square px)",
    "NukeMax_PARResqueeze": "PAR Resqueeze (back to plate)",
}
