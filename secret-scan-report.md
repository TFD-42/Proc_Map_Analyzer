# Secret scan — Proc_Map_Analyzer

Scope: all tracked source/doc/config files in the repository root (`process_analyzer_allinone.py`, `README.md`, `ENRICHMENT_PLAN.md`, `CHANGELOG.md`, `STATUS.md`, `CONTRIBUTING.md`, `SECURITY.md`, `Analyze_Processes.command`, `Install_and_Run.command`, `install.sh`, `install.ps1`, `.github/workflows/ci.yml`), plus a dedicated search for inherently risky files (`.env`, `*.pem`, `*.key`, `id_rsa*`, `credentials.json`).

Update to the previous pass: the project is now a git repository (previously it was not); `process_graph_analyzer.py` was removed (consolidated into `process_analyzer_allinone.py`, the sole generator going forward) and is no longer in scope.

## Secrets detected (values never shown in plaintext)

**None** — pattern search (AWS keys `AKIA...`, `sk-...` keys, GitHub tokens `ghp_...`, `*_KEY`/`*_SECRET`/`*_TOKEN`/`*_PASSWORD`/`*_CREDENTIAL` variables assigned a value, hardcoded private IPs) across the source code, installers, CI config, and documentation: no matches.

## False positives dismissed

| File | Pattern matched | Why it's not a real secret |
|---|---|---|
| `process_analyzer_allinone.py` | `data-key="cat_system_service"` and similar HTML attributes | `data-key` is a DOM attribute name for the graph's legend/filter UI (category labels like `cat_dev-tool`, `low_interest`), not a credential variable. |

## Previously flagged, now resolved

The prior pass (from before this project was moved into a git repo) flagged `demo_data.json` / `demo_graph_3d.html` / `demo_graph.png` as containing non-anonymized real data (public IPs, a real username, real local paths) from a development machine, with a recommendation to regenerate them clean or exclude them before any public release.

Current state: these files are **not present** in this working tree, and `.gitignore` explicitly excludes `demo_data.json`, `demo_graph.png`, and `demo_graph_3d.html` by name (with a comment pointing back to this report), so they cannot be committed as-is even if regenerated locally. No action needed unless these files are reintroduced without anonymization.

## Risky files not tracked in .gitignore

None outstanding — `.gitignore` already excludes real-data outputs (`outputs/`, `process_graph_3d*.html`, `process_graph*.png`, `process_data*.json`, `*.csv`, `rapport_*.md`), the demo files above, the venv, build artifacts, and internal working files (`promotion-report.md`, `.claude/`).

## Summary

No exploitable secret or credential found in the code, installers, CI config, or documentation. The one prior open item (non-anonymized demo files) is resolved: the files aren't present, and `.gitignore` prevents them from being committed as-is if regenerated. Repository is clean for the intended push / public-facing promotion pass.
