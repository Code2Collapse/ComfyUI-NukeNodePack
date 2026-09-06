"""Deep-image compositing invariants.

PORTED FROM: ComfyUI-CustomNodePacks :: tests/test_nukenodemax.py (Feature 2)

deep_composite.py moved here in Apr 2026 and the data model changed with it —
from a list-of-dict DEEP_IMAGE to the tensor-backed DeepImage dataclass — so the
original tests could not be repointed as written. The behaviour they protected is
what matters and is reproduced here against the new API.

Found during the CustomNodePacks triage: this repo had ZERO deep-image coverage
for five registered nodes (DeepFromImage, DeepMerge, DeepHoldout, DeepFlatten,
DeepRecolor). The old tests were the only thing asserting these invariants
anywhere, so deleting them outright would have dropped the feature to nothing.

The invariant that matters is the FLAT_ALPHA antipattern: a deep merge that
silently collapses two samples into one flat matte still produces a plausible
picture, which is exactly why it needs an explicit test rather than an eyeball.
"""

import sys
from pathlib import Path

import pytest
import torch

PACK_ROOT = Path(__file__).resolve().parents[1]
if str(PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(PACK_ROOT))

from nukemax.nodes.deep import DeepFlatten, DeepHoldout, DeepMerge  # noqa: E402
from nukemax.types.deep_image import DeepImage  # noqa: E402

B, H, W = 1, 4, 4


def _layer(rgb, z_value, alpha=1.0):
    """Single-sample DeepImage of a flat colour at a constant depth."""
    img = torch.zeros(B, H, W, 3)
    for c, v in enumerate(rgb):
        img[..., c] = float(v)
    depth = torch.full((B, H, W), float(z_value))
    a = torch.full((B, H, W, 1), float(alpha))
    return DeepImage.from_image_depth(img, depth, alpha=a)


def test_merge_keeps_both_samples_and_does_not_flatten():
    """A merge must retain both samples, not collapse to a single flat matte.

    Collapsing still renders something plausible, so this is asserted on the
    sample count rather than on the picture.
    """
    front = _layer((0.0, 1.0, 0.0), z_value=5.0)   # green, near
    back = _layer((1.0, 0.0, 0.0), z_value=10.0)   # red, far

    merged, = DeepMerge().execute(a=front, b=back, max_samples=8)

    counts = merged.sample_count
    assert int(counts.min().item()) == 2, (
        f"merge collapsed samples (min count {int(counts.min().item())}, expected 2) "
        "— FLAT_ALPHA antipattern"
    )
    assert merged.samples_z.shape[0] == B


def test_opaque_front_fully_occludes_back():
    """Front-to-back over: an opaque near sample must hide the far one entirely."""
    front = _layer((0.0, 1.0, 0.0), z_value=5.0)
    back = _layer((1.0, 0.0, 0.0), z_value=10.0)

    merged, = DeepMerge().execute(a=front, b=back, max_samples=8)
    img, _depth = DeepFlatten().execute(deep=merged)

    g_mean = img[0, ..., 1].mean().item()
    r_mean = img[0, ..., 0].mean().item()
    assert g_mean > 0.95, f"front green dropped (g={g_mean:.3f}) — compositing broken"
    assert r_mean < 0.05, f"back red leaked through an opaque front (r={r_mean:.3f})"


def test_merge_is_order_independent():
    """a+b and b+a must flatten identically — depth decides, not argument order.

    Not in the original suite. Added because the new implementation sorts by z
    after a concat, so argument order is a live way to get this wrong.
    """
    front = _layer((0.0, 1.0, 0.0), z_value=5.0)
    back = _layer((1.0, 0.0, 0.0), z_value=10.0)

    ab, = DeepMerge().execute(a=front, b=back, max_samples=8)
    ba, = DeepMerge().execute(a=back, b=front, max_samples=8)
    img_ab, _ = DeepFlatten().execute(deep=ab)
    img_ba, _ = DeepFlatten().execute(deep=ba)

    assert torch.allclose(img_ab, img_ba, atol=1e-6), (
        "merge result depends on argument order; depth ordering must decide"
    )


def test_holdout_kills_samples_behind_the_matte():
    """Subject samples at or behind an opaque holdout must lose their alpha."""
    front = _layer((0.0, 0.0, 0.0), z_value=5.0)
    back = _layer((1.0, 1.0, 1.0), z_value=10.0)
    subject, = DeepMerge().execute(a=front, b=back, max_samples=8)

    out, = DeepHoldout().execute(subject=subject, holdout=front, alpha_threshold=0.5)

    # every surviving sample must sit in front of the holdout depth (5.0)
    alpha = out.samples_rgba[..., 3]
    behind = out.samples_z >= 5.0
    leaked = alpha[behind].abs().max().item() if behind.any() else 0.0
    assert leaked < 0.01, f"holdout failed: sample behind the matte kept alpha {leaked:.4f}"


def test_holdout_preserves_samples_in_front():
    """The complement: a holdout must not eat what is nearer than the matte.

    Guards against 'fixing' a holdout by zeroing everything.
    """
    near = _layer((0.0, 1.0, 0.0), z_value=1.0)
    matte = _layer((0.0, 0.0, 0.0), z_value=5.0)

    out, = DeepHoldout().execute(subject=near, holdout=matte, alpha_threshold=0.5)
    img, _ = DeepFlatten().execute(deep=out)
    assert img[0, ..., 1].mean().item() > 0.95, "holdout removed a sample in FRONT of the matte"
