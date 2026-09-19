# Derived from Radiance by FXTD Studios (https://github.com/fxtdstudios/radiance).
# Radiance's README declares GPL-3.0; that repository ships no LICENSE file.
#
# This is a PORT, not a clean-room rewrite. Roughly a third of the lines below
# follow the source closely, and the tone-map operators, the 360 projection math
# and the Mertens weights are line-for-line. An earlier header on this file
# claimed "clean-room reimplementation" - that claim was false and is removed.
# Provenance for the whole pack is recorded in NOTICE.md.
#
# What NukeMax changed, and why (a straight copy would have shipped these bugs):
#   * whole-batch processing - the source takes img[0] and silently discards
#     every other frame, which turns a 24-frame sequence into a still
#   * no in-place writes into the caller's IMAGE - the source normalises in
#     place, corrupting the upstream node's cached tensor for every other
#     consumer of that wire
#   * tooltips carrying the VFX rationale, plain-English failures, and an
#     on-node scope / transfer-curve UI that the source does not have
"""HDR / IBL nodes — scene-linear float32, values may exceed 1.0 until tone map."""
from __future__ import annotations

import json
import math

import numpy as np
import torch

from ..._is_changed_util import hash_args_and_kwargs
from ..._tensor_util import require_image_bhwc
from ...utils.hdr_linear import (
    LUMA_AP1,
    LUMA_REC2020,
    LUMA_REC709,
    numpy_to_tensor_float32,
    rec709_luminance,
    rec709_luminance_torch,
    sign_pow_torch,
    tensor_srgb_to_linear,
    tensor_to_numpy_float32,
)
from ...utils.resilience import resilient

_CATEGORY = "NukeMax/HDR"


@resilient
class HDRImageToFloat32:
    DESCRIPTION = "Promote images to float32 scene-linear; optional per-frame normalize (HDR values may exceed 1.0)."

    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, image, normalize=False, source_gamma=1.0, **kw):
        return hash_args_and_kwargs(image=image, normalize=normalize, source_gamma=source_gamma, **kw)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"image": ("IMAGE",)},
            "optional": {
                "normalize": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "tooltip": "Normalize each frame independently when max > 1.0.",
                    },
                ),
                "source_gamma": (
                    "FLOAT",
                    {
                        "default": 1.0,
                        "min": 0.1,
                        "max": 4.0,
                        "step": 0.01,
                        "tooltip": "Decode gamma to linear. 1.0 = already linear.",
                    },
                ),
            },
        }

    def execute(self, image, normalize=False, source_gamma=1.0):
        img = require_image_bhwc(image).float()
        if source_gamma != 1.0:
            img = sign_pow_torch(img, source_gamma)
        if normalize:
            # NEVER write into `img` here. .float() is a no-op on a float32
            # tensor, so it is still the CALLER's tensor - and the caller is an
            # upstream node whose output ComfyUI has cached. The ported version
            # did `img[i] = img[i] / frame_max`, which rewrote that cache for
            # every other node on the same wire. The multiply below allocates,
            # so nothing upstream is touched and no defensive copy is needed.
            # Per frame, not per batch: a sequence normalised as one block
            # inherits the brightest frame's scale and flickers.
            peak = img.flatten(1).max(dim=1).values           # [B]
            scale = torch.where(peak > 1.0, 1.0 / peak, torch.ones_like(peak))
            img = img * scale.view(-1, 1, 1, 1)
        return (img,)


@resilient
class HDRFloat32ColorCorrect:
    DESCRIPTION = "Scene-linear grade with lift/gain/exposure; clamp_output off preserves HDR super-whites."

    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    LUMA_WEIGHTS = {
        "Rec.709 / sRGB": LUMA_REC709,
        "ACEScg / AP1": LUMA_AP1,
        "Rec.2020": LUMA_REC2020,
    }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {"tooltip": "Scene-linear float32 [B,H,W,C]; may exceed 1.0."}),
                "exposure": ("FLOAT", {"default": 0.0, "min": -10.0, "max": 10.0, "step": 0.1,
                                       "tooltip": "Exposure in stops (+1 = 2x brighter)."}),
                "contrast": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 4.0, "step": 0.05,
                                      "tooltip": "Contrast around 18% linear mid-gray."}),
                "brightness": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01}),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.05}),
            },
            "optional": {
                "gamma": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 4.0, "step": 0.01,
                                    "tooltip": "Sign-preserving gamma; 1.0 = no change."}),
                "lift_r": ("FLOAT", {"default": 0.0, "min": -0.5, "max": 0.5, "step": 0.01}),
                "lift_g": ("FLOAT", {"default": 0.0, "min": -0.5, "max": 0.5, "step": 0.01}),
                "lift_b": ("FLOAT", {"default": 0.0, "min": -0.5, "max": 0.5, "step": 0.01}),
                "gain_r": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "gain_g": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "gain_b": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "luma_space": (list(cls.LUMA_WEIGHTS.keys()), {"default": "Rec.709 / sRGB"}),
                "clamp_output": (
                    "BOOLEAN",
                    {"default": False, "tooltip": "Clamp to [0,1]. Off = HDR pass-through."},
                ),
            },
        }

    def execute(
        self,
        image,
        exposure=0.0,
        contrast=1.0,
        brightness=0.0,
        saturation=1.0,
        gamma=1.0,
        lift_r=0.0,
        lift_g=0.0,
        lift_b=0.0,
        gain_r=1.0,
        gain_g=1.0,
        gain_b=1.0,
        luma_space="Rec.709 / sRGB",
        clamp_output=False,
    ):
        img = require_image_bhwc(image).clone().float()
        if img.shape[-1] >= 3:
            if lift_r:
                img[..., 0] += lift_r
            if lift_g:
                img[..., 1] += lift_g
            if lift_b:
                img[..., 2] += lift_b
        if exposure:
            img = img * (2.0 ** exposure)
        if img.shape[-1] >= 3:
            if gain_r != 1.0:
                img[..., 0] *= gain_r
            if gain_g != 1.0:
                img[..., 1] *= gain_g
            if gain_b != 1.0:
                img[..., 2] *= gain_b
        if contrast != 1.0:
            pivot = 0.18
            img = (img - pivot) * contrast + pivot
        if gamma != 1.0:
            img = sign_pow_torch(img, 1.0 / gamma)
        if saturation != 1.0 and img.shape[-1] >= 3:
            w = self.LUMA_WEIGHTS.get(luma_space, LUMA_REC709)
            luma = w[0] * img[..., 0] + w[1] * img[..., 1] + w[2] * img[..., 2]
            luma = luma.unsqueeze(-1)
            img = luma + saturation * (img - luma)
        if brightness:
            img = img + brightness
        if clamp_output:
            img = torch.clamp(img, 0.0, 1.0)
        return (img,)


@resilient
class HDRExpandDynamicRange:
    DESCRIPTION = "Expand SDR to scene-linear HDR by highlight rolloff (output may exceed 1.0)."

    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "source_gamma": ("FLOAT", {"default": 2.2, "min": 1.0, "max": 3.0, "step": 0.1}),
                "highlight_recovery": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1}),
                "black_point": ("FLOAT", {"default": 0.0, "min": -0.1, "max": 0.1, "step": 0.001}),
                "target_stops": ("FLOAT", {"default": 14.0, "min": 8.0, "max": 20.0, "step": 0.5}),
                "highlight_rolloff": ("FLOAT", {"default": 1.5, "min": 1.0, "max": 3.0, "step": 0.1}),
            }
        }

    def execute(
        self,
        image,
        source_gamma=2.2,
        highlight_recovery=1.0,
        black_point=0.0,
        target_stops=14.0,
        highlight_rolloff=1.5,
    ):
        img = require_image_bhwc(image).float()
        linear = tensor_srgb_to_linear(img, source_gamma)
        linear = linear - black_point
        linear = torch.clamp(linear, min=0.0)
        luma = rec709_luminance_torch(linear)
        target_peak = 2.0 ** (target_stops - 8.0)
        threshold = max(0.5, min(0.95, 1.0 - (highlight_rolloff - 1.0) * 0.2))
        if target_peak > 1.0 and highlight_recovery > 0:
            t = threshold
            a = (target_peak - 1.0) / ((1.0 - t) ** 2)
            luma_clamped = torch.clamp(luma, max=1.0)
            expanded_luma = torch.where(
                luma > t,
                t + (luma_clamped - t) + a * torch.pow(luma_clamped - t, 2),
                luma,
            )
            slope_at_1 = 1.0 + 2 * a * (1.0 - t)
            expanded_luma = torch.where(
                luma > 1.0, target_peak + (luma - 1.0) * slope_at_1, expanded_luma
            )
            final_luma = expanded_luma * highlight_recovery + luma * (1.0 - highlight_recovery)
            ratio = (final_luma / (luma + 1e-8)).unsqueeze(-1)
            linear = linear * ratio
        return (linear,)


class _TonemapOps:
    @staticmethod
    def apply_torch(x: torch.Tensor, operator: str, white_point: float) -> torch.Tensor:
        if operator == "reinhard":
            return x / (1.0 + x)
        if operator == "reinhard_extended":
            white_sq = white_point * white_point
            return (x * (1.0 + x / white_sq)) / (1.0 + x)
        if operator == "reinhard_luminance":
            luma = rec709_luminance_torch(x)
            luma = torch.clamp(luma, min=1e-6)
            white_sq = white_point * white_point
            luma_tm = (luma * (1.0 + luma / white_sq)) / (1.0 + luma)
            return x * (luma_tm / luma).unsqueeze(-1)
        if operator == "filmic_aces":
            a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
            x_scaled = x / (white_point + 1e-8)
            return torch.clamp((x_scaled * (a * x_scaled + b)) / (x_scaled * (c * x_scaled + d) + e), 0, 1)
        if operator == "filmic_uncharted2":
            a, b, c, d, e, f = 0.15, 0.50, 0.10, 0.20, 0.02, 0.30

            def curve(v):
                return (v * (a * v + c * b) + d * e) / (v * (a * v + b) + d * f) - e / f

            white_scale = 1.0 / curve(torch.tensor(white_point, device=x.device, dtype=x.dtype))
            return curve(x) * white_scale
        if operator == "agx":
            x = torch.clamp(x, min=1e-10)
            x = torch.log2(x) / 16.0 + 0.5
            x = torch.clamp(x, 0, 1)
            return x * x * (3.0 - 2.0 * x)
        if operator == "linear_clamp":
            return torch.clamp(x / white_point, 0, 1)
        return torch.clamp(x, 0, 1)


@resilient
class HDRToneMap:
    DESCRIPTION = "Map scene-linear HDR to display-referred SDR [0,1] via filmic or Reinhard operators."

    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    OPERATORS = [
        "filmic_aces",
        "filmic_uncharted2",
        "agx",
        "reinhard",
        "reinhard_extended",
        "reinhard_luminance",
        "linear_clamp",
        "exposure_only",
    ]

    PRESETS = {
        "Cinematic Film": {
            "operator": "filmic_aces", "exposure": 0.0, "gamma": 2.2, "white_point": 1.0,
            "contrast": 1.1, "saturation": 0.95, "highlight_compression": 0.8, "shadow_lift": 0.02,
        },
        "HDR Display": {
            "operator": "agx", "exposure": 0.3, "gamma": 2.2, "white_point": 2.0,
            "contrast": 1.0, "saturation": 1.1, "highlight_compression": 0.5, "shadow_lift": 0.0,
        },
        "Web / Social": {
            "operator": "filmic_aces", "exposure": 0.2, "gamma": 2.2, "white_point": 1.0,
            "contrast": 1.15, "saturation": 1.1, "highlight_compression": 0.9, "shadow_lift": 0.01,
        },
    }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"image": ("IMAGE", {"tooltip": "Scene-linear HDR input; may exceed 1.0."})},
            "optional": {
                "preset": (["None (Custom)", *cls.PRESETS.keys()], {"default": "Cinematic Film"}),
                "operator": (cls.OPERATORS, {"default": "filmic_aces"}),
                "exposure": ("FLOAT", {"default": 0.0, "min": -5.0, "max": 5.0, "step": 0.1}),
                "gamma": ("FLOAT", {"default": 2.2, "min": 1.0, "max": 3.0, "step": 0.1}),
                "white_point": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 10.0, "step": 0.1}),
                "contrast": ("FLOAT", {"default": 1.0, "min": 0.5, "max": 2.0, "step": 0.05}),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05}),
                "highlight_compression": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05}),
                "shadow_lift": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 0.2, "step": 0.01}),
            },
        }

    def execute(
        self,
        image,
        preset="Cinematic Film",
        operator="filmic_aces",
        exposure=0.0,
        gamma=2.2,
        white_point=1.0,
        contrast=1.0,
        saturation=1.0,
        highlight_compression=0.5,
        shadow_lift=0.0,
    ):
        if preset != "None (Custom)" and preset in self.PRESETS:
            cfg = self.PRESETS[preset]
            operator = cfg.get("operator", operator)
            exposure = cfg.get("exposure", exposure)
            gamma = cfg.get("gamma", gamma)
            white_point = cfg.get("white_point", white_point)
            contrast = cfg.get("contrast", contrast)
            saturation = cfg.get("saturation", saturation)
            highlight_compression = cfg.get("highlight_compression", highlight_compression)
            shadow_lift = cfg.get("shadow_lift", shadow_lift)

        img = require_image_bhwc(image).float()
        img = img * (2.0 ** exposure)
        if highlight_compression > 0:
            threshold = 1.0 - highlight_compression * 0.5
            compressed = threshold + (img - threshold) / (1.0 + (img - threshold) * highlight_compression * 2)
            img = torch.where(img > threshold, compressed, img)
        if shadow_lift > 0:
            img = img + shadow_lift * (1.0 - img)
        op = operator if operator in self.OPERATORS else "filmic_aces"
        result = _TonemapOps.apply_torch(img, op, white_point)
        if contrast != 1.0:
            result = (result - 0.5) * contrast + 0.5
        if saturation != 1.0 and result.shape[-1] >= 3:
            luma = rec709_luminance_torch(result).unsqueeze(-1)
            result = luma + saturation * (result - luma)
        result = torch.clamp(result, 0, 1)
        result = torch.pow(result, 1.0 / gamma)
        return (result,)


@resilient
class HDRHistogram:
    DESCRIPTION = "Render HDR histogram and stops stats; input may exceed 1.0."

    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("histogram", "stats")

    MODES = ["luminance", "rgb"]

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "mode": (cls.MODES, {"default": "luminance"}),
                "show_clipping": ("BOOLEAN", {"default": True}),
                "stops_range": ("INT", {"default": 14, "min": 8, "max": 24}),
            }
        }

    def execute(self, image, mode="luminance", show_clipping=True, stops_range=14):
        try:
            from PIL import Image, ImageDraw
        except ImportError as exc:
            raise RuntimeError("Pillow is required for HDR Histogram. Install with: pip install Pillow") from exc

        # A scope that silently reads only frame 0 is worse than no scope:
        # it reports a sequence is in range when a LATER frame is blown.
        # Measure the whole batch.
        img_b = tensor_to_numpy_float32(require_image_bhwc(image))
        frame_count = int(img_b.shape[0])
        img = np.nan_to_num(img_b, nan=0.0, posinf=65504.0, neginf=-65504.0)
        luma = rec709_luminance(img) if img.shape[-1] >= 3 else img[..., 0]
        min_val = float(np.min(img))
        max_val = float(np.max(img))
        mean_val = float(np.mean(img))
        eps = 1e-10
        positive = img[img > 0]
        min_positive = float(positive.min()) if positive.size else eps
        dynamic_range = math.log2(max(max_val, eps) / max(min_positive, eps))
        clip_low = float(np.sum(img <= 0) / img.size * 100)
        clip_high = float(np.sum(img >= 1) / img.size * 100)
        scope = "1 frame" if frame_count == 1 else f"{frame_count} frames"
        stats = (
            f"Min: {min_val:.6f}  Max: {max_val:.6f}  Mean: {mean_val:.6f}\n"
            f"Dynamic range: {dynamic_range:.1f} stops\n"
            f"Clipped low: {clip_low:.2f}%  Clipped high: {clip_high:.2f}%\n"
            f"Measured over: {scope}"
        )

        hist_w, hist_h = 512, 320
        hist_img = Image.new("RGB", (hist_w, hist_h), (26, 26, 46))
        draw = ImageDraw.Draw(hist_img)
        margin = 40
        graph_w = hist_w - margin * 2
        graph_h = hist_h - margin * 2
        num_bins = 128
        bin_width = graph_w / num_bins
        channel = luma.flatten() if mode == "luminance" else img[..., 0].flatten()
        hist_vals, _ = np.histogram(channel, bins=num_bins, range=(0, max(1.0, max_val)))
        max_count = max(int(hist_vals.max()), 1)
        for i, count in enumerate(hist_vals):
            bar_h = int((count / max_count) * graph_h * 0.9)
            x1 = margin + int(i * bin_width)
            x2 = margin + int((i + 1) * bin_width)
            draw.rectangle([x1, margin + graph_h - bar_h, x2, margin + graph_h], fill=(233, 69, 96))
        if show_clipping and max_val > 0:
            white_x = margin + int(graph_w * min(1.0 / max_val, 1.0))
            draw.line([(white_x, margin), (white_x, margin + graph_h)], fill=(255, 255, 0), width=2)
        draw.text((margin, 8), f"HDR histogram ({stops_range} stops DR, {scope})",
                  fill=(220, 220, 220))
        hist_np = np.array(hist_img).astype(np.float32) / 255.0

        # Socket values never reach the browser - only the `ui` payload
        # does. The rendered PNG above stays for workflows that want a
        # scope in the graph; this sends the BIN COUNTS instead, so the
        # on-node scope (web/widgets/hdr/hdr_scope.js) can draw a crisp,
        # theme-aware plot at any zoom rather than blitting a fixed bitmap.
        scope = {
            "bins": [int(v) for v in hist_vals],
            "range": [0.0, float(max(1.0, max_val))],
            "min": min_val,
            "max": max_val,
            "mean": mean_val,
            "stops": round(dynamic_range, 2),
            "clip_low": round(clip_low, 3),
            "clip_high": round(clip_high, 3),
            "frames": frame_count,
            "mode": mode,
        }
        return {
            "ui": {"text": [stats], "nukemax_hdr_scope": [json.dumps(scope)]},
            "result": (numpy_to_tensor_float32(hist_np), stats),
        }


def _laplacian_pyramid_blend(low_exp: np.ndarray, high_exp: np.ndarray, levels: int = 5) -> tuple[np.ndarray, np.ndarray]:
    try:
        from scipy.ndimage import gaussian_filter
    except ImportError as exc:
        raise RuntimeError(
            "scipy is required for Laplacian Pyramid blending. Install with: pip install scipy"
        ) from exc

    def build_gaussian_pyramid(img, n_levels):
        pyramid = [img]
        for _ in range(n_levels - 1):
            blurred = gaussian_filter(pyramid[-1], sigma=2)
            pyramid.append(blurred[::2, ::2])
        return pyramid

    def build_laplacian_pyramid(gaussian_pyr):
        laplacian = []
        for i in range(len(gaussian_pyr) - 1):
            upsampled = np.repeat(np.repeat(gaussian_pyr[i + 1], 2, axis=0), 2, axis=1)
            h, w = gaussian_pyr[i].shape[:2]
            laplacian.append(gaussian_pyr[i] - upsampled[:h, :w])
        laplacian.append(gaussian_pyr[-1])
        return laplacian

    g_low = build_gaussian_pyramid(low_exp, levels)
    g_high = build_gaussian_pyramid(high_exp, levels)
    l_low = build_laplacian_pyramid(g_low)
    l_high = build_laplacian_pyramid(g_high)
    lum = rec709_luminance(low_exp)
    mask = (lum > 0.5).astype(np.float32)
    mask_pyr = build_gaussian_pyramid(mask[..., np.newaxis].repeat(3, axis=-1), levels)
    blended = []
    for l_l, l_h, m in zip(l_low, l_high, mask_pyr):
        blended.append(l_l * m + l_h * (1.0 - m))
    result = blended[-1]
    for i in range(len(blended) - 2, -1, -1):
        upsampled = np.repeat(np.repeat(result, 2, axis=0), 2, axis=1)
        h, w = blended[i].shape[:2]
        result = upsampled[:h, :w] + blended[i]
    return result, mask[..., np.newaxis].repeat(3, axis=-1)


@resilient
class HDRExposureBlend:
    DESCRIPTION = "Fuse exposure brackets into scene-linear HDR (output may exceed 1.0)."

    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING")
    RETURN_NAMES = ("blended_hdr", "blend_mask", "blend_info")

    METHODS = [
        "Mertens Fusion",
        "Luminance Weighted",
        "Shadow/Highlight Mask",
        "Exposure Weighted",
        "Laplacian Pyramid",
    ]

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "low_exposure": ("IMAGE", {"tooltip": "Darker bracket — preserves highlights."}),
                "high_exposure": ("IMAGE", {"tooltip": "Brighter bracket — preserves shadows."}),
                "blend_method": (cls.METHODS, {"default": "Mertens Fusion"}),
            },
            "optional": {
                "mid_exposure": ("IMAGE",),
                "shadow_weight": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1}),
                "highlight_weight": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.1}),
                "transition_smoothness": ("FLOAT", {"default": 0.3, "min": 0.05, "max": 1.0, "step": 0.05}),
                "exposure_offset_low": ("FLOAT", {"default": -2.0, "min": -6.0, "max": 0.0, "step": 0.5}),
                "exposure_offset_high": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 6.0, "step": 0.5}),
                "exposure_offset_mid": ("FLOAT", {"default": 0.0, "min": -6.0, "max": 6.0, "step": 0.5}),
            },
        }

    def _mertens_weights(self, img: np.ndarray) -> np.ndarray:
        gray = rec709_luminance(img)
        lap = np.abs(np.gradient(np.gradient(gray, axis=0), axis=0) + np.gradient(np.gradient(gray, axis=1), axis=1))
        mean_rgb = np.mean(img, axis=-1)
        saturation = np.sqrt(np.mean((img - mean_rgb[..., np.newaxis]) ** 2, axis=-1))
        exposedness = np.exp(-0.5 * ((img - 0.5) / 0.2) ** 2)
        exposedness = np.prod(exposedness, axis=-1)
        return lap * saturation * exposedness + 1e-10

    def execute(
        self,
        low_exposure,
        high_exposure,
        blend_method="Mertens Fusion",
        mid_exposure=None,
        shadow_weight=1.0,
        highlight_weight=1.0,
        transition_smoothness=0.3,
        exposure_offset_low=-2.0,
        exposure_offset_high=2.0,
        exposure_offset_mid=0.0,
    ):
        low_b = tensor_to_numpy_float32(require_image_bhwc(low_exposure))
        high_b = tensor_to_numpy_float32(require_image_bhwc(high_exposure))
        mid_b = None
        if mid_exposure is not None:
            mid_b = tensor_to_numpy_float32(require_image_bhwc(mid_exposure))

        # A bracket set is usually a SEQUENCE. The ported code took [0] and
        # dropped the rest silently. Frame counts may legitimately differ - a
        # single still held against a moving plate is a real setup - so the
        # shorter side holds on its last frame rather than erroring.
        batch = max(low_b.shape[0], high_b.shape[0])
        if mid_b is not None:
            batch = max(batch, mid_b.shape[0])

        def _frame(arr, i):
            return arr[min(i, arr.shape[0] - 1)]

        frames, masks = [], []
        for _i in range(batch):
            low_np = _frame(low_b, _i) * (2.0 ** (-exposure_offset_low))
            high_np = _frame(high_b, _i) * (2.0 ** (-exposure_offset_high))
            mid_frame = None if mid_b is None else _frame(mid_b, _i)
            res, msk = self._blend_one(
                low_np, high_np, mid_frame, blend_method, shadow_weight,
                highlight_weight, transition_smoothness, exposure_offset_mid,
                exposure_offset_low, exposure_offset_high,
            )
            frames.append(res)
            masks.append(msk)

        result = np.stack(frames, axis=0)
        mask = np.stack(masks, axis=0)
        dr = math.log2(
            max(float(result.max()), 1e-10)
            / max(float(result[result > 0].min()) if np.any(result > 0) else 1e-10, 1e-10)
        )
        plural = "" if batch == 1 else f" | {batch} frames"
        info = (f"Method: {blend_method}{plural} | DR: {dr:.1f} stops | "
                f"Range: [{result.min():.3f}, {result.max():.3f}]")
        return (torch.from_numpy(result.astype(np.float32)),
                torch.from_numpy(mask.astype(np.float32)), info)

    def _blend_one(
        self,
        low_np,
        high_np,
        mid_np,
        blend_method,
        shadow_weight,
        highlight_weight,
        transition_smoothness,
        exposure_offset_mid,
        exposure_offset_low,
        exposure_offset_high,
    ):
        """Fuse ONE bracket set. Inputs are [H,W,C] and already exposure-aligned."""
        mid_exposure = mid_np
        if blend_method == "Mertens Fusion":
            images = [low_np, high_np]
            if mid_exposure is not None:
                images.insert(1, mid_exposure * (2.0 ** (-exposure_offset_mid)))
            weights = [self._mertens_weights(im) for im in images]
            wsum = np.maximum(sum(weights), 1e-10)
            result = sum(im * (w / wsum)[..., np.newaxis] for im, w in zip(images, weights))
            mask = np.ones_like(result) * 0.5
        elif blend_method == "Luminance Weighted":
            lum = rec709_luminance(low_np)
            x = (lum - 0.5) / transition_smoothness
            low_w = 1.0 / (1.0 + np.exp(-x))
            result = low_np * low_w[..., np.newaxis] + high_np * (1.0 - low_w)[..., np.newaxis]
            mask = low_w[..., np.newaxis].repeat(3, axis=-1)
        elif blend_method == "Shadow/Highlight Mask":
            lum = rec709_luminance(low_np)
            shadow_mask = np.clip((0.25 - lum) / transition_smoothness + 0.5, 0, 1)
            highlight_mask = np.clip((lum - 0.75) / transition_smoothness + 0.5, 0, 1)
            midtone_mask = np.maximum(1.0 - shadow_mask - highlight_mask, 0)
            result = (
                high_np * shadow_mask[..., np.newaxis] * shadow_weight
                + low_np * highlight_mask[..., np.newaxis] * highlight_weight
                + (low_np + high_np) * 0.5 * midtone_mask[..., np.newaxis]
            )
            total = shadow_mask * shadow_weight + highlight_mask * highlight_weight + midtone_mask
            result = result / np.maximum(total[..., np.newaxis], 1e-10)
            mask = np.stack([shadow_mask, midtone_mask, highlight_mask], axis=-1)
        elif blend_method == "Exposure Weighted":
            total_range = abs(exposure_offset_high - exposure_offset_low) or 1.0
            low_w = abs(exposure_offset_high) / total_range
            result = low_np * low_w + high_np * (1.0 - low_w)
            mask = np.ones_like(result) * low_w
        elif blend_method == "Laplacian Pyramid":
            result, mask = _laplacian_pyramid_blend(low_np, high_np)
        else:
            result = (low_np + high_np) * 0.5
            mask = np.ones_like(result) * 0.5

        result = np.maximum(result, 0.0)
        return result, mask.astype(np.float32)


@resilient
class HDRShadowHighlightRecovery:
    DESCRIPTION = "Lift shadows and compress super-whites in scene-linear HDR without hard clamp."

    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "shadow_amount": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 2.0, "step": 0.05}),
                "highlight_amount": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 2.0, "step": 0.05}),
            },
            "optional": {
                "shadow_tone": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 0.5, "step": 0.01}),
                "highlight_tone": ("FLOAT", {"default": 0.75, "min": 0.5, "max": 1.0, "step": 0.01}),
                "color_correction": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.1}),
                "local_contrast": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.1}),
            },
        }

    def execute(
        self,
        image,
        shadow_amount=0.5,
        highlight_amount=0.5,
        shadow_tone=0.25,
        highlight_tone=0.75,
        color_correction=0.5,
        local_contrast=0.0,
    ):
        # [B,H,W,C] throughout. require_image_bhwc guarantees 4-D, so the
        # `img = img[0]` this was ported with fired on EVERY call: a 24-frame
        # sequence came back as a single still, with no message.
        img = tensor_to_numpy_float32(require_image_bhwc(image))
        lum = np.maximum(rec709_luminance(img), 1e-10)
        shadow_mask = np.exp(-3.0 * lum / (shadow_tone + 1e-6))
        shadow_boost = 1.0 + shadow_amount * shadow_mask
        h_pos = (lum - highlight_tone) / (1.0 - highlight_tone + 1e-6)
        highlight_mask = np.maximum(0.0, h_pos)
        highlight_reduce = 1.0 / (1.0 + highlight_amount * highlight_mask * 0.5)
        result = img * shadow_boost[..., np.newaxis] * highlight_reduce[..., np.newaxis]
        if color_correction > 0:
            new_lum = np.maximum(rec709_luminance(result), 1e-10)
            sat_factor = 1.0 - shadow_mask * color_correction * 0.3
            result = new_lum[..., np.newaxis] + sat_factor[..., np.newaxis] * (result - new_lum[..., np.newaxis])
        if local_contrast != 0:
            try:
                from scipy.ndimage import gaussian_filter
            except ImportError as exc:
                raise RuntimeError(
                    "scipy is required when local_contrast is non-zero. Install with: pip install scipy"
                ) from exc
            # sigma 0 on the batch axis: blurring across frames would smear
            # one shot's luminance into the next one's local contrast.
            local_lum = gaussian_filter(lum, sigma=(0, 50, 50))
            detail = lum / (local_lum + 1e-10)
            result = result * (1.0 + local_contrast * (detail - 1.0))[..., np.newaxis]
        return (numpy_to_tensor_float32(result),)


@resilient
class HDRHighlightSynthesis:
    DESCRIPTION = "Expand clipped highlights with procedural grain (scene-linear output may exceed 1.0)."

    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "threshold": ("FLOAT", {"default": 0.95, "min": 0.5, "max": 1.0, "step": 0.01}),
                "expansion": ("FLOAT", {"default": 1.5, "min": 1.0, "max": 4.0, "step": 0.1}),
                "detail_amount": ("FLOAT", {"default": 0.2, "min": 0.0, "max": 1.0, "step": 0.05}),
                "detail_scale": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 5.0, "step": 0.1}),
                "blend_mode": (["Add", "Screen"], {"default": "Add"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
            }
        }

    def execute(
        self,
        image,
        threshold=0.95,
        expansion=1.5,
        detail_amount=0.2,
        detail_scale=1.0,
        blend_mode="Add",
        seed=0,
    ):
        img_np = tensor_to_numpy_float32(require_image_bhwc(image))
        out = np.zeros_like(img_np)
        for b in range(img_np.shape[0]):
            frame = img_np[b]
            h, w, c = frame.shape
            rng = np.random.default_rng(seed + b)
            luma = rec709_luminance(frame) if c >= 3 else frame[..., 0]
            mask = np.clip((luma - threshold) / (1.0 - threshold + 1e-6), 0, 1)
            mask = mask * mask * (3 - 2 * mask)
            if mask.max() < 1e-4:
                out[b] = frame
                continue
            expansion_map = np.maximum(1.0, 1.0 + (luma - threshold) * (expansion - 1.0) * 2.0)
            expanded = frame * (1.0 - mask[..., np.newaxis]) + frame * expansion_map[..., np.newaxis] * mask[..., np.newaxis]
            noise = rng.normal(0, 0.5, (h, w)).astype(np.float32)
            if detail_scale != 1.0:
                h_small = max(1, int(h / detail_scale))
                w_small = max(1, int(w / detail_scale))
                small = rng.normal(0, 0.5, (h_small, w_small)).astype(np.float32)
                ys = np.linspace(0, h_small - 1, h).astype(int)
                xs = np.linspace(0, w_small - 1, w).astype(int)
                noise = small[ys][:, xs]
            noise_layer = noise * detail_amount * mask
            final = expanded.copy()
            if blend_mode == "Screen":
                for ch in range(c):
                    final[..., ch] = 1.0 - (1.0 - final[..., ch]) * (1.0 - np.clip(noise_layer, 0, 1))
            else:
                for ch in range(c):
                    final[..., ch] += noise_layer
            out[b] = np.maximum(0.0, final)
        return (numpy_to_tensor_float32(out),)


@resilient
class HDR360Generate:
    DESCRIPTION = "Project a source image into an equirectangular HDRI panorama (scene-linear, may exceed 1.0)."

    CATEGORY = _CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("panorama", "projection_map")

    PROJECTIONS = ["Equirectangular", "Cube_Map", "Mirror_Ball", "Angular_Map"]
    INTERPOLATIONS = ["Nearest", "Bilinear", "Bicubic", "Lanczos"]
    FILLS = ["Mirror", "Repeat", "Black", "Edge"]

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_image": ("IMAGE",),
                "projection_type": (cls.PROJECTIONS, {"default": "Equirectangular"}),
                "output_width": ("INT", {"default": 256, "min": 64, "max": 8192, "step": 64}),
                "output_height": ("INT", {"default": 128, "min": 32, "max": 4096, "step": 64}),
            },
            "optional": {
                "horizontal_fov": ("FLOAT", {"default": 360.0, "min": 30.0, "max": 360.0, "step": 1.0}),
                "vertical_fov": ("FLOAT", {"default": 180.0, "min": 15.0, "max": 180.0, "step": 1.0}),
                "rotation_y": ("FLOAT", {"default": 0.0, "min": -180.0, "max": 180.0, "step": 1.0}),
                "interpolation": (cls.INTERPOLATIONS, {"default": "Bilinear"}),
                "fill_mode": (cls.FILLS, {"default": "Mirror"}),
                "exposure_adjust": ("FLOAT", {"default": 0.0, "min": -5.0, "max": 5.0, "step": 0.1}),
            },
        }

    def _equirect_xyz(self, width: int, height: int) -> np.ndarray:
        u = np.linspace(0, 1, width)
        v = np.linspace(0, 1, height)
        u, v = np.meshgrid(u, v)
        theta = (u - 0.5) * 2 * np.pi
        phi = (0.5 - v) * np.pi
        x = np.cos(phi) * np.sin(theta)
        y = np.sin(phi)
        z = np.cos(phi) * np.cos(theta)
        return np.stack([x, y, z], axis=-1)

    def _xyz_to_uv(self, xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x, y, z = xyz[..., 0], xyz[..., 1], xyz[..., 2]
        theta = np.arctan2(x, z)
        phi = np.arcsin(np.clip(y, -1, 1))
        return theta / (2 * np.pi) + 0.5, 0.5 - phi / np.pi

    def _fill_uv(self, u, v, fill_mode):
        if fill_mode == "Mirror":
            u = np.abs(np.mod(u, 2.0) - 1.0)
            v = np.abs(np.mod(v, 2.0) - 1.0)
            mask = np.ones_like(u)
        elif fill_mode == "Repeat":
            u = np.mod(u, 1)
            v = np.mod(v, 1)
            mask = np.ones_like(u)
        elif fill_mode == "Edge":
            u = np.clip(u, 0, 1)
            v = np.clip(v, 0, 1)
            mask = np.ones_like(u)
        else:
            mask = ((u >= 0) & (u <= 1) & (v >= 0) & (v <= 1)).astype(np.float32)
            u = np.clip(u, 0, 1)
            v = np.clip(v, 0, 1)
        return u, v, mask

    def execute(
        self,
        source_image,
        projection_type="Equirectangular",
        output_width=256,
        output_height=128,
        horizontal_fov=360.0,
        vertical_fov=180.0,
        rotation_y=0.0,
        interpolation="Bilinear",
        fill_mode="Mirror",
        exposure_adjust=0.0,
    ):
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("opencv-python is required for HDR 360 Generate. Install with: pip install opencv-python") from exc

        # A latlong is often built from a PLATE, not a still. The ported code
        # took frame 0 and dropped the rest without a word.
        img_b = tensor_to_numpy_float32(require_image_bhwc(source_image))
        img = img_b[0]
        xyz = self._equirect_xyz(output_width, output_height)
        if rotation_y:
            ry = np.radians(rotation_y)
            c, s = np.cos(ry), np.sin(ry)
            rot = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float32)
            xyz = xyz @ rot.T
        if projection_type == "Equirectangular":
            u, v = self._xyz_to_uv(xyz)
            h_scale = horizontal_fov / 360.0
            v_scale = vertical_fov / 180.0
            u = (u - 0.5) / h_scale + 0.5
            v = (v - 0.5) / v_scale + 0.5
        elif projection_type == "Cube_Map":
            x, y, z = xyz[..., 0], xyz[..., 1], xyz[..., 2]
            abs_x, abs_y, abs_z = np.abs(x), np.abs(y), np.abs(z)
            face_x_pos = (x >= 0) & (abs_x >= abs_y) & (abs_x >= abs_z)
            face_x_neg = (x < 0) & (abs_x >= abs_y) & (abs_x >= abs_z)
            face_y_pos = (y >= 0) & (abs_y > abs_x) & (abs_y >= abs_z)
            face_y_neg = (y < 0) & (abs_y > abs_x) & (abs_y >= abs_z)
            face_z_pos = (z >= 0) & (abs_z > abs_x) & (abs_z > abs_y)
            u = np.where(
                face_x_pos,
                0.5 + (-z) / (2.0 * abs_x + 1e-8),
                np.where(
                    face_x_neg,
                    0.5 + z / (2.0 * abs_x + 1e-8),
                    np.where(
                        face_y_pos,
                        0.5 + x / (2.0 * abs_y + 1e-8),
                        np.where(
                            face_y_neg,
                            0.5 + x / (2.0 * abs_y + 1e-8),
                            np.where(
                                face_z_pos,
                                0.5 + x / (2.0 * abs_z + 1e-8),
                                0.5 + (-x) / (2.0 * abs_z + 1e-8),
                            ),
                        ),
                    ),
                ),
            )
            v = np.where(
                face_x_pos,
                0.5 + y / (2.0 * abs_x + 1e-8),
                np.where(
                    face_x_neg,
                    0.5 + y / (2.0 * abs_x + 1e-8),
                    np.where(
                        face_y_pos,
                        0.5 + (-z) / (2.0 * abs_y + 1e-8),
                        np.where(
                            face_y_neg,
                            0.5 + z / (2.0 * abs_y + 1e-8),
                            np.where(
                                face_z_pos,
                                0.5 + y / (2.0 * abs_z + 1e-8),
                                0.5 + y / (2.0 * abs_z + 1e-8),
                            ),
                        ),
                    ),
                ),
            )
        elif projection_type == "Mirror_Ball":
            x, y, z = xyz[..., 0], xyz[..., 1], xyz[..., 2]
            m = 2 * np.sqrt(x ** 2 + y ** 2 + (z + 1) ** 2 + 1e-8)
            u, v = x / m + 0.5, y / m + 0.5
        elif projection_type == "Angular_Map":
            x, y, z = xyz[..., 0], xyz[..., 1], xyz[..., 2]
            r = np.arccos(np.clip(z, -1, 1)) / np.pi
            phi = np.arctan2(y, x)
            u, v = r * np.cos(phi) * 0.5 + 0.5, r * np.sin(phi) * 0.5 + 0.5
        else:
            raise ValueError(f"Unknown projection_type: {projection_type}")
        u, v, mask = self._fill_uv(u, v, fill_mode)
        h, w = img.shape[:2]
        map_x = (u * (w - 1)).astype(np.float32)
        map_y = (v * (h - 1)).astype(np.float32)
        interp = {
            "Nearest": cv2.INTER_NEAREST,
            "Bilinear": cv2.INTER_LINEAR,
            "Bicubic": cv2.INTER_CUBIC,
            "Lanczos": cv2.INTER_LANCZOS4,
        }[interpolation]
        border = cv2.BORDER_CONSTANT if fill_mode == "Black" else cv2.BORDER_REFLECT
        # The uv map depends only on the projection, so it is built once and
        # every frame is remapped through it.
        gain = (2.0 ** exposure_adjust) if exposure_adjust else 1.0
        pans = []
        for _i in range(img_b.shape[0]):
            pan = cv2.remap(img_b[_i], map_x, map_y, interp,
                            borderMode=border, borderValue=0)
            if fill_mode == "Black":
                pan = pan * mask[..., np.newaxis]
            if gain != 1.0:
                pan = pan * gain
            pans.append(pan.astype(np.float32))
        panorama = np.stack(pans, axis=0)
        uv_map = np.stack([u, v, mask], axis=-1).astype(np.float32)
        uv_t = torch.from_numpy(uv_map).unsqueeze(0).repeat(panorama.shape[0], 1, 1, 1)
        return (torch.from_numpy(panorama), uv_t)
