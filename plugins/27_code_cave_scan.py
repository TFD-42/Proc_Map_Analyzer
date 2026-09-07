"""Scans the executable on disk for long runs of a single repeated byte
(0x00 most commonly, also 0x90/NOP and 0xCC/INT3) -- the file-level shape
of a "code cave": empty space inside a legitimate binary big enough to
hide a shellcode stub without changing the file's size. This is a
disk-file byte scan, not a live-memory scan (that would need a new
capability this tool doesn't have on macOS -- psutil exposes no
memory-map API on this platform, confirmed directly, not assumed).

Calibration note, read before changing the thresholds below: a naive
absolute-length threshold does NOT work on macOS. Run against a real,
clean, unmodified system (525 real processes), EVERY SINGLE ONE produced
a 0x00 run of 12KB-65KB -- this is routine Mach-O structural padding
(__LINKEDIT / alignment / reserved space), not a hidden anything. The
absolute run length turned out to be roughly CONSTANT regardless of
file size (a 140KB helper and a 310MB app both showed ~20-65KB runs),
which makes runlength/filesize ratio the actually-discriminating signal:
tiny system helpers reached ratios up to 0.248 from padding alone, while
huge binaries sat at ~0.000 for the exact same absolute padding. Both
thresholds below are set with real margin above that observed ceiling
(0.248 ratio, and separately every individual sub-50KB run) -- and were
re-verified to produce zero hits on that same real system after being
raised. This is still a best-effort file-level heuristic, not true
Mach-O/PE/ELF section-boundary parsing (which would need to know what
each byte range is actually *for* to fully separate "padding" from
"cave" -- out of scope for one plugin); treat a hit as "worth a look",
not a verdict, same as everywhere else in this set.
"""
from __future__ import annotations

import os
import re

_FILLER_BYTES = (0x00, 0x90, 0xCC)
_MIN_RUN_TO_CONSIDER = 4096  # per-region floor just to skip trivial/no-op scanning
_MIN_RATIO = 0.35   # real ceiling observed was 0.248; this sits well above it
_MIN_ABSOLUTE = 50_000  # real observed runs at high ratio topped out under 33,000
_MAX_BYTES = 64 * 1024 * 1024


def _runs(data, filler_bytes, min_run):
    findings = []
    for filler in filler_bytes:
        pattern = re.compile(re.escape(bytes([filler])) + b"{%d,}" % min_run)
        run_count = 0
        longest = 0
        for m in pattern.finditer(data):
            run_count += 1
            longest = max(longest, m.end() - m.start())
        if run_count:
            findings.append({"byte": f"0x{filler:02X}", "count": run_count, "longest_run": longest})
    return findings


def enrich(process_info):
    exe = process_info.get("exe")
    if not exe or not os.path.isfile(exe):
        return {}
    try:
        file_size = os.path.getsize(exe)
        with open(exe, "rb") as f:
            data = f.read(_MAX_BYTES)
    except OSError:
        return {}
    if not data or file_size == 0:
        return {}

    findings = _runs(data, _FILLER_BYTES, _MIN_RUN_TO_CONSIDER)
    if not findings:
        return {}

    longest_overall = max(f["longest_run"] for f in findings)
    ratio = longest_overall / file_size
    result = {"regions": findings, "longest_run_ratio_of_file": round(ratio, 3)}
    if longest_overall >= _MIN_ABSOLUTE and ratio >= _MIN_RATIO:
        result["notice"] = (
            f"a single-byte run covers {ratio:.0%} of the file ({longest_overall} bytes) -- "
            "cave-shaped, well above what routine padding looked like on a clean reference system, "
            "still not proof of anything hidden"
        )
    return result
