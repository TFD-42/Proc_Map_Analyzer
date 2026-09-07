"""Flags a suspiciously long base64-looking substring in the cmdline --
a common shape for an encoded payload handed to an interpreter (`python
-c <b64>`, `powershell -enc <b64>`, etc). Long base64 tokens also show
up legitimately (embedded certs, tokens, config blobs), so this is a
"decode and look" signal, not a verdict.
"""
from __future__ import annotations

import re

# 40+ base64 alphabet characters in a row, no whitespace. Deliberately
# excludes "/" from the run (unlike the base64 alphabet itself): a plain
# filesystem path IS 40+ chars of [A-Za-z0-9] chained by "/", which is
# also technically valid base64 charset -- tried this with "/" included
# against a real system's process list and it fired on ~60% of processes,
# every single one a macOS framework path. Standard base64 still reaches
# 40+ consecutive non-"/" characters more often than not; this trades a
# little recall for a lot of precision.
_BASE64_BLOB = re.compile(r"[A-Za-z0-9+]{40,}={0,2}")


def enrich(process_info):
    cmdline = process_info.get("cmdline") or ""
    match = _BASE64_BLOB.search(cmdline)
    if not match:
        return {}
    blob = match.group(0)
    return {
        "notice": "long base64-looking blob in cmdline",
        "length": len(blob),
        "preview": blob[:24] + "...",
    }
