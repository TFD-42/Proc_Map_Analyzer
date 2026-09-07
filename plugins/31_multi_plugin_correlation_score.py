"""Meta-plugin: escalates when MULTIPLE independent --plugin findings
co-occur on the same process. Every other plugin in this directory looks
at one process in isolation and answers one question; none of them ever
learn what the OTHERS already said about that same process. In practice,
"temp-dir execution" alone is weak, "base64 blob in cmdline" alone is
weak, but the two TOGETHER on the same process is a much stronger tell
than either individually -- exactly the kind of correlation a human
analyst does automatically and this plugin set didn't do at all before.

REQUIRES core support added for this: apply_plugin() now hands each
plugin a "prior_plugin_results" list (this SAME process's plugin findings
from every --plugin that ran BEFORE this one on the command line). This
plugin only sees plugins that ran earlier in the SAME --plugin invocation
-- put it LAST in the --plugin argument list (e.g. --plugin plugins/*.py
already sorts numerically, so a filename starting with a high number like
this one's "31_" naturally runs after 01-30). It will NOT see the two
built-in checks (extension-masquerade, --focus-sec's CVE watchlist),
which are applied by the main script after the --plugin loop entirely.

Correlation is by CO-OCCURRENCE COUNT, not by any specific pairing logic
-- deliberately simple and easy to reason about; a more targeted
attack-chain model (specific plugin A + plugin B => named technique)
would be a reasonable follow-up once real co-occurrence data exists to
calibrate against.
"""
from __future__ import annotations

_MIN_FINDINGS_TO_ESCALATE = 2


def enrich(process_info):
    prior = process_info.get("prior_plugin_results") or []
    # A finding "counts" if it actually signals something -- an empty {}
    # never reaches prior_plugin_results in the first place (apply_plugin
    # only appends non-empty dicts), so every entry here already counts.
    if len(prior) < _MIN_FINDINGS_TO_ESCALATE:
        return {}

    contributing = [entry.get("_plugin", "unknown") for entry in prior]
    return {
        "alert": f"{len(prior)} independent plugin findings on the same process",
        "contributing_plugins": contributing,
        "notice": (
            f"{len(prior)} separate signals ({', '.join(contributing)}) fired on this SAME process -- "
            "individually weak signals correlating on one target raise confidence well above any of "
            "them alone; worth prioritizing this process for manual review first"
        ),
    }
