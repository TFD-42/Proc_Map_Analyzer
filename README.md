# System process analyzer (3D graph + local AI)

[![CI](https://github.com/TFD-42/Proc_Map_Analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/TFD-42/Proc_Map_Analyzer/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![Platforms](https://img.shields.io/badge/Platforms-macOS%20%7C%20Linux%20%7C%20Windows%20%7C%20Android%2FTermux-lightgrey.svg)](#android--termux-support)
[![Local-first AI](https://img.shields.io/badge/AI-local--first%20(Ollama)-orange.svg)](#ollama-integration)

<img width="800" height="492" alt="Enregistrementdelecran2026-08-13a19 38 29-ezgif com-optimize" src="https://github.com/user-attachments/assets/d49c4008-3b46-48b3-956f-7c16f69d6ab1" />

> *Interactive 3D process graph analyzer with deterministic risk scoring and local AI enrichment (Ollama) — no data leaves your machine.*

Command-line tool / graphical assistant that analyzes the processes running on a machine, their related files (executable, working directory, open files) and their relationships (parent → child, shared files, network connections), computes a risk level **through deterministic rules** (not only through AI, see [Security: rules + AI](#security-rule-engine--ai-opinion)), enriches every significant process via a **local Ollama** model, then produces by default a **single deliverable: an interactive 3D graph** (a clickable "solar system", `three.js` / `3d-force-graph`) explorable by click, mouse or keyboard (`Ctrl+R` recenters, `Ctrl+`/`Ctrl-` zooms).

Static PNG, JSON export, CSV export and Markdown summary report remain available but **opt-in** (options `--png` / `--json-export` / `--csv-export` / `--report`, see [Command-line mode](#command-line-mode-advanced)) — the novice wizard mode produces and opens only the HTML.

Everything runs **locally**: the only network request made by the script itself is loading the 3D library from a CDN when the HTML file is opened (see [Privacy](#privacy)), and enrichment calls to Ollama stay on `localhost` by default.

**Cross-platform**: Windows, macOS, Linux (compilable to an executable via PyInstaller) and **Android/Termux** (alternative collection backend based on `/proc`, see [Android / Termux support](#android--termux-support)).

---

## Features at a glance

- **Live process map in 3D** — parent/child tree, shared files, network connections, click any node for PID, exe, cmdline, SHA-256, copy-to-clipboard and one-click `kill`.
- **Deterministic risk engine** (rules, scores, incomplete-collection flags) with an optional **second opinion from a local LLM** through Ollama — nothing leaves the machine.
- **38 plug-in security heuristics** ready to use with `--plugin "plugins/*.py"`: process masquerading, execution from temp/downloads/removable media, deleted-but-running binaries, reverse-shell and encoded-PowerShell command lines, LOLBin abuse, secrets in cmdline/env, cloud-metadata and mining-pool contacts, listening on all interfaces, container host-network exposure, code-signature and SHA-256 allow/block lists, entropy and code-cave scans, timestomping, YARA rules, parent-process anomalies, multi-finding correlation… ([full list](#plugins-38-ready-to-use-security-heuristics)).
- **File-analysis mode** (`--stream-focus-on DIR`): walk a directory or a whole disk and run the same pipeline on every file — magic-byte type detection, extension masquerade, entropy/code-cave/YARA plugins — rendered as the same 3D graph. `stream_focus_scan.sh` wraps it for full-filesystem sweeps.
- **High-value target scan** (`--focus-sec`): existence/permission audit of sensitive paths (SSH keys, shadow, shell history, cron, kubeconfig, docker socket…) plus a short, verifiable CVE watchlist (Log4Shell, Zerologon, PrintNightmare, EternalBlue, Follina) — metadata only, file contents are never read.
- **Incident-response friendly**: single-process forensic view (`--pid`), `--watch` loop, `--baseline` / `--compare` against a previous run, `--check-integrity` of executables, `--sandbox` replay of a JSON export, Markdown/CSV/JSON exports.
- **Reproducible install & build**: pinned requirements, in-memory compile check, `install.sh --install-only`, `build.sh`/`build.ps1` (PyInstaller, pinned, smoke-tested, SHA-256), test harness. Works on macOS, Linux, Windows and Android/Termux.

Typical uses: DFIR triage of a suspicious host, threat hunting on a workstation, security review of a server or a build rig, teaching process forensics with a visual map — all offline.

## Table of contents

- [Project files](#project-files)
- [Automatic installation (recommended on a fresh machine)](#automatic-installation-recommended-on-a-fresh-machine)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Wizard mode (novice)](#wizard-mode-novice)
- [Command-line mode (advanced)](#command-line-mode-advanced)
- [File-analysis mode and high-value target scan](#file-analysis-mode-and-high-value-target-scan)
- [Plugins: 38 ready-to-use security heuristics](#plugins-38-ready-to-use-security-heuristics)
- [Security: rule engine + AI opinion](#security-rule-engine--ai-opinion)
- [Ollama integration](#ollama-integration)
- [The interactive 3D graph](#the-interactive-3d-graph)
- [Output files](#output-files)
- [Building an executable (PyInstaller)](#building-an-executable-pyinstaller)
- [Android / Termux support](#android--termux-support)
- [Privacy](#privacy)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [Design assumptions](#design-assumptions)
- [License](#license)

---

## Project files

| File | Role |
|---|---|
| `process_analyzer_allinone.py` | **Main script**, all-in-one. Contains the analysis, the rule-based risk engine, Ollama enrichment, HTML/PNG rendering, JSON/CSV/report exports, the interactive wizard, and auto-installation of the dependencies and of Ollama. This is the one to use and to compile. |
| `Analyze_Processes.command` / `Install_and_Run.command` | macOS bash launchers, from before the interactive wizard was integrated directly into the Python script — kept as convenience wrappers (dependency setup, timestamped outputs, auto-opening results) around `process_analyzer_allinone.py`. Not required if you run the script directly. |
| `ENRICHMENT_PLAN.md` | Roadmap of the 25 identified enrichments (implemented + roadmap), organized by domain and priority. |
| `install.sh` | Automatic installer for macOS / Linux / Android-Termux — see below. |
| `install.ps1` | Automatic installer for Windows — see below. |
| `reinstall.sh` | Deletes `.venv/` (only that) and rebuilds it via `install.sh --install-only`. |
| `compile_check.py` | In-memory syntax check of the main script + every plugin (never writes `__pycache__`). Called by every installer, launcher, `build.sh` and CI. |
| `build.sh` / `build.ps1` | Reproducible PyInstaller build (dedicated `.venv-build/`, pinned deps, smoke test of the executable, `.sha256`) — see [Building an executable](#building-an-executable-pyinstaller). |
| `requirements_frozen.txt` / `requirements.txt` / `requirements_build.txt` | Exact pinned runtime versions (what every installer uses) / lower bounds only (fallback + CI matrix) / pinned PyInstaller for the build. |
| `tests/test_install_scripts.sh` | Verification harness for the installers and the build, on a throw-away copy (`--with-build` to include PyInstaller). |
| `stream_focus_scan.sh` | Full-filesystem sweep launcher built on `--stream-focus-on` (interactive menu or `--root/--ollama-host/--yes` for cron), portable bash — see [File-analysis mode](#file-analysis-mode-and-high-value-target-scan). |
| `plugins/` | **38** `--plugin` heuristics (one per file, numbered 01–38) plus `known_malicious_hashes.txt` (blocklist template) and `yara_rules/` (drop your `.yar` files there) — see [Plugins](#plugins-38-ready-to-use-security-heuristics). Example `--plugin` scripts (one heuristic each: masquerading, temp-dir execution, mining-pool ports, base64 in cmdline, etc.) — copy-pasteable starting points, load one with `--plugin plugins/03_world_writable_binary.py` or all of them at once with `--plugin "plugins/*.py"`. |
| `demo_graph.png`, `demo_graph_3d.html`, `demo_data.json` | Sample outputs generated during development. |

## Automatic installation (recommended on a fresh machine)

On a machine that has **nothing installed** (neither Python nor Ollama), the `install.sh` (macOS/Linux/Termux) and `install.ps1` (Windows) scripts automate everything, in this order, checking at each step what is already present before attempting anything:

1. **Ollama** (local AI engine) — via Homebrew on macOS, the official script on Linux, `winget` or the official installer on Windows, and the Termux package (`pkg install ollama`) on Android when it is available in the repositories.
2. **Ollama model suited to the machine** — downloaded via `ollama pull` if not already present:
   - **Android/Termux**: **mini** model `llama3.2:1b` (~1.3 GB) — limited RAM and storage on mobile;
   - **macOS / Windows / Linux**: **medium** model `llama3:latest` (~4.7 GB).

   The Python script applies the same policy for its own defaults (`--model` and the download offered by the novice wizard).
3. **Python 3** — via Homebrew/`apt`/`dnf`/`pacman`/`zypper`/`pkg` (Termux) on macOS/Linux, via `winget` or the official installer on Windows.
4. **Virtual environment** (`.venv`) — created then activated automatically.
5. **Python dependencies** — installed into that venv from **`requirements_frozen.txt`** (exact pinned versions: the same install on two machines, or months apart, gives the same versions). `requirements.txt` (lower bounds only) is used only if the frozen file is missing, with a warning. On Android, `psutil` is filtered out of the file (internal `/proc` backend instead). The exact `pip install -r …` command is printed before it runs.
6. **Compile check** — `compile_check.py` compiles the main script and every `plugins/*.py` in memory; a syntax error stops here, before anything is launched. Nothing is written to disk (no `__pycache__`).
7. **Launch** of `process_analyzer_allinone.py` (arguments passed to the installer are forwarded as-is to the script, e.g. `./install.sh --no-enrich`).

Two switches make the installers usable on a machine you do not want touched beyond the venv:

- `./install.sh --install-only` / `install.ps1 -InstallOnly` — steps 1–6 only, nothing launched.
- `PMA_SKIP_OLLAMA=1` (environment variable, both installers) — skips steps 1–2 entirely: no Ollama install, no server start, no model download. Nothing is fetched from the internet except pip packages.

```bash
PMA_SKIP_OLLAMA=1 ./install.sh --install-only   # venv + pinned deps + compile check, nothing else
./reinstall.sh                                  # wipe .venv/ and redo the above
tests/test_install_scripts.sh                   # prove it on a throw-away copy (add --with-build for PyInstaller)
```

A failure on Ollama or the model never interrupts the installation (the analysis works without AI, using the rule-based risk engine); a failure on Python, however, is fatal since nothing can run without it.

**macOS / Linux / Termux:**

```bash
chmod +x install.sh
./install.sh
```

**Windows** (PowerShell — if script execution is blocked by the default policy):

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

These installers touch the system (software installation, possibly `sudo`/administrator rights for Ollama or Python depending on the platform) — read them before running them on a sensitive machine, as with any automatic installation script fetched online.

## Prerequisites

- **Python 3.9+**
- Python dependencies: `networkx`, `matplotlib`, `requests`, and `psutil` on every platform except Android/Termux — installed automatically on first launch if missing (except in a compiled executable, see below). On Android/Termux, `psutil` is automatically replaced by an internal backend (see [Android / Termux support](#android--termux-support)).
- **Ollama** (optional) for AI enrichment — installed automatically if needed in wizard mode (see [Ollama integration](#ollama-integration)). Without Ollama, the tool still works, just without the AI-generated descriptions.
- An **internet connection** is required only for: automatic installation of the dependencies/of Ollama, downloading an Ollama model, and displaying the 3D graph (library loaded from a CDN). The process analysis itself requires no external network access.

## Quick start

```bash
python3 process_analyzer_allinone.py
```

Launched **without any argument**, the script starts the interactive wizard (see below). Launched **with options**, it behaves like a classic command-line tool for advanced or scripted usage.

## Wizard mode (novice)

Triggered automatically by double-clicking the compiled executable, or by launching the script without arguments. Asks at most two to four questions depending on the situation:

1. **Maximum number of processes** to include in the graph (default: 150 — the most active in CPU + RAM always take priority, the rest is simply excluded from the graph, never silently truncated without a log).
2. **Ollama model** to use for enrichment:
   - If models are installed locally, they are listed by number (`0` to disable AI).
   - If Ollama is not detected at all, the wizard offers to install it automatically (see [Ollama integration](#ollama-integration)).
   - If Ollama is running but no model is installed, the wizard offers to download the default model (`llama3:latest`).
   - Answering no to both offers never blocks the analysis: it simply continues without AI enrichment.

The number of processes actually enriched by AI is derived automatically from the max process count (`min(max_processes, 40)`) to avoid a third question.

At the end of the run:
- **only the 3D HTML graph is written** (`outputs/process_graph_3d_YYYYMMDD_HHMMSS.html`, next to the script or the executable) and **opens automatically** in the default browser — no PNG, JSON, CSV or report in wizard mode (for those formats, rerun on the command line with `--png` / `--json-export` / `--csv-export` / `--report`, see below);
- the window stays open until a key is pressed, so that a console launched by double-click does not close instantly.

## Command-line mode (advanced)

Used as soon as at least one argument is passed to the script (`--help` included):

```bash
python3 process_analyzer_allinone.py --help
```

| Option | Default | Description |
|---|---|---|
| `--html-output PATH` | `process_graph_3d.html` | Path of the interactive 3D HTML (generated by default) |
| `--no-html` | — | Disables 3D graph generation (not recommended, it is the only default output) |
| `--png` | — | Also generates a static PNG (disabled by default) |
| `--output PATH` | `process_graph.png` | Path of the PNG, used only with `--png` |
| `--json-export PATH` | — | Also exports the collected/enriched/risk data as JSON (disabled by default) |
| `--csv-export PATH` | — | Also exports as CSV, one line per process (disabled by default) |
| `--report PATH` | — | Writes a Markdown summary report (disabled by default) |
| `--model NAME` | `llama3.2` | Ollama model to use |
| `--ollama-host URL` | `http://localhost:11434` | Ollama API URL |
| `--enrich-limit N` | `25` | Max number of AI-enriched processes, sorted by CPU+RAM activity |
| `--enrich-all` | — | Enriches every collected process (ignores `--enrich-limit`) |
| `--no-enrich` | — | Completely disables the Ollama call (rule-based risk stays active) |
| `--min-score N` | `0` | Minimum score (cpu%+mem%) to include a process |
| `--max-processes N` | no limit | Max number of processes included in the graph (keeps the most active) |
| `--max-conn-per-process N` | `20` | Max raw network connections collected per process |
| `--max-conn-total N` | `300` | Max connection edges drawn in total |
| `--max-workers N` | `2` | Parallelism of Ollama calls |
| `--timeout N` | `120` | Timeout per Ollama call, in seconds |
| `-v`, `--verbose` | — | DEBUG-level logs |

### Additional execution modes

| Option | Default | Description |
|---|---|---|
| `--watch` | — | Continuous monitoring: periodic re-collection (collection + rules only, **never** Ollama in a loop), differences shown between cycles, HTML regenerated. Ctrl+C to stop |
| `--interval N` | `60` | Interval in seconds between two `--watch` cycles (minimum 5) |
| `--pid N` | — | Forensic analysis of **one** process: detailed text report + analysis restricted to its subtree (ancestors + descendants) |
| `--compare [PATH]` | — | Compares the current run to a snapshot: without a value, to the previous run in the history; with a path, to a `--json-export` export |
| `--history-file PATH` | `outputs/history.json` | History file populated automatically (50 snapshots kept) |
| `--no-history` | — | Disables automatic snapshot recording |
| `--sandbox PATH` | — | Reads processes from a JSON file (`--json-export` format) instead of the real system — risk-free testing of rules/config/rendering |
| `--preload-model` | — | Downloads/prepares the Ollama model then exits (offline preparation) |

## File-analysis mode and high-value target scan

Two modes added after v0.2.0 reuse the whole pipeline (rule engine, `--plugin`, AI opinion, 3D graph) on something other than live PIDs:

| Option | Default | Effect |
|---|---|---|
| `--stream-focus-on DIR_OR_FILE` | — | **File-analysis mode.** Walks every file under the directory (or analyzes one file), whatever its displayed extension, and turns each one into a pseudo-process (`exe` = file path) so the same rules and plugins run on it. Built-in magic-byte detection flags files whose real content disagrees with their extension (`.txt` that is a Mach-O, `.jpg` that is a script…). Pseudo-filesystems (`/proc`, `/sys`, `/dev`, `/run`, Spotlight/Time Machine volumes) are skipped. |
| `--stream-focus-max-files N` | unlimited | Safety cap on the walk for a broad root such as `/`. |
| `--focus-sec` | — | **High-value target scan.** Checks a built-in list of sensitive paths (SSH keys and `authorized_keys`, `shadow`/`passwd`, shell and database history, cron, kubeconfig, Docker socket and registry credentials…) for existence and risky permissions — metadata only, contents are never read — and tags running or scanned processes against a short CVE watchlist that you can verify independently (Log4Shell, Zerologon, PrintNightmare, EternalBlue, Follina). Works with or without `--stream-focus-on`. |
| `--focus-sec-report PATH` | `outputs/focus_sec_scan_<timestamp>.json` | Where the standalone `--focus-sec` result list is written. |

```bash
# Sweep a user folder with the file-oriented plugins, no AI, capped at 50k files
python3 process_analyzer_allinone.py --stream-focus-on /Users --stream-focus-max-files 50000   --plugin "plugins/26_executable_entropy.py" --plugin "plugins/27_code_cave_scan.py"   --plugin "plugins/32_timestomping_detector.py" --plugin "plugins/34_yara_runner.py" --no-enrich

# Same thing, whole disk, interactive confirmation, Ollama on another machine
./stream_focus_scan.sh --root / --ollama-host http://<ollama-host>:11434 --model llama3.1

# Sensitive-path audit + CVE watchlist on the live process list
python3 process_analyzer_allinone.py --focus-sec --focus-sec-report outputs/focus_sec.json --no-enrich
```

`stream_focus_scan.sh` refuses nothing silently: scanning `/` asks for confirmation (skip with `--yes` for cron), the file cap defaults to 200 000 (`--max-files 0` for unlimited), and the Ollama host is a plain flag — nothing GPU-specific lives in the launcher.

### Advanced analysis and enrichment

| Option | Default | Description |
|---|---|---|
| `--config PATH` | — | Whitelist/blacklist (simple YAML or JSON): the whitelist neutralizes path signals, the blacklist forces the "high" level |
| `--check-integrity` | — | SHA256 of each executable compared to a reference database; a changed fingerprint = "high" signal |
| `--integrity-db PATH` | `outputs/integrity.json` | Fingerprint reference database |
| `--baseline` | — | Adds this run to the CPU/RAM baseline per process name; from 3 samples on, a deviation > 2 standard deviations becomes an anomaly signal |
| `--baseline-file PATH` | `outputs/baseline.json` | Baseline file |
| `--cache` | — | SQLite cache of Ollama enrichments: an identical process already analyzed is served again without an LLM call |
| `--cache-file PATH` | `outputs/enrich_cache.sqlite3` | Cache file |
| `--cache-ttl-days N` | `7` | Validity period of cache entries |
| `--retry-failed N` | `0` | Retries transiently failed enrichments up to N times (exponential backoff) |
| `--plugin PATH [PATH ...]` | — | One or more Python plugins, each exposing `enrich(process_info: dict) -> dict`, applied to each process. Accepts several paths and/or a glob pattern (e.g. `--plugin "plugins/*.py"` — quote it so the script expands it, not the shell); every plugin that returns data for a process gets its own entry rather than overwriting the others |
| `--csv-edges PATH` | — | Exports the graph **relationships** as CSV (importable into Gephi/Neo4j) |

Example `--config` file (YAML):

```yaml
whitelist:
  - "/usr/local/go/*"   # fnmatch patterns accepted
  - "code helper"        # otherwise, substring search (name, exe or cmdline)
  - "ollama"
blacklist:
  - "cryptominer"
  - "/tmp/unknown_*"
```

Example plugin (`my_plugin.py`):

```python
def enrich(process_info):
    # process_info: dict (pid, name, exe, cmdline, cpu_percent, connections, container...)
    if process_info.get("cpu_percent", 0) > 80:
        return {"alert": "critical CPU usage"}
    return {}
```

Usage examples for the new modes:

```bash
# Continuous monitoring every 30 s, with a local whitelist
python3 process_analyzer_allinone.py --watch --interval 30 --config config.yaml
```

```bash
# Forensic report on a suspicious process
python3 process_analyzer_allinone.py --pid 1234 --no-enrich
```

```bash
# Full analysis with AI cache, retry, integrity check and comparison to the previous run
python3 process_analyzer_allinone.py --cache --retry-failed 3 --check-integrity --compare
```

Example for a scheduled run (cron), without AI enrichment but with a timestamped summary report and CSV export (the HTML is always generated):

```bash
python3 process_analyzer_allinone.py \
  --no-enrich \
  --html-output "/var/log/process_graph/graph_$(date +%Y%m%d_%H%M).html" \
  --report "/var/log/process_graph/report_$(date +%Y%m%d_%H%M).md" \
  --csv-export "/var/log/process_graph/data_$(date +%Y%m%d_%H%M).csv"
```

## Plugins: 38 ready-to-use security heuristics

Every file in `plugins/` is an independent `--plugin` module (`enrich(process_info) -> dict`, see [Advanced analysis](#advanced-analysis-and-enrichment)); load one, several, or all of them:

```bash
python3 process_analyzer_allinone.py --plugin "plugins/*.py"          # everything
python3 process_analyzer_allinone.py --plugin plugins/05_reverse_shell_cmdline_pattern.py --plugin plugins/29_powershell_encoded_command.py
```

Findings are surfaced in the 3D graph (legend section, alert/notice/info colouring, detail panel) and in the JSON/CSV exports. Plugin 31 correlates the others: several independent weak signals on one process escalate together. Lists that must be yours are loaded from files or environment variables, never hard-coded: `PMA_HASH_ALLOWLIST` (known-good SHA-256, plugin 12), `PROC_ANALYZER_HASH_BLOCKLIST` (plugin 33, template in `plugins/known_malicious_hashes.txt`), `PMA_OWNERSHIP_RULES` (plugin 23), `plugins/yara_rules/*.yar` (plugin 34, ships with the EICAR test rule only).

| # | Plugin | What it flags |
|---|---|---|
| 01 | `masquerading_system_process_name` | Flags a process whose NAME matches a well-known OS process but whose executable path is outside where that OS actually keeps it -- the classic "masquerading" trick (rename a payload to lo… |
| 02 | `running_from_temp_or_downloads` | Flags a process whose executable lives under a temp/downloads-style directory -- a common landing zone for freshly downloaded or dropped binaries. |
| 03 | `world_writable_binary` | Flags an executable that ANY local user can overwrite (group- or other-writable). |
| 04 | `deleted_binary_still_running` | Flags a process whose executable path no longer exists on disk while the process is still running -- normal after a package upgrade or a self-deleting installer, and also a known techniqu… |
| 05 | `reverse_shell_cmdline_pattern` | Flags a cmdline that matches one of the well-documented reverse-shell one-liners (bash /dev/tcp, nc -e, python socket+dup2, perl/php/socat variants, PowerShell hidden-window download-and-… |
| 06 | `lolbin_suspicious_usage` | Flags a "living-off-the-land binary" (a legitimate, pre-installed OS tool) invoked with flags from its well-documented abuse patterns -- downloading and running remote content, most often. |
| 07 | `base64_blob_in_cmdline` | Flags a suspiciously long base64-looking substring in the cmdline -- a common shape for an encoded payload handed to an interpreter (`python -c <b64>`, `powershell -enc <b64>`, etc). |
| 08 | `cloud_metadata_endpoint_contact` | Flags a connection to a cloud instance-metadata service (169.254.169.254, used by AWS/GCP/Azure/OpenStack/DigitalOcean, and Alibaba Cloud's 100.100.100.200). |
| 09 | `mining_pool_port_heuristic` | Flags a process combining sustained high CPU with an outbound connection on a port conventionally used by cryptocurrency mining pools (Stratum protocol). |
| 10 | `privileged_user_unprivileged_path` | Flags a process running as root/SYSTEM/admin whose executable sits under a directory normal users can write to (their home folder, Desktop, Downloads, /tmp) instead of a system location. |
| 11 | `macos_code_signature_check` | macOS only: runs `codesign --verify` against the executable to check whether its code signature is still intact. |
| 12 | `binary_sha256_fingerprint` | Computes the SHA256 of the executable and checks it against an optional local allow-list (one "hash name" line per entry, same convention as sha256sum -- see ALLOWLIST_PATH below). |
| 13 | `recently_modified_binary` | Flags an executable modified within the last N hours (default 24, override with PMA_RECENT_BINARY_HOURS). |
| 14 | `listening_on_all_interfaces` | Flags a process listening on 0.0.0.0 (or :: for IPv6) -- reachable from every network interface, not just localhost. |
| 15 | `high_connection_fanout` | Flags a process talking to an unusually large number of distinct remote endpoints at once -- the shape of a scanner, a proxy, a P2P client, or beaconing malware alike. |
| 16 | `unix_socket_in_shared_tmp` | Flags a UNIX-domain socket living under a world-readable shared directory (/tmp, /var/tmp, /dev/shm) rather than a private runtime directory. |
| 17 | `resource_pressure_score` | Replaces a crude "cpu > 80 => alert" with a graded 0-100 resource pressure score blending CPU and memory, plus a label -- so a process at 82% CPU / 1% mem and one at 45% CPU / 60% mem bot… |
| 18 | `process_status_via_psutil` | Looks up the live process STATUS (running / sleeping / zombie / stopped / disk-sleep...) via psutil, using only the pid from process_info -- an example of a plugin reaching beyond the fie… |
| 19 | `high_thread_or_fd_count` | Looks up live thread and (POSIX) file-descriptor counts via psutil -- another "reach beyond the given dict" example. |
| 20 | `working_directory_outside_expected_areas` | Flags a process whose working directory sits on removable/external media or another unusual mount point (a USB drive, a mounted disk image, an unexpected network share) rather than the sy… |
| 21 | `container_host_network_exposure` | Flags a containerized process that's also listening on 0.0.0.0 -- worth knowing because it usually means the container runs with `--net=host` (no network namespace isolation at all) or ha… |
| 22 | `docker_container_image_lookup` | If the process is containerized and the `docker` CLI is available, enriches with the image name/tag via `docker inspect` -- turning a bare container id into something readable. |
| 23 | `ownership_tagger_by_path_convention` | Turns a raw process list into an ownership-tagged inventory by matching `cwd`/`exe` against your own path conventions (e.g. |
| 24 | `outdated_interpreter_hint` | Flags a process whose cmdline invokes an end-of-life interpreter -- python2, old Ruby, old PHP. |
| 25 | `secrets_in_cmdline_scan` | Flags cmdlines that look like they carry a secret as a plain argument -- passwords, API keys, tokens passed via --flag=value, or a connection string with embedded credentials. |
| 26 | `executable_entropy` | Computes the Shannon entropy of the executable file on disk (0-8 bits/byte) -- a standard static-analysis proxy for "is this compressed or encrypted", since compressed/encrypted/packed da… |
| 27 | `code_cave_scan` | Scans the executable on disk for long runs of a single repeated byte (0x00 most commonly, also 0x90/NOP and 0xCC/INT3) -- the file-level shape of a "code cave": empty space inside a legit… |
| 28 | `parent_process_anomaly` | Flags a shell/interpreter spawned by a process that normally never spawns one: an office document viewer, a PDF reader, or a browser. |
| 29 | `powershell_encoded_command` | Flags PowerShell invoked with an encoded/obfuscated command -- the single most common shape of a PowerShell-based payload (Empire, Cobalt Strike, PowerSploit, and countless copy-pasted on… |
| 30 | `persistent_external_connection` | Flags a process that (a) has an external (non-loopback) network connection RIGHT NOW and (b) has already appeared, under the same exe+name, in several of the tool's own past runs (--histo… |
| 31 | `multi_plugin_correlation_score` | Meta-plugin: escalates when MULTIPLE independent --plugin findings co-occur on the same process. |
| 32 | `timestomping_detector` | Flags a file-modified-before-it-was-created inconsistency on the executable -- the file-level signature of "timestomping" (an attacker resetting mtime to an old date to blend a dropped bi… |
| 33 | `hash_blocklist_lookup` | Computes the SHA256 of the process's executable (same read-and-hash logic as the main script's --check-integrity / exe_sha256, but usable without enabling that whole feature) and looks it… |
| 34 | `yara_runner` | Runs every *.yar rule file in plugins/yara_rules/ against the process's executable on disk -- turns this into an actual static-signature scanner instead of only heuristics. |
| 35 | `removable_media_execution` | Flags a process running FROM a removable/external media mount point -- the classic BadUSB/autorun/"someone plugged in a drive" vector, and a pattern the existing path-based plugins (01, 0… |
| 36 | `env_var_secrets_scan` | Flags secret-shaped environment variable NAMES on a live process (AWS_SECRET_ACCESS_KEY, LD_PRELOAD, DATABASE_URL with embedded creds, etc.) -- the environment-variable counterpart to plu… |
| 37 | `git_repo_secret_scan` | If the process's cwd is (inside) a git repository, lists TRACKED filenames that look like committed secrets (.env, private keys, credentials.json, ...) -- a very common real-world leak (a… |
| 38 | `lsof_cross_reference` | Cross-analysis link detector via `lsof`: for a given process's exe (or, in --stream-focus-on mode, a scanned FILE's path), finds every OTHER live process that currently has that exact sam… |

Each plugin is 30–120 lines of standard-library Python with its rationale in the docstring — copy one as a template for your own heuristic.

## Security: rule engine + AI opinion

The displayed risk level is **no longer produced solely by the AI**. A deterministic rule engine (`compute_rule_based_risk`) first computes a level from observable signals, without depending on Ollama:

- executable launched from a temporary directory (`/tmp`, `/var/tmp`, `/dev/shm`);
- executable outside the standard system directories;
- executable marked `(deleted)` by the kernel (binary removed from disk after the process was launched);
- empty command line while a real executable is present (kernel threads, which have no executable, are never affected by this rule);
- process listening on all network interfaces (`0.0.0.0`);
- unusual volume of distinct external connections (more than 10);
- match against a **blacklist** pattern from `--config` (immediate "high" level);
- SHA256 fingerprint of the executable different from the known reference (with `--check-integrity`);
- abnormally high CPU or RAM compared to the process baseline (with `--baseline`, from 3 samples on).

A **whitelist** pattern from `--config` neutralizes only the *path* signals (temporary directory / outside standard directories) — the network, integrity and "deleted executable" signals always remain active.

Every triggered rule is **traced by name** (visible in the "Security" panel of the HTML and in the report/CSV), never an opaque score. If Ollama is available, its opinion is combined **by escalation only**: the final level kept is the higher of the two (rules or AI), never the lower — underestimating a risk is considered worse than overestimating it. A divergence between the two opinions is flagged explicitly rather than hidden.

**This rule engine remains an educational and triage-assistance tool, not an antivirus or an EDR**: it has no signature database, performs no behavioral analysis over time, and can just as easily miss a real threat as flag a false positive (e.g. a legitimate development tool launched from `/tmp`). Use it as a starting point for investigation, not as a final verdict.

## Ollama integration

Enrichment asks a local Ollama model to categorize each significant process (category, probable role, risk level, justification, educational explanation) and returns structured JSON.

**Model detection**: via the HTTP API (`GET /api/tags`), never via the `ollama list` command — this avoids depending on the `ollama` binary being on the `PATH`, which remains valid once the script is compiled into an executable.

**Pre-flight check**: before starting the enrichment loop, the script verifies once that the requested model actually exists (tolerant `name` / `name:tag` comparison). A misspelled model name therefore fails immediately with a clear message, rather than producing a repeated error on every process.

**Automatic Ollama installation** (wizard only, with explicit consent — never silent):

| OS | Method |
|---|---|
| macOS | `brew install ollama` if Homebrew is available, otherwise opens the official download page |
| Linux | official script `curl -fsSL https://ollama.com/install.sh \| sh` |
| Windows | download then launch of `OllamaSetup.exe` |

**Model download**: if Ollama is running but no model is installed, the script offers to download `llama3:latest` via `POST /api/pull` (streamed, with a progress bar).

**Call reliability**: a "warm-up" call (small throwaway prompt) is sent once before the loop to force the model to load into memory — without it, several simultaneous calls can all queue up behind a model still loading and time out together. The default parallelism is deliberately modest (`--max-workers 2`) because a local LLM most often serves requests sequentially (a single GPU/CPU): more parallelism speeds nothing up and only piles up requests until they time out.

## The interactive 3D graph

Self-contained HTML file (embedded CSS/JS), navigable with the mouse (drag to orbit, wheel to zoom, click a node for details). Five display modes, selectable at the top of the screen:

- **Type** — colors each process by the category detected by the AI (browser, system service, dev-tool, database, network).
- **Security** (default) — colors by final risk level, with a detailed panel listing the rule-based level, the AI opinion if any, a "diverging opinions" badge in case of disagreement, external connections, and any incomplete-collection fields (denied permissions).
- **Debug** — color gradient based on CPU+RAM load, panel with the raw technical fields (PID, executable, command line, connections).
- **Verbose info** — full dump of all known fields for the selected item.
- **Knowledge** — educational explanation of the process's role (generated by Ollama if enriched, otherwise taken from a small built-in local knowledge base for common system processes).

A clickable legend lets you hide/show entire categories, including a "Display" section with a **"Low-activity processes"** entry, hidden by default: a process with a low connection degree, low CPU+RAM and low final risk is hidden at load time to keep the graph readable even with 150 processes — never a process whose risk is not "low", regardless of its activity. A search field highlights matching nodes.

Camera controls (bottom right, or via keyboard):

| Action | Button | Keyboard |
|---|---|---|
| Zoom in | `+` | `Ctrl` + `+` |
| Zoom out | `–` | `Ctrl` + `-` |
| Recenter | `⟲` | `R` or `Ctrl` + `R` |
| Close panel | `✕` | `Esc` |
| Focus search | — | `/` |
| Switch mode | top buttons | `1` to `5` |

The detail panel offers **"copy" buttons** (PID, executable path, full command line, ready-to-paste `kill <pid>` command, SHA256 if `--check-integrity`) to speed up moving to investigation in a terminal — the `kill` command is only copied, never executed by the page.

Links are colored by relationship type: parent → child, shared file, and by network protocol (TCP/UDP/UNIX) — all colors have been validated to remain distinguishable with color blindness and normal vision.

## Output files

| File | Generated by default? | Content |
|---|---|---|
| `process_graph_3d_*.html` | **Yes, always** (unless `--no-html`) | Interactive graph — opens in any browser, no installation required on the recipient's side. Requires an internet connection at opening time to load the 3D library from a CDN. The only file opened automatically in wizard mode. |
| `process_graph_*.png` | No — option `--png` | Static render of the full graph, with legend, for archiving or quick sharing. |
| `process_data_*.json` | No — option `--json-export` | Raw export of all collected data, of the risk (rules + AI) and of the enrichment, for external processing (Excel, database, another script). |
| `*.csv` | No — option `--csv-export` | One line per process, flattened fields (final risk, triggered rules, AI opinion, incomplete collection…), for direct opening in a spreadsheet. |
| `report_*.md` | No — option `--report` | Executive summary in Markdown: risk distribution, top consumers, external connections, high-risk processes, diverging opinions, incomplete collection, AI enrichment statistics. |

## Building an executable (PyInstaller)

Reproducible build, one command:

```bash
./build.sh            # macOS / Linux  ->  dist/ProcessAnalyzer  (+ .sha256)
```

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1   # Windows -> dist\ProcessAnalyzer.exe (+ .sha256)
```

What the script does, in order (every step is printed): dedicated `.venv-build/` → `pip install -r requirements_frozen.txt -r requirements_build.txt` (runtime deps and PyInstaller both pinned) → `compile_check.py` → PyInstaller with the flags below → **smoke test** (the freshly built executable runs a real `--no-enrich` analysis on 5 processes and must produce a non-empty HTML; `--skip-smoke` / `-SkipSmoke` to bypass on a headless CI) → SHA-256 written next to the artifact. Refuses to run on Android/Termux (PyInstaller does not target it). `build.ps1` mirrors `build.sh` but was written without a Windows machine: syntax-reviewed, not executed — report the printed failing step if it breaks.

The equivalent manual commands (what `build.sh` runs):

```bash
pip install -r requirements_frozen.txt -r requirements_build.txt
pyinstaller --onefile --console --name ProcessAnalyzer \
  --collect-all psutil \
  --collect-submodules matplotlib \
  process_analyzer_allinone.py
```

The executable is produced in `dist/`. Important points:

- **First install all the dependencies (`pip install -r requirements_frozen.txt`) in the SAME environment/venv as the one where you run `pyinstaller`** (`build.sh` does exactly that in `.venv-build/`). PyInstaller only bundles what it sees installed locally at build time — it cannot guess what the script would install on its own during a raw `.py` launch.
- **`--collect-all psutil` is mandatory**, not just recommended: psutil ships an OS-specific compiled extension (`_psutil_osx` / `_psutil_linux` / `_psutil_windows`) that PyInstaller does not always detect on its own. Without this flag, the executable compiles without error but crashes immediately at runtime with `ERROR: missing module(s) in the executable: psutil` (bug encountered and fixed — this flag is what solves it).
- **`--console` is mandatory**: the interactive wizard and the pause before the window closes need it.
- PyInstaller **does not cross-compile**: the command must be run on the same OS as the one targeted (building on macOS produces a macOS binary, etc.).
- In a compiled executable, a missing Python dependency is **no longer** installed automatically (that would be a build bug, not something to fix at runtime) — the script prints a clear message and stops cleanly instead of crashing without explanation.
- On macOS, the unsigned binary will likely be blocked by Gatekeeper on first launch ("unidentified developer"): right-click → Open, or `xattr -cr dist/ProcessAnalyzer` in the Terminal.
- This build configuration (with `--collect-all psutil`) was tested successfully (real build + real execution against real system processes, PNG/HTML/JSON generated correctly) on Linux; no missing dependency detected for psutil/networkx/matplotlib/requests with this set of flags. If ANOTHER module reports a "missing" error at runtime, first check that it is actually installed in the environment used to run `pyinstaller` before adding an extra `--collect-all` for it.

## Android / Termux support

`psutil` has no wheel for Android and installing it from source fails explicitly (`platform android is not supported`) — installing PyInstaller or compiling anything will not change that; it is not an environment problem but a limitation of the library itself.

The script works around this automatically: on Android/Termux (detected via the Android environment variables or the presence of `/system/build.prop`), `psutil` is replaced by an internal backend that reads `/proc/<pid>/*` directly — the same principle as what `psutil` does internally on Linux. No special installation is needed; the script detects the platform on its own and switches over.

**Usage on Termux**:

```bash
pkg install python
python process_analyzer_allinone.py
```

**AI enrichment on Termux**: the Termux repositories provide an `ollama` package — `install.sh` (and the script's novice wizard) attempts to install it automatically, then downloads the **mini** model `llama3.2:1b` (~1.3 GB), suited to a mobile device's RAM and storage (desktop machines get the medium model `llama3:latest`). If the package is not available in your Termux version, the analysis simply continues without AI:

```bash
pkg install ollama
ollama serve &
ollama pull llama3.2:1b
```

`networkx` and `requests` install normally via pip. If the automatic installation of **matplotlib** fails (missing build dependencies — common on Termux), use the precompiled package instead:

```bash
pkg install matplotlib
```

**No compilation possible on Android**: PyInstaller does not target Android/Termux, so there is no `.apk`/binary executable to produce here — the script runs directly via `python process_analyzer_allinone.py`, exactly like any Python script on Termux.

**Limitations specific to this mode** (documented in the script, H14/H15/H16), all tied to Android's own restrictions, not to this script:
- Without root, Android natively limits visibility to the current user's processes (SELinux / `hidepid`) — other applications' processes simply appear invisible or as access denied, never as an error.
- The CPU% is an average since the process started (cumulative CPU time ÷ process age), not a real-time snapshot as with `psutil` — sufficient for prioritizing/sorting processes, not for precise load monitoring.
- Only **IPv4** TCP/UDP connections and UNIX sockets are detected; IPv6 connections are not decoded by this lightweight backend.

This backend was tested under real conditions (real analysis of system processes, real detection of network connections via `/proc/net/*`, full PNG/HTML/JSON generation) on a Linux machine with Android detection forced — the observed behavior was consistent with a classic `psutil` collection on the same machine (same order of magnitude of processes, correct PID/PPID/CPU/memory).

## Privacy

- All the analysis (processes, files, connections) happens **locally**; no data is sent to any external service by the script itself.
- Enrichment calls go to the configured Ollama URL (`http://localhost:11434` by default) — so locally, unless the user explicitly configures a remote host via `--ollama-host`.
- The 3D graph HTML file loads the rendering library (`3d-force-graph`) from a public CDN (`unpkg.com`) when opened — this is the only point of contact with the outside world once the files are generated. Without a connection, the file shows an explicit error message rather than a blank screen.
- Command data (`cmdline`) and other process text inserted into the HTML are escaped to prevent any script injection.

## Known limitations

- On macOS, listing the network connections of a process not owned by the current user requires administrator rights (`sudo`) — without them, those processes simply appear with 0 visible connections (not an error).
- A large Ollama model (e.g. `llama3:latest`, several GB) can take time to load into memory and to generate a response on modest hardware (CPU only) — the default timeouts were calibrated generously for this reason.
- The 3D graph requires an internet connection at opening time (rendering library loaded from a CDN); the PNG and the JSON, on the other hand, are fully usable offline.
- On Android/Termux, the displayed CPU% is an average since the process started (not a real-time snapshot) and only IPv4/UNIX connections are detected — see [Android / Termux support](#android--termux-support) for details.

## Troubleshooting

| Symptom | Probable cause | Solution |
|---|---|---|
| Repeated `Timeout Ollama` | Too many parallel requests for a local model that serves sequentially | Reduce `--max-workers` (already 2 by default) and/or increase `--timeout` |
| `404` on a model | Misspelled model name | Check the actual list with `ollama list` or let the wizard list the available models |
| "externally-managed-environment" error while installing dependencies | Protected Python environment (PEP 668) | The script automatically retries with `--break-system-packages`; otherwise use a virtual environment (`python3 -m venv`) |
| Empty 3D graph / loading error | No internet connection when the HTML was opened | Reconnect then reload the page |
| Window closing instantly (compiled executable) | Should no longer happen — a pause before closing is built in | Check that the build actually used `--console` |
| `ERROR: missing module(s) in the executable: psutil` (or another module) when launching the executable | PyInstaller did not bundle the module's compiled extension (common with psutil on macOS), or the module was not installed in the environment used to build | Rebuild with `--collect-all psutil` (see the build section); for another module, first check `pip show <module>` in the environment used to run `pyinstaller` |

## Design assumptions

The script documents in its header (docstring, "Assumptions made" section) all the default values chosen in the absence of explicit specification: default Ollama model and host, graph truncation thresholds (always logged, never silent), behavior on denied permissions, calibration of the Ollama timeouts and parallelism, and the conditions triggering the interactive wizard versus command-line mode. Refer directly to the `process_analyzer_allinone.py` file for the exhaustive, up-to-date details.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Ellana.
