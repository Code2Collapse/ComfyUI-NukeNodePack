"""Empty inputs get a sentence, not a raw JSONDecodeError / OSError (L7.87, 2026-10-12, tools/c2c_exec_audit.py)."""
from __future__ import annotations

import pytest

from nukemax.core.nkscript import serialize_from_json
from nukemax.nodes.audio import _load_audio
from nukemax.nodes.types_io import NODE_CLASS_MAPPINGS as TYPES_IO


def test_deserialize_nodes_explain_an_empty_or_broken_payload():
    cls = next(c for n, c in TYPES_IO.items() if n.startswith("NukeMax_Deserialize_"))
    with pytest.raises(ValueError, match="paste the JSON"):
        cls().execute("")
    with pytest.raises(ValueError, match="not valid JSON"):
        cls().execute("{nope")


def test_nk_script_and_audio_explain_missing_input(tmp_path):
    with pytest.raises(ValueError, match="node graph as JSON"):
        serialize_from_json("   ")
    with pytest.raises(ValueError, match="enter the path"):
        _load_audio("")
    with pytest.raises(FileNotFoundError, match="no file"):
        _load_audio(str(tmp_path / "missing.wav"))
