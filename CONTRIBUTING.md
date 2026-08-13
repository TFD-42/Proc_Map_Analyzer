# Contributing to System Process Analyzer

Thanks for your interest in this project. This document explains how to set up locally and how changes are validated — staying honest about what actually exists today (no automated test suite yet, see below).

## Installation

Easiest: use the provided installer, which handles Ollama, the default model, Python, the virtual environment, and dependencies in a single command (see the README, "Automatic installation" section):

```bash
# macOS / Linux / Android-Termux
chmod +x install.sh && ./install.sh

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File install.ps1
```

Equivalent manual installation:

```bash
git clone <repo-URL>   # once this project is actually pushed to GitHub
cd process_graph_tool
python3 -m venv .venv
source .venv/bin/activate   # .venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt   # remove psutil on Android/Termux, see requirements.txt
```

## Validating a change (no automated test suite yet)

There is no unit test suite (`pytest`) yet — this is an identified item in [`ENRICHMENT_PLAN.md`](ENRICHMENT_PLAN.md) (Maintenance section, item 14), deliberately left on the roadmap rather than rushed. In the meantime, every change must at minimum pass:

```bash
# Syntax check
python3 -m py_compile process_analyzer_allinone.py

# Real execution test, fast and without an Ollama dependency
python3 process_analyzer_allinone.py --no-enrich --max-processes 30
```

Then check the generated HTML file (open it in a browser: the 5 display modes, the legend, search, keyboard shortcuts `Ctrl+R`/`Ctrl+`/`Ctrl-`) before opening a pull request that touches rendering.

## Code style

No linter configured for now (no `ruff`/`flake8` in CI) — stay consistent with the file's existing style: comments and docstrings in English, explicit error handling (never a silent `except Exception: pass` without a comment justifying why), and documentation of design choices not directly specified by the user in the script's header docstring ("Assumptions made" section, `H1`, `H2`, etc.) rather than buried in function comments.

## Commit conventions

No strict convention enforced (no mandatory `feat:`/`fix:` today) — write clear, imperative-mood messages that explain the *why* of the change, not just the *what*.

## Pull request process

1. Create a branch from the default branch (`main`).
2. Make the change, keeping `process_analyzer_allinone.py` as a single self-contained file (this is a deliberate project constraint, to remain buildable as a single PyInstaller executable — see the header docstring).
3. Verify with the commands from the previous section.
4. Open a pull request using the provided template, describing what changes and why.
5. A review and passing CI are required before merging (see the branch protection configuration, to be enabled once the repository is pushed to GitHub).

## Reporting a bug / proposing a feature

Use the [issue templates](.github/ISSUE_TEMPLATE/) once the repository is on GitHub — they collect the information needed to triage quickly.

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to abide by it.
