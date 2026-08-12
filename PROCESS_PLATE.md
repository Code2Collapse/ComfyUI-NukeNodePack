# PROCESS PLATE — VFX IO / Colour / Comp node program

**Purpose:** a fresh conversation picks this up and continues with zero
re-investigation and zero conflict. Read this file top to bottom before
touching anything. Update the STATE table as you go — that table is the
contract between sessions.

---

## 0. STATE (update this every session)

| batch | scope | status | landed |
|---|---|---|---|
| 1a | `LoadEXRMEC` via OpenImageIO | **DONE** | CNP main `881f06b` |
| 1b | `SaveEXRMEC` via OIIO — compression, bit depth, AOV write, metadata | **DONE** | CNP `e2a6dcf` |
| 1c | Channel/AOV shuffle + metadata nodes (NEXT) | not started | — |
| 2 | OCIO colour tier (12 OCIO + colour half of radiance) | not started | — |
| 3 | Grade tier | not started | — |
| 4 | Transform / Filter tier | not started | — |
| 5 | Merge / Keying tier | not started | — |

**Target pack for ALL of it:** `ComfyUI-NukeMaxNodes`.
Exception already shipped: `LoadEXRMEC` lives in `ComfyUI-CustomNodePacks/nodes/exr_io.py`
because it already existed there. Do NOT duplicate it into NukeMax — extend in place.

---

## 1. Environment facts — verified, do not re-investigate

* ComfyUI python: `D:/PROJECT/ComfyUI_windows_portable/comfy_env/python.exe`
  The plain shell python has **no torch**. Always use the full path.
* **Installed and verified this program:** `OpenImageIO 3.1.16`,
  `PyOpenColorIO 2.5.2`.
  OIIO CLI (`oiiotool`, `maketx`, `idiff`) is in `comfy_env\Scripts`, not on PATH.
* **cv2 CANNOT read EXR in this environment.** OpenCV's OpenEXR codec is
  disabled unless `OPENCV_IO_ENABLE_OPENEXR=1` is set *before* cv2 is imported.
  Every reference pack reads EXR through `cv.imread`, so they fail here. This
  is the measured justification for rebuilding rather than vendoring.
* ComfyUI `IMAGE` = `torch.float32 [B,H,W,C]`, values 0..1 nominal but **not
  clamped** for linear/HDR work. `MASK` = `[B,H,W]`.

## 2. Reference packs — cloned, read-only

`D:/PROJECT/Custom_Nodes/third_party/`

| pack | registered nodes | what it is good for |
|---|---|---|
| `ComfyUI-OCIO` | 12 | thin but correct PyOpenColorIO wrapper |
| `radiance` | 87 | ACES config mgmt, ARRI/DaVinci gamuts, view transforms |
| `nuke-nodes-comfyui` | 32 | the comp operator set |

**= 131 nodes.** Counted by AST-parsing `NODE_CLASS_MAPPINGS`. Do NOT count by
grepping `"key":` — that returns 261/824/234, which is wrong and will mislead
the estimate.

**The gap none of them close:** named EXR channels / AOVs. All three read
RGB(A) and drop `diffuse.R`, `N.x`, `depth.Z`, cryptomatte. That is the
differentiator for this program.

---

## 3. Design contract — every node in this program obeys these

1. **Linear float, never clip.** Do not clamp to 0..1 anywhere in an IO or
   colour node. Clamping on load destroys speculars and emissives.
2. **Model-agnostic means contract-agnostic.** Arbitrary resolution, arbitrary
   channel count, no assumption of 8-bit sRGB 512x512. "Works with every
   HuggingFace model" is not verifiable and is not the target; this is.
3. **No silent fallback.** Every backend downgrade is logged with the reason.
   Total failure raises, naming each attempt and the fix (e.g. `pip install
   OpenImageIO`). Silent substitution is how AOVs go missing until delivery.
4. **Surface what you cannot output.** If a node returns RGB but the file had
   11 channels, the channel list, compression and metadata go out in an `info`
   output. Never drop information without saying so.
5. **`IS_CHANGED`** must hash real inputs — never `float("nan")`.
6. Standard ComfyUI conventions: `INPUT_TYPES`, `RETURN_TYPES`, `FUNCTION`,
   `CATEGORY`, `NODE_CLASS_MAPPINGS`. No new mandatory dependency beyond OIIO
   and OCIO, which are installed.

---

## 4. Verification standard

Every claim gets a measured number, never a reading of the code.

Round-trip fixture that batch 1 must keep passing — write an 11-channel EXR
(`R,G,B,A, diffuse.R/G/B, N.x/y/z, depth.Z`) with DWAA compression and a
`comment` attribute, then assert on read-back:

* all 11 channel names returned
* compression string preserved
* metadata preserved
* `max > 1.0` survives (HDR not clipped)

Baseline already measured for `LoadEXRMEC`: 11 channels, `dwaa`,
`comment='shot_0010'`, `max=1.007`.

---

## 5. Known traps, paid for already

* **Symbol-exists ≠ file-exists.** A previous session shipped `gaze_preflight.py`
  calling `expected_weight_paths()` and `searched_checkpoint_paths()` which
  exist nowhere. Always grep for `def <name>` before calling across modules.
* **Widget order is a contract.** ComfyUI matches widgets by POSITION. Deleting
  or inserting a widget mid-list shifts every later value in saved workflows.
  Hide widgets in JS instead of removing them from `INPUT_TYPES`.
* **Never remove user-facing options without asking.** Doing so broke a working
  setup in this workspace and had to be reverted.
* **Do not `\n` inside a bash heredoc that writes Python string literals** — it
  becomes a real newline and produces an unterminated string. Build the escape
  as `chr(92)+"n"`.
* Push to `main` via the worktree pattern with a real import/compile check on
  the **main copy**, not the dev copy.

---

## 6. Deferred / explicitly out of scope

* **Wan-Animate gaze control.** Architecturally impossible — the face tile is
  compressed to ~20 numbers (`motion_dim=20`) and the pose conditioning image
  contains no iris. Do not add gaze features. See the `wan-animate-face-ceiling`
  memory.
* PoseAndFaceDetectionV2 widget-count reduction — user has not yet named which
  gaze/iris outputs they consume, so nothing may be deleted.
