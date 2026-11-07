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

**Shuffle Pass (NukeMax)** takes Read MultiPass's bundle (one frame), or CustomNodePacks' **Load Video (C2C)**
`exr_passes`. That one is a lazy bundle of every EXR layer over all the loaded frames, so Shuffle Pass gives the
chosen layer (depth, N, diffuse, ...) for the whole selection:
- raw float values, unclamped;
- layer names matched case-insensitively;
- a missing layer is black or refused, by `on_missing`.

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
- Serialize / Deserialize (fixed 2026-11-03): every custom type round-trips through workflow JSON, including Deep
  Image and the Mocha track, lens and project types. Before, their Deserialize nodes always failed.
- Transform (fixed 2026-11-03): a rotation with a centre, skew or per-axis scale set now rotates the picture. Before,
  it squashed the picture, collapsing it entirely at 45 degrees. With only a centre set, the result equals the plain
  path.
- Mocha transform tracks (fixed 2026-11-04): Apply Tracking moves the insert with the track (it moved it the opposite
  way), so Invert Track + Apply Tracking now stabilises a transform track as it already did for corner pins. The
  output mask shows where the warp has picture (it was all white), and an output size different from the source is
  handled. A track longer or shorter than the plate is used frame for frame and holds its last frame (it was
  stretched in time). Apply Lens with zero distortion leaves the image unchanged (the border was darkened).
- Text (fixed 2026-11-04) no longer clamps the plate, so a slate on an EXR keeps its highlights and negative values.
- Median (fixed 2026-11-04) works one frame at a time in row strips, so large sizes on HD/4K plates no longer run out
  of memory (size 8 on one 1080p frame needed about 7 GB). The result is unchanged.
- Merge screen (fixed 2026-11-04) follows Foundry's formula exactly: A+B-AB only where both A and B lie between 0
  and 1, otherwise the larger one. Negative (footroom) values used to blend.
- Sharpen and Median (fixed 2026-11-04) run on images smaller than their size (they raised a padding error).
  The same fix now covers every NukeMax filter that mirrors the image edge (2026-11-05): blurs, edge detect,
  flow, relight, plate tools and the rest repeat the edge where the image is too small to mirror.
- 2026-11-05: Corner Pin, and HistEQ in `clahe` mode, stop with an install message when opencv is missing (they
  returned the input, or ran global equalisation, without a word). Vignette with a negative amount no longer
  pulls values above 1.0 down. The Mocha file nodes re-run when the file is re-exported under the same name.
  HDR Exposure Blend's Laplacian Pyramid no longer leaks colour between channels.
- HDR Color Correct, Expand Dynamic Range, Tone Map, Shadow/Highlight Recovery and Highlight Synthesis
  (fixed 2026-11-05) leave alpha alone on an RGBA image (for example from Multipass Read in `rgba` mode).
  Before, exposure +1 doubled the alpha, and the tone map and saturation changed it too.
- Mocha Apply Tracking / Apply Lens and Defocus (fixed 2026-11-05) take half-precision images, and build their
  sampling grids and kernel on the image's device (a GPU image failed; the GPU case is not yet run here).
  Text's `size` works without Arial installed (most Linux systems ignored it).
- Difference and ZDefocus (fixed 2026-11-05) explain mismatched frame counts (same count, or one frame on one
  side); HDR Exposure Blend explains brackets of different sizes. Both used to fail with a raw tensor error.
- Contact Sheet has a new `tile_scale` input (last; 1.0 = as before) and stops with a message when the sheet does
  not fit in free memory. Mocha Apply Tracking: an output size of 0 uses the track's canvas, and a different
  size is reported in the log (the pins are in canvas pixels).
- HDR Histogram (2026-11-05) measures one frame at a time: same scope and numbers, much less memory
  (24 frames of 960x540: 748 MB extra before, 26 MB now).
- Defocus (2026-11-05) uses an FFT for sizes from 16: same picture, size 128 on a 1080p frame in 0.06 s (was 11.2 s, measured on this CPU).
- Mocha file nodes (2026-11-05): on a server reachable from other machines (`--listen`), the file must be inside
  the C2C media roots (input, output, temp, or a folder in `C2C_MEDIA_ROOTS` / `c2c_media_roots.txt`), as for
  C2C Load Video. A local server reads any path, as before.
- Constant and Text colours (fixed 2026-11-04): a mistyped hex colour such as `#ff00zz` now stops with a message.
  It used to turn black (or white) without a word.
- Deserialize (fixed 2026-11-04) refuses a payload of another type and names the node to use.
- Dissolve and Keymix (fixed 2026-11-04) accept an RGB B under an RGBA A (the missing alpha counts as 1). Different
  frame counts now get a plain message; a still plate with an animated mask still works. Grade's mask gets the
  same frame check.
- RGBA input (fixed 2026-11-06): Compute Optical Flow, Hair-Aware Choke, Sub-Pixel Edge Detect, Material
  Decomposer and Light Probe Estimator use the colour channels and no longer crash on an image with alpha.
- One-frame clips (fixed 2026-11-06): with no frame pair there is no motion, so the flow warps return the image
  unchanged and Flow Visualize / Occlusion Mask give one frame instead of none (the warps used to crash).
- Deep Flatten (fixed 2026-11-06) keeps HDR colour (a 3.0 pixel used to flatten to 1.0); only alpha is limited
  to 0..1. Clean Plate Extractor: a pixel masked out in every frame now takes the first frame's value, as
  documented, instead of turning infinite.
- Roto and Mocha shapes render about 900x faster (2026-11-07): a 1080p frame took 29-45 s on the CPU and now takes
  0.03-0.05 s, with the same mask values (checked against the old code on random, self-intersecting and off-canvas
  shapes, open and closed, every feather mode).
- Editors (Roto, and every panel built on the shared C2C UI): Ctrl+Shift+Z redoes again; Caps Lock no longer breaks
  Ctrl+Z (2026-11-07).
- Very small images (fixed 2026-11-06): an image 1, 3 or 4 pixels tall is no longer mistaken for channels-first data
  (FFT Texture Synthesis returned the wrong channel count; Hair-Aware Choke and Normal-Aware Edge Blur crashed).
- All temporal nodes operate batch-first (B = T), no per-frame Python loops in the hot path.
- The dual-output discipline is enforced: classical VFX socket on the left, AI-consumable socket on the right, on every node where both are meaningful.
- Works inside subgraphs: each node's run status and plain-English error, NkScript copy / paste and the Mocha file drop all follow nodes that live inside (nested) subgraphs.
- NkScript (Ctrl+Shift+C / V, NkScript Parse / Serialize) reads braced values as Nuke does: numbers are a list, words are text. It also took over ComfyUI-CustomNodePacks' TCL Parse / Serialize: saved ones load as the NkScript nodes.
- EXR Sequence Read / Write took over ComfyUI-CustomNodePacks' Load / Save EXR: `single_file` on Read and `file_path` on Write run that engine unchanged. That is OpenImageIO first, named AOV channels, compression, metadata, an alpha channel and an `info_json` output. Saved ones load as these nodes and write the same files (only OpenImageIO's write time stamp differs).

## Example workflow

`example_workflows/master_workflow.json`: EXR plate -> optical flow -> clean plate -> stabilise -> grain match -> EXR write. It uses only ComfyUI core and NukeMax nodes (EXR Sequence Read / Write), so it loads without any other pack (re-saved 2026-10-31; it used to need ComfyUI-CustomNodePacks' old Load / Save EXR).

## License

GPL-3.0 (see `LICENSE`).

Relicensed from Apache-2.0 on 2026-09-19: the `NukeMax/HDR` family is a
port of [radiance](https://github.com/fxtdstudios/radiance), which
declares GPL-3.0. See `NOTICE.md` for the full provenance of every ported
family.

## Vendored engine (2026-11-02)

`nukemax/vendor/c2c_core` is the C2C shared media engine (CustomNodePacks, Apache-2.0), copied byte for byte and
kept equal by the workspace sync and the pre-push gate. NukeMax's coming Read EXR Pro and the readers after it use it
for EXR, sequences, passes and safe server paths, the same engine as Load Video (C2C) and the MiniMax Suite (Rev 3
Part 19). Nothing changes for existing nodes. See `nukemax/vendor/VENDORED.md` and `NOTICE.md`.

## NukeMax Read EXR Pro (2026-11-02)

A production EXR reader (Rev 3 Part 19.4), not a typed path.

**Picking the file**
- *Upload EXR…*: one file, or every frame of a sequence (multi-select). The content is checked (EXR magic number),
  the name is cleaned, and the files are stored in `input/nukemax_exr/` as one batch.
  - An identical file is reused.
  - When a name is taken by a DIFFERENT file, the whole batch gets a version before the frame number
    (`shot_1.1001.exr`, `shot_1.1002.exr` …): a re-uploaded sequence stays a sequence, and nothing is overwritten.
- `mode`: *file*, *sequence* (the whole sequence from any one of its frames, with `frame_range` such as
  `1001-1100`), or *server path*. A server path is held to the C2C media roots when other machines can reach this
  server.
- `layer`: `auto` (RGB(A)) or a layer name.

**Outputs**
- scene-linear float, never clamped;
- the alpha as a MASK;
- every layer as `passes` for NukeMax Shuffle Pass;
- `metadata`: header, layers, sequence and value range;
- a preview made on the server, since browsers do not show EXR.

A changed file or sequence member re-runs the node.

It runs on the vendored C2C media engine, so it reads EXR exactly as Load Video (C2C) does.

**NukeMax EXR Metadata Reader Pro** (Part 19.5) reads an EXR's headers without decoding a pixel.
- Outputs: size, data and display windows, channels with their types, compression, parts, bit depth, colour
  information and timecode, as separate values and as JSON.
- A summary is shown on the node.

**NukeMax EXR Pass Reader** (Part 19.6) loads a multipart / multilayer EXR or its sequence.
- Outputs: the beauty, every pass as one bundle (NukeMax Shuffle Pass takes any of them), the pass names, and up to
  four named passes as their own outputs (`pass_1`…`pass_4`). Each is decoded only when named.

For uploaded files, every output names the input-relative file, never this machine's path.

## NukeMax Write EXR Pro (2026-11-02)

A safe EXR writer (Part 19.7). It takes the image (one frame or a sequence), an optional alpha, an optional pass bundle
(from Read EXR Pro or EXR Pass Reader) and optional metadata.

- **Never a silent overwrite.** By default every write goes into a new `name_v###/` folder and never touches an
  earlier version. With plain names, a write that would replace a file is refused and names the file; `overwrite`
  must be turned on to replace files.
- **Atomic.** A new version is written into a hidden folder and renamed into place whole. A replaced file is written
  beside the old one and renamed over it. A failed or interrupted write leaves no half version and no half file.
- **Formats:** half or float. Data passes (depth, position, normal, motion …) stay 32-bit float when the beauty is
  half. Values above 65504 cannot be stored in half; they are counted and reported, never hidden. Every OpenEXR
  compression is available, in single part (layers as channels) or multipart (one part per layer).
- **Frames:** `frame_start` + `padding`, `name.####.exr` or `name_####.exr`, or an explicit mapping
  (`1001-1010, 1020`, `1001-1019x2`).
- **Colour:** an optional OCIO conversion of the colour channels (data passes are never converted). The colour space
  is written in the header; OpenImageIO 3 stores its own interop id in `oiio:ColorSpace`, so the exact name is also
  kept in `nukemax:colourSpace`.
- **Metadata:** the source header (camera, owner, custom keys) is carried over; the frame rate comes from the
  metadata or the `fps` input.
- **Proof:** a manifest (files, frames, SHA-256, channels, colour, source) is returned and written as
  `<name>.manifest.json`. The node re-opens every file it wrote, checks its hash, and lists exactly those files on
  the node.

A relative `output_dir` lives inside ComfyUI's output folder. An absolute folder follows the readers' rule: any folder
on a server that only listens on this machine, only the C2C media roots on a server reachable from other machines.

## NukeMax Read (2026-11-02)

One reader for stills, numbered sequences and video (Part 19.8 / 19.9), on the same engine as Read EXR Pro.

- **Formats:** EXR, DPX, TIFF, PNG, JPEG, HDR, TGA, BMP, WebP, and the video containers PyAV opens (MOV, MP4, MKV,
  WebM, AVI, MXF). 16-bit TIFF / DPX keep their precision; EXR keeps values above 1.0, its alpha and its passes.
- **Sequences:** detected from one frame you pick, or written as a pattern (`shot.####.exr`, `shot.%04d.dpx`,
  `shot.$F4.png`). A frame range with a step (`1001-1100`, `1001-1100x2`) and a frame shift are available.
  - A gap is refused by default, naming the frame. You can choose to fill it black, hold the previous frame, use the
    nearest frame, or skip it.
  - A range reaching past the ends holds, goes black, loops, bounces or is refused.
- **Video:** frames count from 0, as Load Video (C2C) does. The `audio` output carries the clip's sound for the frames
  read (silence for stills and sequences).
- **Frame numbers:** `frame_numbers` gives them as a range string (`1001-1003, 1005-1007x2`). Write EXR Pro's
  `frame_numbers` reads that string, so the numbering survives a read → write round trip.
- **On the node:** a contact sheet of the range with frame numbers (one preview for a still), and the upload status.
- **Upload media…** takes one file, every frame of a sequence or a video. Files are streamed to disk, checked by their
  content and stored in `input/nukemax_media/`. A different file with the same name becomes a new version, never an
  overwrite. A server path is held to the C2C media roots on a server reachable from other machines.
- Optional OCIO conversion on read (`colour_space` → `convert_to`).

## NukeMax Write (2026-11-02)

One writer for stills, numbered sequences and movies (Part 19.8). It uses the same safety rules as Write EXR Pro:
versioned by default, never a silent overwrite, atomic, a manifest with SHA-256, and the exact files listed on the
node.

- **Formats:** only the ones this machine can write are offered.
  - Stills and sequences: EXR (handed to Write EXR Pro), DPX 8/10/12/16-bit, TIFF 8/16-bit or 32-bit float
    (none / lzw / zip), PNG 8/16-bit, JPEG with a quality setting.
  - Movies: ProRes 422 HQ (.mov), H.264 (.mp4), FFV1 lossless (.mkv). DNxHR, HEVC and ProRes 4444 will follow once
    the shared C2C writer supports them.
- **Honest output:** values outside 0..1 are clipped for the integer formats, and the clipped count is reported.
  JPEG and the movie codecs have no alpha; the node says so rather than dropping it silently. An odd size for H.264 or
  ProRes is refused in words.
- **Numbering:** `frame_start` + `padding`, or a mapping (connect NukeMax Read's `frame_numbers`). `frame_range`
  writes only a subset.
- **Movies:** the `audio` input is muxed in (connect NukeMax Read's `audio` to keep a clip's sound). The rate is exact
  (23.976 = 24000/1001). A new version is a new file, `name_v###.mov`.
- Optional OCIO conversion before writing; the colour space is recorded.

## NukeMax OCIO Config Manager (2026-11-02)

One active OCIO config for the graph (Part 19.10). Connect its `ocio_config` to any NukeMax OCIO node (Color
Transform, Display, Log Convert, Look Transform, Config Info): it wins over that node's own config choice, and the
node says so on its `config` field.

- **Sources:** the built-in ACES configs, `$OCIO`, a config in `models/ocio_configs/`, or any `.ocio` file
  (`config_file`).
- **Report** (on the node and as JSON): source, OCIO version, working space (role `scene_linear`), roles, colour
  spaces, displays and views, looks, the LUT formats this OCIO reads, and **missing LUTs**. Every colour space's and
  look's transforms are checked against the config's search path.
- **Reload:** a config edited on disk is read again on the next run, with no restart. "Reload config" empties the
  cache for every OCIO node.
- **Pick colour space…** on the OCIO nodes and on Read / Write lists the colour spaces (by family), roles,
  displays, views and looks of the node's own config, never a fixed list. The fields stay text, so a saved workflow
  keeps its values and a name from a show config is never refused.

All NukeMax OCIO nodes now load configs through this one cache.

## NukeMax OCIO Read / OCIO Write (2026-11-02)

Colour-managed I/O on NukeMax Read / Write and the OCIO Config Manager (Part 19.10).

- **OCIO Read** reads stills, sequences and video into the working space.
  - The source space is, in order: what you type; a space the file itself declares (NukeMax's own tag, or an EXR's
    colour space); or the config's file rules. The metadata says which one was used.
  - The working space is the one you type, or the config's `scene_linear` role.
  - Alpha is kept. Passes stay as stored, and the metadata says so.
  - The native `video` output carries the clip in its source space with its sound, for ComfyUI's own video nodes.
- **OCIO Write** writes an IMAGE or a native VIDEO (its frames, sound, rate and alpha).
  - It converts from the working space (or the input space you type) to the output space you type, or else to the
    config's file rule for that format. Then NukeMax Write writes it.
  - The config, both spaces and how each was chosen are recorded in the manifest sidecar.
- Measured live: an sRGB PNG read into ACEScg and written back matches the source to within 6e-8.

## Float / HDR path (2026-11-02)

Every NukeMax image node that runs without a model was measured on an HDR ramp (−0.5 … 4.0), looking for clamps to
0..1 and 8-bit hops (Part 19.11; the table is in the C2C workspace, `docs/evidence/L9.80/HDR_AUDIT.md`).

- **Fixed:**
  - Corner Pin and Bilateral no longer pass the image through 8-bit; highlights, negatives and precision survive.
  - Levels has a `clamp` toggle. On (the default) is the classic behaviour; off keeps HDR and negatives. Whites can be
    set above 1.0.
  - FFT Texture Synthesis keeps the example's own range.
- **Clamping on purpose:**
  - Grade's `black_clamp` (on by default, as in Nuke) and `white_clamp` (off).
  - Keyers, display transforms, tone mapping, posterize and ST maps output 0..1 by definition.
  - Hue Shift works in HSV, which has no negative values.
- **Measured live:** Read EXR Pro → Levels (clamp off) → Corner Pin → Bilateral → Write EXR Pro (float) keeps 3, 6
  and 9 exactly.
- **Stock ComfyUI:** VAE Decode clamps to 0..1 (`comfy/sd.py`), and Save / Preview Image write 8-bit. Use Write EXR
  Pro or NukeMax Write to keep float.

## NukeMax Viewer Pro (2026-11-02)

A viewer on the node (Part 19.12). **It views; it never processes.** Its output is its input, untouched. Exposure,
gamma, gain, channel and display change only what you see; they are saved with the workflow but never sent to the
graph. To bake a view into the output, press **Apply view to output**: it copies exposure, gamma and gain into the
node's inputs and turns `apply_view_adjustment` on. The panel says VIEW ONLY or APPLIED.

- **View:** Fit, 1:1 (one source pixel per screen pixel), zoom (wheel at the cursor), pan (drag), double-click to fit.
- **Channels:** RGB, R, G, B, A, luma. Alpha is shown over a checkerboard.
- **Adjust the view:** exposure in stops, gamma, gain; the display is sRGB or raw.
- **Exact values:** hovering shows the proxy value; a click returns the exact full-resolution value (HDR and
  negatives included).
- **Timeline:** first / previous / play / next / last, loop and scrub, with frame number, timecode, fps and duration.
  Frame numbers come from NukeMax Read or Read EXR Pro.
- **Frame info:** size, peak and floor values, and how many pixels are above 1.0 or below 0.
- **Performance:**
  - It writes float16 proxies (long side ≤ 960) and the full-resolution frames (for exact values) to ComfyUI's temp
    folder.
  - A disk budget (`NUKEMAX_VIEWER_CACHE_MB`, default 2048) removes the oldest stores first.
  - The browser keeps at most 64 frames.
- **Measure** (all of it view only):
  - Scopes: histogram, luma waveform, RGB parade, vectorscope, and the exposure distribution in stops from 18 % grey.
    Opening a scope makes room for it instead of shrinking the picture.
  - **False colour:** scene-linear luma in stops, nine bands, legend shown.
  - **Zebra:** stripes where the displayed value reaches 95 %.
  - **Focus peaking:** marks stay visible below 100 %.
  - **Shift-drag** a region: exact full-resolution min / max / mean, and the pixels above 1.0 and below 0.
  - Under the picture: peak luma, its stops over 18 % grey, the share above 1.0 and below 0, and the mean.
- **Compare** (connect `image_b`): A, B, A | B wipe (divider position adjustable), difference, difference heatmap
  (scaled to its own maximum, which is shown), blink.
- **EXR layers** (connect Read EXR Pro's `passes`): pick any layer to view (up to 8).
- **EXR inspector:** source, kind, size, data and display windows, compression, bit depth, colour, fps, every layer's
  channels and types, and the file header.
- **Sound** (connect a native `video`, or `audio`): it plays with the timeline, follows scrubbing, and can be muted.
- **OCIO Player:** the display picker lists the active config's displays and views. OCIO bakes the chosen one into a
  33³ LUT behind a log2 shaper (−12 … +12 stops), and the panel applies it. At 18 % grey it matches OCIO's own
  processor to 1e-4.

The older **Viewer (NukeMax)** is unchanged: its output carries its gain / gamma / channel. Use Viewer Pro when the
output must stay the input.

## NukeMax Handoff (Nuke / Resolve) (2026-11-03)

Hands rendered outputs to Nuke and DaVinci Resolve (Part 19.16). Writing an EXR is not a finished handoff: the node
first re-checks every file each writer manifest names (size and SHA-256). A changed or missing file stops it, named in
words, before anything is written.

- **Inputs:** up to four writer manifests (Write EXR Pro, Write, OCIO Write), the `ocio_config` socket, and shot facts
  (project, sequence, shot, artist, notes).
- **Package:** `nukemax_handoff/<name>_handoff_v###/`, versioned and written atomically.
  - `handoff.json`: for each output, its kind, pattern, frame range, fps, size, channels, pixel type, compression,
    colour interpretation and OCIO config. Also the shot facts and the tool versions.
  - `<name>.nk`: a Nuke script. The Root sets the frame range, fps, format and OCIO colour management (a built-in
    `ocio://` config needs Nuke 15 or later); there is one Read per output, with its colorspace.
  - `<name>.otio`: an OpenTimelineIO timeline. Resolve imports it with File > Import > Timeline.
  - `contact_sheet.png`: the first, middle and last frame of each output, read back from disk.
  - `ocio/`: a file-based OCIO config and its LUT folders, copied.
  - `README.txt`.
- **Checked here:** the `.otio` loads in OpenTimelineIO 0.18. The `.nk` has been checked for structure, but not yet
  opened in Nuke.

**Versions and ComfyUI's cache.** By default ComfyUI 0.39 re-runs every node on each queue: its RAM-pressure cache drops
the previous run's results. A versioned writer (Write EXR Pro, Write, Handoff) therefore writes a new version every
time you queue, as ComfyUI's own Save Image saves a new file. To reuse unchanged results, start ComfyUI with
`--cache-classic`. To replace instead of versioning, set `versioning` to plain names and turn `overwrite` on.

## Fixes 2026-11-02 (status line)

- A NukeMax node with no preview kept "running…" after the run. It now shows how long it ran.

## Fixes 2026-11-02 (saved widget values)

- On frontend 1.53, four NukeMax nodes (Audio Drive Mask, Audio Drive Schedule, PAR Resqueeze and the new Write EXR
  Pro) lost or shifted a widget value on every save → load and on Convert to Subgraph.
  - Cause: the status line under every NukeMax node was saved as an extra value. On a node with exactly one
    connection-only text input, that extra value made the frontend take the workflow for an old format and drop a
    real value.
  - Fixed: the status line is no longer saved, and a workflow saved before the fix loads with every value in its
    place.
  - Not recoverable: a workflow that was loaded and saved again while the bug was there was saved with the moved
    values. Check those four nodes in older workflows.
- An error on a NukeMax node now shows the node's own message, not a line of the Python traceback.
