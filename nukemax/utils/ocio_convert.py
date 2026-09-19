# PORTED FROM: ComfyUI-ACES-IO (third_party/ComfyUI-ACES-IO) by Bishoy Samaan
# PORTED FROM: ComfyUI-OCIO (third_party/ComfyUI-OCIO) by Slava Sexton
# Licence: MIT — OCIO colorspace conversion helper for I/O nodes.
"""Lazy PyOpenColorIO conversion used by EXR/video I/O reconciles."""
from __future__ import annotations

import os

import torch


def apply_colorspace_convert(
    image: torch.Tensor,
    src_colorspace: str,
    dst_colorspace: str,
    *,
    config_path: str = "",
) -> torch.Tensor:
    """Convert IMAGE batch between OCIO colorspaces. Empty src/dst = no-op."""
    src = (src_colorspace or "").strip()
    dst = (dst_colorspace or "").strip()
    if not src or not dst or src == dst:
        return image

    try:
        import PyOpenColorIO as OCIO  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "OCIO colorspace conversion needs PyOpenColorIO. Install with: pip install opencolorio"
        ) from exc

    from ..nodes.ocio import _apply_processor, _load_config

    path = (config_path or "").strip() or os.environ.get("OCIO") or "ocio://studio-config-latest"
    cfg = _load_config(path)
    try:
        processor = cfg.getProcessor(src, dst)
    except Exception as exc:
        raise ValueError(
            f"OCIO cannot convert {src!r} -> {dst!r} using config {path!r}: {exc}"
        ) from exc
    return _apply_processor(image, processor)
