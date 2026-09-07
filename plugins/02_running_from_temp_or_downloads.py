"""Flags a process whose executable lives under a temp/downloads-style
directory -- a common landing zone for freshly downloaded or dropped
binaries. Many legitimate installers and portable apps run from there
too, so this is a "worth a second look" signal, not a verdict.
"""
from __future__ import annotations

_SUSPECT_PATH_FRAGMENTS = (
    "/tmp/", "/var/tmp/", "/dev/shm/",
    "\\appdata\\local\\temp\\", "\\windows\\temp\\",
    "/downloads/", "\\downloads\\",
)


def enrich(process_info):
    exe = (process_info.get("exe") or "").lower()
    if not exe:
        return {}
    hit = next((frag for frag in _SUSPECT_PATH_FRAGMENTS if frag in exe), None)
    if not hit:
        return {}
    return {
        "notice": "binary runs from a temp/downloads-style directory",
        "path_fragment": hit.strip("/\\"),
    }
