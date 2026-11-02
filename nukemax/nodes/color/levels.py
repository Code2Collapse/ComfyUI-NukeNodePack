# PORTED FROM: nuke-nodes-comfyui (third_party/nuke-nodes-comfyui) by Sumit Chatterjee
# Licence: MIT — direct copy authorised by owner; attribution retained.
"""Nuke-style input/output levels adjustment."""
from __future__ import annotations

import torch

from ...utils.resilience import resilient
from ..._tensor_util import require_image_bhwc
from ..._is_changed_util import hash_args_and_kwargs


@resilient
class NukeMax_Levels:
    DESCRIPTION = "Remap input black/white through gamma to output black/white with mix, Nuke ColorLookup-style."
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "input_black": (
                    "FLOAT",
                    {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01},
                ),
                "input_white": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.0, "max": 64.0, "step": 0.01},
                ),
                "gamma": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.1, "max": 3.0, "step": 0.01},
                ),
                "output_black": (
                    "FLOAT",
                    {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01},
                ),
                "output_white": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.0, "max": 64.0, "step": 0.01},
                ),
                "mix": (
                    "FLOAT",
                    {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01},
                ),
            },
            "optional": {
                "clamp": ("BOOLEAN", {"default": True, "tooltip": "On: the input is clamped to input black..white (classic Levels). Off: values below black and above white keep going - HDR and negatives survive (L9.80 slice 6)."}),
            },
        }

    def execute(
        self,
        image,
        input_black,
        input_white,
        gamma,
        output_black,
        output_white,
        mix,
        clamp=True,
    ):
        require_image_bhwc(image)
        img = image

        if img.shape[3] >= 4:
            rgb = img[..., :3]
            alpha = img[..., 3:4]
        else:
            rgb = img[..., :3]
            alpha = None

        input_range = max(float(input_white) - float(input_black), 1e-7)
        rgb_normalized = (rgb - input_black) / input_range
        if clamp:
            rgb_normalized = torch.clamp(rgb_normalized, 0.0, 1.0)

        safe_gamma = max(float(gamma), 0.1)
        # gamma on the positive part only (as Nuke's Grade): a fractional power of a negative is NaN
        rgb_gamma = torch.where(rgb_normalized > 0, rgb_normalized.clamp(min=0) ** (1.0 / safe_gamma),
                                rgb_normalized)

        output_range = float(output_white) - float(output_black)
        rgb_final = rgb_gamma * output_range + output_black

        rgb_final = rgb + (rgb_final - rgb) * mix

        if alpha is not None:
            result = torch.cat([rgb_final, alpha], dim=-1)
        else:
            result = rgb_final

        return (result.contiguous(),)


NODE_CLASS_MAPPINGS = {
    "NukeMax_Levels": NukeMax_Levels,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_Levels": "Levels (NukeMax)",
}
