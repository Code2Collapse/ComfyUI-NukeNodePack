"""Linear-float helpers for the comp-operator tier.

Design contract (PROCESS_PLATE.md section 3) in one sentence: these are
linear-light VFX operators, so **nothing in this module clamps to 0..1**.
A specular highlight at 12.0 stays at 12.0 through every op; clamping it is
how a delivery loses its highlights.

The only values deliberately bounded here are *mattes* — a ComfyUI ``MASK``
is a coverage channel and 0..1 is its actual definition, not a display
convenience.

Failure policy: raise with a message that names the input and the fix. No
silent substitution, no zero-image fallback — a black frame that looks like
a render is worse than a stopped graph.
"""
from __future__ import annotations

from typing import Sequence

import torch
import torch.nn.functional as F

# Rec.709 luminance weights. Correct for linear scene-referred RGB.
LUMA_709 = (0.2126, 0.7152, 0.0722)

# Hue wheel bucket centres used by the hue-based operators (degrees).
HUE_CENTRES = (0.0, 60.0, 120.0, 180.0, 240.0, 300.0)


# ───────────────────────── contract checks ─────────────────────────
def require_image(tensor, name: str = "image") -> torch.Tensor:
    """Validate a ComfyUI IMAGE: torch.float32 [B,H,W,C], any H/W/C.

    Raises with the actual shape and the fix, never returns a substitute.
    """
    if not isinstance(tensor, torch.Tensor):
        raise ValueError(
            f"'{name}' must be a ComfyUI IMAGE tensor [B,H,W,C]; got "
            f"{type(tensor).__name__}. Connect an IMAGE output to '{name}'."
        )
    if tensor.ndim != 4:
        raise ValueError(
            f"'{name}' must be 4-D [B,H,W,C]; got shape {tuple(tensor.shape)}. "
            f"If this came from a MASK, convert it with a Mask-to-Image node first."
        )
    if tensor.shape[-1] < 1:
        raise ValueError(f"'{name}' has 0 channels (shape {tuple(tensor.shape)}).")
    return tensor


def require_mask(tensor, name: str = "mask") -> torch.Tensor:
    """Validate a ComfyUI MASK: [B,H,W] (a [B,H,W,1] IMAGE is also accepted)."""
    if not isinstance(tensor, torch.Tensor):
        raise ValueError(
            f"'{name}' must be a ComfyUI MASK tensor [B,H,W]; got {type(tensor).__name__}."
        )
    if tensor.ndim not in (3, 4):
        raise ValueError(
            f"'{name}' must be [B,H,W] (or [B,H,W,1]); got shape {tuple(tensor.shape)}."
        )
    return tensor


# ───────────────────────── channel plumbing ─────────────────────────
def split_rgb_alpha(image: torch.Tensor):
    """-> (rgb [B,H,W,3], alpha [B,H,W,1] or None, extra [B,H,W,N] or None).

    Channels beyond RGBA (AOV-carrying images) are preserved in ``extra`` and
    handed back untouched by :func:`join_rgb_alpha`. Dropping them silently is
    exactly the failure this program exists to stop.
    """
    c = image.shape[-1]
    if c < 3:
        # 1- or 2-channel image: replicate to RGB so colour maths is defined,
        # and remember nothing extra.
        rgb = image[..., :1].expand(*image.shape[:-1], 3)
        return rgb, None, None
    rgb = image[..., :3]
    alpha = image[..., 3:4] if c >= 4 else None
    extra = image[..., 4:] if c > 4 else None
    return rgb, alpha, extra


def join_rgb_alpha(rgb: torch.Tensor, alpha=None, extra=None) -> torch.Tensor:
    parts = [rgb]
    if alpha is not None:
        parts.append(alpha)
    if extra is not None and extra.shape[-1] > 0:
        parts.append(extra)
    return (parts[0] if len(parts) == 1 else torch.cat(parts, dim=-1)).contiguous()


def luma(rgb: torch.Tensor) -> torch.Tensor:
    """Rec.709 luminance -> [B,H,W]. Unbounded (HDR in, HDR out)."""
    return (rgb[..., 0] * LUMA_709[0]
            + rgb[..., 1] * LUMA_709[1]
            + rgb[..., 2] * LUMA_709[2])


def match_size(src: torch.Tensor, ref: torch.Tensor, mode: str = "bilinear") -> torch.Tensor:
    """Resample ``src`` [B,H,W,C] to ref's H,W. No clamping, no channel loss."""
    if src.shape[1:3] == ref.shape[1:3]:
        return src
    kw = {} if mode in ("nearest", "area") else {"align_corners": False}
    return F.interpolate(src.permute(0, 3, 1, 2), size=tuple(ref.shape[1:3]),
                         mode=mode, **kw).permute(0, 2, 3, 1).contiguous()


def match_batch(src: torch.Tensor, ref: torch.Tensor, name: str = "B") -> torch.Tensor:
    """Broadcast a 1-frame input across ref's batch, or fail loudly on a real mismatch."""
    if src.shape[0] == ref.shape[0]:
        return src
    if src.shape[0] == 1:
        return src.expand(ref.shape[0], *src.shape[1:])
    raise ValueError(
        f"batch mismatch: '{name}' has {src.shape[0]} frames but the reference has "
        f"{ref.shape[0]}. Use a single frame (auto-broadcast) or matching frame counts."
    )


def mask_to_bhwc1(mask: torch.Tensor, ref: torch.Tensor) -> torch.Tensor:
    """MASK [B,H,W] (or [B,H,W,1]) -> [B,H,W,1] resized to ref and broadcast in batch."""
    m = mask.unsqueeze(-1) if mask.ndim == 3 else mask[..., :1]
    m = m.to(device=ref.device, dtype=ref.dtype)
    m = match_size(m, ref)
    return match_batch(m, ref, "mask")


def blend_with_mask(original: torch.Tensor, processed: torch.Tensor, mask) -> torch.Tensor:
    """out = original where mask=0, processed where mask=1. mask may be None."""
    if mask is None:
        return processed
    m = mask_to_bhwc1(mask, original)
    return original + (processed - original) * m


# ───────────────────────── HDR-safe maths ─────────────────────────
def gamma_apply(x: torch.Tensor, gamma: float) -> torch.Tensor:
    """Nuke's gamma: out = x^(1/gamma) for x > 0, x unchanged for x <= 0.

    Positive HDR values are preserved (2.0 ** (1/2.2) is a real number); the
    negative side is passed through rather than NaN-ed or clamped, which is
    what Nuke's Grade does and what keeps negative-lobe filter ringing alive.
    """
    g = float(gamma)
    if g == 1.0:
        return x
    if g <= 0.0:
        raise ValueError(f"gamma must be > 0; got {g}.")
    return torch.where(x > 0, x.clamp(min=0) ** (1.0 / g), x)


def hue_degrees(rgb: torch.Tensor) -> torch.Tensor:
    """Hue in 0..360 -> [B,H,W]. Scale-invariant, so HDR-safe by construction."""
    mx, _ = rgb.max(dim=-1)
    mn, _ = rgb.min(dim=-1)
    d = mx - mn
    safe = torch.where(d.abs() < 1e-12, torch.ones_like(d), d)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = torch.zeros_like(mx)
    h = torch.where(mx == r, ((g - b) / safe) % 6.0, h)
    h = torch.where(mx == g, ((b - r) / safe) + 2.0, h)
    h = torch.where(mx == b, ((r - g) / safe) + 4.0, h)
    h = (h * 60.0) % 360.0
    return torch.where(d.abs() < 1e-12, torch.zeros_like(h), h)


def hue_bucket_weights(h_deg: torch.Tensor) -> torch.Tensor:
    """Triangular weights for the 6 hue buckets -> [..., 6]; rows sum to 1.0.

    60-degree spacing with triangular falloff partitions the wheel exactly,
    so a bucket gain of 1.0 everywhere is a mathematical identity.
    """
    ws = []
    for c in HUE_CENTRES:
        d = (h_deg - c).abs()
        d = torch.minimum(d, 360.0 - d)          # wrap-around distance
        ws.append((1.0 - d / 60.0).clamp(min=0.0))
    return torch.stack(ws, dim=-1)


def saturation_scale(rgb: torch.Tensor, factor: torch.Tensor | float) -> torch.Tensor:
    """Scale saturation about Rec.709 luma. Unbounded on both sides."""
    l = luma(rgb).unsqueeze(-1)
    return l + (rgb - l) * factor


def eval_curve(x: torch.Tensor, knots: Sequence[tuple[float, float]]) -> torch.Tensor:
    """Piecewise-linear lookup with **linear extrapolation** past both ends.

    Extrapolation is the whole point: a 0..1 curve that hard-stops at its last
    knot would flatten every value above 1.0 into a single number, which is a
    clamp wearing a curve's clothes.
    """
    if len(knots) < 2:
        raise ValueError(
            f"a lookup curve needs at least 2 control points; got {len(knots)}. "
            f"Use the form '0,0; 1,1'."
        )
    pts = sorted(knots, key=lambda p: p[0])
    for i in range(1, len(pts)):
        if pts[i][0] - pts[i - 1][0] < 1e-9:
            raise ValueError(
                f"lookup curve has two control points at x={pts[i][0]}; "
                f"x values must be distinct and increasing."
            )
    xs = torch.tensor([p[0] for p in pts], device=x.device, dtype=x.dtype)
    ys = torch.tensor([p[1] for p in pts], device=x.device, dtype=x.dtype)
    flat = x.reshape(-1).contiguous()
    idx = (torch.searchsorted(xs, flat, right=True) - 1).clamp(0, len(pts) - 2)
    x0, x1 = xs[idx], xs[idx + 1]
    y0, y1 = ys[idx], ys[idx + 1]
    t = (flat - x0) / (x1 - x0)                  # <0 or >1 outside -> extrapolates
    return (y0 + t * (y1 - y0)).reshape(x.shape)


def parse_curve(spec: str, name: str) -> list[tuple[float, float]]:
    """Parse ``'0,0; 0.5,0.6; 1,1'`` into control points. Raises on anything else."""
    text = str(spec).strip()
    if not text:
        raise ValueError(
            f"'{name}' is empty. Give at least two 'x,y' control points, "
            f"e.g. '0,0; 1,1' for an identity curve."
        )
    out: list[tuple[float, float]] = []
    for chunk in text.replace("\n", ";").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        bits = [b for b in chunk.replace(":", ",").split(",") if b.strip()]
        if len(bits) != 2:
            raise ValueError(
                f"'{name}': cannot read control point {chunk!r}. Expected 'x,y' pairs "
                f"separated by ';', e.g. '0,0; 0.5,0.6; 1,1'."
            )
        try:
            out.append((float(bits[0]), float(bits[1])))
        except ValueError as exc:
            raise ValueError(
                f"'{name}': {chunk!r} is not a pair of numbers ({exc})."
            ) from None
    return out


def parse_floats(spec: str, name: str, expect: int | None = None) -> list[float]:
    """Parse whitespace/comma separated floats (convolution kernels, colours)."""
    text = str(spec).replace(",", " ").replace(";", " ").split()
    if not text:
        raise ValueError(f"'{name}' is empty; expected a list of numbers.")
    try:
        vals = [float(v) for v in text]
    except ValueError as exc:
        raise ValueError(f"'{name}' contains a non-number: {exc}.") from None
    if expect is not None and len(vals) != expect:
        raise ValueError(
            f"'{name}' needs exactly {expect} numbers; got {len(vals)}."
        )
    return vals


def separable_blur(img_bhwc: torch.Tensor, rx: float, ry: float) -> torch.Tensor:
    """Separable Gaussian blur, radii in pixels. Linear-float, never clamps."""
    rxi, ryi = int(max(0, round(rx))), int(max(0, round(ry)))
    if rxi < 1 and ryi < 1:
        return img_bhwc
    x = img_bhwc.permute(0, 3, 1, 2)
    c = x.shape[1]

    def _k(n):
        sigma = max(0.5, n / 2.0)
        t = torch.arange(2 * n + 1, device=x.device, dtype=x.dtype) - n
        k = torch.exp(-(t ** 2) / (2 * sigma * sigma))
        return k / k.sum()

    if rxi >= 1:
        kx = _k(rxi).view(1, 1, 1, -1).repeat(c, 1, 1, 1)
        x = F.conv2d(F.pad(x, (rxi, rxi, 0, 0), mode="reflect"), kx, groups=c)
    if ryi >= 1:
        ky = _k(ryi).view(1, 1, -1, 1).repeat(c, 1, 1, 1)
        x = F.conv2d(F.pad(x, (0, 0, ryi, ryi), mode="reflect"), ky, groups=c)
    return x.permute(0, 2, 3, 1).contiguous()


def hdr_report(image: torch.Tensor) -> str:
    """One-line range summary for an ``info`` output. Surfaces what survived."""
    mn = float(image.min())
    mx = float(image.max())
    over = int((image > 1.0).sum())
    return (f"shape={tuple(image.shape)} range=[{mn:.4f}, {mx:.4f}] "
            f"pixels>1.0={over}")
