"""Flags a "living-off-the-land binary" (a legitimate, pre-installed OS
tool) invoked with flags from its well-documented abuse patterns --
downloading and running remote content, most often. See the LOLBAS /
GTFOBins projects for the reference catalog this list is drawn from.
Legitimate admin use of the same flags happens; treat as "explain this
one", not "this is malware".
"""
from __future__ import annotations

import re

_LOLBIN_PATTERNS = [
    (re.compile(r"certutil.{0,30}-urlcache", re.I), "certutil used as a downloader"),
    (re.compile(r"certutil.{0,30}-decode", re.I), "certutil used to decode a payload"),
    (re.compile(r"\bmshta\b.{0,10}https?://", re.I), "mshta executing remote HTML application"),
    (re.compile(r"regsvr32.{0,20}/i:https?://", re.I), "regsvr32 remote-scriptlet execution (Squiblydoo)"),
    (re.compile(r"rundll32.{0,20}javascript:", re.I), "rundll32 executing inline JavaScript"),
    (re.compile(r"powershell.{0,60}-enc(odedcommand)?\b", re.I), "PowerShell running a base64-encoded command"),
    (re.compile(r"bitsadmin.{0,20}/transfer", re.I), "bitsadmin used as a downloader"),
    (re.compile(r"wmic\s+process\s+call\s+create", re.I), "wmic used for indirect process creation"),
    (re.compile(r"curl\s+.{0,80}\|\s*(ba)?sh", re.I), "curl output piped directly into a shell"),
    (re.compile(r"wget\s+.{0,80}\|\s*(ba)?sh", re.I), "wget output piped directly into a shell"),
]


def enrich(process_info):
    cmdline = process_info.get("cmdline") or ""
    if not cmdline:
        return {}
    for pattern, description in _LOLBIN_PATTERNS:
        if pattern.search(cmdline):
            return {"alert": "LOLBin-style usage pattern", "detail": description}
    return {}
