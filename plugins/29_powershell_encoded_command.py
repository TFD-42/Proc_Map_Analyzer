"""Flags PowerShell invoked with an encoded/obfuscated command -- the
single most common shape of a PowerShell-based payload (Empire, Cobalt
Strike, PowerSploit, and countless copy-pasted one-liners all use
-EncodedCommand or manual string-obfuscation to dodge naive string
matching and logging). Distinct from plugin 07's generic base64-blob
detector: this is PowerShell-specific and also catches non-base64
obfuscation idioms (char-code arrays, string-splitting/joining,
'.Invoke(' style indirection) that plugin 07 does not look for at all.

Each individual indicator (an -enc flag, one [char] cast, one -join) is
extremely common in entirely benign scripts on its own; the score only
fires past a threshold of MULTIPLE co-occurring indicators, the same
"this shape, not this substring" spirit as the code-cave/entropy plugins.
"""
from __future__ import annotations

import re

_IS_POWERSHELL = re.compile(r"powershell(\.exe)?|pwsh(\.exe)?", re.IGNORECASE)

_INDICATORS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"-e(nc|ncodedcommand)?\b", re.IGNORECASE), "-EncodedCommand flag (or its -e/-enc abbreviation)"),
    (re.compile(r"-w(indowstyle)?\s+hidden", re.IGNORECASE), "-WindowStyle Hidden"),
    (re.compile(r"-nop(rofile)?\b", re.IGNORECASE), "-NoProfile"),
    (re.compile(r"frombase64string", re.IGNORECASE), "[Convert]::FromBase64String (manual base64 decode)"),
    (re.compile(r"\[char\]\s*\d+", re.IGNORECASE), "character-code array reconstruction ([char]N...)"),
    (re.compile(r"-join\s*\(", re.IGNORECASE), "-join operator (string reassembly, common de-obfuscation step)"),
    (re.compile(r"iex\b|invoke-expression", re.IGNORECASE), "IEX / Invoke-Expression (executes a built string)"),
    (re.compile(r"downloadstring|downloadfile|net\.webclient", re.IGNORECASE), "WebClient download cradle"),
    (re.compile(r"bypass\b", re.IGNORECASE), "-ExecutionPolicy Bypass"),
]

_MIN_INDICATORS_TO_FIRE = 2  # any single one alone is common in benign scripts


def enrich(process_info):
    cmdline = process_info.get("cmdline") or ""
    if not _IS_POWERSHELL.search(cmdline):
        return {}

    hits = [label for pattern, label in _INDICATORS if pattern.search(cmdline)]
    if len(hits) < _MIN_INDICATORS_TO_FIRE:
        return {}

    return {
        "notice": f"PowerShell invoked with {len(hits)} co-occurring obfuscation/execution indicators",
        "indicators": hits,
    }
