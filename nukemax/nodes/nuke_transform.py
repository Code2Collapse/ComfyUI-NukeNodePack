"""Comp-operator tier — Transform / Filter batch.

The Nuke transform-and-filter operators that had no equivalent in this pack:

  MotionBlur  linear / rotational / zoom blur by accumulated resampling
  Matrix      arbitrary 3x3 or 5x5 convolution kernel
  FrameHold   freeze one frame of a batch

Already registered by earlier batches and deliberately **not** duplicated:
Transform, Mirror, Position, CornerPin, Tile, ContactSheet, AppendClip,
Reformat, Crop, Blur, Sharpen, Median, Defocus, Soften, Bilateral, ZDefocus,
MinMax, EdgeDetect, Emboss, ErodeDilate, Glow, STMap*.

Contract: linear float in, linear float out, arbitrary resolution and channel
count, no clamping and no uint8 round-trip anywhere. Rotation is computed in
pixel space, so a non-square frame rotates as a rigid body instead of shearing.
"""
from __future__ import annotations

import math

import torch
import torch.nn.functional as F

from .._is_changed_util import hash_args_and_kwargs
from ._comp_linear import parse_floats, require_image

_FILTERS = ("bilinear", "nearest", "bicubic")
_EDGES = ("black", "edge", "reflection")
_PAD = {"black": "zeros", "edge": "border", "reflection": "reflection"}


def _sample(x_bchw, theta, filter_name, edges):
    grid = F.affine_grid(theta.to(x_bchw.dtype), list(x_bchw.shape), align_corners=False)
    return F.grid_sample(x_bchw, grid, mode=filter_name,
                         padding_mode=_PAD[edges], align_corners=False)


class MotionBlur:
    DESCRIPTION = ("Motion blur by accumulated resampling: linear (angle + distance in "
                   "pixels), rotational (degrees about a centre) or zoom (scale about a "
                   "centre). Samples are averaged in linear float, so a blurred specular "
                   "keeps its energy instead of being clipped to white.")
    CATEGORY = "NukeMax/Filter"
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
                "type": (("linear", "rotational", "zoom"), {"default": "linear"}),
                "distance": ("FLOAT", {"default": 20.0, "min": -4096.0, "max": 4096.0, "step": 0.5,
                                       "tooltip": "linear: travel in pixels."}),
                "angle": ("FLOAT", {"default": 0.0, "min": -360.0, "max": 360.0, "step": 0.5,
                                    "tooltip": "linear: direction of travel in degrees."}),
                "rotation": ("FLOAT", {"default": 10.0, "min": -360.0, "max": 360.0, "step": 0.1,
                                       "tooltip": "rotational: total sweep in degrees."}),
                "zoom_amount": ("FLOAT", {"default": 0.1, "min": -4.0, "max": 4.0, "step": 0.005,
                                          "tooltip": "zoom: total scale change (0.1 = 10%)."}),
                "samples": ("INT", {"default": 16, "min": 2, "max": 128,
                                    "tooltip": "More samples = smoother trail, linear cost."}),
                "shutter": (("centred", "leading", "trailing"), {"default": "centred"}),
                "center_x": ("FLOAT", {"default": 0.5, "min": -2.0, "max": 3.0, "step": 0.005}),
                "center_y": ("FLOAT", {"default": 0.5, "min": -2.0, "max": 3.0, "step": 0.005}),
                "filter": (_FILTERS, {"default": "bilinear"}),
                "edges": (_EDGES, {"default": "edge"}),
            }
        }

    def execute(self, image, type, distance, angle, rotation, zoom_amount, samples,
                shutter, center_x, center_y, filter, edges):
        require_image(image)
        b, h, w, _ = image.shape
        n = int(samples)

        amount = {"linear": float(distance),
                  "rotational": float(rotation),
                  "zoom": float(zoom_amount)}[type]
        if amount == 0.0:
            return (image.contiguous(),)          # exact identity, no resample

        if shutter == "centred":
            ts = [(i / (n - 1)) - 0.5 for i in range(n)]
        elif shutter == "leading":
            ts = [i / (n - 1) for i in range(n)]
        else:
            ts = [(i / (n - 1)) - 1.0 for i in range(n)]

        cx = 2.0 * float(center_x) - 1.0
        cy = 2.0 * float(center_y) - 1.0
        x = image.permute(0, 3, 1, 2).contiguous()
        acc = torch.zeros_like(x)

        for t in ts:
            if type == "linear":
                d = float(distance) * t
                rad = math.radians(float(angle))
                dx, dy = d * math.cos(rad), -d * math.sin(rad)   # screen y is down
                theta = torch.tensor([[1.0, 0.0, -2.0 * dx / w],
                                      [0.0, 1.0, -2.0 * dy / h]])
            elif type == "rotational":
                rad = math.radians(float(rotation) * t)
                ca, sa = math.cos(rad), math.sin(rad)
                # Rotate in pixel space so non-square frames do not shear.
                ax, ay = ca, sa * h / w
                bx, by = -sa * w / h, ca
                theta = torch.tensor([[ax, ay, cx - ax * cx - ay * cy],
                                      [bx, by, cy - bx * cx - by * cy]])
            else:                                              # zoom
                s = 1.0 + float(zoom_amount) * t
                if abs(s) < 1e-6:
                    continue
                inv = 1.0 / s
                theta = torch.tensor([[inv, 0.0, cx - inv * cx],
                                      [0.0, inv, cy - inv * cy]])
            theta = theta.unsqueeze(0).repeat(b, 1, 1)
            acc = acc + _sample(x, theta, filter, edges)

        out = acc / float(len(ts))
        return (out.permute(0, 2, 3, 1).contiguous(),)


class Matrix:
    DESCRIPTION = ("Nuke Matrix: convolve every channel with an arbitrary 3x3 or 5x5 "
                   "kernel you type in. Sharpen, soften, edge-detect, custom relief — "
                   "all from one node. Linear float, so kernels with negative lobes keep "
                   "their negative results instead of being crushed to zero.")
    CATEGORY = "NukeMax/Filter"
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
                "size": (("3x3", "5x5"), {"default": "3x3"}),
                "kernel": ("STRING", {
                    "default": "0 0 0  0 1 0  0 0 0",
                    "multiline": True,
                    "tooltip": "Row-major numbers, whitespace or comma separated. "
                               "9 values for 3x3, 25 for 5x5."}),
                "normalize": ("BOOLEAN", {"default": False,
                              "tooltip": "Divide by the kernel sum so overall brightness is "
                                         "preserved. Ignored when the sum is 0 (edge kernels)."}),
                "include_alpha": ("BOOLEAN", {"default": False,
                                  "tooltip": "Filter the alpha channel too. Off keeps the matte crisp."}),
                "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            }
        }

    def execute(self, image, size, kernel, normalize, include_alpha, mix):
        require_image(image)
        k = 3 if size == "3x3" else 5
        vals = parse_floats(kernel, "kernel", expect=k * k)
        kt = torch.tensor(vals, device=image.device, dtype=image.dtype).view(1, 1, k, k)
        if normalize:
            s = float(kt.sum())
            if abs(s) > 1e-9:
                kt = kt / s

        n_filter = image.shape[-1] if include_alpha else min(3, image.shape[-1])
        src = image[..., :n_filter]
        x = src.permute(0, 3, 1, 2)
        c = x.shape[1]
        r = k // 2
        y = F.conv2d(F.pad(x, (r, r, r, r), mode="reflect"), kt.repeat(c, 1, 1, 1), groups=c)
        out = y.permute(0, 2, 3, 1)

        f = float(mix)
        if f < 1.0:
            out = src + (out - src) * f
        if n_filter < image.shape[-1]:
            out = torch.cat([out, image[..., n_filter:]], dim=-1)
        return (out.contiguous(),)


class FrameHold:
    DESCRIPTION = ("Nuke FrameHold: freeze one frame of an image batch and repeat it. "
                   "Use it to hold a clean plate, a matte painting or a reference frame "
                   "against a moving sequence.")
    CATEGORY = "NukeMax/Time"
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
                "frame": ("INT", {"default": 0, "min": -4096, "max": 4096,
                                  "tooltip": "0-based index into the batch. Negative counts "
                                             "back from the end, like Python."}),
                "length": ("INT", {"default": 0, "min": 0, "max": 8192,
                                   "tooltip": "How many frames to output. 0 = match the input batch."}),
            }
        }

    def execute(self, image, frame, length):
        require_image(image)
        b = image.shape[0]
        idx = int(frame)
        if idx < 0:
            idx += b
        if not 0 <= idx < b:
            raise ValueError(
                f"'frame' {frame} is outside the input batch of {b} frame(s) "
                f"(valid: 0..{b - 1}, or -1..-{b} counting back). "
                f"Check the frame count feeding this node."
            )
        n = int(length) or b
        return (image[idx:idx + 1].expand(n, *image.shape[1:]).contiguous(),)


NODE_CLASS_MAPPINGS = {
    "NukeMax_MotionBlur": MotionBlur,
    "NukeMax_Matrix": Matrix,
    "NukeMax_FrameHold": FrameHold,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_MotionBlur": "MotionBlur (NukeMax)",
    "NukeMax_Matrix": "Matrix (NukeMax)",
    "NukeMax_FrameHold": "FrameHold (NukeMax)",
}
