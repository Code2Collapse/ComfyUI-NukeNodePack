# PORTED FROM: nuke-nodes-comfyui (third_party/nuke-nodes-comfyui) by Sumit Chatterjee
# Licence: MIT — direct copy authorised by owner; attribution retained.
"""Sequence path utilities ported from nuke-nodes-comfyui ``io_nodes``."""
from __future__ import annotations

import os
import re
import sys
from typing import List, Optional, Tuple


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def parse_frame_pattern(filepath: str) -> Tuple[str, Optional[str], int]:
    """Detect ``%04d``, ``####``, or literal frame numbers in a path."""
    filepath = filepath.replace("\\", "/")

    match = re.search(r"%(\d*)d", filepath)
    if match:
        padding = int(match.group(1)) if match.group(1) else 4
        return filepath, match.group(0), padding

    match = re.search(r"(#+)", filepath)
    if match:
        hashes = match.group(1)
        padding = len(hashes)
        pattern = filepath.replace(hashes, f"%0{padding}d")
        return pattern, hashes, padding

    match = re.search(r"(\d+)(\.[^.]+)$", filepath)
    if match:
        frame_str = match.group(1)
        padding = len(frame_str)
        ext = match.group(2)
        base = filepath[: match.start()]
        pattern = f"{base}%0{padding}d{ext}"
        return pattern, frame_str, padding

    return filepath, None, 0


def expand_frame_pattern(pattern: str, frame: int, padding: int = 4) -> str:
    """Expand a frame pattern to a concrete filename."""
    if "%" in pattern:
        return pattern % frame

    if "#" in pattern:
        hashes = re.search(r"#+", pattern).group(0)
        return pattern.replace(hashes, str(frame).zfill(len(hashes)))

    return pattern


def auto_detect_sequence(filepath: str) -> Optional[Tuple[str, List[int], int]]:
    """Stat-only sequence detection for bare paths like ``beauty.exr``."""
    filepath = filepath.replace("\\", "/")
    directory = os.path.dirname(filepath)
    basename = os.path.basename(filepath)
    stem, ext = os.path.splitext(basename)
    if not stem:
        return None

    try:
        entries = os.listdir(directory or ".")
    except OSError:
        return None

    ext_rx = f"(?i:{re.escape(ext)})" if _is_windows() else re.escape(ext)
    name_rx = re.compile("^" + re.escape(stem) + r"([._]?)(\d+)" + ext_rx + "$")

    groups: dict[tuple[str, int], list[int]] = {}
    for entry in entries:
        match = name_rx.match(entry)
        if not match:
            continue
        sep, digits = match.group(1), match.group(2)
        groups.setdefault((sep, len(digits)), []).append(int(digits))

    if not groups:
        return None

    sep_rank = {".": 2, "_": 1, "": 0}
    (sep, padding), frame_list = max(
        groups.items(),
        key=lambda item: (len(item[1]), sep_rank.get(item[0][0], 0), item[0][1]),
    )
    frames = sorted(set(frame_list))

    prefix = f"{directory}/" if directory else ""
    pattern = f"{prefix}{stem}{sep}%0{padding}d{ext}"
    return pattern, frames, padding


def file_change_token(filepath: str) -> str:
    """Cheap IS_CHANGED fingerprint from ``os.stat`` only."""
    try:
        st = os.stat(filepath)
        return f"{filepath}|{st.st_mtime_ns}|{st.st_size}"
    except OSError:
        return f"missing:{filepath}"


def resolve_sequence_path(
    file_path: str,
    frame: int,
    *,
    load_as_sequence: bool = True,
) -> str:
    """Mirror ReadMultiPass path resolution for execute and IS_CHANGED."""
    if not file_path:
        return ""

    file_path = os.path.expandvars(os.path.expanduser(file_path))
    pattern, frame_spec, padding = parse_frame_pattern(file_path)

    if load_as_sequence and frame_spec is None:
        detected = auto_detect_sequence(file_path)
        if detected is not None:
            pattern, _frames, padding = detected
            frame_spec = "auto"

    is_sequence = load_as_sequence and frame_spec is not None and padding > 0
    if is_sequence:
        return expand_frame_pattern(pattern, frame, padding)
    return file_path


def _require_oiio():
    try:
        import OpenImageIO as oiio  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "This operation needs OpenImageIO. Install it with: pip install OpenImageIO"
        ) from exc
    return oiio


def read_image_oiio(filepath: str):
    """Read image via OIIO as float32 numpy array (H, W, C)."""
    import numpy as np

    oiio = _require_oiio()
    inp = oiio.ImageInput.open(filepath)
    if inp is None:
        raise RuntimeError(f"OIIO could not open {filepath!r}: {oiio.geterror()}")
    spec = inp.spec()
    pixels = inp.read_image("float")
    inp.close()
    if pixels is None:
        raise RuntimeError(f"OIIO returned no pixel data for {filepath!r}")
    arr = np.array(pixels, dtype=np.float32).reshape(spec.height, spec.width, spec.nchannels)
    return arr


def read_image_oiio_spec(filepath: str) -> dict:
    """Read OIIO ImageSpec attributes without decoding pixels."""
    oiio = _require_oiio()
    inp = oiio.ImageInput.open(filepath)
    if inp is None:
        return {}
    spec = inp.spec()
    inp.close()
    out: dict = {
        "width": spec.width,
        "height": spec.height,
        "nchannels": spec.nchannels,
        "channelnames": list(spec.channelnames),
        "format": str(spec.format),
    }
    for i in range(spec.extra_attribs):
        p = spec.extra_attrib(i)
        try:
            out[p.name] = p.value
        except Exception:  # noqa: BLE001
            out[p.name] = repr(p.value)
    return out


def read_image(filepath: str):
    """Read an image; EXR requires OIIO (cv2 cannot read EXR here)."""
    import numpy as np

    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"File not found: {filepath!r}")
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".exr":
        return read_image_oiio(filepath)
    try:
        return read_image_oiio(filepath)
    except ImportError:
        raise
    except Exception:
        pass
    try:
        from PIL import Image as PILImage
        img = np.array(PILImage.open(filepath), dtype=np.float32)
        if img.max() > 1.0:
            img /= 255.0 if img.max() <= 255 else 65535.0
        if img.ndim == 2:
            img = img[:, :, np.newaxis]
        return img
    except ImportError as exc:
        raise ImportError(
            "Could not read image: OpenImageIO failed and Pillow is not installed."
        ) from exc


def write_image_oiio(
    filepath: str,
    pixels,
    bit_depth: str = "16f",
    compression: str = "zip",
    metadata: dict | None = None,
) -> bool:
    """Write image via OIIO. Returns True on success."""
    import numpy as np

    oiio = _require_oiio()
    height, width = pixels.shape[:2]
    channels = pixels.shape[2] if pixels.ndim > 2 else 1
    if bit_depth == "8":
        format_type = oiio.UINT8
        pixels_out = (np.clip(pixels, 0, 1) * 255).astype(np.uint8)
    elif bit_depth == "16":
        format_type = oiio.UINT16
        pixels_out = (np.clip(pixels, 0, 1) * 65535).astype(np.uint16)
    elif bit_depth == "32f":
        format_type = oiio.FLOAT
        pixels_out = pixels.astype(np.float32)
    else:
        format_type = oiio.HALF
        pixels_out = pixels.astype(np.float16)
    pixels_out = np.ascontiguousarray(pixels_out)
    spec = oiio.ImageSpec(width, height, channels, format_type)
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".exr":
        spec.attribute("compression", compression)
    if metadata:
        for key, value in metadata.items():
            spec.attribute(key, value)
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    out = oiio.ImageOutput.create(filepath)
    if out is None:
        return False
    if not out.open(filepath, spec):
        out.close()
        return False
    ok = out.write_image(pixels_out)
    out.close()
    return bool(ok)
