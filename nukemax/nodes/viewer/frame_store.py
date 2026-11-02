"""NukeMax Viewer Pro's frame store (owner Rev 3 Part 19.12 "Performance"; ledger L9.80 slice 7a).

A run writes what the browser needs and nothing more, under ComfyUI's temp folder (emptied by ComfyUI on start):
  temp/nukemax_viewer/<key>/index.json          frames, sizes, fps, frame numbers, per-frame full-resolution stats
                              a_<i>.f16          the proxy: RGBA float16, long side <= NUKEMAX_VIEWER_PROXY (960)
                              a_<i>.full.z       the full-resolution frame, zlib(RGBA float16, or float32 when a value
                                                 is beyond half's 65504), for exact pixel samples - while within
                                                 NUKEMAX_VIEWER_FULL_FRAMES (96) frames
The whole folder is held to NUKEMAX_VIEWER_CACHE_MB (2048): the least recently used stores are removed first, never the
one being written. Keys are 16 hex characters; a route answers only a key that exists - never a path.
Original code, GPL-3.0-only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import zlib

import numpy as np
import torch
import torch.nn.functional as F

ROOT_NAME = "nukemax_viewer"
KEY_RE = re.compile(r"^[0-9a-f]{16}$")
HALF_MAX = 65504.0


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def root() -> str:
    import folder_paths  # type: ignore[import-not-found]
    return os.path.join(folder_paths.get_temp_directory(), ROOT_NAME)


def new_key(seed: str = "") -> str:
    return hashlib.sha1(f"{seed}|{time.time_ns()}|{os.getpid()}".encode()).hexdigest()[:16]


def path_of(key: str) -> str:
    if not KEY_RE.match(str(key or "")):
        raise KeyError("not a viewer key")
    p = os.path.join(root(), key)
    if not os.path.isdir(p):
        raise KeyError("this viewer store is gone - run the node again")
    return p


def proxy_size(w: int, h: int, long_side: int | None = None) -> tuple[int, int]:
    long_side = long_side or _env_int("NUKEMAX_VIEWER_PROXY", 960)
    s = min(1.0, long_side / max(w, h))
    return max(1, round(w * s)), max(1, round(h * s))


def _rgba(frame: torch.Tensor, alpha: torch.Tensor | None) -> torch.Tensor:
    """[H, W, C] -> [H, W, 4] float32 (alpha from the image, else the mask, else 1)."""
    f = frame.detach().float().cpu()
    if f.shape[-1] >= 4:
        return f[..., :4]
    rgb = f[..., :3] if f.shape[-1] >= 3 else f[..., :1].repeat(1, 1, 3)
    a = alpha.detach().float().cpu()[..., None] if alpha is not None else torch.ones_like(rgb[..., :1])
    return torch.cat([rgb, a], -1)


def _stats(a: np.ndarray) -> dict:
    flat = a.reshape(-1, a.shape[-1])
    fin = np.where(np.isfinite(flat), flat, np.nan)
    return {"min": [round(float(x), 6) for x in np.nanmin(fin, 0)], "max": [round(float(x), 6) for x in np.nanmax(fin, 0)],
            "mean": [round(float(x), 6) for x in np.nanmean(fin, 0)],
            "above_1": int((flat[:, :3] > 1.0).any(1).sum()), "negative": int((flat[:, :3] < 0).any(1).sum()),
            "nan": int(np.isnan(flat).sum()), "inf": int(np.isinf(flat).sum())}


def write_side(key: str, which: str, image: torch.Tensor, alpha: torch.Tensor | None = None) -> dict:
    """Write proxies (+ full frames within budget) of ``image`` [B, H, W, C] as side ``which`` ('a' / 'b')."""
    d = os.path.join(root(), key)
    os.makedirs(d, exist_ok=True)
    if image.ndim == 3:
        image = image.unsqueeze(0)
    n, h, w = int(image.shape[0]), int(image.shape[1]), int(image.shape[2])
    pw, ph = proxy_size(w, h)
    full_budget = _env_int("NUKEMAX_VIEWER_FULL_FRAMES", 96)
    stats, full = [], []
    for i in range(n):
        a = alpha[0 if alpha.shape[0] == 1 else i] if alpha is not None and alpha.ndim == 3 else alpha
        fr = _rgba(image[i], a)                                            # [H, W, 4] float32
        arr = fr.numpy()
        stats.append(_stats(arr))
        prox = F.interpolate(fr.permute(2, 0, 1)[None], size=(ph, pw), mode="area")[0].permute(1, 2, 0) \
            if (pw, ph) != (w, h) else fr
        np.ascontiguousarray(prox.numpy().astype("<f2")).tofile(os.path.join(d, f"{which}_{i}.f16"))
        if i < full_budget:
            wide = bool(np.nanmax(np.abs(np.where(np.isfinite(arr), arr, 0))) > HALF_MAX)
            raw = np.ascontiguousarray(arr.astype("<f4" if wide else "<f2")).tobytes()
            with open(os.path.join(d, f"{which}_{i}.full.z"), "wb") as f:
                f.write(b"F32" if wide else b"F16")
                f.write(zlib.compress(raw, 1))
            full.append(i)
    return {"frames": n, "width": w, "height": h, "proxy": [pw, ph], "full_frames": len(full), "stats": stats}


def write_index(key: str, info: dict) -> None:
    d = os.path.join(root(), key)
    tmp = os.path.join(d, ".index.json.part")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(info, f, default=str)
    os.replace(tmp, os.path.join(d, "index.json"))


def read_index(key: str) -> dict:
    p = path_of(key)
    os.utime(p, None)                                                    # recently used: evicted last
    with open(os.path.join(p, "index.json"), encoding="utf-8") as f:
        return json.load(f)


def proxy_bytes(key: str, i: int, which: str = "a") -> bytes:
    if which not in ("a", "b"):
        raise KeyError("which is a or b")
    p = os.path.join(path_of(key), f"{which}_{int(i)}.f16")
    if not os.path.isfile(p):
        raise KeyError(f"no frame {i}")
    with open(p, "rb") as f:
        return f.read()


def sample(key: str, i: int, x: int, y: int, w: int = 1, h: int = 1, which: str = "a") -> dict:
    """Exact values from the full-resolution frame (or the proxy, said so): one pixel, or a region's statistics.
    x / y / w / h are in SOURCE pixels."""
    idx = read_index(key)
    side = idx.get(which) or {}
    W, H = int(side.get("width", 0)), int(side.get("height", 0))
    if not W:
        raise KeyError(f"no side {which}")
    i = int(i)
    d = path_of(key)
    full = os.path.join(d, f"{which}_{i}.full.z")
    if os.path.isfile(full):
        with open(full, "rb") as f:
            tag, payload = f.read(3), f.read()
        arr = np.frombuffer(zlib.decompress(payload), "<f4" if tag == b"F32" else "<f2").reshape(H, W, 4)
        sx = sy = 1.0
        source = "full resolution"
    else:
        pw, ph = side["proxy"]
        arr = np.fromfile(os.path.join(d, f"{which}_{i}.f16"), "<f2").reshape(ph, pw, 4)
        sx, sy = pw / W, ph / H
        source = f"proxy sample (1:{round(1 / sx, 2)})"
    x0 = max(0, min(int(x * sx), arr.shape[1] - 1))
    y0 = max(0, min(int(y * sy), arr.shape[0] - 1))
    x1 = max(x0 + 1, min(int((x + max(1, w)) * sx), arr.shape[1]))
    y1 = max(y0 + 1, min(int((y + max(1, h)) * sy), arr.shape[0]))
    reg = arr[y0:y1, x0:x1].astype(np.float32)
    out = {"source": source, "frame": i, "x": int(x), "y": int(y), "w": int(max(1, w)), "h": int(max(1, h))}
    if reg.shape[0] * reg.shape[1] == 1:
        out["rgba"] = [round(float(v), 6) for v in reg[0, 0]]
    else:
        out.update(_stats(reg))
    return out


def enforce_budget(keep: str) -> list[str]:
    """Remove the least recently used stores until the folder is under NUKEMAX_VIEWER_CACHE_MB; never ``keep``."""
    budget = _env_int("NUKEMAX_VIEWER_CACHE_MB", 2048) * 1024 * 1024
    base = root()
    if not os.path.isdir(base):
        return []
    stores = []
    for k in os.listdir(base):
        p = os.path.join(base, k)
        if KEY_RE.match(k) and os.path.isdir(p):
            size = sum(os.path.getsize(os.path.join(p, f)) for f in os.listdir(p))
            stores.append((os.path.getmtime(p), k, size))
    total = sum(s for _, _, s in stores)
    removed = []
    for _t, k, s in sorted(stores):
        if total <= budget:
            break
        if k == keep:
            continue
        shutil.rmtree(os.path.join(base, k), ignore_errors=True)       # only our own keyed folders
        total -= s
        removed.append(k)
    return removed
