// _nukemax_errors.js — plain-English translation of runtime errors.
//
// Kept FREE of any ComfyUI import so it can be unit-tested with plain node.
// The kit (_nukemax_kit.js) imports it; nothing else should duplicate these
// rules. CLAUDE.md's visual check requires "error messages in plain English -
// no raw Python tracebacks", and this is that requirement implemented once for
// all 179 nodes.

// ── plain-English errors ────────────────────────────────────────────────────
// Ordered: the FIRST match wins, so put the specific patterns above the generic
// ones. Each message says what to DO, not merely what broke.
const RULES = [
  [/CUDA out of memory|CUDA error: out of memory/i,
   "Out of GPU memory. Lower the resolution, reduce the batch, or run this node on CPU."],
  [/No module named ['"]?OpenImageIO|OpenImageIO is not installed/i,
   "OpenImageIO is not installed, so EXR cannot be read. Install it: pip install OpenImageIO"],
  [/No module named ['"]?cv2/i,
   "OpenCV is not installed. Install it: pip install opencv-python"],
  [/No module named ['"]?PyOpenColorIO|PyOpenColorIO/i,
   "PyOpenColorIO is not installed, so colour transforms cannot run. Install it: pip install opencolorio"],
  [/No module named ['"]?av\b/i,
   "PyAV is not installed, so ProRes/MOV export cannot run. Install it: pip install av"],
  [/ModuleNotFoundError: No module named ['"]([\w.]+)/i,
   (m) => `A required Python package is missing: ${m[1]}. Install it and restart ComfyUI.`],
  [/FileNotFoundError|No such file or directory|could not be found/i,
   "A file on that path does not exist. Check the path, and that the frame number pattern matches the files on disk."],
  [/PermissionError|Access is denied/i,
   "The file or folder cannot be opened - it is locked by another program, or the path is read-only."],
  [/NoneType.*has no attribute|NoneType.*not subscriptable/i,
   "A required input is not connected."],
  [/must have the same (dimensions|shape)|size mismatch|Sizes of tensors must match/i,
   "The inputs are different sizes. Reformat or Crop them to match before this node."],
  [/channels?.*must match|expected \d+ channels/i,
   "The inputs have different channel counts (for example RGB vs RGBA). Shuffle or Premult to match them."],
  [/all masks are empty|mask is empty/i,
   "The mask is empty, so there is nothing to work on. Check the node that generates it."],
  [/division by zero|ZeroDivisionError/i,
   "A value that must not be zero is zero - usually a size, scale or frame count."],
  [/Interrupted|execution was interrupted/i,
   "Cancelled."],
];

export function humaniseError(raw) {
  if (!raw) return "Something went wrong.";
  const text = String(raw);
  for (const [re, msg] of RULES) {
    const m = text.match(re);
    if (m) return typeof msg === "function" ? msg(m) : msg;
  }
  // Fall back to the last meaningful line of the traceback - the exception
  // itself - rather than the first line, which is always "Traceback...".
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i--) {
    if (/^[A-Za-z_.]*(Error|Exception)\b/.test(lines[i])) return lines[i];
  }
  return lines[lines.length - 1] || "Something went wrong.";
}

