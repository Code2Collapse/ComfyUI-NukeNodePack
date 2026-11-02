"""NukeMax Read - the generic media reader (owner Rev 3 Part 19.8 / 19.9; ledger L9.80 slice 4a).

One node for stills, numbered sequences and video, on the vendored C2C media engine (the same engine as Read EXR Pro):
- EXR, DPX, TIFF, PNG, JPEG, HDR, TGA, BMP, WebP and the video containers PyAV opens (MOV / MP4 / MKV / AVI / MXF ...);
- a sequence detected from ONE representative frame, or a pattern (shot.####.exr, shot.%04d.dpx, shot.$F4.png);
- frame range with step (1001-1100, 1001-1100x2), a missing-frame policy (error / black / hold / nearest / skip), an
  out-of-range policy, a frame shift; the frame numbers out as a range string Write EXR Pro's mapping takes;
- optional OCIO conversion on read; the sound of a video (silence for stills / sequences);
- a contact sheet of the range on the node (sequences and video), a single preview for a still;
- upload (streamed to disk, content-checked) or the input-folder list, or a server path held to the C2C media roots;
- a change fingerprint (size + time of the file or of every frame of its sequence).
Original node, GPL-3.0-only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

import numpy as np
import torch

from ...vendor.c2c_core.video import budget as _budget
from ...vendor.c2c_core.video import media as _media
from ...vendor.c2c_core.video import reader as _reader
from ...vendor.c2c_core.video.audio import lazy_audio_for_handle
from ...vendor.c2c_core.video.passes import ExrPasses
from ...vendor.c2c_core.video.sequence import EDGE_POLICIES, MISSING_POLICIES
from . import _media_roots as ROOTS
from . import read_exr_pro as RP

SOURCES = ("input folder", "server path")
MODES = ("auto", "single frame", "sequence", "video")
UPLOAD_SUBFOLDER = "nukemax_media"
STILLS = (".exr", ".dpx", ".tif", ".tiff", ".png", ".jpg", ".jpeg", ".hdr", ".tga", ".bmp", ".webp")
VIDEOS = (".mov", ".mp4", ".m4v", ".mkv", ".webm", ".avi", ".mxf")
LINEAR = (".exr", ".hdr")                     # scene-linear sources: the preview applies the sRGB curve
NAME = "NukeMax Read"

# the first bytes of each format (None = the format has no magic number: the extension decides)
SIGNATURES: dict[str, tuple] = {
    ".exr": ((0, b"\x76\x2f\x31\x01"),), ".png": ((0, b"\x89PNG\r\n\x1a\n"),),
    ".jpg": ((0, b"\xff\xd8\xff"),), ".jpeg": ((0, b"\xff\xd8\xff"),),
    ".tif": ((0, b"II*\x00"), (0, b"MM\x00*"), (0, b"II+\x00"), (0, b"MM\x00+")),
    ".tiff": ((0, b"II*\x00"), (0, b"MM\x00*"), (0, b"II+\x00"), (0, b"MM\x00+")),
    ".dpx": ((0, b"SDPX"), (0, b"XPDS")), ".hdr": ((0, b"#?RADIANCE"), (0, b"#?RGBE")), ".bmp": ((0, b"BM"),),
    ".webp": ((8, b"WEBP"),), ".tga": None,
    ".mov": ((4, b"ftyp"), (4, b"moov"), (4, b"mdat"), (4, b"wide"), (4, b"free")),
    ".mp4": ((4, b"ftyp"),), ".m4v": ((4, b"ftyp"),), ".mkv": ((0, b"\x1a\x45\xdf\xa3"),),
    ".webm": ((0, b"\x1a\x45\xdf\xa3"),), ".avi": ((8, b"AVI "),), ".mxf": ((0, b"\x06\x0e\x2b\x34"),),
}


class ReadError(ValueError):
    """A refusal in plain words."""


# ------------------------------------------------------------------ files
def input_media_files(limit: int = 5000) -> list[str]:
    """Stills and videos in ComfyUI's input folder (two levels deep), input-relative."""
    try:
        root = RP._folder_paths().get_input_directory()
    except Exception:  # noqa: BLE001 - outside ComfyUI (tests)
        return []
    out: list[str] = []
    base = root.rstrip(os.sep).count(os.sep)
    exts = STILLS + VIDEOS
    for dirpath, dirs, files in os.walk(root):
        if dirpath.count(os.sep) - base >= 2:
            dirs[:] = []
        for f in files:
            if f.lower().endswith(exts):
                out.append(os.path.relpath(os.path.join(dirpath, f), root).replace(os.sep, "/"))
                if len(out) >= limit:
                    return sorted(out)
    return sorted(out)


def resolve(source: str, file: str, server_path: str) -> str:
    if source == "server path":
        p = str(server_path or "").strip().strip('"')
        if not p:
            raise ReadError(f"{NAME}: source 'server path' needs server_path (a file, a frame of a sequence, or a "
                            "pattern like shot.####.exr).")
        why = ROOTS.check_run_path(p)
        if why:
            raise ReadError(f"{NAME}: {why}")
        return p
    name = str(file or "").strip()
    if not name:
        raise ReadError(f"{NAME}: no file - upload one (Upload media) or pick one from the list.")
    root = os.path.realpath(RP._folder_paths().get_input_directory())
    p = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath([root, p]) != root:
        raise ReadError(f"{NAME}: the file must be inside ComfyUI's input folder.")
    if not os.path.isfile(p):
        raise FileNotFoundError(f"{NAME}: {name} is not in the input folder - upload it again.")
    return p


def engine_mode(mode: str, path: str) -> str:
    ext = os.path.splitext(re.sub(r"[#@]+|%0?\d*d|\$F\d*", "0", path))[1].lower()
    exr = ext == ".exr"
    if mode == "single frame":
        return "single EXR" if exr else "single image"
    if mode == "sequence":
        return "EXR sequence" if exr else "image sequence"
    if mode == "video":
        return "video file"
    return "auto"


def check_signature(name: str, head: bytes) -> None:
    ext = os.path.splitext(name)[1].lower()
    if ext not in SIGNATURES:
        raise ReadError(f"{name}: {ext or 'no extension'} is not a format {NAME} reads "
                        f"({', '.join(STILLS + VIDEOS)}).")
    sig = SIGNATURES[ext]
    if sig is not None and not any(head[o:o + len(m)] == m for o, m in sig):
        raise ReadError(f"{name}: the content is not {ext[1:].upper()} (its first bytes do not match).")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def store_uploads(parts: list[tuple[str, str]], overwrite: bool = False) -> dict:
    """Uploaded files already streamed to temporary files ([(name, tmp_path)]) -> input/nukemax_media/ as ONE batch:
    identical files reused, a name taken by a DIFFERENT file gives the whole batch one version before the frame
    number (a sequence stays one sequence), never a silent overwrite unless ``overwrite``. Temp files are removed."""
    folder = os.path.join(RP._folder_paths().get_input_directory(), UPLOAD_SUBFOLDER)
    try:
        for name, tmp in parts:
            with open(tmp, "rb") as f:
                check_signature(name, f.read(16))
        os.makedirs(folder, exist_ok=True)
        names = [safe_media_name(n) for n, _ in parts]
        hashes = [_sha256(t) for _, t in parts]

        def clash(fname: str, digest: str) -> bool:
            t = os.path.join(folder, fname)
            return os.path.exists(t) and _sha256(t) != digest

        k = 0
        if not overwrite:
            while any(clash(versioned(n, k) if k else n, d) for n, d in zip(names, hashes)):
                k += 1
        stored, reused = [], 0
        for n, d, (_, tmp) in zip(names, hashes, parts):
            fname = versioned(n, k) if k else n
            target = os.path.join(folder, fname)
            if os.path.exists(target) and not clash(fname, d):
                reused += 1
            else:
                os.replace(tmp, target)                       # same volume: atomic
            stored.append(f"{UPLOAD_SUBFOLDER}/{fname}")
    finally:
        for _, tmp in parts:
            if os.path.exists(tmp):
                os.remove(tmp)
    status = f"{len(stored)} stored" + (f", {reused} already there" if reused else "") + \
        (f" - names were taken by other files, so this upload is version _{k}" if k else "")
    return {"names": stored, "name": stored[0] if stored else "", "status": status, "version": k}


def safe_media_name(name: str) -> str:
    base = os.path.basename(str(name or "").replace("\\", "/"))
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or "upload"


_FRAME = re.compile(r"^(.*?)([._-]?)(\d+)(\.[A-Za-z0-9]+)$")


def versioned(fname: str, k: int) -> str:
    m = _FRAME.match(fname)
    if m and m.group(1):
        return f"{m.group(1)}_{k}{m.group(2)}{m.group(3)}{m.group(4)}"
    stem, ext = os.path.splitext(fname)
    return f"{stem}_{k}{ext}"


# ------------------------------------------------------------------ numbers + previews
def numbers_text(nums: list[int]) -> str:
    """1001,1002,1003,1005,1007 -> '1001-1003, 1005-1007x2' (Write EXR Pro's frame_numbers reads it back)."""
    out, i = [], 0
    while i < len(nums):
        j = i
        step = nums[i + 1] - nums[i] if i + 1 < len(nums) else 1
        while step > 0 and j + 1 < len(nums) and nums[j + 1] - nums[j] == step:
            j += 1
        if j == i:
            out.append(str(nums[i]))
        elif step == 1:
            out.append(f"{nums[i]}-{nums[j]}")
        else:
            out.append(f"{nums[i]}-{nums[j]}x{step}")
        i = j + 1
    return ", ".join(out)


def _display(a: np.ndarray, linear: bool) -> np.ndarray:
    a = np.clip(a, 0, None)
    if linear:
        a = np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(np.clip(a, 1e-8, None), 1 / 2.4) - 0.055)
    return (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)


def _font(size: int):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=size)            # Pillow >= 10.1: a scalable default face
    except TypeError:
        return ImageFont.load_default()


def contact_sheet(image: torch.Tensor, numbers: list[int], linear: bool, cells: int = 12, width: int = 240):
    """Up to ``cells`` frames spread over the range, each labelled with its frame number (19.9). Three columns and a
    large label: the node shows the sheet at about a third of its size, where a 10 px label was unreadable."""
    from PIL import Image, ImageDraw
    n = int(image.shape[0])
    picks = sorted({round(k * (n - 1) / max(1, min(cells, n) - 1)) for k in range(min(cells, n))}) if n > 1 else [0]
    h, w = int(image.shape[1]), int(image.shape[2])
    tw = width
    th = max(1, round(h * tw / max(1, w)))
    cols = min(3, len(picks))
    rows = -(-len(picks) // cols)
    pad, label = 6, 48
    font = _font(40)
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + label + pad) + pad), (18, 18, 22))
    draw = ImageDraw.Draw(sheet)
    for k, idx in enumerate(picks):
        tile = Image.fromarray(_display(image[idx, ..., :3].cpu().numpy(), linear)).resize((tw, th))
        x, y = pad + (k % cols) * (tw + pad), pad + (k // cols) * (th + label + pad)
        sheet.paste(tile, (x, y))
        draw.text((x + 4, y + th + 2), str(numbers[idx]) if idx < len(numbers) else str(idx), fill=(230, 230, 230),
                  font=font)
    return sheet


def _save_temp(img, tag: str) -> dict | None:
    try:
        import folder_paths
        folder = folder_paths.get_temp_directory()
        os.makedirs(folder, exist_ok=True)
        data = np.asarray(img).tobytes()
        name = f"nukemax_read_{tag}_{hashlib.sha1(data).hexdigest()[:12]}.png"
        img.save(os.path.join(folder, name))
        return {"filename": name, "subfolder": "", "type": "temp"}
    except Exception:  # noqa: BLE001 - a preview never fails the read
        return None


# ------------------------------------------------------------------ node
class NukeMax_Read:
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK", "C2C_EXR_PASSES", "AUDIO", "STRING", "STRING", "INT", "FLOAT")
    RETURN_NAMES = ("image", "alpha", "passes", "audio", "metadata", "frame_numbers", "frame_count", "fps")
    DESCRIPTION = ("Reads stills, numbered sequences and video (EXR, DPX, TIFF, PNG, JPEG, HDR, TGA, BMP, WebP, MOV, "
                   "MP4, MKV ...): a sequence from one frame or a pattern, frame range and step, missing-frame policy, "
                   "frame shift, OCIO on read, the video's sound, a contact sheet of the range.")

    @classmethod
    def INPUT_TYPES(cls):
        files = input_media_files() or [""]
        return {
            "required": {
                "file": (files, {"tooltip": "A still, a frame of a sequence or a video in the input folder (Upload "
                                            "media adds files; several frames at once = a sequence)."}),
                "source": (list(SOURCES), {"default": SOURCES[0]}),
                "mode": (list(MODES), {"default": MODES[0], "tooltip": "auto: a numbered frame reads its whole "
                                       "sequence, a video its frames; single frame: only that file."}),
                "frame_range": ("STRING", {"default": "", "tooltip": "e.g. 1001-1100 or 1001-1100x2 (frame "
                                           "numbers; a video counts from 0, as Load Video (C2C) does). Empty = "
                                           "everything."}),
                "missing_frames": (list(MISSING_POLICIES), {"default": "error", "tooltip": "A gap in the "
                                   "sequence: refuse, black, hold the last frame, the nearest frame, or skip it."}),
                "outside_range": (list(EDGE_POLICIES), {"default": "hold", "tooltip": "A range that reaches past "
                                  "the first / last frame."}),
                "frame_shift": ("INT", {"default": 0, "min": -9999999, "max": 9999999, "tooltip": "Added to every "
                                "frame number in frame_numbers and the metadata (a slip, as in Nuke)."}),
            },
            "optional": {
                "server_path": ("STRING", {"default": ""}),
                "layer": ("STRING", {"default": "auto", "tooltip": "EXR: the layer for the image (pass_names / "
                                     "passes give the others)."}),
                "sequence_fps": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1000.0, "step": 0.001,
                                           "tooltip": "A sequence's rate; 0 = the file's own (EXR / DPX) or 24."}),
                "colour_space": ("STRING", {"default": "", "tooltip": "OCIO: the source's colour space."}),
                "convert_to": ("STRING", {"default": "", "tooltip": "OCIO: convert to this space on read (needs "
                                          "colour_space). Empty = no conversion."}),
                "ocio_config": ("STRING", {"default": ""}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, file="", source=SOURCES[0], mode=MODES[0], frame_range="", missing_frames="error",
                   outside_range="hold", frame_shift=0, server_path="", **kw):
        try:
            path = resolve(source, file, server_path)
            fp = RP.fingerprint(path, "file (input folder)" if mode in ("single frame", "video") else "sequence")
        except Exception as exc:  # noqa: BLE001 - execute says what is wrong
            fp = f"error|{exc}"
        rest = "|".join(str(kw.get(k, "")) for k in ("layer", "sequence_fps", "colour_space", "convert_to",
                                                    "ocio_config"))
        return f"{fp}|{mode}|{frame_range}|{missing_frames}|{outside_range}|{frame_shift}|{rest}"

    def execute(self, file="", source=SOURCES[0], mode=MODES[0], frame_range="", missing_frames="error",
                outside_range="hold", frame_shift=0, server_path="", layer="auto", sequence_fps=0.0, colour_space="",
                convert_to="", ocio_config=""):
        path = resolve(source, file, server_path)
        try:
            handle, facts = _media.probe_media(path, mode=engine_mode(mode, path),
                                               layer=str(layer or "auto").strip() or "auto",
                                               sequence_fps=float(sequence_fps or 0))
        except (ValueError, OSError) as exc:
            raise ReadError(f"{NAME}: {exc}") from exc
        src_numbers = list(_media.source_numbers(handle))
        timeline = None
        if str(frame_range or "").strip() or missing_frames != "error" or (facts.sequence is not None and
                                                                           facts.sequence.missing):
            try:
                handle, timeline = _media.apply_timeline(handle, frame_range=str(frame_range or "").strip(),
                                                         missing=missing_frames, edge=outside_range)
            except ValueError as exc:
                raise ReadError(f"{NAME}: {exc}") from exc
        n = len(handle)
        if n == 0:
            raise ReadError(f"{NAME}: the range {frame_range!r} selects no frame.")
        numbers = list(timeline.numbers) if timeline is not None else \
            (src_numbers if len(src_numbers) == n else list(range(1, n + 1)))
        numbers = [int(x) + int(frame_shift) for x in numbers]
        ch = 4 if handle.has_alpha else 3
        fits = _budget.frames_that_fit(int(handle.width), int(handle.height), ch, "float32")
        if n > fits:
            raise _budget.BudgetError(f"{NAME}: " + _budget.budget_error_message(
                asked=n, fits=fits, width=int(handle.width), height=int(handle.height), channels=ch,
                dtype="float32") + " Narrow frame_range.")
        arr = _reader.read(handle, list(range(n)), fmt="float32")
        frames = torch.from_numpy(np.ascontiguousarray(arr))
        image = frames[..., :3].contiguous()
        alpha = frames[..., 3].contiguous() if frames.shape[-1] > 3 else torch.ones(frames.shape[:3])
        cs_in, cs_out = str(colour_space or "").strip(), str(convert_to or "").strip()
        if cs_out and not cs_in:
            raise ReadError(f"{NAME}: convert_to needs colour_space (the space the source is in).")
        if cs_in and cs_out and cs_in != cs_out:
            from ...utils.ocio_convert import apply_colorspace_convert
            image = apply_colorspace_convert(image, cs_in, cs_out, config_path=ocio_config)
        info = getattr(facts, "image", None)
        layers = list(getattr(info, "layers", ()) or ())
        passes = ExrPasses(handle, layers, layer_used=getattr(facts, "layer", "")) if facts.is_exr \
            else ExrPasses.empty()
        audio = lazy_audio_for_handle(handle)
        rel = facts.to_dict() if source == "server path" else RP._rel_all(facts.to_dict())
        fps = float(handle.fps) if float(handle.fps or 0) > 0 else 0.0
        meta = {
            "path": path if source == "server path" else str(file), "source": source, "mode": mode,
            "kind": facts.kind, "frames": n, "size": [int(handle.width), int(handle.height)],
            "fps": f"{handle.fps.numerator}/{handle.fps.denominator}" if hasattr(handle.fps, "numerator") else fps,
            "fps_from": facts.fps_from, "duration_sec": round(n / fps, 4) if fps else None,
            "frame_numbers": {"first": numbers[0], "last": numbers[-1], "count": n, "text": numbers_text(numbers),
                              "shift": int(frame_shift)},
            "timeline": None if timeline is None else {"missing": list(timeline.missing)[:200],
                                                       "outside": list(timeline.outside)[:200],
                                                       "step": timeline.step, "notes": list(timeline.notes)},
            "media": rel, "header": getattr(info, "header", {}) if info is not None else {},
            "colour": {"space": cs_in or None, "converted_to": cs_out if cs_in and cs_out else None},
            "has_alpha": bool(handle.has_alpha), "audio": facts.kind == "video",
            "values": {"min": round(float(image.min()), 6), "max": round(float(image.max()), 6),
                       "above_1": bool(float(image.max()) > 1.0)},
            "warnings": list(facts.warnings),
        }
        linear = os.path.splitext(re.sub(r"[#@]+|%0?\d*d|\$F\d*", "0", path))[1].lower() in LINEAR and not cs_out
        ui = []
        try:
            if n > 1:
                ui.append(_save_temp(contact_sheet(image, numbers, linear), "sheet"))
            else:
                from PIL import Image
                ui.append(_save_temp(Image.fromarray(_display(image[0].cpu().numpy(), linear)), "still"))
        except Exception:  # noqa: BLE001 - a preview never fails the read
            pass
        ui = [u for u in ui if u]
        out = (image, alpha, passes, audio, json.dumps(meta, indent=2, default=str), numbers_text(numbers), n, fps)
        return {"ui": {"images": ui}, "result": out} if ui else out


NODE_CLASS_MAPPINGS = {"NukeMax_Read": NukeMax_Read}
NODE_DISPLAY_NAME_MAPPINGS = {"NukeMax_Read": "NukeMax Read"}


def _register_routes():
    """POST /nukemax/media/upload_media (multipart 'file' x N, optional 'overwrite'): stills / frames / videos into
    input/nukemax_media/, each streamed to disk (a large video never sits in memory) and content-checked.
    GET /nukemax/media/files: the input folder's readable media (the node's refresh)."""
    try:
        from aiohttp import web
        from server import PromptServer  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - outside ComfyUI
        return
    server = getattr(PromptServer, "instance", None)
    if server is None:
        return
    routes = server.routes

    @routes.post("/nukemax/media/upload_media")
    async def _upload(request):
        parts, overwrite = [], False
        limit = int(os.environ.get("NUKEMAX_UPLOAD_MAX_MB", "16384")) * 1024 * 1024
        folder = os.path.join(RP._folder_paths().get_input_directory(), UPLOAD_SUBFOLDER)
        os.makedirs(folder, exist_ok=True)
        try:
            reader = await request.multipart()
            async for part in reader:
                if part.name == "file":
                    name = part.filename or "upload"
                    tmp = os.path.join(folder, f".~upload.{os.getpid()}.{len(parts)}.part")
                    parts.append((name, tmp))
                    size = 0
                    with open(tmp, "wb") as f:
                        while True:
                            c = await part.read_chunk(1 << 20)
                            if not c:
                                break
                            size += len(c)
                            if size > limit:
                                raise ReadError(f"{name} is larger than the upload limit (NUKEMAX_UPLOAD_MAX_MB).")
                            f.write(c)
                elif part.name == "overwrite":
                    overwrite = (await part.text()).strip().lower() in ("1", "true", "yes")
            if not parts:
                return web.json_response({"error": "no file in the upload."}, status=400)
            return web.json_response(store_uploads(parts, overwrite))
        except ValueError as exc:
            for _, tmp in parts:
                if os.path.exists(tmp):
                    os.remove(tmp)
            return web.json_response({"error": str(exc)}, status=400)

    @routes.get("/nukemax/media/files")
    async def _files(request):
        return web.json_response({"files": input_media_files()})


_register_routes()
