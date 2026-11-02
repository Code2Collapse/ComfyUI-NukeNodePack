"""NukeMax Read EXR Pro (owner Rev 3 Part 19.3 / 19.4; ledger L9.80 slice 1b).

A production EXR reader, not a typed path:
- an EXR picked from ComfyUI's input folder (uploaded with the node's own Upload button - the browser's image picker
  does not take .exr), a whole sequence from ONE of its frames, or an explicit server path held to the C2C media roots
  when other machines can reach this server (the same roots as Load Video (C2C), D0.35);
- the layer / channels to read (``auto`` = RGB(A), else a layer name; ``metadata`` lists them);
- scene-linear float, never clamped; the alpha as a MASK; every layer lazily as C2C_EXR_PASSES (NukeMax Shuffle Pass
  takes it); a header / layer / sequence report; a server-made preview (browsers do not decode EXR);
- re-runs when the file or a sequence member changes (size + modification time), cached otherwise.

The engine is the vendored C2C media core (nukemax/vendor/c2c_core, Apache-2.0): one EXR implementation for every C2C
pack. Original node, GPL-3.0-only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

import numpy as np
import torch

from ...vendor.c2c_core.video import budget as _budget
from ...vendor.c2c_core.video import exr as _exr
from ...vendor.c2c_core.video import media as _media
from ...vendor.c2c_core.video import reader as _reader
from ...vendor.c2c_core.video.passes import ExrPasses
from . import _media_roots as ROOTS

MODES = ("file (input folder)", "sequence (input folder)", "server path")
UPLOAD_SUBFOLDER = "nukemax_exr"
EXR_MAGIC = b"\x76\x2f\x31\x01"


def _folder_paths():
    import folder_paths  # type: ignore[import-not-found]
    return folder_paths


def input_exr_files(limit: int = 5000) -> list[str]:
    """EXR files in ComfyUI's input folder (and its subfolders, two levels), as input-relative names."""
    try:
        root = _folder_paths().get_input_directory()
    except Exception:  # noqa: BLE001 - outside ComfyUI (tests)
        return []
    out: list[str] = []
    base_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirs, files in os.walk(root):
        if dirpath.count(os.sep) - base_depth >= 2:
            dirs[:] = []
        for f in files:
            if f.lower().endswith(".exr"):
                out.append(os.path.relpath(os.path.join(dirpath, f), root).replace(os.sep, "/"))
                if len(out) >= limit:
                    return sorted(out)
    return sorted(out)


def resolve(mode: str, file: str, server_path: str) -> str:
    """The path to read, refused in words when it may not be read."""
    if mode == "server path":
        p = str(server_path or "").strip().strip('"')
        if not p:
            raise ValueError("NukeMax Read EXR Pro: mode 'server path' needs server_path (a file, a frame of a "
                             "sequence, or a pattern like shot.####.exr).")
        why = ROOTS.check_run_path(p)
        if why:
            raise ValueError(f"NukeMax Read EXR Pro: {why}")
        return p
    name = str(file or "").strip()
    if not name:
        raise ValueError("NukeMax Read EXR Pro: no file - upload an EXR (Upload EXR) or pick one from the list.")
    root = os.path.realpath(_folder_paths().get_input_directory())
    p = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath([root, p]) != root:
        raise ValueError("NukeMax Read EXR Pro: the file must be inside ComfyUI's input folder.")
    if not os.path.isfile(p):
        raise FileNotFoundError(f"NukeMax Read EXR Pro: {name} is not in the input folder - upload it again.")
    return p


def rel_to_input(text):
    """An absolute path inside ComfyUI's input folder as its input-relative name (outputs never carry the machine's
    paths for uploaded media); anything else unchanged."""
    if not isinstance(text, str) or not text:
        return text
    try:
        root = os.path.realpath(_folder_paths().get_input_directory())
        p = os.path.realpath(text)
        if os.path.commonpath([root, p]) == root:
            return os.path.relpath(p, root).replace(os.sep, "/")
    except Exception:  # noqa: BLE001 - not a path on this machine
        pass
    return text

def _rel_all(value):
    """rel_to_input over every absolute path in a nested dict / list (path, pattern, sequence directory, candidates):
    found live in L9.80 slice 3 - a sequence's folder still named this machine's input path."""
    if isinstance(value, dict):
        return {k: _rel_all(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_rel_all(v) for v in value]
    if isinstance(value, str) and os.path.isabs(value):
        return rel_to_input(value)
    return value


def fingerprint(path: str, mode: str) -> str:
    """Size + modification time of the file, or of every member of its sequence."""
    files = [path]
    if mode != "file (input folder)":
        try:
            from ...vendor.c2c_core.video.probe import resolve_sequence
            files = list(resolve_sequence(path)) or [path]
        except Exception:  # noqa: BLE001 - a single file / a missing one: its own stat
            files = [path]
    h = hashlib.sha1()
    for f in files:
        try:
            st = os.stat(f)
            h.update(f"{f}|{st.st_size}|{st.st_mtime_ns}".encode())
        except OSError:
            h.update(f"{f}|missing".encode())
    return h.hexdigest()


def safe_name(name: str) -> str:
    base = os.path.basename(str(name or "").replace("\\", "/"))
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "upload.exr"
    return base if base.lower().endswith(".exr") else base + ".exr"


def save_upload(name: str, data: bytes, overwrite: bool = False) -> dict:
    """One uploaded EXR: the batch rule for a batch of one (see save_batch)."""
    return save_batch([(name, data)], overwrite)


_FRAME = re.compile(r"^(.*?)([._-]?)(\d+)(\.exr)$", re.I)


def _versioned(fname: str, k: int) -> str:
    """name with version k BEFORE its frame number (shot.1001.exr -> shot_1.1001.exr), so a sequence stays one."""
    m = _FRAME.match(fname)
    if m and m.group(1):
        return f"{m.group(1)}_{k}{m.group(2)}{m.group(3)}{m.group(4)}"
    stem, ext = os.path.splitext(fname)
    return f"{stem}_{k}{ext}"


def save_batch(items: list[tuple[str, bytes]], overwrite: bool = False) -> dict:
    """Store several uploaded EXRs (a sequence) as ONE batch in input/nukemax_exr/. Identical files are reused. When any
    name is taken by a DIFFERENT file, the whole batch gets one version suffix before the frame number (never a mix of
    old and new frames, never a silent overwrite unless ``overwrite``)."""
    for name, data in items:
        if not data.startswith(EXR_MAGIC):
            raise ValueError(f"{name}: not an OpenEXR file (the first bytes are not the EXR magic number).")
    folder = os.path.join(_folder_paths().get_input_directory(), UPLOAD_SUBFOLDER)
    os.makedirs(folder, exist_ok=True)
    names = [safe_name(n) for n, _ in items]

    def clash(fname: str, data: bytes) -> bool:
        t = os.path.join(folder, fname)
        if not os.path.exists(t):
            return False
        with open(t, "rb") as f:
            return hashlib.sha256(f.read()).digest() != hashlib.sha256(data).digest()

    k = 0
    if not overwrite:
        while any(clash(_versioned(n, k) if k else n, d) for n, (_, d) in zip(names, items)):
            k += 1
    stored, reused = [], 0
    for n, (_, data) in zip(names, items):
        fname = _versioned(n, k) if k else n
        target = os.path.join(folder, fname)
        if os.path.exists(target) and not clash(fname, data):
            reused += 1
        else:
            tmp = target + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, target)
        stored.append(f"{UPLOAD_SUBFOLDER}/{fname}")
    status = f"{len(stored)} stored" + (f", {reused} already there" if reused else "") + \
        (f" - names were taken by other files, so this upload is version _{k}" if k else "")
    return {"names": stored, "name": stored[0] if stored else "", "status": status, "version": k}


def _preview(img: torch.Tensor) -> dict | None:
    """A display preview of the first frame (scene-linear -> clipped sRGB), saved to temp: browsers do not show EXR."""
    try:
        import folder_paths
        from PIL import Image
        a = img[0, ..., :3].clamp(min=0).cpu().numpy()
        srgb = np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(np.clip(a, 1e-8, None), 1 / 2.4) - 0.055)
        out = (np.clip(srgb, 0, 1) * 255 + 0.5).astype(np.uint8)
        folder = folder_paths.get_temp_directory()
        os.makedirs(folder, exist_ok=True)
        name = f"nukemax_exr_preview_{hashlib.sha1(out.tobytes()).hexdigest()[:12]}.png"
        Image.fromarray(out).save(os.path.join(folder, name))
        return {"filename": name, "subfolder": "", "type": "temp"}
    except Exception:  # noqa: BLE001 - a preview never fails the read
        return None


class NukeMax_ReadEXRPro:
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK", "C2C_EXR_PASSES", "STRING", "INT")
    RETURN_NAMES = ("image", "alpha", "passes", "metadata", "frame_count")
    OUTPUT_NODE = True
    DESCRIPTION = ("Reads an EXR - a file you upload or pick from the input folder, a whole sequence from one of its "
                   "frames, or a server path - as scene-linear float (never clamped), its alpha, every layer for "
                   "Shuffle Pass, and a header / layer report. The preview is made on the server.")

    @classmethod
    def INPUT_TYPES(cls):
        files = input_exr_files() or [""]
        return {
            "required": {
                "file": (files, {"tooltip": "An EXR in ComfyUI's input folder. Upload new ones with the node's "
                                            "Upload EXR button (sequences: select all their frames)."}),
                "mode": (list(MODES), {"default": MODES[0],
                                       "tooltip": "file: that one EXR. sequence: every frame of its sequence. server "
                                                  "path: server_path (held to the C2C media roots when this server "
                                                  "is reachable from other machines)."}),
                "layer": ("STRING", {"default": "auto", "tooltip": "auto = RGB(A); else a layer name from metadata "
                                                                   "(e.g. diffuse, specular, depth)."}),
                "frame_range": ("STRING", {"default": "", "tooltip": "Sequences: e.g. 1001-1100 (frame numbers). "
                                                                     "Empty = all."}),
            },
            "optional": {
                "server_path": ("STRING", {"default": "", "tooltip": "mode = server path: a file, a frame of a "
                                                                     "sequence or a pattern (shot.####.exr)."}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, file="", mode=MODES[0], layer="auto", frame_range="", server_path=""):
        try:
            return f"{fingerprint(resolve(mode, file, server_path), mode)}|{layer}|{frame_range}"
        except Exception as exc:  # noqa: BLE001 - execute says what is wrong
            return f"error|{exc}"

    def execute(self, file="", mode=MODES[0], layer="auto", frame_range="", server_path=""):
        path = resolve(mode, file, server_path)
        engine_mode = "single EXR" if mode == "file (input folder)" else ("EXR sequence" if mode.startswith("sequence")
                                                                           else "auto")
        handle, facts = _media.probe_media(path, mode=engine_mode, layer=str(layer or "auto").strip() or "auto")
        range_notes: list = []
        if str(frame_range or "").strip():
            handle, tl = _media.apply_timeline(handle, frame_range=str(frame_range).strip())
            range_notes = list(getattr(tl, "notes", ()) or ())
        n = len(handle)
        ch = 4 if handle.has_alpha else 3
        fits = _budget.frames_that_fit(int(handle.width), int(handle.height), ch, "float32")
        if n > fits:
            raise _budget.BudgetError("NukeMax Read EXR Pro: " + _budget.budget_error_message(
                asked=n, fits=fits, width=int(handle.width), height=int(handle.height), channels=ch, dtype="float32")
                + " Narrow frame_range.")
        arr = _reader.read(handle, list(range(n)), fmt="float32")
        frames = torch.from_numpy(np.ascontiguousarray(arr))
        image = frames[..., :3].contiguous()
        alpha = frames[..., 3].contiguous() if frames.shape[-1] > 3 else torch.ones(frames.shape[:3])
        info = getattr(facts, "image", None)
        layers = list(getattr(info, "layers", ()) or ())
        passes = ExrPasses(handle, layers, layer_used=getattr(facts, "layer", "")) if getattr(facts, "is_exr", True) \
            else ExrPasses.empty()
        meta = {
            "path": path if mode == "server path" else str(file),
            "mode": mode, "frames": n, "size": [int(handle.width), int(handle.height)],
            "media": facts.to_dict() if mode == "server path" else _rel_all(facts.to_dict()),
            "header": getattr(info, "header", {}) if info is not None else {},
            "range": range_notes,
            "values": {"min": round(float(image.min()), 6), "max": round(float(image.max()), 6),
                       "above_1": bool(float(image.max()) > 1.0)},
        }
        prev = _preview(image)
        out = (image, alpha, passes, json.dumps(meta, indent=2, default=str), n)
        return {"ui": {"images": [prev]} if prev else {}, "result": out}


NODE_CLASS_MAPPINGS = {"NukeMax_ReadEXRPro": NukeMax_ReadEXRPro}
NODE_DISPLAY_NAME_MAPPINGS = {"NukeMax_ReadEXRPro": "NukeMax Read EXR Pro"}


def _register_routes():
    """POST /nukemax/media/upload (multipart 'file', optional 'overwrite'): one EXR into input/nukemax_exr/.
    GET /nukemax/media/exr_files: the input folder's EXR list (the node's refresh)."""
    try:
        from aiohttp import web
        from server import PromptServer  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - outside ComfyUI
        return
    server = getattr(PromptServer, "instance", None)
    if server is None:                                  # imported without a running server (tests, tools)
        return
    routes = server.routes

    @routes.post("/nukemax/media/upload")
    async def _upload(request):
        try:
            reader = await request.multipart()
            items, overwrite = [], False
            limit = int(os.environ.get("NUKEMAX_UPLOAD_MAX_MB", "4096")) * 1024 * 1024
            async for part in reader:
                if part.name == "file":                      # one or many (every frame of a sequence)
                    name = part.filename or "upload.exr"
                    chunks, size = [], 0
                    while True:
                        c = await part.read_chunk(1 << 20)
                        if not c:
                            break
                        size += len(c)
                        if size > limit:
                            return web.json_response({"error": f"{name} is larger than the upload limit "
                                                               f"(NUKEMAX_UPLOAD_MAX_MB)."}, status=413)
                        chunks.append(c)
                    items.append((name, b"".join(chunks)))
                elif part.name == "overwrite":
                    overwrite = (await part.text()).strip().lower() in ("1", "true", "yes")
            if not items:
                return web.json_response({"error": "no file in the upload."}, status=400)
            return web.json_response(save_batch(items, overwrite))
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

    @routes.get("/nukemax/media/exr_files")
    async def _files(request):
        return web.json_response({"files": input_exr_files()})


_register_routes()
