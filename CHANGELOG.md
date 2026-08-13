# Changelog

All notable changes to this project are documented here.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project will follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once a first version is tagged.

## [Unreleased]

No tagged release yet — the following reflects the current state of development, not a diff between two published versions.

### Added
- Installers: Ollama model **matched to the machine** — mini `llama3.2:1b` (~1.3 GB) on Android/Termux, medium `llama3:latest` (~4.7 GB) on macOS/Windows/Linux. Ollama is now also installed on Android via the Termux package (`pkg install ollama`) when available, instead of being skipped. The Python script applies the same policy to its defaults (`--model`, download offered by the assistant) and can install Ollama via `pkg` under Termux.
- Continuous watch mode `--watch --interval N`: periodic re-collection (collection + rules only, never Ollama in a loop), differences displayed between cycles (new/gone/risk changes), HTML regenerated on each cycle.
- Forensic analysis of a single process `--pid N`: detailed text report (identity, risk and signals, connections, open files, ancestor tree + descendants); analysis and HTML restricted to that subtree.
- Automatic run history (`outputs/history.json`, 50 snapshots, `--no-history` to disable) and `--compare` comparison (no value: vs. the previous run; with a path: vs. a `--json-export` export).
- Whitelist/blacklist configuration `--config config.yaml` (plain YAML or JSON, no pyyaml dependency): the whitelist neutralizes path signals from the rule engine, the blacklist forces the "high" level.
- Integrity check `--check-integrity`: SHA256 of each executable compared against a reference database (`--integrity-db`); a modified fingerprint becomes a "high" risk signal.
- Performance baseline `--baseline`: CPU/RAM statistics by process name; from 3 samples onward, a deviation greater than 2 standard deviations becomes an anomaly signal (z-score).
- Persistent SQLite cache for Ollama enrichments `--cache` (key: name+exe+cmdline, TTL `--cache-ttl-days`, default 7 days) — subsequent runs reuse results without an LLM call; results flagged `from_cache`.
- Retry of transiently failed enrichments `--retry-failed N` (exponential backoff 1s/2s/4s, sequential).
- Plugin system `--plugin file.py`: `enrich(process_info) -> dict` function applied to each process, result merged into the export.
- CSV export of graph relationships `--csv-edges` (source, target, kind, risk levels of both endpoints) — importable into Gephi/Neo4j.
- Container detection (Docker/Podman/containerd/Kubernetes) via `/proc/<pid>/cgroup` on Linux, shown in the panel and exports.
- Model preloading `--preload-model`: downloads the Ollama model then exits, to prepare for offline use.
- Sandbox mode `--sandbox file.json`: replays a JSON export instead of collecting the real system (test rules/config/rendering without risk).
- 3D HTML: "copy" buttons in the panel (PID, executable, full command, `kill` command, SHA256) with a fallback when `navigator.clipboard` is unavailable.
- 3D HTML: new keyboard shortcuts — Escape (close the panel), `/` (focus search), 1-5 (switch display mode).
- Deterministic rule-based risk engine (`compute_rule_based_risk`), combined by escalation with the optional Ollama opinion — the displayed risk level no longer depends solely on the AI.
- Explicit visibility of incomplete per-process collection (permission denied, process gone) in the graph and exports.
- Default filtering of low-activity processes in the 3D graph (toggleable), to reduce visual density.
- Markdown summary report and CSV export, both optional (`--report`, `--csv-export`).
- Android/Termux support via a homemade `/proc` backend, replacing `psutil` (not installable on this platform).
- Keyboard shortcuts in the 3D graph: `Ctrl+R` (recenter), `Ctrl++` / `Ctrl+-` (zoom), in addition to the existing buttons.
- `install.sh` (macOS/Linux/Termux) and `install.ps1` (Windows) installers: automatic installation of Ollama, the default model, Python, virtual environment creation, dependency installation, then launch.
- `ENRICHMENT_PLAN.md`: roadmap of 25 prioritized enrichments.
- Repository governance set up (this file, `SECURITY.md`, `STATUS.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `LICENSE`, `.gitignore`, `requirements.txt`, `.github/`) via `github-repo-bootstrapper`.

### Changed
- Entire project translated to English (docs, installers, CLI/log messages, HTML UI, data field names in exports — French field names like `niveau_risque` become `risk_level`; default output directory renamed from `sorties/` to `outputs/`). Files renamed accordingly: `analyseur_processus_allinone.py` → `process_analyzer_allinone.py`, `Analyser_processus.command` → `Analyze_Processes.command`, `Installer_et_lancer.command` → `Install_and_Run.command`, `PLAN_ENRICHISSEMENT.md` → `ENRICHMENT_PLAN.md`. Note: history/cache files produced by older French versions are not compatible (field names changed) — delete `outputs/` (formerly `sorties/`) artifacts to start fresh.
- Default output reduced to just the interactive 3D graph (HTML) — PNG, JSON, CSV and the report are now optional (`--png`, `--json-export`, `--csv-export`, `--report`) rather than generated systematically.
- `--collect-all psutil` made mandatory in the PyInstaller build command (fixes a real runtime crash on macOS, module wrongly reported missing).

### Fixed
- Burst Ollama timeouts fixed with a warm-up call and reduced default parallelism.

## [0.0.0] - untagged

First known working version of the all-in-one script (collection, graph, Ollama enrichment, PNG + 3D HTML rendering, interactive assistant), before formal changelog tracking began.
