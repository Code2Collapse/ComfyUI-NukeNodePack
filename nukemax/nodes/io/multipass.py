# PORTED FROM: nuke-nodes-comfyui (third_party/nuke-nodes-comfyui) by Sumit Chatterjee
# Licence: MIT — direct copy authorised by owner; attribution retained.
"""Multi-pass EXR read and shuffle nodes."""
from __future__ import annotations

import logging
import os

import torch

from ...types.nuke_passes import NukePasses
from ...utils.resilience import resilient
from ...utils.sumit_io import file_change_token, resolve_sequence_path
from ...utils.sumit_multipass import (
    format_pass_list,
    pass_to_image,
    passes_to_torch,
    pick_beauty_image,
    read_all_passes,
)
from ..._is_changed_util import hash_args_and_kwargs

logger = logging.getLogger(__name__)


@resilient
class NukeMax_ReadMultiPass:
    DESCRIPTION = "Load all EXR layers into a NUKE_PASSES bundle plus a beauty IMAGE preview and pass list."
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    RETURN_TYPES = ("NUKE_PASSES", "IMAGE", "STRING")
    RETURN_NAMES = ("passes", "beauty", "pass_list")

    @classmethod
    def IS_CHANGED(cls, file_path="", frame=1, load_as_sequence=True, **kwargs):
        if not file_path:
            return ""
        actual_path = resolve_sequence_path(
            file_path, frame, load_as_sequence=load_as_sequence
        )
        return file_change_token(actual_path)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "file_path": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": False,
                        "placeholder": "Path to EXR (supports %04d / #### patterns)",
                    },
                ),
                "frame": (
                    "INT",
                    {"default": 1, "min": -999999, "max": 999999, "step": 1},
                ),
            },
            "optional": {
                "load_as_sequence": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": "Expand %04d / #### patterns using the frame input",
                    },
                ),
                "print_pass_list": (
                    "BOOLEAN",
                    {
                        "default": True,
                        "tooltip": "Print the pass list to the console when executed",
                    },
                ),
            },
        }

    def execute(
        self,
        file_path,
        frame,
        load_as_sequence=True,
        print_pass_list=True,
    ):
        if not file_path:
            logger.warning("[NukeMax_ReadMultiPass] No file path specified")
            empty = torch.zeros((1, 512, 512, 3))
            return (NukePasses.empty(), empty, "No file loaded")

        actual_path = resolve_sequence_path(
            file_path, frame, load_as_sequence=load_as_sequence
        )

        if not os.path.exists(actual_path):
            logger.warning("[NukeMax_ReadMultiPass] File not found: %s", actual_path)
            empty = torch.zeros((1, 512, 512, 3))
            return (NukePasses.empty(actual_path), empty, f"File not found: {actual_path}")

        logger.info("[NukeMax_ReadMultiPass] Loading: %s", actual_path)

        try:
            passes_np, channel_names = read_all_passes(actual_path)
        except Exception as exc:
            logger.error("[NukeMax_ReadMultiPass] Error: %s", exc)
            empty = torch.zeros((1, 512, 512, 3))
            return (NukePasses.empty(actual_path), empty, f"Load error: {exc}")

        passes = passes_to_torch(passes_np)
        bundle = NukePasses(
            passes=passes,
            channel_names=tuple(channel_names),
            source_path=actual_path,
        )

        pass_list_str = format_pass_list(passes, channel_names)
        if print_pass_list:
            logger.info(
                "[NukeMax_ReadMultiPass] ===== Passes in %s =====",
                os.path.basename(actual_path),
            )
            logger.info(pass_list_str)
            logger.info("[NukeMax_ReadMultiPass] =============================================")

        beauty = pick_beauty_image(passes)
        return (bundle, beauty, pass_list_str)


@resilient
class NukeMax_ShufflePass:
    DESCRIPTION = "Extract one named pass from a NUKE_PASSES bundle as a standard IMAGE."
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "info")

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "passes": ("NUKE_PASSES",),
                "pass_name": (
                    "STRING",
                    {
                        "default": "RGBA",
                        "multiline": False,
                        "placeholder": "e.g. RGBA, diffuse, N, Z, crypto00",
                    },
                ),
            },
            "optional": {
                "channel_mode": (
                    ["auto", "rgb", "rgba", "single_to_rgb"],
                    {
                        "default": "auto",
                        "tooltip": (
                            "How to convert the pass to a 3/4-channel IMAGE:\n"
                            "  auto: 1ch->gray, 2ch->pad, 3/4ch->as-is, 5+->first 4\n"
                            "  rgb: force 3 channels\n"
                            "  rgba: force 4 channels (add alpha=1)\n"
                            "  single_to_rgb: always treat as grayscale"
                        ),
                    },
                ),
                "on_missing": (
                    ["black", "error"],
                    {
                        "default": "black",
                        "tooltip": "If the named pass is not found: return black or raise",
                    },
                ),
            },
        }

    def execute(self, passes, pass_name, channel_mode="auto", on_missing="black"):
        if not isinstance(passes, NukePasses) or not passes.passes:
            msg = "Empty passes bundle"
            logger.warning("[NukeMax_ShufflePass] %s", msg)
            return (torch.zeros((1, 512, 512, 3)), msg)

        name = pass_name.strip()
        pass_dict = passes.passes

        if name not in pass_dict:
            available = ", ".join(pass_dict.keys())
            msg = f"Pass '{name}' not found. Available: {available}"
            logger.warning("[NukeMax_ShufflePass] %s", msg)
            if on_missing == "error":
                raise ValueError(msg)
            first = next(iter(pass_dict.values()))
            H, W = first.shape[:2]
            return (torch.zeros((1, H, W, 3)), msg)

        arr = pass_dict[name]
        img = pass_to_image(arr, mode=channel_mode)

        C = arr.shape[-1]
        H, W = arr.shape[:2]
        info = (
            f"Pass '{name}': {C}ch, {W}x{H}, "
            f"range [{arr.min():.3f}, {arr.max():.3f}]"
        )
        logger.info("[NukeMax_ShufflePass] %s", info)

        return (img, info)


NODE_CLASS_MAPPINGS = {
    "NukeMax_ReadMultiPass": NukeMax_ReadMultiPass,
    "NukeMax_ShufflePass": NukeMax_ShufflePass,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_ReadMultiPass": "Read MultiPass (NukeMax)",
    "NukeMax_ShufflePass": "Shuffle Pass (NukeMax)",
}
