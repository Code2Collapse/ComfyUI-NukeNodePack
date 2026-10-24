# ComfyUI-NukeMaxNodes

> ### 📖 Full node & parameter reference
> **[NODE_REFERENCE.md](NODE_REFERENCE.md)** documents **every node in this pack**:
> each input's type, default, valid range and what it actually does, plus every
> output. It is generated directly from the live `NODE_CLASS_MAPPINGS`, so the
> descriptions there are the *same strings* you see as tooltips in ComfyUI and
> cannot drift out of date. Start there when you want to know what a knob does;
> read on here for how the pieces fit together.


> **Trademark Notice**: "Nuke" is a registered trademark of **The Foundry Visionmongers Ltd**.
> This project is an independent open-source ComfyUI node pack and is **not affiliated with,
> endorsed by, or associated with The Foundry or its Nuke software** in any way.
> No Foundry code or proprietary assets are used. See [NOTICE.md](NOTICE.md).

Hybrid VFX × AI bridge nodes for ComfyUI. ~50 nodes across 13 file-grouped categories — every traditional VFX operation also exposes an AI-consumable side output (SAM prompts, latent guidance, conditioning curves, EXR metadata) so you can bridge a Nuke/Blender-style compositing flow into a Flux / Qwen-Image / Wan / Z-Image graph without round-tripping to disk.

Foundation: strict custom datatypes (`ROTO_SHAPE`, `FFT_DATA`, `MATERIAL_PBR`, `LIGHT_PROBE`, `AUDIO_TENSOR`, `FLOW_VECTOR`, `EDGE_MAP`, `MEC_RENDER_PASSES`, …), vectorized PyTorch math (BCHW with batch dim = time), per-batch temporal execution, and an optional JS web-extension layer (`web/`) for interactive editors.

## Installation

```bash
cd ComfyUI/custom_nodes
git clone <this-repo> ComfyUI-NukeMaxNodes
pip install -r ComfyUI-NukeMaxNodes/requirements.txt
```

Embedded-Python (ComfyUI portable):

```bash
..\..\python_embeded\python.exe -m pip install -r ComfyUI-NukeMaxNodes\requirements.txt
```

`requirements.txt`: `torch>=2.0`, `numpy>=1.24`, `librosa>=0.10`, `soundfile>=0.12`, `imageio>=2.31` (and optionally `OpenEXR` for native EXR I/O — `imageio` is the cross-platform fallback).

`WEB_DIRECTORY` is set to `./web`, so JS extensions for the interactive bezier editor and curve viewer load automatically. Restart ComfyUI; nodes appear under `NukeMax/<category>`.

## Node groups

Organised by source file under `nukemax/nodes/`. Counts are exact; class names listed for traceability.

### Smart Roto (`roto/`) — 5 nodes

`NukeMax_RotoShapeCreate`, `NukeMax_RotoShapeEdit`, `NukeMax_RotoShapeRender`, `NukeMax_RotoTrack`, `NukeMax_RotoToDiffusionGuidance`.

- **Custom type:** `ROTO_SHAPE` (per-frame bezier control points + tangents).
- **Inputs (typical):** initial keyframe shape (JSON), source IMAGE batch, optional tracker model.
- **Outputs:** `ROTO_SHAPE`, `MASK` (rasterised), and on `RotoToDiffusionGuidance` a CONDITIONING-style guidance bundle.
- **Use case:** classical bezier roto with sub-pixel rasterisation; the `RotoToDiffusionGuidance` bridge converts shapes into spatial conditioning consumable by ControlNet / inpaint nodes downstream.

### Frequency-Guided Generation (`fft/`) — 5 nodes

`NukeMax_FFTAnalyze`, `NukeMax_FFTSynthesize`, `NukeMax_FFTSpectrumViewer`, `NukeMax_FFTLatentMatch`, `NukeMax_FFTBandFilter`.

- **Custom type:** `FFT_DATA` (complex spectrum, log magnitude, phase).
- **Inputs:** IMAGE / LATENT, frequency band specs, optional reference latent.
- **Outputs:** `FFT_DATA`, IMAGE preview, LATENT (frequency-matched).
- **Use case:** seamless inpaint by matching the frequency profile of a generation to surrounding plate; band-isolated noise injection; debugging tile/seam artefacts on Flux/Qwen-Image upscales.

### PBR Relight (`relight/`) — 6 nodes

`NukeMax_MaterialDecompose`, `NukeMax_LightProbeEstimate`, `NukeMax_ThreePointLight`, `NukeMax_PBRRelight`, `NukeMax_MaterialEdit`, `NukeMax_EXRMaterialBridge`.

- **Custom types:** `MATERIAL_PBR` (albedo / normal / roughness / metalness), `LIGHT_PROBE` (HDR environment).
- **Inputs:** IMAGE (or EXR via the bridge), light positions/colors/intensities.
- **Outputs:** decomposed PBR channels, relit IMAGE, exportable EXR.
- **Use case:** estimate a light probe from a single still, relight under three-point lighting, or hand a `MATERIAL_PBR` bundle to Blender/Nuke through `EXRMaterialBridge`. Useful as an upstream stage before Flux/Qwen-Image refines.

### Audio-Reactive (`audio/`) — 5 nodes

`NukeMax_AudioLoad`, `NukeMax_AudioFeatureExtract`, `NukeMax_AudioToCurve`, `NukeMax_AudioMaskModulate`, `NukeMax_AudioCFGModulate`.

- **Custom types:** `AUDIO_TENSOR`, `CURVE` (per-frame floats aligned to a target FPS).
- **Inputs:** audio file path or AUDIO tensor, FPS, frame count, feature ('rms' / 'onset' / 'spectral_centroid' / band energies).
- **Outputs:** `AUDIO_TENSOR`, per-frame `CURVE`, modulated MASK, modulated CFG schedule.
- **Use case:** drive mask intensity or sampler CFG from beat/onset for music-reactive Wan or AnimateDiff renders.

### Sub-Pixel Flow Compositing (`flow/`) — 6 nodes

`NukeMax_FlowEstimate`, `NukeMax_FlowForwardWarp`, `NukeMax_FlowBackwardWarp`, `NukeMax_FlowOcclusion`, `NukeMax_FlowVisualize`, `NukeMax_CleanPlateMerge`.

- **Custom type:** `FLOW_VECTOR` (B×2×H×W).
- **Inputs:** IMAGE batch (T frames), optional reference plate.
- **Outputs:** `FLOW_VECTOR`, warped IMAGE, occlusion MASK, RGB flow viz, clean-plate composite.
- **Use case:** temporal coherence for Wan/AnimateDiff; clean-plate generation for inpaint-anything plates that downstream Flux fills.

### Smart Edge Tools (`edges/`) — 4 nodes

`NukeMax_NormalAwareBlur`, `NukeMax_MatteDensityAdjust`, `NukeMax_SubPixelEdgeDetect`, `NukeMax_HairAwareChoke`.

- **Custom type:** `EDGE_MAP`.
- **Inputs:** IMAGE, optional NORMAL or MATTE.
- **Outputs:** IMAGE / MASK with edge-respecting filtering.
- **Use case:** clean compositing-grade edges before/after a diffusion pass — particularly hair where standard chokes destroy detail.

### Utilities (`utils/`) — 1 node

`UniversalRerouteMEC` — typed reroute node for the MEC type system. Keeps long graphs readable without forcing scalar collapse.

### EXR I/O (`io/`) — 3 nodes

`LoadEXRMEC`, `SaveEXRMEC`, `EXRMetadataReaderMEC`.

- **Custom type:** `MEC_EXR_METADATA`.
- **Inputs:** filepath, channel selection, optional metadata to embed on save.
- **Outputs:** IMAGE (with optional alpha / Z / multi-channel split), full EXR metadata dict.
- **Use case:** read multi-channel EXRs from Nuke / Blender renders, ingest as IMAGE batches for diffusion preprocessing, write back round-trip with metadata preserved.

### Render Passes (`passes/`) — 2 nodes

`MergeRenderPassesMEC`, `DepthOfFieldMaskMEC`.

- **Custom type:** `MEC_RENDER_PASSES`.
- **Inputs:** beauty + diffuse + specular + normal + depth IMAGEs, focus distance / aperture.
- **Outputs:** merged IMAGE, DoF MASK.
- **Use case:** bring 3D render passes into the diffusion graph; build per-region masks (in-focus subject vs out-of-focus background) for targeted inpainting.

### Plate Tools (`plate/`) — 4 nodes

`GrainMatchMEC`, `PlateStabilizerMEC`, `CleanPlateExtractorMEC`, `DifferenceMatteMEC`.

- **Inputs:** plate IMAGE, generated IMAGE, motion estimate.
- **Outputs:** grain-matched IMAGE, stabilised IMAGE batch, clean plate, difference MASK.
- **Use case:** make Flux/Qwen/Wan output composite cleanly into live-action plates — match grain, stabilise jitter, extract clean plates for set extension.

### Geometry Extensions (`geometry_ext/`) — 3 nodes

`DepthWarpMEC`, `NormalToCurvatureMEC`, `PositionPassSplitterMEC`.

- **Inputs:** DEPTH / NORMAL / POSITION IMAGEs.
- **Outputs:** warped IMAGE, curvature MASK, X/Y/Z split IMAGEs.
- **Use case:** turn a depth pass into camera-relative warps; convert normals into curvature masks for ControlNet conditioning; split P-pass for region masking.

### Metadata (`metadata/`) — 3 nodes

`MetadataWriterMEC`, `FrameRangeRouterMEC`, `ShotMetadataNodeMEC`.

- **Inputs:** IMAGE batch, key/value pairs, frame range spec.
- **Outputs:** IMAGE (with metadata attached), routed IMAGE batches per range, shot metadata bundle.
- **Use case:** keep shot codes, frame numbers, and scene/take info traveling with the tensors — pair with `ComfyUI-FolderIncrementer` for fully-versioned saves.

### Color (`color/`) — 3 nodes

`ColorSpaceConvertMEC`, `LUTApplyMEC`, `ExposureGradeMEC`.

- **Inputs:** IMAGE, source/target color space, `.cube` LUT path, exposure / lift / gamma / gain.
- **Outputs:** color-managed IMAGE.
- **Use case:** convert sRGB ↔ ACEScg for diffusion (always do diffusion in linear/sRGB, then grade via LUT/exposure on the way out).

## Use in image/video generation pipelines (Flux / Qwen-Image / Wan / Z-Image / ERNIE-VL)

| Model family | Key bridges from this pack |
|---|---|
| **Flux** | `RotoToDiffusionGuidance` → ControlNet/inpaint conditioning. `FFTLatentMatch` for tile-seamless upscale. `GrainMatchMEC` for live-action composites. `ColorSpaceConvertMEC` + `LUTApplyMEC` to keep the look consistent. |
| **Qwen-Image** | Same pattern as Flux. Use `NormalToCurvatureMEC` outputs as ControlNet hints if a Qwen-compatible curvature ControlNet is loaded. |
| **Wan 2.x** | `FlowEstimate` + `FlowForwardWarp` give per-frame flow conditioning that can be wired into Wan-Animate or AnimateDiff temporal nodes. `AudioToCurve` + `AudioCFGModulate` for music-reactive video. `LoadEXRMEC` for video frame ingest from a renderer. `PlateStabilizerMEC` to denoise camera jitter before sampling. |
| **Z-Image** | Use the FFT and edge tools for refinement passes; same Flux-style ControlNet/inpaint bridges apply where Z-Image exposes them. |
| **GLM-Image** | The IMAGE outputs are model-agnostic and feed cleanly back into the GLM-Image sampler I2I path (via `denoise_strength`). |
| **ERNIE-VL** | Not directly applicable (LLM, not a sampler). The metadata nodes can still be useful for cataloguing ERNIE-VL described frames. |

The strict typing means a `MASK` produced by, for example, `RotoShapeRender` is a normal ComfyUI MASK and connects to any node that accepts MASK — only the *bundle* types (`ROTO_SHAPE`, `FFT_DATA`, `MATERIAL_PBR`, …) are pack-internal.

## Fixes 2026-10-24 (comp basics)

From an audit of the pack against Nuke's behaviour (the full list, with file and line for each finding, is in the
C2C workspace: `docs/evidence/L9.39/`):

- **Merge** follows Nuke's maths. The operation runs on alpha too, so `over` gives a + b(1 - a) where it used to
  give max(a, b). `minus` is now A - B, with the new `from` for B - A; `divide` is now A / B; `matte` is
  A·a + B(1 - a). The output takes B's format (A is resized to it), B's alpha is kept, nothing is clamped, and a
  connected mask no longer crashes. New: `invert_mask`, `conjoint_over`, `disjoint_over`, `geometric`.
  Workflows saved with `minus` or `divide` now get Nuke's result.
- **Premult / Unpremult** keep the alpha (`output` = rgba, the default; rgb for the old 3-channel result) and use
  the image's own alpha when no mask is connected. Not clamped.
- **Viewer** is an output node: it runs with nothing after it. `rgba` keeps alpha, luminance uses Rec.709 weights,
  M (`matte`) shows alpha as a red overlay. The IMAGE output is not clamped; only the preview is.
- **Color Space Convert (C2C):** sRGB -> ACEScg now uses the AP1 matrix (it was sRGB -> AP0), and alpha passes through.
- **Log2Lin** is Kodak Cineon (black / white / film gamma): code 1023 is about 13.5 linear, and it is not clamped.
- **LUTs:** `.3dl` (blue fastest) and `.spi3d` (indexed) tables are now read in the right order, so red and blue
  are no longer swapped. LUT Apply (C2C) keeps alpha.
- **ProRes / MP4 Write:** "MP4 (H.264)" writes real H.264 (it wrote MPEG-4 Part 2). 23.976 / 29.97 are exact
  rates. ProRes and H.264 are converted with the BT.709 matrix and tagged with it.
- **EXR:** channels are read by name (an R, G, B, Z render no longer gives Z as alpha). EXR Channel Router and Light
  Probe to EXR work through OpenImageIO.
- **HDR Tone Map:** new nodes start on their own settings (a preset overrides every setting). **STMap Identity /
  Invert** use pixel centres, like STMap Apply, so Identity -> Apply reproduces the image.

## Fixes 2026-10-24 (batch 2: linear float, Grade, Transform, channels)

- **No more hidden clamps.** About 40 colour operations clipped their result to 0-1 although the pack works in
  linear float: Multiply, Gamma, Invert, Dissolve, Keymix, Transform, Sharpen, Median, Add, Hue Shift, Despill,
  Defocus, Soften, Blur, Emboss, Bilateral, Z Defocus, Min/Max, Vignette, Channel Mixer, Reformat, Color Correct,
  Saturation, Glow, Erode/Dilate, the keyer's despilled colour, Shuffle, Pixel Aspect, Mocha warps, Grain Match, the
  flow warps and the sRGB / Rec.709 conversions. Values above 1 now survive. Mattes, masks and generators still clamp;
  use **Clamp** (or Grade's `white_clamp`) where you want 0-1. Exposure's `preserve_highlights` now defaults to on
  (older workflows keep the value they were saved with).
- **Grade** is Nuke's formula (`lift` was multiplied by `multiply` too). It has Nuke's `black_clamp` (on) and
  `white_clamp` (off), plus `reverse` (undo the grade) and `mix`. Gamma leaves values at or below 0 alone, and a mask
  of another size is resized instead of ignored.
- **Transform** no longer shears non-square frames when it rotates: a 30 px square rotated 45° on a 16:9 frame came
  out 58×32, now 42×42. Square frames give exactly the same result as before. New `invert`.
- **Shuffle:** `output` = rgba keeps the shuffled alpha in the image, and channels 5-8 (Ch4-Ch7) of multi-channel
  images can be picked. **Shuffle Latent** works on video latents (5-D) and keeps the noise mask; a wrong channel is
  an error instead of a silent clamp. **Copy** keeps B's channels beyond RGBA.
- **HDR Histogram** runs on its own (output node), `rgb` really shows R, G and B (it showed red only), and
  `axis = stops` plots exposure in stops around 18% grey over `stops_range`.
- **Mocha Invert Track** for corner pins is the real stabilising homography (it was a point reflection), and the
  corner-pin warp samples pixel centres (it was up to half a pixel off). The Mocha nodes no longer fail to import
  when the server is not up yet.
- **EXR Sequence Save with passes** writes each frame's own image as R, G, B, A next to the passes, uses per-frame
  passes by frame, and writes half floats when `oiio_bit_depth` is 16f.
- **Latent Frequency Match** works on video latents.

## Tests

The test suite stays on the developer's machine and is not in this repository (owner rule 2026-10-23). CI boots
ComfyUI with this pack and fails on an import failure, no registered node, or a traceback from the pack
(`.github/c2c_boot_check.py`).

## Notes

- `types_io.py` intentionally exposes empty mappings; types are registered by their owning category modules.
- All temporal nodes operate batch-first (B = T), no per-frame Python loops in the hot path.
- The dual-output discipline is enforced: classical VFX socket on the left, AI-consumable socket on the right, on every node where both are meaningful.
- Works inside subgraphs: each node's run status and plain-English error, NkScript copy / paste and the Mocha file drop all follow nodes that live inside (nested) subgraphs.

## License

GPL-3.0 (see `LICENSE`).

Relicensed from Apache-2.0 on 2026-09-19: the `NukeMax/HDR` family is a
port of [radiance](https://github.com/fxtdstudios/radiance), which
declares GPL-3.0. See `NOTICE.md` for the full provenance of every ported
family.
