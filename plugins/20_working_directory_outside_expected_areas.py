"""Flags a process whose working directory sits on removable/external
media or another unusual mount point (a USB drive, a mounted disk
image, an unexpected network share) rather than the system disk or the
user's home. A process launched straight from a USB stick or a mounted
.dmg/.iso is a real, common way malware (and, just as often, portable
legitimate tools) gets run on a laptop.
"""
from __future__ import annotations

_UNUSUAL_PREFIXES_DARWIN = ("/volumes/",)
_EXPECTED_PREFIXES_DARWIN = ("/volumes/macintosh hd", "/volumes/data")
_UNUSUAL_PREFIXES_LINUX = ("/media/", "/mnt/", "/run/media/")
_UNUSUAL_PREFIXES_WINDOWS = ("d:\\", "e:\\", "f:\\", "g:\\")  # crude: anything past the usual C:\ system drive


def enrich(process_info):
    cwd = (process_info.get("cwd") or "").lower()
    if not cwd:
        return {}

    if cwd.startswith(_UNUSUAL_PREFIXES_DARWIN) and not cwd.startswith(_EXPECTED_PREFIXES_DARWIN):
        return {
            "notice": "working directory is on a mounted volume (external disk or disk image)",
            "cwd": process_info.get("cwd"),
        }
    if cwd.startswith(_UNUSUAL_PREFIXES_LINUX):
        return {"notice": "working directory is on removable/external media", "cwd": process_info.get("cwd")}
    if cwd.startswith(_UNUSUAL_PREFIXES_WINDOWS):
        return {"notice": "working directory is on a non-system drive", "cwd": process_info.get("cwd")}
    return {}
