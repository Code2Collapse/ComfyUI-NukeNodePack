"""Graph-never-crashes contract for nodes.

Wrap a node class with `@resilient` to catch any exception in `execute`,
log the traceback, and return a safe default tuple matching the node's
declared `RETURN_TYPES` plus an `info` string prefixed `"ERROR: "`.

The decorator inspects `RETURN_TYPES` and synthesizes a passthrough
default. If a node declares an `ERROR_DEFAULTS` classvar (a tuple of
callables `() -> value`), those are used in preference. Nodes whose
last `RETURN_TYPE` is `"STRING"` named `info`/`status`/`error` get an
informative error message in that slot.
"""
from __future__ import annotations

import functools
import logging
import traceback
from typing import Any, Callable

import torch

log = logging.getLogger("nukemax")

#: Errors that mean THE USER WIRED SOMETHING WRONG, not that the maths failed.
#:
#: These are re-raised so the queue stops and the operator sees the problem on the
#: node. Swallowing them returned a BLACK frame from `_zero_for` and let the comp
#: continue - on a 200-frame render that surfaces at review, which is worse than a
#: hard stop AND worse than a passthrough. A missing LUT file, malformed metadata
#: JSON, or a mis-shaped socket is not a transient fault to absorb.
#:
#: Genuine RUNTIME faults (OOM, a codec failing mid-frame, an absent backend) still
#: degrade - that is what the graph-never-crashes contract is actually for.
INPUT_VALIDATION_ERRORS: tuple = (
    FileNotFoundError,
    NotADirectoryError,
    IsADirectoryError,
    PermissionError,
    ValueError,      # bad shapes/sockets via require_image_bhwc, and JSON parse
    TypeError,
    KeyError,
)



#: Magenta - the VFX convention for "this frame is wrong". A black frame reads as
#: a dark shot and survives review; magenta cannot be mistaken for camera output.
ERROR_RGB = (1.0, 0.0, 1.0)


def _error_fill(rt: str) -> Any:
    """Degraded value that is VISIBLY wrong, not silently plausible."""
    rt_u = rt.upper()
    if rt_u == "IMAGE":
        img = torch.zeros(1, 64, 64, 3, dtype=torch.float32)
        for c, v in enumerate(ERROR_RGB):
            img[..., c] = v
        return img
    if rt_u == "MASK":
        # A fully-open mask is loud downstream; an all-zero mask composites
        # nothing and looks like "no change".
        return torch.ones(1, 64, 64, dtype=torch.float32)
    return _zero_for(rt)


def _zero_for(rt: str) -> Any:
    rt_u = rt.upper()
    if rt_u == "IMAGE":
        return torch.zeros(1, 64, 64, 3, dtype=torch.float32)
    if rt_u == "MASK":
        return torch.zeros(1, 64, 64, dtype=torch.float32)
    if rt_u == "LATENT":
        return {"samples": torch.zeros(1, 4, 8, 8, dtype=torch.float32)}
    if rt_u in ("FLOAT",):
        return 0.0
    if rt_u in ("INT",):
        return 0
    if rt_u in ("BOOLEAN", "BOOL"):
        return False
    if rt_u == "STRING":
        return ""
    return None


def resilient(cls=None, *, on_error: str = "raise"):
    """Class decorator. Wraps the node's FUNCTION method.

    ``on_error`` (default ``"raise"``) is the P0 loudness fix. Previously EVERY
    exception was swallowed and the node returned a zeroed tuple - a BLACK frame
    that renders happily and is only noticed at review. Silent degradation is a
    defect, not a policy, so it is now OPT-IN:

        @resilient                      -> raise (default)
        @resilient(on_error="degrade")  -> degrade, LOUDLY

    A node may also set ``ON_ERROR = "degrade"`` as a class attribute. A degraded
    path must be unmistakable, so the wrapper fills IMAGE outputs with MAGENTA
    (never black), opens MASK outputs fully, and writes ``ERROR: <exc>`` into
    EVERY STRING output - not only ones named info/status/error/message, because
    a report socket that stays blank is how the failure stayed invisible.
    """
    if cls is None:
        return lambda c: resilient(c, on_error=on_error)
    fn_name = getattr(cls, "FUNCTION", None)
    if not fn_name or not hasattr(cls, fn_name):
        return cls

    if not hasattr(cls, "IS_CHANGED"):
        from .._is_changed_util import hash_args_and_kwargs

        @classmethod
        def IS_CHANGED(cls, **kwargs):  # noqa: N805
            return hash_args_and_kwargs(**kwargs)

        cls.IS_CHANGED = IS_CHANGED

    original = getattr(cls, fn_name)

    @functools.wraps(original)
    def wrapped(self, *args, **kwargs):
        try:
            with torch.inference_mode():
                return original(self, *args, **kwargs)
        except INPUT_VALIDATION_ERRORS:
            # Bad INPUT - re-raise so the queue stops and the operator sees it.
            # Returning a zeroed tensor here shipped black frames silently.
            raise
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc()
            log.error("[%s] %s\n%s", cls.__name__, exc, tb)
            policy = str(getattr(cls, "ON_ERROR", on_error) or "raise").lower()
            if policy != "degrade":
                # DEFAULT (P0 loudness fix). A runtime fault stops the queue
                # rather than emitting a frame nobody will question.
                raise
            rt = getattr(cls, "RETURN_TYPES", ())
            defaults = list(getattr(cls, "ERROR_DEFAULTS", ()))
            out: list[Any] = []
            for i, t in enumerate(rt):
                if i < len(defaults):
                    try:
                        out.append(defaults[i]())
                        continue
                    except Exception:
                        pass
                out.append(f"ERROR: {exc}" if t.upper() == "STRING" else _error_fill(t))
            return tuple(out)

    setattr(cls, fn_name, wrapped)
    return cls


def resilient_fn(returns: tuple[str, ...]) -> Callable:
    """Function-level variant for ad-hoc node functions."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                log.error("[%s] %s\n%s", fn.__name__, exc, traceback.format_exc())
                out = [_zero_for(t) for t in returns]
                if returns and returns[-1].upper() == "STRING":
                    out[-1] = f"ERROR: {exc}"
                return tuple(out)
        return wrapped
    return deco
