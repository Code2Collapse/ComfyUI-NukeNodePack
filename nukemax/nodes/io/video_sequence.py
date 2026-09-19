# PORTED FROM: ComfyUI-ACES-IO (third_party/ComfyUI-ACES-IO) by Bishoy Samaan
# Licence: MIT — direct copy authorised by owner; attribution retained.
"""Load video files (MOV/MP4/MXF/…) as IMAGE batches via PyAV."""
from __future__ import annotations

import os

import numpy as np
import torch

from ...utils.resilience import resilient
from ..._tensor_util import require_image_bhwc
from ..._is_changed_util import hash_args_and_kwargs
from ...utils.ocio_convert import apply_colorspace_convert


@resilient
class NukeMax_VideoSequenceLoad:
    DESCRIPTION = "Load frames from a video file (ProRes, H.264, DNxHD, etc.) as an IMAGE batch via PyAV."
    CATEGORY = "NukeMax/IO"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "INT", "INT", "INT")
    RETURN_NAMES = ("image", "frame_count", "first_frame", "last_frame")

    @classmethod
    def IS_CHANGED(cls, file_path="", **kwargs):
        path = os.path.expanduser((file_path or "").strip())
        if not path or not os.path.isfile(path):
            return ("missing", path)
        st = os.stat(path)
        return hash_args_and_kwargs(path=path, mtime_ns=st.st_mtime_ns, size=st.st_size, **kwargs)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "file_path": ("STRING", {"default": "", "multiline": False}),
                "frame_mode": (("all", "range"), {"default": "all"}),
            },
            "optional": {
                "first_frame": ("INT", {"default": 0, "min": 0, "max": 999_999}),
                "last_frame": ("INT", {"default": 0, "min": 0, "max": 999_999}),
                "ocio_input_colorspace": ("STRING", {"default": "",
                    "tooltip": "File colorspace; empty = no OCIO conversion on load."}),
                "ocio_output_colorspace": ("STRING", {"default": "",
                    "tooltip": "Working colorspace after load; empty = no conversion."}),
            },
        }

    def execute(
        self,
        file_path,
        frame_mode,
        first_frame=0,
        last_frame=0,
        ocio_input_colorspace="",
        ocio_output_colorspace="",
    ):
        try:
            import av
        except ImportError as exc:
            raise ImportError(
                "VideoSequenceLoad needs PyAV to decode video. Install with: pip install av"
            ) from exc

        path = os.path.expanduser((file_path or "").strip())
        if not path:
            raise ValueError("VideoSequenceLoad: file_path is empty.")
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Video file not found: {path!r}")

        container = av.open(path)
        stream = container.streams.video[0]
        frames_np = []
        for frame in container.decode(stream):
            arr = frame.to_ndarray(format="rgb24").astype(np.float32) / 255.0
            frames_np.append(arr)
        container.close()

        if not frames_np:
            raise RuntimeError(f"VideoSequenceLoad: no frames decoded from {path!r}")

        if frame_mode == "range":
            frames_np = frames_np[int(first_frame): int(last_frame) + 1]
            first_idx = int(first_frame)
            last_idx = int(last_frame)
        else:
            first_idx = 0
            last_idx = len(frames_np) - 1

        tensor = torch.from_numpy(np.stack(frames_np, axis=0))
        tensor = apply_colorspace_convert(tensor, ocio_input_colorspace, ocio_output_colorspace)
        return (tensor, tensor.shape[0], first_idx, last_idx)


NODE_CLASS_MAPPINGS = {
    "NukeMax_VideoSequenceLoad": NukeMax_VideoSequenceLoad,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "NukeMax_VideoSequenceLoad": "Video Sequence Load (NukeMax)",
}
