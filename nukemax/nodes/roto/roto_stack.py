"""Roto Shape Stack — multi-layer animated roto with per-layer blend modes.

Composites up to 6 ROTO_SHAPE inputs into a single MASK using Nuke-style
operations (union, sub, intersect, replace, add, max, min). Each layer
has its own opacity, feather override and invert toggle.

Outputs MASK at the canvas size of the first connected shape. All other
shapes are rasterized at the same canvas (their own canvas_h/canvas_w
are ignored if they differ — caller is responsible for matching sizes).

Float32 throughout — no 8-bit clamps on intermediate buffers (only the
final MASK is clamped to [0,1] to satisfy the MASK convention).
"""
from __future__ import annotations

from typing import Optional

import torch

from ...core import blur, splines
from ...types import RotoShape
from ...utils.resilience import resilient
from ..._is_changed_util import hash_args_and_kwargs


_OPS = ("union", "add", "max", "sub", "intersect", "min", "replace")
_MAX_LAYERS = 6


def _rasterize(shape: RotoShape, samples_per_segment: int, feather_override: float,
               canvas_h: int, canvas_w: int) -> torch.Tensor:
    """Rasterize a single shape onto a (T,H,W) float32 mask. Re-uses the
    shape's own canvas if it matches; otherwise scales the points.
    """
    if shape.canvas_h == canvas_h and shape.canvas_w == canvas_w:
        pts = shape.points
        hi = shape.handles_in
        ho = shape.handles_out
    else:
        sx = canvas_w / float(shape.canvas_w)
        sy = canvas_h / float(shape.canvas_h)
        s = torch.tensor([sx, sy], dtype=shape.points.dtype, device=shape.points.device)
        pts = shape.points * s
        hi = shape.handles_in * s
        ho = shape.handles_out * s
    polyline = splines.shape_to_polyline(
        pts, hi, ho, closed=shape.closed, samples_per_segment=samples_per_segment,
    )
    feather = feather_override if feather_override >= 0 else float(shape.feather.mean().item())
    return splines.rasterize_polygon_sdf(
        polyline, H=canvas_h, W=canvas_w, feather=feather, closed=shape.closed,
    )  # (T,H,W)


def _combine(acc: torch.Tensor, layer: torch.Tensor, op: str) -> torch.Tensor:
    """Combine accumulator with a new layer using a Nuke-style operation."""
    if op == "replace":
        return layer
    if op in ("union", "max"):
        return torch.maximum(acc, layer)
    if op == "add":
        return (acc + layer).clamp(0.0, 1.0)
    if op == "sub":
        return (acc - layer).clamp(0.0, 1.0)
    if op in ("intersect", "min"):
        return torch.minimum(acc, layer)
    return torch.maximum(acc, layer)  # default to union


@resilient
class RotoShapeStack:
    """Composite up to 6 ROTO_SHAPE inputs with per-layer blend modes."""

    DESCRIPTION = (
        "Composite up to 6 animated ROTO_SHAPE inputs into a single MASK. "
        "Per-layer opacity, feather override, invert, and Nuke-style "
        "blend op (union/add/max/sub/intersect/min/replace). All layers "
        "are rasterized onto the canvas of shape_1 (other shapes are "
        "scaled to match)."
    )
    CATEGORY = "NukeMax/Roto"
    FUNCTION = "execute"
    RETURN_TYPES = ("MASK",)
    RETURN_NAMES = ("mask",)
    OUTPUT_TOOLTIPS = ("Composited per-frame mask.",)


    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        req = {
            "shape_1": ("ROTO_SHAPE", {"tooltip": "Bottom layer — defines the output canvas."}),
            "samples_per_segment": ("INT", {"default": 16, "min": 2, "max": 128, "tooltip": "Bezier sampling density per segment."}),
            "global_blur_px": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 256.0, "step": 0.1, "tooltip": "Final Gaussian blur radius applied after compositing."}),
        }
        opt: dict = {}
        for i in range(1, _MAX_LAYERS + 1):
            if i > 1:
                opt[f"shape_{i}"] = ("ROTO_SHAPE", {"tooltip": f"Layer {i} (optional)."})
            opt[f"op_{i}"] = (_OPS, {"default": "union" if i > 1 else "replace",
                                     "tooltip": f"Blend op for layer {i}. Layer 1 is always 'replace'."})
            opt[f"opacity_{i}"] = ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01,
                                             "tooltip": f"Opacity multiplier on layer {i}."})
            opt[f"feather_{i}"] = ("FLOAT", {"default": -1.0, "min": -1.0, "max": 256.0, "step": 0.1,
                                             "tooltip": f"Feather override for layer {i}; <0 uses the shape's per-vertex mean."})
            opt[f"invert_{i}"] = ("BOOLEAN", {"default": False, "tooltip": f"Invert layer {i} (1 - mask) before combining."})
        return {"required": req, "optional": opt}

    def execute(self, shape_1: RotoShape, samples_per_segment: int, global_blur_px: float, **kwargs):
        canvas_h = int(shape_1.canvas_h)
        canvas_w = int(shape_1.canvas_w)

        acc: Optional[torch.Tensor] = None
        for i in range(1, _MAX_LAYERS + 1):
            shp = shape_1 if i == 1 else kwargs.get(f"shape_{i}")
            if shp is None:
                continue
            op = "replace" if i == 1 else str(kwargs.get(f"op_{i}", "union"))
            opacity = float(kwargs.get(f"opacity_{i}", 1.0))
            feather = float(kwargs.get(f"feather_{i}", -1.0))
            invert = bool(kwargs.get(f"invert_{i}", False))

            layer = _rasterize(shp, samples_per_segment, feather, canvas_h, canvas_w)
            if invert:
                layer = 1.0 - layer
            if opacity != 1.0:
                layer = layer * opacity

            if acc is None:
                acc = layer
            else:
                # Broadcast frame count if mismatched (use the longer one).
                if acc.shape[0] != layer.shape[0]:
                    T = max(acc.shape[0], layer.shape[0])
                    if acc.shape[0] == 1:
                        acc = acc.expand(T, -1, -1).contiguous()
                    if layer.shape[0] == 1:
                        layer = layer.expand(T, -1, -1).contiguous()
                acc = _combine(acc, layer, op)

        if acc is None:
            acc = torch.zeros((1, canvas_h, canvas_w), dtype=torch.float32)

        if global_blur_px > 0:
            b = acc.unsqueeze(1)
            acc = blur.gaussian_blur(b, global_blur_px / 3.0).squeeze(1)

        return (acc.clamp(0.0, 1.0),)


NODE_CLASS_MAPPINGS = {"NukeMax_RotoShapeStack": RotoShapeStack}
NODE_DISPLAY_NAME_MAPPINGS = {"NukeMax_RotoShapeStack": "Roto Shape Stack"}