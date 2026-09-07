"""Looks up live thread and (POSIX) file-descriptor counts via psutil --
another "reach beyond the given dict" example. A single high reading is
only weak evidence of a leak (some servers legitimately run hundreds of
threads); watched over repeated runs of this tool, a steadily climbing
count is a much stronger signal than any one sample.
"""
from __future__ import annotations

import psutil

_THREAD_THRESHOLD = 200
_FD_THRESHOLD = 500


def enrich(process_info):
    pid = process_info.get("pid")
    if pid is None:
        return {}
    try:
        proc = psutil.Process(pid)
        num_threads = proc.num_threads()
        num_fds = proc.num_fds() if hasattr(proc, "num_fds") else None
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {}

    result = {}
    if num_threads >= _THREAD_THRESHOLD:
        result["high_thread_count"] = num_threads
    if num_fds is not None and num_fds >= _FD_THRESHOLD:
        result["high_fd_count"] = num_fds
    if result:
        result["notice"] = "resource count high in this single sample -- compare across runs before assuming a leak"
    return result
