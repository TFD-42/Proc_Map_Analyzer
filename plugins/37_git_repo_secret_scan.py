"""If the process's cwd is (inside) a git repository, lists TRACKED
filenames that look like committed secrets (.env, private keys,
credentials.json, ...) -- a very common real-world leak (a developer's
long-running dev server/build watcher process sitting in a repo that has
".env" committed by accident).

Filename listing only (`git ls-files`), NEVER file content -- this
plugin does not read, hash, or reproduce what's actually inside a
flagged file, only that git is tracking a file whose NAME suggests it
shouldn't be. `git` itself must be on PATH; if it isn't, or the process
errors/times out, this is silently a no-op.
"""
from __future__ import annotations

import os
import subprocess

_SUSPICIOUS_NAME_PATTERNS = (
    ".env", "id_rsa", "id_ed25519", "id_dsa", "id_ecdsa",
    "credentials.json", "credentials.yml", "credentials.yaml",
    ".pem", ".pfx", ".p12", "secrets.yml", "secrets.yaml", "secrets.json",
    ".npmrc", ".pypirc", ".netrc",
)

_GIT_TIMEOUT_SECONDS = 5


def _looks_suspicious(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(pat) or os.path.basename(lower) == pat.lstrip(".") for pat in _SUSPICIOUS_NAME_PATTERNS) \
        or any(pat in lower for pat in _SUSPICIOUS_NAME_PATTERNS)


def enrich(process_info):
    cwd = process_info.get("cwd")
    if not cwd or not os.path.isdir(cwd):
        return {}

    try:
        result = subprocess.run(
            ["git", "-C", cwd, "ls-files"],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}  # not a git repo (or no commits yet) -- not an error

    tracked = result.stdout.splitlines()
    hits = [f for f in tracked if _looks_suspicious(f)]
    if not hits:
        return {}

    return {
        "alert": "secret-shaped filename(s) tracked in git",
        "repo_path": cwd,
        "tracked_suspicious_files": hits,
        "notice": (
            f"{len(hits)} file(s) matching a secret-file naming pattern are TRACKED by git in this repo "
            "-- if committed by accident, they are in the repo's history even after being deleted; "
            "content was never read by this plugin"
        ),
    }
