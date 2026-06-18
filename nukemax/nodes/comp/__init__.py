"""Comp — everyday Nuke nodes that were missing, so a basic comp never needs a
round-trip to Nuke: Reformat, Crop, ColorCorrect, Clamp, Saturation, Glow,
Erode/Dilate.

All ops are pure-torch on [B,H,W,C] float 0..1 tensors (no extra deps).
"""
from __future__ import annotations

import math

import torch
import torch.nn.functional as F

from ...utils.resilience import resilient
from ..._tensor_util import require_image_bhwc
from ..._is_changed_util import hash_args_and_kwargs

_LUMA = (0.2126, 0.7152, 0.0722)


def _bchw(img):
    if img.dim() == 3:
        img = img.unsqueeze(0)
    return img[..., :3].permute(0, 3, 1, 2).contiguous()


def _bhwc(x):
    return x.permute(0, 2, 3, 1).contiguous()


def _gauss_kernel(radius: int, device, dtype):
    sigma = max(0.5, radius / 2.0)
    xs = torch.arange(2 * radius + 1, device=device, dtype=dtype) - radius
    g = torch.exp(-(xs ** 2) / (2 * sigma * sigma))
    return g / g.sum()


def _blur(img_bhwc, radius: int):
    if radius < 1:
        return img_bhwc
    x = _bchw(img_bhwc)
    C = x.shape[1]
    k = _gauss_kernel(radius, x.device, x.dtype)
    kh = k.view(1, 1, 1, -1).repeat(C, 1, 1, 1)
    kv = k.view(1, 1, -1, 1).repeat(C, 1, 1, 1)
    x = F.conv2d(F.pad(x, (radius, radius, 0, 0), mode="reflect"), kh, groups=C)
    x = F.conv2d(F.pad(x, (0, 0, radius, radius), mode="reflect"), kv, groups=C)
    return _bhwc(x)


@resilient
class Reformat:
    DESCRIPTION = "Resize an image to a target resolution with a chosen filter; optionally fit/fill while preserving aspect."
    CATEGORY = "NukeMax/Transform"
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
            "width": ("INT", {"default": 1920, "min": 1, "max": 16384}),
            "height": ("INT", {"default": 1080, "min": 1, "max": 16384}),
            "filter": (("bilinear", "bicubic", "nearest", "area"), {"default": "bilinear"}),
            "preserve_aspect": (("none", "fit", "fill"), {"default": "none",
                                "tooltip": "none=stretch; fit=letterbox inside; fill=crop to fill."}),
        }}

    def execute(self, image, width, height, filter, preserve_aspect):
        require_image_bhwc(image)
        x = _bchw(image)
        _, _, h0, w0 = x.shape
        tw, th = int(width), int(height)
        mode = filter
        kw = {} if mode in ("nearest", "area") else {"align_corners": False}
        if preserve_aspect == "none":
            out = F.interpolate(x, size=(th, tw), mode=mode, **kw)
        else:
            s = min(tw / w0, th / h0) if preserve_aspect == "fit" else max(tw / w0, th / h0)
            rw, rh = max(1, round(w0 * s)), max(1, round(h0 * s))
            r = F.interpolate(x, size=(rh, rw), mode=mode, **kw)
            out = torch.zeros(x.shape[0], 3, th, tw, device=x.device, dtype=x.dtype)
            # center fit (pad) or fill (crop)
            oy, ox = (th - rh) // 2, (tw - rw) // 2
            sy, sx = max(0, -oy), max(0, -ox)
            dy, dx = max(0, oy), max(0, ox)
            ch, cw = min(rh - sy, th - dy), min(rw - sx, tw - dx)
            out[:, :, dy:dy + ch, dx:dx + cw] = r[:, :, sy:sy + ch, sx:sx + cw]
        return (_bhwc(out).clamp(0, 1),)


@resilient
class Crop:
    DESCRIPTION = "Crop a rectangular region (x,y,width,height); optionally keep the canvas size (black outside) instead of shrinking."
    CATEGORY = "NukeMax/Transform"
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
            "x": ("INT", {"default": 0, "min": 0, "max": 16384}),
            "y": ("INT", {"default": 0, "min": 0, "max": 16384}),
            "width": ("INT", {"default": 512, "min": 1, "max": 16384}),
            "height": ("INT", {"default": 512, "min": 1, "max": 16384}),
            "keep_canvas": ("BOOLEAN", {"default": False,
                            "tooltip": "Keep original size and black out everything outside the box."}),
        }}

    def execute(self, image, x, y, width, height, keep_canvas):
        require_image_bhwc(image)
        B, H, W, C = image.shape
        x0, y0 = max(0, int(x)), max(0, int(y))
        x1, y1 = min(W, x0 + int(width)), min(H, y0 + int(height))
        if x1 <= x0 or y1 <= y0:
            return (image,)
        if keep_canvas:
            out = torch.zeros_like(image)
            out[:, y0:y1, x0:x1, :] = image[:, y0:y1, x0:x1, :]
            return (out,)
        return (image[:, y0:y1, x0:x1, :].contiguous(),)


@resilient
class ColorCorrect:
    DESCRIPTION = "Nuke-style ColorCorrect: gain (multiply), offset (add), gamma, contrast (around mid-grey) and saturation, applied in that order."
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
            "gain": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01}),
            "offset": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.005}),
            "gamma": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 5.0, "step": 0.01}),
            "contrast": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.01}),
            "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.01}),
        }}

    def execute(self, image, gain, offset, gamma, contrast, saturation):
        require_image_bhwc(image)
        img = image[..., :3]
        out = img * float(gain) + float(offset)
        out = out.clamp(min=1e-6) ** (1.0 / float(gamma)) if gamma != 1.0 else out
        if contrast != 1.0:
            out = (out - 0.5) * float(contrast) + 0.5
        if saturation != 1.0:
            lum = out[..., 0] * _LUMA[0] + out[..., 1] * _LUMA[1] + out[..., 2] * _LUMA[2]
            out = lum.unsqueeze(-1) + (out - lum.unsqueeze(-1)) * float(saturation)
        rest = image[..., 3:]
        out = out.clamp(0, 1)
        if rest.shape[-1]:
            out = torch.cat([out, rest], dim=-1)
        return (out.contiguous(),)


@resilient
class Clamp:
    DESCRIPTION = "Clamp pixel values into a [minimum, maximum] range."
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
            "minimum": ("FLOAT", {"default": 0.0, "min": -10.0, "max": 10.0, "step": 0.01}),
            "maximum": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
        }}

    def execute(self, image, minimum, maximum):
        require_image_bhwc(image)
        lo, hi = float(minimum), float(maximum)
        if hi < lo:
            lo, hi = hi, lo
        return (image.clamp(lo, hi).contiguous(),)


@resilient
class Saturation:
    DESCRIPTION = "Adjust saturation around Rec.709 luminance (0 = greyscale, 1 = unchanged, >1 = more saturated)."
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
            "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.01}),
        }}

    def execute(self, image, saturation):
        require_image_bhwc(image)
        img = image[..., :3]
        lum = img[..., 0] * _LUMA[0] + img[..., 1] * _LUMA[1] + img[..., 2] * _LUMA[2]
        out = (lum.unsqueeze(-1) + (img - lum.unsqueeze(-1)) * float(saturation)).clamp(0, 1)
        rest = image[..., 3:]
        if rest.shape[-1]:
            out = torch.cat([out, rest], dim=-1)
        return (out.contiguous(),)


@resilient
class Glow:
    DESCRIPTION = "Bloom/Glow: isolate pixels above a brightness threshold, blur them, and add the halo back over the image."
    CATEGORY = "NukeMax/Filter"
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
            "threshold": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 1.0, "step": 0.01}),
            "size": ("INT", {"default": 12, "min": 1, "max": 256, "tooltip": "Glow radius in pixels."}),
            "intensity": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 5.0, "step": 0.05}),
        }}

    def execute(self, image, threshold, size, intensity):
        require_image_bhwc(image)
        img = image[..., :3]
        lum = img[..., 0] * _LUMA[0] + img[..., 1] * _LUMA[1] + img[..., 2] * _LUMA[2]
        mask = (lum.unsqueeze(-1) - float(threshold)).clamp(min=0.0) / max(1e-4, 1.0 - float(threshold))
        bright = img * mask
        halo = _blur(bright, int(size)) * float(intensity)
        out = (img + halo).clamp(0, 1)   # additive (screen-like) bloom
        rest = image[..., 3:]
        if rest.shape[-1]:
            out = torch.cat([out, rest], dim=-1)
        return (out.contiguous(),)


@resilient
class ErodeDilate:
    DESCRIPTION = "Morphological erode/dilate. Negative size erodes (shrinks bright/matte regions), positive dilates (grows them)."
    CATEGORY = "NukeMax/Filter"
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
            "size": ("INT", {"default": 0, "min": -64, "max": 64,
                     "tooltip": "Pixels: negative = erode, positive = dilate, 0 = passthrough."}),
        }}

    def execute(self, image, size):
        require_image_bhwc(image)
        n = int(size)
        if n == 0:
            return (image.contiguous(),)
        k = 2 * abs(n) + 1
        x = image.permute(0, 3, 1, 2).contiguous()
        if n > 0:
            x = F.max_pool2d(x, kernel_size=k, stride=1, padding=abs(n))
        else:
            x = -F.max_pool2d(-x, kernel_size=k, stride=1, padding=abs(n))
        return (x.permute(0, 2, 3, 1).clamp(0, 1).contiguous(),)


NODE_CLASS_MAPPINGS = {
    "NukeMax_Reformat": Reformat,
    "NukeMax_Crop": Crop,
    "NukeMax_ColorCorrect": ColorCorrect,
    "NukeMax_Clamp": Clamp,
    "NukeMax_Saturation": Saturation,
    "NukeMax_Glow": Glow,
    "NukeMax_ErodeDilate": ErodeDilate,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_Reformat": "Reformat (NukeMax)",
    "NukeMax_Crop": "Crop (NukeMax)",
    "NukeMax_ColorCorrect": "ColorCorrect (NukeMax)",
    "NukeMax_Clamp": "Clamp (NukeMax)",
    "NukeMax_Saturation": "Saturation (NukeMax)",
    "NukeMax_Glow": "Glow (NukeMax)",
    "NukeMax_ErodeDilate": "Erode/Dilate (NukeMax)",
}