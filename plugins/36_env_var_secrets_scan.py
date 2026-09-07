"""Flags secret-shaped environment variable NAMES on a live process
(AWS_SECRET_ACCESS_KEY, LD_PRELOAD, DATABASE_URL with embedded creds,
etc.) -- the environment-variable counterpart to plugin 25's cmdline
secrets scan, which only ever looks at argv and never at environ(), a
completely different and very common place to leak/inject credentials
or hijack execution (LD_PRELOAD is itself a code-execution vector, not
just a "secret").

Reports which KEY NAMES matched and, only for value-based patterns
(a connection string with embedded credentials), a REDACTED value -- the
actual secret value is never included in the plugin's output, which ends
up in exports/reports/the 3D graph UI; this plugin's whole job is to say
"a secret-shaped variable exists here", never to surface it.

psutil.Process.environ() needs to run as the same user as the target
process (or root) on Linux, and is essentially never permitted on macOS
for another user's process (SIP) -- psutil.AccessDenied is the expected,
common outcome and is silently a no-op, not a plugin failure.
"""
from __future__ import annotations

import re

import psutil

_SECRET_KEY_PATTERN = re.compile(
    r"(SECRET|PASSWORD|PASSWD|TOKEN|API[_-]?KEY|PRIVATE[_-]?KEY|ACCESS[_-]?KEY|"
    r"CREDENTIAL|AUTH|_PWD$)",
    re.IGNORECASE,
)

# These are legitimate execution-hijacking vectors when set, not
# "secrets", but belong in the same "worth a look" bucket.
_HIJACK_VECTOR_KEYS = {"LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "PYTHONSTARTUP", "NODE_OPTIONS"}

_VALUE_HAS_CREDENTIALS = re.compile(r"://[^/\s:]+:[^/\s@]+@")  # scheme://user:pass@host


def _redact(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return value[:2] + "***REDACTED***" + value[-2:]


def enrich(process_info):
    pid = process_info.get("pid")
    if pid is None:
        return {}
    try:
        env = psutil.Process(pid).environ()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return {}
    except Exception:
        return {}
    if not env:
        return {}

    secret_keys = [k for k in env if _SECRET_KEY_PATTERN.search(k)]
    hijack_keys = [k for k in env if k in _HIJACK_VECTOR_KEYS]
    value_hits = [k for k, v in env.items() if isinstance(v, str) and _VALUE_HAS_CREDENTIALS.search(v)]

    if not secret_keys and not hijack_keys and not value_hits:
        return {}

    result = {}
    if secret_keys:
        result["secret_shaped_env_keys"] = sorted(set(secret_keys))
    if hijack_keys:
        result["execution_hijack_env_keys"] = sorted(set(hijack_keys))
        result["hijack_values_redacted"] = {k: _redact(env[k]) for k in hijack_keys}
    if value_hits:
        result["env_values_with_embedded_credentials"] = sorted(set(value_hits))
    result["notice"] = (
        f"{len(secret_keys)} secret-shaped env var name(s), {len(hijack_keys)} execution-hijack "
        f"var(s), {len(value_hits)} value(s) with embedded credentials -- names/redacted values only, "
        "actual secret values are never included in this output"
    )
    return result
