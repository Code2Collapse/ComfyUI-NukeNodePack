"""The safe-write core of NukeMax's writers (Write EXR Pro, Write; owner Rev 3 Part 19.7 / 19.8; ledger L9.80).

Where a write may go, how it is named, and how it lands:
- a relative folder lives under ComfyUI's output folder and may not climb out; an absolute one follows the readers'
  rule (any folder on a loopback-only server, only the C2C media roots on a reachable one);
- versioned by default (name_v###/ for frames, name_v###.ext for a movie), plain names only replace a file when
  overwrite is on - otherwise the write is refused, naming the file;
- atomic: a new version folder is written hidden and renamed whole; a single file / a replaced file is written beside
  its target and renamed over it; an interrupted write removes only what it created.
Original code, GPL-3.0-only.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass, field

from . import _media_roots as MR

DEFAULT_DIR = "nukemax_exr"
PATTERNS = ("name.####.ext", "name_####.ext")


class WriteError(ValueError):
    """A refusal in plain words."""


def _output_root() -> str:
    import folder_paths  # type: ignore[import-not-found]
    return os.path.realpath(folder_paths.get_output_directory())


def resolve_dir(output_dir: str, who: str, default: str = DEFAULT_DIR) -> str:
    raw = str(output_dir or "").strip() or default
    if os.path.isabs(raw):
        msg = MR.check_run_path(raw)
        if msg:
            raise WriteError(f"{who}: {msg}")
        return os.path.realpath(raw)
    root = _output_root()
    path = os.path.realpath(os.path.join(root, raw))
    if os.path.commonpath([root, path]) != root:
        raise WriteError(f"{who}: output_dir {raw!r} climbs out of ComfyUI's output folder - use a folder inside "
                         "it, or an absolute path.")
    return path


def display_path(path: str) -> str:
    """Output-relative for files under the output folder (the browser never learns this machine's layout)."""
    try:
        root = _output_root()
        if os.path.commonpath([root, os.path.realpath(path)]) == root:
            return os.path.relpath(path, root).replace(os.sep, "/")
    except (ValueError, ImportError):
        pass
    return path


def clean_name(name: str, ext: str = ".exr") -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "").strip()).strip("._") or "render"
    return re.sub(re.escape(ext) + "$", "", base, flags=re.IGNORECASE) if ext else base


def parse_frames(text: str, count: int, start: int, who: str = "NukeMax Write EXR Pro") -> list[int]:
    """'' -> start, start+1 ...; '1001-1010, 1020' / '1001-1019x2' -> exactly ``count`` distinct numbers."""
    s = str(text or "").strip()
    if not s:
        return [int(start) + i for i in range(count)]
    out: list[int] = []
    for part in re.split(r"[,\s]+", s):
        if not part:
            continue
        m = re.fullmatch(r"(-?\d+)(?:-(-?\d+)(?:x(\d+))?)?", part)
        if not m:
            raise WriteError(f"{who}: frame_numbers {part!r} is not a number or a range (1001-1010, 1001-1020x2).")
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) is not None else a
        step = int(m.group(3) or 1)
        if b < a or step < 1:
            raise WriteError(f"{who}: frame range {part!r} runs backwards.")
        out.extend(range(a, b + 1, step))
    if len(out) != len(set(out)):
        raise WriteError(f"{who}: frame_numbers repeats a frame - each frame needs its own number.")
    if len(out) != count:
        raise WriteError(f"{who}: frame_numbers gives {len(out)} frame(s) for {count} image(s) - give one number per "
                         "image, or leave it empty to count from frame_start.")
    return out


def frame_file(name: str, frame: int, padding: int, pattern: str, ext: str = ".exr") -> str:
    sep = "_" if pattern.startswith("name_") else "."
    num = f"{abs(frame):0{max(1, int(padding))}d}"
    return f"{name}{sep}{'-' if frame < 0 else ''}{num}{ext}"


def pattern_text(stem: str, padding: int, pattern: str, ext: str = ".exr") -> str:
    return f"{stem}{'_' if pattern.startswith('name_') else '.'}{'#' * max(1, int(padding))}{ext}"


def next_version(directory: str, name: str) -> int:
    """The next free version: name_v###/ folders AND name_v###.ext files count."""
    rx = re.compile(rf"^{re.escape(name)}_v(\d{{3,}})(?:\.[A-Za-z0-9]+)?$")
    found = [int(m.group(1)) for e in (os.listdir(directory) if os.path.isdir(directory) else ())
             if (m := rx.match(e))]
    return max(found, default=0) + 1


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Plan:
    """Where one write lands. ``files`` are basenames inside ``final_dir``."""
    who: str
    stem: str
    version: int
    final_dir: str
    work_dir: str
    whole_folder: bool
    files: list[str]
    manifest_name: str | None
    temps: list[str] = field(default_factory=list)

    def temp_for(self, fname: str) -> str:
        if self.whole_folder:
            p = os.path.join(self.work_dir, fname)
        else:
            root, ext = os.path.splitext(fname)
            p = os.path.join(self.work_dir, f".~{root}.{os.getpid()}{ext}")
        self.temps.append(p)
        return p

    def final(self, fname: str) -> str:
        return os.path.join(self.final_dir, fname)

    def place(self, tmp: str, fname: str) -> str:
        """A finished temp file -> its place (renamed now, or with the whole folder at commit)."""
        if not self.whole_folder:
            os.replace(tmp, self.final(fname))
            self.temps.remove(tmp)
        return self.final(fname)

    def current(self, fname: str) -> str:
        """Where the finished file is right now (before commit: inside the hidden folder)."""
        return os.path.join(self.work_dir, fname) if self.whole_folder else self.final(fname)

    def write_manifest(self, text: str) -> None:
        if not self.manifest_name:
            return
        tmp = self.temp_for(self.manifest_name)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        self.place(tmp, self.manifest_name)

    def commit(self) -> None:
        if self.whole_folder:
            os.replace(self.work_dir, self.final_dir)              # the whole version appears at once
        self.temps.clear()

    def abort(self) -> None:
        for t in self.temps:                                       # only what THIS write created
            try:
                os.remove(t)
            except OSError:
                pass
        self.temps.clear()
        if self.whole_folder and os.path.isdir(self.work_dir):
            for f in os.listdir(self.work_dir):
                try:
                    os.remove(os.path.join(self.work_dir, f))
                except OSError:
                    pass
            try:
                os.rmdir(self.work_dir)
            except OSError:
                pass


def plan(who: str, base: str, name: str, names_for, *, versioned: bool, version: int = 0, overwrite: bool = False,
         sidecar: bool = True, folder_per_version: bool = True) -> Plan:
    """``names_for(stem) -> [basenames]``. Refuses in words what would replace a file without ``overwrite``."""
    ver = 0
    if versioned:
        ver = int(version) if int(version or 0) > 0 else next_version(base, name)
        stem = f"{name}_v{ver:03d}"
        final_dir = os.path.join(base, stem) if folder_per_version else base
    else:
        stem, final_dir = name, base
    files = list(names_for(stem))
    manifest = f"{stem}.manifest.json" if sidecar else None
    targets = [os.path.join(final_dir, f) for f in files + ([manifest] if manifest else [])]
    existing = [t for t in targets if os.path.exists(t)]
    if versioned and not overwrite and (os.path.isdir(final_dir) if folder_per_version else existing):
        where = final_dir if folder_per_version else existing[0]
        raise WriteError(f"{who}: version {ver:03d} already exists ({display_path(where)}) - set version 0 for the "
                         "next free one, or turn overwrite on to replace its files.")
    if existing and not overwrite:
        raise WriteError(f"{who}: {len(existing)} file(s) would be replaced, e.g. {display_path(existing[0])} - turn "
                         "overwrite on, or use versioning.")
    whole = versioned and folder_per_version and not os.path.isdir(final_dir)
    work = os.path.join(base, f".~{stem}.partial-{os.getpid()}-{int(time.time() * 1000)}") if whole else final_dir
    os.makedirs(work, exist_ok=True)
    return Plan(who=who, stem=stem, version=ver, final_dir=final_dir, work_dir=work, whole_folder=whole, files=files,
                manifest_name=manifest)
