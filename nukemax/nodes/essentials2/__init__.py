"""Essentials 2 — more core Nuke daily-drivers (batch 2):

  Color:    Add, HueShift, Log2Lin, Posterize, ClipTest
  Keying:   Keyer (luma/channel range), Difference (vs clean plate), Despill
  Filter:   Defocus (disc bokeh), Soften
  Transform:CornerPin (4-corner perspective), Tile, Switch
  Generate: Noise, Radial, Rectangle

Pure-torch on [B,H,W,C] float 0..1 (cv2 used only for CornerPin, guarded),
matching the existing NukeMax node style (resilient, alpha-preserving, hashed).
"""
from __future__ import annotations

import math

import torch
import torch.nn.functional as F

from ...utils.resilience import resilient
from ..._tensor_util import require_image_bhwc
from ..._is_changed_util import hash_args_and_kwargs

try:
    import cv2
    import numpy as np
    _HAVE_CV2 = True
except Exception:  # noqa: BLE001
    _HAVE_CV2 = False

_LUMA = (0.2126, 0.7152, 0.0722)


def _split(image):
    rgb = image[..., :3]
    alpha = image[..., 3:4] if image.shape[-1] >= 4 else None
    return rgb, alpha


def _join(rgb, alpha):
    return torch.cat([rgb, alpha], dim=-1).contiguous() if alpha is not None else rgb.contiguous()


def _luma(rgb):
    return rgb[..., 0] * _LUMA[0] + rgb[..., 1] * _LUMA[1] + rgb[..., 2] * _LUMA[2]


def _hex(s, default=(0.0, 0.0, 0.0)):
    s = str(s).strip()
    try:
        if s.startswith("#"):
            s = s[1:]
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        return (int(s[0:2], 16) / 255.0, int(s[2:4], 16) / 255.0, int(s[4:6], 16) / 255.0)
    except Exception:  # noqa: BLE001
        return default


def _gauss(img_bhwc, radius):
    if radius < 1:
        return img_bhwc
    x = img_bhwc.permute(0, 3, 1, 2)
    Cc = x.shape[1]
    sigma = max(0.5, radius / 2.0)
    xs = torch.arange(2 * radius + 1, device=x.device, dtype=x.dtype) - radius
    k = torch.exp(-(xs ** 2) / (2 * sigma * sigma)); k = k / k.sum()
    kh = k.view(1, 1, 1, -1).repeat(Cc, 1, 1, 1)
    kv = k.view(1, 1, -1, 1).repeat(Cc, 1, 1, 1)
    x = F.conv2d(F.pad(x, (radius, radius, 0, 0), mode="reflect"), kh, groups=Cc)
    x = F.conv2d(F.pad(x, (0, 0, radius, radius), mode="reflect"), kv, groups=Cc)
    return x.permute(0, 2, 3, 1)


def _rgb_to_hsv(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, _ = rgb.max(-1); mn, _ = rgb.min(-1)
    df = (mx - mn).clamp(min=1e-6)
    h = torch.zeros_like(mx)
    mask = mx == r
    h = torch.where(mask, ((g - b) / df) % 6, h)
    mask = mx == g
    h = torch.where(mask, ((b - r) / df) + 2, h)
    mask = mx == b
    h = torch.where(mask, ((r - g) / df) + 4, h)
    h = (h / 6.0) % 1.0
    s = torch.where(mx > 0, (mx - mn) / mx.clamp(min=1e-6), torch.zeros_like(mx))
    return torch.stack([h, s, mx], dim=-1)


def _hsv_to_rgb(hsv):
    h, s, v = hsv[..., 0] * 6.0, hsv[..., 1], hsv[..., 2]
    i = torch.floor(h)
    f = h - i
    p = v * (1 - s); q = v * (1 - s * f); t = v * (1 - s * (1 - f))
    i = (i % 6).long()
    r = torch.zeros_like(v); g = torch.zeros_like(v); b = torch.zeros_like(v)
    for idx, (rr, gg, bb) in enumerate([(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]):
        m = i == idx
        r = torch.where(m, rr, r); g = torch.where(m, gg, g); b = torch.where(m, bb, b)
    return torch.stack([r, g, b], dim=-1)


# ───────────────────────── Color ─────────────────────────
@resilient
class Add:
    DESCRIPTION = "Add a constant to RGB (per-channel optional). Lift."
    CATEGORY = "NukeMax/Color"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        f = lambda: ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.005})
        return {"required": {"image": ("IMAGE", {}), "value": f(), "red": f(), "green": f(), "blue": f()}}
    def execute(self, image, value, red, green, blue):
        require_image_bhwc(image)
        rgb, a = _split(image)
        add = torch.tensor([red + value, green + value, blue + value], device=rgb.device, dtype=rgb.dtype)
        return (_join((rgb + add).clamp(0, 1), a),)


@resilient
class HueShift:
    DESCRIPTION = "Rotate hue (degrees) and scale saturation/value (HSV)."
    CATEGORY = "NukeMax/Color"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}),
                "hue_degrees": ("FLOAT", {"default": 0.0, "min": -180.0, "max": 180.0, "step": 1.0}),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.01}),
                "value": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.01})}}
    def execute(self, image, hue_degrees, saturation, value):
        require_image_bhwc(image)
        rgb, a = _split(image)
        hsv = _rgb_to_hsv(rgb.clamp(0, 1))
        hsv[..., 0] = (hsv[..., 0] + float(hue_degrees) / 360.0) % 1.0
        hsv[..., 1] = (hsv[..., 1] * float(saturation)).clamp(0, 1)
        hsv[..., 2] = (hsv[..., 2] * float(value)).clamp(0, 1)
        return (_join(_hsv_to_rgb(hsv).clamp(0, 1), a),)


@resilient
class Log2Lin:
    DESCRIPTION = "Convert between log and linear (Cineon-style) colour space."
    CATEGORY = "NukeMax/Color"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}),
                "operation": (("log2lin", "lin2log"), {"default": "log2lin"}),
                "black": ("INT", {"default": 95, "min": 0, "max": 1023}),
                "white": ("INT", {"default": 685, "min": 0, "max": 1023}),
                "gamma": ("FLOAT", {"default": 0.6, "min": 0.01, "max": 2.0, "step": 0.01})}}
    def execute(self, image, operation, black, white, gamma):
        require_image_bhwc(image)
        rgb, a = _split(image)
        bk, wt, g = float(black) / 1023.0, float(white) / 1023.0, float(gamma)
        if operation == "log2lin":
            # map the log black/white points to 0..1, then apply the lin gamma
            out = (((rgb - bk) / max(1e-6, wt - bk)).clamp(min=0.0)) ** (1.0 / g)
        else:
            # inverse: lin gamma back to the log black/white range
            out = (rgb.clamp(min=1e-6) ** g) * (wt - bk) + bk
        return (_join(out.clamp(0, 1), a),)


@resilient
class Posterize:
    DESCRIPTION = "Quantise each channel to N levels (banding / cel-shade)."
    CATEGORY = "NukeMax/Color"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}), "levels": ("INT", {"default": 8, "min": 2, "max": 256})}}
    def execute(self, image, levels):
        require_image_bhwc(image)
        rgb, a = _split(image); n = max(2, int(levels))
        out = (torch.round(rgb * (n - 1)) / (n - 1)).clamp(0, 1)
        return (_join(out, a),)


@resilient
class ClipTest:
    DESCRIPTION = "Diagnostic: tint pixels below 'low' blue and above 'high' red (zebra over/under check)."
    CATEGORY = "NukeMax/Color"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}),
                "low": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.005}),
                "high": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.005})}}
    def execute(self, image, low, high):
        require_image_bhwc(image)
        rgb, a = _split(image); lum = _luma(rgb).unsqueeze(-1)
        out = rgb.clone()
        under = (lum <= float(low)).expand_as(out)
        over = (lum >= float(high)).expand_as(out)
        blue = torch.tensor([0.0, 0.0, 1.0], device=rgb.device); red = torch.tensor([1.0, 0.0, 0.0], device=rgb.device)
        out = torch.where(under, blue, out); out = torch.where(over, red, out)
        return (_join(out, a),)


# ───────────────────────── Keying ─────────────────────────
@resilient
class Keyer:
    DESCRIPTION = "Luminance/channel keyer: build a matte from a value range with soft edges. Outputs the matte as RGB + alpha."
    CATEGORY = "NukeMax/Keying"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK"); RETURN_NAMES = ("image", "matte")
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}),
                "channel": (("luminance", "red", "green", "blue"), {"default": "luminance"}),
                "range_low": ("FLOAT", {"default": 0.2, "min": 0.0, "max": 1.0, "step": 0.005}),
                "range_high": ("FLOAT", {"default": 0.8, "min": 0.0, "max": 1.0, "step": 0.005}),
                "softness": ("FLOAT", {"default": 0.1, "min": 0.0, "max": 0.5, "step": 0.005})}}
    def execute(self, image, channel, range_low, range_high, softness):
        require_image_bhwc(image)
        rgb, _ = _split(image)
        src = {"red": rgb[..., 0], "green": rgb[..., 1], "blue": rgb[..., 2]}.get(channel, _luma(rgb))
        lo, hi, sf = float(range_low), float(range_high), max(1e-4, float(softness))
        up = ((src - (lo - sf)) / sf).clamp(0, 1)
        dn = (((hi + sf) - src) / sf).clamp(0, 1)
        matte = (up * dn).clamp(0, 1)
        img = matte.unsqueeze(-1).repeat(1, 1, 1, 3)
        return (img.contiguous(), matte.contiguous())


@resilient
class Difference:
    DESCRIPTION = "Difference keyer: matte = where image differs from a clean plate (|img-plate|), with gain + threshold."
    CATEGORY = "NukeMax/Keying"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK"); RETURN_NAMES = ("image", "matte")
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}), "clean_plate": ("IMAGE", {}),
                "gain": ("FLOAT", {"default": 4.0, "min": 0.1, "max": 32.0, "step": 0.1}),
                "threshold": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 1.0, "step": 0.005})}}
    def execute(self, image, clean_plate, gain, threshold):
        require_image_bhwc(image); require_image_bhwc(clean_plate)
        a = image[..., :3]; b = clean_plate[..., :3]
        if b.shape[1:3] != a.shape[1:3]:
            b = F.interpolate(b.permute(0, 3, 1, 2), size=a.shape[1:3], mode="bilinear", align_corners=False).permute(0, 2, 3, 1)
        diff = (a - b).abs().amax(-1)
        matte = ((diff - float(threshold)) * float(gain)).clamp(0, 1)
        img = matte.unsqueeze(-1).repeat(1, 1, 1, 3)
        return (img.contiguous(), matte.contiguous())


@resilient
class Despill:
    DESCRIPTION = "Suppress green/blue screen spill: clamp the screen channel toward the average of the other two."
    CATEGORY = "NukeMax/Keying"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}),
                "screen": (("green", "blue"), {"default": "green"}),
                "amount": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01})}}
    def execute(self, image, screen, amount):
        require_image_bhwc(image)
        rgb, a = _split(image); out = rgb.clone()
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        amt = float(amount)
        if screen == "green":
            limit = torch.maximum(r, b)
            out[..., 1] = torch.where(g > limit, g + (limit - g) * amt, g)
        else:
            limit = torch.maximum(r, g)
            out[..., 2] = torch.where(b > limit, b + (limit - b) * amt, b)
        return (_join(out.clamp(0, 1), a),)


# ───────────────────────── Filter ─────────────────────────
@resilient
class Defocus:
    DESCRIPTION = "Disc-bokeh defocus blur (circular kernel) — softer, rounder out-of-focus than gaussian."
    CATEGORY = "NukeMax/Filter"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}), "size": ("INT", {"default": 8, "min": 1, "max": 128})}}
    def execute(self, image, size):
        require_image_bhwc(image)
        rgb, a = _split(image); r = int(size)
        x = rgb.permute(0, 3, 1, 2); C = x.shape[1]
        ys, xs = torch.meshgrid(torch.arange(-r, r + 1), torch.arange(-r, r + 1), indexing="ij")
        disc = ((xs.float() ** 2 + ys.float() ** 2) <= (r * r)).float()
        disc = (disc / disc.sum()).to(x.dtype)
        k = disc.view(1, 1, 2 * r + 1, 2 * r + 1).repeat(C, 1, 1, 1)
        x = F.conv2d(F.pad(x, (r, r, r, r), mode="reflect"), k, groups=C)
        return (_join(x.permute(0, 2, 3, 1).clamp(0, 1), a),)


@resilient
class Soften:
    DESCRIPTION = "Gentle gaussian soften (mix of blurred + original)."
    CATEGORY = "NukeMax/Filter"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}), "size": ("INT", {"default": 3, "min": 1, "max": 64}),
                "amount": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01})}}
    def execute(self, image, size, amount):
        require_image_bhwc(image)
        rgb, a = _split(image)
        out = rgb * (1 - float(amount)) + _gauss(rgb, int(size)) * float(amount)
        return (_join(out.clamp(0, 1), a),)


# ───────────────────────── Transform ─────────────────────────
@resilient
class CornerPin:
    DESCRIPTION = "4-corner perspective pin: map the image corners to (x,y) destinations (normalised 0..1). Needs OpenCV."
    CATEGORY = "NukeMax/Transform"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        p = lambda d: ("FLOAT", {"default": d, "min": -2.0, "max": 3.0, "step": 0.005})
        return {"required": {"image": ("IMAGE", {}),
                "to1_x": p(0.0), "to1_y": p(0.0), "to2_x": p(1.0), "to2_y": p(0.0),
                "to3_x": p(1.0), "to3_y": p(1.0), "to4_x": p(0.0), "to4_y": p(1.0)}}
    def execute(self, image, to1_x, to1_y, to2_x, to2_y, to3_x, to3_y, to4_x, to4_y):
        require_image_bhwc(image)
        if not _HAVE_CV2:
            return (image,)
        B, H, W, C = image.shape
        src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
        dst = np.float32([[to1_x * W, to1_y * H], [to2_x * W, to2_y * H],
                          [to3_x * W, to3_y * H], [to4_x * W, to4_y * H]])
        M = cv2.getPerspectiveTransform(src, dst)
        out = []
        for i in range(B):
            arr = (image[i].cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            w = cv2.warpPerspective(arr, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=0)
            out.append(torch.from_numpy(w.astype(np.float32) / 255.0))
        return (torch.stack(out, 0).to(image.device),)


@resilient
class Tile:
    DESCRIPTION = "Tile / repeat the image in a grid (columns x rows)."
    CATEGORY = "NukeMax/Transform"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}),
                "columns": ("INT", {"default": 2, "min": 1, "max": 16}),
                "rows": ("INT", {"default": 2, "min": 1, "max": 16})}}
    def execute(self, image, columns, rows):
        require_image_bhwc(image)
        return (image.repeat(1, int(rows), int(columns), 1).contiguous(),)


@resilient
class Switch:
    DESCRIPTION = "Pass through input A or B selected by 'which' (0 = A, 1 = B)."
    CATEGORY = "NukeMax/Merge"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"A": ("IMAGE", {}), "B": ("IMAGE", {}), "which": ("INT", {"default": 0, "min": 0, "max": 1})}}
    def execute(self, A, B, which):
        return (B if int(which) == 1 else A,)


# ───────────────────────── Generate ─────────────────────────
@resilient
class Noise:
    DESCRIPTION = "Generate uniform/fractal noise (greyscale or RGB), seeded."
    CATEGORY = "NukeMax/Generate"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"width": ("INT", {"default": 1024, "min": 1, "max": 16384}),
                "height": ("INT", {"default": 1024, "min": 1, "max": 16384}),
                "type": (("greyscale", "rgb"), {"default": "greyscale"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2 ** 31 - 1})}}
    def execute(self, width, height, type, seed):
        g = torch.Generator().manual_seed(int(seed))
        W, H = int(width), int(height)
        if type == "rgb":
            out = torch.rand(1, H, W, 3, generator=g)
        else:
            n = torch.rand(1, H, W, 1, generator=g)
            out = n.repeat(1, 1, 1, 3)
        return (out,)


@resilient
class Radial:
    DESCRIPTION = "Generate a radial gradient (centre -> edge) — soft vignette / falloff source."
    CATEGORY = "NukeMax/Generate"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"width": ("INT", {"default": 1024, "min": 8, "max": 16384}),
                "height": ("INT", {"default": 1024, "min": 8, "max": 16384}),
                "radius": ("FLOAT", {"default": 0.5, "min": 0.01, "max": 2.0, "step": 0.01}),
                "invert": ("BOOLEAN", {"default": False})}}
    def execute(self, width, height, radius, invert):
        W, H = int(width), int(height)
        ys = torch.linspace(-1, 1, H).view(H, 1)
        xs = torch.linspace(-1, 1, W).view(1, W)
        d = torch.sqrt(xs ** 2 + ys ** 2) / max(1e-4, float(radius))
        g = (1.0 - d).clamp(0, 1)
        if invert:
            g = 1.0 - g
        return (g.view(1, H, W, 1).repeat(1, 1, 1, 3),)


@resilient
class Rectangle:
    DESCRIPTION = "Generate a filled rectangle on black (normalised x,y,w,h) — a quick garbage-matte / mask source."
    CATEGORY = "NukeMax/Generate"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK"); RETURN_NAMES = ("image", "mask")
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        p = lambda d: ("FLOAT", {"default": d, "min": 0.0, "max": 1.0, "step": 0.005})
        return {"required": {"width": ("INT", {"default": 1024, "min": 8, "max": 16384}),
                "height": ("INT", {"default": 1024, "min": 8, "max": 16384}),
                "x": p(0.25), "y": p(0.25), "w": p(0.5), "h": p(0.5)}}
    def execute(self, width, height, x, y, w, h):
        W, H = int(width), int(height)
        m = torch.zeros(1, H, W)
        x0, y0 = int(x * W), int(y * H)
        x1, y1 = min(W, int((x + w) * W)), min(H, int((y + h) * H))
        if x1 > x0 and y1 > y0:
            m[:, y0:y1, x0:x1] = 1.0
        img = m.unsqueeze(-1).repeat(1, 1, 1, 3)
        return (img, m)


NODE_CLASS_MAPPINGS = {
    "NukeMax_Add": Add, "NukeMax_HueShift": HueShift, "NukeMax_Log2Lin": Log2Lin,
    "NukeMax_Posterize": Posterize, "NukeMax_ClipTest": ClipTest,
    "NukeMax_Keyer": Keyer, "NukeMax_Difference": Difference, "NukeMax_Despill": Despill,
    "NukeMax_Defocus": Defocus, "NukeMax_Soften": Soften,
    "NukeMax_CornerPin": CornerPin, "NukeMax_Tile": Tile, "NukeMax_Switch": Switch,
    "NukeMax_Noise": Noise, "NukeMax_Radial": Radial, "NukeMax_Rectangle": Rectangle,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_Add": "Add (NukeMax)", "NukeMax_HueShift": "HueShift (NukeMax)",
    "NukeMax_Log2Lin": "Log2Lin (NukeMax)", "NukeMax_Posterize": "Posterize (NukeMax)",
    "NukeMax_ClipTest": "ClipTest (NukeMax)", "NukeMax_Keyer": "Keyer (NukeMax)",
    "NukeMax_Difference": "Difference (NukeMax)", "NukeMax_Despill": "Despill (NukeMax)",
    "NukeMax_Defocus": "Defocus (NukeMax)", "NukeMax_Soften": "Soften (NukeMax)",
    "NukeMax_CornerPin": "CornerPin (NukeMax)", "NukeMax_Tile": "Tile (NukeMax)",
    "NukeMax_Switch": "Switch (NukeMax)", "NukeMax_Noise": "Noise (NukeMax)",
    "NukeMax_Radial": "Radial (NukeMax)", "NukeMax_Rectangle": "Rectangle (NukeMax)",
}
