# WORKLOG — ComfyUI-NukeMaxNodes

**Stage 0 audit, 2026-08-29. Every number below was MEASURED this session, not inherited.**
Regenerate with the commands in the last section. Per R3 this file is the persisted source of
record; a claim that lives only in a chat transcript has now drifted five times.

> **Updated 2026-08-29 after the build passes.** The numbers above are re-measured, not the Stage-0 audit figures. A worklog that still reports its audit snapshot is the stale-record failure R3 exists to prevent.

## 1. Live inventory
| | |
|---|---|
| **Nodes registered (runtime)** | **179** (was 181; exr_io deleted, owned by CustomNodePacks) |
| Registration style | V1 `NODE_CLASS_MAPPINGS`, 33 subpackages |
| `WEB_DIRECTORY` | `./web` |
| Test files | 15 (added test_deep_image.py, test_migrated_vfx_nodes.py) |

## 2. Licence — CORRECTION TO THE BRIEF
**Apache-2.0**, read from `LICENSE` lines 1-3. Brief section 4.3 says "keep MIT while it ports only
MIT nuke-nodes" — **this repo is not MIT.** Apache-2.0 already accepts MIT inbound, so the intent of
that decision is satisfied with no change at all. Flipping it to GPL would permanently block
Apache/MIT consumers and is only worth doing if you specifically want GPL VFX math here.

## 3. Registration smoke
PASS — 181 nodes.

## 4. Findings against the brief P0 list
- **PAR already exists.** `nukemax/nodes/comp/pixel_aspect.py` provides `PARDesqueeze` /
  `PARResqueeze`, and `tests/test_par_aspect.py` cites the real 4448x3840 @ PAR 1.7266 plate.
  Remaining gaps are narrow: PAR baked into the EXR header on write, and a de-squeeze preview.
- **EXR I/O already exists** — `NukeMax_EXRSequenceLoad` / `Save`, `LoadEXRMEC` / `SaveEXRMEC`,
  `EXRMetadataReaderMEC`, `exr_channel_router.py`.
- **Sequence padding is ahead of the competition.** We parse `####`, `%04d` and `_0001`
  (`nukemax/nodes/io/exr_sequence.py:108,139`). CoCoTools issue #18 handles only 4-char `####`.
- **Transfer functions are correct.** `nukemax/nodes/color/color_science.py:35-45` has EOTF and OETF
  the right way round; CoCoTools issue #14 has them reversed. Worth a round-trip test to keep it so.
- **Upload button is blocked by core.** `image_upload: True` is images-only; there is no generic file
  upload. `file_upload` + `accept_filetypes` was only proposed (Comfy-Org/ComfyUI discussion #7603).

## 5. Hang risk (R5) — the real P0
**3 of 47** node files carry an interrupt check. Five modules loop over frames with none:
`io/exr_sequence.py`, `flow/`, `roto/`, `ocio_color/`, `essentials3/`. `_interrupt_check.py` and
`_progress.py` already exist and are simply unused. `exr_sequence.py` is the EXR loader — precisely
the reported hang.

## 6. Invariant sweep
| Check | Result |
|---|---|
| `third_party` runtime imports | 0 |
| `IS_CHANGED` -> `float("nan")` | 0 |
| Hardcoded `.cuda()` | 0 |

## 7. Build queue (post-decision)
1. Hang-proofing — wire the existing helpers into the 5 loop modules. Cheapest real win; needs no
   design decision.
2. Upload/browse per decision 4.2 (folder_paths browser + sequence auto-detect, no new deps).
3. PAR into the EXR header on write, plus de-squeeze preview.
4. Lens model, DOF-from-depth, relight preview from MIT `nuke-nodes-comfyui`.

## 8. Blocked / decisions
Decision 4.3 rests on a wrong premise (repo is Apache-2.0, not MIT). Recommendation: leave as
Apache-2.0, no action.

## Regeneration commands

```
head -3 LICENSE

# registration smoke, the way ComfyUI loads (third_party/ComfyUI/nodes.py:2243-2263):
#   sys.modules[name] = mod   BEFORE   spec.loader.exec_module(mod)
# Anything less can report healthy for a pack that registers nothing.
python <scratch>/regsmoke.py ComfyUI-NukeMaxNodes

D:/PROJECT/ComfyUI_windows_portable/comfy_env/python.exe -m pytest tests/ -q
```

Shell python has no torch — always use the comfy_env interpreter.
