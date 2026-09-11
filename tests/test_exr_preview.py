"""EXR preview route helpers.

The routes themselves need a running PromptServer, so what is testable offline
is the part that actually carries risk: the path allow-list, and the sequence
detection that decides which frame a scrubber is even allowed to ask for.

CPU-only, no weights, no server.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PACK = Path(__file__).resolve().parents[1]
if str(PACK) not in sys.path:
    sys.path.insert(0, str(PACK))

from nukemax.nodes.io import exr_preview_server as eps  # noqa: E402


# ── path allow-list ──────────────────────────────────────────────────────────

def test_path_outside_allowed_roots_is_refused(tmp_path, monkeypatch):
    # INVARIANT: this is the whole point of the allow-list. A route that reads
    # any absolute path turns the browser into a file-exfiltration tool for any
    # page that can reach localhost:8188.
    monkeypatch.setattr(eps, "_comfy_dirs", lambda: [str(tmp_path / "allowed")])
    monkeypatch.delenv("NUKEMAX_EXR_ROOTS", raising=False)
    (tmp_path / "allowed").mkdir()
    outside = tmp_path / "secret.exr"
    outside.write_bytes(b"not really an exr")
    with pytest.raises(ValueError, match="outside the directories"):
        eps._resolve_readable(str(outside))


def test_path_inside_an_allowed_root_is_accepted(tmp_path, monkeypatch):
    # INVARIANT: the guard must not be so tight that the normal case fails.
    root = tmp_path / "allowed"
    root.mkdir()
    monkeypatch.setattr(eps, "_comfy_dirs", lambda: [str(root)])
    monkeypatch.delenv("NUKEMAX_EXR_ROOTS", raising=False)
    f = root / "plate.exr"
    f.write_bytes(b"x")
    assert eps._resolve_readable(str(f)) == os.path.realpath(str(f))


def test_env_var_extends_the_allow_list(tmp_path, monkeypatch):
    # INVARIANT: plates live outside ComfyUI. NUKEMAX_EXR_ROOTS is the documented
    # way to preview them, so it must actually widen the allow-list.
    plates = tmp_path / "plates"
    plates.mkdir()
    f = plates / "shot.exr"
    f.write_bytes(b"x")
    monkeypatch.setattr(eps, "_comfy_dirs", lambda: [])
    monkeypatch.setenv("NUKEMAX_EXR_ROOTS", str(plates))
    assert eps._resolve_readable(str(f)) == os.path.realpath(str(f))


def test_traversal_out_of_an_allowed_root_is_refused(tmp_path, monkeypatch):
    # INVARIANT: ".." must not escape. realpath() is what makes this hold; a
    # plain startswith() on the raw string would let ../../ through.
    root = tmp_path / "allowed"
    root.mkdir()
    (tmp_path / "secret.exr").write_bytes(b"x")
    monkeypatch.setattr(eps, "_comfy_dirs", lambda: [str(root)])
    monkeypatch.delenv("NUKEMAX_EXR_ROOTS", raising=False)
    with pytest.raises(ValueError, match="outside the directories"):
        eps._resolve_readable(str(root / ".." / "secret.exr"))


def test_non_image_extensions_are_refused(tmp_path, monkeypatch):
    # INVARIANT: even inside an allowed root, the preview reads IMAGES only.
    root = tmp_path / "allowed"
    root.mkdir()
    monkeypatch.setattr(eps, "_comfy_dirs", lambda: [str(root)])
    f = root / "config.yaml"
    f.write_bytes(b"secret: 1")
    with pytest.raises(ValueError, match="Only image files"):
        eps._resolve_readable(str(f))


def test_empty_path_is_refused():
    # INVARIANT: an empty path must not resolve to the current directory.
    with pytest.raises(ValueError, match="No file path"):
        eps._resolve_readable("   ")


# ── sequence detection ───────────────────────────────────────────────────────

def _mk(dirpath: Path, name: str) -> None:
    (dirpath / name).write_bytes(b"x")


def test_hash_template_finds_every_frame(tmp_path):
    # INVARIANT: '####' is how a compositor writes a sequence; the scrubber's
    # range comes straight from this.
    for i in (1, 2, 3, 7):
        _mk(tmp_path, "render.%04d.exr" % i)
    template, frames = eps._sequence_frames(str(tmp_path / "render.####.exr"))
    assert frames == [1, 2, 3, 7]
    assert template and template.endswith("render.%04d.exr")


def test_any_frame_of_a_sequence_detects_the_whole_range(tmp_path):
    # INVARIANT: pointing at frame 2 must find 1..3, because that is what a user
    # does - they browse to one file, not to a pattern.
    for i in (1, 2, 3):
        _mk(tmp_path, "shot_%03d.exr" % i)
    _template, frames = eps._sequence_frames(str(tmp_path / "shot_002.exr"))
    assert frames == [1, 2, 3]


def test_printf_template_is_understood(tmp_path):
    # INVARIANT: %04d is the other spelling of the same thing.
    for i in (10, 11):
        _mk(tmp_path, "plate.%04d.exr" % i)
    _t, frames = eps._sequence_frames(str(tmp_path / "plate.%04d.exr"))
    assert frames == [10, 11]


def test_single_still_reports_no_sequence(tmp_path):
    # INVARIANT: a still must NOT grow a frame scrubber.
    _mk(tmp_path, "matte.exr")
    template, frames = eps._sequence_frames(str(tmp_path / "matte.exr"))
    assert frames == []
    assert template is None


# ── channel grouping ─────────────────────────────────────────────────────────

def test_channel_groups_collapse_aov_prefixes():
    # INVARIANT: the AOV dropdown lists LAYERS, not 40 raw channel names.
    names = ["R", "G", "B", "A", "depth.Z", "normal.X", "normal.Y", "normal.Z"]
    assert eps._channel_groups(names) == ["rgba", "depth", "normal"]


def test_select_rgb_promotes_single_channel_to_grey():
    # INVARIANT: a depth AOV is one channel; previewing it must not crash or
    # show a red-only image.
    np = pytest.importorskip("numpy")
    arr = np.zeros((4, 4, 5), dtype="float32")
    arr[:, :, 4] = 0.5
    names = ["R", "G", "B", "A", "depth.Z"]
    out = eps._select_rgb(arr, names, "depth")
    assert out.shape == (4, 4, 3)
    assert float(out.min()) == pytest.approx(0.5)
