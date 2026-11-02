"""NukeMax EXR Metadata Reader Pro and NukeMax EXR Pass Reader (owner Rev 3 Part 19.5 / 19.6; ledger L9.80 slice 2).

Both pick their file like NukeMax Read EXR Pro (the input folder with its Upload EXR button, or a server path held to
the C2C media roots) and run on the vendored C2C media engine.

- Metadata Reader Pro reads HEADERS ONLY (no pixel is decoded): size, display and data windows, channels with their
  types, compression, parts, bit depth, colour information, timecode / frame metadata - as JSON, as separate outputs,
  and as a readable summary on the node.
- Pass Reader loads a multipart / multilayer EXR (or its sequence): the beauty, every pass as one bundle (channel
  names, types and metadata kept; NukeMax Shuffle Pass takes any pass from it), the pass names, and up to four named
  passes as their own outputs - each decoded only when asked for.
Original nodes, GPL-3.0-only.
"""
from __future__ import annotations

import json

import torch

from ...vendor.c2c_core.video import exr as _exr
from . import read_exr_pro as RP

FILE_MODES = ("file (input folder)", "server path")


def _windows(path: str) -> list[dict]:
    """Per part: data window, display window, channel formats, compression, timecode, colour - header only."""
    import OpenImageIO as oiio  # type: ignore[import-not-found]
    inp = oiio.ImageInput.open(path)
    if inp is None:
        raise RuntimeError(f"cannot open {path}: {oiio.geterror()}")
    out = []
    try:
        i = 0
        while inp.seek_subimage(i, 0):
            s = inp.spec()
            fmts = [str(f) for f in s.channelformats] if len(s.channelformats) == len(s.channelnames) \
                else [str(s.format)] * len(s.channelnames)
            get = lambda k: s.getattribute(k)  # noqa: E731
            out.append({
                "part": i, "name": str(get("name") or "") or None,
                "data_window": [int(s.x), int(s.y), int(s.x + s.width - 1), int(s.y + s.height - 1)],
                "display_window": [int(s.full_x), int(s.full_y), int(s.full_x + s.full_width - 1),
                                   int(s.full_y + s.full_height - 1)],
                "channels": [{"name": str(n), "type": f} for n, f in zip(s.channelnames, fmts)],
                "compression": str(get("compression") or "") or None,
                "timecode": str(get("smpte:TimeCode") or get("timeCode") or "") or None,
                "frame": get("frame") if get("frame") is not None else None,
                "colour": {k: _exr._json_value(get(k)) for k in ("oiio:ColorSpace", "chromaticities", "whiteLuminance")
                           if get(k) is not None},
                "deep": bool(s.deep),
            })
            i += 1
    finally:
        inp.close()
    return out


def header_report(path: str) -> dict:
    info = _exr.inspect_image(path)
    parts = _windows(path)
    first = parts[0] if parts else {}
    fmts = sorted({c["type"] for p in parts for c in p["channels"]})
    return {
        "file": info.path, "width": info.width, "height": info.height, "part_count": len(parts),
        "bit_depth": fmts, "data_window": first.get("data_window"), "display_window": first.get("display_window"),
        "compression": first.get("compression"), "timecode": first.get("timecode"), "frame": first.get("frame"),
        "colour": first.get("colour", {}), "deep": info.deep, "fps": str(info.fps) if info.fps else None,
        "parts": parts, "layers": [lay.to_dict() for lay in info.layers], "header": info.header,
    }


def summary(r: dict) -> str:
    lines = [f"{r['width']} x {r['height']}  |  parts {r['part_count']}  |  {', '.join(r['bit_depth'])}  |  "
             f"compression {r['compression'] or '-'}  |  timecode {r['timecode'] or '-'}",
             f"data window {r['data_window']}  |  display window {r['display_window']}"]
    for p in r["parts"]:
        lines.append(f"part {p['part']}{' ' + p['name'] if p['name'] else ''}: "
                     + ", ".join(f"{c['name']}({c['type']})" for c in p["channels"]))
    lines.append("layers: " + ", ".join(f"{lay['key']} [{lay['kind']}]" for lay in r["layers"]))
    return "\n".join(lines)


def _file_inputs():
    files = RP.input_exr_files() or [""]
    return {"file": (files, {"tooltip": "An EXR in the input folder (Upload EXR on NukeMax Read EXR Pro)."}),
            "mode": (list(FILE_MODES), {"default": FILE_MODES[0]})}


class NukeMax_EXRMetadataReaderPro:
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING", "INT", "INT", "INT", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("metadata", "width", "height", "part_count", "channels", "compression", "timecode")
    OUTPUT_NODE = True
    DESCRIPTION = ("Reads an EXR's headers WITHOUT decoding pixels: size, display / data window, channels and their "
                   "types, compression, parts, bit depth, colour information, timecode - JSON, outputs and a summary.")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": _file_inputs(), "optional": {"server_path": ("STRING", {"default": ""})}}

    @classmethod
    def IS_CHANGED(cls, file="", mode=FILE_MODES[0], server_path=""):
        try:
            return RP.fingerprint(RP.resolve(mode, file, server_path), "file (input folder)")
        except Exception as exc:  # noqa: BLE001
            return f"error|{exc}"

    def execute(self, file="", mode=FILE_MODES[0], server_path=""):
        r = header_report(RP.resolve(mode, file, server_path))
        if mode != "server path":
            r["file"] = RP.rel_to_input(r["file"])            # the input-relative name, not this machine's path
        chans = ", ".join(c["name"] for p in r["parts"] for c in p["channels"])
        out = (json.dumps(r, indent=2, default=str), int(r["width"]), int(r["height"]), int(r["part_count"]), chans,
               str(r["compression"] or ""), str(r["timecode"] or ""))
        return {"ui": {"text": [summary(r)]}, "result": out}


class NukeMax_EXRPassReader:
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "C2C_EXR_PASSES", "STRING", "STRING", "IMAGE", "IMAGE", "IMAGE", "IMAGE")
    RETURN_NAMES = ("beauty", "passes", "pass_names", "metadata", "pass_1", "pass_2", "pass_3", "pass_4")
    DESCRIPTION = ("Loads a multipart / multilayer EXR (or its sequence): the beauty, every pass as one bundle (Shuffle "
                   "Pass takes any of them), the pass names, and up to four named passes as their own outputs.")

    @classmethod
    def INPUT_TYPES(cls):
        req = {"file": RP.NukeMax_ReadEXRPro.INPUT_TYPES()["required"]["file"],
               "mode": (list(RP.MODES), {"default": RP.MODES[0]})}
        for k in range(1, 5):
            req[f"pass_{k}"] = ("STRING", {"default": "", "tooltip": f"A pass name for output pass_{k} (pass_names "
                                                                     "lists them); empty = that output is not read."})
        return {"required": req, "optional": {"frame_range": ("STRING", {"default": ""}),
                                              "server_path": ("STRING", {"default": ""})}}

    @classmethod
    def IS_CHANGED(cls, file="", mode=RP.MODES[0], frame_range="", server_path="", **kw):
        return f"{RP.NukeMax_ReadEXRPro.IS_CHANGED(file, mode, 'auto', frame_range, server_path)}|" + \
            "|".join(str(kw.get(f"pass_{k}", "")) for k in range(1, 5))

    def execute(self, file="", mode=RP.MODES[0], pass_1="", pass_2="", pass_3="", pass_4="", frame_range="",
                server_path=""):
        res = RP.NukeMax_ReadEXRPro().execute(file=file, mode=mode, layer="auto", frame_range=frame_range,
                                              server_path=server_path)["result"]
        beauty, _alpha, passes, meta, _n = res
        names = passes.layers() if hasattr(passes, "layers") else []
        outs = []
        for want in (pass_1, pass_2, pass_3, pass_4):
            w = str(want or "").strip()
            if not w:
                outs.append(torch.zeros((1, 1, 1, 3)))
                continue
            match = w if w in names else next((k for k in names if k.lower() == w.lower()), None)
            if match is None:
                raise ValueError(f"NukeMax EXR Pass Reader: no pass '{w}' - this EXR has: {', '.join(names)}.")
            arr = torch.from_numpy(passes.read(match)).float()             # raw float, every frame
            outs.append(arr[..., :3].contiguous() if arr.shape[-1] >= 3 else arr[..., :1].repeat(1, 1, 1, 3))
        return (beauty, passes, "\n".join(names), meta, *outs)


NODE_CLASS_MAPPINGS = {"NukeMax_EXRMetadataReaderPro": NukeMax_EXRMetadataReaderPro,
                       "NukeMax_EXRPassReader": NukeMax_EXRPassReader}
NODE_DISPLAY_NAME_MAPPINGS = {"NukeMax_EXRMetadataReaderPro": "NukeMax EXR Metadata Reader Pro",
                              "NukeMax_EXRPassReader": "NukeMax EXR Pass Reader"}
