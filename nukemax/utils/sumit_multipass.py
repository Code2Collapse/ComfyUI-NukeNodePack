# PORTED FROM: nuke-nodes-comfyui (third_party/nuke-nodes-comfyui) by Sumit Chatterjee
# Licence: MIT — direct copy authorised by owner; attribution retained.
"""Multi-pass EXR helpers ported from nuke-nodes-comfyui ``multipass_nodes``."""
from __future__ import annotations

from collections import OrderedDict
from typing import Dict, List, Tuple

import numpy as np
import torch


def _require_oiio():
    try:
        import OpenImageIO as oiio  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "Multi-pass EXR loading needs OpenImageIO. Install with: pip install OpenImageIO"
        ) from exc
    return oiio

_SUFFIX_ORDER = {
    "R": 0, "G": 1, "B": 2, "A": 3,
    "X": 0, "Y": 1, "Z": 2, "W": 3,
    "r": 0, "g": 1, "b": 2, "a": 3,
    "x": 0, "y": 1, "z": 2, "w": 3,
}

_BEAUTY_CHANNELS = {"R", "G", "B", "A"}


def group_channels(channel_names: List[str]) -> "OrderedDict[str, List[Tuple[int, str]]]":
    """Group OIIO channel names by layer/pass."""
    groups: "OrderedDict[str, List[Tuple[int, str]]]" = OrderedDict()

    for i, name in enumerate(channel_names):
        if "." in name:
            layer, suffix = name.rsplit(".", 1)
        elif name in _BEAUTY_CHANNELS:
            layer, suffix = "RGBA", name
        else:
            layer, suffix = name, ""
        groups.setdefault(layer, []).append((i, suffix))

    for layer, chans in groups.items():
        chans.sort(key=lambda c: _SUFFIX_ORDER.get(c[1], 99))

    return groups


def read_all_passes(filepath: str) -> Tuple[Dict[str, np.ndarray], List[str]]:
    """Read every channel from an EXR and group by layer name."""
    oiio = _require_oiio()
    inp = oiio.ImageInput.open(filepath)
    if inp is None:
        raise RuntimeError(f"OIIO could not open: {filepath} ({oiio.geterror()})")

    spec = inp.spec()
    pixels = inp.read_image("float")
    inp.close()

    if pixels is None:
        raise RuntimeError(f"OIIO returned no pixel data for: {filepath}")

    all_pixels = np.array(pixels, dtype=np.float32).reshape(
        spec.height, spec.width, spec.nchannels
    )

    channel_names = list(spec.channelnames)
    groups = group_channels(channel_names)

    passes: Dict[str, np.ndarray] = {}
    for layer, chans in groups.items():
        indices = [c[0] for c in chans]
        passes[layer] = all_pixels[:, :, indices]

    return passes, channel_names


def passes_to_torch(passes: Dict[str, np.ndarray]) -> Dict[str, torch.Tensor]:
    """Convert numpy pass dict to torch tensors ``[H, W, C]``."""
    return {
        name: torch.from_numpy(np.ascontiguousarray(arr)).float()
        for name, arr in passes.items()
    }


def pass_to_image(arr: torch.Tensor, mode: str = "auto") -> torch.Tensor:
    """Convert a pass ``[H, W, C]`` to ComfyUI IMAGE ``[1, H, W, 3 or 4]``."""
    if arr.dim() == 2:
        arr = arr.unsqueeze(-1)
    H, W, C = arr.shape

    if mode == "single_to_rgb":
        out = arr[..., 0:1].repeat(1, 1, 3)
    elif mode == "rgb":
        if C == 1:
            out = arr.repeat(1, 1, 3)
        elif C == 2:
            zero = torch.zeros(H, W, 1, dtype=arr.dtype)
            out = torch.cat([arr, zero], dim=-1)
        else:
            out = arr[..., :3]
    elif mode == "rgba":
        if C == 1:
            rgb = arr.repeat(1, 1, 3)
            alpha = torch.ones(H, W, 1, dtype=arr.dtype)
            out = torch.cat([rgb, alpha], dim=-1)
        elif C == 2:
            zero = torch.zeros(H, W, 1, dtype=arr.dtype)
            alpha = torch.ones(H, W, 1, dtype=arr.dtype)
            out = torch.cat([arr, zero, alpha], dim=-1)
        elif C == 3:
            alpha = torch.ones(H, W, 1, dtype=arr.dtype)
            out = torch.cat([arr, alpha], dim=-1)
        else:
            out = arr[..., :4]
    else:
        if C == 1:
            out = arr.repeat(1, 1, 3)
        elif C == 2:
            zero = torch.zeros(H, W, 1, dtype=arr.dtype)
            out = torch.cat([arr, zero], dim=-1)
        elif C in (3, 4):
            out = arr
        else:
            out = arr[..., :4]

    return out.unsqueeze(0)


def format_pass_list(
    passes: Dict[str, torch.Tensor],
    raw_channels: List[str],
) -> str:
    """Build a human-readable listing of passes."""
    lines = [
        f"Total channels: {len(raw_channels)}",
        f"Passes: {len(passes)}",
        "",
    ]
    for name, tensor in passes.items():
        H, W, C = tensor.shape
        lines.append(f"  {name:<20} ({C}ch)  {W}x{H}")
    lines.append("")
    lines.append("Raw channel names:")
    lines.append("  " + ", ".join(raw_channels))
    return "\n".join(lines)


def pick_beauty_image(passes: Dict[str, torch.Tensor]) -> torch.Tensor:
    """Default beauty preview: prefer RGBA, else first pass, else placeholder."""
    if "RGBA" in passes:
        return pass_to_image(passes["RGBA"], mode="auto")
    if passes:
        return pass_to_image(next(iter(passes.values())), mode="auto")
    return torch.zeros((1, 512, 512, 3))
