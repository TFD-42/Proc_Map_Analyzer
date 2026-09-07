"""Cross-analysis link detector via `lsof`: for a given process's exe (or,
in --stream-focus-on mode, a scanned FILE's path), finds every OTHER live
process that currently has that exact same file open.

This bridges two things that otherwise never talk to each other in this
tool:
  1. --stream-focus-on's file scan (entropy/code-cave/masquerade
     findings on files on disk) and the LIVE process list: a suspicious
     file found by the file scan might be open RIGHT NOW by a running
     process -- this plugin is what makes that link visible, by running
     the exact same lsof pass over a pseudo-process's "exe" path.
  2. Shared-object/DLL injection: several UNRELATED live processes all
     having the same unusual .so/.dylib mapped open at once is a classic
     injection tell that neither psutil.Process.open_files() (per-process,
     no cross-process view) nor the main graph's file-sharing edges
     (H4, built from p.open_files -- empty for real live processes; that
     field is populated separately, not from lsof) currently surfaces.

Deliberately NOT a per-process `lsof -p <pid>` call (would mean one
subprocess per process -- hundreds of forks on a busy system). Instead
runs ONE system-wide `lsof -Fpn` pass, lazily, the first time enrich() is
called, and serves every process from that single cached path->pids map --
same "expensive setup once, cheap per-process lookup" pattern as the YARA
compiler (plugin 34).

macOS/Linux only (lsof isn't a thing on Windows/Termux); silently a
no-op there via shutil.which().
"""
from __future__ import annotations

import os
import shutil
import subprocess

_LSOF_TIMEOUT_SECONDS = 15
_FILE_TO_PIDS: dict[str, set[int]] | None = None  # built lazily, once


def _build_file_to_pids_map() -> dict[str, set[int]]:
    if not shutil.which("lsof"):
        return {}
    try:
        result = subprocess.run(
            ["lsof", "-Fpn"], capture_output=True, text=True, timeout=_LSOF_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode not in (0, 1):  # lsof exits 1 when some processes were inaccessible -- still usable output
        return {}

    mapping: dict[str, set[int]] = {}
    current_pid: int | None = None
    for line in result.stdout.splitlines():
        if not line:
            continue
        tag, value = line[0], line[1:]
        if tag == "p":
            try:
                current_pid = int(value)
            except ValueError:
                current_pid = None
        elif tag == "n" and current_pid is not None:
            mapping.setdefault(value, set()).add(current_pid)
    return mapping


def _resolve_name(pid: int) -> str:
    try:
        import psutil
        return psutil.Process(pid).name()
    except Exception:
        return f"pid:{pid}"


def enrich(process_info):
    global _FILE_TO_PIDS
    if _FILE_TO_PIDS is None:
        _FILE_TO_PIDS = _build_file_to_pids_map()
    if not _FILE_TO_PIDS:
        return {}

    exe = process_info.get("exe")
    if not exe or not os.path.isabs(exe):
        return {}

    this_pid = process_info.get("pid")
    other_pids = _FILE_TO_PIDS.get(exe, set()) - {this_pid}
    if not other_pids:
        return {}

    others = sorted(other_pids)
    return {
        "notice": (
            f"this exact file is currently open by {len(others)} other live process(es) right now "
            f"(pid {this_pid}{' -- a scanned file, not itself running' if (this_pid or 0) < 0 else ''}) "
            "-- if unrelated to each other, a shared library injected into multiple processes; if this "
            "entry came from --stream-focus-on, it means a file the scan flagged is actively in use"
        ),
        "other_pids_with_file_open": others,
        "other_process_names": sorted({_resolve_name(pid) for pid in others}),
    }
