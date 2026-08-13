"""Node registration aggregator. Imports all ecosystem subpackages and
merges their `NODE_CLASS_MAPPINGS` / `NODE_DISPLAY_NAME_MAPPINGS`.
"""
from __future__ import annotations

import importlib
import logging

log = logging.getLogger("nukemax")

NODE_CLASS_MAPPINGS: dict = {}
NODE_DISPLAY_NAME_MAPPINGS: dict = {}

# Each ecosystem subpackage exposes the same two dicts.
# Use relative imports so this works no matter what folder name
# ComfyUI loads us under (e.g. "ComfyUI-NukeMaxNodes" with a hyphen).
_ECOSYSTEMS = (
    ".nukemax.nodes.types_io",  # serialize/deserialize for custom types
    ".nukemax.nodes.roto",
    ".nukemax.nodes.fft",
    ".nukemax.nodes.relight",
    ".nukemax.nodes.audio",
    ".nukemax.nodes.flow",
    ".nukemax.nodes.edges",
    # Migrated from ComfyUI-CustomNodePacks (Apr 2026)
    ".nukemax.nodes.utils",
    ".nukemax.nodes.io",
    ".nukemax.nodes.passes",
    ".nukemax.nodes.plate",
    ".nukemax.nodes.geometry_ext",
    ".nukemax.nodes.metadata",
    ".nukemax.nodes.color",
    # New (May 2026): deep compositing, shuffle, Nuke-style copy/paste.
    ".nukemax.nodes.deep",
    ".nukemax.nodes.shuffle",
    ".nukemax.nodes.nkscript",
    # New (May 2026): Mocha Pro tracking / shape / lens / project import.
    ".nukemax.nodes.mocha",
    # New (May 2026): STMap lens distortion + OCIO color transform.
    ".nukemax.nodes.lens",
    ".nukemax.nodes.ocio",
    # New (Jun 2026): chroma keyer + premult math (no more Nuke round-trip to pull a matte).
    ".nukemax.nodes.keying",
    # New (Jun 2026): everyday comp nodes — Reformat/Crop/ColorCorrect/Clamp/Saturation/Glow/Erode-Dilate.
    ".nukemax.nodes.comp",
    # New (Jun 2026): core Nuke daily-drivers — Grade/Merge/Transform/Mirror/Sharpen/Median/
    # Invert/Gamma/Multiply/Exposure/Dissolve/Keymix + generators (Constant/Checker/Bars/Ramp).
    ".nukemax.nodes.essentials",
    # Batch 2: Add/HueShift/Log2Lin/Posterize/ClipTest, Keyer/Difference/Despill,
    # Defocus/Soften, CornerPin/Tile/Switch, Noise/Radial/Rectangle.
    ".nukemax.nodes.essentials2",
    # Batch 3: Blur/EdgeDetect/Emboss/Bilateral/ZDefocus/MinMax (filter),
    # Position/ContactSheet/AppendClip (transform), Text/Grid/Vignette (generate),
    # ChannelMixer/HistEQ (color).
    ".nukemax.nodes.essentials3",
    # Comp-operator tier (Aug 2026): linear-float Grade / Transform+Filter /
    # Merge+Keying operators that the essentials batches did not cover.
    ".nukemax.nodes.nuke_grade",
    ".nukemax.nodes.nuke_transform",
    ".nukemax.nodes.nuke_merge",
    # Colour tier (Aug 2026): camera log curves + derived gamut matrices +
    # .cube LUTs + the OCIO CDL/File/Look transforms and config introspection.
    ".nukemax.nodes.ocio_color",
)

for mod_name in _ECOSYSTEMS:
    try:
        mod = importlib.import_module(mod_name, package=__name__)
        NODE_CLASS_MAPPINGS.update(getattr(mod, "NODE_CLASS_MAPPINGS", {}))
        NODE_DISPLAY_NAME_MAPPINGS.update(getattr(mod, "NODE_DISPLAY_NAME_MAPPINGS", {}))
    except Exception as exc:  # noqa: BLE001
        log.warning("[NukeMax] failed to import %s: %s", mod_name, exc)

# Tell ComfyUI where to find our JS.
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
