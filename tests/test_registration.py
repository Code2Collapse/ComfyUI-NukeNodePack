"""NukeMax live registration count.

R11: the harness must load the pack the way ComfyUI does - module name is the
path with '.' replaced by '_x_', and sys.modules[name] is set BEFORE
exec_module. Anything else is measuring a different thing.

The previous version of this file did `sys.path.insert(0, ".")` and
`from __init__ import NODE_CLASS_MAPPINGS`. That imports the package's __init__
as a STANDALONE module, so every `from .nukemax...` inside it fails - and
because __init__ guards each group with try/except, those failures are
swallowed and the count comes back 0. It reported "expected 185, got 0" while
the pack was registering 185 perfectly well.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PACK = Path(__file__).resolve().parents[1]
WORKSPACE = PACK.parent

#: Live count. A change here must be deliberate.
#: 185 after Sumit batch + VideoSequenceLoad + OCIOGrade/Match/ApplyGrade = 189
EXPECTED_NODE_COUNT = 189


def _load_pack():
    """Load exactly as ComfyUI/nodes.py does."""
    core = WORKSPACE.parent / "ComfyUI_windows_portable" / "ComfyUI"
    saved = list(sys.path)
    if core.is_dir() and str(core) not in sys.path:
        sys.path.insert(0, str(core))
    # Production does NOT put the pack dir on sys.path; leaving it there lets an
    # absolute sibling import resolve that would fail for real users.
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != PACK]
    # Real ComfyUI always has PromptServer.instance by the time custom nodes
    # load, and two groups here (nkscript, mocha) register HTTP routes on it.
    # Standalone they raise "type object 'PromptServer' has no attribute
    # 'instance'", their groups are swallowed by __init__'s guards, and the pack
    # silently measures 14 nodes short. Stub it so this counts what production
    # counts.
    _restore_server = None
    try:
        from server import PromptServer  # type: ignore

        if getattr(PromptServer, "instance", None) is None:
            class _Routes:
                def __getattr__(self, _name):
                    def _decorator(*_a, **_k):
                        def _wrap(fn):
                            return fn
                        return _wrap
                    return _decorator

            class _Stub:
                routes = _Routes()

            PromptServer.instance = _Stub()          # type: ignore[attr-defined]
            _restore_server = PromptServer
    except Exception:
        pass

    try:
        name = str(PACK).replace(".", "_x_")
        spec = importlib.util.spec_from_file_location(
            name, PACK / "__init__.py", submodule_search_locations=[str(PACK)]
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod          # BEFORE exec_module
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path[:] = saved
        if _restore_server is not None:
            try:
                del _restore_server.instance      # leave the process as we found it
            except Exception:
                pass


def test_node_registration_count():
    # INVARIANT: a pack that fails to import a group registers FEWER nodes while
    # looking healthy - __init__ catches per-group failures on purpose. Pinning
    # the live count is the only thing that catches it.
    mod = _load_pack()
    mappings = getattr(mod, "NODE_CLASS_MAPPINGS", {})
    count = len(mappings)
    assert count == EXPECTED_NODE_COUNT, (
        f"expected {EXPECTED_NODE_COUNT} nodes, got {count}. "
        f"Sample of what loaded: {sorted(mappings)[:5]}"
    )


def test_the_sumit_port_nodes_are_actually_registered():
    # INVARIANT: the count alone could be right while the NEW nodes are missing
    # and something else drifted. Name them.
    mod = _load_pack()
    mappings = getattr(mod, "NODE_CLASS_MAPPINGS", {})
    for node_id in ("NukeMax_Levels", "NukeMax_ReadMultiPass",
                    "NukeMax_ShufflePass", "NukeMax_Viewer"):
        assert node_id in mappings, f"{node_id} did not register"


def test_aces_ocio_batch_nodes_are_registered():
    mod = _load_pack()
    mappings = getattr(mod, "NODE_CLASS_MAPPINGS", {})
    for node_id in (
        "NukeMax_VideoSequenceLoad",
        "NukeMax_OCIOGrade",
        "NukeMax_OCIOGradeMatch",
        "NukeMax_OCIOApplyGrade",
    ):
        assert node_id in mappings, f"{node_id} did not register"


def test_every_registered_class_has_the_comfy_contract():
    # INVARIANT: a class missing INPUT_TYPES/RETURN_TYPES/FUNCTION registers but
    # throws the moment it is used, which reads as "the node is broken".
    mod = _load_pack()
    bad = []
    for node_id, cls in getattr(mod, "NODE_CLASS_MAPPINGS", {}).items():
        for attr in ("INPUT_TYPES", "RETURN_TYPES", "FUNCTION"):
            if not hasattr(cls, attr):
                bad.append(f"{node_id}.{attr}")
        fn = getattr(cls, "FUNCTION", None)
        if fn and not hasattr(cls, fn):
            bad.append(f"{node_id}.FUNCTION={fn!r} has no such method")
    assert not bad, "incomplete node contracts: " + ", ".join(sorted(bad)[:12])


@pytest.mark.parametrize("node_id", ["NukeMax_ReadMultiPass", "NukeMax_ShufflePass"])
def test_multipass_nodes_speak_the_nuke_passes_type(node_id):
    # INVARIANT: the pass bundle is the whole point of these two - if the custom
    # type is not on their signature they cannot be wired to each other.
    mod = _load_pack()
    cls = getattr(mod, "NODE_CLASS_MAPPINGS", {})[node_id]
    spec = cls.INPUT_TYPES()
    io_text = repr(spec) + repr(getattr(cls, "RETURN_TYPES", ()))
    assert "NUKE_PASSES" in io_text, f"{node_id} does not reference NUKE_PASSES"
