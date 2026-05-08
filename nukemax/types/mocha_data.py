"""Mocha Pro data types.

Lightweight wrappers for tracking / lens / project data parsed from
Mocha Pro exports. Tensors hold per-frame keyframes; static data is
broadcast by repeating along the T axis at consumer time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import torch


@dataclass(frozen=True)
class MochaTrack:
    """Unified container for both corner-pin and transform tracks.

    kind:
      - "corner_pin": params is (T, 4, 2) — image-space xy of the four
        corners in this frame's plate, ordered TL, TR, BR, BL.
      - "transform":  params is (T, 6) — 2x3 affine row-major
        [a, b, tx, c, d, ty] mapping reference plate -> tracked plate.
    """
    kind: str
    params: torch.Tensor
    canvas_h: int
    canvas_w: int
    name: str = ""
    # Per-frame confidence in [0,1], shape (T,). Optional.
    confidence: Optional[torch.Tensor] = None

    def __post_init__(self) -> None:
        assert self.kind in ("corner_pin", "transform"), self.kind
        if self.kind == "corner_pin":
            assert self.params.ndim == 3 and self.params.shape[1:] == (4, 2)
        else:
            assert self.params.ndim == 2 and self.params.shape[1] == 6
        assert self.canvas_h > 0 and self.canvas_w > 0
        if self.confidence is not None:
            assert self.confidence.shape == (self.params.shape[0],)

    @property
    def T(self) -> int:
        return self.params.shape[0]

    def to(self, device) -> "MochaTrack":
        return MochaTrack(
            kind=self.kind,
            params=self.params.to(device),
            canvas_h=self.canvas_h,
            canvas_w=self.canvas_w,
            name=self.name,
            confidence=None if self.confidence is None else self.confidence.to(device),
        )


@dataclass(frozen=True)
class MochaLens:
    """Mocha Pro lens calibration.

    Brown-Conrady distortion with 2 radial + 2 tangential coefficients.
    fx, fy in pixels; cx, cy principal point in pixels.
    """
    fx: float
    fy: float
    cx: float
    cy: float
    k1: float
    k2: float
    p1: float
    p2: float
    canvas_h: int
    canvas_w: int

    def K(self) -> torch.Tensor:
        return torch.tensor(
            [[self.fx, 0.0, self.cx],
             [0.0, self.fy, self.cy],
             [0.0, 0.0, 1.0]],
            dtype=torch.float32,
        )

    def dist_coeffs(self) -> torch.Tensor:
        return torch.tensor([self.k1, self.k2, self.p1, self.p2, 0.0], dtype=torch.float32)


@dataclass(frozen=True)
class MochaProject:
    """Parsed Mocha .mocha project."""
    layers: tuple = ()           # (name, kind) tuples
    tracks: tuple = ()           # tuple[MochaTrack, ...]
    shapes: tuple = ()           # tuple[dict] shape descriptors
    lens: Optional[MochaLens] = None
    canvas_h: int = 0
    canvas_w: int = 0
    fps: float = 24.0
    raw_xml: str = ""            # original XML for power users
