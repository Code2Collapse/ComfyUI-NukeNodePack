"""Server routes backing the on-node EXR preview.

WHY THIS IS SERVER-SIDE: a browser cannot decode OpenEXR. Any preview of a
scene-linear EXR has to be rendered by the server and handed to the page as
PNG, with a display transform already applied -- a linear EXR shown raw looks
almost black, which is the single most common "my Read node is broken" report.
ComfyUI-OCIO reaches the same conclusion in web/ocio_io.js (its preview is an
<img> pointed at a server render route); this is an original implementation of
that idea, not a copy of its code.

Backend is OpenImageIO. In this environment OIIO reads EXR and cv2 does not,
and the `OpenEXR` python module is not installed at all, so OIIO is the only
path -- there is no silent fallback to fake.

PATH SAFETY: these routes turn "read a file off disk" into something any page
open in the browser could ask for. The node itself already takes an arbitrary
path, but a *route* is a wider surface than a node, so reads are confined to
an allow-list: ComfyUI's input/output/temp directories plus anything named in
the NUKEMAX_EXR_ROOTS environment variable (os.pathsep-separated). Put your
plate roots there to preview them.
"""

from __future__ import annotations

import os
import re
from typing import Any

_REGISTERED = False

_IMAGE_EXT = {".exr", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".hdr", ".dpx"}
_SEQ_RE = re.compile(r"(#{2,8}|%0?\d*d)")


# ----------------------------------------------------------------------------
# allow-list
# ----------------------------------------------------------------------------

def _comfy_dirs() -> list[str]:
    out: list[str] = []
    try:
        import folder_paths  # type: ignore

        for fn in ("get_input_directory", "get_output_directory", "get_temp_directory"):
            f = getattr(folder_paths, fn, None)
            if callable(f):
                try:
                    d = f()
                    if d:
                        out.append(d)
                except Exception:
                    pass
    except Exception:
        pass
    return out


def _allowed_roots() -> list[str]:
    roots = _comfy_dirs()
    extra = os.environ.get("NUKEMAX_EXR_ROOTS", "")
    for part in extra.split(os.pathsep):
        part = part.strip()
        if part:
            roots.append(part)
    resolved = []
    for r in roots:
        try:
            resolved.append(os.path.realpath(r))
        except Exception:
            pass
    return resolved


def _resolve_readable(path: str) -> str:
    """Return a real path inside an allowed root, or raise ValueError."""
    if not path or not path.strip():
        raise ValueError("No file path given.")
    real = os.path.realpath(path.strip())
    if os.path.splitext(real)[1].lower() not in _IMAGE_EXT:
        raise ValueError(
            "Only image files can be previewed (" + ", ".join(sorted(_IMAGE_EXT)) + ")."
        )
    roots = _allowed_roots()
    for root in roots:
        if real == root or real.startswith(root + os.sep):
            return real
    raise ValueError(
        "That file is outside the directories the preview is allowed to read. "
        "Allowed: ComfyUI's input/output/temp folders, plus anything listed in the "
        "NUKEMAX_EXR_ROOTS environment variable. Add your plate root there and "
        "restart ComfyUI to preview it."
    )


# ----------------------------------------------------------------------------
# sequence handling
# ----------------------------------------------------------------------------

def _sequence_frames(path: str) -> tuple[str | None, list[int]]:
    """Given any frame of a sequence (or a #### / %04d template), return
    (printf_template, sorted_frame_numbers). ('', []) for a single still."""
    directory = os.path.dirname(path) or "."
    base = os.path.basename(path)

    m = _SEQ_RE.search(base)
    if m:
        token = m.group(1)
        pad = len(token) if token.startswith("#") else int(re.sub(r"\D", "", token) or 4)
        template_base = base[: m.start()] + "%0" + str(pad) + "d" + base[m.end():]
    else:
        m2 = re.search(r"(\d+)(?!.*\d)", os.path.splitext(base)[0])
        if not m2:
            return None, []
        pad = len(m2.group(1))
        stem, ext = os.path.splitext(base)
        template_base = stem[: m2.start()] + "%0" + str(pad) + "d" + stem[m2.end():] + ext

    template = os.path.join(directory, template_base)
    # Split on the FORMAT TOKEN, not on a bare "d" -- "render.%04d.exr" contains a
    # 'd' inside "render", so splitting the whole string produced a nonsense
    # suffix and matched no frames at all.
    tok = re.search(r"%0?\d*d", template_base)
    if not tok:
        return None, []
    prefix = template_base[: tok.start()]
    suffix = template_base[tok.end():]
    frames: list[int] = []
    try:
        for name in os.listdir(directory):
            if not name.startswith(prefix) or not name.endswith(suffix):
                continue
            mid = name[len(prefix): len(name) - len(suffix)] if suffix else name[len(prefix):]
            if mid.isdigit():
                frames.append(int(mid))
    except OSError:
        return None, []
    return (template, sorted(frames)) if frames else (None, [])


# ----------------------------------------------------------------------------
# OCIO
# ----------------------------------------------------------------------------

def _ocio_config():
    try:
        import PyOpenColorIO as ocio  # type: ignore
    except Exception:
        return None, None
    try:
        if os.environ.get("OCIO"):
            return ocio, ocio.GetCurrentConfig()
        return ocio, ocio.Config.CreateFromBuiltinConfig("ocio://default")
    except Exception:
        try:
            return ocio, ocio.GetCurrentConfig()
        except Exception:
            return ocio, None


def _ocio_options() -> dict[str, Any]:
    ocio, cfg = _ocio_config()
    if cfg is None:
        return {"available": False, "displays": [], "views": {}, "default_display": "",
                "default_view": ""}
    try:
        displays = list(cfg.getDisplays())
        views = {d: list(cfg.getViews(d)) for d in displays}
        dd = cfg.getDefaultDisplay()
        dv = cfg.getDefaultView(dd) if dd else ""
        return {"available": True, "displays": displays, "views": views,
                "default_display": dd, "default_view": dv}
    except Exception:
        return {"available": False, "displays": [], "views": {}, "default_display": "",
                "default_view": ""}


def _apply_view(rgb, display: str, view: str):
    """Apply an OCIO display/view to a float RGB numpy array in place-ish."""
    ocio, cfg = _ocio_config()
    if cfg is None or not display or not view:
        return rgb
    try:
        import numpy as np

        dt = ocio.DisplayViewTransform()
        dt.setSrc(ocio.ROLE_SCENE_LINEAR)
        dt.setDisplay(display)
        dt.setView(view)
        proc = cfg.getProcessor(dt).getDefaultCPUProcessor()
        buf = np.ascontiguousarray(rgb.astype("float32"))
        proc.applyRGB(buf)
        return buf
    except Exception:
        return rgb


# ----------------------------------------------------------------------------
# read + encode
# ----------------------------------------------------------------------------

def _read_image(path: str):
    """Read any OIIO-supported file as float32 HxWxC. Raises a human message."""
    try:
        import OpenImageIO as oiio  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "OpenImageIO is not installed, so EXR cannot be decoded. "
            "Install it with: pip install OpenImageIO"
        ) from exc
    inp = oiio.ImageInput.open(path)
    if inp is None:
        raise RuntimeError("Could not open " + os.path.basename(path) + ": " + oiio.geterror())
    try:
        spec = inp.spec()
        pixels = inp.read_image(format="float")
        if pixels is None:
            raise RuntimeError("Could not read pixels from " + os.path.basename(path))
        import numpy as np

        arr = np.asarray(pixels, dtype="float32")
        arr = arr.reshape(spec.height, spec.width, spec.nchannels)
        names = [spec.channelnames[i] for i in range(spec.nchannels)]
        return arr, names, spec
    finally:
        inp.close()


def _encode_png(rgb) -> bytes:
    import numpy as np

    arr = np.clip(rgb, 0.0, 1.0)
    arr = (arr * 255.0 + 0.5).astype("uint8")
    try:
        from PIL import Image  # type: ignore

        import io as _io

        buf = _io.BytesIO()
        Image.fromarray(arr, "RGB").save(buf, format="PNG", optimize=False)
        return buf.getvalue()
    except Exception:
        import imageio.v3 as iio  # type: ignore

        return iio.imwrite("<bytes>", arr, extension=".png")


def _channel_groups(names: list[str]) -> list[str]:
    """Collapse EXR channel names into selectable AOV groups."""
    groups: list[str] = []
    seen = set()
    for n in names:
        grp = n.rsplit(".", 1)[0] if "." in n else "rgba"
        if grp not in seen:
            seen.add(grp)
            groups.append(grp)
    return groups


def _select_rgb(arr, names: list[str], channel: str):
    import numpy as np

    if not channel or channel in ("rgba", "beauty", ""):
        idx = [i for i, n in enumerate(names) if n in ("R", "G", "B")]
        if len(idx) < 3:
            idx = list(range(min(3, arr.shape[2])))
    else:
        idx = [i for i, n in enumerate(names) if n.startswith(channel + ".")]
        if not idx:
            idx = [i for i, n in enumerate(names) if n == channel]
    if not idx:
        idx = list(range(min(3, arr.shape[2])))
    sel = arr[:, :, idx[:3]]
    if sel.shape[2] == 1:
        sel = np.repeat(sel, 3, axis=2)
    elif sel.shape[2] == 2:
        sel = np.concatenate([sel, np.zeros_like(sel[:, :, :1])], axis=2)
    return sel


def _fit(arr, max_w: int):
    import numpy as np

    h, w = arr.shape[:2]
    if w <= max_w or max_w <= 0:
        return arr
    step = max(1, int(round(w / float(max_w))))
    return np.ascontiguousarray(arr[::step, ::step, :])


# ----------------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------------

def register_exr_preview_routes() -> None:
    """Idempotent. Mirrors the mocha route pattern in nodes/mocha/__init__.py."""
    global _REGISTERED
    if _REGISTERED:
        return
    try:
        from server import PromptServer  # type: ignore
        from aiohttp import web  # type: ignore
    except Exception:
        return
    _REGISTERED = True
    routes = PromptServer.instance.routes

    @routes.get("/nukemax/exr/info")
    async def _info(request):  # noqa: ANN001
        raw = request.query.get("path", "")
        try:
            template, frames = _sequence_frames(raw)
            probe = (template % frames[0]) if frames else raw
            real = _resolve_readable(probe)
            arr, names, spec = _read_image(real)
            compression = ""
            try:
                compression = str(spec.getattribute("compression") or "")
            except Exception:
                pass
            return web.json_response({
                "ok": True,
                "name": os.path.basename(real),
                "width": int(spec.width),
                "height": int(spec.height),
                "nchannels": int(spec.nchannels),
                "channels": names,
                "groups": _channel_groups(names),
                "compression": compression,
                "is_sequence": bool(frames),
                "first": frames[0] if frames else 0,
                "last": frames[-1] if frames else 0,
                "count": len(frames),
                "ocio": _ocio_options(),
            })
        except (ValueError, RuntimeError) as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

    @routes.get("/nukemax/exr/thumb")
    async def _thumb(request):  # noqa: ANN001
        q = request.query
        raw = q.get("path", "")
        try:
            frame = int(q.get("frame", "-1"))
        except ValueError:
            frame = -1
        try:
            max_w = max(64, min(2048, int(q.get("w", "512"))))
        except ValueError:
            max_w = 512
        try:
            exposure = float(q.get("exposure", "0"))
        except ValueError:
            exposure = 0.0
        display = q.get("display", "")
        view = q.get("view", "")
        channel = q.get("channel", "")
        try:
            template, frames = _sequence_frames(raw)
            if frames and frame >= 0:
                target = template % frame
            elif frames:
                target = template % frames[0]
            else:
                target = raw
            real = _resolve_readable(target)
            arr, names, _spec = _read_image(real)
            rgb = _select_rgb(arr, names, channel)
            rgb = _fit(rgb, max_w)
            if exposure:
                rgb = rgb * (2.0 ** exposure)
            rgb = _apply_view(rgb, display, view)
            png = _encode_png(rgb)
            return web.Response(body=png, content_type="image/png",
                                headers={"Cache-Control": "no-store"})
        except (ValueError, RuntimeError) as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            return web.json_response({"ok": False, "error": str(exc)}, status=500)

    @routes.post("/nukemax/exr/upload")
    async def _upload(request):  # noqa: ANN001
        try:
            reader = await request.multipart()
            field = await reader.next()
            if field is None or field.name != "file":
                return web.json_response({"ok": False, "error": "missing 'file' field"},
                                         status=400)
            raw_name = os.path.basename(field.filename or "plate.exr")
            safe = re.sub(r"[^A-Za-z0-9._\-]+", "_", raw_name)[:120] or "plate.exr"
            if os.path.splitext(safe)[1].lower() not in _IMAGE_EXT:
                return web.json_response(
                    {"ok": False, "error": "Only image files can be uploaded."}, status=400)
            dirs = _comfy_dirs()
            if not dirs:
                return web.json_response(
                    {"ok": False, "error": "ComfyUI input directory is unavailable."},
                    status=500)
            tgt_dir = os.path.join(dirs[0], "nukemax_exr")
            os.makedirs(tgt_dir, exist_ok=True)
            tgt = os.path.join(tgt_dir, safe)
            if os.path.exists(tgt):
                stem, ext = os.path.splitext(safe)
                i = 1
                while os.path.exists(os.path.join(tgt_dir, stem + "_" + str(i) + ext)):
                    i += 1
                tgt = os.path.join(tgt_dir, stem + "_" + str(i) + ext)
            with open(tgt, "wb") as fh:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    fh.write(chunk)
            return web.json_response({"ok": True, "name": os.path.basename(tgt), "path": tgt})
        except Exception as exc:  # noqa: BLE001
            return web.json_response({"ok": False, "error": str(exc)}, status=500)
