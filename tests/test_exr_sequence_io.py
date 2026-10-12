"""EXR Sequence Save / Load round trip without the OpenEXR bindings (L7.87, 2026-10-12).

The writer fell back to OpenCV, which only handles EXR when OPENCV_IO_ENABLE_OPENEXR=1 is set before ANY module imports
cv2 - on a real ComfyUI install another pack always imports cv2 first, so "EXR Sequence Save" failed (measured by
tools/c2c_exec_audit.py on the owner's stack). OpenImageIO is now the path between OpenEXR and OpenCV.
"""
from __future__ import annotations

import pytest
import torch

from nukemax.nodes.io import exr_sequence as X

pytestmark = pytest.mark.skipif(not X._HAVE_OIIO or X._HAVE_OPENEXR,
                                reason="exercises the OpenImageIO path (OpenImageIO present, OpenEXR bindings absent)")


@pytest.mark.parametrize("bit_depth,tol", [("32f (float)", 0.0), ("16f (half-float)", 1e-3)])
def test_save_then_load_round_trips_through_openimageio(tmp_path, bit_depth, tol):
    g = torch.Generator().manual_seed(3)
    img = torch.rand(3, 24, 40, 3, generator=g) * 4.0          # scene-linear, above 1.0 on purpose
    _out_img, last = X.EXRSequenceSave().execute(img, str(tmp_path), "plate_%04d", bit_depth,
                                                 "ZIP  (lossless, recommended)", start_frame=1)
    files = sorted(p.name for p in tmp_path.glob("*.exr"))
    assert files == ["plate_0001.exr", "plate_0002.exr", "plate_0003.exr"], files
    back = torch.cat([X._load_exr_frame(str(tmp_path / f)) for f in files])
    assert back.shape == img.shape
    assert float((back - img).abs().max()) <= tol * 4.0 + 1e-7
