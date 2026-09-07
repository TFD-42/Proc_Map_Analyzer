"""Flags a file-modified-before-it-was-created inconsistency on the
executable -- the file-level signature of "timestomping" (an attacker
resetting mtime to an old date to blend a dropped binary in with
legitimate old files, while leaving a metadata trail behind because most
tools can't rewrite every timestamp field consistently).

On macOS/BSD, st_birthtime is the actual file-creation time -- content
CANNOT legitimately be modified before the file existed, so
mtime < birthtime is a hard, high-confidence tell (a plain copy/rsync/tar
extraction preserves mtime but sets a fresh birthtime, so this does NOT
false-positive on ordinary file transfers).

Linux has no birthtime in the classic stat() syscall (only recent
kernels/filesystems expose it via statx, not surfaced by Python's
os.stat portably) -- falls back to the much weaker ctime-vs-mtime check
there: ctime (inode metadata change time) significantly AFTER mtime can
mean "content timestamp was rewritten after the fact", but routine
operations (chmod, chown, a package manager re-registering the file)
produce the exact same shape. Reported with visibly lower confidence.
"""
from __future__ import annotations

import os

_LINUX_MIN_GAP_SECONDS = 3600 * 24 * 30  # 30 days: routine metadata touches are usually much smaller


def enrich(process_info):
    exe = process_info.get("exe")
    if not exe or not os.path.isfile(exe):
        return {}
    try:
        st = os.stat(exe)
    except OSError:
        return {}

    birthtime = getattr(st, "st_birthtime", None)
    if birthtime is not None:
        if st.st_mtime < birthtime - 60:  # small slack for filesystem timestamp rounding
            return {
                "alert": "modification time predates creation time",
                "mtime": st.st_mtime,
                "birthtime": birthtime,
                "notice": (
                    "this file's content-modified timestamp is EARLIER than its own creation "
                    "timestamp -- not achievable through normal file operations, a strong sign the "
                    "mtime was deliberately rewritten (timestomping)"
                ),
            }
        return {}

    # No birthtime available (Linux): weaker ctime-vs-mtime heuristic.
    gap = st.st_ctime - st.st_mtime
    if gap > _LINUX_MIN_GAP_SECONDS:
        return {
            "notice": (
                f"inode metadata changed {gap / 86400:.0f} days after the content's mtime -- "
                "consistent with (but not proof of) a rewritten modification time; routine chmod/chown "
                "or package re-registration can produce the same gap on Linux"
            ),
            "ctime_mtime_gap_days": round(gap / 86400, 1),
        }
    return {}
