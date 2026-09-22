# PORTED FROM: nuke-nodes-comfyui (third_party/nuke-nodes-comfyui) by Sumit Chatterjee
# Licence: MIT — direct copy authorised by owner; attribution retained.
"""Nuke-style viewer — processes the frame and previews it on the node."""
from __future__ import annotations

import logging
import os
import random

import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)

#: How many frames of a sequence get a preview thumbnail. A 200-frame render
#: would otherwise write 200 PNGs per queue just to fill a 200px-wide widget.
MAX_PREVIEW_FRAMES = 8

from ...utils.resilience import resilient
from ..._tensor_util import require_image_bhwc
from ..._is_changed_util import hash_args_and_kwargs


_CHANNEL_LABELS = (
    "rgba", "rgb", "red", "green", "blue", "alpha", "luminance",
)


@resilient
class NukeMax_Viewer:
    DESCRIPTION = "Preview an IMAGE with Nuke-style channel isolation, gamma, gain, and optional mask overlay."
    CATEGORY = "NukeMax/Viewer"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "channel": (
                    _CHANNEL_LABELS,
                    {"default": "rgba"},
                ),
                "gamma": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.1, "max": 3.0, "step": 0.1},
                ),
                "gain": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.1, "max": 5.0, "step": 0.1},
                ),
                "show_overlay": ("BOOLEAN", {"default": False}),
                "overlay_text": ("STRING", {"default": ""}),
            },
            "optional": {
                "mask": ("MASK",),
            },
        }

    def execute(
        self,
        image,
        channel,
        gamma,
        gain,
        show_overlay,
        overlay_text,
        mask=None,
    ):
        require_image_bhwc(image)
        img = image

        safe_gamma = max(float(gamma), 0.1)
        img_processed = torch.pow(torch.clamp(img * gain, 0, 1), 1.0 / safe_gamma)

        if img_processed.shape[3] >= 4:
            r = img_processed[..., 0:1]
            g = img_processed[..., 1:2]
            b = img_processed[..., 2:3]
            a = img_processed[..., 3:4]
        else:
            r = img_processed[..., 0:1]
            g = (
                img_processed[..., 1:2]
                if img_processed.shape[3] > 1
                else torch.zeros_like(r)
            )
            b = (
                img_processed[..., 2:3]
                if img_processed.shape[3] > 2
                else torch.zeros_like(r)
            )
            a = torch.ones_like(r)

        if channel == "rgba":
            if img_processed.shape[3] >= 4:
                result = img_processed
            else:
                result = torch.cat(
                    [img_processed, torch.ones_like(img_processed[..., :1])],
                    dim=-1,
                )
        elif channel == "rgb":
            result = torch.cat([r, g, b], dim=-1)
        elif channel == "red":
            result = torch.cat([r, r, r], dim=-1)
        elif channel == "green":
            result = torch.cat([g, g, g], dim=-1)
        elif channel == "blue":
            result = torch.cat([b, b, b], dim=-1)
        elif channel == "alpha":
            result = torch.cat([a, a, a], dim=-1)
        elif channel == "luminance":
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            result = torch.cat([lum, lum, lum], dim=-1)
        else:
            result = img_processed

        if mask is not None and show_overlay:
            m = mask.unsqueeze(-1) if mask.dim() == 3 else mask[..., :1]
            m = m.to(device=result.device, dtype=result.dtype)
            if m.shape[1:3] != result.shape[1:3]:
                m = F.interpolate(
                    m.permute(0, 3, 1, 2),
                    size=result.shape[1:3],
                    mode="bilinear",
                    align_corners=False,
                ).permute(0, 2, 3, 1)
            if m.shape[0] != result.shape[0]:
                if m.shape[0] == 1:
                    m = m.expand(result.shape[0], *m.shape[1:])
                else:
                    raise ValueError(
                        f"mask has {m.shape[0]} frames but image has {result.shape[0]}"
                    )
            overlay_color = torch.tensor(
                [1.0, 0.0, 0.0], device=result.device, dtype=result.dtype
            ).view(1, 1, 1, 3)
            result = result + m * overlay_color * 0.3

        channel_line = (
            f"channel={channel}  gamma={gamma:.2f}  gain={gain:.2f}  "
            f"channels: rgba, rgb, red, green, blue, alpha, luminance"
        )
        ui_text = channel_line
        if overlay_text.strip():
            ui_text = f"{channel_line}\n{overlay_text.strip()}"

        result = result[..., :3].clamp(0, 1).contiguous()
        return {
            "ui": {"text": [ui_text], "images": _write_previews(result)},
            "result": (result,),
        }


def _write_previews(result: torch.Tensor) -> list:
    """Write display-referred PNGs to ComfyUI's temp dir for the on-node viewer.

    Returns the `ui.images` entries the frontend needs. Never raises: a preview
    that cannot be written must not fail a render that otherwise succeeded, so
    a failure comes back as an empty list and the widget says why.
    """
    try:
        import folder_paths
        from PIL import Image
        import numpy as np
    except Exception as exc:  # noqa: BLE001
        logger.info("[NukeMax] Viewer preview unavailable: %s", exc)
        return []

    try:
        out_dir = folder_paths.get_temp_directory()
        os.makedirs(out_dir, exist_ok=True)
        # A fresh prefix per run: the browser caches /view aggressively, and a
        # stable name shows the PREVIOUS render after a parameter change.
        prefix = f"nukemax_viewer_{random.randint(0, 0xFFFFFFFF):08x}"
        frames = result[:MAX_PREVIEW_FRAMES]
        entries = []
        for i in range(frames.shape[0]):
            arr = (frames[i].detach().cpu().numpy() * 255.0).clip(0, 255)
            img = Image.fromarray(arr.astype(np.uint8), mode="RGB")
            name = f"{prefix}_{i:03d}.png"
            img.save(os.path.join(out_dir, name), compress_level=4)
            entries.append({"filename": name, "subfolder": "", "type": "temp"})
        return entries
    except Exception as exc:  # noqa: BLE001
        logger.info("[NukeMax] Viewer preview could not be written: %s", exc)
        return []


NODE_CLASS_MAPPINGS = {
    "NukeMax_Viewer": NukeMax_Viewer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_Viewer": "Viewer (NukeMax)",
}
