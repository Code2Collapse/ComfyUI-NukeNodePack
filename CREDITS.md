# Credits

Several node families in this pack are ports of other people's open-source
work. They are named here, with the licence each upstream declares, because
someone fixing a bug in a node should be able to find out whose idea it was.

`NOTICE` and `NOTICE.md` carry the formal licence terms and the redistribution
conditions. This file is the human one: who wrote it, and where the original is.

Licences below were read from the clones in `../third_party/` on 2026-09-19,
not assumed. Where a project declares a licence only in its README or
`pyproject.toml` and ships no `LICENSE` file, that is said so.

---

## Node families ported into this pack

### radiance — FXTD Studios
<https://github.com/fxtdstudios/radiance> · **GPL-3.0**, declared in the README
badge and credits; the repository ships **no LICENSE file**

The source for **`nukemax/nodes/hdr/`** and **`nukemax/utils/hdr_linear.py`** —
the nine `NukeMax/HDR` nodes: Image To Float32, Float32 Color Correct, Expand
Dynamic Range, Tone Map, Histogram, Exposure Blend, Shadow/Highlight Recovery,
Highlight Synthesis and 360 Panorama.

This is a **port, not a clean-room reimplementation**. An earlier header on
those files claimed otherwise; 301 of 847 lines were verbatim, with runs of up
to 13 consecutive identical lines, and the claim was removed. **This pack is
GPL-3.0 because of these files** — see `NOTICE.md`.

Radiance's own references, which its README credits and which this port
inherits: Reinhard et al. on colour transfer, Hable on filmic tone mapping,
Hill on HDR in Call of Duty, the ACES 2.0 RRT, and Troy Sobotka's AgX.

### nuke-nodes-comfyui — Sumit Chatterjee
<https://github.com/sumitchatterjee13/nuke-nodes-comfyui> · **MIT** (README)

Levels, ReadMultiPass, ShufflePass and the Viewer. The Viewer's backend came
from here; its front-end — the channel keys, the exposure scrub, the pixel
probe — is original, because the upstream has none.

### ComfyUI-ACES-IO — BISAM20
<https://github.com/BISAM20/ComfyUI-ACES-IO> · **MIT** (README)

EXR sequence I/O and the OCIO transforms in `nukemax/nodes/io/` and
`nukemax/nodes/ocio/`. The ACES configs it bundles are ASWF-licensed, and the
ACES 1.2 config is BSD via colour-science.

### ComfyUI-OCIO — Slava Sexton (AI VFX NEWS)
<https://github.com/SlavaSexton/ComfyUI-OCIO> · **MIT** (README badge)

The OCIO grade and curve work in `nukemax/nodes/ocio_color/`.

### ComfyUI-ReLight
**MIT** (README badge and LICENSE)

`nukemax/nodes/relight/light_paint.py` — the ReLight 2D light-painting node,
and the regression suite in `tests/test_relight_2d.py`. It complements this
pack's own PBR relight nodes rather than replacing them: those decompose an
image into albedo/normal/depth and shade it from geometry, this one paints
light onto the plate the way a comper does with a Radial and a Grade.

Changed on the way in: the node id is namespaced (`NukeMax_ReLight2D`) so it
cannot silently collide with the original if both are installed; the SciPy
import is guarded so its absence cannot take the whole relight package down;
and the tests now run against the real `comfy_api` instead of the upstream
stub, which is what caught the schema-introspection differences.

---

## Not ported — reference only

- **The Foundry's Nuke** — this pack takes its node vocabulary from a
  compositor's mental model of Nuke. No code, algorithms or assets from Nuke
  are here, and this project is not affiliated with The Foundry. See
  `NOTICE.md` for the trademark position.

---

## Bundled libraries

PyTorch, NumPy, OpenCV, SciPy, Pillow, librosa, SoundFile, imageio, OpenEXR /
Imath, OpenImageIO and PyOpenColorIO. Their copyrights and licences are in
`NOTICE.md`.

---

If your work is here and the attribution is wrong, thin, or you would rather it
were removed, open an issue — it will be fixed.
