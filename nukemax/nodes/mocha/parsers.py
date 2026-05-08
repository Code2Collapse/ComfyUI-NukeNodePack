"""Parsers for Mocha Pro export formats.

Supported formats:
  - Mocha "Nuke Corner-Pin (.nk)" — embedded CornerPin2D blocks with
    `to1`..`to4` keyed via Nuke's `{ {curve K x...} ...}` syntax.
  - Mocha "Nuke Transform (.nk)" — Transform/Tracker4 with translate /
    rotate / scale / center keyframes.
  - Mocha "After Effects (.txt)" / generic ASCII corner pin: tab- or
    space-separated `frame x1 y1 x2 y2 x3 y3 x4 y4` rows.
  - Mocha "After Effects (.txt)" generic transform: `frame tx ty rot sx sy`.
  - Mocha "Shape Data (.nk)" — Roto/RotoPaint nodes with curves.
  - Mocha "Lens Calibration (.txt)" — key/value pairs with focal_length,
    distortion (k1,k2), principal point, etc.
  - Mocha project (.mocha) — zipped XML with project state.

Parsers are intentionally permissive. When a file is partially
recognised the parser returns whatever it could extract and leaves the
rest as None / empty so downstream nodes can still operate.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Any, Iterable

import torch

from ...types import MochaTrack, MochaLens, MochaProject


# -----------------------------------------------------------------------
# Generic helpers
# -----------------------------------------------------------------------
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _floats(line: str) -> list[float]:
    return [float(s) for s in _NUMBER_RE.findall(line)]


def _read_text(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    # Most Mocha exports are ASCII; tolerate UTF-8 BOM.
    return raw.decode("utf-8-sig", errors="replace")


# -----------------------------------------------------------------------
# Nuke .nk curve parser
# -----------------------------------------------------------------------
# Nuke serialises an animated 1D channel as `{curve K x0 v0 x1 v1 ...}`
# where K is the interpolation flag. A 2D point is `{ {curve ...} {curve ...} }`.
_CURVE_RE = re.compile(r"\{curve[^{}]*?((?:\s+-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)+)\s*\}")


def _parse_nk_curve(curve_text: str) -> dict[int, float]:
    """Return {frame: value} from a Nuke `{curve ...}` body."""
    nums = _floats(curve_text)
    # Pattern is x0 v0 x1 v1 ... — but Nuke sometimes emits a leading
    # 'K' style char which we already stripped. Take pairs.
    out: dict[int, float] = {}
    for i in range(0, len(nums) - 1, 2):
        f = int(round(nums[i]))
        out[f] = nums[i + 1]
    return out


def _parse_nk_2d_point(text: str) -> tuple[dict[int, float], dict[int, float]] | None:
    """Parse `{ {curve ...} {curve ...} }` -> (x_kf, y_kf)."""
    curves = _CURVE_RE.findall(text)
    if len(curves) < 2:
        # Static point of the form `{x y}`
        nums = _floats(text)
        if len(nums) >= 2:
            return ({0: nums[0]}, {0: nums[1]})
        return None
    return (_parse_nk_curve(curves[0]), _parse_nk_curve(curves[1]))


def _resolve_keyframes(kf: dict[int, float], T: int) -> torch.Tensor:
    """Linearly interpolate keyframes onto frames 0..T-1."""
    if not kf:
        return torch.zeros(T)
    fs = sorted(kf.keys())
    vals = torch.tensor([kf[f] for f in fs], dtype=torch.float32)
    out = torch.zeros(T, dtype=torch.float32)
    for t in range(T):
        if t <= fs[0]:
            out[t] = vals[0]
        elif t >= fs[-1]:
            out[t] = vals[-1]
        else:
            # Find bracket
            for i in range(len(fs) - 1):
                if fs[i] <= t <= fs[i + 1]:
                    span = fs[i + 1] - fs[i]
                    a = (t - fs[i]) / max(span, 1)
                    out[t] = (1 - a) * vals[i] + a * vals[i + 1]
                    break
    return out


def _frame_range(*kf_dicts: dict[int, float], default: int = 1) -> int:
    last = 0
    for d in kf_dicts:
        if d:
            last = max(last, max(d.keys()))
    return max(last + 1, default)


# -----------------------------------------------------------------------
# Corner-pin parsers
# -----------------------------------------------------------------------
def parse_corner_pin(path: str, canvas_w: int, canvas_h: int, name: str = "mocha_cp") -> MochaTrack:
    """Auto-detect .nk vs .txt and return a MOCHA_TRACK (kind=corner_pin)."""
    text = _read_text(path)
    if path.lower().endswith(".nk") or "CornerPin2D" in text:
        return _parse_corner_pin_nk(text, canvas_w, canvas_h, name)
    return _parse_corner_pin_ascii(text, canvas_w, canvas_h, name)


def _parse_corner_pin_nk(text: str, canvas_w: int, canvas_h: int, name: str) -> MochaTrack:
    pts: list[tuple[dict, dict]] = []
    # Find each `to1 { ... }` ... `to4 { ... }` block.
    # Use a one-level nested-brace pattern so `{ {curve...} {curve...} }` is
    # captured in full rather than stopping at the first `}`.
    _NESTED1 = r"\{(?:[^{}]|\{[^{}]*\})*\}"
    for label in ("to1", "to2", "to3", "to4"):
        m = re.search(rf"\b{label}\s*({_NESTED1})", text, flags=re.S)
        if not m:
            # Fallback: grab the two {curve} blocks after the label directly
            ml = re.search(rf"\b{label}\b", text)
            if not ml:
                raise ValueError(f"corner pin .nk missing {label}")
            window = text[ml.end():ml.end() + 800]
            hits = list(_CURVE_RE.finditer(window))
            if len(hits) >= 2:
                xkf = _parse_nk_curve(hits[0].group(0))
                ykf = _parse_nk_curve(hits[1].group(0))
                pts.append((xkf, ykf))
                continue
            raise ValueError(f"corner pin .nk could not parse {label}")
        parsed = _parse_nk_2d_point(m.group(1))
        if parsed is None:
            raise ValueError(f"corner pin .nk could not parse {label}")
        pts.append(parsed)

    T = _frame_range(*[d for pair in pts for d in pair])
    params = torch.zeros(T, 4, 2, dtype=torch.float32)
    for i, (xkf, ykf) in enumerate(pts):
        params[:, i, 0] = _resolve_keyframes(xkf, T)
        params[:, i, 1] = _resolve_keyframes(ykf, T)
    return MochaTrack(
        kind="corner_pin", params=params,
        canvas_h=canvas_h, canvas_w=canvas_w, name=name,
    )


def _parse_corner_pin_ascii(text: str, canvas_w: int, canvas_h: int, name: str) -> MochaTrack:
    rows: list[list[float]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("//"):
            continue
        nums = _floats(s)
        # Need at least 9 numbers: frame + 4 xy
        if len(nums) >= 9:
            rows.append(nums[:9])
    if not rows:
        raise ValueError("no corner-pin rows found in ASCII export")
    rows.sort(key=lambda r: r[0])
    T = int(rows[-1][0]) - int(rows[0][0]) + 1
    f0 = int(rows[0][0])
    params = torch.zeros(T, 4, 2, dtype=torch.float32)
    last = None
    by_frame = {int(r[0]) - f0: r[1:9] for r in rows}
    for t in range(T):
        if t in by_frame:
            last = by_frame[t]
        if last is None:
            last = rows[0][1:9]
        for i in range(4):
            params[t, i, 0] = last[i * 2]
            params[t, i, 1] = last[i * 2 + 1]
    return MochaTrack(
        kind="corner_pin", params=params,
        canvas_h=canvas_h, canvas_w=canvas_w, name=name,
    )


# -----------------------------------------------------------------------
# Transform parsers
# -----------------------------------------------------------------------
def parse_transform(path: str, canvas_w: int, canvas_h: int, name: str = "mocha_xf") -> MochaTrack:
    text = _read_text(path)
    if path.lower().endswith(".nk") or "Transform" in text or "Tracker4" in text:
        return _parse_transform_nk(text, canvas_w, canvas_h, name)
    return _parse_transform_ascii(text, canvas_w, canvas_h, name)


def _block_2d(text: str, key: str) -> tuple[dict, dict] | None:
    _NESTED1 = r"\{(?:[^{}]|\{[^{}]*\})*\}"
    m = re.search(rf"\b{key}\s*({_NESTED1})", text, flags=re.S)
    if not m:
        return None
    return _parse_nk_2d_point(m.group(1))


def _block_1d(text: str, key: str) -> dict[int, float] | None:
    m = re.search(rf"\b{key}\s+(.+)", text)
    if not m:
        return None
    val_text = m.group(1).strip()
    if val_text.startswith("{"):
        cm = _CURVE_RE.search(val_text)
        if cm:
            return _parse_nk_curve(cm.group(0))
    nums = _floats(val_text)
    if nums:
        return {0: nums[0]}
    return None


def _parse_transform_nk(text: str, canvas_w: int, canvas_h: int, name: str) -> MochaTrack:
    trans = _block_2d(text, "translate") or ({0: 0.0}, {0: 0.0})
    center = _block_2d(text, "center") or ({0: canvas_w * 0.5}, {0: canvas_h * 0.5})
    scale = _block_2d(text, "scale")
    if scale is None:
        sd = _block_1d(text, "scale") or {0: 1.0}
        scale = (sd, dict(sd))
    rot = _block_1d(text, "rotate") or {0: 0.0}

    all_kf = (trans[0], trans[1], scale[0], scale[1], center[0], center[1], rot)
    T = _frame_range(*all_kf)
    tx = _resolve_keyframes(trans[0], T)
    ty = _resolve_keyframes(trans[1], T)
    sx = _resolve_keyframes(scale[0], T)
    sy = _resolve_keyframes(scale[1], T)
    cx = _resolve_keyframes(center[0], T)
    cy = _resolve_keyframes(center[1], T)
    deg = _resolve_keyframes(rot, T)

    params = torch.zeros(T, 6, dtype=torch.float32)
    for t in range(T):
        # Affine: M = T(c) * R(θ) * S * T(-c) * T(t)
        rad = float(deg[t]) * 3.141592653589793 / 180.0
        cos_t, sin_t = torch.cos(torch.tensor(rad)), torch.sin(torch.tensor(rad))
        a = float(sx[t]) * cos_t.item()
        b = -float(sy[t]) * sin_t.item()
        c = float(sx[t]) * sin_t.item()
        d = float(sy[t]) * cos_t.item()
        # Apply pivot + translation:
        # x' = a*(x - cx) + b*(y - cy) + cx + tx
        tx_full = -a * float(cx[t]) - b * float(cy[t]) + float(cx[t]) + float(tx[t])
        ty_full = -c * float(cx[t]) - d * float(cy[t]) + float(cy[t]) + float(ty[t])
        params[t] = torch.tensor([a, b, tx_full, c, d, ty_full])
    return MochaTrack(
        kind="transform", params=params,
        canvas_h=canvas_h, canvas_w=canvas_w, name=name,
    )


def _parse_transform_ascii(text: str, canvas_w: int, canvas_h: int, name: str) -> MochaTrack:
    rows: list[list[float]] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("//"):
            continue
        nums = _floats(s)
        # frame tx ty rot sx sy  (Mocha "AE" generic transform export)
        if len(nums) >= 6:
            rows.append(nums[:6])
    if not rows:
        raise ValueError("no transform rows found in ASCII export")
    rows.sort(key=lambda r: r[0])
    f0 = int(rows[0][0])
    T = int(rows[-1][0]) - f0 + 1
    cx, cy = canvas_w * 0.5, canvas_h * 0.5
    params = torch.zeros(T, 6, dtype=torch.float32)
    by_frame = {int(r[0]) - f0: r[1:6] for r in rows}
    last = rows[0][1:6]
    for t in range(T):
        if t in by_frame:
            last = by_frame[t]
        tx, ty, deg, sx, sy = last
        rad = deg * 3.141592653589793 / 180.0
        import math
        a = sx * math.cos(rad)
        b = -sy * math.sin(rad)
        c = sx * math.sin(rad)
        d = sy * math.cos(rad)
        tx_full = -a * cx - b * cy + cx + tx
        ty_full = -c * cx - d * cy + cy + ty
        params[t] = torch.tensor([a, b, tx_full, c, d, ty_full])
    return MochaTrack(
        kind="transform", params=params,
        canvas_h=canvas_h, canvas_w=canvas_w, name=name,
    )


# -----------------------------------------------------------------------
# Shape parser (.nk Roto/RotoPaint)
# -----------------------------------------------------------------------
def parse_shape_nk(path: str, canvas_w: int, canvas_h: int) -> list[dict]:
    """Return a list of {points_per_frame: (T,N,2) tensor, name: str, closed: bool}.

    Permissive parse: walks each `Bezier { ... }` / `Shape { ... }` sub-block
    inside a Roto/RotoPaint node and pulls per-vertex point curves.
    """
    text = _read_text(path)
    shapes: list[dict] = []
    # Find sub-blocks. A vertex looks like `point { {curve ...} {curve ...} }`.
    # We grep for these directly; ordering inside the file is the polygon order.
    # Group vertices by their containing `Bezier` / `Shape` block.
    # Match Bezier/Shape blocks, and also layer { points { } } style from Roto.
    block_re = re.compile(r"(?:Bezier|Shape|layer)\s*\{(.*?)\n\s*\}", flags=re.S)
    # point entries: point { {curve x} {curve y} } — one outer brace containing the two curves.
    _NESTED1 = r"\{(?:[^{}]|\{[^{}]*\})*\}"
    point_re = re.compile(rf"\bpoint\s*({_NESTED1})", flags=re.S)
    for bm in block_re.finditer(text):
        body = bm.group(1)
        verts = []
        for pm in point_re.finditer(body):
            parsed = _parse_nk_2d_point(pm.group(1))
            if parsed is not None:
                verts.append(parsed)
        if not verts:
            continue
        all_kf = []
        for xk, yk in verts:
            all_kf += [xk, yk]
        T = _frame_range(*all_kf)
        N = len(verts)
        pts = torch.zeros(T, N, 2, dtype=torch.float32)
        for i, (xk, yk) in enumerate(verts):
            pts[:, i, 0] = _resolve_keyframes(xk, T)
            pts[:, i, 1] = _resolve_keyframes(yk, T)
        shapes.append({
            "points_per_frame": pts,
            "name": f"shape_{len(shapes)}",
            "closed": True,
            "canvas_h": canvas_h, "canvas_w": canvas_w,
        })
    if not shapes:
        raise ValueError(
            "no Bezier/Shape blocks recognised in Mocha shape .nk export")
    return shapes


# -----------------------------------------------------------------------
# Lens parser
# -----------------------------------------------------------------------
def parse_lens(path: str, canvas_w: int, canvas_h: int) -> MochaLens:
    text = _read_text(path)
    kv: dict[str, float] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        # Accept both `key = value` and `key value` (space-separated)
        m = re.match(r"([A-Za-z_][\w_]*)\s*(?:[:=]\s*)?(.+)", s)
        if not m:
            continue
        nums = _floats(m.group(2))
        if nums:
            kv[m.group(1).lower()] = nums[0]
    fx = kv.get("fx") or kv.get("focal_length_x") or kv.get("focal_length") or canvas_w
    fy = kv.get("fy") or kv.get("focal_length_y") or fx
    cx = kv.get("cx") or kv.get("principal_x") or canvas_w * 0.5
    cy = kv.get("cy") or kv.get("principal_y") or canvas_h * 0.5
    k1 = kv.get("k1") or kv.get("distortion") or 0.0
    k2 = kv.get("k2") or 0.0
    p1 = kv.get("p1") or 0.0
    p2 = kv.get("p2") or 0.0
    return MochaLens(
        fx=float(fx), fy=float(fy), cx=float(cx), cy=float(cy),
        k1=float(k1), k2=float(k2), p1=float(p1), p2=float(p2),
        canvas_h=canvas_h, canvas_w=canvas_w,
    )


# -----------------------------------------------------------------------
# .mocha project parser (zipped XML)
# -----------------------------------------------------------------------
def parse_mocha_project(path: str) -> MochaProject:
    """Best-effort parse of the zipped XML inside a .mocha project."""
    raw_xml = ""
    try:
        with zipfile.ZipFile(path, "r") as z:
            # Mocha typically stores the project XML as project.xml or
            # mochaproject.xml; pick the largest .xml entry to be safe.
            xml_entries = [n for n in z.namelist() if n.lower().endswith(".xml")]
            if not xml_entries:
                raise ValueError("no .xml inside .mocha archive")
            xml_entries.sort(key=lambda n: -z.getinfo(n).file_size)
            raw_xml = z.read(xml_entries[0]).decode("utf-8", errors="replace")
    except zipfile.BadZipFile:
        # Some Mocha exports are plain XML without a zip wrapper.
        raw_xml = _read_text(path)

    canvas_w = 0
    canvas_h = 0
    fps = 24.0
    layers: list[tuple[str, str]] = []
    try:
        root = ET.fromstring(raw_xml)
        # Try common attribute / element names.
        for el in root.iter():
            tag = el.tag.lower()
            if tag in ("clip", "project", "movie", "footage"):
                for k, v in el.attrib.items():
                    kl = k.lower()
                    if kl in ("width", "w"):
                        try: canvas_w = int(float(v))
                        except: pass
                    elif kl in ("height", "h"):
                        try: canvas_h = int(float(v))
                        except: pass
                    elif kl in ("fps", "framerate", "rate"):
                        try: fps = float(v)
                        except: pass
            if tag in ("layer", "track", "shape", "spline"):
                name = el.attrib.get("name") or el.attrib.get("title") or tag
                layers.append((name, tag))
    except ET.ParseError:
        pass

    return MochaProject(
        layers=tuple(layers),
        tracks=(),     # full reverse-engineering of project tracks is out of scope
        shapes=(),
        lens=None,
        canvas_h=canvas_h or 1080,
        canvas_w=canvas_w or 1920,
        fps=fps,
        raw_xml=raw_xml,
    )
