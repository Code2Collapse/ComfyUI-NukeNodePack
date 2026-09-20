"""INPUT_TYPES must never touch an unbounded amount of disk.

THE INCIDENT this exists for (2026-09-20). ComfyUI's UI would not open at all.
`/object_info` never returned - not in ten minutes - and since the frontend
blocks on it, the browser showed nothing. `/object_info/KSampler` hung too,
which ruled out any one node's schema and pointed at the asyncio event loop
being blocked wholesale.

Timing `INPUT_TYPES()` across all 1451 registered nodes found it. Every node in
the install built its schema in under 0.013s except two, which took 123 SECONDS
EACH: `NukeMax_LUTApply` and `NukeMax_OCIOFileTransform`. Both called
`_scan_luts()`, which `os.walk`ed every LUT search directory - and that list
included ComfyUI's OUTPUT directory, which had grown to 1,000,015 directories.
One walk took 129s; two nodes made it 246s, paid on every UI load.

`INPUT_TYPES` runs on the event loop, once per node, on every `/object_info`.
So the rule these tests enforce is: it may look at disk, but never without a
bound. Three independent bounds now exist and each is pinned below, because
any one of them alone would have prevented the outage.

CPU-only, no ComfyUI server, no weights.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

PACK = Path(__file__).resolve().parents[1]
if str(PACK) not in sys.path:
    sys.path.insert(0, str(PACK))

ocio = pytest.importorskip("nukemax.nodes.ocio_color")


# ── the bound that was missing ──────────────────────────────────────────────

def test_the_output_directory_is_never_searched_for_luts():
    """A LUT is an input asset, not a render.

    Searching among renders bought nothing and cost the whole server: output
    trees grow without limit, and this list is walked while the event loop
    waits.
    """
    import folder_paths

    dirs = [os.path.normcase(os.path.abspath(d)) for d in ocio._lut_search_dirs()]
    out = os.path.normcase(os.path.abspath(folder_paths.get_output_directory()))
    assert out not in dirs, (
        "the ComfyUI output directory is back in the LUT search path - this is "
        "the exact configuration that froze /object_info for 246 seconds"
    )


def test_the_walk_is_depth_capped(tmp_path, monkeypatch):
    """A pathological tree must not be descended forever."""
    deep = tmp_path
    for i in range(12):
        deep = deep / f"level{i}"
    deep.mkdir(parents=True)
    (deep / "buried.cube").write_text("LUT_3D_SIZE 2\n", encoding="utf-8")
    (tmp_path / "shallow.cube").write_text("LUT_3D_SIZE 2\n", encoding="utf-8")

    monkeypatch.setattr(ocio, "_lut_search_dirs", lambda: [str(tmp_path)])
    ocio._lut_scan_cache.clear()
    found = ocio._scan_luts({".cube"})

    assert "shallow.cube" in found
    assert not any("buried" in f for f in found), (
        f"descended past the {ocio._LUT_SCAN_MAX_DEPTH}-level cap: {found}"
    )


def test_the_walk_is_entry_capped(tmp_path, monkeypatch):
    """Whatever the shape of the tree, the scan stops."""
    for i in range(60):
        (tmp_path / f"d{i}").mkdir()
    monkeypatch.setattr(ocio, "_LUT_SCAN_MAX_ENTRIES", 10)
    monkeypatch.setattr(ocio, "_lut_search_dirs", lambda: [str(tmp_path)])
    ocio._lut_scan_cache.clear()
    ocio._scan_luts({".cube"})      # must return, not hang


def test_the_scan_is_cached_so_object_info_pays_once(tmp_path, monkeypatch):
    """/object_info calls INPUT_TYPES on every node, repeatedly. Without a
    cache the disk cost is multiplied by the node count, which is how two
    nodes turned a 129s walk into a 246s freeze."""
    (tmp_path / "a.cube").write_text("LUT_3D_SIZE 2\n", encoding="utf-8")
    calls = []

    real = ocio._walk_bounded

    def counting(root, exts, budget):
        calls.append(root)
        return real(root, exts, budget)

    monkeypatch.setattr(ocio, "_walk_bounded", counting)
    monkeypatch.setattr(ocio, "_lut_search_dirs", lambda: [str(tmp_path)])
    ocio._lut_scan_cache.clear()

    for _ in range(5):
        ocio._scan_luts({".cube"})
    assert len(calls) == 1, f"the scan ran {len(calls)} times, not once"


# ── the property, stated directly ───────────────────────────────────────────

@pytest.mark.parametrize("node_id", ["NukeMax_LUTApply", "NukeMax_OCIOFileTransform"])
def test_the_two_nodes_that_froze_the_server_build_their_schema_fast(node_id):
    """0.5s is already 40x slower than the slowest other node in the install.

    The point is not the exact number - it is that a regression here is a
    server outage, not a slow node, so it must fail the suite rather than be
    discovered by someone whose UI will not open.
    """
    cls = ocio.NODE_CLASS_MAPPINGS[node_id]
    ocio._lut_scan_cache.clear()
    t = time.perf_counter()
    cls.INPUT_TYPES()
    dt = time.perf_counter() - t
    assert dt < 0.5, f"{node_id}.INPUT_TYPES took {dt:.2f}s"


def test_every_nukemax_node_builds_its_schema_fast():
    """The whole pack, because the next node to do this will be a different one.

    Walks nukemax.nodes.* directly rather than the pack root, whose relative
    imports only resolve under ComfyUI's own loader.
    """
    import importlib
    import pkgutil

    import nukemax.nodes as nodes_pkg

    mappings = {}
    for info in pkgutil.iter_modules(nodes_pkg.__path__):
        try:
            mod = importlib.import_module(f"nukemax.nodes.{info.name}")
        except Exception:  # noqa: BLE001 - an unimportable module is another test's job
            continue
        mappings.update(getattr(mod, "NODE_CLASS_MAPPINGS", {}))

    assert len(mappings) > 50, (
        f"only {len(mappings)} nodes discovered - the walk found nothing to check"
    )

    slow = []
    for node_id, cls in mappings.items():
        if not hasattr(cls, "INPUT_TYPES"):
            continue
        t = time.perf_counter()
        try:
            cls.INPUT_TYPES()
        except Exception:  # noqa: BLE001 - a raising schema is a different test's job
            continue
        dt = time.perf_counter() - t
        if dt > 0.5:
            slow.append(f"{node_id} {dt:.2f}s")
    assert not slow, "schema build is on the event loop; these block it: " + ", ".join(slow)
