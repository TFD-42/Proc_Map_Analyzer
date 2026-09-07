"""macOS only: runs `codesign --verify` against the executable to check
whether its code signature is still intact. A broken/absent signature on
a binary that's supposed to be signed (or was signed once) can mean the
file was modified after signing -- "binary tampering on disk", the same
honest framing this project uses for --check-integrity. It is NOT proof
of malicious intent: plenty of legitimate unsigned or ad-hoc-signed
binaries exist (your own builds, some open-source tools).

Uses subprocess with a LIST of arguments (never shell=True, never a
format string) so nothing in `exe` can be interpreted as shell syntax.

Tested against a running macOS system, this surfaced a real precision
problem worth knowing if you build on this: a meaningful slice of
Apple's OWN system binaries (WebKit XPC services under
/System/Volumes/Preboot/Cryptexes/...) and common Homebrew framework
binaries fail --verify with specific, well-documented, non-security
error strings -- "resource envelope is obsolete (custom omit rules)"
and "code has no resources but signature indicates they must be
present" -- that reflect bundle-structure quirks, not tampering.
Reporting those as "signature check failed" would train you to ignore
this plugin. They're filtered out below; anything else non-zero
(not signed at all, invalid signature, failed requirement, ...) still
fires.
"""
from __future__ import annotations

import subprocess
import sys

_KNOWN_BENIGN_QUIRKS = (
    "resource envelope is obsolete",
    "code has no resources but signature indicates they must be present",
)


def enrich(process_info):
    if sys.platform != "darwin":
        return {}
    exe = process_info.get("exe")
    if not exe:
        return {}
    try:
        result = subprocess.run(
            ["codesign", "--verify", "--verbose", exe],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}

    if result.returncode == 0:
        return {}
    message = (result.stderr or result.stdout or "").strip()
    if any(quirk in message for quirk in _KNOWN_BENIGN_QUIRKS):
        return {}
    return {
        "notice": "code signature check failed",
        "detail": message[:200],
    }
