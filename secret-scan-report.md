# Secret scan — /home/claude/process_graph_tool

Scope: all text files in the folder (`process_analyzer_allinone.py`, `process_graph_analyzer.py`, `README.md`, `ENRICHMENT_PLAN.md`, `Analyze_Processes.command`, `Install_and_Run.command`, `install.sh`, `install.ps1`, `demo_data.json`, `demo_graph_3d.html`), plus a dedicated search for inherently risky files (`.env`, `*.pem`, `*.key`, `id_rsa*`, `credentials.json`).

Note: this folder is still not a git repository (`git status` → `fatal: not a git repository`), so the analysis covers all files in the directory rather than `git ls-files`. Update to the previous pass (08/12, 12:48): adds `install.sh` and `install.ps1` to the scope, new since then.

## Secrets detected (values never shown in plaintext)

**None** — pattern search (AWS keys `AKIA...`, `sk-...` keys, GitHub tokens `ghp_...`, Slack tokens `xox...`, `-----BEGIN PRIVATE KEY-----` blocks, `*_KEY`/`*_SECRET`/`*_TOKEN`/`*_PASSWORD`/`*_CREDENTIAL` variables assigned a value) across the source code, installers, and documentation: no matches. `install.sh`/`install.ps1` only download official public installers (Ollama, Python) and embed no credentials.

## False positives dismissed

| File | Pattern matched | Why it's not a real secret |
|---|---|---|
| `secret-scan-report.md` (previous version) | `AKIA...`, `sk-...`, `ghp_...`, `xox...` | These are the search patterns themselves, spelled out in the report to describe the method — not values found in the code. |

## Out-of-scope finding: real data captured in demo files (still present, unresolved)

Carried over from the previous pass, status unchanged — `demo_data.json` and `demo_graph_3d.html` still contain real data from this development machine (two real, publicly observed public IP addresses, a real system username, real internal executable paths). This is not an exploitable secret in the classic sense, but publishing these files as-is contradicts the project's "everything stays local" angle. Full detail in this report's history (not reproduced here to avoid further scattering the data) or by reading the files themselves directly.

**Recommendation unchanged**: regenerate these three demo files (`demo_data.json`, `demo_graph_3d.html`, `demo_graph.png`) with anonymized data before any public release, or exclude them from a future git repository via `.gitignore`.

## Risky files not tracked in .gitignore

Still no `.gitignore` (no git repository yet). If `github-repo-bootstrapper` is used to initialize the repository, plan to exclude at minimum:

| File / pattern | Recommendation |
|---|---|
| `outputs/` | Timestamped output folder generated on every run (real HTML/PNG/JSON/CSV from the user's machine) — must never be committed. |
| `.venv/` | Virtual environment created by `install.sh` / `install.ps1` — local to each machine. |
| `build/`, `dist/`, `*.spec` | PyInstaller artifacts. |
| `__pycache__/`, `*.pyc` | Python cache (already present in this working folder). |
| `demo_data.json`, `demo_graph_3d.html`, `demo_graph.png` | To be regenerated with clean data before publication (see above) rather than permanently excluded — these are useful examples for the project. |

## Summary

No exploitable secret/credential found in the code, installers, or documentation, including in the two new `install.sh`/`install.ps1` scripts. The only point of attention remains, unchanged since the previous pass, the content of the three demo files that reflect a real run on this development machine — to be regenerated cleanly before any public release or before using `github-repo-bootstrapper`/`github-repo-promoter` to prepare a repository intended to be public.
