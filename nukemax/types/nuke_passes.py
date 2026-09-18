# PORTED FROM: nuke-nodes-comfyui (third_party/nuke-nodes-comfyui) by Sumit Chatterjee
# Licence: MIT — direct copy authorised by owner; attribution retained.
"""Multi-pass EXR bundle — Nuke-style layer dictionary on a typed socket."""
from __future__ import annotations

from dataclasses import dataclass, field

import torch


@dataclass
class NukePasses:
    """All render passes from a multi-channel EXR, keyed by layer name.

    Each pass tensor is ``[H, W, C]`` float32. ``channel_names`` holds the
    raw OIIO channel names from the source file (for debug / pass-list text).
    """

    passes: dict[str, torch.Tensor]
    channel_names: tuple[str, ...] = ()
    source_path: str = ""

    @property
    def names(self) -> list[str]:
        return list(self.passes.keys())

    def get(self, name: str) -> torch.Tensor | None:
        return self.passes.get(name)

    @classmethod
    def empty(cls, message: str = "") -> "NukePasses":
        return cls(passes={}, channel_names=(), source_path=message)
