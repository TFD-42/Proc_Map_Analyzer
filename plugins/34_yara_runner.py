"""Runs every *.yar rule file in plugins/yara_rules/ against the process's
executable on disk -- turns this into an actual static-signature scanner
instead of only heuristics. Optional: requires the `yara-python` package
(NOT in requirements.txt, since most users of this project won't want a
YARA dependency); if it's not installed, or no rule files exist, this
plugin silently returns {} for every process rather than erroring the
whole --plugin run.

Ships with exactly one rule (eicar_test_string.yar): the real, standard,
publicly documented EICAR test signature -- a safe, verifiable "does the
plumbing actually work" example, not a claim of real-malware coverage.
Add your own reviewed .yar rules to that directory for real coverage;
this project will not ship rules for "known malware families" it cannot
independently verify and keep current.

Compiles the rules ONCE per --plugin invocation (module-level, not per
process) -- YARA compilation is the expensive part; scanning each file
against already-compiled rules is cheap.
"""
from __future__ import annotations

import os
from pathlib import Path

_RULES_DIR = Path(__file__).parent / "yara_rules"
_MAX_BYTES = 64 * 1024 * 1024

try:
    import yara
    _rule_files = {p.stem: str(p) for p in _RULES_DIR.glob("*.yar")} if _RULES_DIR.is_dir() else {}
    _COMPILED = yara.compile(filepaths=_rule_files) if _rule_files else None
except ImportError:
    _COMPILED = None
except Exception:
    # A syntactically broken .yar file shouldn't take down the whole
    # --plugin run -- fail closed (no scanning) rather than crash.
    _COMPILED = None


def enrich(process_info):
    if _COMPILED is None:
        return {}
    exe = process_info.get("exe")
    if not exe or not os.path.isfile(exe):
        return {}
    try:
        if os.path.getsize(exe) > _MAX_BYTES:
            return {}
        matches = _COMPILED.match(exe)
    except Exception:
        return {}
    if not matches:
        return {}

    return {
        "alert": "YARA rule match",
        "matched_rules": [m.rule for m in matches],
        "notice": f"executable matched {len(matches)} YARA rule(s): {', '.join(m.rule for m in matches)}",
    }
