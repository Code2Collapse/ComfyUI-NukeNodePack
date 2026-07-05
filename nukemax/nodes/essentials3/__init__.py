"""Essentials 3 — more core Nuke daily-drivers (batch 3):

  Filter:    Blur (Gaussian), EdgeDetect, Emboss, Bilateral, ZDefocus, MinMax
  Transform: Position, ContactSheet, AppendClip
  Generate:  Text, Grid, Vignette
  Color:     ChannelMixer, HistEQ

Pure-torch on [B,H,W,C] float 0..1 (cv2/PIL used only where noted, guarded),
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

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAVE_PIL = True
except Exception:  # noqa: BLE001
    _HAVE_PIL = False

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


def _gauss1d(n, sigma, device, dtype):
    n = max(1, int(n))
    xs = torch.arange(2 * n + 1, device=device, dtype=dtype) - n
    k = torch.exp(-(xs ** 2) / (2 * sigma * sigma))
    return k / k.sum()


def _sep_blur(img_bhwc, rx, ry):
    """Separable Gaussian blur with independent x/y radii (pixels)."""
    rx = int(max(0, round(rx)))
    ry = int(max(0, round(ry)))
    if rx < 1 and ry < 1:
        return img_bhwc
    x = img_bhwc.permute(0, 3, 1, 2)
    Cc = x.shape[1]
    if rx >= 1:
        kx = _gauss1d(rx, max(0.5, rx / 2.0), x.device, x.dtype).view(1, 1, 1, -1).repeat(Cc, 1, 1, 1)
        x = F.conv2d(F.pad(x, (rx, rx, 0, 0), mode="reflect"), kx, groups=Cc)
    if ry >= 1:
        ky = _gauss1d(ry, max(0.5, ry / 2.0), x.device, x.dtype).view(1, 1, -1, 1).repeat(Cc, 1, 1, 1)
        x = F.conv2d(F.pad(x, (0, 0, ry, ry), mode="reflect"), ky, groups=Cc)
    return x.permute(0, 2, 3, 1)


def _conv3x3(img_bhwc, kernel):
    """Apply a 3x3 kernel (list of 9) to each channel independently."""
    x = img_bhwc.permute(0, 3, 1, 2)
    Cc = x.shape[1]
    k = torch.tensor(kernel, device=x.device, dtype=x.dtype).view(1, 1, 3, 3).repeat(Cc, 1, 1, 1)
    x = F.conv2d(F.pad(x, (1, 1, 1, 1), mode="reflect"), k, groups=Cc)
    return x.permute(0, 2, 3, 1)


# ───────────────────────── Filter ─────────────────────────
@resilient
class Blur:
    DESCRIPTION = "Gaussian blur with independent horizontal / vertical size (Nuke Blur)."
    CATEGORY = "NukeMax/Filter"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "size": ("FLOAT", {"default": 4.0, "min": 0.0, "max": 256.0, "step": 0.5}),
            "aspect": ("FLOAT", {"default": 1.0, "min": 0.05, "max": 20.0, "step": 0.05,
                                 "tooltip": "vertical = size, horizontal = size*aspect"}),
            "blur_alpha": ("BOOLEAN", {"default": True}),
        }}
    def execute(self, image, size, aspect, blur_alpha):
        require_image_bhwc(image)
        rgb, a = _split(image)
        rx, ry = size * aspect, size
        rgb = _sep_blur(rgb, rx, ry).clamp(0, 1)
        if a is not None and blur_alpha:
            a = _sep_blur(a, rx, ry).clamp(0, 1)
        return (_join(rgb, a),)


@resilient
class EdgeDetect:
    DESCRIPTION = "Edge detection (Sobel / Prewitt / Laplacian / Roberts) on luma → matte."
    CATEGORY = "NukeMax/Filter"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK"); RETURN_NAMES = ("image", "mask")
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "operator": (["sobel", "prewitt", "laplacian", "roberts"], {}),
            "gain": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 16.0, "step": 0.1}),
            "colored": ("BOOLEAN", {"default": False, "tooltip": "Per-channel edges instead of luma."}),
        }}
    def _grad(self, x, operator):
        if operator == "laplacian":
            return _conv3x3(x, [0, 1, 0, 1, -4, 1, 0, 1, 0]).abs()
        if operator == "roberts":
            gx = _conv3x3(x, [0, 0, 0, 0, 1, 0, 0, 0, -1])
            gy = _conv3x3(x, [0, 0, 0, 0, 0, 1, 0, -1, 0])
            return (gx ** 2 + gy ** 2).sqrt()
        if operator == "prewitt":
            gx = _conv3x3(x, [-1, 0, 1, -1, 0, 1, -1, 0, 1])
            gy = _conv3x3(x, [-1, -1, -1, 0, 0, 0, 1, 1, 1])
        else:  # sobel
            gx = _conv3x3(x, [-1, 0, 1, -2, 0, 2, -1, 0, 1])
            gy = _conv3x3(x, [-1, -2, -1, 0, 0, 0, 1, 2, 1])
        return (gx ** 2 + gy ** 2).sqrt()
    def execute(self, image, operator, gain, colored):
        require_image_bhwc(image)
        rgb, _ = _split(image)
        if colored:
            e = (self._grad(rgb, operator) * gain).clamp(0, 1)
            mask = _luma(e).clamp(0, 1)
            return (e, mask)
        l = _luma(rgb).unsqueeze(-1)
        e = (self._grad(l, operator) * gain).clamp(0, 1)
        return (e.repeat(1, 1, 1, 3), e[..., 0].clamp(0, 1))


@resilient
class Emboss:
    DESCRIPTION = "Directional emboss (relief) filter."
    CATEGORY = "NukeMax/Filter"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "angle": ("FLOAT", {"default": 135.0, "min": 0.0, "max": 360.0, "step": 5.0}),
            "amount": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 5.0, "step": 0.1}),
            "grey": ("BOOLEAN", {"default": True, "tooltip": "Bias to mid-grey like a classic emboss."}),
        }}
    def execute(self, image, angle, amount, grey):
        require_image_bhwc(image)
        rgb, a = _split(image)
        th = math.radians(angle)
        dx, dy = math.cos(th), -math.sin(th)
        k = [-dx - dy, -dy, dx - dy,
             -dx, 0.0, dx,
             -dx + dy, dy, dx + dy]
        k = [v * amount for v in k]
        out = _conv3x3(rgb, k)
        if grey:
            out = out + 0.5
        return (_join(out.clamp(0, 1), a),)


@resilient
class Bilateral:
    DESCRIPTION = "Edge-preserving (bilateral) smoothing — clean noise while keeping edges crisp."
    CATEGORY = "NukeMax/Filter"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "size": ("INT", {"default": 5, "min": 1, "max": 25}),
            "sigma_space": ("FLOAT", {"default": 4.0, "min": 0.5, "max": 50.0, "step": 0.5}),
            "sigma_color": ("FLOAT", {"default": 0.1, "min": 0.01, "max": 1.0, "step": 0.01}),
        }}
    def execute(self, image, size, sigma_space, sigma_color):
        require_image_bhwc(image)
        rgb, a = _split(image)
        if _HAVE_CV2:
            out = torch.empty_like(rgb)
            d = int(size) * 2 + 1
            arr = (rgb.detach().cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            for i in range(arr.shape[0]):
                f = cv2.bilateralFilter(arr[i], d, sigma_color * 255.0, sigma_space)
                out[i] = torch.from_numpy(f.astype(np.float32) / 255.0).to(rgb.device, rgb.dtype)
            return (_join(out.clamp(0, 1), a),)
        # Pure-torch fallback: windowed joint domain/range weighting.
        r = int(size)
        x = rgb.permute(0, 3, 1, 2)
        B, Cc, H, W = x.shape
        xp = F.pad(x, (r, r, r, r), mode="reflect")
        acc = torch.zeros_like(x); wsum = torch.zeros(B, 1, H, W, device=x.device, dtype=x.dtype)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                shift = xp[:, :, r + dy:r + dy + H, r + dx:r + dx + W]
                ws = math.exp(-(dx * dx + dy * dy) / (2 * sigma_space * sigma_space))
                diff = ((shift - x) ** 2).sum(1, keepdim=True)
                wr = torch.exp(-diff / (2 * sigma_color * sigma_color))
                w = wr * ws
                acc += shift * w; wsum += w
        out = (acc / wsum.clamp(min=1e-6)).permute(0, 2, 3, 1)
        return (_join(out.clamp(0, 1), a),)


@resilient
class ZDefocus:
    DESCRIPTION = "Depth-driven defocus — blur scales with distance from the focal plane (a depth map drives it)."
    CATEGORY = "NukeMax/Filter"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "depth": ("IMAGE", {"tooltip": "Depth map (0=near .. 1=far). Luma is used."}),
            "focus_depth": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
            "max_blur": ("FLOAT", {"default": 24.0, "min": 0.0, "max": 128.0, "step": 1.0}),
            "layers": ("INT", {"default": 6, "min": 2, "max": 16}),
        }}
    def execute(self, image, depth, focus_depth, max_blur, layers):
        require_image_bhwc(image)
        rgb, a = _split(image)
        d = _luma(depth[..., :3]) if depth.shape[-1] >= 3 else depth[..., 0]
        if d.shape[1:3] != rgb.shape[1:3]:
            d = F.interpolate(d.unsqueeze(1), size=rgb.shape[1:3], mode="bilinear",
                              align_corners=False).squeeze(1)
        coc = (d - focus_depth).abs()  # 0 at focus .. up to ~max(focus,1-focus)
        denom = max(focus_depth, 1.0 - focus_depth, 1e-3)
        coc = (coc / denom).clamp(0, 1)  # [B,H,W] normalised blur strength
        n = int(layers)
        out = rgb.clone()
        # Composite progressively-blurred copies, selecting each by a CoC band.
        for i in range(1, n):
            t = i / (n - 1)
            radius = t * max_blur
            blurred = _sep_blur(rgb, radius, radius)
            lo = (i - 0.5) / (n - 1)
            w = (coc >= lo).to(rgb.dtype).unsqueeze(-1)
            out = out * (1 - w) + blurred * w
        return (_join(out.clamp(0, 1), a),)


@resilient
class MinMax:
    DESCRIPTION = "Morphological min / max / range filter (grow or shrink bright regions)."
    CATEGORY = "NukeMax/Filter"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "operation": (["max (dilate)", "min (erode)", "range"], {}),
            "size": ("INT", {"default": 3, "min": 1, "max": 49}),
        }}
    def execute(self, image, operation, size):
        require_image_bhwc(image)
        rgb, a = _split(image)
        x = rgb.permute(0, 3, 1, 2)
        k = int(size) * 2 + 1
        mx = F.max_pool2d(x, k, stride=1, padding=k // 2)
        if operation.startswith("max"):
            out = mx
        elif operation.startswith("min"):
            out = -F.max_pool2d(-x, k, stride=1, padding=k // 2)
        else:
            mn = -F.max_pool2d(-x, k, stride=1, padding=k // 2)
            out = mx - mn
        return (_join(out.permute(0, 2, 3, 1).clamp(0, 1), a),)


# ───────────────────────── Transform ─────────────────────────
@resilient
class Position:
    DESCRIPTION = "Integer pixel translate (no interpolation), with black / wrap edges (Nuke Position)."
    CATEGORY = "NukeMax/Transform"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "x": ("INT", {"default": 0, "min": -16384, "max": 16384}),
            "y": ("INT", {"default": 0, "min": -16384, "max": 16384}),
            "wrap": ("BOOLEAN", {"default": False}),
        }}
    def execute(self, image, x, y, wrap):
        require_image_bhwc(image)
        H, W = image.shape[1], image.shape[2]
        # Nuke y is up; shift rows by -y so positive y moves the image up.
        sx, sy = int(x), int(-y)
        if wrap:
            out = torch.roll(image, shifts=(sy, sx), dims=(1, 2))
            return (out.contiguous(),)
        out = torch.zeros_like(image)
        # source range that lands inside the frame after shifting
        ys0, ys1 = max(0, -sy), min(H, H - sy)
        xs0, xs1 = max(0, -sx), min(W, W - sx)
        yd0, xd0 = max(0, sy), max(0, sx)
        if ys1 > ys0 and xs1 > xs0:
            out[:, yd0:yd0 + (ys1 - ys0), xd0:xd0 + (xs1 - xs0), :] = image[:, ys0:ys1, xs0:xs1, :]
        return (out.contiguous(),)


@resilient
class ContactSheet:
    DESCRIPTION = "Lay every image in the batch out into a single rows×cols contact sheet."
    CATEGORY = "NukeMax/Transform"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "columns": ("INT", {"default": 0, "min": 0, "max": 64,
                                 "tooltip": "0 = auto (near-square)."}),
            "gap": ("INT", {"default": 4, "min": 0, "max": 256}),
        }}
    def execute(self, image, columns, gap):
        require_image_bhwc(image)
        B, H, W, C = image.shape
        cols = int(columns) if columns > 0 else max(1, int(math.ceil(math.sqrt(B))))
        rows = int(math.ceil(B / cols))
        g = int(gap)
        sheet = torch.zeros(1, rows * H + (rows - 1) * g, cols * W + (cols - 1) * g, C,
                            device=image.device, dtype=image.dtype)
        if C >= 4:
            sheet[..., 3] = 0.0
        for i in range(B):
            r, c = divmod(i, cols)
            y0, x0 = r * (H + g), c * (W + g)
            sheet[0, y0:y0 + H, x0:x0 + W, :] = image[i]
        return (sheet.contiguous(),)


@resilient
class AppendClip:
    DESCRIPTION = "Concatenate two image batches along the frame (batch) axis — A then B."
    CATEGORY = "NukeMax/Transform"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"a": ("IMAGE", {})}, "optional": {"b": ("IMAGE", {}), "c": ("IMAGE", {})}}
    def _match(self, ref, x):
        if x.shape[1:3] != ref.shape[1:3]:
            x = F.interpolate(x.permute(0, 3, 1, 2), size=ref.shape[1:3], mode="bilinear",
                              align_corners=False).permute(0, 2, 3, 1)
        if x.shape[-1] != ref.shape[-1]:
            if x.shape[-1] < ref.shape[-1]:
                pad = torch.ones(*x.shape[:-1], ref.shape[-1] - x.shape[-1], device=x.device, dtype=x.dtype)
                x = torch.cat([x, pad], dim=-1)
            else:
                x = x[..., :ref.shape[-1]]
        return x
    def execute(self, a, b=None, c=None):
        require_image_bhwc(a)
        clips = [a]
        if b is not None:
            clips.append(self._match(a, b))
        if c is not None:
            clips.append(self._match(a, c))
        return (torch.cat(clips, dim=0).contiguous(),)


# ───────────────────────── Generate ─────────────────────────
@resilient
class Text:
    DESCRIPTION = "Burn text onto the image (slate / annotation). Uses PIL if available."
    CATEGORY = "NukeMax/Generate"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK"); RETURN_NAMES = ("image", "mask")
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "text": ("STRING", {"default": "NukeMax", "multiline": True}),
            "size": ("INT", {"default": 48, "min": 4, "max": 1024}),
            "x": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 1.0, "step": 0.005}),
            "y": ("FLOAT", {"default": 0.05, "min": 0.0, "max": 1.0, "step": 0.005}),
            "color": ("STRING", {"default": "#ffffff"}),
        }}
    def execute(self, image, text, size, x, y, color):
        require_image_bhwc(image)
        B, H, W, C = image.shape
        if not _HAVE_PIL:
            # No PIL → return image unchanged + empty matte rather than crash.
            return (image.contiguous(), torch.zeros(B, H, W, device=image.device, dtype=image.dtype))
        r, g, b = _hex(color, (1.0, 1.0, 1.0))
        out = image.clone()
        matte = torch.zeros(B, H, W, device=image.device, dtype=image.dtype)
        try:
            font = ImageFont.truetype("arial.ttf", int(size))
        except Exception:  # noqa: BLE001
            font = ImageFont.load_default()
        px, py = int(x * W), int(y * H)
        for i in range(B):
            layer = Image.new("L", (W, H), 0)
            d = ImageDraw.Draw(layer)
            d.multiline_text((px, py), str(text), fill=255, font=font, spacing=4)
            m = torch.from_numpy(np.asarray(layer, dtype=np.float32) / 255.0).to(image.device, image.dtype) \
                if _HAVE_CV2 else torch.tensor([[c_ / 255.0 for c_ in row] for row in layer.getdata()]).reshape(H, W).to(image.device, image.dtype)
            matte[i] = m
            col = torch.tensor([r, g, b], device=image.device, dtype=image.dtype).view(1, 1, 3)
            out[i, ..., :3] = out[i, ..., :3] * (1 - m.unsqueeze(-1)) + col * m.unsqueeze(-1)
            if C >= 4:
                out[i, ..., 3] = torch.maximum(out[i, ..., 3], m)
        return (out.clamp(0, 1).contiguous(), matte)


@resilient
class Grid:
    DESCRIPTION = "Generate a grid / graph-paper pattern (line spacing, width, colours)."
    CATEGORY = "NukeMax/Generate"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "width": ("INT", {"default": 1024, "min": 8, "max": 16384}),
            "height": ("INT", {"default": 1024, "min": 8, "max": 16384}),
            "spacing": ("INT", {"default": 64, "min": 2, "max": 4096}),
            "line_width": ("INT", {"default": 1, "min": 1, "max": 64}),
            "line_color": ("STRING", {"default": "#808080"}),
            "bg_color": ("STRING", {"default": "#000000"}),
        }}
    def execute(self, width, height, spacing, line_width, line_color, bg_color):
        W, H = int(width), int(height)
        lr, lg, lb = _hex(line_color, (0.5, 0.5, 0.5))
        br, bg, bb = _hex(bg_color, (0.0, 0.0, 0.0))
        img = torch.empty(1, H, W, 3)
        img[..., 0] = br; img[..., 1] = bg; img[..., 2] = bb
        sp, lw = max(2, int(spacing)), max(1, int(line_width))
        ys = (torch.arange(H) % sp) < lw
        xs = (torch.arange(W) % sp) < lw
        line = ys.view(H, 1) | xs.view(1, W)
        for ch, v in enumerate((lr, lg, lb)):
            img[0, ..., ch] = torch.where(line, torch.tensor(v), img[0, ..., ch])
        return (img.contiguous(),)


@resilient
class Vignette:
    DESCRIPTION = "Radial vignette — darken (or brighten) toward the frame edges."
    CATEGORY = "NukeMax/Generate"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "amount": ("FLOAT", {"default": 0.5, "min": -1.0, "max": 1.0, "step": 0.01}),
            "radius": ("FLOAT", {"default": 0.75, "min": 0.05, "max": 2.0, "step": 0.01}),
            "softness": ("FLOAT", {"default": 0.5, "min": 0.01, "max": 2.0, "step": 0.01}),
        }}
    def execute(self, image, amount, radius, softness):
        require_image_bhwc(image)
        rgb, a = _split(image)
        B, H, W, _ = rgb.shape
        yy = torch.linspace(-1, 1, H, device=rgb.device, dtype=rgb.dtype).view(H, 1)
        xx = torch.linspace(-1, 1, W, device=rgb.device, dtype=rgb.dtype).view(1, W)
        # aspect-correct radial distance
        ar = W / max(1, H)
        d = torch.sqrt((xx * max(1.0, ar)) ** 2 + (yy * max(1.0, 1.0 / ar)) ** 2)
        edge = ((d - radius) / max(1e-3, softness)).clamp(0, 1)
        mask = (edge * abs(amount)).view(1, H, W, 1)
        if amount >= 0:
            out = rgb * (1.0 - mask)
        else:
            out = rgb + (1.0 - rgb) * mask
        return (_join(out.clamp(0, 1), a),)


# ───────────────────────── Color ─────────────────────────
@resilient
class ChannelMixer:
    DESCRIPTION = "RGB channel mixer — each output channel is a weighted sum of input R/G/B (e.g. B&W mix)."
    CATEGORY = "NukeMax/Color"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        m = lambda d: ("FLOAT", {"default": d, "min": -2.0, "max": 2.0, "step": 0.01})
        return {"required": {"image": ("IMAGE", {}),
                "rr": m(1.0), "rg": m(0.0), "rb": m(0.0),
                "gr": m(0.0), "gg": m(1.0), "gb": m(0.0),
                "br": m(0.0), "bg": m(0.0), "bb": m(1.0),
                "monochrome": ("BOOLEAN", {"default": False})}}
    def execute(self, image, rr, rg, rb, gr, gg, gb, br, bg, bb, monochrome):
        require_image_bhwc(image)
        rgb, a = _split(image)
        mat = torch.tensor([[rr, rg, rb], [gr, gg, gb], [br, bg, bb]],
                           device=rgb.device, dtype=rgb.dtype)
        out = torch.einsum("bhwc,oc->bhwo", rgb, mat)
        if monochrome:
            out = out[..., 0:1].repeat(1, 1, 1, 3)
        return (_join(out.clamp(0, 1), a),)


@resilient
class HistEQ:
    DESCRIPTION = "Histogram equalisation / CLAHE on luma — boost local contrast (cv2 if available)."
    CATEGORY = "NukeMax/Color"; FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",); RETURN_NAMES = ("image",)
    @classmethod
    def IS_CHANGED(cls, **k): return hash_args_and_kwargs(**k)
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "mode": (["global", "clahe"], {}),
            "clip_limit": ("FLOAT", {"default": 2.0, "min": 0.5, "max": 16.0, "step": 0.5}),
            "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
        }}
    def execute(self, image, mode, clip_limit, mix):
        require_image_bhwc(image)
        rgb, a = _split(image)
        if _HAVE_CV2:
            out = torch.empty_like(rgb)
            arr = (rgb.detach().cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            clahe = cv2.createCLAHE(clipLimit=float(clip_limit), tileGridSize=(8, 8))
            for i in range(arr.shape[0]):
                lab = cv2.cvtColor(arr[i], cv2.COLOR_RGB2LAB)
                L = lab[..., 0]
                lab[..., 0] = clahe.apply(L) if mode == "clahe" else cv2.equalizeHist(L)
                eq = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
                out[i] = torch.from_numpy(eq.astype(np.float32) / 255.0).to(rgb.device, rgb.dtype)
        else:
            # Pure-torch global equalisation on luma, applied as a gain to RGB.
            l = _luma(rgb)
            out = rgb.clone()
            for i in range(l.shape[0]):
                flat = l[i].reshape(-1)
                ranks = torch.argsort(torch.argsort(flat)).to(rgb.dtype) / max(1, flat.numel() - 1)
                eqL = ranks.reshape(l[i].shape)
                gain = (eqL / l[i].clamp(min=1e-4)).clamp(0, 4).unsqueeze(-1)
                out[i] = rgb[i] * gain
        out = (rgb * (1 - mix) + out * mix).clamp(0, 1)
        return (_join(out, a),)


NODE_CLASS_MAPPINGS = {
    "NukeMax_Blur": Blur, "NukeMax_EdgeDetect": EdgeDetect, "NukeMax_Emboss": Emboss,
    "NukeMax_Bilateral": Bilateral, "NukeMax_ZDefocus": ZDefocus, "NukeMax_MinMax": MinMax,
    "NukeMax_Position": Position, "NukeMax_ContactSheet": ContactSheet, "NukeMax_AppendClip": AppendClip,
    "NukeMax_Text": Text, "NukeMax_Grid": Grid, "NukeMax_Vignette": Vignette,
    "NukeMax_ChannelMixer": ChannelMixer, "NukeMax_HistEQ": HistEQ,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_Blur": "Blur (NukeMax)", "NukeMax_EdgeDetect": "EdgeDetect (NukeMax)",
    "NukeMax_Emboss": "Emboss (NukeMax)", "NukeMax_Bilateral": "Bilateral (NukeMax)",
    "NukeMax_ZDefocus": "ZDefocus (NukeMax)", "NukeMax_MinMax": "MinMax (NukeMax)",
    "NukeMax_Position": "Position (NukeMax)", "NukeMax_ContactSheet": "ContactSheet (NukeMax)",
    "NukeMax_AppendClip": "AppendClip (NukeMax)", "NukeMax_Text": "Text (NukeMax)",
    "NukeMax_Grid": "Grid (NukeMax)", "NukeMax_Vignette": "Vignette (NukeMax)",
    "NukeMax_ChannelMixer": "ChannelMixer (NukeMax)", "NukeMax_HistEQ": "HistEQ (NukeMax)",
}
