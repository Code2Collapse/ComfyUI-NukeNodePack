"""The front-end has to actually load.

Three failures in this pack's history were all invisible to every Python test:

  * a widget file written, reviewed and committed but never imported from the
    entry point, so the node shipped with no UI at all;
  * a relative import pointing at a file that had been moved, which 404s and
    takes the WHOLE module graph down with it - every widget after it in the
    import list stops registering, not just the broken one;
  * a syntax error in one module, same blast radius.

None of those raise in Python. They are a blank node in the browser. This file
checks the module graph the way the browser resolves it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PACK = Path(__file__).resolve().parents[1]
WEB = PACK / "web"
ENTRY = WEB / "nukemax.js"
NODE = shutil.which("node")

#: `import "..."` / `from "..."`, relative specifiers only.
_IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*import\s+(?:[^'"]*?\sfrom\s+)?['"](\.[^'"]+)['"]""",
    re.MULTILINE,
)


def _all_js() -> list[Path]:
    return sorted(p for p in WEB.rglob("*.js") if "node_modules" not in p.parts)


def _relative_imports(path: Path) -> list[str]:
    return _IMPORT_RE.findall(path.read_text(encoding="utf-8"))


def _reachable_from_entry() -> set[Path]:
    """Everything the browser would fetch, starting at the entry point."""
    seen: set[Path] = set()
    queue = [ENTRY]
    while queue:
        cur = queue.pop()
        if cur in seen or not cur.is_file():
            continue
        seen.add(cur)
        for spec in _relative_imports(cur):
            target = (cur.parent / spec).resolve()
            # ComfyUI serves the pack's web dir; ../../scripts/* is the host
            # frontend and is not ours to resolve.
            try:
                target.relative_to(WEB)
            except ValueError:
                continue
            queue.append(target)
    return seen


def test_entry_point_exists():
    assert ENTRY.is_file(), "web/nukemax.js is the only file ComfyUI loads by name"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("path", _all_js(), ids=lambda p: str(p.relative_to(WEB)))
def test_every_module_parses(path: Path):
    # INVARIANT: a syntax error takes down every module imported after it, not
    # just this one. universal_reroute.js in the sibling pack was a SyntaxError
    # for long enough that the node shipped with no frontend at all.
    r = subprocess.run([NODE, "--check", str(path)], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, f"{path.relative_to(WEB)} does not parse:\n{r.stderr}"


def test_every_relative_import_resolves():
    # INVARIANT: an import of a file that no longer exists 404s, and the browser
    # discards the whole module graph below it. This is the exact failure that
    # broke the WanDirector timeline.
    missing = []
    for js in _all_js():
        for spec in _relative_imports(js):
            target = (js.parent / spec).resolve()
            try:
                target.relative_to(WEB)
            except ValueError:
                continue              # ../../scripts/* - the host frontend
            if not target.is_file():
                missing.append(f"{js.relative_to(WEB)} -> {spec}")
    assert not missing, "dangling imports: " + "; ".join(missing)


def test_every_extension_module_is_reachable_from_the_entry_point():
    # INVARIANT: registerExtension only runs if something imports the file.
    # A widget nobody imports is a node with no UI, and nothing says so.
    reachable = _reachable_from_entry()
    orphans = []
    for js in _all_js():
        src = js.read_text(encoding="utf-8")
        if "registerExtension" not in src:
            continue                  # a helper module; reached via its importer
        if js not in reachable:
            orphans.append(str(js.relative_to(WEB)))
    assert not orphans, (
        "these modules call registerExtension but nothing imports them, so they "
        "never run: " + ", ".join(sorted(orphans))
    )


def test_the_hdr_scope_is_wired():
    # The batch this file was added with. Named so a reordering of the import
    # list cannot quietly drop it.
    assert "widgets/hdr/hdr_scope.js" in ENTRY.read_text(encoding="utf-8")


def test_no_widget_module_imports_a_sibling_pack():
    # INVARIANT: R10 - no cross-pack runtime imports. A path into
    # ComfyUI-CustomNodePacks resolves on this machine and 404s on a box that
    # does not have that pack, taking this pack's frontend down with it.
    offenders = []
    for js in _all_js():
        src = js.read_text(encoding="utf-8")
        for pack in ("ComfyUI-CustomNodePacks", "ComfyUI-MiniMaxSuite",
                     "ComfyUI-WanAnimatePreprocessV2", "ComfyUI-WanNodeExperiments"):
            if pack in src:
                offenders.append(f"{js.relative_to(WEB)} -> {pack}")
    assert not offenders, "cross-pack frontend imports: " + "; ".join(offenders)

# ── the uniform layer: every node gets the same house treatment ─────────────

def _family_colour_keys() -> list[str]:
    """The FAMILY_COLOR keys, read out of the kit rather than duplicated here."""
    kit = (WEB / "widgets" / "_nukemax_kit.js").read_text(encoding="utf-8")
    block = kit.split("const FAMILY_COLOR = {", 1)[1].split("};", 1)[0]
    return re.findall(r"(\w+)\s*:", block)


def _family_of(category: str, keys: list[str]) -> str:
    """Mirrors familyOf() in _nukemax_kit.js."""
    tail = category.split("/")[-1] if category else ""
    if tail in keys:
        return tail
    for k in keys:
        if k in category:
            return k
    return ""


def test_every_category_resolves_to_a_family_badge():
    # INVARIANT: the badge is the one piece of UI EVERY node in the pack gets.
    # A category with no colour renders an empty chip - a blank rectangle that
    # reads as a rendering fault, and it is invisible in Python. Six categories
    # (14 nodes) were in that state when this test was written.
    from tests.test_registration import _load_pack

    keys = _family_colour_keys()
    mod = _load_pack()
    blank = {}
    for node_id, cls in getattr(mod, "NODE_CLASS_MAPPINGS", {}).items():
        category = str(getattr(cls, "CATEGORY", ""))
        if not _family_of(category, keys):
            blank.setdefault(category, []).append(node_id)
    assert not blank, (
        "these categories render a blank family badge; add a FAMILY_COLOR entry "
        "in web/widgets/_nukemax_kit.js: "
        + ", ".join(f"{c} ({len(n)} nodes)" for c, n in sorted(blank.items()))
    )


def test_the_viewer_has_a_front_end_and_emits_previews():
    # INVARIANT: a node called Viewer with no picture on it is the complaint
    # this pack exists to answer. Both halves are needed - the ui.images
    # emission AND the widget that draws them.
    backend = (PACK / "nukemax" / "nodes" / "viewer" / "__init__.py").read_text(
        encoding="utf-8")
    assert '"images": _write_previews(result)' in backend
    assert "widgets/viewer/viewer_panel.js" in ENTRY.read_text(encoding="utf-8")
