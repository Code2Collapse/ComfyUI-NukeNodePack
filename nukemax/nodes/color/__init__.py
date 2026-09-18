"""Color science nodes (migrated from ComfyUI-CustomNodePacks)."""
from .color_science import NODE_CLASS_MAPPINGS as _COLOR_C, NODE_DISPLAY_NAME_MAPPINGS as _COLOR_D
from .levels import NODE_CLASS_MAPPINGS as _LEVELS_C, NODE_DISPLAY_NAME_MAPPINGS as _LEVELS_D

NODE_CLASS_MAPPINGS = {**_COLOR_C, **_LEVELS_C}
NODE_DISPLAY_NAME_MAPPINGS = {**_COLOR_D, **_LEVELS_D}
