"""Flags cmdlines that look like they carry a secret as a plain
argument -- passwords, API keys, tokens passed via --flag=value, or a
connection string with embedded credentials. Any local user can read
another process's full cmdline (`ps aux`, /proc/<pid>/cmdline), so a
secret placed there is already exposed on the machine even without this
plugin; the point is making that visible so it gets moved to a config
file, an env var set from a secrets manager, or a file descriptor
instead.
"""
from __future__ import annotations

import re

_SECRET_PATTERNS = [
    re.compile(r"--?(password|passwd|secret|api[-_]?key|token|auth)[= ]\S+", re.I),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                     # AWS access key id
    re.compile(r"\bAuthorization:\s*Bearer\s+\S+", re.I),
    re.compile(r"\bmongodb(\+srv)?://[^:]+:[^@]+@"),         # connection string with embedded credentials
    re.compile(r"\bpostgres(ql)?://[^:]+:[^@]+@"),
]


def enrich(process_info):
    cmdline = process_info.get("cmdline") or ""
    if not cmdline:
        return {}
    if not any(pat.search(cmdline) for pat in _SECRET_PATTERNS):
        return {}
    return {
        "alert": "cmdline may expose a secret in plain text",
        "detail": "any local user can read this via ps/proc -- move it to a config file or secrets manager",
    }
