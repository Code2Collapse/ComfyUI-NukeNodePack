"""NukeMax OCIO Config Manager - one resolver, cache and inventory for every NukeMax OCIO node (owner Rev 3 Part 19.10;
ledger L9.80 slice 5a).

- Sources: the built-in ACES configs (OCIO 2.2+), $OCIO, the configs in models/ocio_configs/, or a config file path.
- ONE cache, keyed on (path, mtime, size): a config edited on disk reloads by itself on the next run; ``reload()``
  empties it (the Reload button). Both OCIO node modules load through it.
- The inventory a show needs: active config and its source, OCIO version, working space (role scene_linear), roles,
  colour spaces (family, encoding, data or not), displays and their views, looks, the file formats this OCIO reads,
  and MISSING LUTS - every colour space's and look's transforms are walked (groups included) and each file transform's
  source resolved through the config's own context and search path.
Original code, GPL-3.0-only.
"""
from __future__ import annotations

import json
import os
import threading

TYPE = "NUKEMAX_OCIO_CONFIG"
_CACHE: dict = {}
_LOCK = threading.Lock()


def _ocio():
    try:
        import PyOpenColorIO as OCIO  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError("OCIO needs PyOpenColorIO. Install it: pip install opencolorio") from exc
    return OCIO


def default_source() -> str:
    """What an empty choice means: $OCIO when it is set and exists, else the built-in ACES studio config."""
    env = os.environ.get("OCIO", "").strip()
    return env if env and os.path.isfile(env) else "ocio://studio-config-latest"


def source_kind(path: str) -> str:
    if path.startswith("ocio://"):
        return "built-in"
    if os.environ.get("OCIO") and os.path.realpath(path) == os.path.realpath(os.environ["OCIO"]):
        return "$OCIO"
    return "file"


def load(path: str):
    """The config at ``path`` (an ocio:// URI or a file), cached until the file changes."""
    OCIO = _ocio()
    if not path:
        path = default_source()
    if path.startswith("ocio://"):
        key = ("builtin", path)
    else:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"OCIO config {path!r} does not exist.")
        st = os.stat(path)
        key = ("file", os.path.realpath(path), st.st_mtime_ns, st.st_size)
    with _LOCK:
        cfg = _CACHE.get(key)
    if cfg is not None:
        return cfg
    try:
        cfg = OCIO.Config.CreateFromBuiltinConfig(path) if path.startswith("ocio://") \
            else OCIO.Config.CreateFromFile(path)
    except Exception as exc:  # noqa: BLE001 - OCIO's own exception types vary by build
        raise ValueError(f"OCIO cannot load the config {path!r}: {exc}") from exc
    with _LOCK:
        if len(_CACHE) > 16:
            _CACHE.clear()
        _CACHE[key] = cfg
    return cfg


def reload() -> int:
    """Forget every cached config (both OCIO modules load through this cache). Returns how many."""
    with _LOCK:
        n = len(_CACHE)
        _CACHE.clear()
    return n


def fingerprint(path: str) -> str:
    if not path or path.startswith("ocio://"):
        return path or default_source()
    try:
        st = os.stat(path)
        return f"{os.path.realpath(path)}|{st.st_mtime_ns}|{st.st_size}"
    except OSError:
        return f"{path}|missing"


def _enum_name(v) -> str:
    s = str(v)
    return s.split(".")[-1] if "." in s else s


def _file_transforms(t, out: list) -> None:
    """Every FileTransform inside ``t`` (groups walked)."""
    if t is None:
        return
    name = type(t).__name__
    if name == "FileTransform":
        out.append(t)
    elif name == "GroupTransform":
        for child in t:                                   # PyOpenColorIO 2.x: a group iterates its transforms
            _file_transforms(child, out)


def missing_luts(cfg) -> list[dict]:
    OCIO = _ocio()
    ctx = cfg.getCurrentContext()
    found: list[dict] = []
    seen: set = set()

    def check(owner: str, t) -> None:
        fts: list = []
        _file_transforms(t, fts)
        for ft in fts:
            src = ft.getSrc()
            if (owner, src) in seen:
                continue
            seen.add((owner, src))
            try:
                ctx.resolveFileLocation(src)
            except Exception as exc:  # noqa: BLE001 - OCIO raises its own Exception type
                found.append({"owner": owner, "file": src, "why": str(exc).splitlines()[0][:200]})

    for cs in cfg.getColorSpaces(OCIO.SearchReferenceSpaceType.SEARCH_REFERENCE_SPACE_ALL,
                                 OCIO.ColorSpaceVisibility.COLORSPACE_ALL):
        for d in (OCIO.ColorSpaceDirection.COLORSPACE_DIR_TO_REFERENCE,
                  OCIO.ColorSpaceDirection.COLORSPACE_DIR_FROM_REFERENCE):
            check(f"colour space {cs.getName()}", cs.getTransform(d))
    for lk in cfg.getLooks():
        check(f"look {lk.getName()}", lk.getTransform())
        check(f"look {lk.getName()}", lk.getInverseTransform())
    return found


def facts(path: str) -> dict:
    """Everything a show needs to know about the active config."""
    OCIO = _ocio()
    path = path or default_source()
    cfg = load(path)
    roles = {str(name): str(space) for name, space in cfg.getRoles()}        # PyOpenColorIO 2.x: (role, space)
    spaces = []
    for cs in cfg.getColorSpaces():
        spaces.append({"name": cs.getName(), "family": cs.getFamily() or "", "encoding": cs.getEncoding() or "",
                       "data": bool(cs.isData()), "aliases": list(cs.getAliases())[:8]})
    displays = {d: list(cfg.getViews(d)) for d in cfg.getDisplays()}
    try:
        cfg.validate()
        valid = "ok"
    except Exception as exc:  # noqa: BLE001
        valid = str(exc).splitlines()[0][:300]
    formats = []
    try:
        for item in OCIO.FileTransform.getFormats():                          # (name, extension) pairs
            name, ext = (item[0], item[1]) if isinstance(item, tuple) else (str(item), "")
            formats.append(f"{name} (.{ext})" if ext else str(name))
    except Exception:  # noqa: BLE001 - an older binding: the list is optional
        formats = []
    missing = missing_luts(cfg)
    return {
        "source": source_kind(path), "path": path, "name": cfg.getName() or os.path.basename(path),
        "description": (cfg.getDescription() or "")[:400], "ocio_version": OCIO.__version__,
        "config_version": f"{cfg.getMajorVersion()}.{cfg.getMinorVersion()}",
        "working_space": roles.get("scene_linear") or "", "roles": roles,
        "colorspaces": spaces, "displays": displays, "default_display": cfg.getDefaultDisplay(),
        "default_view": cfg.getDefaultView(cfg.getDefaultDisplay()) if cfg.getDefaultDisplay() else "",
        "looks": [lk.getName() for lk in cfg.getLooks()], "file_formats": formats,
        "search_path": cfg.getSearchPath(), "working_dir": cfg.getWorkingDir(),
        "missing_luts": missing, "valid": valid,
    }


def lists(path: str) -> dict:
    """The picker's lists: roles, colour spaces by family, displays -> views, looks."""
    f = facts(path)
    fam: dict[str, list[str]] = {}
    for cs in f["colorspaces"]:
        fam.setdefault(cs["family"] or "(no family)", []).append(cs["name"])
    return {"config": f["name"], "source": f["source"], "working_space": f["working_space"], "roles": f["roles"],
            "families": fam, "displays": f["displays"], "looks": f["looks"], "missing_luts": len(f["missing_luts"])}


def nearest(cfg, name: str, limit: int = 8) -> list[str]:
    names = [cs.getName() for cs in cfg.getColorSpaces()]
    low = name.strip().lower()
    hits = [n for n in names if low and (low in n.lower() or n.lower() in low)]
    if not hits:
        import difflib
        hits = difflib.get_close_matches(name, names, n=limit, cutoff=0.4)
    return hits[:limit]


def summary(f: dict) -> str:
    lines = [f"{f['name']}  |  {f['source']}  |  OCIO {f['ocio_version']} (config v{f['config_version']})",
             f"working space: {f['working_space'] or '-'}  |  {len(f['colorspaces'])} colour spaces  |  "
             f"{len(f['displays'])} displays  |  {len(f['looks'])} looks",
             f"default view: {f['default_display']} / {f['default_view']}",
             "missing LUTs: " + (", ".join(f"{m['file']} ({m['owner']})" for m in f["missing_luts"][:4])
                                 + (" ..." if len(f["missing_luts"]) > 4 else "") if f["missing_luts"] else "none"),
             f"validation: {f['valid']}",
             "roles: " + ", ".join(f"{k}={v}" for k, v in list(f["roles"].items())[:10])]
    return "\n".join(lines)


class NukeMax_OCIOConfigManager:
    CATEGORY = "NukeMax/Color"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    RETURN_TYPES = (TYPE, "STRING", "STRING")
    RETURN_NAMES = ("ocio_config", "info", "working_space")
    DESCRIPTION = ("The active OCIO config for the graph: built-in ACES, $OCIO, models/ocio_configs or a file. "
                   "Reports source, working space, roles, colour spaces, displays, views, looks, readable LUT formats "
                   "and missing LUTs; connect ocio_config to any NukeMax OCIO node. An edited config reloads by itself.")

    @classmethod
    def INPUT_TYPES(cls):
        from . import _list_configs
        return {"required": {"config": (_list_configs(), {"tooltip": "Built-in ACES, $OCIO or a config in "
                                                                    "models/ocio_configs/."})},
                "optional": {"config_file": ("STRING", {"default": "", "tooltip": "A .ocio file path on this "
                                                        "server (overrides config; held to the C2C media roots on a "
                                                        "server reachable from other machines)."})}}

    @staticmethod
    def _path(config: str, config_file: str = "") -> str:
        f = str(config_file or "").strip().strip('"')
        if f:
            from ..io import _media_roots as MR
            why = MR.check_run_path(f)
            if why:
                raise ValueError(f"NukeMax OCIO Config Manager: {why}")
            if not os.path.isfile(f):
                raise FileNotFoundError(f"NukeMax OCIO Config Manager: config_file {f!r} does not exist.")
            return f
        from . import _resolve_config_path
        p = _resolve_config_path(config)
        if not p:
            raise FileNotFoundError(f"NukeMax OCIO Config Manager: no config for {config!r} - drop a config "
                                    "folder in models/ocio_configs/, set $OCIO, or pick a built-in ACES config.")
        return p

    @classmethod
    def IS_CHANGED(cls, config="", config_file=""):
        try:
            return fingerprint(cls._path(config, config_file))
        except Exception as exc:  # noqa: BLE001 - execute says what is wrong
            return f"error|{exc}"

    def execute(self, config, config_file=""):
        path = self._path(config, config_file)
        f = facts(path)
        return {"ui": {"text": [summary(f)]}, "result": (path, json.dumps(f, indent=2), f["working_space"])}


NODE_CLASS_MAPPINGS = {"NukeMax_OCIOConfigManager": NukeMax_OCIOConfigManager}
NODE_DISPLAY_NAME_MAPPINGS = {"NukeMax_OCIOConfigManager": "NukeMax OCIO Config Manager"}


def _register_routes():
    """GET /nukemax/ocio/lists?config=<choice or path>: the picker's lists. POST /nukemax/ocio/reload: empty the
    cache. A file path is answered only inside the C2C media roots (routes are always held to them)."""
    try:
        from aiohttp import web
        from server import PromptServer  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - outside ComfyUI
        return
    server = getattr(PromptServer, "instance", None)
    if server is None:
        return
    routes = server.routes

    @routes.get("/nukemax/ocio/lists")
    async def _lists(request):
        choice = request.query.get("config", "").strip()
        try:
            if choice.startswith("ocio://") or not choice:
                path = choice or default_source()
            elif os.path.isabs(choice):
                from ..io import _media_roots as MR
                why = MR.check_route_path(choice)
                if why:
                    return web.json_response({"error": why}, status=403)
                path = choice
            else:
                from . import _resolve_config_path
                path = _resolve_config_path(choice) or ""
                if not path:
                    return web.json_response({"error": f"no config for {choice!r}"}, status=404)
            return web.json_response(lists(path))
        except Exception as exc:  # noqa: BLE001 - said to the picker
            return web.json_response({"error": str(exc)[:300]}, status=400)

    @routes.post("/nukemax/ocio/reload")
    async def _reload(request):
        return web.json_response({"dropped": reload()})


_register_routes()
