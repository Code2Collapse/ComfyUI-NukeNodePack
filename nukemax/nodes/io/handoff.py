"""NukeMax Handoff (Nuke / Resolve) - the DCC handoff of owner Rev 3 Part 19.16 (ledger L9.80 slice 8).

"Do not assume a handoff is complete merely because an EXR file was written." The node takes the manifests of NukeMax's
writers (Write EXR Pro, Write, OCIO Write), RE-HASHES every file they name against them, and only then writes a
versioned, atomic package <output>/<name>_handoff_v###/:
  handoff.json      outputs (kind, pattern, frame range, fps, size, channels, pixel type, compression, colour
                    interpretation + OCIO config), shot facts, package files, tool versions
  <name>.nk         a Nuke script: Root (frames, fps, format, OCIO colour management) + one Read per output
  <name>.otio       OpenTimelineIO (Resolve imports it): one clip per output, image sequence / movie references
  contact_sheet.png first / middle / last frame of each output, read back from the written files
  ocio/             the OCIO config when it is a file (and its search-path folders); a built-in URI is recorded
  README.txt        what each file is
Original node, GPL-3.0-only.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from fractions import Fraction

import numpy as np
import torch

from . import _safe_write as SW

NAME = "NukeMax Handoff"
SCHEMA = "nukemax.handoff/1"
DEFAULT_DIR = "nukemax_handoff"
VERSIONING = ("new version folder (name_v###)", "none (plain names)")


class HandoffError(SW.WriteError):
    pass


def _abs_dir(directory: str) -> str:
    d = str(directory or "")
    return d if os.path.isabs(d) else os.path.join(SW._output_root(), d)


def _fps(v) -> Fraction:
    try:
        f = Fraction(str(v)) if v else Fraction(24)
        return f if f > 0 else Fraction(24)
    except (ValueError, ZeroDivisionError):
        return Fraction(24)


def read_manifest(text: str, slot: str) -> dict:
    try:
        m = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise HandoffError(f"{NAME}: {slot} is not a writer manifest (not JSON).") from exc
    if not isinstance(m, dict) or "files" not in m or "directory" not in m:
        raise HandoffError(f"{NAME}: {slot} is not a writer manifest (connect Write EXR Pro / Write / OCIO Write's "
                           "manifest output).")
    return m


def verify(m: dict, slot: str) -> tuple[str, list[str]]:
    """Every file the manifest names: present, same size, same SHA-256. Returns (folder, absolute files)."""
    d = _abs_dir(m["directory"])
    paths = []
    for e in m["files"]:
        p = os.path.join(d, e["file"])
        if not os.path.isfile(p):
            raise HandoffError(f"{NAME}: {slot}: {SW.display_path(p)} is missing - the handoff stops here.")
        if os.path.getsize(p) != e.get("bytes", os.path.getsize(p)) or SW.sha256(p) != e.get("sha256"):
            raise HandoffError(f"{NAME}: {slot}: {SW.display_path(p)} is not the file that was written (its hash "
                               "differs) - write it again.")
        paths.append(p)
    return d, paths


def describe(m: dict, folder: str, files: list[str], cfg: dict) -> dict:
    pattern = m.get("pattern") or os.path.basename(files[0])
    seq = "#" in pattern
    ext = os.path.splitext(pattern)[1].lower()
    kind = ("exr_sequence" if ext == ".exr" else "image_sequence") if seq else \
        ("movie" if ext in (".mov", ".mp4", ".mkv") else "still")
    frames = [int(x) for x in m.get("frames") or []]
    step = (frames[1] - frames[0]) if len(frames) > 1 else 1
    regular = all(b - a == step for a, b in zip(frames, frames[1:])) if frames else True
    pad = len(re.search(r"#+", pattern).group(0)) if seq else 0
    colour = {"space": m.get("colour_space") or (m.get("ocio") or {}).get("output_space"),
              "converted_from": m.get("converted_from") or (m.get("ocio") or {}).get("input_space"),
              "config": cfg}
    # a movie is ONE file holding many frames: its count is the manifest's frame count, never the file count (L9.80
    # slice 8, live: the ProRes clip came out 1 frame long in Nuke and OTIO)
    count = len(m["files"]) if seq or kind == "still" else int(m.get("frame_count") or m.get("frames_written") or
                                                               len(frames) or 1)
    out = {"kind": kind, "pattern": os.path.join(folder, pattern).replace("\\", "/"),
           "pattern_relative": SW.display_path(os.path.join(folder, pattern)).replace("\\", "/"),
           "first": frames[0] if frames else 1, "last": frames[-1] if frames else 1, "count": count,
           "frames": frames[:2000], "step": step, "regular": regular, "padding": pad,
           "fps": str(_fps(m.get("fps"))), "size": m.get("size"), "channels": m.get("channels"),
           "pixel_type": m.get("pixel_type") or m.get("bit_depth"), "compression": m.get("compression") or
           m.get("codec"), "colour": colour, "source": m.get("source"), "verified_files": len(files),
           "writer_schema": m.get("schema")}
    if kind == "movie":
        out.update({"codec": m.get("codec"), "audio": m.get("audio"), "file": files[0].replace("\\", "/")})
    if not regular:
        out["note"] = "frame numbers are not evenly spaced: the Nuke Read holds the nearest frame in the gaps"
    return out


def ocio_facts(path: str) -> dict:
    if not path:
        return {}
    from ..ocio import config_manager as CM
    f = {"source": CM.source_kind(path), "path": path, "fingerprint": CM.fingerprint(path)}
    try:
        cfg = CM.load(path)
        f["working_space"] = cfg.getRoleColorSpace("scene_linear") or ""
        f["name"] = cfg.getName() or os.path.basename(path)
    except Exception as exc:  # noqa: BLE001 - recorded, the handoff still names the config
        f["error"] = str(exc)[:200]
    return f


def _q(s: str) -> str:
    return '"' + str(s).replace("\\", "/").replace('"', '\\"') + '"'


def nuke_script(name: str, outs: list[dict], cfg: dict) -> str:
    first = min(o["first"] for o in outs)
    last = max(o["last"] for o in outs)
    fps = float(Fraction(outs[0]["fps"]))
    w, h = (outs[0].get("size") or [1920, 1080])[:2]
    lines = ["#! nuke", "version 15.0 v1", "Root {", " inputs 0", f" name {_q(name + '.nk')}",
             f" first_frame {first}", f" last_frame {last}", f" fps {fps:g}",
             f" format \"{w} {h} 0 0 {w} {h} 1 {name}_format\""]
    if cfg.get("path"):
        lines += [" colorManagement OCIO", " OCIO_config custom", f" customOCIOConfigPath {_q(cfg['path'])}"]
        if cfg.get("working_space"):
            lines.append(f" workingSpaceLUT {_q(cfg['working_space'])}")
    lines.append("}")
    for k, o in enumerate(outs):
        ow, oh = (o.get("size") or [w, h])[:2]
        mv = o["kind"] == "movie"
        f0, f1 = (1, o["count"]) if mv else (o["first"], o["last"])
        lines += ["Read {", " inputs 0", f" file {_q(o['file'] if mv else o['pattern'])}",
                  f" format \"{ow} {oh} 0 0 {ow} {oh} 1 \"", f" first {f0}", f" last {f1}",
                  f" origfirst {f0}", f" origlast {f1}", " origset true"]
        if not o.get("regular", True):
            lines.append(" on_error \"nearest frame\"")
        if o["colour"].get("space"):
            lines.append(f" colorspace {_q(o['colour']['space'])}")
        lines += [f" name Read_{k + 1}", f" label {_q(os.path.basename(o['pattern']))}",
                  f" xpos {k * 120}", " ypos 0", "}"]
    return "\n".join(lines) + "\n"


def _rt(value, rate):
    return {"OTIO_SCHEMA": "RationalTime.1", "rate": float(rate), "value": float(value)}


def _tr(start, dur, rate):
    return {"OTIO_SCHEMA": "TimeRange.1", "start_time": _rt(start, rate), "duration": _rt(dur, rate)}


def otio_timeline(name: str, outs: list[dict]) -> dict:
    clips = []
    for o in outs:
        rate = float(Fraction(o["fps"]))
        if o["kind"] == "movie":
            ref = {"OTIO_SCHEMA": "ExternalReference.1", "name": os.path.basename(o["file"]),
                   "target_url": "file:///" + o["file"].lstrip("/"), "available_range": _tr(0, o["count"], rate),
                   "metadata": {}}
            src = _tr(0, o["count"], rate)
        else:
            folder, base = os.path.split(o["pattern"])
            m = re.match(r"^(.*?)(#+)(.*)$", base)
            span = (o["last"] - o["first"]) // max(1, o["step"]) + 1
            ref = {"OTIO_SCHEMA": "ImageSequenceReference.1", "name": base,
                   "target_url_base": "file:///" + folder.lstrip("/") + "/",
                   "name_prefix": m.group(1) if m else base, "name_suffix": m.group(3) if m else "",
                   "start_frame": o["first"], "frame_step": max(1, o["step"]), "rate": rate,
                   "frame_zero_padding": len(m.group(2)) if m else 0, "missing_frame_policy": "hold",
                   "available_range": _tr(o["first"], span, rate), "metadata": {}}
            src = _tr(o["first"], span, rate)
        clips.append({"OTIO_SCHEMA": "Clip.1", "name": os.path.basename(o["pattern"]), "source_range": src,
                      "media_reference": ref, "effects": [], "markers": [], "enabled": True,
                      "metadata": {"nukemax": {k: o[k] for k in ("kind", "fps", "size", "channels", "pixel_type",
                                                                 "compression") if o.get(k) is not None} |
                                   {"colour": o["colour"].get("space")}}})
    track = {"OTIO_SCHEMA": "Track.1", "name": "V1", "kind": "Video", "children": clips, "source_range": None,
             "effects": [], "markers": [], "enabled": True, "metadata": {}}
    return {"OTIO_SCHEMA": "Timeline.1", "name": name, "global_start_time": None, "metadata": {"nukemax": {"schema": SCHEMA}},
            "tracks": {"OTIO_SCHEMA": "Stack.1", "name": "tracks", "children": [track], "source_range": None,
                       "effects": [], "markers": [], "enabled": True, "metadata": {}}}


def _thumbs(o: dict, files: list[str]) -> tuple[torch.Tensor, list[int]]:
    """First / middle / last frame of an output, read back from disk (display-ready float, sRGB for linear EXR)."""
    picks = sorted({0, len(files) // 2, len(files) - 1}) if o["kind"] != "movie" else []
    frames, nums = [], []
    if o["kind"] == "movie":
        import av
        with av.open(files[0]) as c:
            n = o["count"]
            want = sorted({0, n // 2, n - 1})
            for i, f in enumerate(c.decode(video=0)):
                if i in want:
                    frames.append(torch.from_numpy(f.to_ndarray(format="rgb24").astype(np.float32) / 255.0))
                    nums.append(i + 1)
                if i >= want[-1]:
                    break
        return (torch.stack(frames) if frames else torch.zeros(1, 8, 8, 3)), nums
    import OpenImageIO as oiio
    for k in picks:
        inp = oiio.ImageInput.open(files[k])
        arr = np.asarray(inp.read_image(oiio.FLOAT))
        inp.close()
        arr = arr.reshape(arr.shape[0], arr.shape[1], -1)
        rgb = arr[..., :3] if arr.shape[-1] >= 3 else np.repeat(arr[..., :1], 3, -1)
        frames.append(torch.from_numpy(np.ascontiguousarray(rgb, dtype=np.float32)))
        nums.append(o["frames"][k] if k < len(o["frames"]) else k)
    h = min(f.shape[0] for f in frames)
    w = min(f.shape[1] for f in frames)
    return torch.stack([f[:h, :w] for f in frames]), nums


def _copy_ocio(path: str, dest: str) -> list[str]:
    """The config file and the folders its search_path names (relative ones), into ``dest``."""
    copied = []
    if not path or path.startswith("ocio://") or not os.path.isfile(path):
        return copied
    os.makedirs(dest, exist_ok=True)
    shutil.copy2(path, os.path.join(dest, os.path.basename(path)))
    copied.append(os.path.basename(path))
    try:
        from ..ocio import config_manager as CM
        for sp in CM.load(path).getSearchPath().split(":"):
            sp = sp.strip()
            src = os.path.join(os.path.dirname(path), sp)
            if sp and not os.path.isabs(sp) and os.path.isdir(src) and ".." not in sp.replace("\\", "/").split("/"):
                shutil.copytree(src, os.path.join(dest, sp), dirs_exist_ok=True)
                copied.append(sp + "/")
    except Exception:  # noqa: BLE001 - the config is there; LUT folders are best effort and recorded
        pass
    return copied


class NukeMax_Handoff:
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("handoff", "package_dir", "nuke_script")
    DESCRIPTION = ("Hands rendered outputs to Nuke and Resolve: re-checks every written file against its manifest, "
                   "then writes a versioned package - handoff.json (frame range, channels, colour interpretation, "
                   "OCIO), a Nuke script, an OpenTimelineIO timeline, a contact sheet and the OCIO config.")

    @classmethod
    def INPUT_TYPES(cls):
        man = ("STRING", {"forceInput": True, "tooltip": "A writer's manifest (Write EXR Pro / Write / OCIO Write)."})
        return {
            "required": {
                "manifest": man,
                "name": ("STRING", {"default": "shot"}),
                "output_dir": ("STRING", {"default": DEFAULT_DIR}),
                "versioning": (list(VERSIONING), {"default": VERSIONING[0]}),
                "overwrite": ("BOOLEAN", {"default": False}),
                "nuke_script": ("BOOLEAN", {"default": True}),
                "otio_timeline": ("BOOLEAN", {"default": True, "tooltip": "OpenTimelineIO JSON; DaVinci Resolve "
                                                                         "imports it (File > Import > Timeline)."}),
                "contact_sheet": ("BOOLEAN", {"default": True}),
                "copy_ocio_config": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "manifest_2": man, "manifest_3": man, "manifest_4": man,
                "ocio_config": ("NUKEMAX_OCIO_CONFIG", {"tooltip": "From NukeMax OCIO Config Manager; else the "
                                                                   "outputs' own config, else $OCIO / built-in."}),
                "project": ("STRING", {"default": ""}), "sequence": ("STRING", {"default": ""}),
                "shot": ("STRING", {"default": ""}), "artist": ("STRING", {"default": ""}),
                "notes": ("STRING", {"default": "", "multiline": True}),
            },
        }

    def execute(self, manifest, name="shot", output_dir=DEFAULT_DIR, versioning=VERSIONING[0], overwrite=False,
                nuke_script=True, otio_timeline=True, contact_sheet=True, copy_ocio_config=True, manifest_2=None,
                manifest_3=None, manifest_4=None, ocio_config=None, project="", sequence="", shot="", artist="",
                notes=""):
        from ..ocio import config_manager as CM
        slots = [("manifest", manifest), ("manifest_2", manifest_2), ("manifest_3", manifest_3),
                 ("manifest_4", manifest_4)]
        mans = [(slot, read_manifest(t, slot)) for slot, t in slots if t]
        own = next(((m.get("ocio") or {}).get("config") for _, m in mans if (m.get("ocio") or {}).get("config")), "")
        cfg = ocio_facts(ocio_config or own or CM.default_source())
        outs, all_files = [], []
        for slot, m in mans:
            folder, files = verify(m, slot)                       # 19.16: re-checked before anything is written
            outs.append(describe(m, folder, files, cfg))
            all_files.append(files)
        stem_name = SW.clean_name(name, "")
        files_for = ["handoff.json", "README.txt"] + ([f"{stem_name}.nk"] if nuke_script else []) + \
            ([f"{stem_name}.otio"] if otio_timeline else []) + (["contact_sheet.png"] if contact_sheet else [])
        target = SW.plan(NAME, SW.resolve_dir(output_dir, NAME, DEFAULT_DIR), f"{stem_name}_handoff",
                         lambda stem: list(files_for), versioned=versioning == VERSIONING[0], overwrite=overwrite,
                         sidecar=False)
        written = []
        try:
            def put(fname, data, binary=False):
                tmp = target.temp_for(fname)
                with open(tmp, "wb" if binary else "w", encoding=None if binary else "utf-8") as f:
                    f.write(data)
                written.append(target.place(tmp, fname))
            if nuke_script:
                put(f"{stem_name}.nk", nuke_script_fn(stem_name, outs, cfg))
            if otio_timeline:
                put(f"{stem_name}.otio", json.dumps(otio_timeline_fn(stem_name, outs), indent=2))
            if contact_sheet:
                from .read_pro import contact_sheet as sheet
                tiles, nums = [], []
                for o, files in zip(outs, all_files):
                    t, n = _thumbs(o, files)
                    lin = o["kind"] == "exr_sequence" or (o.get("pixel_type") in ("half", "float"))
                    img = sheet(t, n, lin, cells=3, width=240)
                    tiles.append(img)
                import io
                from PIL import Image as PImage
                W = max(t.width for t in tiles)
                H = sum(t.height for t in tiles)
                board = PImage.new("RGB", (W, H), (18, 18, 22))
                y = 0
                for t in tiles:
                    board.paste(t, (0, y))
                    y += t.height
                buf = io.BytesIO()
                board.save(buf, "PNG")
                put("contact_sheet.png", buf.getvalue(), binary=True)
            copied = _copy_ocio(cfg.get("path", ""), os.path.join(target.work_dir, "ocio")) \
                if copy_ocio_config else []
            doc = {"schema": SCHEMA, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                   "shot": {k: v for k, v in (("project", project), ("sequence", sequence), ("shot", shot),
                                              ("artist", artist), ("notes", notes)) if str(v or "").strip()},
                   "outputs": outs, "ocio": cfg | ({"copied": ["ocio/" + c for c in copied]} if copied else {}),
                   "package": {"directory": SW.display_path(target.final_dir), "version": target.version or None,
                               "files": files_for + (["ocio/"] if copied else [])},
                   "tools": _tools(), "verified": True}
            put("handoff.json", json.dumps(doc, indent=2))
            put("README.txt", _readme(stem_name, doc, nuke_script, otio_timeline, contact_sheet, copied))
            target.commit()
        except BaseException:
            target.abort()
            raise
        lines = [f"handoff: {SW.display_path(target.final_dir)}/",
                 f"{len(outs)} output(s), {sum(o['verified_files'] for o in outs)} file(s) re-checked",
                 "colour: " + ", ".join(sorted({str(o['colour'].get('space') or '-') for o in outs})) +
                 f" | OCIO {cfg.get('source', '-')}"] + [os.path.basename(p) for p in written]
        return {"ui": {"text": ["\n".join(lines)]},
                "result": (json.dumps(doc, indent=2), SW.display_path(target.final_dir),
                           SW.display_path(target.final(f"{stem_name}.nk")) if nuke_script else "")}


nuke_script_fn = nuke_script
otio_timeline_fn = otio_timeline


def _tools() -> dict:
    out = {}
    for mod, key in (("OpenImageIO", "openimageio"), ("PyOpenColorIO", "opencolorio"), ("av", "pyav")):
        try:
            m = __import__(mod)
            out[key] = getattr(m, "__version__", getattr(m, "VERSION_STRING", "?"))
        except Exception:  # noqa: BLE001
            continue
    try:
        import tomllib
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "..", "..", "pyproject.toml"), "rb") as f:
            out["nukemax"] = tomllib.load(f).get("project", {}).get("version")
    except Exception:  # noqa: BLE001
        pass
    return out


def _readme(name, doc, nk, ot, cs, copied) -> str:
    rows = ["NukeMax handoff package", "=" * 23, "",
            f"handoff.json       outputs, frame ranges, channels, colour interpretation, OCIO config, tool versions"]
    if nk:
        rows.append(f"{name}.nk".ljust(19) + "Nuke script: File > Open (Nuke 15+ for a built-in OCIO config URI)")
    if ot:
        rows.append(f"{name}.otio".ljust(19) + "OpenTimelineIO: DaVinci Resolve File > Import > Timeline")
    if cs:
        rows.append("contact_sheet.png  first / middle / last frame of each output, read back from disk")
    if copied:
        rows.append("ocio/              the OCIO config and its LUT folders")
    rows += ["", "Every file listed in handoff.json was re-checked (SHA-256) against its writer's manifest before "
                 "this package was written.", ""]
    for o in doc["outputs"]:
        rows.append(f"- {o['kind']}: {o['pattern']}  frames {o['first']}-{o['last']} ({o['count']})  {o['fps']} fps  "
                    f"colour {o['colour'].get('space') or '-'}")
    return "\n".join(rows) + "\n"


NODE_CLASS_MAPPINGS = {"NukeMax_Handoff": NukeMax_Handoff}
NODE_DISPLAY_NAME_MAPPINGS = {"NukeMax_Handoff": "NukeMax Handoff (Nuke / Resolve)"}
