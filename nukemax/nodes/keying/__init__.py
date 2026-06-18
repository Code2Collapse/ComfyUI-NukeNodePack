"""Keying — Nuke-style keyer + premult math.

A compositing pack with no keyer forces a round-trip to Nuke for the most
common task of all: pulling a matte off a green/blue screen. This ecosystem
adds that, plus the premultiply/unpremultiply pair every correct `Merge (over)`
depends on.

Nodes:
  - ChromaKeyer  : screen-colour difference keyer with softness + despill,
                   outputs despilled IMAGE + MASK (alpha). Equivalent to a
                   light Keylight/IBK for the everyday case.
  - Premult      : RGB *= alpha  (straight → premultiplied).
  - Unpremult    : RGB /= alpha  (premultiplied → straight, /0 guarded).

All ops are pure-torch on [B,H,W,C] float 0..1 tensors.
"""
from __future__ import annotations

import torch

from ...utils.resilience import resilient
from ..._tensor_util import require_image_bhwc
from ..._is_changed_util import hash_args_and_kwargs


def _rgb_a(image: torch.Tensor):
    """Split [B,H,W,C] into R,G,B and (alpha or ones)."""
    C = image.shape[-1]
    R = image[..., 0]
    G = image[..., 1] if C > 1 else R
    B = image[..., 2] if C > 2 else R
    A = image[..., 3] if C > 3 else torch.ones_like(R)
    return image, R, G, B, A


@resilient
class ChromaKeyer:
    DESCRIPTION = "Screen-colour difference keyer with softness and despill. Outputs the despilled image plus an alpha matte (foreground = 1)."
    CATEGORY = "NukeMax/Keying"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "matte")
    OUTPUT_TOOLTIPS = (
        "Input RGB with screen spill suppressed.",
        "Alpha matte: 1 on the foreground subject, 0 on the screen.",
    )


    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "Footage shot against a coloured screen."}),
                "screen": (("green", "blue", "red"), {"default": "green",
                            "tooltip": "Which screen colour to key out."}),
                "tolerance": ("FLOAT", {"default": 0.05, "min": -1.0, "max": 1.0, "step": 0.005,
                            "tooltip": "Where the matte starts to open. Lower = keys more of the screen."}),
                "softness": ("FLOAT", {"default": 0.20, "min": 0.001, "max": 1.0, "step": 0.005,
                            "tooltip": "Width of the soft edge between full foreground and full screen."}),
                "despill": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                            "tooltip": "How strongly to pull screen colour out of the edges (1 = full)."}),
            },
        }

    def execute(self, image, screen, tolerance, softness, despill):
        require_image_bhwc(image)
        image, R, G, B, _A = _rgb_a(image)
        if screen == "green":
            prim, other = G, torch.maximum(R, B)
            ci = 1
        elif screen == "blue":
            prim, other = B, torch.maximum(R, G)
            ci = 2
        else:
            prim, other = R, torch.maximum(G, B)
            ci = 0
        # Screen "dominance": positive where the screen colour outweighs the rest.
        d = prim - other
        hi = tolerance + max(1e-4, float(softness))
        bg = ((d - tolerance) / (hi - tolerance)).clamp(0.0, 1.0)   # 1 = pure screen
        matte = (1.0 - bg).clamp(0.0, 1.0)                          # 1 = foreground

        rgb = image[..., :3].clone()
        if despill > 0.0:
            # Suppress the screen channel down toward the other channels in spill areas.
            spill = (d.clamp(min=0.0)) * float(despill)
            new_prim = torch.maximum(prim - spill, other)
            rgb[..., ci] = torch.minimum(rgb[..., ci], new_prim)
        rgb = rgb.clamp(0.0, 1.0).contiguous()
        return (rgb, matte)


@resilient
class Premult:
    DESCRIPTION = "Premultiply: multiply RGB by an alpha matte (straight → premultiplied), as required before a Merge (over)."
    CATEGORY = "NukeMax/Keying"
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
                "image": ("IMAGE", {}),
                "alpha": ("MASK", {"tooltip": "Matte to premultiply with (1 keeps, 0 zeroes)."}),
            },
        }

    def execute(self, image, alpha):
        require_image_bhwc(image)
        image, R, _G, _B, _A = _rgb_a(image)
        a = alpha
        if a.dim() == 2:
            a = a.unsqueeze(0)
        # broadcast mask [B,H,W] -> [B,H,W,1] and match batch
        a = a.unsqueeze(-1)
        if a.shape[0] != image.shape[0] and a.shape[0] == 1:
            a = a.expand(image.shape[0], -1, -1, -1)
        rgb = (image[..., :3] * a).clamp(0.0, 1.0).contiguous()
        return (rgb,)


@resilient
class Unpremult:
    DESCRIPTION = "Unpremultiply: divide RGB by an alpha matte (premultiplied → straight) so colour ops act on un-darkened edges. Division by zero is guarded."
    CATEGORY = "NukeMax/Keying"
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
                "image": ("IMAGE", {}),
                "alpha": ("MASK", {"tooltip": "Matte to divide by; zero-alpha pixels are left unchanged."}),
            },
        }

    def execute(self, image, alpha):
        require_image_bhwc(image)
        image, R, _G, _B, _A = _rgb_a(image)
        a = alpha
        if a.dim() == 2:
            a = a.unsqueeze(0)
        a = a.unsqueeze(-1)
        if a.shape[0] != image.shape[0] and a.shape[0] == 1:
            a = a.expand(image.shape[0], -1, -1, -1)
        safe = a.clamp(min=1e-5)
        rgb = torch.where(a > 1e-5, image[..., :3] / safe, image[..., :3])
        rgb = rgb.clamp(0.0, 1.0).contiguous()
        return (rgb,)


NODE_CLASS_MAPPINGS = {
    "NukeMax_ChromaKeyer": ChromaKeyer,
    "NukeMax_Premult": Premult,
    "NukeMax_Unpremult": Unpremult,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_ChromaKeyer": "Chroma Keyer (NukeMax)",
    "NukeMax_Premult": "Premult (NukeMax)",
    "NukeMax_Unpremult": "Unpremult (NukeMax)",
}