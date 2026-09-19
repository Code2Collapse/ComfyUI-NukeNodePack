# NOTICE — ComfyUI-NukeMaxNodes

Copyright (c) 2025-2026 Code2Collapse  
License: Apache License 2.0 (see LICENSE)

---

## Trademark Disclaimer

**"Nuke"** is a registered trademark of **The Foundry Visionmongers Ltd**.
This project (ComfyUI-NukeMaxNodes) is an independent open-source ComfyUI
node pack. It is **not affiliated with, endorsed by, or associated with
The Foundry Visionmongers Ltd** in any way.

The name reflects conceptual inspiration from professional VFX compositing
workflows; no code, algorithms, or proprietary assets from The Foundry's
Nuke software are included or reproduced in this project.

---

## Ported Node Source

Some node families in this pack are **ports of other open-source ComfyUI node
packs**, not independent implementations. They are listed here so that anyone
reading, forking or redistributing this repository knows exactly what is
derived and from where. Where a file follows its source closely, the file
header says so.

| NukeMax family | Upstream project | Licence the upstream declares |
| --- | --- | --- |
| `NukeMax/HDR` (`nukemax/nodes/hdr/`, `nukemax/utils/hdr_linear.py`) | [radiance](https://github.com/fxtdstudios/radiance) by FXTD Studios | README badge and credits say **GPL-3.0**; the repository ships **no LICENSE file** |
| `NukeMax/IO` EXR sequence, `NukeMax/OCIO` transforms | [ComfyUI-ACES-IO](https://github.com/BISAM20/ComfyUI-ACES-IO) by BISAM20 | README says **MIT** |
| `NukeMax/OCIO` grade / curves | [ComfyUI-OCIO](https://github.com/SlavaSexton/ComfyUI-OCIO) by Slava Sexton (AI VFX NEWS) | README badge says **MIT** |
| `NukeMax` Nuke-parity operators (Levels, MultiPass, ShufflePass, Viewer) | [nuke-nodes-comfyui](https://github.com/sumitchatterjee13/nuke-nodes-comfyui) by Sumit Chatterjee | README says **MIT** |

None of the four upstream clones in this workspace's `third_party/` ships an
actual `LICENSE` file; the licence in each row is the one the project's README
or `pyproject.toml` declares.

Front-ends are **not** ported. Every node in this pack carries a NukeMax
front-end written for this pack (`web/widgets/`), because the upstream UIs are
either absent or thinner than what these nodes need.

### Open licence question on the HDR family

`radiance` declares GPL-3.0 in its README but ships no LICENSE file, and this
repository's `LICENSE` is Apache-2.0. Those two are not compatible for
redistribution of a combined work. This is recorded here rather than papered
over; the repository owner decides how it is resolved (relicense this pack,
rewrite the HDR family independently, or drop it).

---

## Third-Party Libraries

The following open-source libraries are used by this project. Their
copyrights and licenses are reproduced for compliance.

### 1. PyTorch

**Repository**: <https://github.com/pytorch/pytorch>  
**Copyright**: Copyright (c) 2016-2024 Facebook, Inc. and its affiliates  
**License**: BSD-style license  
<https://github.com/pytorch/pytorch/blob/main/LICENSE>

### 2. NumPy

**Repository**: <https://github.com/numpy/numpy>  
**Copyright**: Copyright (c) 2005-2024 NumPy Developers  
**License**: BSD 3-Clause  
<https://github.com/numpy/numpy/blob/main/LICENSE.txt>

### 3. librosa

**Repository**: <https://github.com/librosa/librosa>  
**Copyright**: Copyright (c) 2013-2024 librosa development team  
**License**: ISC License  
<https://github.com/librosa/librosa/blob/main/LICENSE.md>

### 4. SoundFile (PySoundFile)

**Repository**: <https://github.com/bastibe/python-soundfile>  
**Copyright**: Copyright (c) 2013 Bastian Bechtold  
**License**: BSD 3-Clause  
<https://github.com/bastibe/python-soundfile/blob/master/LICENSE>

### 5. imageio

**Repository**: <https://github.com/imageio/imageio>  
**Copyright**: Copyright (c) 2014-2024 imageio contributors  
**License**: BSD 2-Clause  
<https://github.com/imageio/imageio/blob/master/LICENSE>

### 6. OpenCV

**Repository**: <https://github.com/opencv/opencv>  
**License**: Apache License 2.0 (since OpenCV 4.5)  
<https://github.com/opencv/opencv/blob/master/LICENSE>

### 7. SciPy

**Repository**: <https://github.com/scipy/scipy>  
**Copyright**: Copyright (c) 2001-2024 SciPy Developers  
**License**: BSD 3-Clause  
<https://github.com/scipy/scipy/blob/main/LICENSE.txt>

### 8. OpenEXR / Imath (optional dependency)

**Repository**: <https://github.com/AcademySoftwareFoundation/openexr>  
**Copyright**: Copyright (c) Contributors to the OpenEXR Project  
**License**: BSD 3-Clause  
<https://github.com/AcademySoftwareFoundation/openexr/blob/main/LICENSE.md>

---

## FFT Algorithms

The FFT routines in `nukemax/nodes/fft/fft_tensor.py` use PyTorch's built-in
`torch.fft` module which is based on the FFTPACK / cuFFT libraries included
in PyTorch under its own BSD license.

---

## Optical Flow

Optical-flow estimation in `nukemax/nodes/flow/flow_field.py` uses standard
PyTorch and OpenCV algorithms. No code is copied from proprietary sources.
