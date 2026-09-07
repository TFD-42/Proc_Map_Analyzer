"""Computes the SHA256 of the executable and checks it against an
optional local allow-list (one "hash  name" line per entry, same
convention as sha256sum -- see ALLOWLIST_PATH below). No network lookup:
you populate the allow-list yourself from binaries you already trust, so
nothing about what's running on this machine is ever sent anywhere. If
the allow-list doesn't exist, this just reports the hash for you to
collect.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

ALLOWLIST_PATH = Path(os.environ.get("PMA_HASH_ALLOWLIST", "known_good_hashes.txt"))


def _load_allowlist():
    if not ALLOWLIST_PATH.exists():
        return set()
    hashes = set()
    for line in ALLOWLIST_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            hashes.add(line.split()[0].lower())
    return hashes


_ALLOWLIST = _load_allowlist()


def _sha256_file(path, chunk_size=1 << 20):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def enrich(process_info):
    exe = process_info.get("exe")
    if not exe or not os.path.isfile(exe):
        return {}
    try:
        digest = _sha256_file(exe)
    except OSError:
        return {}

    result = {"sha256": digest}
    if _ALLOWLIST:
        result["known"] = digest.lower() in _ALLOWLIST
    return result
