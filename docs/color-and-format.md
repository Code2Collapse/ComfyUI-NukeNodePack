# Color, Format & I/O — the Nuke-parity pipeline

> This guide covers the pro color and format nodes: an OCIO/ACES color
> pipeline (with built-in ARRI LogC support and no config downloads), EXR
> sequence read/write, ProRes export, Nuke-style Reformat, and the anamorphic
> pixel-aspect round trip. Together they let a VFX plate move through an AI
> graph and back to Nuke without a color or geometry surprise.

---

## OCIO / ACES color

Three nodes under **NukeMax/Color**, all backed by OpenColorIO:

| Node | Mirrors | Does |
|---|---|---|
| **OCIO Color Transform** | OCIOColorSpace | Convert an image between any two colorspaces of a config |
| **OCIO Log Convert (Nuke)** | OCIOLogConvert | Scene-linear ↔ compositing-log via the config's roles (ACEScg ↔ ACEScct) |
| **OCIO Display (Nuke)** | OCIODisplay | Bake a display+view transform (e.g. sRGB / ACES SDR video); invert for round-trips; `list_options` introspects the config |

### Built-in ACES configs — no download

OpenColorIO 2.2+ ships ACES configs *inside the library*. The `config`
dropdown lists them first, so everything works out of the box:

- **ACES Studio** — includes **ARRI LogC3 (EI800)** and **LogC4**, camera log
  spaces, and full display/view pipelines
- **ACES CG**
- **OCIO default (ACES)**

Drop your own `.ocio` config folder into `ComfyUI/models/ocio_configs/`, or set
the `$OCIO` environment variable, and it appears in the dropdown too.

> **Install:** `pip install opencolorio>=2.2`. If it isn't installed the nodes
> raise a clear message rather than silently doing nothing.

**Example — ARRI LogC4 plate to working space:**

```
Load plate → OCIO Color Transform
   config = ACES Studio
   src = "ARRI LogC4"   dst = "ACEScg"
→ [scene-linear ACEScg] → your AI graph
```

---

## EXR sequences & ProRes (NukeMax/IO)

| Node | Mirrors | Does |
|---|---|---|
| **EXR Sequence Read (Nuke)** | Read | Load an EXR sequence (`render.####.exr`, `%04d`, or any frame file) or a single EXR. Auto-detects the frame range; missing frames can **error / insert black / hold** the previous frame |
| **EXR Sequence Write (Nuke)** | Write | Save an IMAGE batch as an EXR sequence — half/float, all standard compressions (ZIP / PIZ / DWAA / …) |
| **ProRes / MP4 Write** | Write | Export a batch as Apple **ProRes 422 / 422 HQ / 4444 / 4444 XQ** (via PyAV; **alpha preserved on 4444** with RGBA input) or H.264 MP4 |

Sequence detection follows Nuke's naming rules, including the "last digit group
is the frame number" convention so `shot_v01_0042.exr` parses correctly (the
`v01` isn't mistaken for the frame). The reader's cache is filesystem-aware —
it re-runs when the frames on disk change.

> **Install:** `pip install av OpenEXR` for ProRes and best-quality EXR (an
> OpenCV fallback is used if `OpenEXR` bindings are absent).

---

## Reformat — never distort by default

**Reformat** (NukeMax/Transform) resizes with true Nuke fit-mode semantics.
The default never stretches your image:

| `fit_mode` | Behaviour |
|---|---|
| **fit** *(default)* | Letterbox — the whole image fits inside the target box, padded |
| **fill** | Crop to fill — covers the box, overflow cropped |
| **width** / **height** | Match that edge, pad/crop the other |
| **distort** | The **only** mode that allows non-uniform scale (explicit opt-in) |

Aspect presets drive the target box from a cinema ratio (`1.85:1`, `2:1`,
`2.35:1`, `2.39:1`, …), from the input's own ratio (`from_input` — handles odd
sizes like `4448×3840` exactly), or a custom `W:H`. Padding is black / white /
**transparent** (transparent outputs RGBA). Alpha is carried through.

---

## Anamorphic pixel aspect (NukeMax/Transform)

**PAR Desqueeze** and **PAR Resqueeze** handle non-square-pixel (anamorphic)
plates so AI never distorts them. This is the `4448×3840 @ PAR 1.7266` (2:1
display) case: desqueeze to a true square-pixel `7680×3840` before AI,
resqueeze back to the exact `4448×3840` after. The `par_info` string carries
the undo data and is **interchangeable with CustomNodePacks'
PARDesqueezeMEC/PARResqueezeMEC**.

See the full write-up in CustomNodePacks →
[`docs/anamorphic-par.md`](../../ComfyUI-CustomNodePacks/docs/anamorphic-par.md).

---

## A complete VFX round trip

```
Nuke → EXR sequence (LogC4 or ACEScg)
  → EXR Sequence Read (hold on missing frames)
  → OCIO Color Transform (LogC4 → ACEScg)   [if needed]
  → PAR Desqueeze (1.7266)   [if anamorphic]  ── par_info ─┐
  → … AI graph (Wan / Flux / inpaint) …                    │
  → PAR Resqueeze ◀───────────────────────────────────────┘
  → OCIO Display (bake sRGB for review)  OR  keep scene-linear
  → EXR Sequence Write  /  ProRes 4444 Write
  → back to Nuke
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| OCIO nodes error "requires PyOpenColorIO" | `pip install opencolorio>=2.2` into the ComfyUI environment |
| ARRI LogC not in the colorspace list | Pick the **ACES Studio** built-in config (CG config omits camera log spaces) |
| ProRes node errors about PyAV | `pip install av` — only needed for MOV export, MP4 uses OpenCV |
| Reformat output squished | You're on `distort` (or legacy `none`) — use **fit** (default) or **from_input** |
| EXR sequence loads one frame only | Point at a frame that's part of a numbered sequence, or use a `####`/`%04d` pattern |

---

## License

Apache-2.0. OCIO/EXR/ProRes I/O adapted from ComfyUI-ACES-IO (MIT, © 2025
Bishoy Samaan) with attribution in the source headers. "Nuke" is a trademark
of The Foundry; this pack is independent and unaffiliated.
