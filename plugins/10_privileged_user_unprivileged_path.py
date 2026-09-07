"""Flags a process running as root/SYSTEM/admin whose executable sits
under a directory normal users can write to (their home folder, Desktop,
Downloads, /tmp) instead of a system location. That combination means a
non-privileged user's mistake or malice can end up executing as root --
worth knowing about even when today it's just a misconfigured cron job
or launch agent, not an attack.
"""
from __future__ import annotations

_PRIVILEGED_USERS = {"root", "system", "administrator", "administrateur"}
_USER_WRITABLE_FRAGMENTS = ("/home/", "/users/", "\\users\\", "/desktop/", "/downloads/", "/tmp/", "/documents/")


def enrich(process_info):
    username = (process_info.get("username") or "").lower()
    # usernames are sometimes "DOMAIN\\user" or end in "$" for service accounts
    if username.split("\\")[-1] not in _PRIVILEGED_USERS:
        return {}
    exe = (process_info.get("exe") or "").lower()
    if not exe:
        return {}
    hit = next((frag for frag in _USER_WRITABLE_FRAGMENTS if frag in exe), None)
    if not hit:
        return {}
    return {
        "alert": "privileged user running from a user-writable path",
        "detail": f"runs as '{process_info.get('username')}' from '{process_info.get('exe')}'",
    }
