# Scene-linear helpers derived from Radiance by FXTD Studios
# (https://github.com/fxtdstudios/radiance; README declares GPL-3.0, no LICENSE
# file shipped). A port, not a clean-room rewrite - see NOTICE.md.
"""Scene-linear HDR helpers — float32 tensors, no silent clamping."""
from __future__ import annotations

import numpy as np
import torch

LUMA_REC709 = (0.2126, 0.7152, 0.0722)
LUMA_AP1 = (0.2722, 0.6741, 0.0537)
LUMA_REC2020 = (0.2627, 0.6780, 0.0593)


def sign_pow_torch(x: torch.Tensor, exp: float) -> torch.Tensor:
    return torch.sign(x) * torch.pow(torch.clamp(torch.abs(x), min=1e-12), exp)


def tensor_srgb_to_linear(tensor: torch.Tensor, gamma: float = 2.2) -> torch.Tensor:
    if abs(gamma - 1.0) < 0.01:
        return tensor.float()
    sign = torch.sign(tensor)
    abs_tensor = torch.abs(tensor)
    if abs(gamma - 2.2) < 0.1:
        linear = torch.where(
            abs_tensor <= 0.04045,
            abs_tensor / 12.92,
            torch.pow((abs_tensor + 0.055) / 1.055, 2.4),
        )
    else:
        linear = torch.pow(abs_tensor, gamma)
    return sign * linear


def tensor_to_numpy_float32(tensor: torch.Tensor) -> np.ndarray:
    tensor = tensor.detach().float()
    return tensor.cpu().numpy().astype(np.float32)


def numpy_to_tensor_float32(array: np.ndarray) -> torch.Tensor:
    if array.ndim == 3:
        array = array[np.newaxis, ...]
    return torch.from_numpy(array.astype(np.float32))


def rec709_luminance(img: np.ndarray) -> np.ndarray:
    return 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]


def rec709_luminance_torch(img: torch.Tensor) -> torch.Tensor:
    return 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]
