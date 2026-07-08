"""Regression — PAR desqueeze/resqueeze round trip (anamorphic pipeline).

The user's plate: 4448x3840 @ PAR 1.7266 displays as 2:1 in Nuke but reads
as 1.158:1 square-pixel in ComfyUI. Desqueeze must produce the true 2:1
square-pixel frame (7680x3840 via stretch_width); resqueeze must restore the
exact original pixel dimensions.

Run with the ComfyUI python:  python tests/test_par_aspect.py
Auto-invoked by .claude/checks/validate_nodes.py (test_*_aspect.py glob).
"""
import sys
from pathlib import Path

import torch

PACK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK_ROOT))

from nukemax.nodes.comp.pixel_aspect import PARDesqueeze, PARResqueeze  # noqa: E402
import json  # noqa: E402


def run() -> int:
    fails = []

    def check(name, cond, detail):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}: {detail}")
        if not cond:
            fails.append(name)

    src = torch.rand(1, 3840, 4448, 3)
    de = PARDesqueeze()
    rs = PARResqueeze()

    # stretch_width: 4448x3840 @1.7266 -> 7680x3840, display AR 2.0
    out, info = de.execute(src, "ARRI 4448x3840→2:1 (1.7266)", 1.7266, "stretch_width", "bicubic")
    meta = json.loads(info)
    check("desqueeze size", out.shape[2] == 7680 and out.shape[1] == 3840,
          f"{out.shape[2]}x{out.shape[1]} (want 7680x3840)")
    check("display aspect", abs(meta["display_aspect"] - 2.0) < 0.01,
          f"{meta['display_aspect']} (want 2.0)")
    check("square AR", abs(out.shape[2] / out.shape[1] - 2.0) < 0.01,
          f"{out.shape[2]/out.shape[1]:.4f}")

    # round trip restores the EXACT plate dimensions
    back, _ = rs.execute(out, info, "bicubic")
    check("resqueeze exact", back.shape[2] == 4448 and back.shape[1] == 3840,
          f"{back.shape[2]}x{back.shape[1]} (want 4448x3840)")

    # squash_height alternative: 4448 x round(3840/1.7266)=2224
    out2, info2 = de.execute(src, "custom", 1.7266, "squash_height", "bilinear")
    check("squash size", out2.shape[2] == 4448 and out2.shape[1] == 2224,
          f"{out2.shape[2]}x{out2.shape[1]} (want 4448x2224)")
    back2, _ = rs.execute(out2, info2, "bilinear")
    check("squash round trip", back2.shape[2] == 4448 and back2.shape[1] == 3840,
          f"{back2.shape[2]}x{back2.shape[1]}")

    # PAR < 1 (NTSC DV 720x480 @0.9091 -> width shrinks to 655)
    ntsc = torch.rand(1, 480, 720, 3)
    out3, info3 = de.execute(ntsc, "NTSC DV (0.9091)", 1.0, "stretch_width", "bicubic")
    check("NTSC PAR<1", out3.shape[2] == round(720 * 0.9091),
          f"{out3.shape[2]} (want {round(720*0.9091)})")

    # square PAR is a no-op
    out4, _ = de.execute(ntsc, "square 1.0", 1.0, "stretch_width", "bicubic")
    check("PAR 1.0 no-op", out4.shape == ntsc.shape, f"{tuple(out4.shape)}")

    # resqueeze even after the AI changed resolution (e.g. upscaled 2x)
    up = torch.rand(1, 7680, 15360, 3)   # pretend 2x upscale of the 2:1 frame
    back3, _ = rs.execute(up, info, "bicubic")
    check("resqueeze after upscale", back3.shape[2] == 4448 and back3.shape[1] == 3840,
          f"{back3.shape[2]}x{back3.shape[1]}")

    # bad par_info fails loudly with guidance (resilient wrapper converts to
    # zero-output at runtime; direct call must raise)
    try:
        rs.execute.__wrapped__(rs, ntsc, "not json", "bicubic")
        check("bad info raises", False, "no exception")
    except ValueError as e:
        check("bad info raises", "par_info" in str(e), str(e)[:60])

    if fails:
        print(f"\nFAIL ({len(fails)}): {fails}")
        return 1
    print("\nPASS — PAR round-trip regression (9 assertions)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
