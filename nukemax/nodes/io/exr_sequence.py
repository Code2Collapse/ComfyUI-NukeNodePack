"""EXR sequence Read/Write + ProRes MOV export — Nuke Read/Write parity.

Sequence detection, missing-frame policies (error/black/hold), EXR half/float
write with the full compression set, and ProRes 422/422HQ/4444/4444XQ export
via PyAV (alpha preserved on 4444 profiles).

Adapted from ComfyUI-ACES-IO — Copyright (c) 2025 Bishoy Samaan,
MIT License, https://github.com/BISAM20/ComfyUI-ACES-IO
Changes for NukeMax: house IS_CHANGED (content/fs hash, never nan),
@resilient registration, plain path widgets instead of ACES_PATH custom
types, NukeMax categories, and file-mtime cache keys on the loader.
"""
from __future__ import annotations

import os
import re

import numpy as np
import torch

# Must be set before cv2 is imported or its EXR support stays disabled.
os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")

_CV2_EXR_HINT = (
    "OpenCV only handles EXR when OPENCV_IO_ENABLE_OPENEXR=1 is set BEFORE cv2 is "
    "first imported anywhere in the process. If another extension imported cv2 "
    "first, set that variable in the environment before starting ComfyUI, or "
    "install the OpenEXR bindings instead."
)

try:
    import OpenEXR  # type: ignore[import-not-found]
    import Imath    # type: ignore[import-not-found]
    _HAVE_OPENEXR = True
except ImportError:
    _HAVE_OPENEXR = False

from ...utils.resilience import resilient
from ..._tensor_util import require_image_bhwc
from ..._is_changed_util import hash_args_and_kwargs

COMPRESSIONS = {
    "ZIP  (lossless, recommended)": "ZIP_COMPRESSION",
    "ZIPS (lossless, scanline)":    "ZIPS_COMPRESSION",
    "PIZ  (lossless, wavelet)":     "PIZ_COMPRESSION",
    "PXR24 (lossy, 24-bit)":        "PXR24_COMPRESSION",
    "RLE  (lossless, run-length)":  "RLE_COMPRESSION",
    "B44  (lossy, fixed ratio)":    "B44_COMPRESSION",
    "DWAA (lossy, DCT, fast)":      "DWAA_COMPRESSION",
    "None (uncompressed)":          "NO_COMPRESSION",
}
BIT_DEPTHS = ["16f (half-float)", "32f (float)"]

_PRORES_PROFILES = {
    "MOV ProRes 422":     (2, False),
    "MOV ProRes 422 HQ":  (3, False),
    "MOV ProRes 4444":    (4, True),
    "MOV ProRes 4444 XQ": (5, True),
}


def _require_cv2():
    """cv2 is the EXR fallback used when the OpenEXR bindings are absent.

    A bare `import cv2` here surfaced a raw ModuleNotFoundError, and cv2.imwrite
    signals failure by RETURNING False rather than raising, so a failed EXR write
    was silent. Both are routed through this helper instead.
    """
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "Reading or writing EXR needs either the OpenEXR bindings or OpenCV, "
            "and neither is installed. Install one of them: "
            "'pip install OpenEXR' or 'pip install opencv-python'."
        ) from exc
    return cv2


# ── EXR single-frame helpers ─────────────────────────────────────────


def _save_exr_frame(img_hwc: np.ndarray, path: str, use_half: bool, compression_key: str) -> None:
    H, W, C = img_hwc.shape
    if _HAVE_OPENEXR:
        comp_name = COMPRESSIONS.get(compression_key, "ZIP_COMPRESSION")
        header = OpenEXR.Header(W, H)
        header["compression"] = Imath.Compression(getattr(Imath.Compression, comp_name))
        ptype = Imath.PixelType(Imath.PixelType.HALF if use_half else Imath.PixelType.FLOAT)
        names = ["R", "G", "B", "A"][:C] if C in (3, 4) else [f"c{i}" for i in range(C)]
        header["channels"] = {ch: Imath.Channel(ptype) for ch in names}
        out = OpenEXR.OutputFile(path, header)
        dt = np.float16 if use_half else np.float32
        out.writePixels({ch: img_hwc[:, :, i].astype(dt).tobytes() for i, ch in enumerate(names)})
        out.close()
        return
    cv2 = _require_cv2()
    if C == 3:
        buf = img_hwc[:, :, ::-1]
    elif C == 4:
        buf = img_hwc[:, :, [2, 1, 0, 3]]
    else:
        buf = img_hwc
    # imwrite reports failure by returning False, never by raising.
    if not cv2.imwrite(path, buf.astype(np.float32)):
        raise IOError("Could not write " + repr(path) + " via OpenCV. " + _CV2_EXR_HINT)


def _load_exr_frame(path: str) -> torch.Tensor:
    if not os.path.isfile(path):
        raise FileNotFoundError(f"EXR file not found: {path!r}")
    if _HAVE_OPENEXR:
        f = OpenEXR.InputFile(path)
        dw = f.header()["dataWindow"]
        W, H = dw.max.x - dw.min.x + 1, dw.max.y - dw.min.y + 1
        PT = Imath.PixelType(Imath.PixelType.FLOAT)
        chans = list(f.header().get("channels", {}).keys())
        ordered = [c for c in ("R", "G", "B", "A") if c in chans] or chans[:4]
        img = np.stack([np.frombuffer(f.channel(c, PT), dtype=np.float32).reshape(H, W)
                        for c in ordered], axis=-1)
        return torch.from_numpy(img.copy()).unsqueeze(0)
    cv2 = _require_cv2()
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYCOLOR | cv2.IMREAD_ANYDEPTH)
    if img is None:
        raise IOError("OpenCV could not read " + repr(path) + ". " + _CV2_EXR_HINT)
    img = img.astype(np.float32)
    if img.ndim == 2:
        img = img[:, :, None]
    elif img.shape[2] == 3:
        img = img[:, :, ::-1].copy()
    elif img.shape[2] == 4:
        img = img[:, :, [2, 1, 0, 3]].copy()
    return torch.from_numpy(img).unsqueeze(0)


# ── Nuke-style sequence detection (render.####.exr / %04d / _0001) ──


def _detect_sequence(path: str):
    """Return (printf_template, sorted_frames) or (path, None) for a plain file."""
    import glob as _glob
    path = os.path.expanduser(path.strip())
    dirpath = os.path.dirname(os.path.abspath(path))
    bname = os.path.basename(path)
    hash_m = re.search(r"(#+)", bname)
    printf_m = re.search(r"(%0*\d*d)", bname)
    if hash_m:
        pad = len(hash_m.group(1))
        template = os.path.join(dirpath, re.sub(r"#+", f"%0{pad}d", bname, count=1))
        glob_pat = os.path.join(_glob.escape(dirpath), re.sub(r"#+", "*", bname, count=1))
    elif printf_m:
        template = os.path.join(dirpath, bname)
        glob_pat = os.path.join(_glob.escape(dirpath), re.sub(r"%0*\d*d", "*", bname, count=1))
    else:
        root, ext = os.path.splitext(bname)
        digit_ms = list(re.finditer(r"\d+", root))
        if not digit_ms:
            return path, None
        last = digit_ms[-1]        # LAST digit group = frame (handles v01 tokens)
        pad = len(last.group())
        prefix, suffix = root[:last.start()], root[last.end():]
        template = os.path.join(dirpath, f"{prefix}%0{pad}d{suffix}{ext}")
        glob_pat = os.path.join(_glob.escape(dirpath),
                                f"{_glob.escape(prefix)}*{_glob.escape(suffix)}{_glob.escape(ext)}")
    tb = os.path.basename(template)
    fmt = re.search(r"%0*\d*d", tb)
    frame_re = re.compile(
        "^" + re.escape(tb[:fmt.start()]) + r"(\d+)" + re.escape(tb[fmt.end():]) + "$",
        re.IGNORECASE) if fmt else None
    frames = []
    for f in sorted(_glob.glob(glob_pat)):
        m = frame_re.match(os.path.basename(f)) if frame_re else None
        if m:
            frames.append(int(m.group(1)))
    if not frames:
        return path, None
    return template, sorted(set(frames))


@resilient
class EXRSequenceLoad:
    DESCRIPTION = ("Nuke Read: load an EXR sequence (render.####.exr, %04d, or any "
                   "frame file of the sequence) or a single EXR. Missing frames can "
                   "error, insert black, or hold the previous frame.")
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "INT", "INT", "INT")
    RETURN_NAMES = ("image", "frame_count", "width", "height")

    @classmethod
    def IS_CHANGED(cls, path="", **kwargs):
        # fs-aware: re-run when the resolved first frame changes on disk.
        template, frames = _detect_sequence(path or "")
        probe = template % frames[0] if frames else template
        try:
            st = os.stat(probe)
            fs = (st.st_mtime_ns, st.st_size, len(frames or []))
        except OSError:
            fs = ("missing",)
        return hash_args_and_kwargs(path=path, fs=fs, **kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "path": ("STRING", {"default": "", "tooltip":
                     "Any frame of the sequence, a ####/%04d pattern, or a single .exr"}),
            "missing_frames": (("error", "black", "hold"), {"default": "error"}),
        }, "optional": {
            "start_frame": ("INT", {"default": -1, "min": -1, "max": 10_000_000,
                            "tooltip": "-1 = first detected frame"}),
            "end_frame": ("INT", {"default": -1, "min": -1, "max": 10_000_000,
                          "tooltip": "-1 = last detected frame"}),
            "every_nth": ("INT", {"default": 1, "min": 1, "max": 1000}),
        }}

    def execute(self, path, missing_frames, start_frame=-1, end_frame=-1, every_nth=1):
        template, frames = _detect_sequence(path)
        if frames is None:
            t = _load_exr_frame(template)
            return (t, 1, t.shape[2], t.shape[1])
        lo = frames[0] if start_frame < 0 else start_frame
        hi = frames[-1] if end_frame < 0 else end_frame
        wanted = list(range(lo, hi + 1, max(1, every_nth)))
        frame_set = set(frames)
        tensors, last_good, ref_shape = [], None, None
        for i in wanted:
            if i in frame_set:
                last_good = _load_exr_frame(template % i)
                ref_shape = ref_shape or last_good.shape[1:]
                tensors.append(last_good)
                continue
            if missing_frames == "error":
                raise FileNotFoundError(
                    f"EXRSequenceLoad: frame {i} missing (available {frames[0]}–{frames[-1]}).")
            if ref_shape is None:
                ref = _load_exr_frame(template % frames[0])
                ref_shape = ref.shape[1:]
            if missing_frames == "black" or last_good is None:
                tensors.append(torch.zeros(1, *ref_shape))
            else:
                tensors.append(last_good)
        out = torch.cat(tensors, dim=0)
        return (out, out.shape[0], out.shape[2], out.shape[1])


@resilient
class EXRSequenceSave:
    DESCRIPTION = ("Nuke Write: save an IMAGE batch as an EXR sequence (filename %04d "
                   "→ frame numbers) — half/float, all standard compressions.")
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "last_path")
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE", {}),
            "output_dir": ("STRING", {"default": "output/exr"}),
            "filename": ("STRING", {"default": "render_%04d",
                         "tooltip": "%04d is replaced by the frame number"}),
            "bit_depth": (BIT_DEPTHS, {"default": BIT_DEPTHS[0]}),
            "compression": (tuple(COMPRESSIONS.keys()),
                            {"default": next(iter(COMPRESSIONS))}),
        }, "optional": {
            "start_frame": ("INT", {"default": 1, "min": 0, "max": 10_000_000}),
        }}

    def execute(self, image, output_dir, filename, bit_depth, compression, start_frame=1):
        require_image_bhwc(image)
        os.makedirs(output_dir.strip(), exist_ok=True)
        use_half = "16f" in bit_depth
        last = ""
        for b in range(image.shape[0]):
            n = start_frame + b
            base = re.sub(r"%0(\d+)d", lambda m: f"{n:0{int(m.group(1))}d}", filename)
            if not base.lower().endswith(".exr"):
                base += ".exr"
            last = os.path.join(output_dir.strip(), base)
            _save_exr_frame(image[b].cpu().float().numpy(), last, use_half, compression)
        return {"ui": {"text": [last]}, "result": (image, last)}


@resilient
class ProResSave:
    DESCRIPTION = ("Export an IMAGE batch as Apple ProRes MOV (422 / 422 HQ / 4444 / "
                   "4444 XQ via PyAV prores_ks; 4444 keeps alpha on RGBA input) "
                   "or H.264 MP4.")
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "saved_path")
    OUTPUT_NODE = True

    FORMATS = ["MOV ProRes 4444", "MOV ProRes 4444 XQ",
               "MOV ProRes 422 HQ", "MOV ProRes 422", "MP4 (H.264)"]

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE", {}),
            "output_dir": ("STRING", {"default": "output/mov"}),
            "filename": ("STRING", {"default": "output"}),
            "format": (tuple(cls.FORMATS), {"default": "MOV ProRes 4444"}),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 0.5}),
        }}

    def execute(self, images, output_dir, filename, format, fps):
        require_image_bhwc(images)
        os.makedirs(output_dir.strip(), exist_ok=True)
        ext = ".mp4" if format.startswith("MP4") else ".mov"
        fname = filename if filename.lower().endswith(ext) else filename + ext
        path = os.path.join(output_dir.strip(), fname)
        if format in _PRORES_PROFILES:
            profile, is_4444 = _PRORES_PROFILES[format]
            self._write_prores(images, path, fps, profile, is_4444)
        else:
            self._write_mp4(images, path, fps)
        return {"ui": {"text": [path]}, "result": (images, path)}

    @staticmethod
    def _write_prores(t: torch.Tensor, path: str, fps: float, profile: int, is_4444: bool):
        try:
            import av
        except ImportError as exc:
            raise ImportError("ProResSave needs PyAV: pip install av") from exc
        from fractions import Fraction
        B, H, W, C = t.shape
        has_alpha = is_4444 and C == 4
        src_fmt = "rgba64le" if has_alpha else "rgb48le"
        pix_fmt = "yuva444p10le" if is_4444 else "yuv422p10le"
        container = av.open(path, mode="w", format="mov")
        stream = container.add_stream("prores_ks", rate=Fraction(fps).limit_denominator(10000))
        stream.width, stream.height, stream.pix_fmt = W, H, pix_fmt
        stream.options = {"profile": str(profile)}
        for i in range(B):
            f16 = (t[i].cpu().float().numpy() * 65535.0).clip(0, 65535).astype(np.uint16)
            arr = f16 if has_alpha else f16[:, :, :3]
            frame = av.VideoFrame.from_ndarray(arr, format=src_fmt).reformat(format=pix_fmt)
            frame.pts = i
            for pkt in stream.encode(frame):
                container.mux(pkt)
        for pkt in stream.encode():
            container.mux(pkt)
        container.close()

    @staticmethod
    def _write_mp4(t: torch.Tensor, path: str, fps: float):
        import cv2
        B, H, W, _ = t.shape
        vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))
        try:
            for i in range(B):
                u8 = (t[i, :, :, :3].cpu().float().numpy() * 255.0).clip(0, 255).astype(np.uint8)
                vw.write(u8[:, :, ::-1])
        finally:
            vw.release()


NODE_CLASS_MAPPINGS = {
    "NukeMax_EXRSequenceLoad": EXRSequenceLoad,
    "NukeMax_EXRSequenceSave": EXRSequenceSave,
    "NukeMax_ProResSave": ProResSave,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_EXRSequenceLoad": "EXR Sequence Read (Nuke)",
    "NukeMax_EXRSequenceSave": "EXR Sequence Write (Nuke)",
    "NukeMax_ProResSave": "ProRes / MP4 Write",
}
