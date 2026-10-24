"""Shuffle — Nuke-style channel routing.

Lets you remap any source channel (R,G,B,A,Lum,Const0,Const1) into any
destination channel of the output. Equivalent to Nuke's `Shuffle` /
`ShuffleCopy`. Works on regular IMAGEs and on LATENT tensors.
"""
from __future__ import annotations

import torch

from ...utils.resilience import resilient
from ..._tensor_util import require_image_bhwc
from ..._is_changed_util import hash_args_and_kwargs


# appended (saved values stay valid): channels 5-8 of a multi-channel image (EXR passes)
_CH_OPTS = ("R", "G", "B", "A", "Lum", "0", "1", "Inv_R", "Inv_G", "Inv_B", "Inv_A", "Ch4", "Ch5", "Ch6", "Ch7")


def _pick(image_bhwc: torch.Tensor, code: str) -> torch.Tensor:
    B, H, W, C = image_bhwc.shape
    R = image_bhwc[..., 0]
    G = image_bhwc[..., 1] if C > 1 else R
    Bch = image_bhwc[..., 2] if C > 2 else R
    A = image_bhwc[..., 3] if C > 3 else torch.ones_like(R)
    if code == "R": return R
    if code == "G": return G
    if code == "B": return Bch
    if code == "A": return A
    if code == "Lum":
        return 0.2126 * R + 0.7152 * G + 0.0722 * Bch
    if code == "0": return torch.zeros_like(R)
    if code == "1": return torch.ones_like(R)
    if code == "Inv_R": return 1.0 - R
    if code == "Inv_G": return 1.0 - G
    if code == "Inv_B": return 1.0 - Bch
    if code == "Inv_A": return 1.0 - A
    if code.startswith("Ch") and code[2:].isdigit():
        i = int(code[2:])
        if i >= C:
            raise ValueError(f"Shuffle: channel {code} asked for, but the image has {C} channels (0-{C - 1}).")
        return image_bhwc[..., i]
    return R


@resilient
class ShuffleImage:
    DESCRIPTION = "Remap RGBA channels Nuke-style. Each output channel is picked from any source channel or a constant."
    CATEGORY = "NukeMax/Channel"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "alpha")


    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE", {}),
                "out_R": (_CH_OPTS, {"default": "R"}),
                "out_G": (_CH_OPTS, {"default": "G"}),
                "out_B": (_CH_OPTS, {"default": "B"}),
                "out_A": (_CH_OPTS, {"default": "A"}),
            },
            "optional": {
                # L9.39, appended: the IMAGE output used to be RGB always (alpha only on the MASK output)
                "output": (["rgb", "rgba"], {"default": "rgb",
                           "tooltip": "rgb: three channels (alpha on the MASK output), as before. rgba: the "
                                      "shuffled alpha stays in the image too."}),
            },
        }

    def execute(self, image, out_R, out_G, out_B, out_A, output="rgb"):
        require_image_bhwc(image)
        r = _pick(image, out_R)
        g = _pick(image, out_G)
        b = _pick(image, out_B)
        a = _pick(image, out_A)
        out = torch.stack([r, g, b, a], dim=-1)     # L9.39: channels copied exactly, no clamp
        img = out if output == "rgba" else out[..., :3]
        return (img.contiguous(), a)


@resilient
class ShuffleLatent:
    DESCRIPTION = "Remap latent channels by index. Use this to swap or zero out specific latent dimensions."
    CATEGORY = "NukeMax/Channel"
    FUNCTION = "execute"
    RETURN_TYPES = ("LATENT",)
    RETURN_NAMES = ("latent",)


    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return hash_args_and_kwargs(**kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "latent": ("LATENT", {}),
                "mapping": ("STRING", {
                    "default": "0,1,2,3",
                    "tooltip": "Comma-separated source-channel indices (or 'z' for zero, 'o' for one) for each "
                               "output channel. Works on image (4-D) and video (5-D) latents; the latent's noise "
                               "mask and other entries are kept.",
                }),
            },
        }

    def execute(self, latent, mapping):
        # L9.39: `B, C, H, W = z.shape` crashed on video latents [B,C,T,H,W]; the result kept "samples" only (noise
        # mask and batch index lost); a bad index was silently clamped.
        z = latent["samples"] if isinstance(latent, dict) else latent
        if getattr(z, "is_nested", False):
            raise ValueError("Shuffle Latent: this is a nested (audio + video) latent - split it first.")
        C = int(z.shape[1])
        codes = [s.strip().lower() for s in str(mapping).split(",") if s.strip()]
        if not codes:
            raise ValueError("Shuffle Latent: mapping is empty - list one source channel per output channel.")
        one = list(z.shape)
        one[1] = 1
        out = []
        for code in codes:
            if code == "z":
                out.append(torch.zeros(one, device=z.device, dtype=z.dtype))
            elif code == "o":
                out.append(torch.ones(one, device=z.device, dtype=z.dtype))
            else:
                try:
                    idx = int(code)
                except ValueError:
                    raise ValueError(f"Shuffle Latent: '{code}' is not a channel index, 'z' or 'o'.") from None
                if not 0 <= idx < C:
                    raise ValueError(f"Shuffle Latent: channel {idx} does not exist - this latent has {C} "
                                     f"channels (0-{C - 1}).")
                out.append(z[:, idx:idx + 1])
        new = dict(latent) if isinstance(latent, dict) else {}
        new["samples"] = torch.cat(out, dim=1)
        return (new,)


NODE_CLASS_MAPPINGS = {
    "NukeMax_ShuffleImage": ShuffleImage,
    "NukeMax_ShuffleLatent": ShuffleLatent,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_ShuffleImage": "Shuffle (NukeMax)",
    "NukeMax_ShuffleLatent": "Shuffle Latent (NukeMax)",
}