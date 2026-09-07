#!/usr/bin/env bash
#
# reinstall.sh — rebuild the Python environment from scratch, reproducibly.
#
# What it does, and nothing else:
#   1. deletes .venv/ (the ONLY thing it deletes — never your outputs/, never
#      the code)
#   2. removes any stale __pycache__/ left by a previous Python run
#   3. re-runs ./install.sh --install-only, which recreates .venv from
#      requirements_frozen.txt (exact pinned versions) and compile-checks the
#      code. Nothing is launched.
#
# Ollama is left untouched unless install.sh decides it is missing; export
# PMA_SKIP_OLLAMA=1 to guarantee nothing AI-related is installed or fetched.
#
# Usage:
#   ./reinstall.sh
#   PMA_SKIP_OLLAMA=1 ./reinstall.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -f "$SCRIPT_DIR/install.sh" ]; then
    printf '\033[1;31m[error]\033[0m install.sh not found next to reinstall.sh (%s). Aborting.\n' "$SCRIPT_DIR" >&2
    exit 1
fi

if [ -d "$VENV_DIR" ]; then
    printf '\033[1;34m[reinstall]\033[0m removing %s\n' "$VENV_DIR"
    rm -rf "$VENV_DIR"
fi

# Stale bytecode from a previous run (never shipped, never needed).
find "$SCRIPT_DIR" -type d -name __pycache__ -not -path '*/.git/*' -prune -exec rm -rf {} + 2>/dev/null

printf '\033[1;34m[reinstall]\033[0m running ./install.sh --install-only\n'
exec "$SCRIPT_DIR/install.sh" --install-only "$@"
