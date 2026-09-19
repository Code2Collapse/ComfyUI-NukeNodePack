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

NODE_CLASS_MAPPINGS = {
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
