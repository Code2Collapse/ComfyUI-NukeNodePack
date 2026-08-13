"""Comp-operator tier — Merge / Keying batch.

The two Nuke merge-and-key operators that had no equivalent in this pack:

  Copy      route channels from A into B, keeping B's format (Nuke Copy).
            The existing Shuffle node has a single input, so "put A's matte on
            B" was not expressible anywhere in the pack before this.
  HueKeyer  pull a matte from a hue + saturation range.

Already registered by earlier batches and deliberately **not** duplicated:
Merge, Dissolve, Keymix, Switch, Premult, Unpremult, ChromaKeyer, Keyer,
Difference, Despill, ShuffleImage, EXRChannelRouter.

Contract: linear float in, linear float out. Colour channels are never
clamped; mattes are, because 0..1 coverage is a ComfyUI MASK's definition.
"""
from __future__ import annotations

import torch

from .._is_changed_util import hash_args_and_kwargs
from ._comp_linear import (
    hue_degrees,
    match_batch,
    match_size,
    require_image,
)

# Sources a Copy output channel can be wired from.
_SOURCES = ("B.R", "B.G", "B.B", "B.A", "B.Lum",
            "A.R", "A.G", "A.B", "A.A", "A.Lum",
            "0", "1")


def _channel(a, b, code):
    """Pull one [B,H,W] plane named by ``code`` from image A or B."""
    src = a if code.startswith("A.") else b
    which = code.split(".")[-1] if "." in code else code
    if code == "0":
        return torch.zeros_like(b[..., 0])
    if code == "1":
        return torch.ones_like(b[..., 0])
    c = src.shape[-1]
    if which == "R":
        return src[..., 0]
    if which == "G":
        return src[..., 1] if c > 1 else src[..., 0]
    if which == "B":
        return src[..., 2] if c > 2 else src[..., 0]
    if which == "A":
        if c > 3:
            return src[..., 3]
        # A solid matte is the honest answer for an image with no alpha, but
        # say so rather than letting a silent 1.0 look like a real key.
        raise ValueError(
            f"'{code}' was requested but that input has {c} channel(s) and no alpha. "
            f"Feed an RGBA image, or pick a different source for that output channel."
        )
    # Lum
    r = src[..., 0]
    g = src[..., 1] if c > 1 else r
    bl = src[..., 2] if c > 2 else r
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl


class Copy:
    DESCRIPTION = ("Nuke Copy: build an output from B's format by routing each of R/G/B/A "
                   "from either input. The default copies A's alpha onto B's RGB — the "
                   "standard 'attach this matte to that plate' move. Values pass through "
                   "unchanged, so an HDR plate stays HDR.")
    CATEGORY = "NukeMax/Channel"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "alpha")

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "A": ("IMAGE", {"tooltip": "Source of the copied channels."}),
                "B": ("IMAGE", {"tooltip": "Background. The output takes B's resolution."}),
                "out_R": (_SOURCES, {"default": "B.R"}),
                "out_G": (_SOURCES, {"default": "B.G"}),
                "out_B": (_SOURCES, {"default": "B.B"}),
                "out_A": (_SOURCES, {"default": "A.A"}),
            }
        }

    def execute(self, A, B, out_R, out_G, out_B, out_A):
        require_image(A, "A")
        require_image(B, "B")
        a = match_batch(match_size(A, B), B, "A")
        planes = [_channel(a, B, out_R), _channel(a, B, out_G),
                  _channel(a, B, out_B), _channel(a, B, out_A)]
        out = torch.stack(planes, dim=-1).contiguous()
        return (out, out[..., 3].contiguous())


class HueKeyer:
    DESCRIPTION = ("Pull a matte from a hue range with a saturation floor — the fast way to "
                   "isolate 'everything green' or 'that red jacket' without a screen. Hue and "
                   "saturation are both measured scale-invariantly, so an HDR pixel at 8.0 "
                   "keys the same as the identical colour at 0.8.")
    CATEGORY = "NukeMax/Keying"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "matte")

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {}),
                "hue_center": ("FLOAT", {"default": 120.0, "min": 0.0, "max": 360.0, "step": 1.0,
                                         "tooltip": "0=red, 60=yellow, 120=green, 180=cyan, "
                                                    "240=blue, 300=magenta."}),
                "hue_width": ("FLOAT", {"default": 40.0, "min": 0.0, "max": 180.0, "step": 1.0,
                                        "tooltip": "Half-width of the fully-keyed band, in degrees."}),
                "hue_softness": ("FLOAT", {"default": 20.0, "min": 0.0, "max": 180.0, "step": 1.0,
                                           "tooltip": "Degrees of falloff outside the band."}),
                "min_saturation": ("FLOAT", {"default": 0.15, "min": 0.0, "max": 1.0, "step": 0.005,
                                             "tooltip": "Below this, a pixel is too grey to have a "
                                                        "reliable hue and is excluded."}),
                "saturation_softness": ("FLOAT", {"default": 0.1, "min": 0.001, "max": 1.0, "step": 0.005}),
                "invert": ("BOOLEAN", {"default": False}),
                "set_alpha": ("BOOLEAN", {"default": True,
                              "tooltip": "Write the matte into the output image's alpha channel."}),
            }
        }

    def execute(self, image, hue_center, hue_width, hue_softness, min_saturation,
                saturation_softness, invert, set_alpha):
        require_image(image)
        if image.shape[-1] < 3:
            raise ValueError(
                f"HueKeyer needs at least 3 channels to measure hue; the input has "
                f"{image.shape[-1]}. Feed an RGB or RGBA image."
            )
        rgb = image[..., :3]
        h = hue_degrees(rgb)

        d = (h - float(hue_center)).abs()
        d = torch.minimum(d, 360.0 - d)
        soft = max(1e-4, float(hue_softness))
        hue_m = (1.0 - (d - float(hue_width)).clamp(min=0.0) / soft).clamp(0.0, 1.0)

        mx, _ = rgb.max(dim=-1)
        mn, _ = rgb.min(dim=-1)
        sat = torch.where(mx.abs() > 1e-9, (mx - mn) / mx.abs(), torch.zeros_like(mx))
        s_soft = max(1e-4, float(saturation_softness))
        sat_m = ((sat - float(min_saturation)) / s_soft).clamp(0.0, 1.0)

        matte = (hue_m * sat_m).clamp(0.0, 1.0)
        if invert:
            matte = 1.0 - matte

        out = image
        if set_alpha:
            if image.shape[-1] >= 4:
                out = torch.cat([image[..., :3], matte.unsqueeze(-1), image[..., 4:]], dim=-1)
            else:
                out = torch.cat([image[..., :3], matte.unsqueeze(-1)], dim=-1)
        return (out.contiguous(), matte.contiguous())


NODE_CLASS_MAPPINGS = {
    "NukeMax_Copy": Copy,
    "NukeMax_HueKeyer": HueKeyer,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_Copy": "Copy (NukeMax)",
    "NukeMax_HueKeyer": "HueKeyer (NukeMax)",
}
