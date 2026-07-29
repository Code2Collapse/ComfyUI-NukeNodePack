# NukeMax Nodes — Node Reference

*Auto-generated from the live `NODE_CLASS_MAPPINGS` on 2026-07-29 — 165 nodes. Every parameter description below is the node's own tooltip, so this file cannot drift from the code.*

Regenerate after changing any node's `INPUT_TYPES`.


## Contents

- **C2C/Color** (3)
  - [Color Space Convert (C2C)](#colorspaceconvertmec)
  - [Exposure Grade (C2C)](#exposuregrademec)
  - [LUT Apply (.cube) (C2C)](#lutapplymec)
- **C2C/Geometry** (3)
  - [Depth Warp (C2C)](#depthwarpmec)
  - [Normal → Curvature (C2C)](#normaltocurvaturemec)
  - [Position Pass Splitter (C2C)](#positionpasssplittermec)
- **C2C/IO** (3)
  - [EXR Metadata Reader (C2C)](#exrmetadatareadermec)
  - [Load EXR (C2C)](#loadexrmec)
  - [Save EXR (C2C)](#saveexrmec)
- **C2C/Metadata** (3)
  - [Frame Range Router (C2C)](#framerangeroutermec)
  - [Metadata Writer (C2C)](#metadatawritermec)
  - [Shot Metadata Reader (C2C)](#shotmetadatanodemec)
- **C2C/PlateTools** (4)
  - [Clean Plate Extractor (C2C)](#cleanplateextractormec)
  - [Difference Matte (C2C)](#differencemattemec)
  - [Grain Match (C2C)](#grainmatchmec)
  - [Plate Stabilizer (C2C)](#platestabilizermec)
- **C2C/Render** (2)
  - [Depth-of-Field Mask (C2C)](#depthoffieldmaskmec)
  - [Merge Render Passes (C2C)](#mergerenderpassesmec)
- **C2C/Utils** (1)
  - [Universal Reroute / Dot (NukeMax)](#universalreroutemec)
- **NukeMax/Audio** (5)
  - [Audio Drive Mask](#nukemax-audiodrivemask)
  - [Audio Drive Schedule](#nukemax-audiodriveschedule)
  - [Audio Load & Analyze](#nukemax-audioloadanalyze)
  - [Audio Spectrogram](#nukemax-audiospectrogram)
  - [Audio → Float Curve](#nukemax-audiotofloatcurve)
- **NukeMax/Channel** (2)
  - [Shuffle (NukeMax)](#nukemax-shuffleimage)
  - [Shuffle Latent (NukeMax)](#nukemax-shufflelatent)
- **NukeMax/Color** (18)
  - [Add (NukeMax)](#nukemax-add)
  - [ChannelMixer (NukeMax)](#nukemax-channelmixer)
  - [Clamp (NukeMax)](#nukemax-clamp)
  - [ClipTest (NukeMax)](#nukemax-cliptest)
  - [ColorCorrect (NukeMax)](#nukemax-colorcorrect)
  - [Exposure (NukeMax)](#nukemax-exposure)
  - [Gamma (NukeMax)](#nukemax-gamma)
  - [Grade (NukeMax)](#nukemax-grade)
  - [HistEQ (NukeMax)](#nukemax-histeq)
  - [HueShift (NukeMax)](#nukemax-hueshift)
  - [Invert (NukeMax)](#nukemax-invert)
  - [Log2Lin (NukeMax)](#nukemax-log2lin)
  - [Multiply (NukeMax)](#nukemax-multiply)
  - [OCIO Color Transform](#nukemax-ociocolortransform)
  - [OCIO Display (Nuke)](#nukemax-ociodisplay)
  - [OCIO Log Convert (Nuke)](#nukemax-ociologconvert)
  - [Posterize (NukeMax)](#nukemax-posterize)
  - [Saturation (NukeMax)](#nukemax-saturation)
- **NukeMax/Deep** (5)
  - [Deep Flatten (NukeMax)](#nukemax-deepflatten)
  - [Deep From Image (NukeMax)](#nukemax-deepfromimage)
  - [Deep Holdout (NukeMax)](#nukemax-deepholdout)
  - [Deep Merge (NukeMax)](#nukemax-deepmerge)
  - [Deep Recolor (NukeMax)](#nukemax-deeprecolor)
- **NukeMax/Edges** (4)
  - [Hair-Aware Choke](#nukemax-hairawarechoke)
  - [Matte Density Adjust](#nukemax-mattedensityadjust)
  - [Normal-Aware Edge Blur](#nukemax-normalawareedgeblur)
  - [Sub-Pixel Edge Detect](#nukemax-subpixeledgedetect)
- **NukeMax/FFT** (5)
  - [FFT Analyze](#nukemax-fftanalyze)
  - [FFT Synthesize](#nukemax-fftsynthesize)
  - [FFT Texture Synthesis](#nukemax-ffttexturesynthesis)
  - [Frequency Mask](#nukemax-frequencymask)
  - [Latent Frequency Match](#nukemax-latentfrequencymatch)
- **NukeMax/Filter** (12)
  - [Bilateral (NukeMax)](#nukemax-bilateral)
  - [Blur (NukeMax)](#nukemax-blur)
  - [Defocus (NukeMax)](#nukemax-defocus)
  - [EdgeDetect (NukeMax)](#nukemax-edgedetect)
  - [Emboss (NukeMax)](#nukemax-emboss)
  - [Erode/Dilate (NukeMax)](#nukemax-erodedilate)
  - [Glow (NukeMax)](#nukemax-glow)
  - [Median (NukeMax)](#nukemax-median)
  - [MinMax (NukeMax)](#nukemax-minmax)
  - [Sharpen (NukeMax)](#nukemax-sharpen)
  - [Soften (NukeMax)](#nukemax-soften)
  - [ZDefocus (NukeMax)](#nukemax-zdefocus)
- **NukeMax/Flow** (6)
  - [Clean Plate Merge](#nukemax-cleanplatemerge)
  - [Compute Optical Flow](#nukemax-computeopticalflow)
  - [Flow Backward Warp](#nukemax-flowbackwardwarp)
  - [Flow Forward Warp](#nukemax-flowforwardwarp)
  - [Flow Occlusion Mask](#nukemax-flowocclusionmask)
  - [Flow Visualize](#nukemax-flowvisualize)
- **NukeMax/Generate** (10)
  - [CheckerBoard (NukeMax)](#nukemax-checkerboard)
  - [ColorBars (NukeMax)](#nukemax-colorbars)
  - [Constant (NukeMax)](#nukemax-constant)
  - [Grid (NukeMax)](#nukemax-grid)
  - [Noise (NukeMax)](#nukemax-noise)
  - [Radial (NukeMax)](#nukemax-radial)
  - [Ramp (NukeMax)](#nukemax-ramp)
  - [Rectangle (NukeMax)](#nukemax-rectangle)
  - [Text (NukeMax)](#nukemax-text)
  - [Vignette (NukeMax)](#nukemax-vignette)
- **NukeMax/IO** (4)
  - [EXR Channel Router](#nukemax-exrchannelrouter)
  - [EXR Sequence Read (Nuke)](#nukemax-exrsequenceload)
  - [EXR Sequence Write (Nuke)](#nukemax-exrsequencesave)
  - [ProRes / MP4 Write](#nukemax-proressave)
- **NukeMax/IO/AUDIO_FEATURES** (2)
  - [Deserialize Audio Features](#nukemax-deserialize-audio-features)
  - [Serialize Audio Features](#nukemax-serialize-audio-features)
- **NukeMax/IO/DEEP_IMAGE** (2)
  - [Deserialize Deep Image](#nukemax-deserialize-deep-image)
  - [Serialize Deep Image](#nukemax-serialize-deep-image)
- **NukeMax/IO/FFT_TENSOR** (2)
  - [Deserialize Fft Tensor](#nukemax-deserialize-fft-tensor)
  - [Serialize Fft Tensor](#nukemax-serialize-fft-tensor)
- **NukeMax/IO/FLOW_FIELD** (2)
  - [Deserialize Flow Field](#nukemax-deserialize-flow-field)
  - [Serialize Flow Field](#nukemax-serialize-flow-field)
- **NukeMax/IO/LIGHT_PROBE** (2)
  - [Deserialize Light Probe](#nukemax-deserialize-light-probe)
  - [Serialize Light Probe](#nukemax-serialize-light-probe)
- **NukeMax/IO/LIGHT_RIG** (2)
  - [Deserialize Light Rig](#nukemax-deserialize-light-rig)
  - [Serialize Light Rig](#nukemax-serialize-light-rig)
- **NukeMax/IO/MATERIAL_SET** (2)
  - [Deserialize Material Set](#nukemax-deserialize-material-set)
  - [Serialize Material Set](#nukemax-serialize-material-set)
- **NukeMax/IO/MOCHA_LENS** (2)
  - [Deserialize Mocha Lens](#nukemax-deserialize-mocha-lens)
  - [Serialize Mocha Lens](#nukemax-serialize-mocha-lens)
- **NukeMax/IO/MOCHA_PROJECT** (2)
  - [Deserialize Mocha Project](#nukemax-deserialize-mocha-project)
  - [Serialize Mocha Project](#nukemax-serialize-mocha-project)
- **NukeMax/IO/MOCHA_TRACK** (2)
  - [Deserialize Mocha Track](#nukemax-deserialize-mocha-track)
  - [Serialize Mocha Track](#nukemax-serialize-mocha-track)
- **NukeMax/IO/ROTO_SHAPE** (2)
  - [Deserialize Roto Shape](#nukemax-deserialize-roto-shape)
  - [Serialize Roto Shape](#nukemax-serialize-roto-shape)
- **NukeMax/IO/TRACKING_DATA** (2)
  - [Deserialize Tracking Data](#nukemax-deserialize-tracking-data)
  - [Serialize Tracking Data](#nukemax-serialize-tracking-data)
- **NukeMax/Keying** (6)
  - [Chroma Keyer (NukeMax)](#nukemax-chromakeyer)
  - [Despill (NukeMax)](#nukemax-despill)
  - [Difference (NukeMax)](#nukemax-difference)
  - [Keyer (NukeMax)](#nukemax-keyer)
  - [Premult (NukeMax)](#nukemax-premult)
  - [Unpremult (NukeMax)](#nukemax-unpremult)
- **NukeMax/Lens** (3)
  - [STMap Apply (Lens Distortion)](#nukemax-stmapapply)
  - [STMap Identity](#nukemax-stmapidentity)
  - [STMap Invert](#nukemax-stmapinvert)
- **NukeMax/Merge** (4)
  - [Dissolve (NukeMax)](#nukemax-dissolve)
  - [Keymix (NukeMax)](#nukemax-keymix)
  - [Merge (NukeMax)](#nukemax-merge)
  - [Switch (NukeMax)](#nukemax-switch)
- **NukeMax/Mocha** (12)
  - [Mocha — Apply / Remove Lens Distortion](#nukemax-mochaapplylens)
  - [Mocha — Apply Tracking (Warp)](#nukemax-mochaapplytracking)
  - [Mocha — Import (Auto: paste / upload)](#nukemax-mochaimportauto)
  - [Mocha — Import Corner Pin (file path)](#nukemax-mochaimportcornerpin)
  - [Mocha — Import Corner Pin (paste / upload)](#nukemax-mochaimportcornerpinpaste)
  - [Mocha — Import Lens Calibration](#nukemax-mochaimportlens)
  - [Mocha — Open .mocha Project](#nukemax-mochaimportproject)
  - [Mocha — Import Shapes → MASK (file path)](#nukemax-mochaimportshapesasmask)
  - [Mocha — Import Shapes → MASK (paste / upload)](#nukemax-mochaimportshapesasmaskpaste)
  - [Mocha — Import Transform (file path)](#nukemax-mochaimporttransform)
  - [Mocha — Import Transform (paste / upload)](#nukemax-mochaimporttransformpaste)
  - [Mocha — Invert Track (Stabilize)](#nukemax-mochainverttrack)
- **NukeMax/NkScript** (2)
  - [NkScript Parse (NukeMax)](#nukemax-nkscriptparse)
  - [NkScript Serialize (NukeMax)](#nukemax-nkscriptserialize)
- **NukeMax/Relight** (6)
  - [Light Probe Estimator](#nukemax-lightprobeestimator)
  - [Light Probe → EXR](#nukemax-lightprobetoexr)
  - [Light Rig Builder](#nukemax-lightrigbuilder)
  - [Material Decomposer (Heuristic)](#nukemax-materialdecomposerheuristic)
  - [Material Decomposer (Models)](#nukemax-materialdecomposermodels)
  - [3-Point Relight](#nukemax-threepointrelight)
- **NukeMax/Roto** (7)
  - [Roto Keyframe Interp](#nukemax-rotokeyframeinterp)
  - [Roto Shape From File](#nukemax-rotoshapefromfile)
  - [Roto Shape Renderer](#nukemax-rotoshaperenderer)
  - [Roto Shape Stack](#nukemax-rotoshapestack)
  - [Roto Shape → AI Tracker](#nukemax-rotoshapetoaitracker)
  - [Roto Shape → Diffusion Guidance](#nukemax-rotoshapetodiffusionguidance)
  - [Roto Spline Editor](#nukemax-rotosplineeditor)
- **NukeMax/Transform** (11)
  - [AppendClip (NukeMax)](#nukemax-appendclip)
  - [ContactSheet (NukeMax)](#nukemax-contactsheet)
  - [CornerPin (NukeMax)](#nukemax-cornerpin)
  - [Crop (NukeMax)](#nukemax-crop)
  - [Mirror (NukeMax)](#nukemax-mirror)
  - [PAR Desqueeze (anamorphic → square px)](#nukemax-pardesqueeze)
  - [PAR Resqueeze (back to plate)](#nukemax-parresqueeze)
  - [Position (NukeMax)](#nukemax-position)
  - [Reformat (NukeMax)](#nukemax-reformat)
  - [Tile (NukeMax)](#nukemax-tile)
  - [Transform (NukeMax)](#nukemax-transform)


---

## C2C/Color


### ColorSpaceConvertMEC

**Shown in the menu as:** Color Space Convert (C2C)

Convert IMAGE between sRGB, linear, Rec.709, and ACEScg.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Image batch to convert. |
| `src_space` | choice: `srgb`, `linear`, `rec709`, `acescg` | default `"srgb"` | Color space the input image is encoded in. |
| `dst_space` | choice: `srgb`, `linear`, `rec709`, `acescg` | default `"linear"` | Color space to convert the image into. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | Image converted into the destination color space. |


### ExposureGradeMEC

**Shown in the menu as:** Exposure Grade (C2C)

Exposure (stops), WB (temp/tint), and contrast around a pivot.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Image batch to grade. |
| `exposure_stops` | `FLOAT` | default `0.0`, range -10.0…10.0, step 0.05 | Exposure adjustment in stops (linear multiply by 2**stops). |
| `temperature` | `FLOAT` | default `0.0`, range -100.0…100.0, step 1.0 | White-balance temperature; positive=warmer (more red, less blue). |
| `tint` | `FLOAT` | default `0.0`, range -100.0…100.0, step 1.0 | White-balance tint; positive=magenta, negative=green. |
| `contrast` | `FLOAT` | default `1.0`, range 0.0…4.0, step 0.05 | Contrast multiplier around the mid-grey pivot. |
| `pivot` | `FLOAT` | default `0.18`, range 0.001…0.999, step 0.001 | Mid-grey pivot for contrast (0.18 = scene-linear grey). |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `operate_in_linear` | `BOOLEAN` | default `True` | If True (recommended), input is treated as sRGB-encoded, linearized for the math, then re-encoded. If False, the math is done directly on the encoded values (legacy / display-referred). |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | Graded image clamped to [0,1]. |


### LUTApplyMEC

**Shown in the menu as:** LUT Apply (.cube) (C2C)

Apply a .cube LUT (Adobe format, 1D or 3D) with optional strength blend.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Image batch to grade. |
| `lut_path` | `STRING` | default `""` | Filesystem path to an Adobe .cube LUT (1D or 3D). |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `strength` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.01 | Blend factor between the original (0) and graded (1) image. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | LUT-graded image clamped to [0,1]. |
| 1 | `info_json` | `STRING` | JSON metadata describing LUT dim, size, and strength. |


---

## C2C/Geometry


### DepthWarpMEC

**Shown in the menu as:** Depth Warp (C2C)

Horizontal parallax warp driven by a depth pass.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Source image batch to warp horizontally. |
| `depth` | `IMAGE` |  | Depth pass (uses red channel); auto-resized to image. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `max_shift_pixels` | `FLOAT` | default `16.0`, range -512.0…512.0, step 0.5 | Maximum horizontal shift in pixels at depth==1; negative shifts the other eye. |
| `pivot` | `FLOAT` | default `0.5`, range 0.0…1.0, step 0.01 | Depth value mapped to zero shift (the convergence plane). |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | Image warped horizontally according to the depth pass. |


### NormalToCurvatureMEC

**Shown in the menu as:** Normal → Curvature (C2C)

Compute curvature mask from a tangent-space normal pass.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `normal` | `IMAGE` |  | Tangent-space normal pass (RGB encodes XYZ in [0,1]). |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `scale` | `FLOAT` | default `1.0`, range 0.1…32.0, step 0.1 | Multiplier on the divergence before remapping to [0,1]. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `curvature` | `MASK` | Curvature mask in [0,1]; 0.5 is flat, brighter is convex. |


### PositionPassSplitterMEC

**Shown in the menu as:** Position Pass Splitter (C2C)

Split position pass into X/Y/Z masks (auto- or manually-ranged).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `position` | `IMAGE` |  | World-position pass with XYZ encoded in RGB channels. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `auto_normalize` | `BOOLEAN` | default `True` | If true, use per-frame min/max for each axis instead of manual ranges. |
| `x_min` | `FLOAT` | default `0.0`, range -1000000.0…1000000.0 | Manual minimum X value when auto_normalize is off. |
| `x_max` | `FLOAT` | default `1.0`, range -1000000.0…1000000.0 | Manual maximum X value when auto_normalize is off. |
| `y_min` | `FLOAT` | default `0.0`, range -1000000.0…1000000.0 | Manual minimum Y value when auto_normalize is off. |
| `y_max` | `FLOAT` | default `1.0`, range -1000000.0…1000000.0 | Manual maximum Y value when auto_normalize is off. |
| `z_min` | `FLOAT` | default `0.0`, range -1000000.0…1000000.0 | Manual minimum Z value when auto_normalize is off. |
| `z_max` | `FLOAT` | default `1.0`, range -1000000.0…1000000.0 | Manual maximum Z value when auto_normalize is off. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `x_mask` | `MASK` | Normalized X-axis mask in [0,1]. |
| 1 | `y_mask` | `MASK` | Normalized Y-axis mask in [0,1]. |
| 2 | `z_mask` | `MASK` | Normalized Z-axis mask in [0,1]. |


---

## C2C/IO


### EXRMetadataReaderMEC

**Shown in the menu as:** EXR Metadata Reader (C2C)

Read OpenEXR header (compression, channels, custom attributes) without decoding pixels. Uses OpenEXR if installed, otherwise pure-Python parser.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `file_path` | `STRING` | default `""` | Absolute path to a .exr file. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `force_pure_python` | `BOOLEAN` | default `False` | Skip OpenEXR even if installed; useful for benchmarking. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `metadata_json` | `STRING` | Pretty-printed JSON of the EXR header attributes plus library/file info. |
| 1 | `width` | `INT` | Image width derived from dataWindow. |
| 2 | `height` | `INT` | Image height derived from dataWindow. |
| 3 | `channels_csv` | `STRING` | Comma-separated list of channel names found in the header. |


### LoadEXRMEC

**Shown in the menu as:** Load EXR (C2C)

Load EXR as scene-linear IMAGE. Tries OpenEXR → imageio.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `file_path` | `STRING` | default `""` | Absolute filesystem path to the EXR file to load. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | Loaded image as scene-linear IMAGE [1,H,W,3] float32. |
| 1 | `info_json` | `STRING` | JSON describing the backend used and basic file info. |


### SaveEXRMEC

**Shown in the menu as:** Save EXR (C2C)

Save IMAGE batch as EXR(s).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Image batch to write to disk as EXR. |
| `file_path` | `STRING` | default `""` | Absolute output path. Batches add _0001, _0002 suffixes. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `half_float` | `BOOLEAN` | default `True` | 16-bit half (smaller, recommended). |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `info_json` | `STRING` | JSON list of written frames with backend info and forward-slash paths. |


---

## C2C/Metadata


### FrameRangeRouterMEC

**Shown in the menu as:** Frame Range Router (C2C)

Slice a video batch by [start:end:step].


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `images` | `IMAGE` |  | Image batch to slice. |
| `start` | `INT` | default `0`, range -100000…100000 | Inclusive start frame index; negatives index from the end. |
| `end` | `INT` | default `-1`, range -100000…100000 | Exclusive end frame index; -1 means to the end of the batch. |
| `step` | `INT` | default `1`, range 1…1000 | Frame stride. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `mask` | `MASK` |  | Optional companion mask sliced with the same range/step. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `images` | `IMAGE` | Sliced image batch. |
| 1 | `mask` | `MASK` | Sliced mask batch (zeros if no mask provided). |
| 2 | `frame_count` | `INT` | Number of frames in the output batch. |


### MetadataWriterMEC

**Shown in the menu as:** Metadata Writer (C2C)

Write a JSON sidecar; pass the image through.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Image batch to pass through unchanged. |
| `sidecar_path` | `STRING` | default `""` | Filesystem path of the JSON sidecar to write. |
| `metadata_json` | `STRING` | default `"{}"`, multiline | JSON object to write into the sidecar. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `merge_existing` | `BOOLEAN` | default `False` | If true, merge over an existing sidecar instead of overwriting. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | Pass-through image batch. |
| 1 | `written_path` | `STRING` | Forward-slash path of the written sidecar. |


### ShotMetadataNodeMEC

**Shown in the menu as:** Shot Metadata Reader (C2C)

Read a shot.json descriptor; missing fields return empty defaults.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `shot_json_path` | `STRING` | default `""` | Filesystem path to a shot.json descriptor file. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `show` | `STRING` | Show name from the descriptor. |
| 1 | `shot` | `STRING` | Shot name from the descriptor. |
| 2 | `task` | `STRING` | Task name from the descriptor. |
| 3 | `frame_in` | `INT` | First frame of the shot. |
| 4 | `frame_out` | `INT` | Last frame of the shot. |
| 5 | `fps` | `FLOAT` | Frame rate of the shot. |
| 6 | `raw_json` | `STRING` | Raw shot JSON re-serialized for downstream nodes. |


---

## C2C/PlateTools


### CleanPlateExtractorMEC

**Shown in the menu as:** Clean Plate Extractor (C2C)

Median across a batch (with optional mask exclusion) → clean plate.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `images` | `IMAGE` |  | Image batch to median across. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `exclude_mask` | `MASK` |  | Pixels where mask>=0.5 are excluded from the median. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `clean_plate` | `IMAGE` | Single-frame clean plate computed as a per-pixel median. |


### DifferenceMatteMEC

**Shown in the menu as:** Difference Matte (C2C)

Difference matte: |a-b| → MASK with threshold + softness.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image_a` | `IMAGE` |  | Reference image (e.g. clean plate). |
| `image_b` | `IMAGE` |  | Comparison image; auto-resized to match image_a. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `metric` | choice: `l2`, `l1` | default `"l2"` | Per-pixel difference metric across RGB channels. |
| `threshold` | `FLOAT` | default `0.05`, range 0.0…1.0, step 0.001 | Difference value at which the mask is fully on. |
| `softness` | `FLOAT` | default `0.05`, range 0.0…1.0, step 0.001 | Soft transition width around the threshold (0=hard step). |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `mask` | `MASK` | Per-pixel difference mask in [0,1]. |


### GrainMatchMEC

**Shown in the menu as:** Grain Match (C2C)

Extract grain from a reference plate and re-apply it to target.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `reference` | `IMAGE` |  | Reference plate whose grain will be sampled. |
| `target` | `IMAGE` |  | Clean image batch to receive the matched grain. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `intensity` | `FLOAT` | default `1.0`, range 0.0…4.0, step 0.05 | Multiplier on the extracted grain before adding to the target. |
| `denoise_kernel` | `INT` | default `5`, range 3…15, step 2 | Box-filter kernel size used to estimate denoise(reference); odd values only. |
| `seed` | `INT` | default `0`, range 0…2147483647 | Seed controlling which reference frame is sampled per target frame. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | Target image batch with reference grain re-applied. |
| 1 | `info_json` | `STRING` | JSON metadata describing grain std and parameters used. |


### PlateStabilizerMEC

**Shown in the menu as:** Plate Stabilizer (C2C)

Stabilize a video batch to frame 0 via ORB+affine (cv2) or FFT translation.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `images` | `IMAGE` |  | Image batch to stabilize to its first frame. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `max_features` | `INT` | default `500`, range 50…5000, step 50 | Maximum ORB feature count when cv2 is available. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `images` | `IMAGE` | Stabilized image batch warped to frame 0. |
| 1 | `info_json` | `STRING` | JSON describing the backend and per-frame transform records. |


---

## C2C/Render


### DepthOfFieldMaskMEC

**Shown in the menu as:** Depth-of-Field Mask (C2C)

Convert depth pass → CoC mask (defocus alpha) and in-focus mask.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `depth` | `IMAGE` |  | Z-depth pass; 1 or 3 channels (R used by default). |
| `focus_distance` | `FLOAT` | default `0.5`, range 0.0…100.0, step 0.001 | Depth value at which the image is perfectly in focus. |
| `aperture` | `FLOAT` | default `0.1`, range 0.001…100.0, step 0.001 | Depth distance over which the CoC ramps from 0 to 1. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `invert` | `BOOLEAN` | default `False` | Invert the focus mask (1 = in focus, 0 = defocus). |
| `depth_channel` | choice: `R`, `G`, `B`, `luma` | default `"R"` | Which channel of the depth pass to read; 'luma' uses Rec.709 weights. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `coc_mask` | `MASK` | Defocus alpha mask (1=fully out of focus). |
| 1 | `in_focus_mask` | `MASK` | Complementary in-focus mask (1=in focus). |


### MergeRenderPassesMEC

**Shown in the menu as:** Merge Render Passes (C2C)

Composite beauty + auxiliary render passes.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `beauty` | `IMAGE` |  | Primary beauty/full-shaded render pass. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `diffuse` | `IMAGE` |  | Optional diffuse render pass added with diffuse_gain. |
| `specular` | `IMAGE` |  | Optional specular render pass added with specular_gain. |
| `emission` | `IMAGE` |  | Optional emission/self-illumination pass added with emission_gain. |
| `ao` | `IMAGE` |  | Optional ambient-occlusion pass multiplied into beauty. |
| `diffuse_gain` | `FLOAT` | default `0.0`, range -2.0…4.0, step 0.05 | Additive multiplier for the diffuse pass. |
| `specular_gain` | `FLOAT` | default `0.0`, range -2.0…4.0, step 0.05 | Additive multiplier for the specular pass. |
| `emission_gain` | `FLOAT` | default `1.0`, range 0.0…4.0, step 0.05 | Additive multiplier for the emission pass. |
| `ao_strength` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.01 | How strongly AO darkens the beauty pass (0=ignored, 1=full). |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | Composited image with beauty plus weighted auxiliary passes. |


---

## C2C/Utils


### UniversalRerouteMEC

**Shown in the menu as:** Universal Reroute / Dot (NukeMax)

Drop onto any connection to reroute it. Compact dot shape. Auto-adapts to IMAGE, LATENT, MASK, STRING, etc. Right-click → 'Remove Reroute (reconnect)' to dissolve.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `anything` | `*` |  | Any input value; the slot type adapts to whatever is connected. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `output` | `*` | Pass-through of the input value with matching type. |


---

## NukeMax/Audio


### NukeMax_AudioDriveMask

**Shown in the menu as:** Audio Drive Mask

Modulate a per-frame mask by an audio-driven float curve via intensity scaling, dilation, or feathering.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `mask` | `MASK` |  | Per-frame mask batch to modulate. |
| `curve` | `FLOAT` | **connection-only** | Per-frame float curve (e.g. from Audio To Float Curve). |
| `mode` | choice: `intensity`, `dilate`, `feather` |  | How the curve modulates the mask: brightness, morphological dilation, or Gaussian feather. |
| `amount` | `FLOAT` | default `1.0`, range 0.0…32.0 | Strength of the modulation. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `mask` | `MASK` | Mask modulated frame-by-frame by the curve. |


### NukeMax_AudioDriveSchedule

**Shown in the menu as:** Audio Drive Schedule

Map an audio float curve to a per-frame value schedule (e.g. CFG/denoise) and emit it as JSON plus the scaled curve.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `curve` | `FLOAT` | **connection-only** | Per-frame float curve to remap. |
| `min_value` | `FLOAT` | default `4.0`, range 0.0…100.0 | Schedule value when the curve is at 0. |
| `max_value` | `FLOAT` | default `12.0`, range 0.0…100.0 | Schedule value when the curve is at 1. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `schedule_json` | `STRING` | JSON-encoded list of per-frame schedule values. |
| 1 | `curve` | `FLOAT` | Per-frame schedule values as a float list. |


### NukeMax_AudioLoadAnalyze

**Shown in the menu as:** Audio Load & Analyze

Load an audio file and compute STFT magnitude, onset envelope, BPM, spectral centroid and RMS as AUDIO_FEATURES.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `path` | `STRING` | default `""` | Filesystem path to the audio file (wav/flac/mp3 if librosa is available). |
| `n_fft` | `INT` | default `2048`, range 256…16384 | FFT window size used for the STFT. |
| `hop_length` | `INT` | default `512`, range 64…4096 | STFT hop length in samples. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `audio` | `AUDIO_FEATURES` | Bundle of audio features (waveform, STFT, onsets, centroid, RMS). |
| 1 | `bpm` | `FLOAT` | Estimated tempo in beats per minute. |
| 2 | `info` | `STRING` | Human-readable summary string. |


### NukeMax_AudioSpectrogram

**Shown in the menu as:** Audio Spectrogram

Render an STFT magnitude spectrogram from AUDIO_FEATURES as an RGB image, optionally on a log magnitude scale.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `audio` | `AUDIO_FEATURES` |  | Audio feature bundle to visualize. |
| `log_scale` | `BOOLEAN` | default `True` | If true, display log10 magnitude; otherwise linear magnitude. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `spectrogram` | `IMAGE` | Greyscale RGB spectrogram image (frequency on Y, time on X). |


### NukeMax_AudioToFloatCurve

**Shown in the menu as:** Audio → Float Curve

Convert an audio feature band (bass/mid/treble/onsets/centroid/full) into a per-frame float curve and 1D viz mask.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `audio` | `AUDIO_FEATURES` |  | Audio feature bundle from Audio Load & Analyze. |
| `frame_count` | `INT` | default `60`, range 1…100000 | Length of the output curve in frames. |
| `fps` | `FLOAT` | default `30.0`, range 1.0…240.0 | Target frames-per-second for time-aligning the curve. |
| `band` | choice: `full`, `bass`, `mid`, `treble`, `onsets`, `centroid` |  | Which audio feature band to extract the curve from. |
| `smoothing` | `FLOAT` | default `0.0`, range 0.0…1.0, step 0.01 | Temporal Gaussian smoothing of the curve (0=none). |
| `gain` | `FLOAT` | default `1.0`, range 0.0…32.0 | Multiplier applied to the curve before clamping. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `curve` | `FLOAT` | Per-frame float curve normalized to [0,1]. |
| 1 | `curve_image_1d` | `MASK` | 1D mask visualization of the curve over time. |


---

## NukeMax/Channel


### NukeMax_ShuffleImage

**Shown in the menu as:** Shuffle (NukeMax)

Remap RGBA channels Nuke-style. Each output channel is picked from any source channel or a constant.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `out_R` | choice: `R`, `G`, `B`, `A`, `Lum`, `0`, `1`, `Inv_R`, … (+3) | default `"R"` | — |
| `out_G` | choice: `R`, `G`, `B`, `A`, `Lum`, `0`, `1`, `Inv_R`, … (+3) | default `"G"` | — |
| `out_B` | choice: `R`, `G`, `B`, `A`, `Lum`, `0`, `1`, `Inv_R`, … (+3) | default `"B"` | — |
| `out_A` | choice: `R`, `G`, `B`, `A`, `Lum`, `0`, `1`, `Inv_R`, … (+3) | default `"A"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |
| 1 | `alpha` | `MASK` | — |


### NukeMax_ShuffleLatent

**Shown in the menu as:** Shuffle Latent (NukeMax)

Remap latent channels by index. Use this to swap or zero out specific latent dimensions.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `latent` | `LATENT` |  | — |
| `mapping` | `STRING` | default `"0,1,2,3"` | Comma-separated source-channel indices (or 'z' for zero, 'o' for one) for each output channel. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `latent` | `LATENT` | — |


---

## NukeMax/Color


### NukeMax_Add

**Shown in the menu as:** Add (NukeMax)

Add a constant to RGB (per-channel optional). Lift.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `value` | `FLOAT` | default `0.0`, range -1.0…1.0, step 0.005 | — |
| `red` | `FLOAT` | default `0.0`, range -1.0…1.0, step 0.005 | — |
| `green` | `FLOAT` | default `0.0`, range -1.0…1.0, step 0.005 | — |
| `blue` | `FLOAT` | default `0.0`, range -1.0…1.0, step 0.005 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_ChannelMixer

**Shown in the menu as:** ChannelMixer (NukeMax)

RGB channel mixer — each output channel is a weighted sum of input R/G/B (e.g. B&W mix).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `rr` | `FLOAT` | default `1.0`, range -2.0…2.0, step 0.01 | — |
| `rg` | `FLOAT` | default `0.0`, range -2.0…2.0, step 0.01 | — |
| `rb` | `FLOAT` | default `0.0`, range -2.0…2.0, step 0.01 | — |
| `gr` | `FLOAT` | default `0.0`, range -2.0…2.0, step 0.01 | — |
| `gg` | `FLOAT` | default `1.0`, range -2.0…2.0, step 0.01 | — |
| `gb` | `FLOAT` | default `0.0`, range -2.0…2.0, step 0.01 | — |
| `br` | `FLOAT` | default `0.0`, range -2.0…2.0, step 0.01 | — |
| `bg` | `FLOAT` | default `0.0`, range -2.0…2.0, step 0.01 | — |
| `bb` | `FLOAT` | default `1.0`, range -2.0…2.0, step 0.01 | — |
| `monochrome` | `BOOLEAN` | default `False` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Clamp

**Shown in the menu as:** Clamp (NukeMax)

Clamp pixel values into a [minimum, maximum] range.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `minimum` | `FLOAT` | default `0.0`, range -10.0…10.0, step 0.01 | — |
| `maximum` | `FLOAT` | default `1.0`, range -10.0…10.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_ClipTest

**Shown in the menu as:** ClipTest (NukeMax)

Diagnostic: tint pixels below 'low' blue and above 'high' red (zebra over/under check).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `low` | `FLOAT` | default `0.0`, range 0.0…1.0, step 0.005 | — |
| `high` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.005 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_ColorCorrect

**Shown in the menu as:** ColorCorrect (NukeMax)

Nuke-style ColorCorrect: gain (multiply), offset (add), gamma, contrast (around mid-grey) and saturation, applied in that order.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `gain` | `FLOAT` | default `1.0`, range 0.0…10.0, step 0.01 | — |
| `offset` | `FLOAT` | default `0.0`, range -1.0…1.0, step 0.005 | — |
| `gamma` | `FLOAT` | default `1.0`, range 0.01…5.0, step 0.01 | — |
| `contrast` | `FLOAT` | default `1.0`, range 0.0…4.0, step 0.01 | — |
| `saturation` | `FLOAT` | default `1.0`, range 0.0…4.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Exposure

**Shown in the menu as:** Exposure (NukeMax)

Adjust exposure in stops (out = in * 2^stops).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `stops` | `FLOAT` | default `0.0`, range -10.0…10.0, step 0.1 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Gamma

**Shown in the menu as:** Gamma (NukeMax)

Apply gamma correction (out = in ^ (1/gamma)); >1 brightens mids.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `gamma` | `FLOAT` | default `1.0`, range 0.01…5.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Grade

**Shown in the menu as:** Grade (NukeMax)

Nuke Grade: per-channel blackpoint/whitepoint remap to lift/gain, then multiply, offset and gamma — the standard primary grade. out = ((in-bp)/(wp-bp) * (gain-lift) + lift) * multiply + offset, then ^(1/gamma).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `blackpoint` | `FLOAT` | default `0.0`, range -1.0…1.0, step 0.001 | — |
| `whitepoint` | `FLOAT` | default `1.0`, range 0.0…4.0, step 0.001 | — |
| `lift` | `FLOAT` | default `0.0`, range -1.0…1.0, step 0.001 | — |
| `gain` | `FLOAT` | default `1.0`, range 0.0…4.0, step 0.001 | — |
| `multiply` | `FLOAT` | default `1.0`, range 0.0…8.0, step 0.001 | — |
| `offset` | `FLOAT` | default `0.0`, range -1.0…1.0, step 0.001 | — |
| `gamma` | `FLOAT` | default `1.0`, range 0.01…5.0, step 0.01 | — |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `mask` | `MASK` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_HistEQ

**Shown in the menu as:** HistEQ (NukeMax)

Histogram equalisation / CLAHE on luma — boost local contrast (cv2 if available).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `mode` | choice: `global`, `clahe` |  | — |
| `clip_limit` | `FLOAT` | default `2.0`, range 0.5…16.0, step 0.5 | — |
| `mix` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_HueShift

**Shown in the menu as:** HueShift (NukeMax)

Rotate hue (degrees) and scale saturation/value (HSV).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `hue_degrees` | `FLOAT` | default `0.0`, range -180.0…180.0, step 1.0 | — |
| `saturation` | `FLOAT` | default `1.0`, range 0.0…4.0, step 0.01 | — |
| `value` | `FLOAT` | default `1.0`, range 0.0…4.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Invert

**Shown in the menu as:** Invert (NukeMax)

Invert RGB (1 - value). Alpha is preserved.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Log2Lin

**Shown in the menu as:** Log2Lin (NukeMax)

Convert between log and linear (Cineon-style) colour space.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `operation` | choice: `log2lin`, `lin2log` | default `"log2lin"` | — |
| `black` | `INT` | default `95`, range 0…1023 | — |
| `white` | `INT` | default `685`, range 0…1023 | — |
| `gamma` | `FLOAT` | default `0.6`, range 0.01…2.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Multiply

**Shown in the menu as:** Multiply (NukeMax)

Multiply RGB by a constant (per-channel optional). Linear gain.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `value` | `FLOAT` | default `1.0`, range 0.0…16.0, step 0.01 | — |
| `red` | `FLOAT` | default `1.0`, range 0.0…16.0, step 0.01 | — |
| `green` | `FLOAT` | default `1.0`, range 0.0…16.0, step 0.01 | — |
| `blue` | `FLOAT` | default `1.0`, range 0.0…16.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_OCIOColorTransform

**Shown in the menu as:** OCIO Color Transform

Industry-standard OpenColorIO v2 color transform. Drop config folders in ComfyUI/models/ocio_configs/ (or set $OCIO env var). Requires PyOpenColorIO. Float32 scene-linear preserved.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Source image. |
| `config` | choice: `builtin: ACES Studio (LogC3/C4, camera spaces)`, `builtin: ACES CG`, `builtin: OCIO default (ACES)` |  | OCIO config (drop in models/ocio_configs/ or set $OCIO). |
| `src_colorspace` | `STRING` | default `"ACES - ACES2065-1"` | Source colorspace name (must match config exactly). |
| `dst_colorspace` | `STRING` | default `"Output - sRGB"` | Destination colorspace name. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `list_spaces` | `BOOLEAN` | default `False` | If true, emit the available colorspaces in info_json and pass image through unchanged. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | Transformed IMAGE. |
| 1 | `info_json` | `STRING` | JSON with config path and applied transform. |


### NukeMax_OCIODisplay

**Shown in the menu as:** OCIO Display (Nuke)

Apply the config's display/view pipeline (e.g. sRGB / ACES SDR video) to a scene-referred image and bake it in — mirrors Nuke's OCIODisplay. Set list_options to see the available displays and views.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `config` | choice: `builtin: ACES Studio (LogC3/C4, camera spaces)`, `builtin: ACES CG`, `builtin: OCIO default (ACES)` |  | — |
| `input_colorspace` | `STRING` | default `"ACEScg"` | — |
| `display` | `STRING` | default `""` | Blank = config default display. |
| `view` | `STRING` | default `""` | Blank = default view for the display. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `invert` | `BOOLEAN` | default `False` | Display-referred back to input colorspace (roundtrips). |
| `list_options` | `BOOLEAN` | default `False` | Pass image through; emit displays/views in info_json. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |
| 1 | `info_json` | `STRING` | — |


### NukeMax_OCIOLogConvert

**Shown in the menu as:** OCIO Log Convert (Nuke)

Convert between the config's scene_linear and compositing_log roles (ACES: ACEScg ↔ ACEScct) — mirrors Nuke's OCIOLogConvert.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `config` | choice: `builtin: ACES Studio (LogC3/C4, camera spaces)`, `builtin: ACES CG`, `builtin: OCIO default (ACES)` |  | — |
| `operation` | choice: `log_to_linear`, `linear_to_log` | default `"log_to_linear"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Posterize

**Shown in the menu as:** Posterize (NukeMax)

Quantise each channel to N levels (banding / cel-shade).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `levels` | `INT` | default `8`, range 2…256 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Saturation

**Shown in the menu as:** Saturation (NukeMax)

Adjust saturation around Rec.709 luminance (0 = greyscale, 1 = unchanged, >1 = more saturated).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `saturation` | `FLOAT` | default `1.0`, range 0.0…4.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


---

## NukeMax/Deep


### NukeMax_DeepFlatten

**Shown in the menu as:** Deep Flatten (NukeMax)

Flatten a DEEP_IMAGE to a regular IMAGE + front-depth MASK using front-to-back over compositing.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `deep` | `DEEP_IMAGE` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |
| 1 | `depth` | `MASK` | — |


### NukeMax_DeepFromImage

**Shown in the menu as:** Deep From Image (NukeMax)

Build a single-sample DEEP_IMAGE from an IMAGE and a depth MASK (or alpha).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | RGB(A) source image batch. |
| `depth` | `MASK` |  | Per-pixel depth (lower = closer). |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `alpha` | `MASK` |  | Optional explicit alpha mask; otherwise IMAGE alpha is used. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `deep` | `DEEP_IMAGE` | — |


### NukeMax_DeepHoldout

**Shown in the menu as:** Deep Holdout (NukeMax)

Use the front-most opaque sample of `holdout` to mask all `subject` samples behind it (true deep holdout).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `subject` | `DEEP_IMAGE` |  | — |
| `holdout` | `DEEP_IMAGE` |  | — |
| `alpha_threshold` | `FLOAT` | default `0.5`, range 0.0…1.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `deep` | `DEEP_IMAGE` | — |


### NukeMax_DeepMerge

**Shown in the menu as:** Deep Merge (NukeMax)

Merge two DEEP_IMAGE streams sample-wise. Output keeps up to max_samples per pixel, sorted front-to-back.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `a` | `DEEP_IMAGE` |  | — |
| `b` | `DEEP_IMAGE` |  | — |
| `max_samples` | `INT` | default `8`, range 1…64 | Cap on samples kept per pixel after merge. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `deep` | `DEEP_IMAGE` | — |


### NukeMax_DeepRecolor

**Shown in the menu as:** Deep Recolor (NukeMax)

Tint samples deeper than (or shallower than) a Z threshold. Useful for atmospheric depth/fog passes.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `deep` | `DEEP_IMAGE` |  | — |
| `z_threshold` | `FLOAT` | default `0.5`, range 0.0…1000000.0, step 0.01 | — |
| `tint_r` | `FLOAT` | default `1.0`, range 0.0…4.0, step 0.01 | — |
| `tint_g` | `FLOAT` | default `1.0`, range 0.0…4.0, step 0.01 | — |
| `tint_b` | `FLOAT` | default `1.0`, range 0.0…4.0, step 0.01 | — |
| `mode` | choice: `deeper`, `shallower` |  | — |
| `amount` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `deep` | `DEEP_IMAGE` | — |


---

## NukeMax/Edges


### NukeMax_HairAwareChoke

**Shown in the menu as:** Hair-Aware Choke

Choke a matte adaptively, applying less choke in high-frequency 'hair' regions and more in smooth regions.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `mask` | `MASK` |  | Input matte to choke. |
| `image` | `IMAGE` |  | Companion image used to estimate hair-frequency energy. |
| `choke` | `FLOAT` | default `1.5`, range -8.0…8.0, step 0.1 | Choke amount; positive erodes, negative dilates, 0 is no-op. |
| `hair_window` | `INT` | default `5`, range 1…31 | Window size in pixels for the local std-dev hair detector. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `mask` | `MASK` | Hair-aware choked mask. |


### NukeMax_MatteDensityAdjust

**Shown in the menu as:** Matte Density Adjust

Adjust gamma and contrast only on the semi-transparent edge band of a matte; opaque and clear regions are preserved exactly.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `mask` | `MASK` |  | Input matte to adjust. |
| `gamma` | `FLOAT` | default `1.0`, range 0.05…8.0, step 0.01 | Gamma applied to the edge band; <1 darkens, >1 brightens. |
| `contrast` | `FLOAT` | default `1.0`, range 0.0…8.0, step 0.01 | Contrast multiplier around 0.5 for the edge band. |
| `edge_lo` | `FLOAT` | default `0.01`, range 0.0…0.5 | Lower alpha bound that defines the edge band. |
| `edge_hi` | `FLOAT` | default `0.99`, range 0.5…1.0 | Upper alpha bound that defines the edge band. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `mask` | `MASK` | Mask with adjusted edge density. |


### NukeMax_NormalAwareEdgeBlur

**Shown in the menu as:** Normal-Aware Edge Blur

Cross-bilateral mask blur gated by a normal map; smooths within surfaces while preserving normal discontinuities.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `mask` | `MASK` |  | Mask to blur. |
| `normal` | `IMAGE` |  | Normal map (0..1 RGB) used to gate the bilateral kernel. |
| `sigma` | `FLOAT` | default `4.0`, range 0.0…64.0, step 0.1 | Gaussian standard deviation in pixels. |
| `normal_threshold` | `FLOAT` | default `0.85`, range -1.0…1.0, step 0.01 | Minimum cosine similarity between normals for samples to contribute. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `mask` | `MASK` | Mask blurred only across surfaces with similar normals. |


### NukeMax_SubPixelEdgeDetect

**Shown in the menu as:** Sub-Pixel Edge Detect

Sobel edge detector with sub-pixel localization; emits an edge magnitude mask and the top-K edge points as tracking data.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Image batch to detect edges on. |
| `top_k` | `INT` | default `256`, range 1…4096 | Number of strongest edge points kept per frame as tracks. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `edges` | `MASK` | Per-pixel edge magnitude normalized to [0,1]. |
| 1 | `tracks` | `TRACKING_DATA` | Top-K edge point coordinates with confidence per frame. |


---

## NukeMax/FFT


### NukeMax_FFTAnalyze

**Shown in the menu as:** FFT Analyze

Compute the centered 2D FFT of an image batch and return its magnitude/phase as an FFT_TENSOR.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Image batch to transform into the frequency domain. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `fft` | `FFT_TENSOR` | FFT tensor bundle (magnitude, phase, original spatial size). |


### NukeMax_FFTSynthesize

**Shown in the menu as:** FFT Synthesize

Inverse-FFT an FFT_TENSOR back into an image batch.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `fft` | `FFT_TENSOR` |  | FFT tensor bundle to inverse-transform. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | Reconstructed image clamped to [0,1]. |


### NukeMax_FFTTextureSynthesis

**Shown in the menu as:** FFT Texture Synthesis

Synthesize a same-spectrum texture from an exemplar by cloning its magnitude and randomizing phase.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `exemplar` | `IMAGE` |  | Reference texture image whose spectrum is cloned. |
| `out_height` | `INT` | default `512`, range 16…4096 | Output texture height in pixels. |
| `out_width` | `INT` | default `512`, range 16…4096 | Output texture width in pixels. |
| `seed` | `INT` | default `0`, range 0…2147483647 | Random seed driving the synthesized phase. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | Synthesized texture image at the requested resolution. |


### NukeMax_FrequencyMask

**Shown in the menu as:** Frequency Mask

Apply a soft radial band-pass filter to an FFT_TENSOR, keeping frequencies between low and high.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `fft` | `FFT_TENSOR` |  | FFT tensor bundle to filter. |
| `low` | `FLOAT` | default `0.0`, range 0.0…0.5, step 0.005 | Inner radius of the pass band as a fraction of Nyquist. |
| `high` | `FLOAT` | default `0.5`, range 0.0…0.5, step 0.005 | Outer radius of the pass band as a fraction of Nyquist. |
| `softness` | `FLOAT` | default `0.02`, range 0.0…0.5, step 0.005 | Edge softness of the band-pass transition. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `fft` | `FFT_TENSOR` | Band-pass filtered FFT tensor bundle. |


### NukeMax_LatentFrequencyMatch

**Shown in the menu as:** Latent Frequency Match

Reshape a noise latent's ring-averaged frequency spectrum to match a context image while preserving phase.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `noise_latent` | `LATENT` |  | Source noise latent to be spectrum-corrected. |
| `context_image` | `IMAGE` |  | Reference image whose ring-averaged spectrum is the target. |
| `n_bins` | `INT` | default `64`, range 8…256 | Number of radial bins used to estimate the ring spectrum. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `latent` | `LATENT` | Latent whose spectrum is matched to the context image. |


---

## NukeMax/Filter


### NukeMax_Bilateral

**Shown in the menu as:** Bilateral (NukeMax)

Edge-preserving (bilateral) smoothing — clean noise while keeping edges crisp.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `size` | `INT` | default `5`, range 1…25 | — |
| `sigma_space` | `FLOAT` | default `4.0`, range 0.5…50.0, step 0.5 | — |
| `sigma_color` | `FLOAT` | default `0.1`, range 0.01…1.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Blur

**Shown in the menu as:** Blur (NukeMax)

Gaussian blur with independent horizontal / vertical size (Nuke Blur).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `size` | `FLOAT` | default `4.0`, range 0.0…256.0, step 0.5 | — |
| `aspect` | `FLOAT` | default `1.0`, range 0.05…20.0, step 0.05 | vertical = size, horizontal = size*aspect |
| `blur_alpha` | `BOOLEAN` | default `True` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Defocus

**Shown in the menu as:** Defocus (NukeMax)

Disc-bokeh defocus blur (circular kernel) — softer, rounder out-of-focus than gaussian.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `size` | `INT` | default `8`, range 1…128 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_EdgeDetect

**Shown in the menu as:** EdgeDetect (NukeMax)

Edge detection (Sobel / Prewitt / Laplacian / Roberts) on luma → matte.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `operator` | choice: `sobel`, `prewitt`, `laplacian`, `roberts` |  | — |
| `gain` | `FLOAT` | default `1.0`, range 0.0…16.0, step 0.1 | — |
| `colored` | `BOOLEAN` | default `False` | Per-channel edges instead of luma. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |
| 1 | `mask` | `MASK` | — |


### NukeMax_Emboss

**Shown in the menu as:** Emboss (NukeMax)

Directional emboss (relief) filter.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `angle` | `FLOAT` | default `135.0`, range 0.0…360.0, step 5.0 | — |
| `amount` | `FLOAT` | default `1.0`, range 0.0…5.0, step 0.1 | — |
| `grey` | `BOOLEAN` | default `True` | Bias to mid-grey like a classic emboss. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_ErodeDilate

**Shown in the menu as:** Erode/Dilate (NukeMax)

Morphological erode/dilate. Negative size erodes (shrinks bright/matte regions), positive dilates (grows them).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `size` | `INT` | default `0`, range -64…64 | Pixels: negative = erode, positive = dilate, 0 = passthrough. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Glow

**Shown in the menu as:** Glow (NukeMax)

Bloom/Glow: isolate pixels above a brightness threshold, blur them, and add the halo back over the image.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `threshold` | `FLOAT` | default `0.7`, range 0.0…1.0, step 0.01 | — |
| `size` | `INT` | default `12`, range 1…256 | Glow radius in pixels. |
| `intensity` | `FLOAT` | default `1.0`, range 0.0…5.0, step 0.05 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Median

**Shown in the menu as:** Median (NukeMax)

Median filter (salt-and-pepper / grain denoise). size = window radius.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `size` | `INT` | default `1`, range 1…8 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_MinMax

**Shown in the menu as:** MinMax (NukeMax)

Morphological min / max / range filter (grow or shrink bright regions).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `operation` | choice: `max (dilate)`, `min (erode)`, `range` |  | — |
| `size` | `INT` | default `3`, range 1…49 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Sharpen

**Shown in the menu as:** Sharpen (NukeMax)

Unsharp-mask sharpen: amount * (image - blurred), added back.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `amount` | `FLOAT` | default `1.0`, range 0.0…8.0, step 0.05 | — |
| `size` | `INT` | default `3`, range 1…64 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Soften

**Shown in the menu as:** Soften (NukeMax)

Gentle gaussian soften (mix of blurred + original).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `size` | `INT` | default `3`, range 1…64 | — |
| `amount` | `FLOAT` | default `0.5`, range 0.0…1.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_ZDefocus

**Shown in the menu as:** ZDefocus (NukeMax)

Depth-driven defocus — blur scales with distance from the focal plane (a depth map drives it).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `depth` | `IMAGE` |  | Depth map (0=near .. 1=far). Luma is used. |
| `focus_depth` | `FLOAT` | default `0.5`, range 0.0…1.0, step 0.01 | — |
| `max_blur` | `FLOAT` | default `24.0`, range 0.0…128.0, step 1.0 | — |
| `layers` | `INT` | default `6`, range 2…16 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


---

## NukeMax/Flow


### NukeMax_CleanPlateMerge

**Shown in the menu as:** Clean Plate Merge

Warp a clean plate along the flow chain and merge it under the object mask to remove a moving object from footage.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `footage` | `IMAGE` |  | Original footage batch containing the unwanted object. |
| `clean_plate` | `IMAGE` |  | Clean reference plate (single frame or batch) to warp into the hole. |
| `object_mask` | `MASK` |  | Mask covering the object to remove (1=replace with plate). |
| `flow` | `FLOW_FIELD` |  | Flow field bundle used to align the plate to each frame. |
| `feather_px` | `FLOAT` | default `4.0`, range 0.0…64.0 | Gaussian feather radius in pixels applied to the object mask edge. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | Clean composite with the masked object replaced by the warped plate. |


### NukeMax_ComputeOpticalFlow

**Shown in the menu as:** Compute Optical Flow

Compute forward and backward optical flow plus a forward-backward consistency occlusion mask for an image batch.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `frames` | `IMAGE` |  | Image batch (sequential frames) to compute optical flow on. |
| `method` | choice: `auto`, `torch_lk`, `opencv_farneback` |  | Flow algorithm: auto picks OpenCV Farneback if available, else torch LK. |
| `consistency_threshold` | `FLOAT` | default `1.5`, range 0.0…32.0, step 0.1 | Pixel error threshold for forward-backward consistency check used to flag occlusions. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `flow` | `FLOW_FIELD` | Flow field bundle containing forward flow, backward flow, and forward occlusion mask. |


### NukeMax_FlowBackwardWarp

**Shown in the menu as:** Flow Backward Warp

Backward-warp an image batch using a precomputed flow field in either the forward or backward direction.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Source image batch to warp. |
| `flow` | `FLOW_FIELD` |  | Flow field bundle from Compute Optical Flow. |
| `direction` | choice: `forward`, `backward` |  | Which flow vector to use for the backward warp. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `warped` | `IMAGE` | Image batch resampled by the chosen flow direction. |


### NukeMax_FlowForwardWarp

**Shown in the menu as:** Flow Forward Warp

Splat-style forward warp of an image batch using the forward flow; also returns the splat weight as a mask.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Source image batch to splat-forward. |
| `flow` | `FLOW_FIELD` |  | Flow field bundle from Compute Optical Flow. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `warped` | `IMAGE` | Forward-warped image, normalized by accumulated splat weight. |
| 1 | `weight` | `MASK` | Per-pixel splat coverage (0=no contribution, 1=full). |


### NukeMax_FlowOcclusionMask

**Shown in the menu as:** Flow Occlusion Mask

Extract the occlusion mask from a flow bundle, computing it from forward-backward consistency if missing.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `flow` | `FLOW_FIELD` |  | Flow field bundle from Compute Optical Flow. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `occlusion` | `MASK` | Per-pixel forward-flow occlusion mask (1=occluded/inconsistent). |


### NukeMax_FlowVisualize

**Shown in the menu as:** Flow Visualize

Render a Middlebury-style HSV color visualization of the forward flow vectors.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `flow` | `FLOW_FIELD` |  | Flow field bundle from Compute Optical Flow. |
| `max_magnitude` | `FLOAT` | default `32.0`, range 0.5…1024.0 | Pixel magnitude that maps to full saturation in the visualization. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | RGB image visualizing flow direction (hue) and magnitude (saturation). |


---

## NukeMax/Generate


### NukeMax_CheckerBoard

**Shown in the menu as:** CheckerBoard (NukeMax)

Generate a checkerboard test pattern (size = square size in px).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `width` | `INT` | default `1920`, range 1…16384 | — |
| `height` | `INT` | default `1080`, range 1…16384 | — |
| `size` | `INT` | default `64`, range 1…2048 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_ColorBars

**Shown in the menu as:** ColorBars (NukeMax)

Generate SMPTE-style vertical colour bars.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `width` | `INT` | default `1920`, range 8…16384 | — |
| `height` | `INT` | default `1080`, range 8…16384 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Constant

**Shown in the menu as:** Constant (NukeMax)

Generate a solid-colour image at a chosen resolution.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `width` | `INT` | default `1920`, range 1…16384 | — |
| `height` | `INT` | default `1080`, range 1…16384 | — |
| `color` | `STRING` | default `"#000000"` | — |
| `batch` | `INT` | default `1`, range 1…64 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Grid

**Shown in the menu as:** Grid (NukeMax)

Generate a grid / graph-paper pattern (line spacing, width, colours).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `width` | `INT` | default `1024`, range 8…16384 | — |
| `height` | `INT` | default `1024`, range 8…16384 | — |
| `spacing` | `INT` | default `64`, range 2…4096 | — |
| `line_width` | `INT` | default `1`, range 1…64 | — |
| `line_color` | `STRING` | default `"#808080"` | — |
| `bg_color` | `STRING` | default `"#000000"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Noise

**Shown in the menu as:** Noise (NukeMax)

Generate uniform/fractal noise (greyscale or RGB), seeded.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `width` | `INT` | default `1024`, range 1…16384 | — |
| `height` | `INT` | default `1024`, range 1…16384 | — |
| `type` | choice: `greyscale`, `rgb` | default `"greyscale"` | — |
| `seed` | `INT` | default `0`, range 0…2147483647 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Radial

**Shown in the menu as:** Radial (NukeMax)

Generate a radial gradient (centre -> edge) — soft vignette / falloff source.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `width` | `INT` | default `1024`, range 8…16384 | — |
| `height` | `INT` | default `1024`, range 8…16384 | — |
| `radius` | `FLOAT` | default `0.5`, range 0.01…2.0, step 0.01 | — |
| `invert` | `BOOLEAN` | default `False` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Ramp

**Shown in the menu as:** Ramp (NukeMax)

Generate a linear gradient ramp (horizontal/vertical) between two values.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `width` | `INT` | default `1920`, range 8…16384 | — |
| `height` | `INT` | default `1080`, range 8…16384 | — |
| `direction` | choice: `horizontal`, `vertical` | default `"horizontal"` | — |
| `start` | `FLOAT` | default `0.0`, range 0.0…1.0, step 0.01 | — |
| `end` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Rectangle

**Shown in the menu as:** Rectangle (NukeMax)

Generate a filled rectangle on black (normalised x,y,w,h) — a quick garbage-matte / mask source.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `width` | `INT` | default `1024`, range 8…16384 | — |
| `height` | `INT` | default `1024`, range 8…16384 | — |
| `x` | `FLOAT` | default `0.25`, range 0.0…1.0, step 0.005 | — |
| `y` | `FLOAT` | default `0.25`, range 0.0…1.0, step 0.005 | — |
| `w` | `FLOAT` | default `0.5`, range 0.0…1.0, step 0.005 | — |
| `h` | `FLOAT` | default `0.5`, range 0.0…1.0, step 0.005 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |
| 1 | `mask` | `MASK` | — |


### NukeMax_Text

**Shown in the menu as:** Text (NukeMax)

Burn text onto the image (slate / annotation). Uses PIL if available.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `text` | `STRING` | default `"NukeMax"`, multiline | — |
| `size` | `INT` | default `48`, range 4…1024 | — |
| `x` | `FLOAT` | default `0.05`, range 0.0…1.0, step 0.005 | — |
| `y` | `FLOAT` | default `0.05`, range 0.0…1.0, step 0.005 | — |
| `color` | `STRING` | default `"#ffffff"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |
| 1 | `mask` | `MASK` | — |


### NukeMax_Vignette

**Shown in the menu as:** Vignette (NukeMax)

Radial vignette — darken (or brighten) toward the frame edges.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `amount` | `FLOAT` | default `0.5`, range -1.0…1.0, step 0.01 | — |
| `radius` | `FLOAT` | default `0.75`, range 0.05…2.0, step 0.01 | — |
| `softness` | `FLOAT` | default `0.5`, range 0.01…2.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


---

## NukeMax/IO


### NukeMax_EXRChannelRouter

**Shown in the menu as:** EXR Channel Router

Load a multilayer EXR and auto-route common AOVs into separate outputs: beauty IMAGE, raw depth IMAGE, normalized depth MASK, normal IMAGE, position IMAGE, motion IMAGE, plus a custom CSV channel pick. Float32 scene-linear; never clamps.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `file_path` | `STRING` | default `""` | Absolute path to a multilayer EXR. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `custom_channels_csv` | `STRING` | default `""` | Comma-separated channel names to pack into the 'custom' IMAGE (e.g. 'albedo.R,albedo.G,albedo.B'). |
| `depth_channel` | `STRING` | default `"Z"` | Channel name to treat as depth (default 'Z'). |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `beauty` | `IMAGE` | Beauty RGB. |
| 1 | `depth_raw` | `IMAGE` | Raw depth (Z) replicated to RGB (float, unbounded). |
| 2 | `depth_norm` | `MASK` | Linearly normalized depth MASK in [0,1] (for previews). |
| 3 | `normal` | `IMAGE` | Surface normal vector (N.x/N.y/N.z -> RGB). |
| 4 | `position` | `IMAGE` | World position (P.x/P.y/P.z -> RGB). |
| 5 | `motion` | `IMAGE` | Motion vector (motion.x/motion.y -> RG, B=0). |
| 6 | `custom` | `IMAGE` | Custom CSV channels (3-channel) — empty if unspecified. |
| 7 | `info_json` | `STRING` | JSON with full channel list and per-AOV resolution. |


### NukeMax_EXRSequenceLoad

**Shown in the menu as:** EXR Sequence Read (Nuke)

Nuke Read: load an EXR sequence (render.####.exr, %04d, or any frame file of the sequence) or a single EXR. Missing frames can error, insert black, or hold the previous frame.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `path` | `STRING` | default `""` | Any frame of the sequence, a ####/%04d pattern, or a single .exr |
| `missing_frames` | choice: `error`, `black`, `hold` | default `"error"` | — |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `start_frame` | `INT` | default `-1`, range -1…10000000 | -1 = first detected frame |
| `end_frame` | `INT` | default `-1`, range -1…10000000 | -1 = last detected frame |
| `every_nth` | `INT` | default `1`, range 1…1000 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |
| 1 | `frame_count` | `INT` | — |
| 2 | `width` | `INT` | — |
| 3 | `height` | `INT` | — |


### NukeMax_EXRSequenceSave

**Shown in the menu as:** EXR Sequence Write (Nuke)

Nuke Write: save an IMAGE batch as an EXR sequence (filename %04d → frame numbers) — half/float, all standard compressions.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `output_dir` | `STRING` | default `"output/exr"` | — |
| `filename` | `STRING` | default `"render_%04d"` | %04d is replaced by the frame number |
| `bit_depth` | choice: `16f (half-float)`, `32f (float)` | default `"16f (half-float)"` | — |
| `compression` | choice: `ZIP  (lossless, recommended)`, `ZIPS (lossless, scanline)`, `PIZ  (lossless, wavelet)`, `PXR24 (lossy, 24-bit)`, `RLE  (lossless, run-length)`, `B44  (lossy, fixed ratio)`, `DWAA (lossy, DCT, fast)`, `None (uncompressed)` | default `"ZIP  (lossless, recommended)"` | — |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `start_frame` | `INT` | default `1`, range 0…10000000 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |
| 1 | `last_path` | `STRING` | — |


### NukeMax_ProResSave

**Shown in the menu as:** ProRes / MP4 Write

Export an IMAGE batch as Apple ProRes MOV (422 / 422 HQ / 4444 / 4444 XQ via PyAV prores_ks; 4444 keeps alpha on RGBA input) or H.264 MP4.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `images` | `IMAGE` |  | — |
| `output_dir` | `STRING` | default `"output/mov"` | — |
| `filename` | `STRING` | default `"output"` | — |
| `format` | choice: `MOV ProRes 4444`, `MOV ProRes 4444 XQ`, `MOV ProRes 422 HQ`, `MOV ProRes 422`, `MP4 (H.264)` | default `"MOV ProRes 4444"` | — |
| `fps` | `FLOAT` | default `24.0`, range 1.0…120.0, step 0.5 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `images` | `IMAGE` | — |
| 1 | `saved_path` | `STRING` | — |


---

## NukeMax/IO/AUDIO_FEATURES


### NukeMax_Deserialize_AUDIO_FEATURES

**Shown in the menu as:** Deserialize Audio Features


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `payload` | `STRING` | default `""`, multiline | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `obj` | `AUDIO_FEATURES` | — |


### NukeMax_Serialize_AUDIO_FEATURES

**Shown in the menu as:** Serialize Audio Features


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `obj` | `AUDIO_FEATURES` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `payload` | `STRING` | — |


---

## NukeMax/IO/DEEP_IMAGE


### NukeMax_Deserialize_DEEP_IMAGE

**Shown in the menu as:** Deserialize Deep Image


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `payload` | `STRING` | default `""`, multiline | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `obj` | `DEEP_IMAGE` | — |


### NukeMax_Serialize_DEEP_IMAGE

**Shown in the menu as:** Serialize Deep Image


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `obj` | `DEEP_IMAGE` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `payload` | `STRING` | — |


---

## NukeMax/IO/FFT_TENSOR


### NukeMax_Deserialize_FFT_TENSOR

**Shown in the menu as:** Deserialize Fft Tensor


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `payload` | `STRING` | default `""`, multiline | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `obj` | `FFT_TENSOR` | — |


### NukeMax_Serialize_FFT_TENSOR

**Shown in the menu as:** Serialize Fft Tensor


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `obj` | `FFT_TENSOR` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `payload` | `STRING` | — |


---

## NukeMax/IO/FLOW_FIELD


### NukeMax_Deserialize_FLOW_FIELD

**Shown in the menu as:** Deserialize Flow Field


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `payload` | `STRING` | default `""`, multiline | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `obj` | `FLOW_FIELD` | — |


### NukeMax_Serialize_FLOW_FIELD

**Shown in the menu as:** Serialize Flow Field


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `obj` | `FLOW_FIELD` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `payload` | `STRING` | — |


---

## NukeMax/IO/LIGHT_PROBE


### NukeMax_Deserialize_LIGHT_PROBE

**Shown in the menu as:** Deserialize Light Probe


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `payload` | `STRING` | default `""`, multiline | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `obj` | `LIGHT_PROBE` | — |


### NukeMax_Serialize_LIGHT_PROBE

**Shown in the menu as:** Serialize Light Probe


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `obj` | `LIGHT_PROBE` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `payload` | `STRING` | — |


---

## NukeMax/IO/LIGHT_RIG


### NukeMax_Deserialize_LIGHT_RIG

**Shown in the menu as:** Deserialize Light Rig


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `payload` | `STRING` | default `""`, multiline | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `obj` | `LIGHT_RIG` | — |


### NukeMax_Serialize_LIGHT_RIG

**Shown in the menu as:** Serialize Light Rig


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `obj` | `LIGHT_RIG` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `payload` | `STRING` | — |


---

## NukeMax/IO/MATERIAL_SET


### NukeMax_Deserialize_MATERIAL_SET

**Shown in the menu as:** Deserialize Material Set


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `payload` | `STRING` | default `""`, multiline | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `obj` | `MATERIAL_SET` | — |


### NukeMax_Serialize_MATERIAL_SET

**Shown in the menu as:** Serialize Material Set


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `obj` | `MATERIAL_SET` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `payload` | `STRING` | — |


---

## NukeMax/IO/MOCHA_LENS


### NukeMax_Deserialize_MOCHA_LENS

**Shown in the menu as:** Deserialize Mocha Lens


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `payload` | `STRING` | default `""`, multiline | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `obj` | `MOCHA_LENS` | — |


### NukeMax_Serialize_MOCHA_LENS

**Shown in the menu as:** Serialize Mocha Lens


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `obj` | `MOCHA_LENS` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `payload` | `STRING` | — |


---

## NukeMax/IO/MOCHA_PROJECT


### NukeMax_Deserialize_MOCHA_PROJECT

**Shown in the menu as:** Deserialize Mocha Project


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `payload` | `STRING` | default `""`, multiline | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `obj` | `MOCHA_PROJECT` | — |


### NukeMax_Serialize_MOCHA_PROJECT

**Shown in the menu as:** Serialize Mocha Project


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `obj` | `MOCHA_PROJECT` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `payload` | `STRING` | — |


---

## NukeMax/IO/MOCHA_TRACK


### NukeMax_Deserialize_MOCHA_TRACK

**Shown in the menu as:** Deserialize Mocha Track


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `payload` | `STRING` | default `""`, multiline | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `obj` | `MOCHA_TRACK` | — |


### NukeMax_Serialize_MOCHA_TRACK

**Shown in the menu as:** Serialize Mocha Track


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `obj` | `MOCHA_TRACK` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `payload` | `STRING` | — |


---

## NukeMax/IO/ROTO_SHAPE


### NukeMax_Deserialize_ROTO_SHAPE

**Shown in the menu as:** Deserialize Roto Shape


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `payload` | `STRING` | default `""`, multiline | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `obj` | `ROTO_SHAPE` | — |


### NukeMax_Serialize_ROTO_SHAPE

**Shown in the menu as:** Serialize Roto Shape


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `obj` | `ROTO_SHAPE` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `payload` | `STRING` | — |


---

## NukeMax/IO/TRACKING_DATA


### NukeMax_Deserialize_TRACKING_DATA

**Shown in the menu as:** Deserialize Tracking Data


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `payload` | `STRING` | default `""`, multiline | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `obj` | `TRACKING_DATA` | — |


### NukeMax_Serialize_TRACKING_DATA

**Shown in the menu as:** Serialize Tracking Data


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `obj` | `TRACKING_DATA` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `payload` | `STRING` | — |


---

## NukeMax/Keying


### NukeMax_ChromaKeyer

**Shown in the menu as:** Chroma Keyer (NukeMax)

Screen-colour difference keyer with softness and despill. Outputs the despilled image plus an alpha matte (foreground = 1).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Footage shot against a coloured screen. |
| `screen` | choice: `green`, `blue`, `red` | default `"green"` | Which screen colour to key out. |
| `tolerance` | `FLOAT` | default `0.05`, range -1.0…1.0, step 0.005 | Where the matte starts to open. Lower = keys more of the screen. |
| `softness` | `FLOAT` | default `0.2`, range 0.001…1.0, step 0.005 | Width of the soft edge between full foreground and full screen. |
| `despill` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.05 | How strongly to pull screen colour out of the edges (1 = full). |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | Input RGB with screen spill suppressed. |
| 1 | `matte` | `MASK` | Alpha matte: 1 on the foreground subject, 0 on the screen. |


### NukeMax_Despill

**Shown in the menu as:** Despill (NukeMax)

Suppress green/blue screen spill: clamp the screen channel toward the average of the other two.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `screen` | choice: `green`, `blue` | default `"green"` | — |
| `amount` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Difference

**Shown in the menu as:** Difference (NukeMax)

Difference keyer: matte = where image differs from a clean plate (|img-plate|), with gain + threshold.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `clean_plate` | `IMAGE` |  | — |
| `gain` | `FLOAT` | default `4.0`, range 0.1…32.0, step 0.1 | — |
| `threshold` | `FLOAT` | default `0.05`, range 0.0…1.0, step 0.005 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |
| 1 | `matte` | `MASK` | — |


### NukeMax_Keyer

**Shown in the menu as:** Keyer (NukeMax)

Luminance/channel keyer: build a matte from a value range with soft edges. Outputs the matte as RGB + alpha.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `channel` | choice: `luminance`, `red`, `green`, `blue` | default `"luminance"` | — |
| `range_low` | `FLOAT` | default `0.2`, range 0.0…1.0, step 0.005 | — |
| `range_high` | `FLOAT` | default `0.8`, range 0.0…1.0, step 0.005 | — |
| `softness` | `FLOAT` | default `0.1`, range 0.0…0.5, step 0.005 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |
| 1 | `matte` | `MASK` | — |


### NukeMax_Premult

**Shown in the menu as:** Premult (NukeMax)

Premultiply: multiply RGB by an alpha matte (straight → premultiplied), as required before a Merge (over).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `alpha` | `MASK` |  | Matte to premultiply with (1 keeps, 0 zeroes). |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Unpremult

**Shown in the menu as:** Unpremult (NukeMax)

Unpremultiply: divide RGB by an alpha matte (premultiplied → straight) so colour ops act on un-darkened edges. Division by zero is guarded.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `alpha` | `MASK` |  | Matte to divide by; zero-alpha pixels are left unchanged. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


---

## NukeMax/Lens


### NukeMax_STMapApply

**Shown in the menu as:** STMap Apply (Lens Distortion)

Apply a Nuke-style STMap to an IMAGE. The STMap is an RGB image where R=U, G=V in [0,1]. Each output pixel reads from the source at (R,G). Use this to apply lens distortion / un-distortion.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Source image to warp. |
| `stmap` | `IMAGE` |  | STMap. R=U, G=V in [0,1]. Output resolution matches the STMap. |
| `interpolation` | choice: `bilinear`, `bicubic`, `nearest` | default `"bilinear"` | Sampling mode. |
| `padding_mode` | choice: `zeros`, `border`, `reflection` | default `"border"` | Behaviour outside [0,1] UV range. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `preserve_hdr` | `BOOLEAN` | default `True` | Keep float32 unbounded (no clamp). Disable for SDR images. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | Warped IMAGE at the STMap resolution. |


### NukeMax_STMapIdentity

**Shown in the menu as:** STMap Identity

Build an identity STMap at the given resolution (R=U, G=V, B=0).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `width` | `INT` | default `1920`, range 16…16384 | STMap width in pixels. |
| `height` | `INT` | default `1080`, range 16…16384 | STMap height in pixels. |
| `batch` | `INT` | default `1`, range 1…1024 | Batch size. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `stmap` | `IMAGE` | Identity STMap as IMAGE (B,H,W,3) float32. |


### NukeMax_STMapInvert

**Shown in the menu as:** STMap Invert

Numerically invert an STMap (e.g. convert a distort-map into an undistort-map). Uses scatter+inpaint; accurate to ~sub-pixel for smooth lens warps. Output resolution matches input.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `stmap` | `IMAGE` |  | STMap to invert. |
| `fill_iterations` | `INT` | default `8`, range 0…64 | Hole-fill passes after scatter. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `stmap_inv` | `IMAGE` | Inverted STMap. |


---

## NukeMax/Merge


### NukeMax_Dissolve

**Shown in the menu as:** Dissolve (NukeMax)

Cross-dissolve between A and B by 'which' (0 = A, 1 = B).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `A` | `IMAGE` |  | — |
| `B` | `IMAGE` |  | — |
| `which` | `FLOAT` | default `0.5`, range 0.0…1.0, step 0.01 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Keymix

**Shown in the menu as:** Keymix (NukeMax)

Keymix: A where mask=1, B where mask=0 (A*mask + B*(1-mask)).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `A` | `IMAGE` |  | — |
| `B` | `IMAGE` |  | — |
| `mask` | `MASK` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Merge

**Shown in the menu as:** Merge (NukeMax)

Nuke Merge: composite A over/under B with the full operation set (over/under/atop/in/out/mask/stencil/plus/minus/multiply/screen/overlay/difference/max/min/average). 'mix' dissolves the result back toward B.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `A` | `IMAGE` |  | — |
| `B` | `IMAGE` |  | — |
| `operation` | choice: `over`, `under`, `atop`, `in`, `out`, `mask`, `stencil`, `plus`, … (+8) | default `"over"` | — |
| `mix` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.01 | Blend the merge result back toward B (1 = full merge). |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Switch

**Shown in the menu as:** Switch (NukeMax)

Pass through input A or B selected by 'which' (0 = A, 1 = B).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `A` | `IMAGE` |  | — |
| `B` | `IMAGE` |  | — |
| `which` | `INT` | default `0`, range 0…1 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


---

## NukeMax/Mocha


### NukeMax_MochaApplyLens

**Shown in the menu as:** Mocha — Apply / Remove Lens Distortion

Apply or remove Mocha-estimated lens distortion to an IMAGE batch (Brown-Conrady model).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `lens` | `MOCHA_LENS` |  | — |
| `mode` | choice: `undistort`, `distort` | default `"undistort"` | undistort: remove lens warp. distort: re-introduce it (e.g. for re-rendering CG into a distorted plate). |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_MochaApplyTracking

**Shown in the menu as:** Mocha — Apply Tracking (Warp)

Warp the source IMAGE batch onto the tracked plane defined by a MOCHA_TRACK. Useful for screen replacements (corner-pin) or per-frame transform follow.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `source` | `IMAGE` |  | Source plate to warp INTO the tracked region. |
| `track` | `MOCHA_TRACK` |  | — |
| `out_width` | `INT` | default `1920`, range 1…16384 | — |
| `out_height` | `INT` | default `1080`, range 1…16384 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |
| 1 | `mask` | `MASK` | — |


### NukeMax_MochaImportAuto

**Shown in the menu as:** Mocha — Import (Auto: paste / upload)

One importer for Mocha/Nuke tracking exports: paste the .nk text OR upload a file. Auto-detects CornerPin2D vs Transform/Tracker4 and returns a MOCHA_TRACK.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `nk_text` | `STRING` | default `""`, multiline | Paste a Mocha/Nuke CornerPin2D or Transform/Tracker4 .nk export here. |
| `uploaded_file` | `STRING` | default `""` | Filename under ComfyUI/input/mocha/ — set by the Upload .nk button. |
| `canvas_width` | `INT` | default `1920`, range 1…16384 | — |
| `canvas_height` | `INT` | default `1080`, range 1…16384 | — |
| `name` | `STRING` | default `"mocha_track"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `track` | `MOCHA_TRACK` | Parsed tracking data. |
| 1 | `info` | `STRING` | Which format was detected and parsed. |


### NukeMax_MochaImportCornerPin

**Shown in the menu as:** Mocha — Import Corner Pin (file path)

Load a Mocha Pro corner-pin tracking export (.nk Nuke or ASCII .txt) into a MOCHA_TRACK socket.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `file_path` | `STRING` | default `""` | Absolute path to Mocha corner-pin export (.nk or .txt). |
| `canvas_width` | `INT` | default `1920`, range 1…16384 | — |
| `canvas_height` | `INT` | default `1080`, range 1…16384 | — |
| `name` | `STRING` | default `"mocha_cp"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `track` | `MOCHA_TRACK` | — |


### NukeMax_MochaImportCornerPinPaste

**Shown in the menu as:** Mocha — Import Corner Pin (paste / upload)

Paste Mocha's tracking data straight from the clipboard: supports Mocha Pro's 'Copy to Clipboard' After Effects Keyframe Data (Corner Pin AND CC Power Pin), the Nuke .nk CornerPin2D export, and plain ASCII 'frame x1 y1 … x4 y4' rows. AE clipboard blocks carry the true plate size — canvas_width/height are then auto-corrected from the data. Files can also be uploaded via the Upload button.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `nk_text` | `STRING` | default `""`, multiline | Paste tracking data here — in Mocha use Export → After Effects Corner Pin (or CC Power Pin) → COPY TO CLIPBOARD and paste the whole block (starts with 'Adobe After Effects … Keyframe Data'). .nk CornerPin2D exports and plain 'frame x1 y1 … x4 y4' rows also work. |
| `uploaded_file` | `STRING` | default `""` | Filename inside ComfyUI/input/mocha/ — set automatically by the Upload .nk button. |
| `canvas_width` | `INT` | default `1920`, range 1…16384 | — |
| `canvas_height` | `INT` | default `1080`, range 1…16384 | — |
| `name` | `STRING` | default `"mocha_cp"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `track` | `MOCHA_TRACK` | — |


### NukeMax_MochaImportLens

**Shown in the menu as:** Mocha — Import Lens Calibration

Load a Mocha Pro lens calibration export (key/value .txt) into a MOCHA_LENS socket.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `file_path` | `STRING` | default `""` | — |
| `canvas_width` | `INT` | default `1920`, range 1…16384 | — |
| `canvas_height` | `INT` | default `1080`, range 1…16384 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `lens` | `MOCHA_LENS` | — |


### NukeMax_MochaImportProject

**Shown in the menu as:** Mocha — Open .mocha Project

Open a Mocha Pro .mocha project (zipped XML) and extract canvas size, fps, and a layer/shape/track summary. Use the dedicated import nodes for tracking/shape/lens data.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `file_path` | `STRING` | default `""` | Absolute path to a .mocha project file. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `project` | `MOCHA_PROJECT` | — |
| 1 | `summary` | `STRING` | — |
| 2 | `canvas_w` | `INT` | — |
| 3 | `canvas_h` | `INT` | — |
| 4 | `fps` | `FLOAT` | — |


### NukeMax_MochaImportShapesAsMask

**Shown in the menu as:** Mocha — Import Shapes → MASK (file path)

Load a Mocha Pro Shape Data export (.nk) and rasterize all contained shapes to a per-frame MASK batch.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `file_path` | `STRING` | default `""` | — |
| `canvas_width` | `INT` | default `1920`, range 1…16384 | — |
| `canvas_height` | `INT` | default `1080`, range 1…16384 | — |
| `feather_pixels` | `FLOAT` | default `0.0`, range 0.0…256.0, step 0.5 | — |
| `combine` | choice: `union`, `intersect` | default `"union"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `mask` | `MASK` | — |


### NukeMax_MochaImportShapesAsMaskPaste

**Shown in the menu as:** Mocha — Import Shapes → MASK (paste / upload)

Mocha shape → MASK. Paste the .nk shape export directly into nk_text, OR press Upload .nk to drop in a file (stored under ComfyUI/input/mocha/). No absolute paths needed.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `nk_text` | `STRING` | default `""`, multiline | Paste the Mocha shape .nk export here. Or click Upload .nk. |
| `uploaded_file` | `STRING` | default `""` | Filename inside ComfyUI/input/mocha/ — set by Upload .nk button. |
| `canvas_width` | `INT` | default `1920`, range 1…16384 | — |
| `canvas_height` | `INT` | default `1080`, range 1…16384 | — |
| `feather_pixels` | `FLOAT` | default `0.0`, range 0.0…256.0, step 0.5 | — |
| `combine` | choice: `union`, `intersect` | default `"union"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `mask` | `MASK` | — |
| 1 | `frame_count` | `INT` | — |
| 2 | `shape_count` | `INT` | — |


### NukeMax_MochaImportTransform

**Shown in the menu as:** Mocha — Import Transform (file path)

Load a Mocha Pro transform tracking export (.nk Transform/Tracker4 or ASCII frame/tx/ty/rot/sx/sy) as MOCHA_TRACK.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `file_path` | `STRING` | default `""` | — |
| `canvas_width` | `INT` | default `1920`, range 1…16384 | — |
| `canvas_height` | `INT` | default `1080`, range 1…16384 | — |
| `name` | `STRING` | default `"mocha_xf"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `track` | `MOCHA_TRACK` | — |


### NukeMax_MochaImportTransformPaste

**Shown in the menu as:** Mocha — Import Transform (paste / upload)

Same as Mocha Import Transform, but accepts the .nk export pasted directly into the text box OR uploaded via the Upload .nk button.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `nk_text` | `STRING` | default `""`, multiline | — |
| `uploaded_file` | `STRING` | default `""` | — |
| `canvas_width` | `INT` | default `1920`, range 1…16384 | — |
| `canvas_height` | `INT` | default `1080`, range 1…16384 | — |
| `name` | `STRING` | default `"mocha_xf"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `track` | `MOCHA_TRACK` | — |


### NukeMax_MochaInvertTrack

**Shown in the menu as:** Mocha — Invert Track (Stabilize)

Invert a MOCHA_TRACK so applying it stabilizes the plate (locks the tracked plane).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `track` | `MOCHA_TRACK` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `track_inverse` | `MOCHA_TRACK` | — |


---

## NukeMax/NkScript


### NukeMax_NkScriptParse

**Shown in the menu as:** NkScript Parse (NukeMax)

Parse a Nuke-style text block (.nk syntax) and emit a JSON description of the encoded subgraph.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `text` | `STRING` | default `""`, multiline | Nuke-style .nk text block to parse. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `json` | `STRING` | — |
| 1 | `node_count` | `INT` | — |


### NukeMax_NkScriptSerialize

**Shown in the menu as:** NkScript Serialize (NukeMax)

Convert a JSON subgraph description (same shape produced by NkScriptParse) into Nuke-style text.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `subgraph_json` | `STRING` | default `""`, multiline | JSON describing nodes + links to serialise. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `text` | `STRING` | — |


---

## NukeMax/Relight


### NukeMax_LightProbeEstimator

**Shown in the menu as:** Light Probe Estimator

Estimate an HDR equirectangular light probe by dividing the image by albedo and binning radiance by surface normal.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Source image (sRGB) to extract incoming radiance from. |
| `materials` | `MATERIAL_SET` |  | Material set providing albedo and normal for the same image. |
| `probe_height` | `INT` | default `256`, range 32…4096 | Height of the output equirect probe in pixels. |
| `probe_width` | `INT` | default `512`, range 32…8192 | Width of the output equirect probe in pixels. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `probe` | `LIGHT_PROBE` | Equirectangular HDR light probe bundle. |


### NukeMax_LightProbeToEXR

**Shown in the menu as:** Light Probe → EXR

Write a LIGHT_PROBE to a 32-bit float EXR file (or .npy fallback) for use in external DCC apps.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `probe` | `LIGHT_PROBE` |  | Light probe to write to disk. |
| `out_dir` | `STRING` | default `"output"` | Output directory (created if missing). |
| `filename` | `STRING` | default `"probe.exr"` | Output file name; .exr if OpenEXR is available. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `path` | `STRING` | Filesystem path of the written probe file (forward slashes). |


### NukeMax_LightRigBuilder

**Shown in the menu as:** Light Rig Builder

Build a LIGHT_RIG from a JSON state or key/fill/rim parameters with a global ambient term.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `rig_state` | `STRING` | default `""`, multiline | Optional JSON string describing lights and ambient; overrides the simple sliders. |
| `key_intensity` | `FLOAT` | default `1.0`, range 0.0…10.0 | Intensity of the key light when no JSON state is provided. |
| `fill_intensity` | `FLOAT` | default `0.4`, range 0.0…10.0 | Intensity of the fill light when no JSON state is provided. |
| `rim_intensity` | `FLOAT` | default `0.6`, range 0.0…10.0 | Intensity of the rim/back light when no JSON state is provided. |
| `ambient` | `FLOAT` | default `0.05`, range 0.0…1.0 | Greyscale ambient term added to all surfaces. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `rig` | `LIGHT_RIG` | Light rig bundle (lights tuple plus ambient color). |


### NukeMax_MaterialDecomposerHeuristic

**Shown in the menu as:** Material Decomposer (Heuristic)

Heuristic albedo/normal/depth/roughness decomposition from a single image, using local-mean albedo and luminance gradients.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Input image to decompose into materials. |
| `albedo_blur_sigma` | `FLOAT` | default `8.0`, range 0.5…64.0 | Gaussian sigma in pixels used to estimate albedo as a local mean. |
| `depth_strength` | `FLOAT` | default `0.5`, range 0.0…4.0 | Strength of luminance-gradient lift used to fake the normal map. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `materials` | `MATERIAL_SET` | Material set bundle (albedo, normal, depth, roughness). |


### NukeMax_MaterialDecomposerModels

**Shown in the menu as:** Material Decomposer (Models)

Model-backed material decomposition (Marigold/StableNormal); falls back to heuristic decomposer if weights are unavailable.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | Input image to decompose. |
| `depth_model` | `STRING` | default `"marigold"` | Identifier of the depth model to use if available. |
| `normal_model` | `STRING` | default `"stable_normal"` | Identifier of the normal model to use if available. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `materials` | `MATERIAL_SET` | Material set bundle (albedo, normal, depth, roughness). |
| 1 | `info` | `STRING` | Status message describing which backend was used. |


### NukeMax_ThreePointRelight

**Shown in the menu as:** 3-Point Relight

Relight a MATERIAL_SET with a LIGHT_RIG using a Lambert+Phong shader and optional Reinhard tonemap.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `materials` | `MATERIAL_SET` |  | Albedo/normal/depth/roughness bundle. |
| `rig` | `LIGHT_RIG` |  | Light rig describing the lights and ambient. |
| `fov_deg` | `FLOAT` | default `50.0`, range 5.0…170.0 | Camera vertical field-of-view in degrees used to reconstruct view rays. |
| `tonemap` | `BOOLEAN` | default `True` | Apply a Reinhard tonemap before returning sRGB. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | Relit sRGB image of the materials under the rig. |


---

## NukeMax/Roto


### NukeMax_RotoKeyframeInterp

**Shown in the menu as:** Roto Keyframe Interp

Interpolate sparse-keyframe roto data to a dense per-frame ROTO_SHAPE using smoothstep tweening between keyframes.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `roto` | `ROTO_SHAPE` |  | — |
| `keyframe_indices` | `STRING` | default `"0,9"` | Comma-separated 0-based frame indices the input keyframes correspond to. |
| `frame_count` | `INT` | default `10`, range 1…4096 | — |
| `easing` | choice: `linear`, `smoothstep`, `smootherstep` | default `"smoothstep"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `roto` | `ROTO_SHAPE` | — |


### NukeMax_RotoShapeFromFile

**Shown in the menu as:** Roto Shape From File

Load a ROTO_SHAPE from a JSON file on disk using the same schema as the spline editor.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `path` | `STRING` | default `""` | Filesystem path to a JSON file containing a roto spline state. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `roto` | `ROTO_SHAPE` | Roto shape parsed from the JSON file. |


### NukeMax_RotoShapeRenderer

**Shown in the menu as:** Roto Shape Renderer

Rasterize a ROTO_SHAPE to a per-frame mask with optional flow-driven directional motion blur.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `roto` | `ROTO_SHAPE` |  | Roto shape to rasterize. |
| `samples_per_segment` | `INT` | default `16`, range 2…128 | Bezier sampling density per segment when building the polyline. |
| `feather_override` | `FLOAT` | default `-1.0`, range -1.0…256.0, step 0.1 | Feather radius in pixels; <0 uses the per-vertex feather mean. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `flow` | `FLOW_FIELD` |  | Optional flow used to drive directional motion blur. |
| `motion_blur_strength` | `FLOAT` | default `0.0`, range 0.0…4.0, step 0.05 | Multiplier on flow vectors for the directional blur amount. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `mask` | `MASK` | Rasterized per-frame roto mask. |


### NukeMax_RotoShapeStack

**Shown in the menu as:** Roto Shape Stack

Composite up to 6 animated ROTO_SHAPE inputs into a single MASK. Per-layer opacity, feather override, invert, and Nuke-style blend op (union/add/max/sub/intersect/min/replace). All layers are rasterized onto the canvas of shape_1 (other shapes are scaled to match).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `shape_1` | `ROTO_SHAPE` |  | Bottom layer — defines the output canvas. |
| `samples_per_segment` | `INT` | default `16`, range 2…128 | Bezier sampling density per segment. |
| `global_blur_px` | `FLOAT` | default `0.0`, range 0.0…256.0, step 0.1 | Final Gaussian blur radius applied after compositing. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `op_1` | choice: `union`, `add`, `max`, `sub`, `intersect`, `min`, `replace` | default `"replace"` | Blend op for layer 1. Layer 1 is always 'replace'. |
| `opacity_1` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.01 | Opacity multiplier on layer 1. |
| `feather_1` | `FLOAT` | default `-1.0`, range -1.0…256.0, step 0.1 | Feather override for layer 1; <0 uses the shape's per-vertex mean. |
| `invert_1` | `BOOLEAN` | default `False` | Invert layer 1 (1 - mask) before combining. |
| `shape_2` | `ROTO_SHAPE` |  | Layer 2 (optional). |
| `op_2` | choice: `union`, `add`, `max`, `sub`, `intersect`, `min`, `replace` | default `"union"` | Blend op for layer 2. Layer 1 is always 'replace'. |
| `opacity_2` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.01 | Opacity multiplier on layer 2. |
| `feather_2` | `FLOAT` | default `-1.0`, range -1.0…256.0, step 0.1 | Feather override for layer 2; <0 uses the shape's per-vertex mean. |
| `invert_2` | `BOOLEAN` | default `False` | Invert layer 2 (1 - mask) before combining. |
| `shape_3` | `ROTO_SHAPE` |  | Layer 3 (optional). |
| `op_3` | choice: `union`, `add`, `max`, `sub`, `intersect`, `min`, `replace` | default `"union"` | Blend op for layer 3. Layer 1 is always 'replace'. |
| `opacity_3` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.01 | Opacity multiplier on layer 3. |
| `feather_3` | `FLOAT` | default `-1.0`, range -1.0…256.0, step 0.1 | Feather override for layer 3; <0 uses the shape's per-vertex mean. |
| `invert_3` | `BOOLEAN` | default `False` | Invert layer 3 (1 - mask) before combining. |
| `shape_4` | `ROTO_SHAPE` |  | Layer 4 (optional). |
| `op_4` | choice: `union`, `add`, `max`, `sub`, `intersect`, `min`, `replace` | default `"union"` | Blend op for layer 4. Layer 1 is always 'replace'. |
| `opacity_4` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.01 | Opacity multiplier on layer 4. |
| `feather_4` | `FLOAT` | default `-1.0`, range -1.0…256.0, step 0.1 | Feather override for layer 4; <0 uses the shape's per-vertex mean. |
| `invert_4` | `BOOLEAN` | default `False` | Invert layer 4 (1 - mask) before combining. |
| `shape_5` | `ROTO_SHAPE` |  | Layer 5 (optional). |
| `op_5` | choice: `union`, `add`, `max`, `sub`, `intersect`, `min`, `replace` | default `"union"` | Blend op for layer 5. Layer 1 is always 'replace'. |
| `opacity_5` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.01 | Opacity multiplier on layer 5. |
| `feather_5` | `FLOAT` | default `-1.0`, range -1.0…256.0, step 0.1 | Feather override for layer 5; <0 uses the shape's per-vertex mean. |
| `invert_5` | `BOOLEAN` | default `False` | Invert layer 5 (1 - mask) before combining. |
| `shape_6` | `ROTO_SHAPE` |  | Layer 6 (optional). |
| `op_6` | choice: `union`, `add`, `max`, `sub`, `intersect`, `min`, `replace` | default `"union"` | Blend op for layer 6. Layer 1 is always 'replace'. |
| `opacity_6` | `FLOAT` | default `1.0`, range 0.0…1.0, step 0.01 | Opacity multiplier on layer 6. |
| `feather_6` | `FLOAT` | default `-1.0`, range -1.0…256.0, step 0.1 | Feather override for layer 6; <0 uses the shape's per-vertex mean. |
| `invert_6` | `BOOLEAN` | default `False` | Invert layer 6 (1 - mask) before combining. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `mask` | `MASK` | Composited per-frame mask. |


### NukeMax_RotoShapeToAITracker

**Shown in the menu as:** Roto Shape → AI Tracker

Propagate a frame-0 roto shape across a frame batch using a flow field or per-vertex NCC tracking.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `roto` | `ROTO_SHAPE` |  | Source roto shape; only frame 0 is used as the seed. |
| `frames` | `IMAGE` |  | Image batch to propagate the shape across. |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `flow` | `FLOW_FIELD` |  | Optional precomputed flow field; bypasses NCC search. |
| `search_radius` | `INT` | default `8`, range 1…64 | NCC search window radius in pixels when no flow is provided. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `roto_animated` | `ROTO_SHAPE` | Roto shape with per-frame propagated points and handles. |
| 1 | `tracks` | `TRACKING_DATA` | Per-frame tracking data (coords, velocity, confidence) for the vertices. |


### NukeMax_RotoShapeToDiffusionGuidance

**Shown in the menu as:** Roto Shape → Diffusion Guidance

Convert a roto shape into hard, soft, and latent-resolution masks plus SAM-style box+point prompts as JSON.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `roto` | `ROTO_SHAPE` |  | Roto shape to convert into diffusion guidance. |
| `soft_radius_px` | `FLOAT` | default `16.0`, range 0.0…256.0 | Gaussian feather radius in pixels for the soft mask. |
| `latent_downscale` | `INT` | default `8`, range 1…32 | Spatial downscale factor for the latent-resolution mask (e.g. 8 for SD VAE). |
| `samples_per_segment` | `INT` | default `16`, range 2…128 | Bezier sampling density per segment. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `mask_hard` | `MASK` | Hard binary roto mask at canvas resolution. |
| 1 | `mask_soft` | `MASK` | Soft Gaussian-feathered roto mask for inpainting. |
| 2 | `mask_latent` | `MASK` | Roto mask downsampled to latent resolution. |
| 3 | `sam_prompts_json` | `STRING` | JSON list of per-frame SAM prompts (boxes, points, labels). |


### NukeMax_RotoSplineEditor

**Shown in the menu as:** Roto Spline Editor

Parse a JSON spline state from the interactive bezier editor into a ROTO_SHAPE on the given canvas.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `spline_state` | `STRING` | default `"{}"`, multiline | JSON string from the JS bezier editor describing per-frame points, handles, and feather. |
| `canvas_height` | `INT` | default `512`, range 8…8192 | Canvas height in pixels when the JSON does not specify one. |
| `canvas_width` | `INT` | default `512`, range 8…8192 | Canvas width in pixels when the JSON does not specify one. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `roto` | `ROTO_SHAPE` | Per-frame roto shape (points, handles, feather, canvas). |


---

## NukeMax/Transform


### NukeMax_AppendClip

**Shown in the menu as:** AppendClip (NukeMax)

Concatenate two image batches along the frame (batch) axis — A then B.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `a` | `IMAGE` |  | — |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `b` | `IMAGE` |  | — |
| `c` | `IMAGE` |  | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_ContactSheet

**Shown in the menu as:** ContactSheet (NukeMax)

Lay every image in the batch out into a single rows×cols contact sheet.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `columns` | `INT` | default `0`, range 0…64 | 0 = auto (near-square). |
| `gap` | `INT` | default `4`, range 0…256 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_CornerPin

**Shown in the menu as:** CornerPin (NukeMax)

4-corner perspective pin: map the image corners to (x,y) destinations (normalised 0..1). Needs OpenCV.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `to1_x` | `FLOAT` | default `0.0`, range -2.0…3.0, step 0.005 | — |
| `to1_y` | `FLOAT` | default `0.0`, range -2.0…3.0, step 0.005 | — |
| `to2_x` | `FLOAT` | default `1.0`, range -2.0…3.0, step 0.005 | — |
| `to2_y` | `FLOAT` | default `0.0`, range -2.0…3.0, step 0.005 | — |
| `to3_x` | `FLOAT` | default `1.0`, range -2.0…3.0, step 0.005 | — |
| `to3_y` | `FLOAT` | default `1.0`, range -2.0…3.0, step 0.005 | — |
| `to4_x` | `FLOAT` | default `0.0`, range -2.0…3.0, step 0.005 | — |
| `to4_y` | `FLOAT` | default `1.0`, range -2.0…3.0, step 0.005 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Crop

**Shown in the menu as:** Crop (NukeMax)

Crop a rectangular region (x,y,width,height); optionally keep the canvas size (black outside) instead of shrinking.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `x` | `INT` | default `0`, range 0…16384 | — |
| `y` | `INT` | default `0`, range 0…16384 | — |
| `width` | `INT` | default `512`, range 1…16384 | — |
| `height` | `INT` | default `512`, range 1…16384 | — |
| `keep_canvas` | `BOOLEAN` | default `False` | Keep original size and black out everything outside the box. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Mirror

**Shown in the menu as:** Mirror (NukeMax)

Flop (mirror horizontal) and/or Flip (mirror vertical).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `flop_horizontal` | `BOOLEAN` | default `False` | — |
| `flip_vertical` | `BOOLEAN` | default `False` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_PARDesqueeze

**Shown in the menu as:** PAR Desqueeze (anamorphic → square px)

Anamorphic plate → SQUARE pixels for AI processing (Nuke: 4448x3840 @ PAR 1.7266 → 7680x3840 at 2:1). par_info feeds PAR Resqueeze for an exact round trip.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `par_preset` | choice: `custom`, `square 1.0`, `anamorphic 2x (2.0)`, `anamorphic 1.8x (1.8)`, `ARRI 4448x3840→2:1 (1.7266)`, `anamorphic 1.5x (1.5)`, `anamorphic 1.33x (1.33)`, `NTSC DV (0.9091)`, … (+1) | default `"ARRI 4448x3840→2:1 (1.7266)"` | — |
| `pixel_aspect` | `FLOAT` | default `1.7266`, range 0.1…4.0, step 0.0001 | Used when par_preset = custom. |
| `method` | choice: `stretch_width`, `squash_height` | default `"stretch_width"` | — |
| `filter` | choice: `bicubic`, `bilinear`, `nearest`, `area` | default `"bicubic"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |
| 1 | `par_info` | `STRING` | — |


### NukeMax_PARResqueeze

**Shown in the menu as:** PAR Resqueeze (back to plate)

Square-pixel AI output → the plate's original pixel dimensions (reapply PAR in Nuke's format). Exact W×H restore, even if the AI changed resolution.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `par_info` | `STRING` | default `""`, **connection-only** | — |
| `filter` | choice: `bicubic`, `bilinear`, `nearest`, `area` | default `"bicubic"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |
| 1 | `info` | `STRING` | — |


### NukeMax_Position

**Shown in the menu as:** Position (NukeMax)

Integer pixel translate (no interpolation), with black / wrap edges (Nuke Position).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `x` | `INT` | default `0`, range -16384…16384 | — |
| `y` | `INT` | default `0`, range -16384…16384 | — |
| `wrap` | `BOOLEAN` | default `False` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Reformat

**Shown in the menu as:** Reformat (NukeMax)

Nuke-style Reformat: fit (letterbox), fill (crop), width, height, or explicit distort. Never distorts unless 'distort' is selected. Aspect presets (cinema ratios) or the input's own ratio can drive the target box.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `width` | `INT` | default `1920`, range 1…16384 | — |
| `height` | `INT` | default `1080`, range 1…16384 | — |
| `filter` | choice: `bilinear`, `bicubic`, `nearest`, `area` | default `"bilinear"` | — |
| `fit_mode` | choice: `fit`, `fill`, `width`, `height`, `distort`, `none` | default `"fit"` | fit=letterbox (default, never distorts); fill=crop to fill; width/height=match that edge, pad/crop the other; distort=allow non-uniform scale (explicit opt-in). |

**Optional inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `aspect_preset` | choice: `off`, `from_input`, `custom`, `1:1`, `4:3`, `3:2`, `16:9`, `1.85:1`, … (+5) | default `"off"` | Overrides target height from width: named cinema ratio, the input's own ratio (from_input), or custom W:H below. |
| `custom_ratio_w` | `FLOAT` | default `1.0`, range 0.01…100.0, step 0.001 | — |
| `custom_ratio_h` | `FLOAT` | default `1.0`, range 0.01…100.0, step 0.001 | — |
| `pad` | choice: `black`, `white`, `transparent` | default `"black"` | Letterbox/pillarbox fill. 'transparent' outputs RGBA. |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Tile

**Shown in the menu as:** Tile (NukeMax)

Tile / repeat the image in a grid (columns x rows).


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `columns` | `INT` | default `2`, range 1…16 | — |
| `rows` | `INT` | default `2`, range 1…16 | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |


### NukeMax_Transform

**Shown in the menu as:** Transform (NukeMax)

2D Transform: translate (px), rotate (deg), scale, around a center, with a chosen filter. Uses an affine grid sample.


**Required inputs**

| Parameter | Type | Constraints | What it does |
|---|---|---|---|
| `image` | `IMAGE` |  | — |
| `translate_x` | `FLOAT` | default `0.0`, range -8192…8192, step 1 | — |
| `translate_y` | `FLOAT` | default `0.0`, range -8192…8192, step 1 | — |
| `rotate` | `FLOAT` | default `0.0`, range -360.0…360.0, step 0.1 | — |
| `scale` | `FLOAT` | default `1.0`, range 0.01…16.0, step 0.01 | — |
| `filter` | choice: `bilinear`, `nearest`, `bicubic` | default `"bilinear"` | — |
| `wrap` | choice: `black`, `edge`, `reflection` | default `"black"` | — |

**Outputs**

| # | Name | Type | What it is |
|---|---|---|---|
| 0 | `image` | `IMAGE` | — |
