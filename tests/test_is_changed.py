"""Regression tests for IS_CHANGED content hashing (no float nan)."""
from __future__ import annotations

import torch

from nukemax._is_changed_util import hash_args_and_kwargs
from nukemax.nodes.comp import Clamp, Reformat
from nukemax.nodes.fft import FFTAnalyze
from nukemax.nodes.keying import ChromaKeyer


def _img():
    return torch.rand(1, 16, 16, 3, dtype=torch.float32)


def test_hash_args_and_kwargs_stable_for_same_tensor():
    a = _img()
    h1 = hash_args_and_kwargs(a, width=512, height=512)
    h2 = hash_args_and_kwargs(a, width=512, height=512)
    assert h1 == h2
    assert h1 != float("nan")


def test_hash_args_and_kwargs_changes_when_tensor_changes():
    a = _img()
    b = a.clone()
    b[0, 0, 0, 0] += 0.01
    h_a = hash_args_and_kwargs(a)
    h_b = hash_args_and_kwargs(b)
    assert h_a != h_b


def test_hash_args_and_kwargs_changes_when_scalar_changes():
    a = _img()
    assert hash_args_and_kwargs(a, width=512) != hash_args_and_kwargs(a, width=256)


def test_reformat_is_changed_present_and_not_nan():
    img = _img()
    out = Reformat.IS_CHANGED(image=img, width=32, height=32, filter="bilinear", preserve_aspect="none")
    assert isinstance(out, str)
    assert out != str(float("nan"))


def test_clamp_is_changed_differs_for_different_images():
    a, b = _img(), _img()
    ha = Clamp.IS_CHANGED(image=a, minimum=0.0, maximum=1.0)
    hb = Clamp.IS_CHANGED(image=b, minimum=0.0, maximum=1.0)
    assert ha != hb


def test_chroma_keyer_is_changed_differs_on_screen():
    img = _img()
    g = ChromaKeyer.IS_CHANGED(
        image=img, screen="green", tolerance=0.05, softness=0.2, despill=1.0,
    )
    b = ChromaKeyer.IS_CHANGED(
        image=img, screen="blue", tolerance=0.05, softness=0.2, despill=1.0,
    )
    assert g != b


def test_fft_analyze_is_changed_injected_by_resilient():
    img = _img()
    out = FFTAnalyze.IS_CHANGED(image=img)
    assert isinstance(out, str) and len(out) == 32
