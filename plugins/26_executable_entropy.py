"""Computes the Shannon entropy of the executable file on disk (0-8
bits/byte) -- a standard static-analysis proxy for "is this compressed
or encrypted", since compressed/encrypted/packed data looks close to
random while ordinary machine code and data don't. High entropy is
exactly what a packer (legitimate, for size, or malicious, to defeat
static scanning) produces; it is also what a legitimate app with an
embedded compressed resource (an installer, a game with packed assets)
produces. This plugin can tell you "unusually random-looking", never
"packed" or "malicious" -- that distinction needs more context than one
number.

File-based (reads the executable on disk), same access pattern as the
existing sha256/codesign plugins -- no live memory access, no new
capability.
"""
from __future__ import annotations

import math
import os
from collections import Counter

# 7.5 is a commonly cited packer/compression threshold in the security
# literature (max is 8.0 for byte-level entropy) -- high enough that
# ordinary machine code and text virtually never cross it on their own.
_HIGH_ENTROPY_THRESHOLD = 7.5
_MAX_BYTES = 64 * 1024 * 1024  # cap I/O and CPU on very large binaries


def _file_entropy(path, chunk_size=1 << 20, max_bytes=_MAX_BYTES):
    counts = Counter()
    total = 0
    truncated = False
    with open(path, "rb") as f:
        while total < max_bytes:
            chunk = f.read(min(chunk_size, max_bytes - total))
            if not chunk:
                break
            counts.update(chunk)
            total += len(chunk)
        else:
            truncated = f.read(1) != b""
    if total == 0:
        return 0.0, 0, False
    entropy = -sum((c / total) * math.log2(c / total) for c in counts.values())
    return entropy, total, truncated


def enrich(process_info):
    exe = process_info.get("exe")
    if not exe or not os.path.isfile(exe):
        return {}
    try:
        entropy, sampled_bytes, truncated = _file_entropy(exe)
    except OSError:
        return {}

    result = {"entropy_bits_per_byte": round(entropy, 2), "sampled_bytes": sampled_bytes}
    if truncated:
        result["sampled_bytes_truncated"] = True
    if entropy >= _HIGH_ENTROPY_THRESHOLD:
        result["notice"] = "unusually high entropy for an executable -- possibly packed, compressed, or encrypted content"
    return result
