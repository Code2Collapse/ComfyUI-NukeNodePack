"""NukeMax Viewer Pro (owner Rev 3 Part 19.12; ledger L9.80 slice 7a).

VIEW, never process: the IMAGE output is the input, untouched. Exposure, gamma, gain, channel, display, A/B ... live
in the viewer panel (browser) and never reach the graph. To bake the view into the output, the panel's "Apply view to
output" copies exposure / gamma / gain into this node's three widgets and turns apply_view_adjustment on - an explicit,
visible act (the panel says VIEW ONLY or APPLIED).

The run writes a frame store (frame_store.py) the panel reads through keyed routes: float16 proxies for display, the
full-resolution frames for exact pixel samples, per-frame statistics, frame numbers and fps.
Original node, GPL-3.0-only.
"""
from __future__ import annotations

import json

import torch

from . import frame_store as FS


class NukeMax_ViewerPro:
    CATEGORY = "NukeMax/Viewer"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    DESCRIPTION = ("A professional viewer on the node: fit / 100% / zoom / pan, R G B A luma, exposure in stops, gamma, "
                   "gain, checkerboard alpha, exact pixel values, timeline with timecode. VIEW ONLY: the output is the "
                   "input, untouched, unless you press Apply view to output.")

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"image": ("IMAGE",)},
            "optional": {
                "alpha": ("MASK", {"tooltip": "Shown as the alpha channel when the image has none."}),
                "metadata": ("STRING", {"forceInput": True, "tooltip": "Read / Read EXR Pro metadata: frame numbers, "
                                                                       "fps and the source shown in the panel."}),
                "frame_numbers": ("STRING", {"default": "", "tooltip": "e.g. 1001-1100 (Read's frame_numbers); empty "
                                                                       "= from the metadata, else from 0."}),
                "fps": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1000.0, "step": 0.001,
                                  "tooltip": "0 = the metadata's rate, else 24."}),
                "apply_view_adjustment": ("BOOLEAN", {"default": False, "tooltip": "Off: the output is the input, "
                                                      "untouched. On: exposure / gamma / gain below are applied."}),
                "exposure": ("FLOAT", {"default": 0.0, "min": -20.0, "max": 20.0, "step": 0.1,
                                       "tooltip": "Stops. Used only when apply_view_adjustment is on."}),
                "gamma": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 5.0, "step": 0.01}),
                "gain": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 100.0, "step": 0.01}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    @staticmethod
    def _numbers(text: str, meta: dict, n: int) -> list[int]:
        from ..io._safe_write import parse_frames
        s = str(text or "").strip() or str(((meta.get("frame_numbers") or {}).get("text")) or "").strip()
        if s:
            try:
                return parse_frames(s, n, 0, "NukeMax Viewer Pro")
            except ValueError:
                pass
        # Read EXR Pro's metadata carries the sequence itself (first / step / count), not a numbers text
        seq = (meta.get("media") or {}).get("sequence") if isinstance(meta.get("media"), dict) else None
        if isinstance(seq, dict) and int(seq.get("count") or 0) == n and seq.get("first") is not None:
            step = max(1, int(seq.get("step") or 1))
            return [int(seq["first"]) + k * step for k in range(n)]
        return list(range(n))

    @staticmethod
    def _fps(fps: float, meta: dict) -> float:
        if float(fps or 0) > 0:
            return float(fps)
        v = meta.get("fps") or (meta.get("media") or {}).get("fps") if isinstance(meta, dict) else None
        try:
            if isinstance(v, str) and "/" in v:
                a, b = v.split("/")
                return float(a) / float(b)
            if v:
                return float(v)
        except (ValueError, ZeroDivisionError):
            pass
        return 24.0

    def execute(self, image, alpha=None, metadata=None, frame_numbers="", fps=0.0, apply_view_adjustment=False,
                exposure=0.0, gamma=1.0, gain=1.0, unique_id=None):
        if image.ndim == 3:
            image = image.unsqueeze(0)
        try:
            meta = json.loads(metadata) if str(metadata or "").strip() else {}
        except json.JSONDecodeError:
            meta = {"raw": str(metadata)[:2000]}
        if not isinstance(meta, dict):
            meta = {"value": meta}
        n = int(image.shape[0])
        key = FS.new_key(str(unique_id or id(self)))
        side = FS.write_side(key, "a", image, alpha)
        info = {"key": key, "a": side, "frames": n, "numbers": self._numbers(frame_numbers, meta, n),
                "fps": self._fps(fps, meta), "has_alpha": bool(image.shape[-1] >= 4 or alpha is not None),
                "applied": bool(apply_view_adjustment),
                "applied_values": {"exposure": float(exposure), "gamma": float(gamma), "gain": float(gain)},
                "metadata": {k: meta[k] for k in list(meta)[:40]}}
        FS.write_index(key, info)
        FS.enforce_budget(key)
        out = image
        if apply_view_adjustment:
            x = image[..., :3] * (float(gain) * 2.0 ** float(exposure))
            g = max(float(gamma), 0.1)
            if g != 1.0:
                x = torch.where(x > 0, x.clamp(min=0) ** (1.0 / g), x)       # HDR-safe: values <= 0 pass through
            out = torch.cat([x, image[..., 3:]], -1) if image.shape[-1] > 3 else x
        ui = {"key": key, "frames": n, "width": side["width"], "height": side["height"], "proxy": side["proxy"],
              "fps": info["fps"], "applied": info["applied"]}
        return {"ui": {"nukemax_viewer": [ui]}, "result": (out,)}


NODE_CLASS_MAPPINGS = {"NukeMax_ViewerPro": NukeMax_ViewerPro}
NODE_DISPLAY_NAME_MAPPINGS = {"NukeMax_ViewerPro": "NukeMax Viewer Pro"}


def _register_routes():
    """GET /nukemax/viewer/index?key, /frame?key&i&which (f16 proxy), /sample?key&i&x&y&w&h&which. Keys only."""
    try:
        from aiohttp import web
        from server import PromptServer  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - outside ComfyUI
        return
    server = getattr(PromptServer, "instance", None)
    if server is None:
        return
    routes = server.routes

    @routes.get("/nukemax/viewer/index")
    async def _index(request):
        try:
            return web.json_response(FS.read_index(request.query.get("key", "")))
        except (KeyError, OSError) as exc:
            return web.json_response({"error": str(exc).strip("'")}, status=404)

    @routes.get("/nukemax/viewer/frame")
    async def _frame(request):
        q = request.query
        try:
            data = FS.proxy_bytes(q.get("key", ""), int(q.get("i", "0")), q.get("which", "a"))
        except (KeyError, ValueError, OSError) as exc:
            return web.json_response({"error": str(exc).strip("'")}, status=404)
        return web.Response(body=data, content_type="application/octet-stream",
                            headers={"Cache-Control": "private, max-age=3600"})

    @routes.get("/nukemax/viewer/sample")
    async def _sample(request):
        q = request.query
        try:
            return web.json_response(FS.sample(q.get("key", ""), int(q.get("i", "0")), int(float(q.get("x", "0"))),
                                               int(float(q.get("y", "0"))), int(q.get("w", "1")),
                                               int(q.get("h", "1")), q.get("which", "a")))
        except (KeyError, ValueError, OSError) as exc:
            return web.json_response({"error": str(exc).strip("'")}, status=404)


_register_routes()
