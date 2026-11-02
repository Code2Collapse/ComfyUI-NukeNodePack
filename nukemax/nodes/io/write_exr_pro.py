"""NukeMax Write EXR Pro (owner Rev 3 Part 19.7; ledger L9.80 slice 3).

A professional EXR writer on OpenImageIO:
- the image (one frame or a sequence), an optional alpha, an optional C2C_EXR_PASSES bundle (every pass, or the ones
  named) and an optional metadata JSON (Read EXR Pro / Metadata Reader Pro: its source header is carried over);
- frame numbers from frame_start + padding or an explicit mapping (1001-1010, 1020);
- half or float, with data passes (depth, position, normal, motion ...) kept float when the beauty is half;
  every compression OpenEXR has; single part (layers as channels) or multipart (one part per layer);
- optional OCIO conversion of the colour channels (never of data passes) and the colour space written in the header;
- overwrite only when asked; versioned output (name_v###/) by default;
- ATOMIC: a new version is written into a hidden folder and renamed into place whole, a replaced file is written beside
  it and renamed over it - a failed or interrupted write never leaves a half version or a half file;
- a manifest (files, frames, SHA-256, channels, colour, source) returned and written as a sidecar.
The node then re-opens every file it wrote and reports exactly those files.
Original node, GPL-3.0-only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time

import numpy as np
import torch

from . import _media_roots as MR

BIT_DEPTHS = ("half (16-bit float)", "float (32-bit)")
COMPRESSIONS = ("zip", "zips", "piz", "pxr24", "b44", "b44a", "dwaa", "dwab", "rle", "none")
LAYOUTS = ("single part (layers as channels)", "multipart (one part per layer)")
VERSIONING = ("new version folder (name_v###)", "none (plain names)")
PATTERNS = ("name.####.exr", "name_####.exr")
ALPHA_MODES = ("write as given", "premultiply RGB by alpha")
METADATA_MODES = ("source header + writer keys", "writer keys only")
HALF_MAX = 65504.0
DEFAULT_DIR = "nukemax_exr"
SCHEMA = "nukemax.write_exr_pro/1"

# header keys that describe the file's own structure: OpenImageIO writes them from the spec, a copy would lie
_STRUCTURAL = {"channels", "compression", "datawindow", "displaywindow", "lineorder", "name", "type", "version",
               "chunkcount", "tiles", "framespersecond", "smpte:timecode", "timecode"}


class WriteError(ValueError):
    """A refusal in plain words."""


def _oiio():
    try:
        import OpenImageIO as oiio  # type: ignore[import-not-found]
    except ImportError as exc:
        raise WriteError("NukeMax Write EXR Pro needs OpenImageIO (pip install OpenImageIO).") from exc
    return oiio


def _output_root() -> str:
    import folder_paths  # type: ignore[import-not-found]
    return os.path.realpath(folder_paths.get_output_directory())


def resolve_dir(output_dir: str) -> str:
    """A relative folder lives under ComfyUI's output folder (and may not climb out of it); an absolute one follows
    the readers' rule: any folder on a loopback-only server, only the C2C media roots on a reachable one."""
    raw = str(output_dir or "").strip() or DEFAULT_DIR
    if os.path.isabs(raw):
        msg = MR.check_run_path(raw)
        if msg:
            raise WriteError(f"NukeMax Write EXR Pro: {msg}")
        return os.path.realpath(raw)
    root = _output_root()
    path = os.path.realpath(os.path.join(root, raw))
    if os.path.commonpath([root, path]) != root:
        raise WriteError(f"NukeMax Write EXR Pro: output_dir {raw!r} climbs out of ComfyUI's output folder - use a "
                         "folder inside it, or an absolute path.")
    return path


def display_path(path: str) -> str:
    """Output-relative for files under the output folder (the browser never learns this machine's layout)."""
    try:
        root = _output_root()
        if os.path.commonpath([root, os.path.realpath(path)]) == root:
            return os.path.relpath(path, root).replace(os.sep, "/")
    except (ValueError, ImportError):
        pass
    return path


def clean_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "").strip()).strip("._") or "render"
    return re.sub(r"\.exr$", "", base, flags=re.IGNORECASE)


def parse_frames(text: str, count: int, start: int) -> list[int]:
    """'' -> start, start+1 ...; '1001-1010, 1020' -> exactly ``count`` distinct numbers or a refusal."""
    s = str(text or "").strip()
    if not s:
        return [int(start) + i for i in range(count)]
    out: list[int] = []
    for part in re.split(r"[,\s]+", s):
        if not part:
            continue
        m = re.fullmatch(r"(-?\d+)(?:-(-?\d+)(?:x(\d+))?)?", part)
        if not m:
            raise WriteError(f"NukeMax Write EXR Pro: frame_numbers {part!r} is not a number or a range (1001-1010, "
                             "1001-1020x2).")
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) is not None else a
        step = int(m.group(3) or 1)
        if b < a or step < 1:
            raise WriteError(f"NukeMax Write EXR Pro: frame range {part!r} runs backwards.")
        out.extend(range(a, b + 1, step))
    if len(out) != len(set(out)):
        raise WriteError("NukeMax Write EXR Pro: frame_numbers repeats a frame - each frame needs its own number.")
    if len(out) != count:
        raise WriteError(f"NukeMax Write EXR Pro: frame_numbers gives {len(out)} frame(s) for {count} image(s) - "
                         "give one number per image, or leave it empty to count from frame_start.")
    return out


def frame_file(name: str, frame: int, padding: int, pattern: str) -> str:
    sep = "_" if pattern.startswith("name_") else "."
    num = f"{abs(frame):0{max(1, int(padding))}d}"
    return f"{name}{sep}{'-' if frame < 0 else ''}{num}.exr"


def next_version(directory: str, name: str) -> int:
    rx = re.compile(rf"^{re.escape(name)}_v(\d{{3,}})$")
    found = [int(m.group(1)) for e in (os.listdir(directory) if os.path.isdir(directory) else ())
             if (m := rx.match(e))]
    return max(found, default=0) + 1


def _metadata(text: str) -> dict:
    s = str(text or "").strip()
    if not s:
        return {}
    try:
        m = json.loads(s)
    except json.JSONDecodeError as exc:
        raise WriteError(f"NukeMax Write EXR Pro: metadata is not JSON ({exc.msg} at character {exc.pos}).") from exc
    return m if isinstance(m, dict) else {"value": m}


def _fps(fps: float, meta: dict):
    from fractions import Fraction
    if float(fps or 0) > 0:
        return Fraction(float(fps)).limit_denominator(1001000)
    raw = (meta.get("media") or {}).get("fps") if isinstance(meta.get("media"), dict) else None
    try:
        if raw:
            f = Fraction(str(raw))
            return f if 0 < f <= 1000 else None
    except (ValueError, ZeroDivisionError):
        return None
    return None


def header_attributes(meta: dict, mode: str) -> tuple[list[tuple], list[str]]:
    """(name, value[, typedesc]) for the source header's attributes that can be carried, and the ones that cannot."""
    if mode != METADATA_MODES[0]:
        return [], []
    src = meta.get("header") if isinstance(meta.get("header"), dict) else {}
    keep, skipped = [], []
    for k, v in src.items():
        key = str(k)
        low = key.lower()
        if low in _STRUCTURAL or low.startswith(("oiio:", "openexr:", "nukemax:")):
            continue
        if isinstance(v, bool):
            keep.append((key, int(v)))
        elif isinstance(v, (int, float, str)):
            keep.append((key, v))
        elif isinstance(v, list) and len(v) == 16 and all(isinstance(x, (int, float)) for x in v):
            keep.append((key, tuple(float(x) for x in v), "matrix"))
        else:
            skipped.append(key)
    return keep, skipped


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _plan_passes(passes, wanted: str, size: tuple[int, int], count: int) -> list[dict]:
    """The passes to write: [{key, kind, channels (file names), alpha}], the beauty's own layer left out."""
    if passes is None or getattr(passes, "c2c_type", None) != "C2C_EXR_PASSES" or not passes.layers():
        if str(wanted or "").strip() and passes is not None:
            raise WriteError("NukeMax Write EXR Pro: passes_to_write names passes, but the passes input is empty.")
        return []
    info = {lay["key"]: lay for lay in passes.to_dict().get("layers", [])}
    used = str(getattr(passes, "layer_used", "") or "")
    names = [k.strip() for k in str(wanted or "").split(",") if k.strip()]
    if names:
        low = {k.lower(): k for k in info}
        missing = [n for n in names if n not in info and n.lower() not in low]
        if missing:
            raise WriteError(f"NukeMax Write EXR Pro: no pass {', '.join(map(repr, missing))} in the bundle - it has "
                             f"{', '.join(info)}.")
        keys = [n if n in info else low[n.lower()] for n in names]
    else:
        keys = [k for k in info if k != used and k.lower() not in ("rgba", "rgb")]
    if len(passes) != count:
        raise WriteError(f"NukeMax Write EXR Pro: the passes bundle has {len(passes)} frame(s), the image {count} - "
                         "write the same frames (one Read EXR Pro feeds both).")
    out = []
    for k in keys:
        lay = info[k]
        out.append({"key": k, "kind": lay.get("kind", "colour"), "data": bool(lay.get("data")),
                    "channels": list(lay.get("channels") or []), "alpha": lay.get("alpha") or ""})
    return out


class NukeMax_WriteEXRPro:
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING", "INT", "STRING", "STRING")
    RETURN_NAMES = ("manifest", "written_paths", "frame_count", "backend", "metadata_report")
    DESCRIPTION = ("Writes EXR frames safely: half / float (data passes stay float), any compression, single part or "
                   "multipart with passes, OCIO colour conversion, a new version folder by default and overwrite only "
                   "when asked, atomic writes, a manifest with SHA-256 - and it lists exactly the files it wrote.")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "output_dir": ("STRING", {"default": DEFAULT_DIR, "tooltip": "A folder inside ComfyUI's output folder, "
                                          "or an absolute path (a server reachable from other machines: only inside "
                                          "the C2C media roots)."}),
                "filename": ("STRING", {"default": "shot"}),
                "frame_pattern": (list(PATTERNS), {"default": PATTERNS[0]}),
                "frame_start": ("INT", {"default": 1001, "min": -999999, "max": 9999999}),
                "padding": ("INT", {"default": 4, "min": 1, "max": 10}),
                "bit_depth": (list(BIT_DEPTHS), {"default": BIT_DEPTHS[0]}),
                "compression": (list(COMPRESSIONS), {"default": "zip"}),
                "layout": (list(LAYOUTS), {"default": LAYOUTS[0]}),
                "versioning": (list(VERSIONING), {"default": VERSIONING[0], "tooltip": "A new name_v### folder per "
                                                  "write (never touches an earlier one), or plain names in output_dir."}),
                "overwrite": ("BOOLEAN", {"default": False, "tooltip": "Replace files that already exist. Off: a write "
                                          "that would replace a file is refused, naming it."}),
                "sidecar": ("BOOLEAN", {"default": True, "tooltip": "Also write the manifest as <name>.manifest.json."}),
            },
            "optional": {
                "alpha": ("MASK",),
                "passes": ("C2C_EXR_PASSES", {"tooltip": "The pass bundle of NukeMax Read EXR Pro / EXR Pass Reader."}),
                "metadata": ("STRING", {"forceInput": True, "tooltip": "Read EXR Pro / Metadata Reader Pro metadata: "
                                        "its source header is embedded, its fps used."}),
                "frame_numbers": ("STRING", {"default": "", "tooltip": "Frame mapping, e.g. 1001-1010, 1020 or "
                                             "1001-1019x2 (one number per image). Empty: count from frame_start."}),
                "version": ("INT", {"default": 0, "min": 0, "max": 9999, "tooltip": "0 = the next free version; a "
                                    "number = exactly that version (refused if it exists, unless overwrite)."}),
                "passes_to_write": ("STRING", {"default": "", "tooltip": "Comma-separated pass names; empty = every "
                                               "pass in the bundle."}),
                "data_passes_float": ("BOOLEAN", {"default": True, "tooltip": "Depth, position, normal, motion and "
                                                  "other data passes stay 32-bit float when the beauty is half."}),
                "alpha_mode": (list(ALPHA_MODES), {"default": ALPHA_MODES[0], "tooltip": "EXR stores premultiplied "
                                                   "(associated) alpha: premultiply a straight image here."}),
                "colour_space": ("STRING", {"default": "", "tooltip": "The colour space of the written pixels, stored "
                                            "in the header (e.g. ACEScg). Empty = none stored."}),
                "convert_from": ("STRING", {"default": "", "tooltip": "OCIO: convert the colour channels from this "
                                            "space to colour_space before writing (data passes never). Empty = no "
                                            "conversion."}),
                "ocio_config": ("STRING", {"default": "", "tooltip": "OCIO config file; empty = $OCIO, else the "
                                           "built-in studio config."}),
                "fps": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1000.0, "step": 0.001, "tooltip": "Written as "
                                  "FramesPerSecond; 0 = the metadata's rate, else none."}),
                "embed_metadata": (list(METADATA_MODES), {"default": METADATA_MODES[0]}),
            },
        }

    # ------------------------------------------------------------------ execute
    def execute(self, image, output_dir=DEFAULT_DIR, filename="shot", frame_pattern=PATTERNS[0], frame_start=1001,
                padding=4, bit_depth=BIT_DEPTHS[0], compression="zip", layout=LAYOUTS[0], versioning=VERSIONING[0],
                overwrite=False, sidecar=True, alpha=None, passes=None, metadata=None, frame_numbers="", version=0,
                passes_to_write="", data_passes_float=True, alpha_mode=ALPHA_MODES[0], colour_space="",
                convert_from="", ocio_config="", fps=0.0, embed_metadata=METADATA_MODES[0]):
        oiio = _oiio()
        if image.ndim == 3:
            image = image.unsqueeze(0)
        n, h, w = int(image.shape[0]), int(image.shape[1]), int(image.shape[2])
        if compression not in COMPRESSIONS:
            raise WriteError(f"NukeMax Write EXR Pro: unknown compression {compression!r} - use one of "
                             f"{', '.join(COMPRESSIONS)}.")
        name = clean_name(filename)
        frames = parse_frames(frame_numbers, n, frame_start)
        meta = _metadata(metadata)
        plan = _plan_passes(passes, passes_to_write, (h, w), n)
        a = None
        if alpha is not None:
            a = alpha if alpha.ndim == 3 else alpha.unsqueeze(0)
            if tuple(a.shape[1:]) != (h, w):
                raise WriteError(f"NukeMax Write EXR Pro: the alpha is {a.shape[2]}x{a.shape[1]}, the image {w}x{h}.")
            if a.shape[0] not in (1, n):
                raise WriteError(f"NukeMax Write EXR Pro: {a.shape[0]} alpha frame(s) for {n} image(s).")
        half = bit_depth == BIT_DEPTHS[0]
        multipart = layout == LAYOUTS[1]
        cs_out, cs_in = str(colour_space or "").strip(), str(convert_from or "").strip()
        if cs_in and not cs_out:
            raise WriteError("NukeMax Write EXR Pro: convert_from needs colour_space (the space to convert to).")

        # ---- where, and what may be replaced
        base = resolve_dir(output_dir)
        versioned = versioning == VERSIONING[0]
        ver = 0
        if versioned:
            ver = int(version) if int(version or 0) > 0 else next_version(base, name)
            stem = f"{name}_v{ver:03d}"
            final_dir = os.path.join(base, stem)
        else:
            stem, final_dir = name, base
        files = [frame_file(stem, f, padding, frame_pattern) for f in frames]
        manifest_name = f"{stem}.manifest.json"
        targets = [os.path.join(final_dir, f) for f in files] + ([os.path.join(final_dir, manifest_name)]
                                                                 if sidecar else [])
        existing = [t for t in targets if os.path.exists(t)]
        if versioned and os.path.isdir(final_dir) and not overwrite:
            raise WriteError(f"NukeMax Write EXR Pro: version {ver:03d} already exists ({display_path(final_dir)}) - "
                             "set version 0 for the next free one, or turn overwrite on to replace its files.")
        if existing and not overwrite:
            raise WriteError(f"NukeMax Write EXR Pro: {len(existing)} file(s) would be replaced, e.g. "
                             f"{display_path(existing[0])} - turn overwrite on, or use versioning.")
        whole_folder = versioned and not os.path.isdir(final_dir)   # a new version: written hidden, renamed whole
        work_dir = os.path.join(base, f".~{stem}.partial-{os.getpid()}-{int(time.time() * 1000)}") if whole_folder \
            else final_dir
        os.makedirs(work_dir, exist_ok=True)

        # ---- colour (beauty + colour passes; data passes never)
        conv = None
        if cs_in and cs_in != cs_out:
            from ...utils.ocio_convert import apply_colorspace_convert

            def conv(t):  # noqa: E306
                return apply_colorspace_convert(t, cs_in, cs_out, config_path=ocio_config)
        converted = ["beauty"] if conv else []

        attrs, skipped = header_attributes(meta, embed_metadata)
        rate = _fps(fps, meta)
        src_media = meta.get("media") if isinstance(meta.get("media"), dict) else {}
        source = {k: v for k, v in (("path", meta.get("path")), ("pattern", src_media.get("pattern")),
                                    ("layer", src_media.get("layer"))) if v}
        report = {"embedded": [x[0] for x in attrs], "skipped": skipped, "writer": [], "half_overflow": 0,
                  "nan": 0, "converted": converted}
        written, temps = [], []
        try:
            for i, frame in enumerate(frames):
                rgb = image[i:i + 1, ..., :3].float()
                if conv:
                    rgb = conv(rgb)
                rgb = rgb[0].cpu().numpy()
                fa = a[0 if a.shape[0] == 1 else i].float().cpu().numpy() if a is not None else None
                if fa is not None and alpha_mode == ALPHA_MODES[1]:
                    rgb = rgb * fa[..., None]
                parts = [{"name": "rgba", "names": ["R", "G", "B"] + (["A"] if fa is not None else []),
                          "planes": [rgb[..., 0], rgb[..., 1], rgb[..., 2]] + ([fa] if fa is not None else []),
                          "float": [False] * (4 if fa is not None else 3)}]
                for p in plan:
                    arr = passes.read(p["key"], [i])[0].astype(np.float32)
                    if arr.shape[:2] != (h, w):
                        raise WriteError(f"NukeMax Write EXR Pro: pass {p['key']!r} is {arr.shape[1]}x{arr.shape[0]}, "
                                         f"the image {w}x{h}.")
                    if conv and not p["data"]:
                        arr = np.concatenate([conv(torch.from_numpy(arr[None, ..., :3]))[0].numpy(), arr[..., 3:]], -1)
                        if p["key"] not in converted:
                            converted.append(p["key"])
                    chans = p["channels"] or [f"{p['key']}.R", f"{p['key']}.G", f"{p['key']}.B"]
                    planes = [arr[..., min(k, arr.shape[-1] - 1)] for k in range(len(chans))]
                    names = list(chans)
                    # only the pass's OWN alpha (diffuse.A): a layer that reports the main 'A' would write it twice,
                    # and two channels of one name make OpenEXR mix up the planes (found by the round-trip test)
                    if p["alpha"] and arr.shape[-1] > 3 and p["alpha"].lower().startswith(p["key"].lower() + "."):
                        names.append(p["alpha"])
                        planes.append(arr[..., 3])
                    keep_float = bool(data_passes_float and p["data"])
                    parts.append({"name": p["key"], "names": names, "planes": planes,
                                  "float": [keep_float] * len(names)})
                for part in parts:                                # what half cannot hold, said - never hidden
                    for plane, is_float in zip(part["planes"], part["float"]):
                        report["nan"] += int(np.isnan(plane).sum())
                        if half and not is_float:
                            report["half_overflow"] += int((np.abs(plane) > HALF_MAX).sum())
                if not multipart:
                    parts = [{"name": "", "names": [x for pt in parts for x in pt["names"]],
                              "planes": [x for pt in parts for x in pt["planes"]],
                              "float": [x for pt in parts for x in pt["float"]]}]
                final = os.path.join(final_dir, files[i])
                tmp = os.path.join(work_dir, files[i]) if whole_folder else \
                    os.path.join(work_dir, f".~{files[i][:-4]}.{os.getpid()}.exr")
                temps.append(tmp)
                writer_keys = self._write(oiio, tmp, parts, w, h, half, compression, attrs, rate, cs_out, frame,
                                          source)
                if not report["writer"]:
                    report["writer"] = writer_keys
                if not whole_folder:
                    os.replace(tmp, final)                          # atomic per file
                    temps.remove(tmp)
                written.append(final)
            channels = [x for pt in parts for x in pt["names"]]
            man = {"schema": SCHEMA, "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                   "directory": display_path(final_dir), "version": ver or None,
                   "pattern": f"{stem}{'_' if frame_pattern.startswith('name_') else '.'}"
                              f"{'#' * max(1, int(padding))}.exr",
                   "frames": frames, "frame_count": n, "size": [w, h], "layout": "multipart" if multipart else
                   "single part", "parts": [pt["name"] or "(single)" for pt in parts], "channels": channels,
                   "pixel_type": "half" if half else "float",
                   "float_channels": [x for pt in parts for x, f in zip(pt["names"], pt["float"]) if f or not half],
                   "compression": compression, "colour_space": cs_out or None, "converted_from": cs_in or None,
                   "converted": converted, "alpha": None if a is None else alpha_mode,
                   "fps": f"{rate.numerator}/{rate.denominator}" if rate else None, "source": source,
                   "half_overflow": report["half_overflow"], "nan": report["nan"], "overwrite": bool(overwrite)}
            if whole_folder:
                man_files = [os.path.join(work_dir, f) for f in files]
            else:
                man_files = written
            man["files"] = [{"file": os.path.basename(p), "frame": fr, "bytes": os.path.getsize(p),
                             "sha256": _sha256(p)} for p, fr in zip(man_files, frames)]
            text = json.dumps(man, indent=2)
            if sidecar:
                mp = os.path.join(work_dir, manifest_name if whole_folder else f".~{manifest_name}.{os.getpid()}")
                with open(mp, "w", encoding="utf-8") as f:
                    f.write(text)
                if not whole_folder:
                    os.replace(mp, os.path.join(final_dir, manifest_name))
            if whole_folder:
                os.replace(work_dir, final_dir)                     # the whole version appears at once
                temps.clear()
        except BaseException:
            for t in temps:                                         # only what THIS write created
                try:
                    os.remove(t)
                except OSError:
                    pass
            if whole_folder:
                for f in os.listdir(work_dir) if os.path.isdir(work_dir) else ():
                    try:
                        os.remove(os.path.join(work_dir, f))
                    except OSError:
                        pass
                try:
                    os.rmdir(work_dir)
                except OSError:
                    pass
            raise

        # ---- confirm: re-open each file, compare its hash with the manifest
        confirmed = []
        for p, entry in zip(written, man["files"]):
            inp = oiio.ImageInput.open(p)
            if inp is None:
                raise WriteError(f"NukeMax Write EXR Pro: {display_path(p)} was written but cannot be re-opened: "
                                 f"{oiio.geterror()}")
            ok = (inp.spec().width, inp.spec().height) == (w, h)
            inp.close()
            if not ok or _sha256(p) != entry["sha256"]:
                raise WriteError(f"NukeMax Write EXR Pro: {display_path(p)} does not match what was written.")
            confirmed.append(display_path(p))
        stale = []
        if not versioned and overwrite:                     # earlier frames of the same name, left as they were
            rx = re.compile(rf"^{re.escape(stem)}[._]-?\d+\.exr$")
            stale = sorted(f for f in os.listdir(final_dir) if rx.match(f) and f not in files)
        backend = f"OpenImageIO {oiio.VERSION_STRING} (OpenEXR)" + (" + OpenColorIO" if conv else "")
        rep = dict(report, stale_frames_kept=stale[:50], stale_count=len(stale))
        summary = self._summary(man, confirmed, rep, sidecar, stem)
        return {"ui": {"text": [summary]},
                "result": (text, "\n".join(confirmed), n, backend, json.dumps(rep, indent=2))}

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _write(oiio, path, parts, w, h, half, compression, attrs, rate, cs_out, frame, source) -> list[str]:
        specs = []
        writer_keys = ["Software", "nukemax:frame"] + (["FramesPerSecond"] if rate else []) + \
            (["oiio:ColorSpace", "nukemax:colourSpace"] if cs_out else []) + (["nukemax:source"] if source else [])
        for pt in parts:
            spec = oiio.ImageSpec(w, h, len(pt["names"]), "half" if half else "float")
            spec.channelnames = tuple(pt["names"])
            spec.channelformats = tuple(oiio.TypeDesc("float" if (f or not half) else "half") for f in pt["float"])
            if "A" in pt["names"]:
                spec.alpha_channel = pt["names"].index("A")
            spec.attribute("compression", compression)
            if pt["name"]:
                spec.attribute("name", pt["name"])
            for item in attrs:
                try:
                    if len(item) == 3:
                        spec.attribute(item[0], oiio.TypeDesc(item[2]), item[1])
                    else:
                        spec.attribute(item[0], item[1])
                except Exception:  # noqa: BLE001 - one odd source attribute never fails a write
                    pass
            spec.attribute("Software", "NukeMax Write EXR Pro")
            spec.attribute("nukemax:frame", int(frame))
            if rate:
                spec.attribute("FramesPerSecond", oiio.TypeDesc("rational"), (int(rate.numerator),
                                                                              int(rate.denominator)))
            if cs_out:                       # OpenImageIO 3 stores ITS interop id (ACEScg -> lin_ap1_scene) ...
                spec.attribute("oiio:ColorSpace", cs_out)
                spec.attribute("nukemax:colourSpace", cs_out)   # ... so the exact name is kept beside it
            if source:
                spec.attribute("nukemax:source", json.dumps(source))
            specs.append(spec)
        out = oiio.ImageOutput.create(path)
        if out is None:
            raise WriteError(f"NukeMax Write EXR Pro: OpenImageIO has no EXR writer: {oiio.geterror()}")
        try:
            if len(specs) > 1 and not out.supports("multiimage"):
                raise WriteError("NukeMax Write EXR Pro: this OpenImageIO cannot write multipart EXR - use single part.")
            ok = out.open(path, tuple(specs)) if len(specs) > 1 else out.open(path, specs[0])
            if not ok:
                raise WriteError(f"NukeMax Write EXR Pro: cannot open {os.path.basename(path)} for writing: "
                                 f"{out.geterror()}")
            for k, (pt, spec) in enumerate(zip(parts, specs)):
                if k and not out.open(path, spec, "AppendSubimage"):
                    raise WriteError(f"NukeMax Write EXR Pro: cannot add part {pt['name']!r}: {out.geterror()}")
                buf = np.ascontiguousarray(np.stack(pt["planes"], axis=-1), dtype=np.float32)
                if not out.write_image(buf):
                    raise WriteError(f"NukeMax Write EXR Pro: writing {os.path.basename(path)} failed: "
                                     f"{out.geterror()}")
        finally:
            out.close()
        return writer_keys

    @staticmethod
    def _summary(man, confirmed, rep, sidecar, stem) -> str:
        fr = man["frames"]
        span = f"{fr[0]}" if len(fr) == 1 else f"{fr[0]}-{fr[-1]}"
        lines = [f"wrote {len(confirmed)} file(s) to {man['directory']}/",
                 f"frames {span} | {man['pixel_type']} | {man['compression']} | {man['layout']} | "
                 f"{len(man['channels'])} channels",
                 "half overflow: " + (f"{rep['half_overflow']} value(s) above 65504 stored as infinity"
                                      if rep["half_overflow"] else "none")
                 + (f"  |  NaN: {rep['nan']}" if rep["nan"] else "")
                 + (f"  |  colour: {man['converted_from']} -> {man['colour_space']}" if man["converted_from"] else
                    (f"  |  colour space: {man['colour_space']}" if man["colour_space"] else ""))]
        if sidecar:
            lines.append(f"manifest: {stem}.manifest.json")
        if rep.get("stale_count"):
            lines.append(f"note: {rep['stale_count']} older frame(s) of this name are still in the folder")
        lines += confirmed[:12] + ([f"... and {len(confirmed) - 12} more"] if len(confirmed) > 12 else [])
        return "\n".join(lines)


NODE_CLASS_MAPPINGS = {"NukeMax_WriteEXRPro": NukeMax_WriteEXRPro}
NODE_DISPLAY_NAME_MAPPINGS = {"NukeMax_WriteEXRPro": "NukeMax Write EXR Pro"}
