"""Mocha Pro support nodes.

Six features:
  1. CornerPin tracking import (.nk corner-pin or ASCII export).
  2. Transform tracking import (.nk Transform/Tracker4 or ASCII).
  3. Shape / roto import as MASK.
  4. Stabilization (invert tracking and apply to plate).
  5. Lens distortion import (k1,k2,p1,p2 + intrinsics) + apply/remove.
  6. Raw .mocha project parser.

Plus a generic "apply tracking" warp node usable for screen replacement.
"""
from __future__ import annotations

import logging
import math
import os
import re
from typing import Optional

import torch
import torch.nn.functional as F

from ...types import MochaTrack, MochaLens, MochaProject, RotoShape
from ...core import splines
from ...utils.resilience import resilient
from . import parsers as P

log = logging.getLogger("nukemax.mocha")


# -----------------------------------------------------------------------
# Path helpers — accept absolute path, or a filename under ComfyUI/input
# (subdir "mocha/" by default, where the upload route stores files).
# -----------------------------------------------------------------------
def _input_dir() -> str:
    try:
        import folder_paths  # type: ignore
        return folder_paths.get_input_directory()
    except Exception:
        # Fallback: ComfyUI/input relative to working dir
        return os.path.abspath(os.path.join(os.getcwd(), "input"))


def _resolve_path(p: str) -> str:
    """Resolve an input path: accept absolute, or a bare filename living under
    ComfyUI/input/mocha/ (where the upload endpoint stores files)."""
    if not p:
        raise ValueError("file_path is empty — paste text or upload a .nk file")
    if os.path.isabs(p) and os.path.exists(p):
        return p
    base = _input_dir()
    for candidate in (
        os.path.join(base, "mocha", p),
        os.path.join(base, p),
        os.path.abspath(p),
    ):
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(
        f"could not locate {p!r}. Tried: ComfyUI/input/mocha/{p}, "
        f"ComfyUI/input/{p}, and absolute path. Use the Upload .nk button or paste the file text."
    )


# -----------------------------------------------------------------------
# Server route: POST /nukemax/mocha/upload
#   multipart with `file` -> writes to ComfyUI/input/mocha/<safe_name>
#   returns {"ok": True, "name": "...", "path": "/abs/path"}
# -----------------------------------------------------------------------
def _register_mocha_routes() -> None:
    try:
        from server import PromptServer  # type: ignore
        from aiohttp import web  # type: ignore
    except Exception:
        return
    routes = PromptServer.instance.routes

    @routes.post("/nukemax/mocha/upload")
    async def _upload(request):  # noqa: ANN001
        try:
            reader = await request.multipart()
            field = await reader.next()
            if field is None or field.name != "file":
                return web.json_response({"ok": False, "error": "missing 'file' field"}, status=400)
            raw_name = os.path.basename(field.filename or "mocha_upload.nk")
            safe = re.sub(r"[^A-Za-z0-9._\-]+", "_", raw_name)[:120] or "mocha_upload.nk"
            tgt_dir = os.path.join(_input_dir(), "mocha")
            os.makedirs(tgt_dir, exist_ok=True)
            tgt = os.path.join(tgt_dir, safe)
            # Avoid overwriting: append _1, _2 ... if needed.
            if os.path.exists(tgt):
                stem, ext = os.path.splitext(safe)
                i = 1
                while os.path.exists(os.path.join(tgt_dir, f"{stem}_{i}{ext}")):
                    i += 1
                safe = f"{stem}_{i}{ext}"
                tgt = os.path.join(tgt_dir, safe)
            size = 0
            with open(tgt, "wb") as f:
                while True:
                    chunk = await field.read_chunk(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > 50 * 1024 * 1024:  # 50 MB cap
                        f.close()
                        try:
                            os.remove(tgt)
                        except OSError:
                            pass
                        return web.json_response(
                            {"ok": False, "error": "file too large (max 50 MB)"}, status=413)
                    f.write(chunk)
            return web.json_response({"ok": True, "name": safe, "path": tgt, "bytes": size})
        except Exception as e:  # noqa: BLE001
            log.exception("mocha upload failed")
            return web.json_response({"ok": False, "error": str(e)}, status=400)


_register_mocha_routes()


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------
def _images_to_bchw(image: torch.Tensor) -> torch.Tensor:
    # Comfy IMAGE is (B,H,W,C) float32 in [0,1]
    if image.ndim != 4:
        raise ValueError(f"IMAGE must be (B,H,W,C); got shape {tuple(image.shape)}")
    return image.permute(0, 3, 1, 2).contiguous()


def _bchw_to_image(x: torch.Tensor) -> torch.Tensor:
    return x.permute(0, 2, 3, 1).contiguous().clamp(0.0, 1.0)


def _broadcast_T(tensor_T: torch.Tensor, B: int) -> torch.Tensor:
    """Broadcast a (T,...) tensor onto B frames by clamping the index."""
    T = tensor_T.shape[0]
    if T == B:
        return tensor_T
    if T == 1:
        return tensor_T.expand(B, *tensor_T.shape[1:]).contiguous()
    # Resample by nearest-frame index
    idx = torch.linspace(0, T - 1, B).round().long().clamp_(0, T - 1)
    return tensor_T[idx].contiguous()


def _affine_to_grid(affine_2x3_per_frame: torch.Tensor, H: int, W: int) -> torch.Tensor:
    """Convert per-frame 2x3 image-space affine matrices to PyTorch grid_sample sampling grid.

    PyTorch's affine_grid expects the matrix mapping NORMALIZED output
    coords [-1,1] to NORMALIZED input coords [-1,1]. We get
    image-space (px) matrix `M_img` mapping `dst_px -> src_px`. The
    conversion is M_norm = N · M_img · N^{-1}, where N maps norm->px.
    """
    B = affine_2x3_per_frame.shape[0]
    # N: norm -> px:  px = ((coord + 1) / 2) * (W or H) - 0.5
    # Or simpler: build a homogeneous norm matrix.
    # px = a*x + b*y + tx, where x,y in px coords.
    # Convert to grid: we want the affine such that given normalized
    # output (u,v) we sample input (u',v'). Using torch's affine_grid:
    grids = []
    for t in range(B):
        a, b, tx, c, d, ty = affine_2x3_per_frame[t].tolist()
        # Build transform that maps normalized output -> normalized input.
        # px_out = (u+1)/2 * W ; we want px_in = a*px_out + b*py_out + tx, ...
        # Then u_in = 2*px_in/W - 1.
        # Compose:
        # u_in = 2/W * (a*((u+1)/2*W) + b*((v+1)/2*H) + tx) - 1
        #      = a*(u+1) + (b*H/W)*(v+1) + 2*tx/W - 1
        #      = a*u + (b*H/W)*v + (a + b*H/W + 2*tx/W - 1)
        # v_in similarly.
        a_n = a
        b_n = b * H / W
        tx_n = a + b * H / W + 2 * tx / W - 1
        c_n = c * W / H
        d_n = d
        ty_n = c * W / H + d + 2 * ty / H - 1
        m = torch.tensor([[a_n, b_n, tx_n], [c_n, d_n, ty_n]], dtype=torch.float32)
        grid = F.affine_grid(m.unsqueeze(0), [1, 1, H, W], align_corners=False)
        grids.append(grid)
    return torch.cat(grids, dim=0)


def _corner_pin_to_homography(src_pts: torch.Tensor, dst_pts: torch.Tensor) -> torch.Tensor:
    """Solve the 3x3 homography mapping src 4 points to dst 4 points.
    Both are (4,2) tensors. Returns (3,3)."""
    A = []
    b = []
    for i in range(4):
        x, y = src_pts[i].tolist()
        X, Y = dst_pts[i].tolist()
        A.append([x, y, 1, 0, 0, 0, -X * x, -X * y])
        A.append([0, 0, 0, x, y, 1, -Y * x, -Y * y])
        b.append(X); b.append(Y)
    A_t = torch.tensor(A, dtype=torch.float64)
    b_t = torch.tensor(b, dtype=torch.float64)
    sol = torch.linalg.lstsq(A_t, b_t.unsqueeze(1)).solution.squeeze(1)
    H = torch.eye(3, dtype=torch.float64)
    H[0, 0] = sol[0]; H[0, 1] = sol[1]; H[0, 2] = sol[2]
    H[1, 0] = sol[3]; H[1, 1] = sol[4]; H[1, 2] = sol[5]
    H[2, 0] = sol[6]; H[2, 1] = sol[7]
    return H.float()


def _homography_warp(image_bchw: torch.Tensor, H_per_frame: torch.Tensor, out_h: int, out_w: int) -> torch.Tensor:
    """Apply per-frame 3x3 image-space homography (mapping dst px -> src px).

    Build a sampling grid by inverting H to get src->dst, but actually
    we want for each output pixel the source pixel; pass H mapping
    out->in. Uses a manual grid because torch.affine_grid is affine only.
    """
    B, C, _, _ = image_bchw.shape
    Bp = H_per_frame.shape[0]
    if Bp != B:
        # Broadcast
        H_per_frame = _broadcast_T(H_per_frame, B)
    yy, xx = torch.meshgrid(
        torch.arange(out_h, dtype=torch.float32),
        torch.arange(out_w, dtype=torch.float32),
        indexing="ij",
    )
    ones = torch.ones_like(xx)
    pts = torch.stack([xx, yy, ones], dim=-1)        # (Hout,Wout,3)
    out = []
    for t in range(B):
        H = H_per_frame[t]
        src = pts @ H.T                              # (Hout,Wout,3)
        src_x = src[..., 0] / src[..., 2].clamp(min=1e-6)
        src_y = src[..., 1] / src[..., 2].clamp(min=1e-6)
        # Normalize to [-1,1] for grid_sample
        in_h, in_w = image_bchw.shape[-2:]
        gx = 2 * src_x / max(in_w - 1, 1) - 1
        gy = 2 * src_y / max(in_h - 1, 1) - 1
        grid = torch.stack([gx, gy], dim=-1).unsqueeze(0)
        warped = F.grid_sample(
            image_bchw[t:t + 1].to(grid.dtype), grid.to(image_bchw.dtype),
            mode="bilinear", padding_mode="zeros", align_corners=False,
        )
        out.append(warped)
    return torch.cat(out, dim=0)


# -----------------------------------------------------------------------
# 1. Corner-pin tracking import
# -----------------------------------------------------------------------
@resilient
class MochaImportCornerPin:
    DESCRIPTION = "Load a Mocha Pro corner-pin tracking export (.nk Nuke or ASCII .txt) into a MOCHA_TRACK socket."
    CATEGORY = "NukeMax/Mocha"
    FUNCTION = "execute"
    RETURN_TYPES = ("MOCHA_TRACK",)
    RETURN_NAMES = ("track",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "file_path": ("STRING", {"default": "", "tooltip": "Absolute path to Mocha corner-pin export (.nk or .txt)."}),
            "canvas_width": ("INT", {"default": 1920, "min": 1, "max": 16384}),
            "canvas_height": ("INT", {"default": 1080, "min": 1, "max": 16384}),
            "name": ("STRING", {"default": "mocha_cp"}),
        }}

    def execute(self, file_path, canvas_width, canvas_height, name):
        track = P.parse_corner_pin(_resolve_path(file_path), int(canvas_width), int(canvas_height), name)
        return (track,)


# -----------------------------------------------------------------------
# 1b. Corner-pin — Paste / Upload variant
# -----------------------------------------------------------------------
@resilient
class MochaImportCornerPinPaste:
    DESCRIPTION = ("Same as Mocha Import Corner Pin, but accepts the .nk export pasted directly into the text box "
                   "OR uploaded via the Upload .nk button (file is saved under ComfyUI/input/mocha/).")
    CATEGORY = "NukeMax/Mocha"
    FUNCTION = "execute"
    RETURN_TYPES = ("MOCHA_TRACK",)
    RETURN_NAMES = ("track",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "nk_text": ("STRING", {"multiline": True, "default": "",
                                    "tooltip": "Paste the contents of the Mocha .nk corner-pin export here. "
                                               "Or use the Upload .nk button to populate uploaded_file."}),
            "uploaded_file": ("STRING", {"default": "",
                                          "tooltip": "Filename inside ComfyUI/input/mocha/ — set automatically by the Upload .nk button."}),
            "canvas_width": ("INT", {"default": 1920, "min": 1, "max": 16384}),
            "canvas_height": ("INT", {"default": 1080, "min": 1, "max": 16384}),
            "name": ("STRING", {"default": "mocha_cp"}),
        }}

    def execute(self, nk_text, uploaded_file, canvas_width, canvas_height, name):
        text = (nk_text or "").strip()
        hint_nk = False
        if not text and uploaded_file:
            path = _resolve_path(uploaded_file)
            with open(path, "rb") as f:
                text = f.read().decode("utf-8-sig", errors="replace")
            hint_nk = path.lower().endswith(".nk")
        if not text:
            raise ValueError("paste the .nk corner-pin export into nk_text, or upload a file")
        track = P.parse_corner_pin_text(text, int(canvas_width), int(canvas_height), name, hint_nk=hint_nk)
        return (track,)


# -----------------------------------------------------------------------
# 2. Transform tracking import
# -----------------------------------------------------------------------
@resilient
class MochaImportTransform:
    DESCRIPTION = "Load a Mocha Pro transform tracking export (.nk Transform/Tracker4 or ASCII frame/tx/ty/rot/sx/sy) as MOCHA_TRACK."
    CATEGORY = "NukeMax/Mocha"
    FUNCTION = "execute"
    RETURN_TYPES = ("MOCHA_TRACK",)
    RETURN_NAMES = ("track",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "file_path": ("STRING", {"default": ""}),
            "canvas_width": ("INT", {"default": 1920, "min": 1, "max": 16384}),
            "canvas_height": ("INT", {"default": 1080, "min": 1, "max": 16384}),
            "name": ("STRING", {"default": "mocha_xf"}),
        }}

    def execute(self, file_path, canvas_width, canvas_height, name):
        track = P.parse_transform(_resolve_path(file_path), int(canvas_width), int(canvas_height), name)
        return (track,)


# -----------------------------------------------------------------------
# 2b. Transform — Paste / Upload variant
# -----------------------------------------------------------------------
@resilient
class MochaImportTransformPaste:
    DESCRIPTION = ("Same as Mocha Import Transform, but accepts the .nk export pasted directly into the text box "
                   "OR uploaded via the Upload .nk button.")
    CATEGORY = "NukeMax/Mocha"
    FUNCTION = "execute"
    RETURN_TYPES = ("MOCHA_TRACK",)
    RETURN_NAMES = ("track",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "nk_text": ("STRING", {"multiline": True, "default": ""}),
            "uploaded_file": ("STRING", {"default": ""}),
            "canvas_width": ("INT", {"default": 1920, "min": 1, "max": 16384}),
            "canvas_height": ("INT", {"default": 1080, "min": 1, "max": 16384}),
            "name": ("STRING", {"default": "mocha_xf"}),
        }}

    def execute(self, nk_text, uploaded_file, canvas_width, canvas_height, name):
        text = (nk_text or "").strip()
        hint_nk = False
        if not text and uploaded_file:
            path = _resolve_path(uploaded_file)
            with open(path, "rb") as f:
                text = f.read().decode("utf-8-sig", errors="replace")
            hint_nk = path.lower().endswith(".nk")
        if not text:
            raise ValueError("paste the .nk transform export into nk_text, or upload a file")
        track = P.parse_transform_text(text, int(canvas_width), int(canvas_height), name, hint_nk=hint_nk)
        return (track,)


# -----------------------------------------------------------------------
# 3. Apply tracking (warp screen replacement)
# -----------------------------------------------------------------------
@resilient
class MochaApplyTracking:
    DESCRIPTION = "Warp the source IMAGE batch onto the tracked plane defined by a MOCHA_TRACK. Useful for screen replacements (corner-pin) or per-frame transform follow."
    CATEGORY = "NukeMax/Mocha"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "source": ("IMAGE", {"tooltip": "Source plate to warp INTO the tracked region."}),
            "track": ("MOCHA_TRACK",),
            "out_width": ("INT", {"default": 1920, "min": 1, "max": 16384}),
            "out_height": ("INT", {"default": 1080, "min": 1, "max": 16384}),
        }}

    def execute(self, source, track: MochaTrack, out_width, out_height):
        bchw = _images_to_bchw(source)
        B = bchw.shape[0]
        H, W = bchw.shape[-2:]
        out_h, out_w = int(out_height), int(out_width)
        if track.kind == "corner_pin":
            params = _broadcast_T(track.params, B)
            # Source corners in source-image px space:
            src_corners = torch.tensor([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], dtype=torch.float32)
            H_list = []
            for t in range(B):
                dst = params[t]                       # (4,2) target plate corners
                # Build inverse mapping (out px -> src px). Solve dst->src.
                Hmat = _corner_pin_to_homography(dst, src_corners)
                H_list.append(Hmat)
            H_stack = torch.stack(H_list, dim=0)
            warped = _homography_warp(bchw, H_stack, out_h, out_w)
            # Mask = 1 where warped pixel falls inside source bounds; rebuild via
            # rasterizing the destination quad polygon.
            poly_T = params  # (B,4,2) already
            mask = splines.rasterize_polygon_sdf(poly_T, out_h, out_w, feather=0.0, closed=True)
        else:
            params = _broadcast_T(track.params, B)
            grid = _affine_to_grid(params, out_h, out_w)
            warped = F.grid_sample(bchw.float(), grid, mode="bilinear", padding_mode="zeros", align_corners=False)
            mask = torch.ones(B, out_h, out_w, dtype=torch.float32)
        return (_bchw_to_image(warped), mask)


# -----------------------------------------------------------------------
# 4. Shape / roto import as MASK
# -----------------------------------------------------------------------
@resilient
class MochaImportShapesAsMask:
    DESCRIPTION = "Load a Mocha Pro Shape Data export (.nk) and rasterize all contained shapes to a per-frame MASK batch."
    CATEGORY = "NukeMax/Mocha"
    FUNCTION = "execute"
    RETURN_TYPES = ("MASK",)
    RETURN_NAMES = ("mask",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "file_path": ("STRING", {"default": ""}),
            "canvas_width": ("INT", {"default": 1920, "min": 1, "max": 16384}),
            "canvas_height": ("INT", {"default": 1080, "min": 1, "max": 16384}),
            "feather_pixels": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 256.0, "step": 0.5}),
            "combine": (("union", "intersect"), {"default": "union"}),
        }}

    def execute(self, file_path, canvas_width, canvas_height, feather_pixels, combine):
        shapes = P.parse_shape_nk(_resolve_path(file_path), int(canvas_width), int(canvas_height))
        return _rasterize_shapes(shapes, int(canvas_height), int(canvas_width),
                                  float(feather_pixels), combine)


# -----------------------------------------------------------------------
# 4b. Shape / roto — Paste / Upload variant (the one users actually want)
# -----------------------------------------------------------------------
@resilient
class MochaImportShapesAsMaskPaste:
    DESCRIPTION = ("Mocha shape → MASK. Paste the .nk shape export directly into nk_text, OR press "
                   "Upload .nk to drop in a file (stored under ComfyUI/input/mocha/). No absolute paths needed.")
    CATEGORY = "NukeMax/Mocha"
    FUNCTION = "execute"
    RETURN_TYPES = ("MASK", "INT", "INT")
    RETURN_NAMES = ("mask", "frame_count", "shape_count")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "nk_text": ("STRING", {"multiline": True, "default": "",
                                    "tooltip": "Paste the Mocha shape .nk export here. Or click Upload .nk."}),
            "uploaded_file": ("STRING", {"default": "",
                                          "tooltip": "Filename inside ComfyUI/input/mocha/ — set by Upload .nk button."}),
            "canvas_width": ("INT", {"default": 1920, "min": 1, "max": 16384}),
            "canvas_height": ("INT", {"default": 1080, "min": 1, "max": 16384}),
            "feather_pixels": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 256.0, "step": 0.5}),
            "combine": (("union", "intersect"), {"default": "union"}),
        }}

    def execute(self, nk_text, uploaded_file, canvas_width, canvas_height, feather_pixels, combine):
        text = (nk_text or "").strip()
        if not text and uploaded_file:
            path = _resolve_path(uploaded_file)
            with open(path, "rb") as f:
                text = f.read().decode("utf-8-sig", errors="replace")
        if not text:
            raise ValueError("paste the .nk shape export into nk_text, or upload a file via the button")
        shapes = P.parse_shape_text(text, int(canvas_width), int(canvas_height))
        mask, = _rasterize_shapes(shapes, int(canvas_height), int(canvas_width),
                                   float(feather_pixels), combine)
        T = int(mask.shape[0])
        return (mask, T, len(shapes))


def _rasterize_shapes(shapes, canvas_h: int, canvas_w: int,
                      feather_pixels: float, combine: str):
    """Shared rasteriser for the file-path and paste variants."""
    masks: list[torch.Tensor] = []
    if not shapes:
        return (torch.zeros(1, canvas_h, canvas_w),)
    T_max = max(s["points_per_frame"].shape[0] for s in shapes)
    for s in shapes:
        poly = s["points_per_frame"]
        if poly.shape[0] < T_max:
            pad = poly[-1:].expand(T_max - poly.shape[0], *poly.shape[1:])
            poly = torch.cat([poly, pad], dim=0)
        m = splines.rasterize_polygon_sdf(
            poly, canvas_h, canvas_w,
            feather=feather_pixels, closed=True,
        )
        masks.append(m)
    stack = torch.stack(masks, dim=0)
    if combine == "union":
        combined = stack.amax(dim=0)
    else:
        combined = stack.amin(dim=0)
    return (combined,)


# -----------------------------------------------------------------------
# 5. Stabilization (invert track + apply)
# -----------------------------------------------------------------------
@resilient
class MochaInvertTrack:
    DESCRIPTION = "Invert a MOCHA_TRACK so applying it stabilizes the plate (locks the tracked plane)."
    CATEGORY = "NukeMax/Mocha"
    FUNCTION = "execute"
    RETURN_TYPES = ("MOCHA_TRACK",)
    RETURN_NAMES = ("track_inverse",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"track": ("MOCHA_TRACK",)}}

    def execute(self, track: MochaTrack):
        if track.kind == "corner_pin":
            T = track.T
            # Inverse = swap roles src<->dst by reflecting around frame 0
            ref = track.params[0:1].expand(T, -1, -1).contiguous()
            # New dst = ref, new src = original dst -> equivalent to mapping
            # tracked plate back to its first-frame position.
            new_params = ref + (ref - track.params)
            # Better: keep first frame as identity, propagate backwards via
            # direct substitution:
            new_params = track.params.clone()
            for t in range(T):
                new_params[t] = ref[t] + (ref[t] - track.params[t])
            return (MochaTrack(
                kind="corner_pin", params=new_params,
                canvas_h=track.canvas_h, canvas_w=track.canvas_w,
                name=track.name + "_inv",
                confidence=track.confidence,
            ),)
        # Transform: invert each 2x3 affine
        T = track.T
        new_params = torch.zeros_like(track.params)
        ref = track.params[0]
        ref_M = torch.tensor([[ref[0], ref[1], ref[2]], [ref[3], ref[4], ref[5]], [0, 0, 1]], dtype=torch.float32)
        for t in range(T):
            p = track.params[t]
            M = torch.tensor([[p[0], p[1], p[2]], [p[3], p[4], p[5]], [0, 0, 1]], dtype=torch.float32)
            try:
                Minv = torch.linalg.inv(M)
            except Exception:
                Minv = torch.eye(3)
            stab = ref_M @ Minv
            new_params[t] = torch.tensor([stab[0, 0], stab[0, 1], stab[0, 2], stab[1, 0], stab[1, 1], stab[1, 2]])
        return (MochaTrack(
            kind="transform", params=new_params,
            canvas_h=track.canvas_h, canvas_w=track.canvas_w,
            name=track.name + "_inv",
            confidence=track.confidence,
        ),)


# -----------------------------------------------------------------------
# 6. Lens distortion import + apply / remove
# -----------------------------------------------------------------------
@resilient
class MochaImportLens:
    DESCRIPTION = "Load a Mocha Pro lens calibration export (key/value .txt) into a MOCHA_LENS socket."
    CATEGORY = "NukeMax/Mocha"
    FUNCTION = "execute"
    RETURN_TYPES = ("MOCHA_LENS",)
    RETURN_NAMES = ("lens",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "file_path": ("STRING", {"default": ""}),
            "canvas_width": ("INT", {"default": 1920, "min": 1, "max": 16384}),
            "canvas_height": ("INT", {"default": 1080, "min": 1, "max": 16384}),
        }}

    def execute(self, file_path, canvas_width, canvas_height):
        lens = P.parse_lens(_resolve_path(file_path), int(canvas_width), int(canvas_height))
        return (lens,)


def _build_distortion_grid(lens: MochaLens, mode: str) -> torch.Tensor:
    """Return a (1,H,W,2) grid for grid_sample. mode='undistort' produces a
    grid that, when sampled from a distorted image, yields a corrected
    image. mode='distort' is the inverse (rare; iterative)."""
    H, W = lens.canvas_h, lens.canvas_w
    yy, xx = torch.meshgrid(
        torch.arange(H, dtype=torch.float32),
        torch.arange(W, dtype=torch.float32),
        indexing="ij",
    )
    # Normalize to camera coords
    x = (xx - lens.cx) / lens.fx
    y = (yy - lens.cy) / lens.fy
    if mode == "undistort":
        r2 = x * x + y * y
        radial = 1 + lens.k1 * r2 + lens.k2 * r2 * r2
        x_d = x * radial + 2 * lens.p1 * x * y + lens.p2 * (r2 + 2 * x * x)
        y_d = y * radial + lens.p1 * (r2 + 2 * y * y) + 2 * lens.p2 * x * y
    else:  # distort: iterative inverse
        x_d, y_d = x.clone(), y.clone()
        for _ in range(5):
            r2 = x_d * x_d + y_d * y_d
            radial = 1 + lens.k1 * r2 + lens.k2 * r2 * r2
            dx = 2 * lens.p1 * x_d * y_d + lens.p2 * (r2 + 2 * x_d * x_d)
            dy = lens.p1 * (r2 + 2 * y_d * y_d) + 2 * lens.p2 * x_d * y_d
            x_d = (x - dx) / radial
            y_d = (y - dy) / radial
    # Back to pixels and normalize for grid_sample
    src_x = x_d * lens.fx + lens.cx
    src_y = y_d * lens.fy + lens.cy
    gx = 2 * src_x / max(W - 1, 1) - 1
    gy = 2 * src_y / max(H - 1, 1) - 1
    return torch.stack([gx, gy], dim=-1).unsqueeze(0)


@resilient
class MochaApplyLens:
    DESCRIPTION = "Apply or remove Mocha-estimated lens distortion to an IMAGE batch (Brown-Conrady model)."
    CATEGORY = "NukeMax/Mocha"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "lens": ("MOCHA_LENS",),
            "mode": (("undistort", "distort"), {"default": "undistort", "tooltip": "undistort: remove lens warp. distort: re-introduce it (e.g. for re-rendering CG into a distorted plate)."}),
        }}

    def execute(self, image, lens: MochaLens, mode):
        bchw = _images_to_bchw(image)
        B, C, H, W = bchw.shape
        if (H, W) != (lens.canvas_h, lens.canvas_w):
            # Resize lens to match plate; assume principal point/focal scale linearly.
            sx = W / lens.canvas_w
            sy = H / lens.canvas_h
            lens = MochaLens(
                fx=lens.fx * sx, fy=lens.fy * sy,
                cx=lens.cx * sx, cy=lens.cy * sy,
                k1=lens.k1, k2=lens.k2, p1=lens.p1, p2=lens.p2,
                canvas_h=H, canvas_w=W,
            )
        grid = _build_distortion_grid(lens, mode)
        grid = grid.expand(B, -1, -1, -1).to(bchw.dtype)
        out = F.grid_sample(bchw, grid, mode="bilinear", padding_mode="zeros", align_corners=False)
        return (_bchw_to_image(out),)


# -----------------------------------------------------------------------
# 7. .mocha project parser
# -----------------------------------------------------------------------
@resilient
class MochaImportProject:
    DESCRIPTION = "Open a Mocha Pro .mocha project (zipped XML) and extract canvas size, fps, and a layer/shape/track summary. Use the dedicated import nodes for tracking/shape/lens data."
    CATEGORY = "NukeMax/Mocha"
    FUNCTION = "execute"
    RETURN_TYPES = ("MOCHA_PROJECT", "STRING", "INT", "INT", "FLOAT")
    RETURN_NAMES = ("project", "summary", "canvas_w", "canvas_h", "fps")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "file_path": ("STRING", {"default": "", "tooltip": "Absolute path to a .mocha project file."}),
        }}

    def execute(self, file_path):
        proj = P.parse_mocha_project(_resolve_path(file_path))
        lines = [
            f"canvas: {proj.canvas_w} x {proj.canvas_h}",
            f"fps: {proj.fps}",
            f"layers: {len(proj.layers)}",
        ]
        for name, kind in proj.layers[:50]:
            lines.append(f"  - {kind}: {name}")
        if len(proj.layers) > 50:
            lines.append(f"  ... (+{len(proj.layers) - 50} more)")
        summary = "\n".join(lines)
        return (proj, summary, proj.canvas_w, proj.canvas_h, proj.fps)


# -----------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------
NODE_CLASS_MAPPINGS = {
    "NukeMax_MochaImportCornerPin":         MochaImportCornerPin,
    "NukeMax_MochaImportCornerPinPaste":    MochaImportCornerPinPaste,
    "NukeMax_MochaImportTransform":         MochaImportTransform,
    "NukeMax_MochaImportTransformPaste":    MochaImportTransformPaste,
    "NukeMax_MochaApplyTracking":           MochaApplyTracking,
    "NukeMax_MochaImportShapesAsMask":      MochaImportShapesAsMask,
    "NukeMax_MochaImportShapesAsMaskPaste": MochaImportShapesAsMaskPaste,
    "NukeMax_MochaInvertTrack":             MochaInvertTrack,
    "NukeMax_MochaImportLens":              MochaImportLens,
    "NukeMax_MochaApplyLens":               MochaApplyLens,
    "NukeMax_MochaImportProject":           MochaImportProject,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_MochaImportCornerPin":         "Mocha — Import Corner Pin (file path)",
    "NukeMax_MochaImportCornerPinPaste":    "Mocha — Import Corner Pin (paste / upload)",
    "NukeMax_MochaImportTransform":         "Mocha — Import Transform (file path)",
    "NukeMax_MochaImportTransformPaste":    "Mocha — Import Transform (paste / upload)",
    "NukeMax_MochaApplyTracking":           "Mocha — Apply Tracking (Warp)",
    "NukeMax_MochaImportShapesAsMask":      "Mocha — Import Shapes → MASK (file path)",
    "NukeMax_MochaImportShapesAsMaskPaste": "Mocha — Import Shapes → MASK (paste / upload)",
    "NukeMax_MochaInvertTrack":             "Mocha — Invert Track (Stabilize)",
    "NukeMax_MochaImportLens":              "Mocha — Import Lens Calibration",
    "NukeMax_MochaApplyLens":               "Mocha — Apply / Remove Lens Distortion",
    "NukeMax_MochaImportProject":           "Mocha — Open .mocha Project",
}
