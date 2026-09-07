"""Flags a shell/interpreter spawned by a process that normally never
spawns one: an office document viewer, a PDF reader, or a browser. This
is one of the highest-signal indicators in real incident response
(macro malware, malicious PDF launch actions, browser exploit chains all
end with "Word/Acrobat/Chrome -> cmd.exe") and is completely absent from
the existing plugin set, which only looks AT a process, never at its
parent's identity.

process_info only carries ppid (an int); the parent's own name isn't
handed to plugins, so this reaches out via psutil (guaranteed importable,
see plugin 18) to resolve it. The parent may have already exited by the
time this runs (it often has, in a real attack: the dropper spawns and
returns immediately) -- psutil.NoSuchProcess is the COMMON case here, not
an error, and is handled silently.
"""
from __future__ import annotations

import psutil

_SUSPICIOUS_CHILD_NAMES = {
    "cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe",
    "mshta.exe", "rundll32.exe", "regsvr32.exe", "bitsadmin.exe",
    "bash", "sh", "zsh", "dash", "ksh",
}

# Substrings (lowercased) of a PARENT name that should never legitimately
# spawn one of the shells/interpreters above during normal use.
_UNEXPECTED_PARENT_SUBSTRINGS = (
    "winword", "excel", "powerpnt", "outlook", "mspub", "onenote",
    "acrobat", "acrord32", "foxitreader",
    "chrome", "firefox", "msedge", "safari",
)


def enrich(process_info):
    name = (process_info.get("name") or "").lower()
    if name not in _SUSPICIOUS_CHILD_NAMES:
        return {}

    ppid = process_info.get("ppid")
    if ppid is None:
        return {}

    try:
        parent_name = psutil.Process(ppid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return {}

    parent_lower = parent_name.lower()
    if not any(sub in parent_lower for sub in _UNEXPECTED_PARENT_SUBSTRINGS):
        return {}

    return {
        "alert": "unexpected parent -> shell/interpreter chain",
        "parent_pid": ppid,
        "parent_name": parent_name,
        "child_name": process_info.get("name"),
        "notice": (
            f"'{parent_name}' spawned '{process_info.get('name')}' -- office/PDF/browser apps "
            "normally never launch a shell or scripting host directly; classic macro-malware, "
            "malicious-PDF-action, or browser-exploit-chain shape"
        ),
    }
