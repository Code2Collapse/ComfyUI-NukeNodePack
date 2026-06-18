"""EXR Multi-channel Router — split arbitrary AOVs out of a multilayer EXR.

OpenEXR files routinely carry beauty + Z + N + P + motion + cryptomatte
as separate channels. The default LoadEXRMEC reads only R/G/B. This
node parses the full channel list and auto-routes common AOVs to
dedicated IMAGE / MASK / STRING sockets.

Heuristics (case-insensitive):
  beauty       <- {R,G,B}      -> IMAGE
  depth (Z)    <- Z | depth.Z  -> MASK (normalized to [0,1] of finite range)
  depth_raw    <- Z            -> IMAGE (raw float, single channel replicated)
  normal       <- N.x N.y N.z | normal.{x,y,z}  -> IMAGE
  position     <- P.x P.y P.z | position.{x,y,z} -> IMAGE
  motion       <- motion.x motion.y | vec.x vec.y -> IMAGE (z=0)
  custom_csv   <- user-supplied "albedo.R,albedo.G,albedo.B" -> IMAGE
  channels_csv <- full channel list as STRING

Float32 throughout. Single-channel "MASK" returns are also unbounded
float (depth_raw); the normalized depth MASK is the linear-rescale into
[0,1].
"""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import torch

from ...utils.resilience import resilient
from ..._is_changed_util import hash_args_and_kwargs


log = logging.getLogger("NukeMax.EXRRouter")


def _read_exr_channels(path: str, want: Sequence[str]) -> Tuple[Dict[str, np.ndarray], dict]:
    """Read the requested channel names (e.g. ['R','G','B','Z','N.x']).

    Returns ({name: (H,W) float32}, info_dict). Missing channels are
    omitted from the result; caller decides how to react.
    """
    try:
        import OpenEXR  # type: ignore[import-not-found]
        import Imath  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "EXR Channel Router requires OpenEXR+Imath. "
            "Install: `pip install OpenEXR Imath` (or use ComfyUI Manager)."
        ) from exc

    f = OpenEXR.InputFile(path)
    try:
        h = f.header()
        dw = h["dataWindow"]
        w = dw.max.x - dw.min.x + 1
        height = dw.max.y - dw.min.y + 1
        pt = Imath.PixelType(Imath.PixelType.FLOAT)
        all_channels = list(h["channels"].keys())
        out: Dict[str, np.ndarray] = {}
        for c in want:
            if c in h["channels"]:
                buf = f.channel(c, pt)
                arr = np.frombuffer(buf, dtype=np.float32).reshape(height, w)
                out[c] = arr
        info = {
            "width": w, "height": height,
            "all_channels": all_channels,
            "compression": str(h.get("compression", "?")),
        }
    finally:
        f.close()
    return out, info


def _channels_for_aov(all_channels: List[str], names: Sequence[str]) -> Optional[List[str]]:
    """Return the matching channel names in priority order or None."""
    lower = {c.lower(): c for c in all_channels}
    found: List[str] = []
    for n in names:
        if n.lower() in lower:
            found.append(lower[n.lower()])
    return found if len(found) == len(names) else None


def _stack_or_zero(chans: Dict[str, np.ndarray], names: List[str], h: int, w: int) -> np.ndarray:
    """Stack 3 channel arrays into (H,W,3); zero-fill missing."""
    parts = []
    for n in names:
        if n in chans:
            parts.append(chans[n])
        else:
            parts.append(np.zeros((h, w), dtype=np.float32))
    return np.stack(parts, axis=-1)


def _normalize_depth(z: np.ndarray) -> np.ndarray:
    finite = np.isfinite(z)
    if not finite.any():
        return np.zeros_like(z)
    zmin = float(z[finite].min())
    zmax = float(z[finite].max())
    if zmax - zmin < 1e-12:
        return np.zeros_like(z)
    out = (z - zmin) / (zmax - zmin)
    out[~finite] = 0.0
    return out.clip(0.0, 1.0)


@resilient
class EXRChannelRouter:
    """Load an EXR and split common AOVs (beauty, depth, normal, position, motion)."""

    DESCRIPTION = (
        "Load a multilayer EXR and auto-route common AOVs into separate "
        "outputs: beauty IMAGE, raw depth IMAGE, normalized depth MASK, "
        "normal IMAGE, position IMAGE, motion IMAGE, plus a custom CSV "
        "channel pick. Float32 scene-linear; never clamps."
    )
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "IMAGE", "MASK", "IMAGE", "IMAGE", "IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = (
        "beauty", "depth_raw", "depth_norm", "normal",
        "position", "motion", "custom", "info_json",
    )
    OUTPUT_TOOLTIPS = (
        "Beauty RGB.",
        "Raw depth (Z) replicated to RGB (float, unbounded).",
        "Linearly normalized depth MASK in [0,1] (for previews).",
        "Surface normal vector (N.x/N.y/N.z -> RGB).",
        "World position (P.x/P.y/P.z -> RGB).",
        "Motion vector (motion.x/motion.y -> RG, B=0).",
        "Custom CSV channels (3-channel) — empty if unspecified.",
        "JSON with full channel list and per-AOV resolution.",
    )


    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "file_path": ("STRING", {"default": "",
                                          "tooltip": "Absolute path to a multilayer EXR."}),
            },
            "optional": {
                "custom_channels_csv": ("STRING", {
                    "default": "",
                    "tooltip": "Comma-separated channel names to pack into the 'custom' IMAGE (e.g. 'albedo.R,albedo.G,albedo.B').",
                }),
                "depth_channel": ("STRING", {
                    "default": "Z",
                    "tooltip": "Channel name to treat as depth (default 'Z').",
                }),
            },
        }

    def execute(self, file_path: str, custom_channels_csv: str = "", depth_channel: str = "Z"):
        if not file_path or not os.path.isfile(file_path):
            raise FileNotFoundError(f"EXR not found: {file_path!r}")

        # Build the channel wish-list.
        wishlist: List[str] = ["R", "G", "B", depth_channel,
                                "N.x", "N.y", "N.z", "normal.x", "normal.y", "normal.z",
                                "P.x", "P.y", "P.z", "position.x", "position.y", "position.z",
                                "motion.x", "motion.y", "vec.x", "vec.y"]
        custom_names = [c.strip() for c in custom_channels_csv.split(",") if c.strip()]
        wishlist += custom_names

        chans, info = _read_exr_channels(file_path, wishlist)
        H, W = int(info["height"]), int(info["width"])
        all_c = info["all_channels"]

        # Beauty.
        beauty = _stack_or_zero(chans, ["R", "G", "B"], H, W)

        # Depth.
        if depth_channel in chans:
            z = chans[depth_channel]
            depth_raw = np.stack([z, z, z], axis=-1)
            depth_norm = _normalize_depth(z)
        else:
            depth_raw = np.zeros((H, W, 3), dtype=np.float32)
            depth_norm = np.zeros((H, W), dtype=np.float32)

        # Normal — try N.x/N.y/N.z then normal.{x,y,z}.
        n_set = _channels_for_aov(all_c, ["N.x", "N.y", "N.z"]) or \
                _channels_for_aov(all_c, ["normal.x", "normal.y", "normal.z"])
        if n_set:
            normal = _stack_or_zero(chans, n_set, H, W)
        else:
            normal = np.zeros((H, W, 3), dtype=np.float32)

        # Position.
        p_set = _channels_for_aov(all_c, ["P.x", "P.y", "P.z"]) or \
                _channels_for_aov(all_c, ["position.x", "position.y", "position.z"])
        if p_set:
            position = _stack_or_zero(chans, p_set, H, W)
        else:
            position = np.zeros((H, W, 3), dtype=np.float32)

        # Motion (2-channel).
        m_set = _channels_for_aov(all_c, ["motion.x", "motion.y"]) or \
                _channels_for_aov(all_c, ["vec.x", "vec.y"])
        if m_set:
            mx = chans.get(m_set[0], np.zeros((H, W), dtype=np.float32))
            my = chans.get(m_set[1], np.zeros((H, W), dtype=np.float32))
            motion = np.stack([mx, my, np.zeros_like(mx)], axis=-1)
        else:
            motion = np.zeros((H, W, 3), dtype=np.float32)

        # Custom.
        if custom_names:
            present = [n for n in custom_names if n in chans]
            if len(present) >= 1:
                # Pad to 3 channels with zeros.
                while len(present) < 3:
                    present.append("__zero__")
                parts = []
                for n in present[:3]:
                    parts.append(chans[n] if n in chans else np.zeros((H, W), dtype=np.float32))
                custom = np.stack(parts, axis=-1)
            else:
                custom = np.zeros((H, W, 3), dtype=np.float32)
        else:
            custom = np.zeros((H, W, 3), dtype=np.float32)

        def _to_img(arr: np.ndarray) -> torch.Tensor:
            return torch.from_numpy(np.ascontiguousarray(arr)).unsqueeze(0).float()

        beauty_t = _to_img(beauty)
        depth_raw_t = _to_img(depth_raw)
        depth_norm_t = torch.from_numpy(np.ascontiguousarray(depth_norm)).unsqueeze(0).float()  # MASK (B,H,W)
        normal_t = _to_img(normal)
        position_t = _to_img(position)
        motion_t = _to_img(motion)
        custom_t = _to_img(custom)

        info_out = {
            "file": os.path.basename(file_path),
            "width": W, "height": H,
            "all_channels": all_c,
            "compression": info.get("compression"),
            "matched": {
                "beauty": ["R" in chans, "G" in chans, "B" in chans],
                "depth": depth_channel in chans,
                "normal": n_set,
                "position": p_set,
                "motion": m_set,
                "custom": custom_names,
            },
        }
        return (beauty_t, depth_raw_t, depth_norm_t, normal_t,
                position_t, motion_t, custom_t, json.dumps(info_out, indent=2))


NODE_CLASS_MAPPINGS = {"NukeMax_EXRChannelRouter": EXRChannelRouter}
NODE_DISPLAY_NAME_MAPPINGS = {"NukeMax_EXRChannelRouter": "EXR Channel Router"}