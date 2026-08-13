"""Iridas/Adobe `.cube` LUT parsing and sampling — clean-room, HDR-safe.

Written from the published .cube format description, not adapted from any
reference pack (`third_party/radiance`, the pack that also ships a LUT node,
is GPL-3.0 and cannot be copied here).

THE HDR PROBLEM THIS SOLVES
---------------------------
A 3D LUT is only *defined* over its domain, normally 0..1. Every LUT node the
reference packs ship clamps the sample coordinate into that domain, so a
specular at 8.0 and a specular at 80.0 both come out as whatever the LUT's
white corner holds — the highlight range is destroyed and nothing says so.

This module offers three explicit policies and always reports how many
samples fell outside:

* ``extrapolate`` (default) — sample at the domain edge, then continue along
  the LUT's own edge gradient. Smooth, monotonic, and the HDR range survives.
* ``clamp`` — the classic (lossy) behaviour, for matching Nuke's Vectorfield.
* ``passthrough`` — out-of-domain samples keep their input value untouched.

No policy clips the result to 0..1.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import torch

DOMAIN_POLICIES = ("extrapolate", "clamp", "passthrough")
INTERPOLATIONS = ("tetrahedral", "trilinear")


@dataclass
class Cube:
    """A parsed .cube LUT. `table` is [N,N,N,3] indexed [blue, green, red]."""

    table: torch.Tensor
    size: int
    dim: int                      # 1 for LUT_1D_SIZE, 3 for LUT_3D_SIZE
    domain_min: Tuple[float, float, float]
    domain_max: Tuple[float, float, float]
    title: str
    path: str
    validator: Tuple[int, int]    # (st_mtime_ns, st_size)
    _devices: Dict[str, torch.Tensor] = field(default_factory=dict, repr=False)

    def on(self, device: torch.device) -> torch.Tensor:
        key = str(device)
        if key not in self._devices:
            self._devices[key] = self.table.to(device)
        return self._devices[key]


_CACHE: Dict[str, Cube] = {}
_CACHE_LOCK = threading.RLock()
_CACHE_MAX = 16


def _validator(path: str) -> Tuple[int, int]:
    st = os.stat(path)
    return (st.st_mtime_ns, st.st_size)


def load_cube(path: str) -> Cube:
    """Parse a .cube file, caching on (mtime, size). Raises on anything odd."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"LUT file does not exist: {path}")
    v = _validator(path)
    with _CACHE_LOCK:
        hit = _CACHE.get(path)
        if hit is not None and hit.validator == v:
            return hit
    cube = _parse_cube(path, v)
    with _CACHE_LOCK:
        while len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[path] = cube
    return cube


def _parse_cube(path: str, validator: Tuple[int, int]) -> Cube:
    size = 0
    dim = 0
    title = ""
    dmin = [0.0, 0.0, 0.0]
    dmax = [1.0, 1.0, 1.0]
    rows: List[Tuple[float, float, float]] = []

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            head = line.split(None, 1)[0].upper()
            if head == "TITLE":
                title = line.split(None, 1)[1].strip().strip('"') if " " in line else ""
            elif head in ("LUT_3D_SIZE", "LUT_1D_SIZE"):
                try:
                    size = int(line.split()[1])
                except (IndexError, ValueError) as exc:
                    raise ValueError(f"{path}:{lineno}: malformed {head}: {line!r}") from exc
                dim = 3 if head == "LUT_3D_SIZE" else 1
            elif head in ("DOMAIN_MIN", "DOMAIN_MAX"):
                try:
                    vals = [float(x) for x in line.split()[1:4]]
                except ValueError as exc:
                    raise ValueError(f"{path}:{lineno}: malformed {head}: {line!r}") from exc
                if len(vals) != 3:
                    raise ValueError(f"{path}:{lineno}: {head} needs 3 values, got {len(vals)}")
                if head == "DOMAIN_MIN":
                    dmin = vals
                else:
                    dmax = vals
            elif head in ("LUT_IN_VIDEO_RANGE", "LUT_OUT_VIDEO_RANGE"):
                continue  # informational only
            else:
                parts = line.split()
                if len(parts) != 3:
                    raise ValueError(
                        f"{path}:{lineno}: expected 3 floats per data line, got {len(parts)}: {line!r}"
                    )
                try:
                    rows.append((float(parts[0]), float(parts[1]), float(parts[2])))
                except ValueError as exc:
                    raise ValueError(f"{path}:{lineno}: non-numeric data: {line!r}") from exc

    if dim == 0 or size <= 0:
        raise ValueError(
            f"{path}: no LUT_3D_SIZE or LUT_1D_SIZE found — this is not a valid .cube file"
        )
    if size < 2:
        raise ValueError(f"{path}: LUT size {size} is too small; need at least 2")
    expected = size ** 3 if dim == 3 else size
    if len(rows) != expected:
        raise ValueError(
            f"{path}: LUT size {size} (dim {dim}D) needs {expected} data rows, found {len(rows)}"
        )
    for i, (lo, hi) in enumerate(zip(dmin, dmax)):
        if hi <= lo:
            raise ValueError(
                f"{path}: DOMAIN_MAX[{i}]={hi} is not greater than DOMAIN_MIN[{i}]={lo}"
            )

    flat = torch.tensor(rows, dtype=torch.float32)
    if dim == 3:
        # .cube data order: red varies fastest -> reshape gives [blue, green, red].
        table = flat.reshape(size, size, size, 3).contiguous()
    else:
        # Promote a 1D LUT to a separable 3D table so one sampler serves both.
        r = flat[:, 0]
        g = flat[:, 1]
        b = flat[:, 2]
        table = torch.stack(
            torch.broadcast_tensors(
                r.view(1, 1, size), g.view(1, size, 1), b.view(size, 1, 1)
            ),
            dim=-1,
        ).contiguous()

    return Cube(table=table, size=size, dim=dim, domain_min=tuple(dmin),
                domain_max=tuple(dmax), title=title, path=path, validator=validator)


def _gather(table_flat: torch.Tensor, n: int, ri, gi, bi) -> torch.Tensor:
    """Fetch corners from a flat [N^3, 3] table given integer r/g/b indices."""
    return table_flat[(bi * n + gi) * n + ri]


def sample(cube: Cube, rgb: torch.Tensor, interpolation: str = "tetrahedral",
           domain_policy: str = "extrapolate") -> Tuple[torch.Tensor, float]:
    """Apply `cube` to an [..., 3] float tensor.

    Returns (result, fraction_of_samples_outside_the_domain). Never clips.
    """
    if interpolation not in INTERPOLATIONS:
        raise ValueError(
            f"unknown interpolation {interpolation!r}; expected one of {INTERPOLATIONS}"
        )
    if domain_policy not in DOMAIN_POLICIES:
        raise ValueError(
            f"unknown domain policy {domain_policy!r}; expected one of {DOMAIN_POLICIES}"
        )

    device = rgb.device
    n = cube.size
    table = cube.on(device)
    table_flat = table.reshape(-1, 3)

    dmin = torch.tensor(cube.domain_min, dtype=torch.float32, device=device)
    dmax = torch.tensor(cube.domain_max, dtype=torch.float32, device=device)

    flat = rgb.reshape(-1, 3).float()
    # Position in grid units, 0 .. n-1. May legitimately fall outside.
    coord = (flat - dmin) / (dmax - dmin) * (n - 1)
    outside = (coord < 0) | (coord > (n - 1))
    out_frac = float(outside.any(dim=-1).float().mean().item()) if flat.numel() else 0.0

    clamped = coord.clamp(0.0, float(n - 1))
    base = _interp(table_flat, n, clamped, interpolation)

    if out_frac > 0.0 and domain_policy != "clamp":
        over = coord - clamped                      # 0 inside, signed outside
        if domain_policy == "passthrough":
            keep = outside.any(dim=-1, keepdim=True)
            base = torch.where(keep, flat, base)
        else:                                       # extrapolate
            # First-order Taylor extension off the domain boundary. Each axis
            # contributes independently and every gradient is measured from
            # the ORIGINAL edge value, never from a partially extended one.
            result = base
            for axis in range(3):
                ov = over[:, axis]
                if not bool((ov != 0).any()):
                    continue
                # One grid step back INTO the domain along this axis, so
                # (base - inner) is the LUT's own gradient at the boundary.
                inner = clamped.clone()
                inner[:, axis] = inner[:, axis] - torch.sign(ov)
                inner = inner.clamp(0.0, float(n - 1))
                grad = base - _interp(table_flat, n, inner, interpolation)
                result = result + grad * ov.abs().unsqueeze(-1)
            base = result

    return base.reshape(rgb.shape), out_frac


def _interp(table_flat: torch.Tensor, n: int, coord: torch.Tensor,
            interpolation: str) -> torch.Tensor:
    """Sample at `coord` (already inside 0..n-1), [P,3] -> [P,3]."""
    i0 = coord.floor().clamp(0, n - 2).long()
    f = coord - i0.float()
    r0, g0, b0 = i0[:, 0], i0[:, 1], i0[:, 2]
    r1, g1, b1 = r0 + 1, g0 + 1, b0 + 1
    fr, fg, fb = f[:, 0:1], f[:, 1:2], f[:, 2:3]

    c000 = _gather(table_flat, n, r0, g0, b0)
    c100 = _gather(table_flat, n, r1, g0, b0)
    c010 = _gather(table_flat, n, r0, g1, b0)
    c001 = _gather(table_flat, n, r0, g0, b1)
    c110 = _gather(table_flat, n, r1, g1, b0)
    c101 = _gather(table_flat, n, r1, g0, b1)
    c011 = _gather(table_flat, n, r0, g1, b1)
    c111 = _gather(table_flat, n, r1, g1, b1)

    if interpolation == "trilinear":
        c00 = c000 * (1 - fr) + c100 * fr
        c01 = c001 * (1 - fr) + c101 * fr
        c10 = c010 * (1 - fr) + c110 * fr
        c11 = c011 * (1 - fr) + c111 * fr
        c0 = c00 * (1 - fg) + c10 * fg
        c1 = c01 * (1 - fg) + c11 * fg
        return c0 * (1 - fb) + c1 * fb

    # Tetrahedral (Kasson et al.): the unit cube splits into 6 tetrahedra
    # chosen by the ordering of the fractional coordinates. More accurate than
    # trilinear along the neutral axis, which is where grading LUTs live.
    out = torch.empty_like(c000)
    x, y, z = fr, fg, fb
    xg, yg, zg = x.squeeze(-1), y.squeeze(-1), z.squeeze(-1)

    m_xy = xg > yg
    m_yz = yg > zg
    m_xz = xg > zg

    # The six orderings of (x, y, z). Mutually exclusive and exhaustive:
    #   x>y>z | x>z>y | z>x>y | z>y>x | y>z>x | y>x>z
    cases = (
        (m_xy & m_yz,             c100 - c000, c110 - c100, c111 - c110),   # x>y>z
        (m_xy & ~m_yz & m_xz,     c100 - c000, c111 - c101, c101 - c100),   # x>z>y
        (m_xy & ~m_yz & ~m_xz,    c101 - c001, c111 - c101, c001 - c000),   # z>x>y
        (~m_xy & ~m_yz,           c111 - c011, c011 - c001, c001 - c000),   # z>y>x
        (~m_xy & m_yz & ~m_xz,    c111 - c011, c010 - c000, c011 - c010),   # y>z>x
        (~m_xy & m_yz & m_xz,     c110 - c010, c010 - c000, c111 - c110),   # y>x>z
    )
    filled = torch.zeros_like(xg, dtype=torch.bool)
    for mask, dx, dy, dz in cases:
        m = mask & ~filled
        if not bool(m.any()):
            continue
        val = c000 + dx * x + dy * y + dz * z
        out = torch.where(m.unsqueeze(-1), val, out)
        filled = filled | m
    if not bool(filled.all()):
        # Every (x,y,z) ordering is covered by the six cases above; if this
        # ever fires the mask algebra is wrong and silence would be worse.
        raise RuntimeError(
            "tetrahedral interpolation left "
            f"{int((~filled).sum())} samples unassigned — LUT sampler bug"
        )
    return out
