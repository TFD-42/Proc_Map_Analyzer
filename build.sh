#!/usr/bin/env bash
#
# build.sh — reproducible PyInstaller build of process_analyzer_allinone.py
# (macOS and Linux; Windows uses build.ps1; Android/Termux cannot build —
# PyInstaller does not target it, the script runs as plain .py there).
#
# Steps (each printed as it runs, nothing hidden):
#   1. Platform check (refuses Android explicitly)
#   2. Dedicated build venv  .venv-build/  (separate from the runtime .venv so
#      PyInstaller never leaks into it)
#   3. Pinned dependencies: requirements_frozen.txt (runtime, exact versions)
#      + requirements_build.txt (pyinstaller, exact version)
#   4. Compile check (compile_check.py, in memory)
#   5. pyinstaller --onefile --console --collect-all psutil
#      --collect-submodules matplotlib   (the flag set documented in the
#      README; --collect-all psutil is mandatory, see README "Building an
#      executable")
#   6. Smoke test: the freshly built executable runs a real short analysis
#      (--no-enrich, 5 processes, HTML only) and the HTML must be non-empty
#   7. SHA-256 of the artifact written next to it (dist/ProcessAnalyzer.sha256)
#
# Usage:
#   ./build.sh                # full build + smoke test
#   ./build.sh --skip-smoke   # build only (e.g. headless CI without /proc access)
#
# Output: dist/ProcessAnalyzer  (+ .sha256).  Work files in build/ (safe to
# delete). Both dirs are git-ignored.
# PyInstaller does not cross-compile: run this ON the OS you target.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/process_analyzer_allinone.py"
BUILD_VENV="$SCRIPT_DIR/.venv-build"
REQ_FROZEN="$SCRIPT_DIR/requirements_frozen.txt"
REQ_BUILD="$SCRIPT_DIR/requirements_build.txt"
DIST_DIR="$SCRIPT_DIR/dist"
WORK_DIR="$SCRIPT_DIR/build"
APP_NAME="ProcessAnalyzer"
TMP_DIR="${TMPDIR:-/tmp}"
SKIP_SMOKE=0

log()  { printf '\n\033[1;34m[build]\033[0m %s\n' "$1"; }
err()  { printf '\033[1;31m[error]\033[0m %s\n' "$1" >&2; }

for arg in "$@"; do
    case "$arg" in
        --skip-smoke) SKIP_SMOKE=1 ;;
        -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
        *) err "Unknown argument: $arg (see --help)"; exit 2 ;;
    esac
done

# 1. Platform ---------------------------------------------------------------
if [ -n "${ANDROID_ROOT:-}" ] || [ -n "${ANDROID_DATA:-}" ] || [[ "${PREFIX:-}" == *com.termux* ]] || [ -f /system/build.prop ]; then
    err "Android/Termux detected: PyInstaller does not target Android, no executable can be built here."
    err "Run the script directly instead:  ./install.sh   (see README, 'Android / Termux support')."
    exit 2
fi
for f in "$PY_SCRIPT" "$REQ_FROZEN" "$REQ_BUILD" "$SCRIPT_DIR/compile_check.py"; do
    [ -f "$f" ] || { err "Missing file: $f"; exit 1; }
done
log "Platform: $(uname -s) $(uname -m)"

# 2. Python + build venv ----------------------------------------------------
PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && [ "$("$candidate" -c 'import sys; print(sys.version_info[0])' 2>/dev/null)" = "3" ]; then
        PYTHON_BIN="$candidate"; break
    fi
done
[ -n "$PYTHON_BIN" ] || { err "Python 3 not found. Run ./install.sh first (it installs Python)."; exit 1; }
log "Python: $("$PYTHON_BIN" --version 2>&1) ($(command -v "$PYTHON_BIN"))"

PY_MINOR="$("$PYTHON_BIN" -c 'import sys; print(sys.version_info[1])' 2>/dev/null || echo 0)"
if [ "$PY_MINOR" -lt 10 ] 2>/dev/null; then
    err "Python 3.10+ is required since v0.3.0 (found $("$PYTHON_BIN" --version 2>&1)): requirements_frozen.txt pins Pillow/requests/urllib3 versions that dropped Python 3.9 support upstream."
    err "Install a newer Python so it is first on PATH as python3, then rerun this script."
    exit 1
fi

if [ ! -x "$BUILD_VENV/bin/python" ]; then
    log "Creating build venv: $BUILD_VENV"
    "$PYTHON_BIN" -m venv "$BUILD_VENV" || { err "venv creation failed (python3-venv installed?)"; exit 1; }
else
    log "Reusing build venv: $BUILD_VENV"
fi
VPY="$BUILD_VENV/bin/python"

# 3. Pinned dependencies ----------------------------------------------------
log "Installing pinned dependencies:  pip install -r requirements_frozen.txt -r requirements_build.txt"
"$VPY" -m pip install --upgrade pip --quiet
"$VPY" -m pip install --quiet -r "$REQ_FROZEN" -r "$REQ_BUILD" || { err "pip install failed (see above)."; exit 1; }
log "PyInstaller: $("$VPY" -m PyInstaller --version 2>/dev/null)"

# 4. Compile check ----------------------------------------------------------
log "Compile check"
"$VPY" "$SCRIPT_DIR/compile_check.py" || { err "Compile check failed — not building."; exit 1; }

# 5. Build ------------------------------------------------------------------
log "Running PyInstaller (this takes a minute or two)"
rm -rf "$WORK_DIR" "$DIST_DIR/$APP_NAME" "$DIST_DIR/$APP_NAME.sha256"
set -x
"$VPY" -m PyInstaller --clean --noconfirm --onefile --console --name "$APP_NAME" \
    --collect-all psutil \
    --collect-submodules matplotlib \
    --distpath "$DIST_DIR" --workpath "$WORK_DIR" --specpath "$WORK_DIR" \
    "$PY_SCRIPT"
STATUS=$?
set +x
[ "$STATUS" -eq 0 ] || { err "PyInstaller failed (exit $STATUS)."; exit "$STATUS"; }
EXE="$DIST_DIR/$APP_NAME"
[ -x "$EXE" ] || { err "Build finished but $EXE is missing."; exit 1; }
log "Built: $EXE ($(du -h "$EXE" | cut -f1))"

# 6. Smoke test -------------------------------------------------------------
if [ "$SKIP_SMOKE" = "1" ]; then
    log "Smoke test skipped (--skip-smoke)."
else
    SMOKE_HTML="$TMP_DIR/pma_build_smoke.$$.html"
    log "Smoke test:  $EXE --no-enrich --max-processes 5 --html-output $SMOKE_HTML"
    # stdin closed on purpose: a frozen executable pauses on "Press Enter to
    # close this window..." before exiting (wizard-friendly), which would hang
    # an unattended build forever. </dev/null makes that input() return at once.
    if "$EXE" --no-enrich --max-processes 5 --html-output "$SMOKE_HTML" </dev/null >/dev/null 2>&1 && [ -s "$SMOKE_HTML" ]; then
        log "Smoke test OK (HTML produced: $(du -h "$SMOKE_HTML" | cut -f1))"
        rm -f "$SMOKE_HTML"
    else
        err "Smoke test FAILED: the executable did not produce a non-empty HTML. Re-run without >/dev/null to see its output:"
        err "  $EXE --no-enrich --max-processes 5 --html-output $SMOKE_HTML </dev/null"
        exit 1
    fi
fi

# 7. Checksum ---------------------------------------------------------------
if command -v shasum >/dev/null 2>&1; then
    (cd "$DIST_DIR" && shasum -a 256 "$APP_NAME" > "$APP_NAME.sha256")
else
    (cd "$DIST_DIR" && sha256sum "$APP_NAME" > "$APP_NAME.sha256")
fi
log "SHA-256: $(cut -d' ' -f1 "$DIST_DIR/$APP_NAME.sha256")  (written to dist/$APP_NAME.sha256)"
log "Done. Executable: $EXE"
