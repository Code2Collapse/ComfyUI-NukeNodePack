"""Cubic Bezier evaluation + signed-distance rasterization."""
from __future__ import annotations

import torch
import torch.nn.functional as F


def eval_cubic_bezier(p0: torch.Tensor, p1: torch.Tensor, p2: torch.Tensor, p3: torch.Tensor, n_samples: int) -> torch.Tensor:
    """Each input: (..., 2). Returns (..., n_samples, 2)."""
    t = torch.linspace(0, 1, n_samples, device=p0.device, dtype=p0.dtype)
    t = t.view(*([1] * (p0.ndim - 1)), n_samples, 1)
    omt = 1 - t
    p0e = p0.unsqueeze(-2)
    p1e = p1.unsqueeze(-2)
    p2e = p2.unsqueeze(-2)
    p3e = p3.unsqueeze(-2)
    return (omt ** 3) * p0e + 3 * (omt ** 2) * t * p1e + 3 * omt * (t ** 2) * p2e + (t ** 3) * p3e


def shape_to_polyline(
    points: torch.Tensor,         # (T,N,2)
    handles_in: torch.Tensor,     # (T,N,2)
    handles_out: torch.Tensor,    # (T,N,2)
    closed: bool,
    samples_per_segment: int = 16,
) -> torch.Tensor:
    """Returns polyline (T, N*samples_per_segment, 2)."""
    T, N, _ = points.shape
    if N < 2:
        return points.clone()
    next_idx = torch.arange(N, device=points.device)
    next_idx = (next_idx + 1) % N if closed else (next_idx + 1).clamp(max=N - 1)
    p0 = points
    p3 = points[:, next_idx, :]
    p1 = handles_out
    p2 = handles_in[:, next_idx, :]
    segs = eval_cubic_bezier(p0, p1, p2, p3, samples_per_segment)  # (T,N,S,2)
    if not closed:
        segs = segs[:, :-1]
    return segs.reshape(T, -1, 2)


def rasterize_polygon_sdf(
    polyline: torch.Tensor,    # (T, P, 2)
    H: int,
    W: int,
    feather: torch.Tensor | float = 0.0,  # (T,) or scalar pixels
    closed: bool = True,
) -> torch.Tensor:
    """Rasterize a polygon to a soft mask via signed-distance + raycast.

    Returns (T, H, W) in [0,1]. Inside = 1, feathered band around edge. Pixel (x, y) is sampled at the integer point
    (x, y); inside = even-odd crossings of a ray towards +x.

    L9.165 (A24, measured): same values as the original all-pixels-against-all-edges version
    (`_rasterize_polygon_sdf_bruteforce`, kept as the reference), at a fraction of the cost:
    - inside / outside: the same crossing test per ROW (one x per crossing edge, identical float expression), turned
      into per-pixel crossing counts with a difference array + cumulative sum: O(rows x edges + pixels);
    - distance: it only changes the result inside the feather band (|distance| < feather/2 for closed shapes, <
      feather for open strokes; outside it the clamp gives exactly 1 or 0), so each edge is evaluated only over its
      own box widened by that band, with the identical per-pixel formula, keeping the minimum. A pixel nearer than the
      band to some edge lies in that edge's box, so in-band values are exact; feather 0 needs no distance at all.
    """
    T, P, _ = polyline.shape
    device = polyline.device
    dtype = polyline.dtype
    out = torch.zeros(T, H, W, device=device, dtype=dtype)
    if P < 2 or H <= 0 or W <= 0:
        return out
    if closed:
        next_pts = polyline[:, torch.arange(P, device=device).roll(-1)]
        edges = torch.stack([polyline, next_pts], dim=2)  # (T,P,2,2)
    else:
        edges = torch.stack([polyline[:, :-1], polyline[:, 1:]], dim=2)
    a = edges[:, :, 0, :]   # (T,E,2)
    b = edges[:, :, 1, :]
    ab = b - a
    ab_len2 = (ab * ab).sum(-1).clamp_min(1e-12)  # (T,E)
    rows = torch.arange(H, device=device, dtype=dtype).unsqueeze(1)    # (H,1) = py
    xs = torch.arange(W, device=device, dtype=dtype)
    ys = torch.arange(H, device=device, dtype=dtype)

    for t in range(T):
        f = float(feather) if not isinstance(feather, torch.Tensor) else float(feather[t].item())
        a_t, b_t, ab_t, l2_t = a[t], b[t], ab[t], ab_len2[t]

        inside = None
        if closed:
            # identical crossing test to the reference, evaluated once per (row, edge)
            ay = a_t[:, 1].unsqueeze(0)
            by = b_t[:, 1].unsqueeze(0)
            ax = a_t[:, 0].unsqueeze(0)
            bx = b_t[:, 0].unsqueeze(0)
            cond_y = (ay > rows) != (by > rows)                              # (H,E)
            denom = (by - ay)
            denom_safe = torch.where(denom.abs() < 1e-12, torch.ones_like(denom), denom)
            x_at = ax + (rows - ay) * (bx - ax) / denom_safe                 # (H,E)
            # pixels px (integers 0..W-1) with px < x_at are px in [0, ceil(x_at) - 1]
            stop = torch.ceil(x_at).clamp(0, W).to(torch.int64)
            hit = cond_y & (stop > 0)
            diff = torch.zeros(H, W + 1, device=device, dtype=torch.int32)
            diff[:, 0] = hit.sum(dim=1).to(torch.int32)
            diff.scatter_add_(1, torch.where(hit, stop, torch.full_like(stop, W)),
                              -hit.to(torch.int32))
            counts = diff[:, :W].cumsum(dim=1)
            inside = (counts % 2 == 1)

        if closed and f <= 0:
            out[t] = inside.to(dtype)
            continue
        if not closed and f <= 0:
            continue                                                         # empty, as the reference

        band = (0.5 * f if closed else f) + 1.0                              # +1 px margin for the box rounding
        dmin2 = torch.full((H, W), float("inf"), device=device, dtype=dtype)
        lo = torch.minimum(a_t, b_t) - band
        hi = torch.maximum(a_t, b_t) + band
        x0s = lo[:, 0].floor().clamp(0, W - 1).to(torch.int64).tolist()
        x1s = hi[:, 0].ceil().clamp(0, W - 1).to(torch.int64).tolist()
        y0s = lo[:, 1].floor().clamp(0, H - 1).to(torch.int64).tolist()
        y1s = hi[:, 1].ceil().clamp(0, H - 1).to(torch.int64).tolist()
        hi_x = hi[:, 0].tolist()
        lo_x = lo[:, 0].tolist()
        hi_y = hi[:, 1].tolist()
        lo_y = lo[:, 1].tolist()
        for e in range(a_t.shape[0]):
            if hi_x[e] < 0 or lo_x[e] > W - 1 or hi_y[e] < 0 or lo_y[e] > H - 1:
                continue                                                     # band entirely off-canvas
            x0, x1, y0, y1 = x0s[e], x1s[e], y0s[e], y1s[e]
            sub = torch.stack(torch.meshgrid(ys[y0:y1 + 1], xs[x0:x1 + 1], indexing="ij")[::-1], dim=-1)
            pts = sub.reshape(-1, 2)                                         # (M,2) as (x,y), like the reference
            ap = pts - a_t[e]
            tparam = ((ap * ab_t[e]).sum(-1) / l2_t[e]).clamp(0, 1)
            closest = a_t[e] + tparam.unsqueeze(-1) * ab_t[e]
            d2 = ((pts - closest) ** 2).sum(-1).view(y1 - y0 + 1, x1 - x0 + 1)
            view = dmin2[y0:y1 + 1, x0:x1 + 1]
            torch.minimum(view, d2, out=view)
        min_d = dmin2.sqrt()
        if not closed:
            out[t] = (1.0 - (min_d / f).clamp(0, 1))
        else:
            signed = torch.where(inside, min_d, -min_d)
            out[t] = (signed / f + 0.5).clamp(0, 1)
    return out


def _rasterize_polygon_sdf_bruteforce(
    polyline: torch.Tensor,    # (T, P, 2)
    H: int,
    W: int,
    feather: torch.Tensor | float = 0.0,  # (T,) or scalar pixels
    closed: bool = True,
) -> torch.Tensor:
    """REFERENCE (the pre-L9.165 implementation, kept verbatim for the equality tests): every pixel against every
    edge, O(pixels x edges). 29-45 s per 1080p frame on CPU (docs/RUST_ACCELERATION_AUDIT.md).

    Rasterize a polygon to a soft mask via signed-distance + raycast.

    Returns (T, H, W) in [0,1]. Inside = 1, feathered band around edge.
    Vectorized across all polygon edges.
    """
    T, P, _ = polyline.shape
    device = polyline.device
    dtype = polyline.dtype
    # Build edges (T, E, 2, 2): start/end points per segment.
    if closed:
        next_pts = polyline[:, torch.arange(P, device=device).roll(-1)]
        edges = torch.stack([polyline, next_pts], dim=2)  # (T,P,2,2)
    else:
        edges = torch.stack([polyline[:, :-1], polyline[:, 1:]], dim=2)
    E = edges.shape[1]

    yy, xx = torch.meshgrid(
        torch.arange(H, device=device, dtype=dtype),
        torch.arange(W, device=device, dtype=dtype),
        indexing="ij",
    )
    pix = torch.stack([xx, yy], dim=-1)  # (H,W,2)
    pix_flat = pix.reshape(-1, 2)        # (HW, 2)

    a = edges[:, :, 0, :]  # (T,E,2)
    b = edges[:, :, 1, :]
    ab = b - a              # (T,E,2)
    ab_len2 = (ab * ab).sum(-1).clamp_min(1e-12)  # (T,E)

    # For memory: process pixels in chunks across H rows.
    out = torch.empty(T, H, W, device=device, dtype=dtype)
    chunk_rows = max(1, min(H, 65536 // max(W, 1) // max(E, 1)))
    for t in range(T):
        a_t = a[t]            # (E,2)
        b_t = b[t]
        ab_t = ab[t]
        ab_len2_t = ab_len2[t]
        for r0 in range(0, H, chunk_rows):
            r1 = min(H, r0 + chunk_rows)
            P_chunk = pix[r0:r1].reshape(-1, 2)        # (M,2)
            M = P_chunk.shape[0]
            ap = P_chunk.unsqueeze(1) - a_t.unsqueeze(0)    # (M,E,2)
            tparam = (ap * ab_t.unsqueeze(0)).sum(-1) / ab_len2_t.unsqueeze(0)
            tparam = tparam.clamp(0, 1)
            closest = a_t.unsqueeze(0) + tparam.unsqueeze(-1) * ab_t.unsqueeze(0)  # (M,E,2)
            d2 = ((P_chunk.unsqueeze(1) - closest) ** 2).sum(-1)                    # (M,E)
            min_d = d2.min(dim=1).values.sqrt()                                     # (M,)

            # Even-odd raycast for inside/outside via horizontal ray to +x.
            ay = a_t[:, 1].unsqueeze(0)
            by = b_t[:, 1].unsqueeze(0)
            ax = a_t[:, 0].unsqueeze(0)
            bx = b_t[:, 0].unsqueeze(0)
            py = P_chunk[:, 1].unsqueeze(1)
            px = P_chunk[:, 0].unsqueeze(1)
            cond_y = (ay > py) != (by > py)
            # x of edge at py: ax + (py-ay)*(bx-ax)/(by-ay)
            denom = (by - ay)
            denom_safe = torch.where(denom.abs() < 1e-12, torch.ones_like(denom), denom)
            x_at = ax + (py - ay) * (bx - ax) / denom_safe
            cross = cond_y & (px < x_at)
            inside = (cross.sum(dim=1) % 2 == 1)

            f = float(feather) if not isinstance(feather, torch.Tensor) else float(feather[t].item())
            if not closed:
                # Open polylines (Nuke parity): no fill, only a soft stroke
                # band of width ``f`` along the polyline. With f=0 the mask
                # is empty.
                if f <= 0:
                    m = torch.zeros_like(min_d)
                else:
                    m = (1.0 - (min_d / f).clamp(0, 1))
            elif f <= 0:
                m = inside.to(dtype)
            else:
                # Soft band of width f around the edge.
                signed = torch.where(inside, min_d, -min_d)
                m = (signed / f + 0.5).clamp(0, 1)
            out[t, r0:r1] = m.view(r1 - r0, W)
    return out
