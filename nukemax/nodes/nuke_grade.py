"""Comp-operator tier — Grade batch.

The three Nuke grade operators that had no equivalent anywhere in this pack:

  ColorLookup  per-channel lookup curves with linear extrapolation
  SoftClip     asymptotic highlight/shadow rolloff — the *correct* answer to
               "this is too bright", as opposed to a hard clamp
  HueCorrect   per-hue saturation / luminance correction

Existing operators (Grade, ColorCorrect, Gamma, Multiply, Add, Exposure,
Saturation, ChannelMixer, HueShift, Log2Lin, Posterize, Clamp) were already
registered by earlier batches and are **not** duplicated here.

Contract: linear float in, linear float out. Nothing clamps to 0..1, all four
of R/G/B/A plus any AOV channels beyond them survive, and every failure raises
a message naming the input and the fix rather than returning a black frame.
"""
from __future__ import annotations

import torch

from .._is_changed_util import hash_args_and_kwargs
from ._comp_linear import (
    blend_with_mask,
    eval_curve,
    hue_bucket_weights,
    hue_degrees,
    join_rgb_alpha,
    luma,
    parse_curve,
    require_image,
    split_rgb_alpha,
)

_IDENTITY_CURVE = "0,0; 1,1"
_CURVE_HELP = ("Control points as 'x,y' pairs separated by ';'. The curve is "
               "linearly extrapolated past the first and last point, so values "
               "above 1.0 keep moving instead of flattening into a clamp.")


class ColorLookup:
    DESCRIPTION = ("Nuke ColorLookup: a master lookup curve followed by per-channel "
                   "R/G/B/A curves. Piecewise-linear between control points and "
                   "linearly extrapolated beyond them, so HDR values above 1.0 are "
                   "remapped rather than clipped.")
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        curve = lambda: ("STRING", {"default": _IDENTITY_CURVE, "multiline": False,
                                    "tooltip": _CURVE_HELP})
        return {
            "required": {
                "image": ("IMAGE", {}),
                "master": curve(),
                "red": curve(),
                "green": curve(),
                "blue": curve(),
                "alpha": curve(),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01,
                                  "tooltip": "Dissolve the result back toward the input."}),
            },
            "optional": {"mask": ("MASK", {})},
        }

    @staticmethod
    def _is_identity(points) -> bool:
        return len(points) == 2 and points[0] == (0.0, 0.0) and points[1] == (1.0, 1.0)

    def execute(self, image, master, red, green, blue, alpha, mix, mask=None):
        require_image(image)
        rgb, a, extra = split_rgb_alpha(image)
        out = rgb

        m_pts = parse_curve(master, "master")
        if not self._is_identity(m_pts):
            out = eval_curve(out, m_pts)

        per_channel = (parse_curve(red, "red"),
                       parse_curve(green, "green"),
                       parse_curve(blue, "blue"))
        if any(not self._is_identity(p) for p in per_channel):
            chans = []
            for i, pts in enumerate(per_channel):
                c = out[..., i:i + 1]
                chans.append(c if self._is_identity(pts) else eval_curve(c, pts))
            out = torch.cat(chans, dim=-1)

        a_out = a
        if a is not None:
            a_pts = parse_curve(alpha, "alpha")
            if not self._is_identity(a_pts):
                a_out = eval_curve(a, a_pts)

        f = float(mix)
        if f < 1.0:
            out = rgb + (out - rgb) * f
            if a_out is not None and a is not None:
                a_out = a + (a_out - a) * f
        out = blend_with_mask(rgb, out, mask)
        return (join_rgb_alpha(out, a_out, extra),)


class SoftClip:
    DESCRIPTION = ("Nuke SoftClip: roll highlights off asymptotically toward a ceiling "
                   "instead of clipping them flat. Below 'knee' the image is untouched "
                   "and the slope is continuous at the knee, so no visible edge appears. "
                   "Optionally does the same on the shadow side.")
    CATEGORY = "NukeMax/Color"
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
                "knee": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 100.0, "step": 0.01,
                                   "tooltip": "Values below this are passed through unchanged."}),
                "ceiling": ("FLOAT", {"default": 4.0, "min": -10.0, "max": 1000.0, "step": 0.1,
                                      "tooltip": "Asymptote. Output approaches but never reaches it. "
                                                 "Must be greater than 'knee'."}),
                "roll_shadows": ("BOOLEAN", {"default": False,
                                             "tooltip": "Mirror the rolloff below 'shadow_knee'."}),
                "shadow_knee": ("FLOAT", {"default": 0.0, "min": -100.0, "max": 10.0, "step": 0.01}),
                "floor": ("FLOAT", {"default": -1.0, "min": -1000.0, "max": 10.0, "step": 0.1,
                                    "tooltip": "Lower asymptote. Must be less than 'shadow_knee'."}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": {"mask": ("MASK", {})},
        }

    @staticmethod
    def _roll_high(x, knee, ceiling):
        span = ceiling - knee
        over = (x - knee).clamp(min=0.0)
        return torch.where(x > knee, knee + span * (1.0 - torch.exp(-over / span)), x)

    def execute(self, image, knee, ceiling, roll_shadows, shadow_knee, floor, mix, mask=None):
        require_image(image)
        k, c = float(knee), float(ceiling)
        if c <= k:
            raise ValueError(
                f"'ceiling' ({c}) must be greater than 'knee' ({k}); otherwise there is "
                f"no headroom to roll off into. Raise 'ceiling' or lower 'knee'."
            )
        rgb, a, extra = split_rgb_alpha(image)
        out = self._roll_high(rgb, k, c)

        if roll_shadows:
            sk, fl = float(shadow_knee), float(floor)
            if fl >= sk:
                raise ValueError(
                    f"'floor' ({fl}) must be less than 'shadow_knee' ({sk}) when "
                    f"'roll_shadows' is on. Lower 'floor' or raise 'shadow_knee'."
                )
            # Mirror the highlight rolloff about the shadow knee.
            out = -self._roll_high(-out, -sk, -fl)

        f = float(mix)
        if f < 1.0:
            out = rgb + (out - rgb) * f
        out = blend_with_mask(rgb, out, mask)
        return (join_rgb_alpha(out, a, extra),)


class HueCorrect:
    DESCRIPTION = ("Nuke HueCorrect: six hue buckets (red/yellow/green/cyan/blue/magenta) "
                   "each drive a gain on either saturation or luminance. Weights are "
                   "triangular with 60-degree spacing, so leaving every gain at 1.0 is an "
                   "exact identity. Hue is measured scale-invariantly, so HDR pixels are "
                   "bucketed correctly instead of all reading as white.")
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        gain = lambda: ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.01})
        return {
            "required": {
                "image": ("IMAGE", {}),
                "target": (("saturation", "luminance"), {"default": "saturation",
                           "tooltip": "saturation = chroma gain about Rec.709 luma; "
                                      "luminance = overall gain on that hue."}),
                "red": gain(),
                "yellow": gain(),
                "green": gain(),
                "cyan": gain(),
                "blue": gain(),
                "magenta": gain(),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": {"mask": ("MASK", {})},
        }

    def execute(self, image, target, red, yellow, green, cyan, blue, magenta, mix, mask=None):
        require_image(image)
        rgb, a, extra = split_rgb_alpha(image)
        gains = [float(red), float(yellow), float(green),
                 float(cyan), float(blue), float(magenta)]
        if all(g == 1.0 for g in gains) or float(mix) == 0.0:
            return (join_rgb_alpha(rgb, a, extra),)

        w = hue_bucket_weights(hue_degrees(rgb))               # [B,H,W,6]
        gv = torch.tensor(gains, device=rgb.device, dtype=rgb.dtype)
        gain = (w * gv).sum(dim=-1, keepdim=True)              # [B,H,W,1]

        if target == "saturation":
            l = luma(rgb).unsqueeze(-1)
            out = l + (rgb - l) * gain
        else:
            out = rgb * gain

        f = float(mix)
        if f < 1.0:
            out = rgb + (out - rgb) * f
        out = blend_with_mask(rgb, out, mask)
        return (join_rgb_alpha(out, a, extra),)


NODE_CLASS_MAPPINGS = {
    "NukeMax_ColorLookup": ColorLookup,
    "NukeMax_SoftClip": SoftClip,
    "NukeMax_HueCorrect": HueCorrect,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_ColorLookup": "ColorLookup (NukeMax)",
    "NukeMax_SoftClip": "SoftClip (NukeMax)",
    "NukeMax_HueCorrect": "HueCorrect (NukeMax)",
}
