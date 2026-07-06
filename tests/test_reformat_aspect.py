"""Regression test — Reformat aspect-ratio behaviour (the "squeeze" bug).

Bug: Reformat defaulted to a silent non-uniform stretch, so non-1:1 sources
(repro: 4448x3840) came out distorted toward the target box's ratio.

Run with the ComfyUI python (needs torch):
    cd ComfyUI-NukeMaxNodes && python tests/test_reformat_aspect.py
Also invoked by .claude/checks/validate_nodes.py when torch is available.
"""
import sys
from pathlib import Path

import torch

PACK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK_ROOT))

from nukemax.nodes.comp import Reformat  # noqa: E402


def _content_box(img_bhwc):
    """Bounding box of non-black pixels (content vs letterbox padding)."""
    m = (img_bhwc[0].amax(dim=-1) > 0.01)
    ys = torch.where(m.any(dim=1))[0]
    xs = torch.where(m.any(dim=0))[0]
    return int(xs[0]), int(ys[0]), int(xs[-1] - xs[0] + 1), int(ys[-1] - ys[0] + 1)


def _src(w, h):
    """Mid-grey source so content is distinguishable from black padding."""
    return torch.full((1, h, w, 3), 0.5)


def run():
    node = Reformat()
    failures = []
    report = []

    def check(name, cond, detail):
        report.append(f"  {'PASS' if cond else 'FAIL'}  {name}: {detail}")
        if not cond:
            failures.append(name)

    cases = [("square 512x512", 512, 512), ("16:9 1280x720", 1280, 720),
             ("repro 4448x3840", 4448, 3840)]
    TW, TH = 1920, 1080

    for label, w, h in cases:
        src = _src(w, h)
        src_ar = w / h

        # fit (default): canvas is target box, CONTENT keeps source AR
        (out,) = node.execute(src, TW, TH, "bilinear", "fit")
        _, _, cw, ch = _content_box(out)
        check(f"fit/{label} canvas", out.shape[1:3] == (TH, TW),
              f"canvas {out.shape[2]}x{out.shape[1]} (want {TW}x{TH})")
        check(f"fit/{label} content AR", abs(cw / ch - src_ar) < 0.02,
              f"content {cw}x{ch} AR {cw/ch:.3f} (source {src_ar:.3f})")

        # fill: canvas fully covered (no padding anywhere)
        (out,) = node.execute(src, TW, TH, "bilinear", "fill")
        x0, y0, cw, ch = _content_box(out)
        check(f"fill/{label} covers", (x0, y0, cw, ch) == (0, 0, TW, TH),
              f"content box {x0},{y0} {cw}x{ch}")

        # width: content width == target width; scale is UNIFORM, so visible
        # height is the uniformly-scaled height, cropped to the canvas when it
        # overflows (Nuke crops vertical overflow in width mode).
        (out,) = node.execute(src, TW, TH, "bilinear", "width")
        _, _, cw, ch = _content_box(out)
        expect_h = min(TH, round(h * TW / w))
        check(f"width/{label}", cw == TW and abs(ch - expect_h) <= 1,
              f"content {cw}x{ch} (want {TW}x{expect_h})")

        # distort: explicit opt-in fills the box even when ARs differ
        (out,) = node.execute(src, TW, TH, "bilinear", "distort")
        check(f"distort/{label}", out.shape[1:3] == (TH, TW),
              f"canvas {out.shape[2]}x{out.shape[1]}")

    # from_input preset: target box adopts the source's own ratio, so even
    # fit produces zero padding and exact AR for the odd 4448x3840 source.
    src = _src(4448, 3840)
    (out,) = node.execute(src, 1112, 999, "bilinear", "fit", aspect_preset="from_input")
    ar = out.shape[2] / out.shape[1]
    check("from_input/4448x3840", abs(ar - 4448 / 3840) < 0.01,
          f"canvas {out.shape[2]}x{out.shape[1]} AR {ar:.3f} (source {4448/3840:.3f})")

    # legacy "none" still runs (alias of distort) so old workflows don't break
    (out,) = node.execute(_src(640, 480), TW, TH, "bilinear", "none")
    check("legacy none", out.shape[1:3] == (TH, TW), f"{out.shape[2]}x{out.shape[1]}")

    # RGBA survives (old code hardcoded 3 channels and crashed/dropped alpha)
    rgba = torch.cat([_src(640, 480), torch.ones(1, 480, 640, 1)], dim=-1)
    (out,) = node.execute(rgba, TW, TH, "bilinear", "fit")
    check("rgba fit channels", out.shape[-1] == 4, f"channels {out.shape[-1]}")

    # transparent pad yields alpha=0 in the letterbox area
    (out,) = node.execute(_src(512, 512), TW, TH, "bilinear", "fit", pad="transparent")
    check("transparent pad", out.shape[-1] == 4 and float(out[0, 0, 0, 3]) == 0.0,
          f"channels {out.shape[-1]} corner alpha {float(out[0,0,0,3]):.2f}")

    print("Reformat aspect-ratio regression:")
    print("\n".join(report))
    if failures:
        print(f"\nFAIL ({len(failures)}): {failures}")
        return 1
    print(f"\nPASS — {len(report)} assertions")
    return 0


if __name__ == "__main__":
    sys.exit(run())
