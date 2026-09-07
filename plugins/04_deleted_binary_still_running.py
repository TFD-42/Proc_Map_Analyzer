"""Flags a process whose executable path no longer exists on disk while
the process is still running -- normal after a package upgrade or a
self-deleting installer, and also a known technique to hide a dropped
binary from a later disk scan while it keeps running in memory. Context
decides which; this plugin only surfaces the fact.
"""
from __future__ import annotations

import os


def enrich(process_info):
    exe = process_info.get("exe")
    if not exe:
        return {}
    # Linux sometimes reports this directly with a literal " (deleted)"
    # suffix appended to the path itself; strip it before checking.
    deleted_suffix = exe.endswith(" (deleted)")
    path = exe[: -len(" (deleted)")] if deleted_suffix else exe
    if deleted_suffix or not os.path.exists(path):
        return {
            "notice": "executable missing or unreadable on disk",
            "detail": "process still runs from a binary that's gone or inaccessible "
                      "(permission-denied looks the same as deleted) -- upgrade artifact, "
                      "self-cleanup, or hidden persistence",
        }
    return {}
