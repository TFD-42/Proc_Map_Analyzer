"""Turns a raw process list into an ownership-tagged inventory by
matching `cwd`/`exe` against your own path conventions (e.g. every
service deployed under /opt/<team>/... or /srv/<service>/...) -- pure
fleet-management value, no security angle at all. Edit OWNERSHIP_RULES
below (or point PMA_OWNERSHIP_RULES at a JSON file with the same shape)
to match how your own machines are laid out.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# path fragment -> owner label. Longest fragment checked first so a more
# specific rule isn't shadowed by a shorter generic one.
OWNERSHIP_RULES = {
    "/opt/data-platform/": "data-platform-team",
    "/opt/payments/": "payments-team",
    "/srv/www/": "web-team",
}

_rules_file = os.environ.get("PMA_OWNERSHIP_RULES")
if _rules_file and Path(_rules_file).exists():
    try:
        OWNERSHIP_RULES.update(json.loads(Path(_rules_file).read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        pass

_SORTED_FRAGMENTS = sorted(OWNERSHIP_RULES, key=len, reverse=True)


def enrich(process_info):
    haystack = f"{process_info.get('cwd') or ''} {process_info.get('exe') or ''}".lower()
    for fragment in _SORTED_FRAGMENTS:
        if fragment.lower() in haystack:
            return {"owner": OWNERSHIP_RULES[fragment]}
    return {}
