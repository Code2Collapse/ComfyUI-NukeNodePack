"""Decode a generated image as log, and say whether that was even valid.

WHY THIS NODE EXISTS.

A diffusion model emits `[0,1]`. To get scene-linear HDR out of one, it has to
have been TRAINED to emit a log encoding - LogC3, say - and then you run the
inverse curve and the highlights are real because they were generated.

Run that same inverse curve on a model that was trained on ordinary
display-referred sRGB and you get a picture with values above 1.0 that looks
like HDR and is not. The specular on a window frame was clipped at 1.0 during
training and is still clipped; decoding gives a smooth ramp where a real
highlight would have had detail. Nothing raises. The file is a valid EXR. It is
simply not HDR, and the only way to find out is to grade it and discover there
is nothing in the highlights to recover.

THE CHECK IS NOT A HEURISTIC. Every log curve maps linear zero to a positive
code value - LogC3 to 0.0928, LogC4 to 0.0929, ACEScct to 0.0729 - because the
encoding reserves that footroom for negative-linear sensor noise. So:

    a genuinely LogC3-encoded image has NO pixels below 0.0928
    an sRGB image decoded as LogC3 puts about 9% of its pixels below it

and every one of those decodes to a NEGATIVE linear value. Negative light does
not exist. A nonzero count is proof, not a guess, that the input is not in the
encoding you claimed, and the node says so instead of writing a confident EXR.

Measured on this pack's own curves:

    curve         encoded black   mid grey   ceiling (linear at code 1.0)
    ARRI LogC3       0.0928        0.3910         55.08
    ARRI LogC4       0.0929        0.2784        469.80
    ACEScct          0.0729        0.4136        222.86

The curves themselves are this pack's existing `ocio_color._curves`, so there
is one implementation of LogC3 here rather than two that can drift apart.
"""

from __future__ import annotations

import numpy as np
import torch

from ..ocio_color._curves import resolve_curve
from ..._is_changed_util import hash_args_and_kwargs
from ..._tensor_util import require_image_bhwc
from ...utils.resilience import resilient

# Only curves with FOOTROOM are offered, and that is not a stylistic choice -
# the whole check depends on it. Measured across this pack's curve set:
#
#     ACEScct               linear 0 -> 0.0729      usable
#     ARRI LogC3            linear 0 -> 0.0928      usable
#     ARRI LogC4            linear 0 -> 0.0929      usable
#     Canon Log 3           linear 0 -> 0.1251      usable
#     Cineon                linear 0 -> 0.0929      usable
#     Panasonic V-Log       linear 0 -> 0.1250      usable
#     RED Log3G10           linear 0 -> 0.0916      usable
#     Sony S-Log3           linear 0 -> 0.0929      usable
#
#     DaVinci Intermediate  linear 0 -> 0.0000      NO footroom
#     ACEScc                linear 0 -> -0.3585     NO footroom (below zero)
#
# For those last two there is no code value that proves an image is not in
# them, so the check would pass everything and the node would give exactly the
# false confidence it exists to prevent. They are excluded rather than offered
# with a caveat nobody reads.
GENERATED_CURVES = ("ARRI LogC3", "ARRI LogC4", "ACEScct", "Sony S-Log3",
                    "RED Log3G10", "Panasonic V-Log", "Canon Log 3", "Cineon")

# Below this, a curve has no usable footroom and the check is meaningless.
MIN_FOOTROOM = 1e-4

# Above this fraction of physically-impossible pixels, the input is simply not
# in the claimed encoding. 1% is well clear of the ~0.0% a real log image
# gives and far below the ~9% a display-referred image gives, so it separates
# the two cases without sitting on top of either.
IMPOSSIBLE_FRACTION_LIMIT = 0.01


def _curve(name: str):
    fwd, inv, gamut = resolve_curve(name)
    return fwd, inv, gamut


def _scalar(fn, value: float) -> float:
    out = fn(torch.tensor([float(value)], dtype=torch.float32))
    return float(np.asarray(out).reshape(-1)[0])


def encoded_black(curve: str) -> float:
    """The code value linear zero maps to. Nothing real sits below it.

    Refuses a curve with no footroom rather than returning 0.0 and letting the
    check silently pass everything - which is worse than no check, because the
    node would then be asserting something it never tested.
    """
    fwd, _, _ = _curve(curve)
    black = _scalar(fwd, 0.0)
    if black < MIN_FOOTROOM:
        raise ValueError(
            f"{curve} puts linear zero at code {black:.4f}, so it has no "
            "footroom - there is no code value that could prove an image is "
            "NOT in this encoding. The validity check this node is built "
            "around cannot work for it, so it is not offered. Use a curve "
            "with footroom (" + ", ".join(GENERATED_CURVES) + ") and convert "
            "afterwards with Camera Log Convert if you need this one.")
    return black


def ceiling(curve: str) -> float:
    """Linear value at code 1.0 - how much range the encoding can carry."""
    _, inv, _ = _curve(curve)
    return _scalar(inv, 1.0)


def mid_grey(curve: str) -> float:
    """Where 0.18 linear lands. Useful for eyeballing whether an image is
    sitting where a log image should sit."""
    fwd, _, _ = _curve(curve)
    return _scalar(fwd, 0.18)


def impossible_fraction(image: torch.Tensor, curve: str) -> float:
    """Fraction of pixels that would decode to negative linear light.

    This is the whole check. It is arithmetic, not statistics: a value below
    the curve's own black point decodes below zero, and there is no such thing
    as negative light.
    """
    return float((image < encoded_black(curve)).float().mean())


def decode(image: torch.Tensor, curve: str, *,
           clamp_negative: bool = True) -> torch.Tensor:
    """Log code values -> scene-linear."""
    _, inv, _ = _curve(curve)
    lin = torch.as_tensor(np.asarray(inv(image.float())), dtype=torch.float32)
    if clamp_negative:
        lin = lin.clamp(min=0.0)
    return lin


def reinhard(linear: torch.Tensor) -> torch.Tensor:
    """A preview only. Scene-linear cannot be shown on a display as-is, and a
    plain clamp would hide exactly the highlights this node is about."""
    return (linear / (1.0 + linear)).clamp(0.0, 1.0)


def describe(image: torch.Tensor, linear: torch.Tensor, curve: str,
             impossible: float, *, proceeded: bool) -> str:
    """What was decoded, and whether it meant anything."""
    black = encoded_black(curve)
    cap = ceiling(curve)
    peak = float(linear.max())
    above_one = float((linear > 1.0).float().mean())

    lines = [
        f"Decoded as {curve}: code 1.0 becomes {cap:.1f} linear, "
        f"mid grey sits at {mid_grey(curve):.4f}.",
        f"Peak linear value {peak:.2f}; {above_one * 100:.1f}% of pixels are "
        "above 1.0.",
    ]

    if impossible > IMPOSSIBLE_FRACTION_LIMIT:
        lines.append(
            f"THIS IMAGE IS NOT {curve.upper()}-ENCODED. "
            f"{impossible * 100:.1f}% of its pixels are below {black:.4f}, "
            "which is where this curve puts linear zero - they decode to "
            "NEGATIVE light, which does not exist. A genuinely log-encoded "
            "image has none at all.")
        lines.append(
            "What you are most likely looking at: a model trained on ordinary "
            "display-referred output. Running an inverse log curve over it "
            "produces values above 1.0 that LOOK like HDR and are not - the "
            "highlights were clipped during training and are still clipped, "
            "so there is nothing in them to recover when you grade it.")
        lines.append(
            "To get real HDR out of a generator it has to have been TRAINED "
            "to emit this encoding, usually via a LoRA whose targets were "
            "log-encoded frames. Without that, this node is applying a curve, "
            "not recovering range.")
        if proceeded:
            lines.append(
                "Proceeded anyway because assume_encoded is on. The output is "
                "an expansion, not a reconstruction - do not ship it as HDR.")
    else:
        lines.append(
            f"The encoding checks out: {impossible * 100:.2f}% of pixels fall "
            f"below the curve's black point of {black:.4f}, so nothing decodes "
            "to negative light. That is consistent with genuine "
            f"{curve} material.")
        if above_one < 0.001:
            lines.append(
                "Note: almost nothing decoded above 1.0. The encoding is "
                "right, but the image has no highlight range in it - either "
                "the shot genuinely has none, or it was generated without "
                "anything bright in frame.")

    return "\n".join(lines)


@resilient
class GeneratedHDRDecode:
    """Decode a generated [0,1] image to scene-linear, and check it is real."""

    DESCRIPTION = (
        "Decode a model's [0,1] output as a log encoding to get scene-linear "
        "HDR - and check that the claim holds. Every log curve maps linear "
        "zero to a positive code value, so an image with pixels below that "
        "point is not in that encoding: those pixels decode to negative light. "
        "The check is arithmetic, not a guess, and it catches the case that "
        "otherwise passes silently - an sRGB-trained model whose output looks "
        "like HDR after decoding but has no highlight detail to recover."
    )
    CATEGORY = "NukeMax/HDR"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "IMAGE", "BOOLEAN", "FLOAT", "STRING")
    RETURN_NAMES = ("hdr_linear", "preview", "is_encoded", "peak_linear", "report")
    OUTPUT_TOOLTIPS = (
        "Scene-linear HDR. Values run well above 1.0 - send it to an EXR "
        "writer, not to a preview.",
        "Reinhard-tonemapped for looking at. Scene-linear cannot be shown "
        "directly, and a plain clamp would hide the highlights this is about.",
        "False when the input is not actually in the chosen encoding.",
        "The largest linear value produced.",
        "What was decoded and whether it meant anything.",
    )

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {
                    "tooltip": "A model's [0,1] output, believed to be "
                               "log-encoded."}),
                "log_curve": (list(GENERATED_CURVES), {
                    "default": "ARRI LogC3",
                    "tooltip": "The encoding the model was TRAINED to emit - "
                               "not one picked for the look. LogC3 carries "
                               "about 55x linear, LogC4 about 470x, ACEScct "
                               "about 223x."}),
            },
            "optional": {
                "assume_encoded": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Decode even when the check says the input is "
                               "not in this encoding. The result is an "
                               "expansion, not a reconstruction - useful for "
                               "looking at, not for shipping as HDR."}),
                "clamp_negative": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Clamp negative linear values to zero. Turn it "
                               "OFF only to inspect how far below zero a bad "
                               "decode goes; an EXR with negative light in it "
                               "will upset anything downstream."}),
            },
        }

    def execute(self, image, log_curve, assume_encoded=False,
                clamp_negative=True):
        require_image_bhwc(image)
        img = image.float()

        impossible = impossible_fraction(img, log_curve)
        ok = impossible <= IMPOSSIBLE_FRACTION_LIMIT

        if not ok and not assume_encoded:
            raise ValueError(
                f"This image is not {log_curve}-encoded: "
                f"{impossible * 100:.1f}% of its pixels sit below "
                f"{encoded_black(log_curve):.4f}, the code value this curve "
                "gives linear zero, so they would decode to negative light. A "
                "genuinely log-encoded image has none.\n\n"
                "Most likely the model was trained on ordinary "
                "display-referred output, in which case decoding produces "
                "values above 1.0 that look like HDR but have no highlight "
                "detail to recover - they were clipped during training.\n\n"
                "Pick the encoding the model actually emits, or switch on "
                "assume_encoded to decode anyway and get an expansion rather "
                "than a reconstruction.")

        linear = decode(img, log_curve, clamp_negative=bool(clamp_negative))
        report = describe(img, linear, log_curve, impossible,
                          proceeded=not ok)
        return (linear, reinhard(linear), bool(ok), float(linear.max()), report)


NODE_CLASS_MAPPINGS = {
    "NukeMax_GeneratedHDRDecode": GeneratedHDRDecode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_GeneratedHDRDecode": "Generated HDR Decode (log → linear)",
}
