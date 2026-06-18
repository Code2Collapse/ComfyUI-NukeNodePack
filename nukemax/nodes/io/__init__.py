"""EXR I/O nodes (migrated from ComfyUI-CustomNodePacks)."""
from .exr_io import (
    NODE_CLASS_MAPPINGS as _EXRIO_C,
    NODE_DISPLAY_NAME_MAPPINGS as _EXRIO_D,
)
from .exr_metadata_reader import (
    NODE_CLASS_MAPPINGS as _EXRMETA_C,
    NODE_DISPLAY_NAME_MAPPINGS as _EXRMETA_D,
)
from .exr_channel_router import (
    NODE_CLASS_MAPPINGS as _EXRROUTER_C,
    NODE_DISPLAY_NAME_MAPPINGS as _EXRROUTER_D,
)

NODE_CLASS_MAPPINGS = {**_EXRIO_C, **_EXRMETA_C, **_EXRROUTER_C}
NODE_DISPLAY_NAME_MAPPINGS = {**_EXRIO_D, **_EXRMETA_D, **_EXRROUTER_D}
