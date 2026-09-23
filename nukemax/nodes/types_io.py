"""Generic Serialize/Deserialize nodes for every NukeMax custom type.

These let workflow JSON survive across reloads by encoding the
dataclasses to a base64 payload string.
"""
from __future__ import annotations

import json

from ..types import TYPE_NAMES
from ..types import serialize as ser_mod
from ..utils.resilience import resilient


def _pretty(type_name: str) -> str:
    return type_name.title().replace("_", " ")


def _make_serialize(type_name: str):
    pretty = _pretty(type_name)

    @resilient
    class _Serialize:
        CATEGORY = f"NukeMax/IO/{type_name}"
        # Generated per type, because a node with no description shows a blank
        # tooltip in the menu - and these are the nodes someone reaches for
        # when they already do not know how to get a {pretty} across a reload.
        DESCRIPTION = (
            f"Encode a {pretty} into a JSON payload string so it survives a "
            "workflow save and reload. ComfyUI only persists wires between "
            f"nodes that both exist in one run; a {pretty} handed to Serialize "
            "becomes text you can store in the workflow, paste elsewhere, or "
            f"feed back through Deserialize {pretty}. This is a sink node, so "
            "it can end a chain the way Save Image does."
        )
        FUNCTION = "execute"
        RETURN_TYPES = ("STRING",)
        RETURN_NAMES = ("payload",)
        # Sink node — same convention as SaveImage/SaveLatent. Marking
        # Serialize as an output node is what allows it to terminate a
        # workflow chain (otherwise its STRING payload has nowhere to go
        # in vanilla Comfy).
        OUTPUT_NODE = True

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"obj": (type_name,)}}

        def execute(self, obj):
            d = ser_mod.serialize(obj)
            return (json.dumps(d),)

    _Serialize.__name__ = f"Serialize_{type_name}"
    return _Serialize


def _make_deserialize(type_name: str):
    pretty = _pretty(type_name)

    @resilient
    class _Deserialize:
        CATEGORY = f"NukeMax/IO/{type_name}"
        DESCRIPTION = (
            f"Rebuild a {pretty} from the JSON payload that Serialize "
            f"{pretty} produced. Paste the payload in, or wire it from a "
            "stored string, and carry on as if the original node were still "
            "upstream. The payload must have come from the matching Serialize "
            f"node - a payload for a different type will not read as a "
            f"{pretty}."
        )
        FUNCTION = "execute"
        RETURN_TYPES = (type_name,)
        RETURN_NAMES = ("obj",)

        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {"payload": ("STRING", {"multiline": True, "default": ""})}}

        def execute(self, payload):
            d = json.loads(payload)
            return (ser_mod.deserialize(d),)

    _Deserialize.__name__ = f"Deserialize_{type_name}"
    return _Deserialize


NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

for _t in TYPE_NAMES:
    s = _make_serialize(_t)
    d = _make_deserialize(_t)
    skey = f"NukeMax_Serialize_{_t}"
    dkey = f"NukeMax_Deserialize_{_t}"
    NODE_CLASS_MAPPINGS[skey] = s
    NODE_CLASS_MAPPINGS[dkey] = d
    pretty = _pretty(_t)
    NODE_DISPLAY_NAME_MAPPINGS[skey] = f"Serialize {pretty}"
    NODE_DISPLAY_NAME_MAPPINGS[dkey] = f"Deserialize {pretty}"
