"""NukeMax OCIO Read and NukeMax OCIO Write (owner Rev 3 Part 19.10; ledger L9.80 slice 5b).

Colour-managed I/O on top of NukeMax Read / NukeMax Write and the OCIO Config Manager:
- OCIO Read: the source space is what you type, else an authored header (nukemax:colourSpace; oiio:ColorSpace for EXR),
  else the CONFIG's file rules (getColorSpaceFromFilepath) - the metadata says which; the IMAGE is converted to the
  working space (typed, else the config's scene_linear role); alpha untouched; passes as stored (said). A native VIDEO
  output carries the clip in its SOURCE space with its sound and alpha, so core video nodes get display-referred frames.
- OCIO Write: IMAGE or a native VIDEO (its frames, sound, rate and alpha); input space typed or scene_linear; output
  space typed or the config's file rule for the output format; converted, then written by NukeMax Write (EXR by Write
  EXR Pro) with the output space tagged and the OCIO facts in the manifest sidecar.
Original nodes, GPL-3.0-only.
"""
from __future__ import annotations

import json
import os
from fractions import Fraction

from ..ocio import config_manager as CM
from . import read_pro as R
from . import write_pro as W

NAME_R, NAME_W = "NukeMax OCIO Read", "NukeMax OCIO Write"
_READ_DROP = ("colour_space", "convert_to", "ocio_config")
_WRITE_DROP = ("image", "colour_space", "convert_from", "ocio_config")


def _space(cfg, name: str, label: str, who: str) -> str:
    cs = cfg.getColorSpace(name)
    if cs is None:
        near = CM.nearest(cfg, name)
        raise ValueError(f"{who}: {label} {name!r} is not in this OCIO config" +
                         (f" - did you mean {', '.join(near)}?" if near else ".") +
                         " Pick colour space… lists the config's spaces.")
    return cs.getName()


def _convert(cfg, image, src: str, dst: str):
    if src == dst:
        return image
    from ..ocio import _apply_processor
    return _apply_processor(image, cfg.getProcessor(src, dst))


def _rule_space(cfg, filepath: str) -> str:
    """The config's file-rule space for a path (PyOpenColorIO 2.5 returns (name, rule index))."""
    r = cfg.getColorSpaceFromFilepath(filepath)
    return r[0] if isinstance(r, tuple) else r


def _video(images, fps: float, audio, alpha):
    """A core native VIDEO from components (core 0.39 comfy_api); None when the core has no such API."""
    try:
        from comfy_api.input_impl import VideoFromComponents
        from comfy_api.util import VideoComponents
    except Exception:  # noqa: BLE001 - an older core: the IMAGE output still works
        return None
    aud = None
    if audio is not None:
        try:
            aud = {"waveform": audio["waveform"], "sample_rate": int(audio["sample_rate"])}
        except Exception:  # noqa: BLE001 - no decodable sound: a silent video
            aud = None
    return VideoFromComponents(VideoComponents(images=images, frame_rate=Fraction(fps or 24).limit_denominator(1001000),
                                               audio=aud, alpha=alpha))


class NukeMax_OCIORead:
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK", "C2C_EXR_PASSES", "AUDIO", "VIDEO", "STRING", "STRING", "INT", "FLOAT")
    RETURN_NAMES = ("image", "alpha", "passes", "audio", "video", "metadata", "frame_numbers", "frame_count", "fps")
    DESCRIPTION = ("Reads stills, sequences and video into the OCIO working space: the source space from you, the "
                   "file's header or the config's file rules (said which), converted to scene_linear or your working "
                   "space; alpha kept; a native VIDEO of the source clip with its sound.")

    @classmethod
    def INPUT_TYPES(cls):
        base = R.NukeMax_Read.INPUT_TYPES()
        opt = {k: v for k, v in base["optional"].items() if k not in _READ_DROP}
        opt.update({
            "ocio_config": (CM.TYPE, {"tooltip": "From NukeMax OCIO Config Manager; empty = $OCIO, else the built-in "
                                                 "ACES studio config."}),
            "source_space": ("STRING", {"default": "", "tooltip": "Empty = the file's header, else the config's file "
                                                                  "rules."}),
            "working_space": ("STRING", {"default": "", "tooltip": "Empty = the config's scene_linear role."}),
        })
        return {"required": dict(base["required"]), "optional": opt}

    @classmethod
    def IS_CHANGED(cls, ocio_config=None, source_space="", working_space="", **kw):
        return f"{R.NukeMax_Read.IS_CHANGED(**kw)}|{CM.fingerprint(ocio_config or '')}|{source_space}|{working_space}"

    def execute(self, ocio_config=None, source_space="", working_space="", **kw):
        out = R.NukeMax_Read().execute(**kw)
        ui = out.get("ui") if isinstance(out, dict) else None
        image, alpha, passes, audio, meta, nums, n, fps = out["result"] if isinstance(out, dict) else out
        m = json.loads(meta)
        path = ocio_config or CM.default_source()
        cfg = CM.load(path)
        typed = str(source_space or "").strip()
        header = m.get("header") or {}
        if typed:
            src, how = _space(cfg, typed, "source_space", NAME_R), "typed"
        else:
            src = how = ""
            # an AUTHORED header only: ours always; OpenImageIO's own oiio:ColorSpace only for EXR, where it comes
            # from the file - for PNG / JPEG / TIFF it is OpenImageIO's guess and would override the config's rules
            is_exr = str(m.get("kind", "")).startswith("exr")
            for key in ("nukemax:colourSpace",) + (("oiio:ColorSpace",) if is_exr else ()):
                v = header.get(key)
                if v and cfg.getColorSpace(str(v)) is not None:
                    src, how = cfg.getColorSpace(str(v)).getName(), f"file header ({key})"
                    break
            if not src:
                probe = str(m.get("path") or m.get("media", {}).get("path") or "")
                src = _rule_space(cfg, probe)
                how = "the config's file rules"
        work = _space(cfg, str(working_space).strip(), "working_space", NAME_R) if str(working_space or "").strip() \
            else cfg.getRoleColorSpace("scene_linear")
        if not work:
            raise ValueError(f"{NAME_R}: this config has no scene_linear role - type a working_space.")
        converted = _convert(cfg, image, src, work)
        video = _video(image, fps, audio if m.get("kind") == "video" else None, alpha if m.get("has_alpha") else None)
        m["colour"] = {"config": path, "config_source": CM.source_kind(path), "source_space": src,
                       "source_from": how, "working_space": work, "converted": src != work,
                       "passes": "as stored (not converted)"}
        result = (converted, alpha, passes, audio, video, json.dumps(m, indent=2, default=str), nums, n, fps)
        return {"ui": ui, "result": result} if ui else result


class NukeMax_OCIOWrite:
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = W.NukeMax_Write.RETURN_TYPES
    RETURN_NAMES = W.NukeMax_Write.RETURN_NAMES
    DESCRIPTION = ("Writes IMAGE or a native VIDEO through OCIO: from the working space (or your input space) to the "
                   "output space you type or the config's file rule for the format, then NukeMax Write; the OCIO facts "
                   "go into the manifest sidecar.")

    @classmethod
    def INPUT_TYPES(cls):
        base = W.NukeMax_Write.INPUT_TYPES()
        req = {k: v for k, v in base["required"].items() if k not in _WRITE_DROP}
        opt = {"image": ("IMAGE",), "video": ("VIDEO", {"tooltip": "A native VIDEO: its frames, sound, rate and "
                                                                   "alpha are written."})}
        opt.update({k: v for k, v in base["optional"].items() if k not in _WRITE_DROP})
        opt.update({
            "ocio_config": (CM.TYPE, {"tooltip": "From NukeMax OCIO Config Manager; empty = $OCIO, else the built-in "
                                                 "ACES studio config."}),
            "input_space": ("STRING", {"default": "", "tooltip": "Empty = the config's scene_linear role."}),
            "output_space": ("STRING", {"default": "", "tooltip": "Empty = the config's file rule for this format."}),
        })
        return {"required": req, "optional": opt}

    def execute(self, image=None, video=None, ocio_config=None, input_space="", output_space="", **kw):
        if image is None and video is None:
            raise ValueError(f"{NAME_W}: connect an image or a video.")
        if image is None:
            comps = video.get_components()
            image = comps.images
            if kw.get("audio") is None and comps.audio is not None:
                kw["audio"] = comps.audio
            if not float(kw.get("fps") or 0):
                kw["fps"] = float(comps.frame_rate)
            if kw.get("alpha") is None and getattr(comps, "alpha", None) is not None:
                kw["alpha"] = comps.alpha
        path = ocio_config or CM.default_source()
        cfg = CM.load(path)
        src = _space(cfg, input_space.strip(), "input_space", NAME_W) if str(input_space or "").strip() \
            else cfg.getRoleColorSpace("scene_linear")
        fmt = kw.get("format", "png")
        ext = W.STILLS[fmt][0] if fmt in W.STILLS else W.MOVIES[fmt][1]
        if str(output_space or "").strip():
            dst, how = _space(cfg, output_space.strip(), "output_space", NAME_W), "typed"
        else:
            dst, how = _rule_space(cfg, f"out{ext}"), f"the config's file rule for {ext}"
        converted = _convert(cfg, image[..., :3], src, dst)
        extra = {"ocio": {"config": path, "config_source": CM.source_kind(path), "fingerprint": CM.fingerprint(path),
                          "input_space": src, "output_space": dst, "output_from": how, "converted": src != dst}}
        return W.NukeMax_Write().execute(image=converted, colour_space=dst, convert_from="", ocio_config="",
                                         manifest_extra=extra, **kw)


NODE_CLASS_MAPPINGS = {"NukeMax_OCIORead": NukeMax_OCIORead, "NukeMax_OCIOWrite": NukeMax_OCIOWrite}
NODE_DISPLAY_NAME_MAPPINGS = {"NukeMax_OCIORead": "NukeMax OCIO Read", "NukeMax_OCIOWrite": "NukeMax OCIO Write"}
