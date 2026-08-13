# Enrichment Plan — process_analyzer_allinone.py

This document takes the provided diagnosis (8 areas) and breaks it down into 25 concrete, prioritized enrichments. The logic follows the diagnosis: moving from accumulating capabilities to reliability of results, noise reduction, traceability of decisions, and concrete diagnostic help.

Each item indicates its status: **[Implemented]** = already in `process_analyzer_allinone.py` as of this document's date, **[Roadmap]** = proposed, not yet done.

## Security — Very high priority

Diagnosis finding: the risk level is produced by the AI model, so it is too dependent on the AI and insufficiently grounded in observable rules.

1. **[Implemented]** Deterministic rule engine for the risk level (`compute_rule_based_risk`), independent of the AI: executable outside standard directories, launched from a temporary directory (`/tmp`, `/var/tmp`, `/dev/shm`, `%TEMP%`), executable missing from disk, listening on all interfaces (`0.0.0.0`/`::`), empty command line while the process is running, unusual volume of distinct external connections. Each triggered rule is traced (`rule_signals`), never an opaque score.
2. **[Implemented]** The Ollama opinion becomes a second opinion annotated separately (`ai_level` vs. `rules_level`): the final displayed level is the higher of the two (`final_level`, an "escalation only" combination — underestimating a risk is worse than overestimating it). A "divergent opinions" badge appears if the AI and the rules disagree.
3. **[Roadmap]** Configurable whitelist/blacklist (external YAML/JSON) of known processes (browsers, editors, system daemons) to further reduce scoring noise without relying on the AI.
4. **[Roadmap]** History of risk-level changes per process between two consecutive runs (comparison with the previous capture in `outputs/`) to spot drift over time rather than an isolated snapshot.

## Collection — Very high priority

Diagnosis finding: good general coverage, but measurements are sometimes incomplete without clear visibility.

5. **[Implemented]** Explicit per-process collection status (`incomplete_collection`): every field that could not be read (permission denied, process gone between enumeration and reading) is traced by name instead of silently becoming `None`/`0`/an empty list. Visible in the HTML's Debug/verbose Info panel.
6. **[Roadmap]** Light, targeted retry for processes whose PID disappears during collection (instead of a plain skip), with a dedicated counter in the summary report ("N ephemeral processes missed").
7. **[Roadmap]** Detection and explicit flagging of zombie processes in the graph (visually distinct node), instead of silently treating them as normal processes or letting them vanish from collection.
8. **[Roadmap]** "Watch" mode: lightweight, configurable periodic re-run that only does collection + rule-based scoring (never the AI) to detect changes continuously without computational overhead or network dependency.

## Graph — Very high priority

Diagnosis finding: parent/child relationships, shared files, and network connections are well modeled, but the graph can be dense and hard to interpret.

9. **[Implemented]** Default filtering of "low-interest" nodes in the 3D HTML: a process with low connection degree, low CPU+RAM, and low final risk is hidden by default (toggleable from the legend, "Display" section), so the initial graph stays readable even with 150 processes.
10. **[Roadmap]** Clustering of identical child processes (e.g., 50 threads/workers of the same parent) into a single expandable aggregated node, instead of 50 individual nodes.
11. **[Roadmap]** "Diff" mode: compare two captures (before/after, or two runs) and highlight in the graph processes that appeared, disappeared, or whose risk changed.
12. **[Roadmap]** Layout editing: offer a "hierarchical" mode (parent/child tree) as an alternative to the current force-directed layout, more readable for a pure process tree.

## Maintenance — Very high priority

Diagnosis finding: monolithic script of over 2000 lines, tests and changes are difficult.

13. **[Roadmap]** Split the file into modules (`collection.py`, `graph.py`, `ai.py`, `export.py`, `ui_html.py`, `cli.py`) with an entry point that assembles them — while keeping a "single-file build" mode (automatic concatenation) so as not to break the PyInstaller `--onefile` distribution, which needs a single source file convenient to point to.
14. **[Roadmap]** Unit test suite (pytest) for pure, deterministic functions: `/proc` parsing, `compute_rule_based_risk`, `build_graph`, JSON/CSV serialization — a realistic target before any refactor, since these are the functions least coupled to the environment.
15. **[Roadmap]** Centralized configuration (a single `Config` dataclass) grouping constants currently scattered around (`RISK_COLORS`, thresholds, default timeouts) to reduce the number of places to touch when changing behavior.
16. **[Roadmap]** Minimal CI (lint + `py_compile` + pytest tests) on every change, even without a formal git repository today — preparatory for eventual publication.

## Export — High priority

Diagnosis finding: no summary report, no history, no analytical formats.

17. **[Implemented]** Markdown summary report generated on every run (`--report`, enabled by default): number of processes by final risk level, top 5 CPU+RAM consumers, distinct external connections, list of high-risk processes with justification, processes with incomplete collection, AI enrichment statistics (model, number enriched, failures). Readable without opening the HTML — especially useful for CLI/cron usage.
18. **[Implemented]** CSV export (`--csv-export`) in addition to the existing JSON, for direct opening in a spreadsheet (one row per process, flattened fields).
19. **[Roadmap]** Run history: each timestamped run in `outputs/`, with a small generated HTML index listing previous runs for quick comparison (direct link to each report/graph).

## Local AI — High priority

Diagnosis finding: preflight, warm-up, JSON handling, and error fallback are already in place, but there's a risk of unverified or costly results.

20. **[Roadmap]** Strict validation of the JSON returned by Ollama via an explicit schema (e.g., `jsonschema`), with ONE automatic retry on non-conforming output (slightly reworded prompt) before falling back to the default enrichment.
21. **[Roadmap]** Enrichment cache keyed by process fingerprint (hash of name+path+cmdline) to avoid re-querying the AI on every run for the same known binaries already seen in a previous run.
22. **[Roadmap]** Display the real cost of enrichment in the summary report (total time, number of calls, model used, number of failures/timeouts).

## 3D HTML Interface — High priority

Diagnosis finding: good prototype, but few diagnostic actions and limited accessibility.

23. **[Roadmap]** Per-process action panel: "copy PID", "copy executable path", "copy full command line" buttons — no automatic network action, purely local copy-paste.
24. **[Roadmap]** Accessibility mode: full keyboard navigation of the graph and panel, verified contrast, alternative HTML table to the 3D rendering for screen readers.
25. **[Roadmap]** Direct export from the UI of the currently filtered/visible subset (JSON/CSV), so a full analysis doesn't need to be rerun just to extract a filtered view.

## Summary of choices for this iteration (Phase 1)

Implemented in this pass, covering the 4 areas ranked "Very high priority" plus part of "High":

- Security: items 1, 2
- Collection: item 5
- Graph: item 9
- Export: items 17, 18

Deliberately left on the roadmap: the modular file split (item 13) and unit tests (item 14), which are the changes with the highest regression risk and the longest to validate properly — better handled in a dedicated iteration, once this base has been retested under real conditions.
