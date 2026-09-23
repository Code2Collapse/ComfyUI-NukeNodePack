"""ReLight 2D's light placer, and the contract it depends on.

The node shipped its lights as SIX numeric widgets - a position x and y for
each of three lights, plus four radii. Every one of those is a place on the
picture, and a place on a picture is something you point at. Typing 0.7 / 0.3
and re-rendering to find out where that landed is the slowest way there is to
put a key light down.

The placer drives those same widgets. It adds no backend field and keeps no
private state, which is the important part: the NUMBERS are what a saved
workflow stores, so a widget with its own copy of the position would lose the
placement on reload - the classic version of this bug.

These tests pin the name agreement. If the node renames a widget the dot stops
moving with no error at all, and the placer just looks broken.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

PACK = Path(__file__).resolve().parents[1]
if str(PACK) not in sys.path:
    sys.path.insert(0, str(PACK))

PLACER = PACK / "web" / "widgets" / "relight" / "light_placer_2d.js"
ENTRY = PACK / "web" / "nukemax.js"

#: Every widget the placer reads or writes.
DRIVEN = (
    "light_position_x", "light_position_y",
    "inner_circle_radius", "outer_circle_radius",
    "light2_position_x", "light2_position_y",
    "light2_inner_radius", "light2_outer_radius",
    "light3_position_x", "light3_position_y",
    "light3_inner_radius", "light3_outer_radius",
    "num_light_sources",
)


def placer_source() -> str:
    assert PLACER.exists(), "the 2D light placer is gone"
    return PLACER.read_text(encoding="utf-8")


@pytest.mark.parametrize("widget", DRIVEN)
def test_the_node_still_has_every_widget_the_placer_drives(widget):
    ghdr = pytest.importorskip("nukemax.nodes.relight.light_paint",
                               reason="ReLight 2D needs the v3 API, SciPy, PIL")
    ids = {i.id for i in ghdr.ReLight.define_schema().inputs}
    assert widget in ids, (
        f"ReLight 2D no longer has {widget!r}, so the placer writes to nothing "
        "and the dot moves while the render does not.")


@pytest.mark.parametrize("widget", DRIVEN)
def test_the_placer_still_names_every_widget(widget):
    assert f'"{widget}"' in placer_source(), (
        f"the placer stopped driving {widget!r}")


def test_the_placer_keeps_no_private_state():
    """serialize:false, because the numeric widgets ARE the saved state. A
    DOM widget that serialised its own copy would fight them on reload."""
    src = placer_source()
    assert "serialize: false" in src or "serialize:false" in src, (
        "the placer serialises its own state, which will disagree with the "
        "numeric widgets a saved workflow actually restores")


def test_the_placer_is_imported_by_the_entry_file():
    """NukeMax loads every widget from one entry file. A widget that is not
    imported there simply never runs."""
    assert "light_placer_2d.js" in ENTRY.read_text(encoding="utf-8")


def test_the_import_depth_is_right():
    """This pack's UI died once because a widget used three ../ where four
    were needed: WEB_DIRECTORY mounts at /extensions/<pack>/, so web/ is
    stripped and the count equals the depth from the PACK root. One 404 here
    takes down every NukeMax node's front-end, reported only as a
    vite:preloadError.
    """
    rel = PLACER.relative_to(PACK)
    want = len(rel.parts)
    for m in re.finditer(r"""from\s+["']((?:\.\./)+(?:scripts|extensions)/[^"']*)["']""",
                         placer_source()):
        assert m.group(1).count("../") == want, (
            f"{m.group(1)} uses {m.group(1).count('../')}x ../ but needs {want}x")


def test_it_does_not_collide_with_the_hemisphere_placer():
    """The 3D rig placer next door drives NukeMax_LightRigBuilder. Two
    extensions under one name means one of them silently loses."""
    other = (PACK / "web" / "widgets" / "relight" / "light_placer.js").read_text(encoding="utf-8")
    def ext_name(src):
        m = re.search(r"""registerExtension\(\s*\{\s*name\s*:\s*["']([^"']+)["']""", src)
        return m.group(1) if m else None
    assert ext_name(placer_source()) != ext_name(other)
    assert 'nodeData.name !== NODE_NAME' in placer_source()


def test_it_targets_the_2d_node_not_the_rig_builder():
    """Same word, different geometry: a light on a hemisphere is an angle, a
    light on a plate is a position. Binding the wrong one produces a widget
    whose drags mean nothing."""
    assert 'const NODE_NAME = "NukeMax_ReLight2D"' in placer_source()


def test_drag_listeners_live_on_the_window():
    """A fast drag leaves the 13px dot behind. With the listeners on the dot,
    the light then sticks to the cursor after the button comes up."""
    src = placer_source()
    assert "window.addEventListener(\"pointermove\"" in src
    assert "window.removeEventListener(\"pointermove\"" in src, (
        "the move listener is never removed - it outlives the node")


def test_radii_are_scaled_against_the_short_edge():
    """The backend builds its falloff against the short edge. A ring drawn
    against the long edge looks right on a square and lies on a 16:9 plate."""
    assert "shortEdge" in placer_source()
