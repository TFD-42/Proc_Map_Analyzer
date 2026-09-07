# Changelog

All notable changes to this project are documented here.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project will follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once a first version is tagged.

## [Unreleased]

### Added
- `compile_check.py`: single in-memory syntax check of the main script and every `plugins/*.py` (builtin `compile()`, never writes `__pycache__`/`.pyc`). Called by `install.sh`, `install.ps1`, both `.command` launchers, `build.sh`/`build.ps1` and CI, so "the code compiles" is defined once.
- `build.sh` / `build.ps1`: reproducible PyInstaller build in a dedicated `.venv-build/` from `requirements_frozen.txt` + `requirements_build.txt` (PyInstaller pinned), with the README flag set (`--collect-all psutil --collect-submodules matplotlib`), a smoke test of the produced executable (real `--no-enrich` run, HTML must be non-empty) and a `.sha256` next to the artifact. Refuses Android explicitly. `build.ps1` mirrors `build.sh` but was written without a Windows machine: syntax-reviewed, not executed.
- `requirements_build.txt`: build-only pin (`pyinstaller==6.22.2`).
- `install.sh --install-only` / `install.ps1 -InstallOnly`: install + compile check without launching the analyzer. `PMA_SKIP_OLLAMA=1` (both installers) skips every Ollama step — nothing fetched from the internet except pip packages.
- `tests/test_install_scripts.sh`: verification harness that runs `install.sh --install-only`, checks `pip freeze` against every pin of `requirements_frozen.txt`, checks that nothing was launched and no `__pycache__` was written, runs `reinstall.sh`, and optionally `build.sh` (`--with-build`) — all on a throw-away copy in `$TMPDIR`. Wired into CI as a second job.

### Changed
- All five installers/launchers (`install.sh`, `install.ps1`, `Install_and_Run.command`, `Analyze_Processes.command`, `reinstall.sh`) now install from `requirements_frozen.txt` (exact pinned versions) instead of an unpinned hand-written `pip install psutil networkx matplotlib requests` — two installs made months apart now resolve to the same versions. `requirements.txt` is only a fallback, with a warning. On Android/Termux `psutil` is filtered out of the requirements file rather than hand-listed.
- `Analyze_Processes.command` no longer does `pip install --user` into the system Python: it uses the project `.venv` and bootstraps it via `PMA_SKIP_OLLAMA=1 ./install.sh --install-only` when missing.
- `Install_and_Run.command` re-installs only when `requirements_frozen.txt` changes (sha256 stamp inside `.venv/`) instead of probing four hard-coded module names.
- `reinstall.sh` rewritten in bash (was zsh, preferred the unpinned file, silently ran `npm install`): deletes only `.venv/` and stale `__pycache__/`, then delegates to `install.sh --install-only`.
- `install.sh`: Ollama server log goes to `$TMPDIR` (Termux has no `/tmp`); the `curl … | sh` line is printed before it runs; every installer now prints the exact `pip install -r …` command it executes.
- CI: `py_compile` of the main script replaced by `compile_check.py` (covers the plugins too).
- `plugins/`: **38** `--plugin` heuristics (was 27 in the first draft of this entry): masquerading process names, execution from temp/downloads, world-writable binaries, deleted-but-running binaries, reverse-shell command-line patterns, LOLBin abuse, base64 blobs, cloud metadata access, mining-pool ports, privileged-user-in-unprivileged-path, macOS code signature checks, SHA256 fingerprinting, recently-modified binaries, listening-on-all-interfaces, high connection fan-out, UNIX sockets in shared tmp, resource pressure scoring, process status, thread/FD counts, working directory outside expected areas, container/host-network exposure, Docker image lookup, path-based ownership tagging, outdated interpreter hints, secrets-in-cmdline scanning, executable entropy, code-cave scanning, **parent-process anomaly (Office/browser spawning a shell), encoded PowerShell commands, persistent external connections, multi-plugin correlation score, timestomping detection, SHA256 blocklist lookup (`PROC_ANALYZER_HASH_BLOCKLIST`, template `plugins/known_malicious_hashes.txt`), YARA runner (`plugins/yara_rules/*.yar`, ships with the EICAR test rule), execution from removable media, secret-shaped environment variable names, tracked secrets in the process's git repository, and `lsof` cross-reference**.
- `--stream-focus-on DIR_OR_FILE` (file-analysis mode): walks a directory tree — or one file — and runs the whole pipeline (rules, `--plugin`, optional AI opinion, 3D graph) on every file turned into a pseudo-process, with built-in magic-byte type detection and extension-masquerade flagging; `--stream-focus-max-files N` caps the walk. Pseudo-filesystems are skipped.
- `--focus-sec` (high-value target scan): existence/permission audit of a built-in list of sensitive paths (SSH keys, shadow/passwd, shell/DB history, cron, kubeconfig, Docker socket/credentials…) — metadata only — plus tagging of processes against a short verifiable CVE watchlist (Log4Shell, Zerologon, PrintNightmare, EternalBlue, Follina). Standalone JSON report via `--focus-sec-report` (default `outputs/focus_sec_scan_<timestamp>.json`).
- `stream_focus_scan.sh`: portable bash launcher for full-filesystem sweeps on top of `--stream-focus-on` (interactive menu, `--root/--ollama-host/--model/--yes/--max-files` for unattended use; replaces an earlier macOS-only zsh snippet that depended on `shlock`/`fs_usage`).
- README: "Features at a glance", a documented section for the two new modes, and a table of all 38 plugins generated from their docstrings.
- `--plugin` results are now surfaced in the interactive 3D graph (previously computed but only visible via `--json-export`): a legend section, per-severity coloring (alert/notice/info, reusing the risk-level red/amber/grey vocabulary), and a detail-panel block showing each plugin's full returned data.
- `--plugin` accepts several paths and/or a glob pattern in one run (e.g. `--plugin "plugins/*.py"`) instead of exactly one file. `enrichment["plugin"]` is now a list (one entry per plugin that returned data for a given process, tagged with the plugin's filename) rather than a single dict, so multiple plugins firing on the same process no longer overwrite one another — severity escalates across all of them the same way rules-vs-AI risk does (alert > notice > info, never silently dropped to the lower one).

## [0.2.0] - 2026-08-15

### Added
- "Export CSV" button in the interactive 3D graph, next to search: exports exactly the nodes currently visible under the legend filters (all categories on -> everything; only one checked -> only matching nodes).
- Explicit "License" section in the README (MIT, matching `LICENSE`) — previously only referenced via badge.

### Changed
- Consolidated to a single generator script: `process_graph_analyzer.py` removed, `process_analyzer_allinone.py` is now the sole source for the interactive 3D HTML (superset CLI, already what the richer generated HTML on disk actually came from). Both `.command` launchers and CI updated to target it.
- README's AI badge retitled from "100% local AI" to "Local-first AI" — `--ollama-host` genuinely supports pointing enrichment at a remote Ollama instance, so the unqualified "100%" overstated the guarantee.

### Fixed
- The interactive 3D graph failed to render at all: `_HTML_TEMPLATE` is a plain (non-raw) Python triple-quoted string, and `\r\n` written for the embedded JS was being interpreted by Python's own string parser as a real carriage-return/newline at generation time, planting a raw line break inside a regex literal — a JS syntax error that aborted the whole script before `ForceGraph3D` ever ran, regardless of the underlying process data.
- `Analyze_Processes.command` and `Install_and_Run.command` always claimed a PNG was written in their completion summary, even though neither launcher passes `--png` (PNG generation is opt-in and was never actually produced) — the summary now only lists outputs that were actually generated.

## [0.1.0] - 2026-08-13

First tagged release: all-in-one system process analyzer with interactive 3D graph, deterministic rule-based risk engine, optional local AI enrichment (Ollama), and multi-platform installers (macOS, Linux, Windows, Android/Termux).

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

### Removed
- Dead code: the unreferenced `category_color()` helper in both scripts (the "Type" coloring mode lives entirely in the embedded HTML/JS, which has its own `categoryColor` copy; the Python `CATEGORY_COLORS` palette dict stays as the documented source of truth). Snippets backed up under `.claude/dead_code_backup/` locally before removal.

### Fixed
- Burst Ollama timeouts fixed with a warm-up call and reduced default parallelism.

## [0.0.0] - untagged

First known working version of the all-in-one script (collection, graph, Ollama enrichment, PNG + 3D HTML rendering, interactive assistant), before formal changelog tracking began.
