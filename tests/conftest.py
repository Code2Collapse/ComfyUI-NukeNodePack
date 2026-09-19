"""Make ComfyUI's own modules importable when the suite runs outside ComfyUI.

Most of this pack is deliberately testable with nothing but torch and numpy.
A few things cannot be: anything that writes a preview goes through
`folder_paths`, which only exists inside a ComfyUI checkout. Without it those
tests do not fail - they pass vacuously, because the node is built to degrade
quietly when the host is missing, so the suite would be green while the preview
was broken.

So: find a ComfyUI checkout if there is one and put it on sys.path. Tests that
need it are marked `requires_comfy` and SKIP (loudly, with a reason) when there
is none, rather than silently measuring the fallback path and calling it a pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PACK = Path(__file__).resolve().parents[1]
WORKSPACE = PACK.parent

#: Where a ComfyUI checkout usually sits relative to a custom-node pack. The
#: first two cover this workspace (Windows dev box, junctioned into the
#: portable install); the third covers a pack living in custom_nodes/ directly,
#: which is the layout on the Linux box.
_CANDIDATES = (
    WORKSPACE.parent / "ComfyUI_windows_portable" / "ComfyUI",
    WORKSPACE / "ComfyUI",
    PACK.parent.parent,
)


def _find_comfy() -> Path | None:
    for cand in _CANDIDATES:
        try:
            if (cand / "folder_paths.py").is_file():
                return cand
        except OSError:
            continue
    return None


COMFY_ROOT = _find_comfy()
if COMFY_ROOT is not None and str(COMFY_ROOT) not in sys.path:
    sys.path.insert(0, str(COMFY_ROOT))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_comfy: needs a real ComfyUI checkout on sys.path "
        "(folder_paths, temp directory)",
    )


def pytest_collection_modifyitems(config, items):
    if COMFY_ROOT is not None:
        return
    skip = pytest.mark.skip(
        reason="no ComfyUI checkout found next to this pack; "
               "folder_paths is unavailable"
    )
    for item in items:
        if "requires_comfy" in item.keywords:
            item.add_marker(skip)
