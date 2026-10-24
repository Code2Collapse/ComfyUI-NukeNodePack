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
    DESCRIPTION = ("Nuke Grade: blackpoint/whitepoint remap to lift/gain, multiply, offset and gamma, exactly as "
                   "Nuke computes it: A = multiply*(gain-lift)/(whitepoint-blackpoint), B = offset+lift-A*blackpoint, "
                   "out = (A*in+B)^(1/gamma) (gamma leaves values <= 0 alone). black_clamp (on) / white_clamp (off) "
                   "as in Nuke; reverse undoes the grade; mix blends with the input. Linear float: no other clamp.")
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
        }, "optional": {
            "mask": ("MASK", {"tooltip": "Where the grade applies; another size is resized to the image."}),
            # L9.39, appended (saved widgets keep their positions): Nuke Grade's own knobs
            "black_clamp": ("BOOLEAN", {"default": True,
                            "tooltip": "Clamp negative results to 0 (Nuke's default)."}),
            "white_clamp": ("BOOLEAN", {"default": False,
                            "tooltip": "Clamp results above 1 (off: highlights stay, linear float)."}),
            "reverse": ("BOOLEAN", {"default": False,
                        "tooltip": "Apply the inverse grade - undoes this grade with the same settings."}),
            "mix": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01,
                    "tooltip": "Blend with the input (0 = untouched)."}),
        }}

    def execute(self, image, blackpoint, whitepoint, lift, gain, multiply, offset, gamma, mask=None,
                black_clamp=True, white_clamp=False, reverse=False, mix=1.0):
        require_image_bhwc(image)
        rgb, alpha = _split(image)
        bp, wp = float(blackpoint), float(whitepoint)
        denom = (wp - bp) if abs(wp - bp) > 1e-6 else 1e-6
        # Nuke's Grade (L9.39: lift used to be multiplied by `multiply` too, and the result clamped to 0..1)
        a = float(multiply) * (float(gain) - float(lift)) / denom
        b = float(offset) + float(lift) - a * bp
        g = float(gamma)
        if not reverse:
            out = a * rgb + b
            if g != 1.0:
                out = torch.where(out > 0, out.clamp(min=0) ** (1.0 / g), out)
        else:
            x = torch.where(rgb > 0, rgb.clamp(min=0) ** g, rgb) if g != 1.0 else rgb
            out = (x - b) / (a if abs(a) > 1e-12 else 1e-12)
        if black_clamp:
            out = out.clamp(min=0)
        if white_clamp:
            out = out.clamp(max=1)
        w = float(mix)
        if mask is not None:
            m = mask
            if m.dim() == 3:
                m = m.unsqueeze(-1)
            if m.shape[1:3] != rgb.shape[1:3]:
                m = F.interpolate(m.permute(0, 3, 1, 2).float(), size=rgb.shape[1:3], mode="bilinear",
                                  align_corners=False).permute(0, 2, 3, 1)
            w = m.to(rgb.dtype) * w
        if not (isinstance(w, float) and w == 1.0):
            out = rgb * (1 - w) + out * w
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
        return (_join(rgb * g, alpha),)


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
        # values <= 0 pass through, as Nuke's Gamma does (they used to become 1e-6, then everything was clamped)
        out = torch.where(rgb > 0, rgb.clamp(min=0) ** (1.0 / float(gamma)), rgb) if gamma != 1.0 else rgb
        return (_join(out, alpha),)


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
        return (_join(1.0 - rgb, alpha),)


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
                             "stops": ("FLOAT", {"default": 0.0, "min": -10.0, "max": 10.0, "step": 0.1})},
                "optional": {
                    "exposure_mode": (("stops", "printer_lights", "film_density"), {
                        "default": "stops",
                        "tooltip": "Unit for the stops knob: f-stops, printer lights, or film density."}),
                    "multiply": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.01}),
                    "offset": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                    "preserve_highlights": ("BOOLEAN", {"default": True,
                        "tooltip": "On (default since L9.39): linear float, values above 1 stay. Off: clamp to "
                                   "0-1 (older workflows keep the value they were saved with)."}),
                }}

    def execute(self, image, stops, exposure_mode="stops", multiply=1.0, offset=0.0,
                preserve_highlights=True):
        require_image_bhwc(image)
        rgb, alpha = _split(image)
        s = float(stops)
        if exposure_mode == "printer_lights":
            exp_mult = 10.0 ** (s / 25.0)
        elif exposure_mode == "film_density":
            exp_mult = 10.0 ** (-s)
        else:
            exp_mult = 2.0 ** s
        out = rgb * exp_mult * float(multiply) + float(offset)
        if not preserve_highlights:
            out = out.clamp(0, 1)
        return (_join(out, alpha),)


# ───────────────────────── Merge ─────────────────────────
# saved workflows store the operation name: new ones are appended
_MERGE_OPS = ("over", "under", "atop", "in", "out", "mask", "stencil",
              "plus", "minus", "multiply", "screen", "overlay", "difference",
              "max", "min", "average",
              "soft_light", "hard_light", "color_dodge", "color_burn",
              "darken", "lighten", "exclusion", "divide", "hypot", "xor", "matte", "copy",
              "from", "conjoint_over", "disjoint_over", "geometric")


def _merge_op(op, A, B, a, b):
    """Nuke's Merge formula for one set of channels. A, B premultiplied values; a, b their alphas (broadcast). The
    same formula runs on the alpha channel itself (A = a, B = b), as Nuke's Merge does with output = rgba."""
    if op == "over":       return A + B * (1 - a)
    if op == "under":      return A * (1 - b) + B
    if op == "atop":       return A * b + B * (1 - a)
    if op == "in":         return A * b
    if op == "out":        return A * (1 - b)
    if op == "mask":       return B * a
    if op == "stencil":    return B * (1 - a)
    if op == "plus":       return A + B
    if op == "minus":      return A - B                       # Nuke: A - B ("from" is B - A)
    if op == "from":       return B - A
    if op == "multiply":   return torch.where((A < 0) & (B < 0), A, A * B)
    if op == "screen":     return torch.where((A <= 1) & (B <= 1), A + B - A * B, torch.maximum(A, B))
    if op == "overlay":    return torch.where(B < 0.5, 2 * A * B, 1 - 2 * (1 - A) * (1 - B))
    if op == "hard_light": return torch.where(A < 0.5, 2 * A * B, 1 - 2 * (1 - A) * (1 - B))
    if op == "soft_light":
        return torch.where(B < 0.5, 2 * A * B + B ** 2 * (1 - 2 * A),
                           2 * B * (1 - A) + torch.sqrt(B.clamp(min=0)) * (2 * A - 1))
    if op == "difference": return (A - B).abs()
    if op in ("max", "lighten"): return torch.maximum(A, B)
    if op in ("min", "darken"):  return torch.minimum(A, B)
    if op == "average":    return (A + B) * 0.5
    if op == "color_dodge":
        return torch.where(A >= 1.0, torch.maximum(A, B), B / (1 - A).clamp(min=1e-7))
    if op == "color_burn":
        return torch.where(A <= 0.0, torch.minimum(A, B), 1 - (1 - B) / A.clamp(min=1e-7))
    if op == "exclusion":  return A + B - 2 * A * B
    if op == "divide":                                       # Nuke: A / B, 0 where both are negative
        q = A / torch.where(B.abs() < 1e-12, torch.full_like(B, 1e-12), B)
        return torch.where((A < 0) & (B < 0), torch.zeros_like(A), q)
    if op == "hypot":      return torch.sqrt(A * A + B * B)
    if op == "xor":        return A * (1 - b) + B * (1 - a)
    if op == "matte":      return A * a + B * (1 - a)       # A unpremultiplied over B
    if op == "copy":       return A
    if op == "geometric":
        den = A + B
        return torch.where(den.abs() < 1e-12, torch.zeros_like(A), 2 * A * B / torch.where(
            den.abs() < 1e-12, torch.ones_like(den), den))
    if op == "conjoint_over":                                # A + B(1-a)/b where a < b, else A
        return torch.where(a >= b, A, A + B * (1 - a / b.clamp(min=1e-12)))
    if op == "disjoint_over":                                # A + B(1-a)/b where a + b > 1, else A + B
        return torch.where(a + b <= 1, A + B, A + B * (1 - a) / b.clamp(min=1e-12))
    raise ValueError(f"Unknown merge operation {op!r}; pick one of {', '.join(_MERGE_OPS)}.")


@resilient
class Merge:
    DESCRIPTION = ("Nuke Merge: A merged with B by the chosen operation (over, under, atop, in, out, mask, stencil, "
                   "plus, minus, from, multiply, screen, overlay, difference, max, min, average, divide, conjoint / "
                   "disjoint over, ...). As in Nuke the operation runs on alpha too, the output takes B's format "
                   "(A is resized to it), and nothing is clamped. 'mix' (times the optional mask) dissolves the "
                   "result back toward B.")
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
        }, "optional": {
            "mask": ("MASK", {"tooltip": "Optional matte: the mix is applied only where it is white."}),
            # L9.39 - appended
            "invert_mask": ("BOOLEAN", {"default": False, "tooltip": "Use the inverse of the mask."}),
        }}

    def execute(self, A, B, operation, mix, mask=None, invert_mask=False):
        require_image_bhwc(A); require_image_bhwc(B)
        if A.shape[0] != B.shape[0] and 1 not in (A.shape[0], B.shape[0]):
            raise ValueError(f"A has {A.shape[0]} frames and B has {B.shape[0]}; give them the same count "
                             "(or a single frame on one side).")
        A = _match_hw(A, B).to(B.dtype)                       # B's format, as in Nuke
        a_rgb, a_a = _split(A)
        b_rgb, b_a = _split(B)
        aa = a_a if a_a is not None else torch.ones_like(a_rgb[..., :1])
        ba = b_a if b_a is not None else torch.ones_like(b_rgb[..., :1])
        out = _merge_op(operation, a_rgb, b_rgb, aa, ba)
        has_alpha = a_a is not None or b_a is not None
        out_a = _merge_op(operation, aa, ba, aa, ba) if has_alpha else None
        m = torch.full_like(b_rgb[..., :1], float(mix))
        if mask is not None:
            mm = _mask_1c(mask, b_rgb)
            m = m * ((1.0 - mm) if invert_mask else mm)
        if mask is not None or float(mix) < 1.0:
            out = b_rgb * (1 - m) + out * m
            if out_a is not None:
                out_a = ba * (1 - m) + out_a * m
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
        return ((A * (1 - w) + B * w).contiguous(),)


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
        return ((A * m + B * (1 - m)).contiguous(),)


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
            # NOTE: lanczos / keys / mitchell were briefly offered here and every
            # one of them silently ran bicubic. F.grid_sample supports only
            # nearest / bilinear / bicubic, and an arbitrary affine warp cannot
            # use a separable kernel without a bespoke resampler. Offering a
            # filter that quietly does something else is worse than not offering
            # it - a compositor picking "lanczos" would be measuring a lie.
            "filter": (("bilinear", "nearest", "bicubic"),
                       {"default": "bilinear"}),
            "wrap": (("black", "edge", "reflection"), {"default": "black"}),
        }, "optional": {
            "center_x": ("FLOAT", {"default": -1.0, "min": -8192, "max": 8192, "step": 1,
                         "tooltip": "-1 = image centre (legacy default)."}),
            "center_y": ("FLOAT", {"default": -1.0, "min": -8192, "max": 8192, "step": 1}),
            "skew_x": ("FLOAT", {"default": 0.0, "min": -89.0, "max": 89.0, "step": 0.1}),
            "skew_y": ("FLOAT", {"default": 0.0, "min": -89.0, "max": 89.0, "step": 0.1}),
            "scale_x": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 16.0, "step": 0.01}),
            "scale_y": ("FLOAT", {"default": 1.0, "min": 0.01, "max": 16.0, "step": 0.01}),
            # L9.39, appended
            "invert": ("BOOLEAN", {"default": False,
                       "tooltip": "Apply the inverse transform (undoes this one with the same settings)."}),
        }}

    def execute(self, image, translate_x, translate_y, rotate, scale, filter, wrap,
                center_x=-1.0, center_y=-1.0, skew_x=0.0, skew_y=0.0,
                scale_x=1.0, scale_y=1.0, invert=False):
        require_image_bhwc(image)
        B, H, W, C = image.shape
        x = image.permute(0, 3, 1, 2)
        ang = torch.tensor(float(rotate) * 3.14159265 / 180.0)
        cos, sin = torch.cos(ang), torch.sin(ang)
        tx = -2.0 * float(translate_x) / W
        ty = -2.0 * float(translate_y) / H
        pad = {"black": "zeros", "edge": "border", "reflection": "reflection"}[wrap]
        legacy = (center_x < 0 and center_y < 0 and skew_x == 0.0 and skew_y == 0.0
                  and scale_x == 1.0 and scale_y == 1.0)
        # The output->input map is built in PIXEL space: in = A_inv (out - c) + c - T, then expressed in
        # grid_sample's normalised coordinates. L9.39: it used to be built in normalised space, where x and y have
        # different scales on a non-square frame, so a rotation sheared the picture. For square frames this is
        # exactly the previous matrix, so existing results do not change.
        if legacy:
            s = 1.0 / max(1e-6, float(scale))
            a_inv = [[s * float(cos), s * float(sin)], [-s * float(sin), s * float(cos)]]
            c = ((W - 1) * 0.5, (H - 1) * 0.5)
        else:
            sx = 1.0 / max(1e-6, float(scale) * float(scale_x))
            sy = 1.0 / max(1e-6, float(scale) * float(scale_y))
            skx = float(skew_x) * 3.14159265 / 180.0
            sky = float(skew_y) * 3.14159265 / 180.0
            tan_x, tan_y = float(torch.tan(torch.tensor(skx))), float(torch.tan(torch.tensor(sky)))
            cf, sf = float(cos), float(sin)
            a_inv = [[sx * cf + tan_y * sx * sf, sx * sf], [sy * sf + tan_x * sy * cf, sy * cf]]
            # a centre given in pixel-edge coordinates is pixel-centre cx - 0.5 (what the old formula meant)
            c = (float(center_x) - 0.5 if center_x >= 0 else (W - 1) * 0.5,
                 float(center_y) - 0.5 if center_y >= 0 else (H - 1) * 0.5)
        mode = filter if filter in ("nearest", "bilinear", "bicubic") else "bilinear"
        m = torch.tensor([[a_inv[0][0], a_inv[0][1], 0.0], [a_inv[1][0], a_inv[1][1], 0.0], [0.0, 0.0, 1.0]],
                         dtype=torch.float64)
        to_c = torch.tensor([[1.0, 0, -c[0]], [0, 1.0, -c[1]], [0, 0, 1.0]], dtype=torch.float64)
        back = torch.tensor([[1.0, 0, c[0] - float(translate_x)], [0, 1.0, c[1] - float(translate_y)],
                             [0, 0, 1.0]], dtype=torch.float64)
        px_map = back @ m @ to_c                                   # out_px -> in_px
        if invert:
            px_map = torch.linalg.inv(px_map)
        d = torch.tensor([[W * 0.5, 0, (W - 1) * 0.5], [0, H * 0.5, (H - 1) * 0.5], [0, 0, 1.0]],
                         dtype=torch.float64)                      # normalised -> pixel (align_corners=False)
        theta = (torch.linalg.inv(d) @ px_map @ d)[:2].to(x.dtype).unsqueeze(0).repeat(B, 1, 1)
        grid = F.affine_grid(theta, x.shape, align_corners=False)
        out = F.grid_sample(x, grid.to(x.dtype), mode=mode, padding_mode=pad, align_corners=False)
        return (out.permute(0, 2, 3, 1).contiguous(),)


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
        out = rgb + (rgb - blurred) * float(amount)
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
        return (_join(out, alpha),)


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
        }, "optional": {
            "extended_pattern": (("off", "radial", "diagonal", "checkerboard"), {
                "default": "off",
                "tooltip": "When off, only horizontal/vertical (legacy). Otherwise overrides direction."}),
        }}

    def execute(self, width, height, direction, start, end, extended_pattern="off"):
        W, H = int(width), int(height)
        if extended_pattern == "off":
            if direction == "horizontal":
                t = torch.linspace(float(start), float(end), W).view(1, 1, W, 1)
                out = t.repeat(1, H, 1, 3)
            else:
                t = torch.linspace(float(start), float(end), H).view(1, H, 1, 1)
                out = t.repeat(1, 1, W, 3)
            return (out.clamp(0, 1),)
        y = torch.linspace(0, 1, H).view(-1, 1).expand(H, W)
        x = torch.linspace(0, 1, W).view(1, -1).expand(H, W)
        if extended_pattern == "horizontal":
            ramp = x
        elif extended_pattern == "vertical":
            ramp = y
        elif extended_pattern == "diagonal":
            ramp = (x + y) * 0.5
        elif extended_pattern == "radial":
            cx, cy = W * 0.5, H * 0.5
            yy = torch.arange(H, dtype=torch.float32).view(-1, 1) - cy
            xx = torch.arange(W, dtype=torch.float32).view(1, -1) - cx
            dist = torch.sqrt(xx ** 2 + yy ** 2)
            ramp = (dist / dist.max().clamp(min=1e-6)).clamp(0, 1)
        else:  # checkerboard
            cs = max(1, min(W, H) // 8)
            ramp = ((x * W // cs) % 2 + (y * H // cs) % 2) % 2
        ramp = float(start) + ramp * (float(end) - float(start))
        out = ramp.unsqueeze(0).unsqueeze(-1).repeat(1, 1, 1, 3)
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
