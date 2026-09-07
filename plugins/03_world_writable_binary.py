"""Flags an executable that ANY local user can overwrite (group- or
other-writable). If that's true, whoever controls the file controls what
runs next time the process (or its parent, e.g. a cron job or service)
restarts it -- a classic local privilege-escalation / persistence vector.
POSIX only (os.stat mode bits); a no-op on Windows, which uses ACLs
instead of a mode bitmask.
"""
from __future__ import annotations

import os
import stat
import sys


def enrich(process_info):
    if sys.platform.startswith("win"):
        return {}
    exe = process_info.get("exe")
    if not exe:
        return {}
    try:
        mode = os.stat(exe).st_mode
    except OSError:
        return {}

    writable_by = []
    if mode & stat.S_IWGRP:
        writable_by.append("group")
    if mode & stat.S_IWOTH:
        writable_by.append("other")
    if not writable_by:
        return {}

    return {
        "alert": "world/group-writable executable",
        "detail": f"{exe} is writable by: {', '.join(writable_by)} -- anyone in that scope can replace it",
    }
