"""NukeMax Write - the generic media writer (owner Rev 3 Part 19.8 / 19.9; ledger L9.80 slice 4b).

Stills and numbered sequences (EXR, DPX, TIFF, PNG, JPEG) and movies, on the same safe-write core as Write EXR Pro:
versioned by default, overwrite only when asked, atomic, a manifest with SHA-256, every file re-checked and listed.
- EXR goes to NukeMax Write EXR Pro (one EXR writer, not two);
- DPX 8/10/12/16-bit, TIFF 8/16/32-bit float (none / lzw / zip), PNG 8/16-bit, JPEG with a quality - values outside
  0..1 are clipped for the integer formats and COUNTED in the report, never hidden; JPEG has no alpha (said);
- movies through the vendored C2C stream writer: only the codecs that writer AND this machine's PyAV can write are
  offered (today ProRes 422 HQ, H.264, FFV1; DNxHR / HEVC / ProRes 4444 come with the shared writer, L9.104);
  the AUDIO input is muxed in; the rate is exact (23.976 = 24000/1001);
- frame numbers from frame_start + padding or a mapping (Read's frame_numbers), a frame_range keeps a subset;
- optional OCIO conversion before writing; the colour space recorded.
Original node, GPL-3.0-only.
"""
from __future__ import annotations

import json
import os
import re
import time
from fractions import Fraction

import numpy as np

from . import _safe_write as SW
from .write_exr_pro import COMPRESSIONS as EXR_COMPRESSIONS
from .write_exr_pro import NukeMax_WriteEXRPro

NAME = "NukeMax Write"
SCHEMA = "nukemax.write/1"
DEFAULT_DIR = "nukemax_out"
VERSIONING = ("new version (name_v###)", "none (plain names)")
DEPTHS = ("auto", "8-bit", "10-bit", "12-bit", "16-bit", "half float", "32-bit float")
COMPRESSION = ("auto", "none", "zip", "lzw") + tuple(c for c in EXR_COMPRESSIONS if c not in ("zip", "none"))

# still format: (extension, OpenImageIO writer, bit depths allowed - the first is 'auto', alpha?)
STILLS = {
    "exr": (".exr", "openexr", ("half float", "32-bit float"), True),
    "dpx": (".dpx", "dpx", ("10-bit", "8-bit", "12-bit", "16-bit"), True),
    "tiff": (".tif", "tiff", ("16-bit", "8-bit", "32-bit float"), True),
    "png": (".png", "png", ("8-bit", "16-bit"), True),
    "jpeg": (".jpg", "jpeg", ("8-bit",), False),
}
# movie: label -> (engine codec, extension, PyAV encoder)
MOVIES = {
    "mov - ProRes 422 HQ": ("prores", ".mov", "prores_ks"),
    "mp4 - H.264": ("h264", ".mp4", "libx264"),
    "mkv - FFV1 (lossless)": ("ffv1", ".mkv", "ffv1"),
}


class WriteError(SW.WriteError):
    pass


def available_formats() -> list[str]:
    """Only what this machine can write: OpenImageIO's writers and the engine's codecs PyAV can encode."""
    out: list[str] = []
    try:
        import OpenImageIO as oiio  # type: ignore[import-not-found]
        have = set(str(oiio.get_string_attribute("output_format_list")).split(","))
        out += [k for k, v in STILLS.items() if v[1] in have]
    except Exception:  # noqa: BLE001 - no OpenImageIO: no stills
        pass
    try:
        import av

        from ...vendor.c2c_core.video.writer import CODECS
        for label, (codec, _ext, enc) in MOVIES.items():
            try:
                av.codec.Codec(enc, "w")
            except Exception:  # noqa: BLE001 - this build cannot encode it
                continue
            if codec in CODECS:
                out.append(label)
    except Exception:  # noqa: BLE001 - no PyAV: no movies
        pass
    return out or ["png"]


def expand_ranges(text: str) -> set[int]:
    nums: set[int] = set()
    for part in re.split(r"[,\s]+", str(text or "").strip()):
        if not part:
            continue
        m = re.fullmatch(r"(-?\d+)(?:-(-?\d+)(?:x(\d+))?)?", part)
        if not m:
            raise WriteError(f"{NAME}: frame_range {part!r} is not a number or a range (1001-1050, 1001-1050x2).")
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) is not None else a
        nums.update(range(a, b + 1, int(m.group(3) or 1)))
    return nums


def _depth(fmt: str, depth: str, movie: bool) -> str:
    if movie:
        if depth in ("auto", "8-bit", "10-bit"):
            return depth
        raise WriteError(f"{NAME}: a movie is written 8-bit or 10-bit, not {depth}.")
    allowed = STILLS[fmt][2]
    if depth == "auto":
        return allowed[0]
    if depth not in allowed:
        raise WriteError(f"{NAME}: {fmt.upper()} is written {', '.join(allowed)} - not {depth}.")
    return depth


def _compression(fmt: str, comp: str) -> str:
    allowed = {"tiff": ("none", "lzw", "zip"), "png": ("zip",), "dpx": ("none",), "jpeg": ("jpeg",),
               "exr": EXR_COMPRESSIONS}[fmt]
    if comp == "auto":
        return {"tiff": "zip", "png": "zip", "dpx": "none", "jpeg": "jpeg", "exr": "zip"}[fmt]
    if comp not in allowed:
        raise WriteError(f"{NAME}: {fmt.upper()} takes compression {', '.join(allowed)} - not {comp}.")
    return comp


class NukeMax_Write:
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING", "INT", "STRING", "STRING")
    RETURN_NAMES = ("manifest", "written_paths", "frame_count", "backend", "metadata_report")
    DESCRIPTION = ("Writes stills, numbered sequences (EXR, DPX, TIFF, PNG, JPEG) or a movie (ProRes, H.264, FFV1 - "
                   "what this machine can write) with sound: versioned, never a silent overwrite, atomic, a manifest "
                   "with SHA-256, the exact files listed.")

    @classmethod
    def INPUT_TYPES(cls):
        fmts = available_formats()
        return {
            "required": {
                "image": ("IMAGE",),
                "format": (fmts, {"default": "png" if "png" in fmts else fmts[0], "tooltip": "Only what this "
                                  "machine can write is listed."}),
                "output_dir": ("STRING", {"default": DEFAULT_DIR}),
                "filename": ("STRING", {"default": "shot"}),
                "bit_depth": (list(DEPTHS), {"default": "auto", "tooltip": "auto: EXR half, DPX 10-bit, TIFF 16-bit, "
                                             "PNG / JPEG 8-bit, a movie its codec's own."}),
                "compression": (list(COMPRESSION), {"default": "auto"}),
                "quality": ("INT", {"default": 90, "min": 1, "max": 100, "tooltip": "JPEG and H.264."}),
                "frame_pattern": (list(SW.PATTERNS), {"default": SW.PATTERNS[0]}),
                "frame_start": ("INT", {"default": 1001, "min": -999999, "max": 9999999}),
                "padding": ("INT", {"default": 4, "min": 1, "max": 10}),
                "fps": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1000.0, "step": 0.001, "tooltip": "0 = the "
                                  "metadata's rate, else 24. 23.976 is written exactly (24000/1001)."}),
                "versioning": (list(VERSIONING), {"default": VERSIONING[0]}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "sidecar": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "alpha": ("MASK",),
                "audio": ("AUDIO", {"tooltip": "A movie: muxed in (a still / sequence: ignored, said)."}),
                "metadata": ("STRING", {"forceInput": True}),
                "frame_numbers": ("STRING", {"default": "", "tooltip": "Frame mapping (NukeMax Read's frame_numbers, "
                                             "or 1001-1010, 1020). Empty: from frame_start."}),
                "frame_range": ("STRING", {"default": "", "tooltip": "Write only these frame numbers."}),
                "version": ("INT", {"default": 0, "min": 0, "max": 9999}),
                "colour_space": ("STRING", {"default": ""}),
                "convert_from": ("STRING", {"default": ""}),
                "ocio_config": ("STRING", {"default": ""}),
            },
        }

    def execute(self, image, format="png", output_dir=DEFAULT_DIR, filename="shot", bit_depth="auto",
                compression="auto", quality=90, frame_pattern=SW.PATTERNS[0], frame_start=1001, padding=4, fps=0.0,
                versioning=VERSIONING[0], overwrite=False, sidecar=True, alpha=None, audio=None, metadata=None,
                frame_numbers="", frame_range="", version=0, colour_space="", convert_from="", ocio_config="",
                manifest_extra=None):
        # manifest_extra: facts a caller adds to the manifest sidecar (OCIO Write: config + spaces); Python only
        self._extra = dict(manifest_extra or {})
        if image.ndim == 3:
            image = image.unsqueeze(0)
        n, h, w = int(image.shape[0]), int(image.shape[1]), int(image.shape[2])
        movie = format in MOVIES
        if not movie and format not in STILLS:
            raise WriteError(f"{NAME}: unknown format {format!r}.")
        frames = SW.parse_frames(frame_numbers, n, frame_start, NAME)
        keep = list(range(n))
        if str(frame_range or "").strip():
            want = expand_ranges(frame_range)
            keep = [i for i, f in enumerate(frames) if f in want]
            if not keep:
                raise WriteError(f"{NAME}: frame_range {frame_range!r} keeps none of frames {frames[0]}-{frames[-1]}.")
        if format == "exr":                                  # one EXR writer: Write EXR Pro
            d = _depth("exr", bit_depth, False)
            res = NukeMax_WriteEXRPro().execute(
                image=image[keep], alpha=None if alpha is None else (alpha if alpha.shape[0] == 1 else alpha[keep]),
                output_dir=output_dir, filename=filename,
                frame_pattern="name_####.exr" if frame_pattern.startswith("name_") else "name.####.exr",
                frame_start=frame_start, padding=padding,
                bit_depth="half (16-bit float)" if d == "half float" else "float (32-bit)",
                compression=_compression("exr", compression), versioning="new version folder (name_v###)"
                if versioning == VERSIONING[0] else "none (plain names)", overwrite=overwrite, sidecar=sidecar,
                metadata=metadata, frame_numbers=", ".join(str(frames[i]) for i in keep), version=version,
                colour_space=colour_space, convert_from=convert_from, ocio_config=ocio_config, fps=fps,
                manifest_extra=self._extra)
            return res
        image = image[keep]
        frames = [frames[i] for i in keep]
        if alpha is not None:
            alpha = alpha if alpha.ndim == 3 else alpha.unsqueeze(0)
            if tuple(alpha.shape[1:]) != (h, w):
                raise WriteError(f"{NAME}: the alpha is {alpha.shape[2]}x{alpha.shape[1]}, the image {w}x{h}.")
            alpha = alpha if alpha.shape[0] == 1 else alpha[keep]
        cs_out, cs_in = str(colour_space or "").strip(), str(convert_from or "").strip()
        if cs_in and not cs_out:
            raise WriteError(f"{NAME}: convert_from needs colour_space (the space to convert to).")
        if cs_in and cs_in != cs_out:
            from ...utils.ocio_convert import apply_colorspace_convert
            image = apply_colorspace_convert(image[..., :3], cs_in, cs_out, config_path=ocio_config)
        meta = {}
        if str(metadata or "").strip():
            try:
                meta = json.loads(metadata)
            except json.JSONDecodeError as exc:
                raise WriteError(f"{NAME}: metadata is not JSON ({exc.msg}).") from exc
        rate = Fraction(float(fps)).limit_denominator(1001000) if float(fps or 0) > 0 else None
        if rate is None and isinstance(meta, dict) and isinstance(meta.get("media"), dict) and meta["media"].get("fps"):
            try:
                rate = Fraction(str(meta["media"]["fps"]))
            except (ValueError, ZeroDivisionError):
                rate = None
        rate = rate or Fraction(24, 1)
        base = SW.resolve_dir(output_dir, NAME, DEFAULT_DIR)
        name = SW.clean_name(filename, "")
        report = {"clipped": 0, "nan": 0, "notes": []}
        if movie:
            return self._movie(format, image, alpha, audio, frames, rate, base, name, bit_depth, quality, versioning,
                               version, overwrite, sidecar, cs_out, cs_in, report)
        return self._stills(format, image, alpha, audio, frames, rate, base, name, bit_depth, compression, quality,
                            frame_pattern, padding, versioning, version, overwrite, sidecar, cs_out, cs_in, report)

    # ------------------------------------------------------------------ stills / sequences
    def _stills(self, fmt, image, alpha, audio, frames, rate, base, name, bit_depth, compression, quality,
                frame_pattern, padding, versioning, version, overwrite, sidecar, cs_out, cs_in, report):
        import OpenImageIO as oiio  # type: ignore[import-not-found]
        ext, writer, _depths, has_alpha = STILLS[fmt]
        depth = _depth(fmt, bit_depth, False)
        comp = _compression(fmt, compression)
        if alpha is not None and not has_alpha:
            report["notes"].append(f"{fmt.upper()} has no alpha: the alpha was not written.")
            alpha = None
        if audio is not None:
            report["notes"].append("Stills have no sound: the audio input was not written.")
        n, h, w = int(image.shape[0]), int(image.shape[1]), int(image.shape[2])
        integer = depth not in ("half float", "32-bit float")
        td = {"8-bit": "uint8", "10-bit": "uint16", "12-bit": "uint16", "16-bit": "uint16", "half float": "half",
              "32-bit float": "float"}[depth]
        target = SW.plan(NAME, base, name, lambda stem: [SW.frame_file(stem, f, padding, frame_pattern, ext)
                                                         for f in frames],
                         versioned=versioning == VERSIONING[0], version=version, overwrite=overwrite, sidecar=sidecar)
        written = []
        try:
            for i, frame in enumerate(frames):
                px = image[i, ..., :3].float().cpu().numpy()
                if alpha is not None:
                    px = np.concatenate([px, alpha[0 if alpha.shape[0] == 1 else i].float().cpu().numpy()[..., None]],
                                        -1)
                report["nan"] += int(np.isnan(px).sum())
                if integer:
                    report["clipped"] += int(((px < 0) | (px > 1)).sum())
                    px = np.clip(np.nan_to_num(px), 0, 1)
                spec = oiio.ImageSpec(w, h, int(px.shape[-1]), td)
                spec.channelnames = ("R", "G", "B", "A")[:px.shape[-1]]
                if px.shape[-1] == 4:
                    spec.alpha_channel = 3
                if depth in ("10-bit", "12-bit"):
                    spec.attribute("oiio:BitsPerSample", int(depth[:2]))
                spec.attribute("compression", f"jpeg:{int(quality)}" if fmt == "jpeg" else comp)
                spec.attribute("Software", NAME)
                spec.attribute("nukemax:frame", int(frame))
                if cs_out:
                    spec.attribute("oiio:ColorSpace", cs_out)
                    spec.attribute("nukemax:colourSpace", cs_out)
                tmp = target.temp_for(target.files[i])
                out = oiio.ImageOutput.create(tmp)
                if out is None:
                    raise WriteError(f"{NAME}: OpenImageIO has no {fmt.upper()} writer: {oiio.geterror()}")
                try:
                    if not out.open(tmp, spec) or not out.write_image(np.ascontiguousarray(px, dtype=np.float32)):
                        raise WriteError(f"{NAME}: writing {target.files[i]} failed: {out.geterror()}")
                finally:
                    out.close()
                written.append(target.place(tmp, target.files[i]))
            man = self._manifest(target, fmt, frames, (w, h), {"bit_depth": depth, "compression": comp,
                                                                "quality": int(quality) if fmt == "jpeg" else None,
                                                                "alpha": alpha is not None}, rate, cs_out, cs_in,
                                 report, SW.pattern_text(target.stem, padding, frame_pattern, ext))
            man.update(getattr(self, "_extra", {}))
            text = json.dumps(man, indent=2)
            target.write_manifest(text)
            target.commit()
        except BaseException:
            target.abort()
            raise
        confirmed = []
        for p, entry in zip(written, man["files"]):
            inp = oiio.ImageInput.open(p)
            ok = inp is not None and (inp.spec().width, inp.spec().height) == (w, h)
            if inp is not None:
                inp.close()
            if not ok or SW.sha256(p) != entry["sha256"]:
                raise WriteError(f"{NAME}: {SW.display_path(p)} does not match what was written.")
            confirmed.append(SW.display_path(p))
        backend = f"OpenImageIO {oiio.VERSION_STRING} ({writer})" + (" + OpenColorIO" if cs_in else "")
        return self._result(man, confirmed, report, backend, target)

    # ------------------------------------------------------------------ movies
    def _movie(self, label, image, alpha, audio, frames, rate, base, name, bit_depth, quality, versioning, version,
               overwrite, sidecar, cs_out, cs_in, report):
        import av

        from ...vendor.c2c_core.video.writer import StreamWriter, WriterError
        codec, ext, _enc = MOVIES[label]
        depth = _depth("", bit_depth, True)
        if alpha is not None:
            report["notes"].append(f"{label} has no alpha: the alpha was not written.")
        n, h, w = int(image.shape[0]), int(image.shape[1]), int(image.shape[2])
        target = SW.plan(NAME, base, name, lambda stem: [f"{stem}{ext}"], versioned=versioning == VERSIONING[0],
                         version=version, overwrite=overwrite, sidecar=sidecar, folder_per_version=False)
        sr = ch = 0
        wave = None
        if audio is not None:
            wave = audio["waveform"]
            wave = (wave[0] if wave.ndim == 3 else wave).float().cpu().numpy()
            sr, ch = int(audio["sample_rate"]), int(wave.shape[0])
        fname = target.files[0]
        try:
            tmp = target.temp_for(fname)
            try:
                wr = StreamWriter(tmp, rate, w, h, codec=codec, quality=int(quality), ten_bit=depth == "10-bit",
                                  audio_rate=sr, audio_channels=ch)
            except WriterError as exc:
                raise WriteError(f"{NAME}: {exc}") from exc
            try:
                for k in range(0, n, 16):                    # bounded memory: 16 frames per call
                    chunk = image[k:k + 16, ..., :3].float().cpu().numpy()
                    report["nan"] += int(np.isnan(chunk).sum())
                    report["clipped"] += int(((chunk < 0) | (chunk > 1)).sum())
                    wr.write(np.clip(np.nan_to_num(chunk), 0, 1))
                if wave is not None:
                    wr.write_audio(wave)
            finally:
                wr.close()
            path = target.place(tmp, fname)
            info = {"codec": codec, "pix_fmt": wr.pix_fmt, "frames_written": int(wr.frames),
                    "audio": {"sample_rate": sr, "channels": min(2, ch), "seconds": round(wave.shape[-1] / sr, 4)}
                    if wave is not None else None, "ten_bit": wr.ten_bit}
            man = self._manifest(target, label, frames, (w, h), info, rate, cs_out, cs_in, report, fname)
            man.update(getattr(self, "_extra", {}))
            text = json.dumps(man, indent=2)
            target.write_manifest(text)
            target.commit()
        except BaseException:
            target.abort()
            raise
        c = av.open(path)
        try:
            vs = c.streams.video[0]
            ok = (vs.codec_context.width, vs.codec_context.height) == (w, h)
            has_audio = bool(c.streams.audio)
        finally:
            c.close()
        if not ok or SW.sha256(path) != man["files"][0]["sha256"] or (wave is not None and not has_audio):
            raise WriteError(f"{NAME}: {SW.display_path(path)} does not match what was written.")
        backend = f"PyAV {av.__version__} ({codec})" + (" + OpenColorIO" if cs_in else "")
        return self._result(man, [SW.display_path(path)], report, backend, target)

    # ------------------------------------------------------------------ shared
    @staticmethod
    def _manifest(target, fmt, frames, size, info, rate, cs_out, cs_in, report, pattern) -> dict:
        man = {"schema": SCHEMA, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "format": fmt,
               "directory": SW.display_path(target.final_dir), "version": target.version or None, "pattern": pattern,
               "frames": frames, "frame_count": len(frames), "size": list(size),
               "fps": f"{rate.numerator}/{rate.denominator}", "colour_space": cs_out or None,
               "converted_from": cs_in or None, "clipped": report["clipped"], "nan": report["nan"],
               "notes": report["notes"], **info}
        man["files"] = [{"file": f, "bytes": os.path.getsize(target.current(f)), "sha256": SW.sha256(target.current(f))}
                        | ({"frame": frames[i]} if len(target.files) == len(frames) else {})
                        for i, f in enumerate(target.files)]
        return man

    @staticmethod
    def _result(man, confirmed, report, backend, target):
        fr = man["frames"]
        lines = [f"wrote {len(confirmed)} file(s) to {man['directory']}/",
                 f"{man['format']} | frames {fr[0]}-{fr[-1]} ({len(fr)}) | {man['fps']} fps"]
        if report["clipped"]:
            lines.append(f"clipped to 0..1: {report['clipped']} value(s)")
        lines += report["notes"]
        if target.manifest_name:
            lines.append(f"manifest: {target.manifest_name}")
        lines += confirmed[:12] + ([f"... and {len(confirmed) - 12} more"] if len(confirmed) > 12 else [])
        return {"ui": {"text": ["\n".join(lines)]},
                "result": (json.dumps(man, indent=2), "\n".join(confirmed), len(fr), backend,
                           json.dumps(report, indent=2))}


NODE_CLASS_MAPPINGS = {"NukeMax_Write": NukeMax_Write}
NODE_DISPLAY_NAME_MAPPINGS = {"NukeMax_Write": "NukeMax Write"}
