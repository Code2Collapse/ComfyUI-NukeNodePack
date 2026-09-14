"""House UI kit: the plain-English error table.

CLAUDE.md's visual check requires "error messages in plain English - no raw
Python tracebacks". That rule is implemented once, in
web/widgets/_nukemax_errors.js, and applies to all 179 nodes - so it is worth
actually EXECUTING rather than eyeballing.

The rules module deliberately has no ComfyUI imports, which is what lets plain
node run it here. If someone adds an `import ... from "../../scripts/app.js"`
to it, these tests fail loudly rather than the rules quietly going untested.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

PACK = Path(__file__).resolve().parents[1]
RULES_JS = PACK / "web" / "widgets" / "_nukemax_errors.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _humanise(samples: list[str]) -> list[str]:
    """Run the real JS rules over a batch of raw error texts."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # copy the module next to the driver so its relative path resolves
        (tmp / "_nukemax_errors.mjs").write_bytes(RULES_JS.read_bytes())
        driver = tmp / "run.mjs"
        driver.write_text(
            'import { humaniseError } from "./_nukemax_errors.mjs";\n'
            "const inp = JSON.parse(process.argv[2]);\n"
            "console.log(JSON.stringify(inp.map(humaniseError)));\n",
            encoding="utf-8",
        )
        r = subprocess.run([NODE, str(driver), json.dumps(samples)],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout.strip())


def test_rules_module_has_no_comfyui_imports():
    # INVARIANT: the moment this module imports ComfyUI, it stops being
    # testable and the whole table goes unverified.
    src = RULES_JS.read_text(encoding="utf-8")
    assert "scripts/app.js" not in src
    assert "scripts/api.js" not in src


def test_missing_package_names_the_package():
    # INVARIANT: "install something" is useless; the message must say WHICH.
    (out,) = _humanise(
        ["ModuleNotFoundError: No module named 'skimage'"])
    assert "skimage" in out
    assert "Traceback" not in out


def test_the_exr_and_ocio_cases_give_the_install_command():
    # INVARIANT: these three are the pack's most common first-run failures, and
    # each has an exact fix, so the message should carry it.
    outs = _humanise([
        "ModuleNotFoundError: No module named 'OpenImageIO'",
        "ModuleNotFoundError: No module named 'PyOpenColorIO'",
        "ModuleNotFoundError: No module named 'av'",
    ])
    assert "pip install OpenImageIO" in outs[0]
    assert "opencolorio" in outs[1].lower()
    assert "pip install av" in outs[2]


def test_out_of_memory_says_what_to_do():
    # INVARIANT: an OOM message that does not suggest an action wastes the
    # artist's next ten minutes.
    (out,) = _humanise(
        ["torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB"])
    assert "memory" in out.lower()
    assert any(k in out.lower() for k in ("resolution", "batch", "cpu"))


def test_unconnected_input_is_not_reported_as_nonetype():
    # INVARIANT: "'NoneType' object has no attribute 'shape'" is the single most
    # common ComfyUI error and means exactly one thing to a user: a wire is missing.
    (out,) = _humanise(
        ["AttributeError: 'NoneType' object has no attribute 'shape'"])
    assert "not connected" in out.lower()
    assert "NoneType" not in out


def test_size_mismatch_points_at_the_fix():
    # INVARIANT: in a compositing pack, mismatched inputs are routine and the
    # remedy is always the same - Reformat or Crop first.
    (out,) = _humanise(
        ["RuntimeError: Sizes of tensors must match except in dimension 0"])
    assert "different sizes" in out.lower() or "same size" in out.lower()
    assert "Reformat" in out or "Crop" in out


def test_missing_file_mentions_the_frame_pattern():
    # INVARIANT: for a Read node the usual cause is not a typo in the folder but
    # a #### pattern that does not match what is on disk.
    (out,) = _humanise(
        ["FileNotFoundError: [Errno 2] No such file or directory: 'D:/plates/sh010.1001.exr'"])
    assert "exist" in out.lower()
    assert "frame number" in out.lower() or "pattern" in out.lower()


def test_unknown_errors_fall_back_to_the_exception_not_the_traceback_header():
    # INVARIANT: the LAST meaningful line is the exception; the first is always
    # "Traceback (most recent call last):", which tells the user nothing.
    (out,) = _humanise([
        "Traceback (most recent call last):\n"
        '  File "x.py", line 3, in <module>\n'
        "    boom()\n"
        "WeirdCustomError: the flux capacitor is unseated"
    ])
    assert out.startswith("WeirdCustomError")
    assert "Traceback" not in out


def test_empty_input_never_returns_empty_string():
    # INVARIANT: a blank status strip reads as "fine". It must always say something.
    for out in _humanise(["", "   "]):
        assert out.strip()


def test_interrupt_is_not_dressed_up_as_a_failure():
    # INVARIANT: the user pressed cancel. Showing a scary error for it is wrong.
    (out,) = _humanise(["KeyboardInterrupt: Interrupted"])
    assert out.lower().startswith("cancel")
