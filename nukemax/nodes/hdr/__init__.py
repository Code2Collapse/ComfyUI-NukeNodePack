"""HDR / IBL nodes — scene-linear imaging ported from Radiance (see NOTICE.md)."""
from .nodes import (
    HDR360Generate,
    HDRExposureBlend,
    HDRExpandDynamicRange,
    HDRFloat32ColorCorrect,
    HDRHighlightSynthesis,
    HDRHistogram,
    HDRImageToFloat32,
    HDRShadowHighlightRecovery,
    HDRToneMap,
)

# The generated-HDR decode lives in its own module: it reaches into
# ocio_color for the transfer curves, so one failure there must not take the
# nine math-only HDR nodes below with it.
try:
    from .generated_hdr import (
        NODE_CLASS_MAPPINGS as _GENHDR_MAPPINGS,
        NODE_DISPLAY_NAME_MAPPINGS as _GENHDR_DISPLAY,
    )
except Exception as _gh_exc:  # noqa: BLE001
    import logging as _lg
    _GENHDR_MAPPINGS, _GENHDR_DISPLAY = {}, {}
    _lg.getLogger("nukemax").warning(
        "[NukeMax] Generated HDR Decode unavailable: %s", _gh_exc)


NODE_CLASS_MAPPINGS = {
    **_GENHDR_MAPPINGS,
    "NukeMax_HDRImageToFloat32": HDRImageToFloat32,
    "NukeMax_HDRFloat32ColorCorrect": HDRFloat32ColorCorrect,
    "NukeMax_HDRExpandDynamicRange": HDRExpandDynamicRange,
    "NukeMax_HDRToneMap": HDRToneMap,
    "NukeMax_HDRHistogram": HDRHistogram,
    "NukeMax_HDRExposureBlend": HDRExposureBlend,
    "NukeMax_HDRShadowHighlightRecovery": HDRShadowHighlightRecovery,
    "NukeMax_HDRHighlightSynthesis": HDRHighlightSynthesis,
    "NukeMax_HDR360Generate": HDR360Generate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **_GENHDR_DISPLAY,
    "NukeMax_HDRImageToFloat32": "HDR Image To Float32 (NukeMax)",
    "NukeMax_HDRFloat32ColorCorrect": "HDR Float32 Color Correct (NukeMax)",
    "NukeMax_HDRExpandDynamicRange": "HDR Expand Dynamic Range (NukeMax)",
    "NukeMax_HDRToneMap": "HDR Tone Map (NukeMax)",
    "NukeMax_HDRHistogram": "HDR Histogram (NukeMax)",
    "NukeMax_HDRExposureBlend": "HDR Exposure Blend (NukeMax)",
    "NukeMax_HDRShadowHighlightRecovery": "HDR Shadow/Highlight Recovery (NukeMax)",
    "NukeMax_HDRHighlightSynthesis": "HDR Highlight Synthesis (NukeMax)",
    "NukeMax_HDR360Generate": "HDR 360 Panorama (NukeMax)",
}
