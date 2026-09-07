"""Computes the SHA256 of the process's executable (same read-and-hash
logic as the main script's --check-integrity / exe_sha256, but usable
without enabling that whole feature) and looks it up against a LOCAL,
user-maintained blocklist file -- entirely offline, no network call, no
telemetry.

The blocklist (known_malicious_hashes.txt, next to this plugin) ships
EMPTY: this project will not hardcode "known malicious" hashes it cannot
independently verify at review time -- a stale or fabricated hash list
in a security tool is worse than no list, since it implies a coverage
that isn't real. Point PROC_ANALYZER_HASH_BLOCKLIST at your own vetted
feed (see the shipped file's header for sourcing suggestions) to get any
actual hits.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

_MAX_BYTES = 128 * 1024 * 1024
_DEFAULT_BLOCKLIST = Path(__file__).parent / "known_malicious_hashes.txt"


def _load_blocklist() -> set[str]:
    path = Path(os.environ.get("PROC_ANALYZER_HASH_BLOCKLIST", str(_DEFAULT_BLOCKLIST)))
    if not path.is_file():
        return set()
    hashes = set()
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip().lower()
            if line and not line.startswith("#"):
                hashes.add(line)
    except OSError:
        return set()
    return hashes


def _sha256_of(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        total = 0
        with open(path, "rb") as f:
            while total < _MAX_BYTES:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                h.update(chunk)
                total += len(chunk)
        return h.hexdigest()
    except OSError:
        return None


def enrich(process_info):
    exe = process_info.get("exe")
    if not exe or not os.path.isfile(exe):
        return {}

    blocklist = _load_blocklist()
    if not blocklist:
        return {}  # nothing to compare against -- silent, not an error

    digest = _sha256_of(exe)
    if digest is None or digest not in blocklist:
        return {}

    return {
        "alert": "executable SHA256 matches the local malicious-hash blocklist",
        "sha256": digest,
        "notice": f"'{exe}' matches an entry in the blocklist -- treat as a confirmed hit, not a heuristic",
    }
