"""Flags a process whose NAME matches a well-known OS process but whose
executable path is outside where that OS actually keeps it -- the classic
"masquerading" trick (rename a payload to look like svchost.exe / launchd
/ systemd). A path mismatch is a strong tell, not proof: some legitimate
third-party tools reuse common short names too.
"""
from __future__ import annotations

# name (lowercased, no .exe) -> expected path prefixes (lowercase, checked
# after normalizing backslashes to forward slashes)
_EXPECTED_PATH_PREFIXES = {
    "svchost": ["c:/windows/system32", "c:/windows/syswow64"],
    "csrss": ["c:/windows/system32"],
    "lsass": ["c:/windows/system32"],
    "winlogon": ["c:/windows/system32"],
    "explorer": ["c:/windows"],
    "launchd": ["/sbin"],
    "systemd": ["/usr/lib/systemd", "/lib/systemd", "/usr/sbin", "/sbin"],
    "init": ["/sbin", "/usr/sbin"],
    "cron": ["/usr/sbin", "/sbin"],
    "sshd": ["/usr/sbin", "/sbin", "/usr/bin"],
}


def enrich(process_info):
    name = (process_info.get("name") or "").lower()
    if name.endswith(".exe"):
        name = name[:-4]
    exe = process_info.get("exe")
    expected = _EXPECTED_PATH_PREFIXES.get(name)
    if not expected or not exe:
        return {}

    exe_norm = exe.lower().replace("\\", "/")
    if any(exe_norm.startswith(prefix) for prefix in expected):
        return {}

    return {
        "alert": "possible masquerading",
        "detail": f"'{process_info.get('name')}' usually runs from {expected[0]} or similar, "
                   f"but this one runs from '{exe}'",
    }
