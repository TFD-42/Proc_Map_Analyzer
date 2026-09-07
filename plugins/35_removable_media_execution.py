"""Flags a process running FROM a removable/external media mount point --
the classic BadUSB/autorun/"someone plugged in a drive" vector, and a
pattern the existing path-based plugins (01, 02, 20) don't check for:
they cover /tmp, Downloads, and non-standard directories, but a mounted
external volume is none of those.

Path-prefix based, so it only covers where each OS conventionally mounts
removable volumes -- it cannot itself distinguish a truly removable USB
drive from a permanently-mounted external/network volume under the same
mount root (e.g. a NAS mounted under /Volumes on macOS); that
distinction would need an OS-specific "is removable" API this
cross-platform tool doesn't call. Treat a hit as "runs from a mount
point commonly used for removable media", not "definitely a USB stick".

No Windows drive-letter heuristic: fixed vs removable drive letters
aren't distinguishable from a path string alone (both are "D:\\..."),
and guessing would be pure noise.
"""
from __future__ import annotations

_REMOVABLE_MOUNT_PREFIXES = (
    "/Volumes/",       # macOS (also covers non-removable external/network mounts, see caveat above)
    "/media/",         # Linux (most distros' default auto-mount root)
    "/run/media/",     # Linux (systemd/udisks2 auto-mount root)
    "/mnt/",           # Linux (manual mounts; noisier, includes many legitimate permanent mounts)
)

# The boot volume itself lives under /Volumes on macOS too (e.g.
# "/Volumes/Macintosh HD") -- excluding common boot-volume names avoids
# flagging every single process on a default macOS install.
_MACOS_BOOT_VOLUME_NAMES = ("macintosh hd", "system", "data")


def enrich(process_info):
    exe = process_info.get("exe") or ""
    if not exe:
        return {}

    for prefix in _REMOVABLE_MOUNT_PREFIXES:
        if not exe.startswith(prefix):
            continue
        if prefix == "/Volumes/":
            remainder = exe[len(prefix):].split("/", 1)[0].lower()
            if remainder in _MACOS_BOOT_VOLUME_NAMES:
                return {}
        return {
            "notice": f"executable runs from a removable/external media mount point ({exe})",
            "mount_prefix": prefix,
        }
    return {}
