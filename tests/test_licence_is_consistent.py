"""The pack must declare ONE licence, in every place it declares one.

This repository shipped for months with `LICENSE` saying Apache-2.0 and
`pyproject.toml` saying MIT. Nothing noticed, because nothing reads both. A
package manager reads pyproject, a human reads LICENSE, and GitHub reads
whichever it recognises first — so three parties can each be told something
different and all of them believe they know the terms.

It is a five-line check and it would have caught that, so it exists now. It is
also the guard on the 2026-09-19 relicense to GPL-3.0: a later edit that
updates one file and forgets the others puts the repository straight back into
the state it was just dug out of.
"""

from __future__ import annotations

import re
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]

#: The single source of truth. Changing this is a deliberate relicense, and
#: every assertion below has to be brought with it.
DECLARED = "GPL-3.0"


def test_the_license_file_is_the_full_gpl3_text():
    text = (PACK / "LICENSE").read_text(encoding="utf-8", errors="replace")
    assert "GNU GENERAL PUBLIC LICENSE" in text
    assert "Version 3, 29 June 2007" in text
    # The real text is ~674 lines. A stub or a one-line "see upstream" is not a
    # licence grant, and GPL section 4 requires the notice to travel with it.
    assert len(text.splitlines()) > 600, "LICENSE looks truncated"


def test_pyproject_agrees_with_the_license_file():
    # THE regression: pyproject said MIT while LICENSE said Apache-2.0.
    toml = (PACK / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'license\s*=\s*\{\s*text\s*=\s*"([^"]+)"', toml)
    assert m, "pyproject.toml declares no license text"
    assert m.group(1).startswith(DECLARED), (
        f"pyproject.toml says {m.group(1)!r}, LICENSE is {DECLARED}"
    )


def test_notice_files_agree():
    for name in ("NOTICE", "NOTICE.md"):
        text = (PACK / name).read_text(encoding="utf-8", errors="replace")
        assert "GNU General Public License v3.0" in text, (
            f"{name} does not state the current licence"
        )


def test_readme_agrees():
    readme = (PACK / "README.md").read_text(encoding="utf-8", errors="replace")
    assert re.search(r"^GPL-3\.0 \(see `LICENSE`\)\.", readme, re.M), (
        "README's License section does not say GPL-3.0"
    )


def test_no_source_file_claims_a_different_licence():
    # A per-file header is the one a reader trusts when they copy that file out.
    stale = []
    for path in PACK.rglob("*.py"):
        if any(part in path.parts for part in
               (".git", "__pycache__", "third_party", "THIRD_PARTY_LICENSES")):
            continue
        for i, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines()[:30], 1):
            # Only the pack's OWN licence claims matter. Lines that name an
            # upstream's licence ("ported from X, MIT") are attribution and
            # must stay exactly as they are.
            if re.search(r"^\s*#.*\b(Apache-2\.0|MIT License)\b", line) and \
                    not re.search(r"port|derived|upstream|from |\(c\)|Copyright \(c\) 20",
                                  line, re.I):
                stale.append(f"{path.relative_to(PACK)}:{i}: {line.strip()}")
    assert not stale, (
        "these headers still claim the old licence: " + "; ".join(stale[:8])
    )


def test_the_hdr_family_says_it_is_a_port():
    # The relicense only makes sense alongside the reason for it. If this claim
    # ever reverts to "clean-room", the GPL-3 licence stops being justified and
    # somebody will try to undo it.
    src = (PACK / "nukemax" / "nodes" / "hdr" / "nodes.py").read_text(encoding="utf-8")
    assert "clean-room" not in src.lower() or "not a clean-room" in src.lower()
    assert "radiance" in src.lower()
    assert "PORT, not a clean-room" in src
