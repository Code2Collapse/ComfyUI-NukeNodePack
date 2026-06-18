"""Tensor contract helpers for ComfyUI node inputs."""
from __future__ import annotations

import torch


def require_image_bhwc(tensor: torch.Tensor, name: str = "image") -> torch.Tensor:
    """Validate ComfyUI IMAGE tensor shape [B, H, W, C]."""
    if not isinstance(tensor, torch.Tensor) or tensor.ndim != 4:
        raise ValueError(
            f"{name} must be a 4D IMAGE tensor [B,H,W,C]; "
            f"got {type(tensor).__name__} shape {getattr(tensor, 'shape', None)}"
        )
    return tensor
