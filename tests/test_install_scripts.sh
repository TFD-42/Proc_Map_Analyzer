#!/usr/bin/env bash
#
# tests/test_install_scripts.sh — verification harness for the install /
# reinstall / build scripts. Everything runs on a COPY of the project in
# $TMPDIR, so the real tree (and its .venv) is never touched.
#
# Checks:
#   1. every shell script parses (bash -n)
#   2. compile_check.py exits 0 on the shipped code
#   3. PMA_SKIP_OLLAMA=1 ./install.sh --install-only  exits 0, creates .venv,
#      does NOT launch the analyzer (no outputs/), writes NO __pycache__
#   4. every pin of requirements_frozen.txt is installed at exactly that
#      version in the venv (pip freeze) -> the install is reproducible
#   5. ./reinstall.sh recreates the venv from scratch and exits 0
#   6. (only with --with-build) ./build.sh produces dist/ProcessAnalyzer,
#      its .sha256, and passes its own smoke test
#
# Usage:
#   tests/test_install_scripts.sh               # ~1-2 min (pip downloads)
#   tests/test_install_scripts.sh --with-build  # + PyInstaller build, several min
#
# Exit code: 0 if every check passed, 1 otherwise. Ollama is never touched.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WITH_BUILD=0
[ "${1:-}" = "--with-build" ] && WITH_BUILD=1

WORK="$(mktemp -d "${TMPDIR:-/tmp}/pma_install_test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
COPY="$WORK/Proc_Map_Analyzer"

PASS=0; FAIL=0
ok()   { PASS=$((PASS + 1)); printf '  \033[1;32mPASS\033[0m %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); printf '  \033[1;31mFAIL\033[0m %s\n' "$1"; }
section() { printf '\n\033[1;34m== %s\033[0m\n' "$1"; }

section "1. shell syntax (bash -n)"
for f in install.sh reinstall.sh build.sh Install_and_Run.command Analyze_Processes.command tests/test_install_scripts.sh; do
    if bash -n "$ROOT/$f" 2>/dev/null; then ok "$f"; else fail "$f does not parse"; fi
done

section "2. compile_check.py on the shipped code"
if python3 "$ROOT/compile_check.py"; then ok "compile_check.py exit 0"; else fail "compile_check.py reported errors"; fi

section "3. isolated copy + install.sh --install-only (PMA_SKIP_OLLAMA=1)"
mkdir -p "$COPY"
rsync -a --exclude='.git/' --exclude='.venv/' --exclude='.venv-build/' --exclude='build/' --exclude='dist/' \
      --exclude='outputs/' --exclude='__pycache__/' --exclude='.DS_Store' "$ROOT/" "$COPY/"
echo "  copy: $COPY"
INSTALL_LOG="$WORK/install.log"
if (cd "$COPY" && PMA_SKIP_OLLAMA=1 ./install.sh --install-only >"$INSTALL_LOG" 2>&1); then
    ok "install.sh --install-only exit 0"
else
    fail "install.sh --install-only failed — last 30 lines:"; tail -30 "$INSTALL_LOG" | sed 's/^/      /'
fi
[ -x "$COPY/.venv/bin/python" ] && ok ".venv created" || fail ".venv/bin/python missing"
grep -q "Using pinned versions from requirements_frozen.txt" "$INSTALL_LOG" && ok "pinned requirements_frozen.txt used" || fail "install did not use requirements_frozen.txt"
grep -q "compile check: .* files OK" "$INSTALL_LOG" && ok "compile check ran" || fail "compile check did not run"
grep -q "Step 7/7 skipped" "$INSTALL_LOG" && ok "analyzer NOT launched (--install-only honoured)" || fail "--install-only not honoured"
[ ! -d "$COPY/outputs" ] && ok "no outputs/ created (nothing ran)" || fail "outputs/ appeared: something was executed"
if [ -z "$(find "$COPY" -name __pycache__ -not -path "$COPY/.venv/*" 2>/dev/null)" ]; then ok "no __pycache__ written in the tree"; else fail "__pycache__ found in the tree"; fi
grep -qE 'Installing Ollama|Downloading model|Starting the Ollama server|ollama pull' "$INSTALL_LOG" && fail "Ollama was touched despite PMA_SKIP_OLLAMA=1" || ok "Ollama untouched"

section "4. reproducibility: pip freeze == requirements_frozen.txt"
if [ -x "$COPY/.venv/bin/python" ]; then
    FROZEN_NOW="$("$COPY/.venv/bin/python" -m pip freeze 2>/dev/null | tr 'A-Z_' 'a-z-')"
    MISSING=0
    while IFS= read -r line; do
        line="${line%%#*}"; line="$(echo "$line" | tr -d '[:space:]' | tr 'A-Z_' 'a-z-')"
        [ -z "$line" ] && continue
        if ! grep -qx "$line" <<<"$FROZEN_NOW"; then MISSING=$((MISSING + 1)); echo "      not at pinned version: $line"; fi
    done < "$ROOT/requirements_frozen.txt"
    [ "$MISSING" -eq 0 ] && ok "every pin installed at the exact pinned version" || fail "$MISSING pin(s) differ from requirements_frozen.txt"
else
    fail "skipped (no venv)"
fi

section "5. reinstall.sh"
touch "$COPY/.venv/MARKER_OLD_VENV"
REINSTALL_LOG="$WORK/reinstall.log"
if (cd "$COPY" && PMA_SKIP_OLLAMA=1 ./reinstall.sh >"$REINSTALL_LOG" 2>&1); then ok "reinstall.sh exit 0"; else fail "reinstall.sh failed — last 20 lines:"; tail -20 "$REINSTALL_LOG" | sed 's/^/      /'; fi
[ ! -f "$COPY/.venv/MARKER_OLD_VENV" ] && [ -x "$COPY/.venv/bin/python" ] && ok "venv really recreated from scratch" || fail "old venv survived reinstall"

if [ "$WITH_BUILD" = "1" ]; then
    section "6. build.sh (PyInstaller, pinned)"
    BUILD_LOG="$WORK/build.log"
    if (cd "$COPY" && ./build.sh >"$BUILD_LOG" 2>&1); then ok "build.sh exit 0 (includes its own smoke test)"; else fail "build.sh failed — last 30 lines:"; tail -30 "$BUILD_LOG" | sed 's/^/      /'; fi
    [ -x "$COPY/dist/ProcessAnalyzer" ] && ok "dist/ProcessAnalyzer produced ($(du -h "$COPY/dist/ProcessAnalyzer" 2>/dev/null | cut -f1))" || fail "dist/ProcessAnalyzer missing"
    [ -s "$COPY/dist/ProcessAnalyzer.sha256" ] && ok "dist/ProcessAnalyzer.sha256 written" || fail "checksum file missing"
    grep -q "Smoke test OK" "$BUILD_LOG" && ok "built executable ran a real analysis" || fail "smoke test did not pass"
else
    section "6. build.sh — skipped (pass --with-build to run it)"
fi

printf '\n\033[1m%d passed, %d failed\033[0m\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
