"""Deep from image: a one-frame depth / alpha serves every frame (L7.87, 2026-10-12, tools/c2c_exec_audit.py)."""
from __future__ import annotations

import pytest
import torch

from nukemax.types.deep_image import DeepImage


def test_one_depth_for_every_frame():
    img = torch.rand(3, 8, 10, 3)
    depth = torch.rand(1, 8, 10)
    deep = DeepImage.from_image_depth(img, depth)
    assert deep.samples_z.shape == (3, 1, 8, 10)
    assert torch.equal(deep.samples_z[2, 0], depth[0])


def test_per_frame_depth_and_alpha_stay_per_frame():
    img = torch.rand(2, 4, 4, 3)
    depth, alpha = torch.rand(2, 4, 4), torch.rand(2, 4, 4)
    deep = DeepImage.from_image_depth(img, depth, alpha)
    assert torch.equal(deep.samples_z[:, 0], depth)
    assert torch.allclose(deep.samples_rgba[:, 0, ..., 3], alpha)


@pytest.mark.parametrize("depth,match", [(torch.rand(2, 4, 5), "pixels"), (torch.rand(3, 4, 4), "frames")])
def test_mismatches_are_named(depth, match):
    with pytest.raises(ValueError, match=match):
        DeepImage.from_image_depth(torch.rand(2, 4, 4, 3), depth)
