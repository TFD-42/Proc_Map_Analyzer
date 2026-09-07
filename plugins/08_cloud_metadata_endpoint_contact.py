"""Flags a connection to a cloud instance-metadata service
(169.254.169.254, used by AWS/GCP/Azure/OpenStack/DigitalOcean, and
Alibaba Cloud's 100.100.100.200). Anything talking to it can potentially
retrieve IAM/service-account credentials for the instance -- a
well-known SSRF and credential-theft target. Plenty of legitimate SDKs
and agents talk to it too (the cloud provider's own CLI, cloud-init,
monitoring agents); this only flags contact, not intent.
"""
from __future__ import annotations

_METADATA_IPS = {"169.254.169.254", "100.100.100.200"}


def enrich(process_info):
    for conn in process_info.get("connections") or []:
        raddr = conn.get("raddr") or ""
        host = raddr.rsplit(":", 1)[0] if ":" in raddr else raddr
        if host in _METADATA_IPS:
            return {
                "notice": "contacts a cloud instance-metadata endpoint",
                "endpoint": raddr,
            }
    return {}
