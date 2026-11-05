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


def reflect_pad(x: torch.Tensor, pads) -> torch.Tensor:
    """F.pad(mode="reflect"), but where the image side is not larger than its pad (mirror padding cannot run there
    and raised a PyTorch error) the edge is repeated instead. A22 L9.142. `pads` as in F.pad: last dim first."""
    import torch.nn.functional as F
    pads = tuple(int(p) for p in pads)
    ok = True
    for i in range(0, len(pads), 2):
        size = x.shape[-1 - i // 2]
        if max(pads[i], pads[i + 1]) >= size:
            ok = False
            break
    return F.pad(x, pads, mode="reflect" if ok else "replicate")


def check_frame_counts(n_a: int, n_b: int, what_a: str, what_b: str) -> None:
    """Two batches work together when their frame counts match or one side is a single frame (it is held on every
    frame). Anything else is explained here instead of a raw tensor broadcast error (A22 L9.137)."""
    n_a, n_b = int(n_a), int(n_b)
    if n_a != n_b and 1 not in (n_a, n_b):
        raise ValueError(f"{what_a} has {n_a} frames and {what_b} has {n_b}; give them the same number of frames, "
                         "or a single frame on one side.")
