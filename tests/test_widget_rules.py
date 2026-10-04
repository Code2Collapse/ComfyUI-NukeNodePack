"""Static rules for NukeMax web widget modules under web/widgets/."""

from __future__ import annotations

import re
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
WEB = PACK / "web"

ALLOWED_IMPORTS = frozenset({
    "../../../../scripts/app.js",
    "../../c2c_ui/index.js",
    "./hdr_curves.js",
})

WIDGET_FILES = [
    WEB / "widgets/viewer/viewer_panel.js",
    WEB / "widgets/io/exr_preview.js",
    WEB / "widgets/hdr/hdr_scope.js",
    WEB / "widgets/relight/light_placer.js",
    WEB / "widgets/relight/light_placer_2d.js",
    WEB / "widgets/roto/roto_editor.js",
    WEB / "widgets/audio/waveform_preview.js",
    WEB / "widgets/mocha/upload.js",
]


def _import_specs(src: str) -> list[str]:
    specs: list[str] = []
    for m in re.finditer(
        r'(?:import\s+[^;]*?\s+from\s+|import\s*)["\']([^"\']+)["\']',
        src,
    ):
        specs.append(m.group(1))
    return specs


def test_widget_imports_only_allowed_modules():
    for path in WIDGET_FILES:
        assert path.is_file(), f"missing widget {path}"
        specs = _import_specs(path.read_text(encoding="utf-8"))
        bad = [s for s in specs if s not in ALLOWED_IMPORTS]
        assert not bad, f"{path.name}: disallowed imports {bad}"


def test_widgets_use_mount_panel():
    for path in WIDGET_FILES:
        src = path.read_text(encoding="utf-8")
        assert "mountPanel(" in src, f"{path.name}: must mount via mountPanel"


def test_widgets_no_start_loading_loop():
    for path in WIDGET_FILES:
        src = path.read_text(encoding="utf-8")
        assert "startLoadingLoop(" not in src, f"{path.name}: must not use startLoadingLoop"


def test_widgets_no_self_rescheduling_raf_loops():
    loop_pat = re.compile(
        r"requestAnimationFrame\s*\(\s*(?:function\s*)?\(?\s*(\w+)",
    )
    for path in WIDGET_FILES:
        src = path.read_text(encoding="utf-8")
        for m in loop_pat.finditer(src):
            name = m.group(1)
            if re.search(rf"requestAnimationFrame\s*\(\s*{name}\b", src):
                raise AssertionError(
                    f"{path.name}: self-rescheduling rAF loop via {name}",
                )


def test_widgets_no_var_in_canvas_colours():
    colour_assign = re.compile(
        r"(?:fillStyle|strokeStyle)\s*=\s*[^;]*var\s*\(",
    )
    for path in WIDGET_FILES:
        src = path.read_text(encoding="utf-8")
        assert not colour_assign.search(src), (
            f"{path.name}: canvas colours must not use var() — resolve at draw time"
        )


def test_widgets_no_text_overflow_ellipsis():
    for path in WIDGET_FILES:
        src = path.read_text(encoding="utf-8")
        assert "text-overflow" not in src, f"{path.name}: must not ellipsize text"
        assert "ellipsis" not in src.lower(), f"{path.name}: must not ellipsize text"
