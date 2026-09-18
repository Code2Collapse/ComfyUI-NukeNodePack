# PORTED FROM: nuke-nodes-comfyui (third_party/nuke-nodes-comfyui) by Sumit Chatterjee
# Licence: MIT — direct copy authorised by owner; attribution retained.
"""Native LUT parsers (.3dl, .csp, .spi1d, .spi3d) — no torch at module scope."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def parse_3dl_lut(filepath: Path) -> dict[str, Any]:
    """
    Parse a .3dl LUT file (Autodesk/Lustre format).

    Returns dict with 'size', 'data', 'domain_min', 'domain_max', 'type'.
    """
    lut_data: dict[str, Any] = {
        "title": filepath.stem,
        "domain_min": [0.0, 0.0, 0.0],
        "domain_max": [1.0, 1.0, 1.0],
        "size": 0,
        "data": [],
        "type": "3D",
        "input_range": None,
        "output_bit_depth": 12,
    }

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    data_lines: list[list[int]] = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()

        if lut_data["input_range"] is None and len(parts) >= 2:
            try:
                values = [int(x) for x in parts]
                if len(values) >= 2 and values[0] < values[-1]:
                    lut_data["input_range"] = values
                    continue
            except ValueError:
                pass

        if len(parts) >= 3:
            try:
                rgb = [int(x) for x in parts[:3]]
                data_lines.append(rgb)
            except ValueError:
                continue

    data_count = len(data_lines)
    for size in (17, 33, 65, 32, 64, 16):
        if size**3 == data_count:
            lut_data["size"] = size
            break

    if lut_data["size"] == 0 and data_count > 0:
        lut_data["size"] = int(round(data_count ** (1 / 3)))

    if data_lines:
        data_array = np.array(data_lines, dtype=np.float32)
        max_val = data_array.max()
        if max_val > 1.0:
            if max_val <= 255:
                data_array /= 255.0
            elif max_val <= 1023:
                data_array /= 1023.0
            elif max_val <= 4095:
                data_array /= 4095.0
            elif max_val <= 65535:
                data_array /= 65535.0
        lut_data["data"] = data_array

    return lut_data


def parse_csp_lut(filepath: Path) -> dict[str, Any]:
    """
    Parse a .csp LUT file (Rising Sun Research Cinespace format).

    Supports 3D LUT sections with ``inR inG inB -> outR outG outB`` data lines
    or bare ``outR outG outB`` triplets after a size header.
    """
    lut_data: dict[str, Any] = {
        "title": filepath.stem,
        "domain_min": [0.0, 0.0, 0.0],
        "domain_max": [1.0, 1.0, 1.0],
        "size": 0,
        "data": [],
        "type": "3D",
    }

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    data_lines: list[list[float]] = []
    in_3d_section = False

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        upper = line.upper()
        if upper.startswith("CS_") and "MIN" in upper:
            try:
                val = float(line.split()[-1])
                lut_data["domain_min"] = [val, val, val]
            except ValueError:
                pass
            continue
        if upper.startswith("CS_") and "MAX" in upper:
            try:
                val = float(line.split()[-1])
                lut_data["domain_max"] = [val, val, val]
            except ValueError:
                pass
            continue
        if upper.startswith("CS_3D_SIZE") or upper.startswith("CS_LUT3D_SIZE"):
            try:
                lut_data["size"] = int(line.split()[-1])
            except ValueError:
                pass
            continue
        if upper in ("3D", "LUT3D"):
            in_3d_section = True
            continue
        if upper in ("1D", "LUT1D"):
            lut_data["type"] = "1D"
            in_3d_section = False
            continue

        parts = line.replace(",", " ").split()
        if "->" in line:
            try:
                arrow_idx = parts.index("->")
                out_parts = parts[arrow_idx + 1 : arrow_idx + 4]
                rgb = [float(x) for x in out_parts[:3]]
                data_lines.append(rgb)
            except (ValueError, IndexError):
                continue
            continue

        if in_3d_section and len(parts) == 3 and lut_data["size"] == 0:
            try:
                sizes = [int(x) for x in parts]
                if all(s > 0 for s in sizes):
                    lut_data["size"] = sizes[0]
                    continue
            except ValueError:
                pass

        if len(parts) >= 3:
            try:
                rgb = [float(x) for x in parts[:3]]
                data_lines.append(rgb)
            except ValueError:
                continue

    if data_lines:
        data_array = np.array(data_lines, dtype=np.float32)
        if lut_data["size"] == 0:
            count = len(data_lines)
            for size in (17, 33, 65, 32, 64, 16):
                if size**3 == count:
                    lut_data["size"] = size
                    break
            if lut_data["size"] == 0 and count > 0:
                lut_data["size"] = int(round(count ** (1 / 3)))
        lut_data["data"] = data_array

    return lut_data


def parse_spi3d_lut(filepath: Path) -> dict[str, Any]:
    """Parse a .spi3d LUT file (Sony Pictures Imageworks format)."""
    lut_data: dict[str, Any] = {
        "title": filepath.stem,
        "domain_min": [0.0, 0.0, 0.0],
        "domain_max": [1.0, 1.0, 1.0],
        "size": 0,
        "data": [],
        "type": "3D",
    }

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    data_lines: list[list[float]] = []
    header_done = False

    for line in lines:
        line = line.strip()
        if not line:
            continue

        parts = line.split()

        if parts[0].upper() == "SPILUT":
            continue

        if not header_done and len(parts) == 2:
            try:
                int(parts[0])
                int(parts[1])
                header_done = True
                continue
            except ValueError:
                pass

        if header_done and lut_data["size"] == 0 and len(parts) == 1:
            try:
                lut_data["size"] = int(parts[0])
                continue
            except ValueError:
                pass

        if len(parts) >= 6:
            try:
                rgb = [float(parts[3]), float(parts[4]), float(parts[5])]
                data_lines.append(rgb)
            except ValueError:
                continue

    if data_lines:
        lut_data["data"] = np.array(data_lines, dtype=np.float32)

    return lut_data


def parse_spi1d_lut(filepath: Path) -> dict[str, Any]:
    """Parse a .spi1d LUT file (Sony Pictures Imageworks 1D format)."""
    lut_data: dict[str, Any] = {
        "title": filepath.stem,
        "domain_min": [0.0, 0.0, 0.0],
        "domain_max": [1.0, 1.0, 1.0],
        "size": 0,
        "data": [],
        "type": "1D",
    }

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    data_lines: list[list[float]] = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()

        if parts[0].lower() == "from":
            lut_data["domain_min"] = [float(parts[1])] * 3
        elif parts[0].lower() == "to":
            lut_data["domain_max"] = [float(parts[1])] * 3
        elif parts[0].lower() == "length":
            lut_data["size"] = int(parts[1])
        elif parts[0].lower() in ("version", "components"):
            continue
        elif len(parts) >= 1:
            try:
                if len(parts) == 1:
                    val = float(parts[0])
                    data_lines.append([val, val, val])
                elif len(parts) >= 3:
                    rgb = [float(x) for x in parts[:3]]
                    data_lines.append(rgb)
            except ValueError:
                continue

    if data_lines:
        lut_data["data"] = np.array(data_lines, dtype=np.float32)
        if lut_data["size"] == 0:
            lut_data["size"] = len(data_lines)

    return lut_data


def load_native_lut(path: str | Path) -> dict[str, Any]:
    """
    Load a native LUT file and return parsed data with a numpy ``data`` array.

    Supported extensions: .3dl, .csp, .spi3d, .spi1d
    """
    filepath = Path(path)

    if not filepath.exists():
        raise FileNotFoundError(f"LUT file not found: {filepath}")

    ext = filepath.suffix.lower()

    try:
        if ext == ".3dl":
            return parse_3dl_lut(filepath)
        if ext == ".csp":
            return parse_csp_lut(filepath)
        if ext == ".spi3d":
            return parse_spi3d_lut(filepath)
        if ext == ".spi1d":
            return parse_spi1d_lut(filepath)
        raise ValueError(f"Unsupported native LUT format: {ext}")
    except Exception as exc:
        logger.error(f"[sumit_lut_native] Error loading LUT {filepath}: {exc}")
        raise
