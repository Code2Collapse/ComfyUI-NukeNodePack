"""EXR I/O nodes (migrated from ComfyUI-CustomNodePacks)."""
# exr_io (LoadEXRMEC / SaveEXRMEC) is owned by ComfyUI-CustomNodePacks.
# Its OpenImageIO backend is the only EXR path that works in this environment
# (cv2 cannot read EXR here), and its SaveEXRMEC is the 6-input superset with
# compression / metadata_json / aov_alpha. The 229-line copy that lived here was
# the shadowed duplicate and is deleted; NukeMax keeps its own Nuke-parity
# EXRSequenceLoad / EXRSequenceSave / EXRChannelRouter, which do not import it.
from .exr_metadata_reader import (
    NODE_CLASS_MAPPINGS as _EXRMETA_C,
    NODE_DISPLAY_NAME_MAPPINGS as _EXRMETA_D,
)
from .exr_channel_router import (
    NODE_CLASS_MAPPINGS as _EXRROUTER_C,
    NODE_DISPLAY_NAME_MAPPINGS as _EXRROUTER_D,
)
from .exr_sequence import (
    NODE_CLASS_MAPPINGS as _EXRSEQ_C,
    NODE_DISPLAY_NAME_MAPPINGS as _EXRSEQ_D,
)
from .multipass import (
    NODE_CLASS_MAPPINGS as _MULTIPASS_C,
    NODE_DISPLAY_NAME_MAPPINGS as _MULTIPASS_D,
)
from .video_sequence import (
    NODE_CLASS_MAPPINGS as _VIDEO_C,
    NODE_DISPLAY_NAME_MAPPINGS as _VIDEO_D,
)

# L9.80 (Rev 3 Part 19.4): the production EXR reader, on the vendored C2C media engine
from .read_exr_pro import (
    NODE_CLASS_MAPPINGS as _READPRO_C,
    NODE_DISPLAY_NAME_MAPPINGS as _READPRO_D,
)

from .exr_inspect_pro import (
    NODE_CLASS_MAPPINGS as _INSPECTPRO_C,
    NODE_DISPLAY_NAME_MAPPINGS as _INSPECTPRO_D,
)

# L9.80 slice 3 (Part 19.7): the safe, versioned, atomic EXR writer
from .write_exr_pro import (
    NODE_CLASS_MAPPINGS as _WRITEPRO_C,
    NODE_DISPLAY_NAME_MAPPINGS as _WRITEPRO_D,
)

NODE_CLASS_MAPPINGS = {**_EXRMETA_C, **_EXRROUTER_C, **_EXRSEQ_C, **_MULTIPASS_C, **_VIDEO_C, **_READPRO_C,
                       **_INSPECTPRO_C, **_WRITEPRO_C}
NODE_DISPLAY_NAME_MAPPINGS = {**_EXRMETA_D, **_EXRROUTER_D, **_EXRSEQ_D, **_MULTIPASS_D, **_VIDEO_D, **_READPRO_D,
                              **_INSPECTPRO_D, **_WRITEPRO_D}

# On-node EXR preview routes. Guarded and idempotent: importing this package
# outside a running ComfyUI (the test harness does exactly that) must not fail,
# so register_exr_preview_routes() returns quietly when `server` is absent.
try:
    from .exr_preview_server import register_exr_preview_routes as _register_exr_preview

    _register_exr_preview()
except Exception as _exc:  # noqa: BLE001
    import logging as _logging

    _logging.getLogger(__name__).info("NukeMax EXR preview routes not registered: %s", _exc)
