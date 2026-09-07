"""Flags a UNIX-domain socket living under a world-readable shared
directory (/tmp, /var/tmp, /dev/shm) rather than a private runtime
directory. A socket's own permissions still gate who can connect, but a
predictable, discoverable path in a shared directory is a softer target
than one under a private per-user runtime dir -- worth a glance, not a
verdict.
"""
from __future__ import annotations

_SHARED_TMP_PREFIXES = ("/tmp/", "/var/tmp/", "/dev/shm/")


def enrich(process_info):
    exposed = []
    for conn in process_info.get("connections") or []:
        if conn.get("protocol") != "unix":
            continue
        path = conn.get("laddr") or ""
        if path.startswith(_SHARED_TMP_PREFIXES):
            exposed.append(path)
    if not exposed:
        return {}
    return {"notice": "UNIX socket under a shared temp directory", "sockets": exposed}
