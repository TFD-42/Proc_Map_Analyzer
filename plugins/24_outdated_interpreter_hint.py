"""Flags a process whose cmdline invokes an end-of-life interpreter --
python2, old Ruby, old PHP. An EOL runtime stops receiving security
patches, so anything it runs inherits every vulnerability found in it
since. The version table below is intentionally short and conservative
(only unambiguous, long-EOL majors) to avoid nagging about "old but
still supported" versions.
"""
from __future__ import annotations

import re

_EOL_PATTERNS = [
    (re.compile(r"\bpython\s*2(\.\d+)?\b"), "Python 2 (EOL since 2020-01-01)"),
    (re.compile(r"\bruby\s*2\.[0-4]\b"), "Ruby < 2.5 (EOL)"),
    (re.compile(r"\bphp\s*5(\.\d+)?\b"), "PHP 5 (EOL since 2019-01-01)"),
]


def enrich(process_info):
    cmdline = process_info.get("cmdline") or ""
    if not cmdline:
        return {}
    for pattern, label in _EOL_PATTERNS:
        if pattern.search(cmdline):
            return {"notice": "cmdline invokes an end-of-life interpreter", "detail": label}
    return {}
