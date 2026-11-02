# Vendored code

| Folder | Canonical source | Licence | Kept equal by |
|---|---|---|---|
| `c2c_core/` | [ComfyUI-CustomNodePacks](https://github.com/Code2Collapse/ComfyUI-CustomNodePacks) `c2c_core/` (same author, Code2Collapse) | Apache-2.0 (`c2c_core-LICENSE.txt` beside this file). Apache-2.0 code may be included in this GPL-3.0-only pack. | `tools/sync_vendored.py` group `py-core` (workspace), and the pre-push gate's `vendored_sync` check |

**Why** (2026-11-02, ledger L9.80, owner Rev 3 Part 19): NukeMax's EXR / media input (Read EXR Pro and the readers
after it) runs on the same engine as CustomNodePacks' Load Video (C2C) and the MiniMax Suite. EXR, sequence, pass and
safe-path handling is therefore one implementation, not a third one.

**Rules**
- Never edit `c2c_core/` here. Fix the canonical tree in CustomNodePacks, then run `tools/sync_vendored.py --write`.
- When several packs are installed, each copy loads under its own package name (`nukemax.vendor.c2c_core`).
  Objects that cross packs, such as the `C2C_VIDEO` handle and EXR passes, are checked by their fields or contract
  name, never with `isinstance`.
