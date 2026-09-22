"""Every relative JS import must resolve to a file that exists.

THE INCIDENT this exists for (2026-09-20). The user reported that node
parameters "became hidden/corrupted" - widgets simply absent from the node
body. No python test could see it, because nothing was wrong in python.

Two widget modules imported ComfyUI's app with the wrong number of "../".
A file at `web/widgets/hdr/hdr_scope.js` is SERVED at
`/extensions/ComfyUI-NukeMaxNodes/widgets/hdr/hdr_scope.js`, so reaching
`/scripts/app.js` needs FOUR `../`, not the three that are correct from the
pack root. Three resolves to `/extensions/scripts/app.js`, which 404s.

That alone would be a dead widget. What made it a pack-wide outage is that
`nukemax.js` imports every widget module, so one 404 took the ENTIRE front-end
down with it - and the browser reports that as a `vite:preloadError`, not as a
broken node. Every NukeMax node then drew with none of its custom UI.

The rule: depth of the file under the web root, plus two (for `/extensions/`
and the pack directory), is how many `../` it takes to reach the server root.

Static - no ComfyUI server, no browser.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

import pytest

PACK = Path(__file__).resolve().parents[1]
WEB = PACK / "web"

# Paths ComfyUI itself serves from the web root. They are not files in this
# repo, so existence is asserted against this list rather than the filesystem.
CORE_PREFIXES = ("scripts/", "extensions/core/", "lib/", "types/", "assets/")

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"""^[^\n'"]*?//.*?$""", re.M)
_IMPORT = re.compile(
    r"""(?:^|\s)(?:import|export)\s+(?:[^'"()]*?\sfrom\s+)?['"]([^'"]+)['"]"""
    r"""|import\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.M,
)


def _strip_comments(src: str) -> str:
    # Several modules document their own usage with an example import line in
    # a comment. Counting those reports failures that do not exist.
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", src))


def _js_files() -> list[Path]:
    return sorted(WEB.rglob("*.js")) if WEB.is_dir() else []


def _imports(path: Path) -> list[tuple[int, str]]:
    src = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
    out = []
    for m in _IMPORT.finditer(src):
        spec = m.group(1) or m.group(2)
        if spec and spec.startswith("."):
            out.append((src[:m.start()].count("\n") + 1, spec))
    return out


def _served_dir(path: Path) -> str:
    """The URL directory this file is served from, relative to the web root."""
    rel = path.relative_to(WEB).as_posix()
    return posixpath.dirname(f"extensions/{PACK.name}/{rel}")


@pytest.mark.skipif(not WEB.is_dir(), reason="pack has no web/ directory")
def test_every_relative_import_resolves():
    broken = []
    for f in _js_files():
        for line, spec in _imports(f):
            target = posixpath.normpath(posixpath.join(_served_dir(f), spec))
            if target.startswith(".."):
                broken.append(
                    f"{f.relative_to(WEB).as_posix()}:{line} -> {spec} "
                    f"escapes the server root")
                continue
            if target.startswith(CORE_PREFIXES):
                continue                      # served by ComfyUI itself
            prefix = f"extensions/{PACK.name}/"
            if not target.startswith(prefix):
                broken.append(
                    f"{f.relative_to(WEB).as_posix()}:{line} -> {spec} "
                    f"resolves to /{target}, outside this pack and not a core path")
                continue
            on_disk = WEB / target[len(prefix):]
            if not on_disk.is_file():
                broken.append(
                    f"{f.relative_to(WEB).as_posix()}:{line} -> {spec} "
                    f"resolves to /{target}, which does not exist")
    assert not broken, (
        "a JS import that 404s takes down every module that imports it, and "
        "the node then renders with none of its widgets:\n  " + "\n  ".join(broken)
    )


@pytest.mark.skipif(not WEB.is_dir(), reason="pack has no web/ directory")
def test_the_app_import_depth_matches_the_files_own_depth():
    """Stated as the rule, so the failure names the number to use.

    This is the specific slip that caused the outage, and it is easy to
    reintroduce by copying a widget file into a deeper directory.
    """
    wrong = []
    for f in _js_files():
        depth = len(f.relative_to(WEB).parent.parts)    # 0 at the web root
        need = depth + 2                                 # + /extensions/ + pack dir
        src = _strip_comments(f.read_text(encoding="utf-8", errors="replace"))
        for m in re.finditer(r"""['"]((?:\.\./)+)(scripts/[A-Za-z0-9_.]+)['"]""", src):
            got = m.group(1).count("../")
            if got != need:
                wrong.append(
                    f"{f.relative_to(WEB).as_posix()} imports {m.group(2)} with "
                    f"{got} x '../' but sits {depth} deep, so it needs {need}")
    assert not wrong, "\n  " + "\n  ".join(wrong)


@pytest.mark.skipif(not WEB.is_dir(), reason="pack has no web/ directory")
def test_the_check_can_actually_fail(tmp_path, monkeypatch):
    """Negative control: a deliberately wrong depth must be caught.

    Without this, a regex that quietly stopped matching would keep both tests
    above green forever while the front-end was broken.
    """
    fake_web = tmp_path / "web"
    (fake_web / "widgets" / "hdr").mkdir(parents=True)
    (fake_web / "widgets" / "hdr" / "x.js").write_text(
        'import { app } from "../../../scripts/app.js";\n', encoding="utf-8")
    monkeypatch.setattr("tests.test_js_imports_resolve.WEB", fake_web)

    with pytest.raises(AssertionError, match=r"needs 4"):
        test_the_app_import_depth_matches_the_files_own_depth()
