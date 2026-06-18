"""STMap Lens Distortion — Nuke-style UV-map warping.

An STMap is an RGB IMAGE where R encodes the source U coordinate and G
encodes the source V coordinate, both in [0,1]. Applying an STMap to a
source image is a per-pixel lookup: `dst[x,y] = src[stmap.r[x,y], stmap.g[x,y]]`.

Nodes:
  - STMapApply: warp IMAGE through an STMap using bilinear/bicubic/nearest.
  - STMapInvert: numerically invert an STMap (so apply -> apply_inv ≈ identity).
  - STMapIdentity: build an identity STMap at given resolution.

Float32 throughout. The IMAGE convention is (B,H,W,3) float32. We treat
the STMap's first 2 channels as (U,V). The V axis is "image-down" (V=0
at top, V=1 at bottom) which matches Nuke's stmap output convention.

torch.nn.functional.grid_sample expects normalized grid coordinates in
[-1,1] where (-1,-1) is the top-left corner. We convert STMap [0,1] to
[-1,1] directly.
"""
from __future__ import annotations

import torch
import torch.nn.functional as F

from ...utils.resilience import resilient


_INTERP_MODES = ("bilinear", "bicubic", "nearest")
_INV_TYPES = ("STMAP",)


def _uv_to_grid(uv: torch.Tensor) -> torch.Tensor:
    """(B,H,W,2) in [0,1] -> grid_sample grid in [-1,1] (V axis flip optional).

    Nuke's stmap convention: U increases right (0=left, 1=right), V
    increases down (0=top, 1=bottom). PyTorch grid_sample expects
    (-1,-1) at the top-left, (+1,+1) at the bottom-right, so a direct
    `2*uv - 1` mapping is correct.
    """
    return (uv * 2.0 - 1.0).clamp(-2.0, 2.0)


@resilient
class STMapApply:
    """Warp IMAGE through an STMap (Nuke-style UV-map lens distortion)."""

    DESCRIPTION = (
        "Apply a Nuke-style STMap to an IMAGE. The STMap is an RGB image "
        "where R=U, G=V in [0,1]. Each output pixel reads from the source "
        "at (R,G). Use this to apply lens distortion / un-distortion."
    )
    CATEGORY = "NukeMax/Lens"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    OUTPUT_TOOLTIPS = ("Warped IMAGE at the STMap resolution.",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "Source image to warp."}),
                "stmap": ("IMAGE", {"tooltip": "STMap. R=U, G=V in [0,1]. Output resolution matches the STMap."}),
                "interpolation": (_INTERP_MODES, {"default": "bilinear", "tooltip": "Sampling mode."}),
                "padding_mode": (("zeros", "border", "reflection"), {"default": "border",
                                                                      "tooltip": "Behaviour outside [0,1] UV range."}),
            },
            "optional": {
                "preserve_hdr": ("BOOLEAN", {"default": True,
                                              "tooltip": "Keep float32 unbounded (no clamp). Disable for SDR images."}),
            },
        }

    def execute(self, image: torch.Tensor, stmap: torch.Tensor,
                interpolation: str, padding_mode: str, preserve_hdr: bool = True):
        if image.ndim != 4 or stmap.ndim != 4:
            raise ValueError("STMapApply expects IMAGE tensors (B,H,W,3).")
        # Match batch sizes via broadcast.
        B = max(image.shape[0], stmap.shape[0])
        if image.shape[0] == 1 and B > 1:
            image = image.expand(B, -1, -1, -1)
        if stmap.shape[0] == 1 and B > 1:
            stmap = stmap.expand(B, -1, -1, -1)
        if image.shape[0] != stmap.shape[0]:
            raise ValueError(
                f"STMapApply: batch mismatch image={image.shape[0]} stmap={stmap.shape[0]}"
            )

        uv = stmap[..., :2]  # (B,H,W,2)
        grid = _uv_to_grid(uv)
        # grid_sample wants (B,C,H,W) input.
        src = image.permute(0, 3, 1, 2).contiguous().float()
        out = F.grid_sample(
            src, grid, mode=interpolation, padding_mode=padding_mode, align_corners=False,
        )
        out = out.permute(0, 2, 3, 1).contiguous()
        if not preserve_hdr:
            out = out.clamp(0.0, 1.0)
        return (out,)


@resilient
class STMapIdentity:
    """Build an identity STMap (no distortion) at a given resolution."""

    DESCRIPTION = "Build an identity STMap at the given resolution (R=U, G=V, B=0)."
    CATEGORY = "NukeMax/Lens"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("stmap",)
    OUTPUT_TOOLTIPS = ("Identity STMap as IMAGE (B,H,W,3) float32.",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "width": ("INT", {"default": 1920, "min": 16, "max": 16384, "tooltip": "STMap width in pixels."}),
                "height": ("INT", {"default": 1080, "min": 16, "max": 16384, "tooltip": "STMap height in pixels."}),
                "batch": ("INT", {"default": 1, "min": 1, "max": 1024, "tooltip": "Batch size."}),
            },
        }

    def execute(self, width: int, height: int, batch: int):
        ys = torch.linspace(0.0, 1.0, height, dtype=torch.float32)
        xs = torch.linspace(0.0, 1.0, width, dtype=torch.float32)
        vv, uu = torch.meshgrid(ys, xs, indexing="ij")
        stmap = torch.stack([uu, vv, torch.zeros_like(uu)], dim=-1)  # (H,W,3)
        stmap = stmap.unsqueeze(0).expand(batch, -1, -1, -1).contiguous()
        return (stmap,)


@resilient
class STMapInvert:
    """Numerically invert an STMap so that apply(inv) undoes apply(original).

    Approach: build a coordinate grid of the destination, then run
    apply(stmap) on the IDENTITY map to find where each source pixel
    lands. Scatter those landings back into a target grid. Holes are
    filled by an inpainting pass via grid-distance-based averaging.

    For typical lens distortion (smooth + monotonic in radial direction)
    this gives a result that's accurate to within ~0.5 pixel.
    """

    DESCRIPTION = (
        "Numerically invert an STMap (e.g. convert a distort-map into an "
        "undistort-map). Uses scatter+inpaint; accurate to ~sub-pixel for "
        "smooth lens warps. Output resolution matches input."
    )
    CATEGORY = "NukeMax/Lens"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("stmap_inv",)
    OUTPUT_TOOLTIPS = ("Inverted STMap.",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "stmap": ("IMAGE", {"tooltip": "STMap to invert."}),
                "fill_iterations": ("INT", {"default": 8, "min": 0, "max": 64,
                                              "tooltip": "Hole-fill passes after scatter."}),
            },
        }

    def execute(self, stmap: torch.Tensor, fill_iterations: int):
        if stmap.ndim != 4 or stmap.shape[-1] < 2:
            raise ValueError("STMapInvert expects an IMAGE (B,H,W,3) STMap.")
        B, H, W, _ = stmap.shape
        device = stmap.device

        # Destination identity coords in pixel space.
        ys = torch.arange(H, dtype=torch.float32, device=device)
        xs = torch.arange(W, dtype=torch.float32, device=device)
        vv, uu = torch.meshgrid(ys, xs, indexing="ij")  # (H,W)

        out = torch.zeros((B, H, W, 3), dtype=torch.float32, device=device)
        for b in range(B):
            # Source pixel that the STMap reads FROM for each output pixel.
            src_u = stmap[b, ..., 0] * (W - 1)  # (H,W) float
            src_v = stmap[b, ..., 1] * (H - 1)
            # Round to nearest integer source pixel, clamp to bounds.
            su = src_u.round().long().clamp_(0, W - 1)
            sv = src_v.round().long().clamp_(0, H - 1)
            # For each destination index (uu,vv), we know it reads from (su,sv).
            # For the INVERSE, we want: when output==destination, source is (uu,vv).
            # That is: at position (sv,su) in the inverse map, write (uu/W, vv/H).
            acc = torch.zeros((H, W, 2), dtype=torch.float32, device=device)
            count = torch.zeros((H, W), dtype=torch.float32, device=device)
            u_norm = uu / max(W - 1, 1)
            v_norm = vv / max(H - 1, 1)
            flat_idx = sv * W + su  # (H,W)
            acc_flat = acc.view(H * W, 2)
            count_flat = count.view(H * W)
            acc_flat.index_add_(0, flat_idx.view(-1),
                                torch.stack([u_norm, v_norm], dim=-1).view(-1, 2))
            count_flat.index_add_(0, flat_idx.view(-1), torch.ones(H * W, device=device))
            mask = (count > 0).float().unsqueeze(-1)
            inv_uv = torch.where(mask > 0, acc / count.clamp_min(1).unsqueeze(-1),
                                 torch.zeros_like(acc))

            # Hole fill via box-blur-of-known-pixels.
            if fill_iterations > 0:
                kn = torch.tensor([[1.0]], device=device).view(1, 1, 1, 1) * 0  # placeholder
                # Simple 3x3 averaging using filled neighbors.
                m = mask  # (H,W,1)
                uv = inv_uv  # (H,W,2)
                for _ in range(fill_iterations):
                    # pad and sum
                    uvm_chw = (uv * m).permute(2, 0, 1).unsqueeze(0)  # (1,2,H,W)
                    m_chw = m.permute(2, 0, 1).unsqueeze(0)  # (1,1,H,W)
                    k = torch.ones((1, 1, 3, 3), device=device)
                    uv_sum_u = F.conv2d(uvm_chw[:, 0:1], k, padding=1)
                    uv_sum_v = F.conv2d(uvm_chw[:, 1:2], k, padding=1)
                    m_sum = F.conv2d(m_chw, k, padding=1)
                    new_uv = torch.cat([uv_sum_u, uv_sum_v], dim=1) / m_sum.clamp_min(1e-6)
                    new_uv = new_uv.squeeze(0).permute(1, 2, 0)
                    new_m = (m_sum > 0).float().squeeze(0).permute(1, 2, 0)
                    # Keep already-known pixels; fill new ones from neighbors.
                    fill_mask = (m == 0).float() * new_m
                    uv = uv * m + new_uv * fill_mask
                    m = torch.clamp(m + fill_mask, 0.0, 1.0)
                inv_uv = uv

            out[b, ..., 0] = inv_uv[..., 0]
            out[b, ..., 1] = inv_uv[..., 1]
            out[b, ..., 2] = 0.0
        return (out,)


NODE_CLASS_MAPPINGS = {
    "NukeMax_STMapApply": STMapApply,
    "NukeMax_STMapInvert": STMapInvert,
    "NukeMax_STMapIdentity": STMapIdentity,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_STMapApply": "STMap Apply (Lens Distortion)",
    "NukeMax_STMapInvert": "STMap Invert",
    "NukeMax_STMapIdentity": "STMap Identity",
}
