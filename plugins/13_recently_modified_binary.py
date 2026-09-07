"""Flags an executable modified within the last N hours (default 24,
override with PMA_RECENT_BINARY_HOURS). Right after a real security
event this is exactly what you'd look for; day to day it mostly catches
normal package upgrades and your own rebuilds. Pair it with your own
judgment about whether an update was expected right now.
"""
from __future__ import annotations

import os
import time

_RECENT_HOURS = float(os.environ.get("PMA_RECENT_BINARY_HOURS", "24"))


def enrich(process_info):
    exe = process_info.get("exe")
    if not exe:
        return {}
    try:
        mtime = os.stat(exe).st_mtime
    except OSError:
        return {}

    age_hours = (time.time() - mtime) / 3600
    if age_hours < 0 or age_hours > _RECENT_HOURS:
        return {}
    return {
        "notice": "executable modified recently",
        "age_hours": round(age_hours, 1),
    }
