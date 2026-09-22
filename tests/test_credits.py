"""Every upstream this pack ports from must be named in CREDITS.md.

Attribution rots in exactly one way: someone ports a family, writes an honest
header on the file, and the credits page never hears about it. Six months later
the only record is a comment nobody reads.

So the header IS the record, and this walks them. A module that names an
upstream repository in its first lines must have that repository in CREDITS.md,
or this fails with the URL it could not find.

The convention a ported module follows:

    # Ported from <Project> by <author> (<LICENCE>,
    # https://github.com/<owner>/<repo>), <what was taken>.

`NOTICE` carries the formal terms; CREDITS.md is the readable one. Both have to
exist and both have to agree with the source.
"""

from __future__ import annotations

import re
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
CREDITS = PACK / "CREDITS.md"

SKIP_DIRS = {"__pycache__", ".git", "third_party", "_deprecated", "_AUDIT",
             "node_modules", "tests", "_tests"}

#: How many lines at the top of a module count as its header.
HEADER_LINES = 30

_GITHUB = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)")
_ATTRIBUTION = re.compile(
    r"\b(ported from|Ported from|PORTED FROM|derived from|Derived from|"
    r"adapted from|Adapted from)\b")


def _source_files():
    for path in sorted(PACK.rglob("*.py")):
        if any(p in SKIP_DIRS for p in path.parts):
            continue
        yield path


def _attributed_modules() -> dict[Path, set[tuple[str, str]]]:
    """Modules whose header names an upstream GitHub project."""
    found: dict[Path, set[tuple[str, str]]] = {}
    for path in _source_files():
        try:
            head = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        block = "\n".join(head[:HEADER_LINES])
        if not _ATTRIBUTION.search(block):
            continue
        repos = {(o, r.removesuffix(".git")) for o, r in _GITHUB.findall(block)}
        if repos:
            found[path] = repos
    return found


def test_credits_file_exists():
    assert CREDITS.is_file(), (
        "CREDITS.md is where a user finds out whose work a node came from; "
        "NOTICE is the legal text, not a readable answer"
    )


def test_every_attributed_module_is_credited():
    # THE check. A header that names a repo the credits page has never heard of
    # means the attribution exists only for whoever opens that one file.
    credits = CREDITS.read_text(encoding="utf-8")
    missing = []
    for path, repos in _attributed_modules().items():
        for owner, repo in repos:
            if repo.lower() not in credits.lower():
                missing.append(f"{path.relative_to(PACK)} -> {owner}/{repo}")
    assert not missing, (
        "these modules name an upstream that CREDITS.md does not: "
        + "; ".join(sorted(missing))
    )


def test_the_scanner_actually_finds_the_known_ports():
    # A scanner that matches nothing passes this file silently. The HDR family
    # is known to carry headers, so it must show up.
    found = _attributed_modules()
    names = {p.name for p in found}
    assert len(found) >= 2, f"only found {len(found)} attributed modules: {names}"
    paths = {str(p.relative_to(PACK)).replace("\\", "/") for p in found}
    assert any(p.startswith("nukemax/nodes/hdr/") for p in paths), (
        f"the HDR port lost its attribution header; found {sorted(paths)}"
    )


def test_credits_names_a_licence_for_every_upstream_it_lists():
    # "We used their code" without "under these terms" is half an attribution.
    credits = CREDITS.read_text(encoding="utf-8")
    sections = re.findall(r"^### (.+?) — (.+)$", credits, re.M)
    assert sections, "CREDITS.md has no '### Project — Author' sections"
    for project, _author in sections:
        block = credits.split(f"### {project} — ", 1)[1].split("\n###", 1)[0]
        assert _GITHUB.search(block), f"{project}: no repository link"


def test_notice_and_credits_both_mention_the_ported_families():
    notice = (PACK / "NOTICE").read_text(encoding="utf-8")
    credits = CREDITS.read_text(encoding="utf-8")
    for token in ("Radiance", "GPL-3"):
        assert token in notice or token in (PACK / "NOTICE.md").read_text(
            encoding="utf-8"), f"the NOTICE files lost {token}"
    for token in ("radiance", "FXTD Studios", "GPL-3.0"):
        assert token in credits, f"CREDITS.md lost {token}"


def test_credits_says_the_hdr_family_is_a_port():
    # The licence of this whole pack rests on that sentence. If the credits page
    # ever softens it back to "inspired by", the GPL-3 has no stated cause.
    credits = CREDITS.read_text(encoding="utf-8")
    assert "port, not a clean-room" in credits.lower()
