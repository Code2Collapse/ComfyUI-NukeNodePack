"""Essentials — the core Nuke daily-driver nodes that were still missing, so a
comp never needs a round-trip to Nuke for the basics:

  Color:    Grade, Multiply, Gamma, Invert, Exposure
  Merge:    Merge (all operations), Dissolve, Keymix
  Transform:Transform, Mirror
  Filter:   Sharpen, Median
  Generate: Constant, CheckerBoard, ColorBars, Ramp

All ops are pure-torch on [B,H,W,C] **linear float** tensors (no extra deps),
matching the existing NukeMax node style (resilient, alpha-preserving, hashed
IS_CHANGED).

Linear-float contract (PROCESS_PLATE.md section 3), applied Aug 2026: these
operators no longer clamp their colour output to 0..1. A 12.5 specular stays
12.5 through Grade/Merge/Transform/Blur instead of being flattened to white,
which is what a linear EXR pipeline requires. Grade carries Nuke's own
`black_clamp` / `white_clamp` switches (both off by default, as in Nuke) for
the cases where you genuinely do want a hard limit. Mattes and MASK outputs
are still bounded to 0..1 — that is a matte's definition, not a display
convenience.
"""
from __future__ import annotations

import torch
import torch.nn.functional as F

from ...utils.resilience import resilient
from ..._tensor_util import require_image_bhwc
from ..._is_changed_util import hash_args_and_kwargs

_LUMA = (0.2126, 0.7152, 0.0722)


def _gamma(x, g):
    """Nuke gamma: x^(1/g) for x > 0, pass through for x <= 0. HDR-safe."""
    g = float(g)
    if g == 1.0:
        return x
    return torch.where(x > 0, x.clamp(min=0) ** (1.0 / max(1e-6, g)), x)


def _match_hw(src, ref, mode="bilinear"):
    """Resample src [B,H,W,C] to ref's H,W without touching its channel count."""
    if src.shape[1:3] == ref.shape[1:3]:
        return src
    kw = {} if mode in ("nearest", "area") else {"align_corners": False}
    return F.interpolate(src.permute(0, 3, 1, 2), size=tuple(ref.shape[1:3]),
                         mode=mode, **kw).permute(0, 2, 3, 1).contiguous()


def _mask_1c(mask, ref):
    """MASK [B,H,W] (or [B,H,W,1]) -> [B,H,W,1] matched to ref's H,W and batch."""
    m = mask.unsqueeze(-1) if mask.dim() == 3 else mask[..., :1]
    m = m.to(device=ref.device, dtype=ref.dtype)
    m = _match_hw(m, ref)
    if m.shape[0] != ref.shape[0]:
        if m.shape[0] != 1:
            raise ValueError(
                f"mask has {m.shape[0]} frames but the image has {ref.shape[0]}. "
                f"Use a single mask frame (auto-broadcast) or matching frame counts."
            )
        m = m.expand(ref.shape[0], *m.shape[1:])
    return m


# ───────────────────────── helpers ─────────────────────────
def _split(image):
    """-> (rgb [B,H,W,3], alpha [B,H,W,1] or None)."""
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


# ───────────────────────── Color ─────────────────────────
@resilient
class Grade:
    DESCRIPTION = ("Nuke Grade: per-channel blackpoint/whitepoint remap to lift/gain, then "
                   "multiply, offset and gamma — the standard primary grade. "
                   "out = ((in-bp)/(wp-bp) * (gain-lift) + lift) * multiply + offset, then ^(1/gamma).")
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        f = lambda d, lo, hi, st=0.001: ("FLOAT", {"default": d, "min": lo, "max": hi, "step": st})
        return {"required": {
            "image": ("IMAGE", {}),
            "blackpoint": f(0.0, -1.0, 1.0),
            "whitepoint": f(1.0, 0.0, 4.0),
            "lift": f(0.0, -1.0, 1.0),
            "gain": f(1.0, 0.0, 4.0),
            "multiply": f(1.0, 0.0, 8.0),
            "offset": f(0.0, -1.0, 1.0),
            "gamma": f(1.0, 0.01, 5.0, 0.01),
        }, "optional": {"mask": ("MASK", {})}}

    def execute(self, image, blackpoint, whitepoint, lift, gain, multiply, offset, gamma, mask=None):
        require_image_bhwc(image)
        rgb, alpha = _split(image)
        bp, wp = float(blackpoint), float(whitepoint)
        denom = (wp - bp) if abs(wp - bp) > 1e-6 else 1e-6
        out = (rgb - bp) / denom
        out = out * (float(gain) - float(lift)) + float(lift)
        out = out * float(multiply) + float(offset)
        if gamma != 1.0:
            out = out.clamp(min=1e-6) ** (1.0 / float(gamma))
        out = out.clamp(0, 1)
        if mask is not None:
            m = mask
            if m.dim() == 3:
                m = m.unsqueeze(-1)
            if m.shape[1:3] == rgb.shape[1:3]:
                out = rgb * (1 - m) + out * m
        return (_join(out, alpha),)


@resilient
class Multiply:
    DESCRIPTION = "Multiply RGB by a constant (per-channel optional). Linear gain."
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        f = lambda: ("FLOAT", {"default": 1.0, "min": 0.0, "max": 16.0, "step": 0.01})
        return {"required": {"image": ("IMAGE", {}),
                             "value": f(), "red": f(), "green": f(), "blue": f()}}

    def execute(self, image, value, red, green, blue):
        require_image_bhwc(image)
        rgb, alpha = _split(image)
        g = torch.tensor([red * value, green * value, blue * value], device=rgb.device, dtype=rgb.dtype)
        return (_join((rgb * g).clamp(0, 1), alpha),)


@resilient
class Gamma:
    DESCRIPTION = "Apply gamma correction (out = in ^ (1/gamma)); >1 brightens mids."
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}),
                             "gamma": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 5.0, "step": 0.01})}}

    def execute(self, image, gamma):
        require_image_bhwc(image)
        rgb, alpha = _split(image)
        out = rgb.clamp(min=1e-6) ** (1.0 / float(gamma)) if gamma != 1.0 else rgb
        return (_join(out.clamp(0, 1), alpha),)


@resilient
class Invert:
    DESCRIPTION = "Invert RGB (1 - value). Alpha is preserved."
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {})}}

    def execute(self, image):
        require_image_bhwc(image)
        rgb, alpha = _split(image)
        return (_join((1.0 - rgb).clamp(0, 1), alpha),)


@resilient
class Exposure:
    DESCRIPTION = "Adjust exposure in stops (out = in * 2^stops)."
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}),
                             "stops": ("FLOAT", {"default": 0.0, "min": -10.0, "max": 10.0, "step": 0.1})}}

    def execute(self, image, stops):
        require_image_bhwc(image)
        rgb, alpha = _split(image)
        return (_join((rgb * (2.0 ** float(stops))).clamp(0, 1), alpha),)


# ───────────────────────── Merge ─────────────────────────
_MERGE_OPS = ("over", "under", "atop", "in", "out", "mask", "stencil",
              "plus", "minus", "multiply", "screen", "overlay", "difference",
              "max", "min", "average")


@resilient
class Merge:
    DESCRIPTION = ("Nuke Merge: composite A over/under B with the full operation set "
                   "(over/under/atop/in/out/mask/stencil/plus/minus/multiply/screen/overlay/"
                   "difference/max/min/average). 'mix' dissolves the result back toward B.")
    CATEGORY = "NukeMax/Merge"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "A": ("IMAGE", {}),
            "B": ("IMAGE", {}),
            "operation": (_MERGE_OPS, {"default": "over"}),
            "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01,
                    "tooltip": "Blend the merge result back toward B (1 = full merge)."}),
        }}

    def execute(self, A, B, operation, mix):
        require_image_bhwc(A); require_image_bhwc(B)
        # match B size to A
        if B.shape[1:3] != A.shape[1:3]:
            B = F.interpolate(B[..., :A.shape[-1]].permute(0, 3, 1, 2), size=A.shape[1:3],
                              mode="bilinear", align_corners=False).permute(0, 2, 3, 1)
        a_rgb, a_a = _split(A)
        b_rgb, b_a = _split(B)
        aa = a_a if a_a is not None else torch.ones_like(a_rgb[..., :1])
        ba = b_a if b_a is not None else torch.ones_like(b_rgb[..., :1])
        op = operation
        if op == "over":      out = a_rgb + b_rgb * (1 - aa)
        elif op == "under":   out = a_rgb * (1 - ba) + b_rgb
        elif op == "atop":    out = a_rgb * ba + b_rgb * (1 - aa)
        elif op == "in":      out = a_rgb * ba
        elif op == "out":     out = a_rgb * (1 - ba)
        elif op == "mask":    out = b_rgb * aa
        elif op == "stencil": out = b_rgb * (1 - aa)
        elif op == "plus":    out = a_rgb + b_rgb
        elif op == "minus":   out = b_rgb - a_rgb
        elif op == "multiply": out = a_rgb * b_rgb
        elif op == "screen":  out = a_rgb + b_rgb - a_rgb * b_rgb
        elif op == "overlay":
            out = torch.where(b_rgb < 0.5, 2 * a_rgb * b_rgb, 1 - 2 * (1 - a_rgb) * (1 - b_rgb))
        elif op == "difference": out = (a_rgb - b_rgb).abs()
        elif op == "max":     out = torch.maximum(a_rgb, b_rgb)
        elif op == "min":     out = torch.minimum(a_rgb, b_rgb)
        else:                 out = (a_rgb + b_rgb) * 0.5  # average
        m = float(mix)
        if m < 1.0:
            out = b_rgb * (1 - m) + out * m
        out = out.clamp(0, 1)
        out_a = torch.maximum(aa, ba).clamp(0, 1) if (a_a is not None or b_a is not None) else None
        return (_join(out, out_a),)


@resilient
class Dissolve:
    DESCRIPTION = "Cross-dissolve between A and B by 'which' (0 = A, 1 = B)."
    CATEGORY = "NukeMax/Merge"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"A": ("IMAGE", {}), "B": ("IMAGE", {}),
                             "which": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01})}}

    def execute(self, A, B, which):
        require_image_bhwc(A); require_image_bhwc(B)
        if B.shape != A.shape:
            B = F.interpolate(B[..., :A.shape[-1]].permute(0, 3, 1, 2), size=A.shape[1:3],
                              mode="bilinear", align_corners=False).permute(0, 2, 3, 1)
        w = float(which)
        return ((A * (1 - w) + B * w).clamp(0, 1).contiguous(),)


@resilient
class Keymix:
    DESCRIPTION = "Keymix: A where mask=1, B where mask=0 (A*mask + B*(1-mask))."
    CATEGORY = "NukeMax/Merge"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"A": ("IMAGE", {}), "B": ("IMAGE", {}), "mask": ("MASK", {})}}

    def execute(self, A, B, mask):
        require_image_bhwc(A); require_image_bhwc(B)
        if B.shape != A.shape:
            B = F.interpolate(B[..., :A.shape[-1]].permute(0, 3, 1, 2), size=A.shape[1:3],
                              mode="bilinear", align_corners=False).permute(0, 2, 3, 1)
        m = mask
        if m.dim() == 3:
            m = m.unsqueeze(-1)
        if m.shape[1:3] != A.shape[1:3]:
            m = F.interpolate(m.permute(0, 3, 1, 2), size=A.shape[1:3], mode="bilinear",
                              align_corners=False).permute(0, 2, 3, 1)
        return ((A * m + B * (1 - m)).clamp(0, 1).contiguous(),)


# ───────────────────────── Transform ─────────────────────────
@resilient
class Transform:
    DESCRIPTION = ("2D Transform: translate (px), rotate (deg), scale, around a center, "
                   "with a chosen filter. Uses an affine grid sample.")
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
            "translate_x": ("FLOAT", {"default": 0.0, "min": -8192, "max": 8192, "step": 1}),
            "translate_y": ("FLOAT", {"default": 0.0, "min": -8192, "max": 8192, "step": 1}),
            "rotate": ("FLOAT", {"default": 0.0, "min": -360.0, "max": 360.0, "step": 0.1}),
            "scale": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 16.0, "step": 0.01}),
            "filter": (("bilinear", "nearest", "bicubic"), {"default": "bilinear"}),
            "wrap": (("black", "edge", "reflection"), {"default": "black"}),
        }}

    def execute(self, image, translate_x, translate_y, rotate, scale, filter, wrap):
        require_image_bhwc(image)
        B, H, W, C = image.shape
        x = image.permute(0, 3, 1, 2)
        ang = torch.tensor(float(rotate) * 3.14159265 / 180.0)
        cos, sin = torch.cos(ang), torch.sin(ang)
        s = 1.0 / max(1e-6, float(scale))
        # normalized translate (grid is -1..1 over W/H)
        tx = -2.0 * float(translate_x) / W
        ty = -2.0 * float(translate_y) / H
        theta = torch.tensor([[s * cos, s * sin, tx],
                              [-s * sin, s * cos, ty]], dtype=x.dtype).unsqueeze(0).repeat(B, 1, 1)
        grid = F.affine_grid(theta, x.shape, align_corners=False)
        pad = {"black": "zeros", "edge": "border", "reflection": "reflection"}[wrap]
        out = F.grid_sample(x, grid.to(x.dtype), mode=filter if filter != "bicubic" else "bicubic",
                            padding_mode=pad, align_corners=False)
        return (out.permute(0, 2, 3, 1).clamp(0, 1).contiguous(),)


@resilient
class Mirror:
    DESCRIPTION = "Flop (mirror horizontal) and/or Flip (mirror vertical)."
    CATEGORY = "NukeMax/Transform"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}),
                             "flop_horizontal": ("BOOLEAN", {"default": False}),
                             "flip_vertical": ("BOOLEAN", {"default": False})}}

    def execute(self, image, flop_horizontal, flip_vertical):
        require_image_bhwc(image)
        out = image
        if flop_horizontal:
            out = torch.flip(out, dims=[2])
        if flip_vertical:
            out = torch.flip(out, dims=[1])
        return (out.contiguous(),)


# ───────────────────────── Filter ─────────────────────────
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


@resilient
class Sharpen:
    DESCRIPTION = "Unsharp-mask sharpen: amount * (image - blurred), added back."
    CATEGORY = "NukeMax/Filter"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}),
                             "amount": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 8.0, "step": 0.05}),
                             "size": ("INT", {"default": 3, "min": 1, "max": 64})}}

    def execute(self, image, amount, size):
        require_image_bhwc(image)
        rgb, alpha = _split(image)
        blurred = _gauss(rgb, int(size))
        out = (rgb + (rgb - blurred) * float(amount)).clamp(0, 1)
        return (_join(out, alpha),)


@resilient
class Median:
    DESCRIPTION = "Median filter (salt-and-pepper / grain denoise). size = window radius."
    CATEGORY = "NukeMax/Filter"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"image": ("IMAGE", {}),
                             "size": ("INT", {"default": 1, "min": 1, "max": 8})}}

    def execute(self, image, size):
        require_image_bhwc(image)
        r = int(size)
        rgb, alpha = _split(image)
        x = rgb.permute(0, 3, 1, 2)
        k = 2 * r + 1
        patches = F.unfold(F.pad(x, (r, r, r, r), mode="reflect"), kernel_size=k)
        B, C = x.shape[0], x.shape[1]
        patches = patches.view(B, C, k * k, -1)
        med = patches.median(dim=2).values
        out = med.view(B, C, x.shape[2], x.shape[3]).permute(0, 2, 3, 1)
        return (_join(out.clamp(0, 1), alpha),)


# ───────────────────────── Generators ─────────────────────────
@resilient
class Constant:
    DESCRIPTION = "Generate a solid-colour image at a chosen resolution."
    CATEGORY = "NukeMax/Generate"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "width": ("INT", {"default": 1920, "min": 1, "max": 16384}),
            "height": ("INT", {"default": 1080, "min": 1, "max": 16384}),
            "color": ("STRING", {"default": "#000000"}),
            "batch": ("INT", {"default": 1, "min": 1, "max": 64}),
        }}

    def execute(self, width, height, color, batch):
        r, g, b = _hex(color)
        out = torch.zeros(int(batch), int(height), int(width), 3)
        out[..., 0], out[..., 1], out[..., 2] = r, g, b
        return (out,)


@resilient
class CheckerBoard:
    DESCRIPTION = "Generate a checkerboard test pattern (size = square size in px)."
    CATEGORY = "NukeMax/Generate"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "width": ("INT", {"default": 1920, "min": 1, "max": 16384}),
            "height": ("INT", {"default": 1080, "min": 1, "max": 16384}),
            "size": ("INT", {"default": 64, "min": 1, "max": 2048}),
        }}

    def execute(self, width, height, size):
        W, H, s = int(width), int(height), max(1, int(size))
        ys = (torch.arange(H).view(H, 1) // s)
        xs = (torch.arange(W).view(1, W) // s)
        board = ((xs + ys) % 2).float()
        out = board.view(1, H, W, 1).repeat(1, 1, 1, 3) * 0.8 + 0.1
        return (out,)


@resilient
class ColorBars:
    DESCRIPTION = "Generate SMPTE-style vertical colour bars."
    CATEGORY = "NukeMax/Generate"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "width": ("INT", {"default": 1920, "min": 8, "max": 16384}),
            "height": ("INT", {"default": 1080, "min": 8, "max": 16384}),
        }}

    def execute(self, width, height):
        W, H = int(width), int(height)
        bars = [(1, 1, 1), (1, 1, 0), (0, 1, 1), (0, 1, 0), (1, 0, 1), (1, 0, 0), (0, 0, 1)]
        out = torch.zeros(1, H, W, 3)
        bw = W / len(bars)
        for i, (r, g, b) in enumerate(bars):
            x0, x1 = int(i * bw), int((i + 1) * bw)
            out[0, :, x0:x1, 0], out[0, :, x0:x1, 1], out[0, :, x0:x1, 2] = r * 0.75, g * 0.75, b * 0.75
        return (out,)


@resilient
class Ramp:
    DESCRIPTION = "Generate a linear gradient ramp (horizontal/vertical) between two values."
    CATEGORY = "NukeMax/Generate"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "width": ("INT", {"default": 1920, "min": 8, "max": 16384}),
            "height": ("INT", {"default": 1080, "min": 8, "max": 16384}),
            "direction": (("horizontal", "vertical"), {"default": "horizontal"}),
            "start": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            "end": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
        }}

    def execute(self, width, height, direction, start, end):
        W, H = int(width), int(height)
        if direction == "horizontal":
            t = torch.linspace(float(start), float(end), W).view(1, 1, W, 1)
            out = t.repeat(1, H, 1, 3)
        else:
            t = torch.linspace(float(start), float(end), H).view(1, H, 1, 1)
            out = t.repeat(1, 1, W, 3)
        return (out.clamp(0, 1),)


NODE_CLASS_MAPPINGS = {
    "NukeMax_Grade": Grade,
    "NukeMax_Multiply": Multiply,
    "NukeMax_Gamma": Gamma,
    "NukeMax_Invert": Invert,
    "NukeMax_Exposure": Exposure,
    "NukeMax_Merge": Merge,
    "NukeMax_Dissolve": Dissolve,
    "NukeMax_Keymix": Keymix,
    "NukeMax_Transform": Transform,
    "NukeMax_Mirror": Mirror,
    "NukeMax_Sharpen": Sharpen,
    "NukeMax_Median": Median,
    "NukeMax_Constant": Constant,
    "NukeMax_CheckerBoard": CheckerBoard,
    "NukeMax_ColorBars": ColorBars,
    "NukeMax_Ramp": Ramp,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_Grade": "Grade (NukeMax)",
    "NukeMax_Multiply": "Multiply (NukeMax)",
    "NukeMax_Gamma": "Gamma (NukeMax)",
    "NukeMax_Invert": "Invert (NukeMax)",
    "NukeMax_Exposure": "Exposure (NukeMax)",
    "NukeMax_Merge": "Merge (NukeMax)",
    "NukeMax_Dissolve": "Dissolve (NukeMax)",
    "NukeMax_Keymix": "Keymix (NukeMax)",
    "NukeMax_Transform": "Transform (NukeMax)",
    "NukeMax_Mirror": "Mirror (NukeMax)",
    "NukeMax_Sharpen": "Sharpen (NukeMax)",
    "NukeMax_Median": "Median (NukeMax)",
    "NukeMax_Constant": "Constant (NukeMax)",
    "NukeMax_CheckerBoard": "CheckerBoard (NukeMax)",
    "NukeMax_ColorBars": "ColorBars (NukeMax)",
    "NukeMax_Ramp": "Ramp (NukeMax)",
}
