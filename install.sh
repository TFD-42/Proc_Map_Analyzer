#!/usr/bin/env bash
#
# install.sh — automatically installs EVERYTHING needed to run
# process_analyzer_allinone.py on a clean machine (macOS, Linux, or
# Android/Termux), then launches the script.
#
# Order of steps (each one first checks whether it's already present, and
# never reinstalls anything unnecessarily):
#   1. Ollama (local AI engine) — including on Android/Termux (`pkg
#      install ollama` package) when it is available in the Termux repos
#   2. An Ollama model ADAPTED TO THE MACHINE:
#        - Android/Termux: MINI model (llama3.2:1b, ~1.3 GB) — limited
#          RAM and storage on mobile
#        - macOS / Linux : MEDIUM model (llama3:latest, ~4.7 GB)
#      (Windows, handled by install.ps1, also gets the medium model)
#   3. Python 3
#   4. Creation + activation of a virtual environment (.venv)
#   5. Python dependencies (pip) — from requirements_frozen.txt (exact
#      pinned versions, reproducible install) when present, otherwise from
#      requirements.txt (lower bounds only). psutil is skipped on Android.
#   6. Compile check: every .py (main script + plugins/) is compiled in
#      memory to catch a syntax error BEFORE launch. Nothing is written to
#      disk (no __pycache__), so the tree stays exactly as shipped.
#   7. Launching process_analyzer_allinone.py
#
# Usage:
#   chmod +x install.sh
#   ./install.sh                  # install everything, then launch
#   ./install.sh --install-only   # install + compile check, do NOT launch
#   PMA_SKIP_OLLAMA=1 ./install.sh   # skip steps 1-2 (no AI, no download,
#                                    # nothing fetched from the internet
#                                    # except pip packages)
#
# Every other argument is forwarded as-is to the Python script
# (e.g. ./install.sh --no-enrich --max-processes 50).
#
# No step fails silently: a failure installing Ollama or the model does not
# interrupt the rest (the analysis works without AI), but the absence of
# Python is fatal (nothing can run without it).

set -uo pipefail  # No -e on purpose: each step handles its own errors

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/process_analyzer_allinone.py"
VENV_DIR="$SCRIPT_DIR/.venv"
REQ_FROZEN="$SCRIPT_DIR/requirements_frozen.txt"
REQ_LOOSE="$SCRIPT_DIR/requirements.txt"
OLLAMA_HOST="http://localhost:11434"
# Portable temp dir: Termux has no /tmp, it exposes $TMPDIR ($PREFIX/tmp).
TMP_DIR="${TMPDIR:-/tmp}"

# --install-only is consumed here; everything else is forwarded to Python.
INSTALL_ONLY=0
FORWARD_ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--install-only" ]; then
        INSTALL_ONLY=1
    else
        FORWARD_ARGS+=("$arg")
    fi
done
# Models by machine size — the actual choice is made after platform
# detection, see below.
MODEL_MINI="llama3.2:1b"      # ~1.3 GB — Android/Termux (limited RAM/storage)
MODEL_MEDIUM="llama3:latest"  # ~4.7 GB — macOS/Linux

log()  { printf '\n\033[1;34m[install]\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m[warning]\033[0m %s\n' "$1"; }
err()  { printf '\033[1;31m[error]\033[0m %s\n' "$1" >&2; }

if [ ! -f "$PY_SCRIPT" ]; then
    err "process_analyzer_allinone.py not found next to this script ($SCRIPT_DIR)."
    err "Place install.sh in the same folder as process_analyzer_allinone.py and rerun."
    exit 1
fi

# ---------------------------------------------------------------------------
# 0. Platform detection (same logic as the Python script, to stay
#    consistent: Android/Termux has neither Ollama nor psutil available).
# ---------------------------------------------------------------------------
IS_ANDROID=0
if [ -n "${ANDROID_ROOT:-}" ] || [ -n "${ANDROID_DATA:-}" ] || [[ "${PREFIX:-}" == *com.termux* ]] || [ -f /system/build.prop ]; then
    IS_ANDROID=1
fi

OS_NAME="$(uname -s)"
if [ "$IS_ANDROID" = "1" ]; then
    PLATFORM="android"
elif [ "$OS_NAME" = "Darwin" ]; then
    PLATFORM="macos"
elif [ "$OS_NAME" = "Linux" ]; then
    PLATFORM="linux"
else
    PLATFORM="unknown"
fi
log "Detected platform: $PLATFORM"

# Ollama model adapted to the machine: mini on Android (limited
# RAM/storage), medium everywhere else.
if [ "$PLATFORM" = "android" ]; then
    DEFAULT_MODEL="$MODEL_MINI"
    log "AI model selected for this machine: $DEFAULT_MODEL (mini, ~1.3 GB — suited for mobile)"
else
    DEFAULT_MODEL="$MODEL_MEDIUM"
    log "AI model selected for this machine: $DEFAULT_MODEL (medium, ~4.7 GB)"
fi

# ---------------------------------------------------------------------------
# 1. Ollama
# ---------------------------------------------------------------------------
log "Step 1/7: checking Ollama..."
if [ "${PMA_SKIP_OLLAMA:-0}" = "1" ]; then
    log "PMA_SKIP_OLLAMA=1 — Ollama install/start/model download skipped (analysis will run without AI)."
elif command -v ollama >/dev/null 2>&1; then
    log "Ollama already installed ($(command -v ollama))."
else
    case "$PLATFORM" in
        macos)
            if command -v brew >/dev/null 2>&1; then
                log "Installing Ollama via Homebrew (may take a few minutes)..."
                brew install ollama || warn "Homebrew installation of Ollama failed — the analysis will continue without AI."
            else
                warn "Homebrew not found — installing Ollama via the official script..."
                log "Running: curl -fsSL https://ollama.com/install.sh | sh   (remote script executed as-is; set PMA_SKIP_OLLAMA=1 to avoid it)"
                curl -fsSL https://ollama.com/install.sh | sh || warn "Automatic Ollama installation failed — the analysis will continue without AI."
            fi
            ;;
        linux)
            log "Installing Ollama via the official script (may prompt for the sudo password)..."
            log "Running: curl -fsSL https://ollama.com/install.sh | sh   (remote script executed as-is; set PMA_SKIP_OLLAMA=1 to avoid it)"
            curl -fsSL https://ollama.com/install.sh | sh || warn "Automatic Ollama installation failed — the analysis will continue without AI."
            ;;
        android)
            # Termux now provides an ollama package in its repos —
            # we try it, and degrade gracefully if unavailable (older
            # Termux versions, un-synced repo...).
            if command -v pkg >/dev/null 2>&1; then
                log "Installing Ollama via pkg (Termux)..."
                pkg install -y ollama || warn "ollama package unavailable in this Termux — AI enrichment will stay disabled, the analysis will still work (rule-based risk engine still active)."
            else
                warn "'pkg' command not found (Termux?) — Ollama not installed, the analysis will continue without AI."
            fi
            ;;
        *)
            warn "Unrecognized platform ($OS_NAME) — install Ollama manually from https://ollama.com/download if you want AI enrichment."
            ;;
    esac
fi

# Start the server regardless of OS as soon as the ollama binary exists
# (including on Termux, where the package may have just been installed).
if [ "${PMA_SKIP_OLLAMA:-0}" != "1" ] && command -v ollama >/dev/null 2>&1; then
    if ! curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
        log "Starting the Ollama server in the background (log: $TMP_DIR/ollama_serve.log)..."
        nohup ollama serve >"$TMP_DIR/ollama_serve.log" 2>&1 &
        for _ in $(seq 1 15); do
            curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1 && break
            sleep 2
        done
    fi
fi

# ---------------------------------------------------------------------------
# 2. Default Ollama model
# ---------------------------------------------------------------------------
log "Step 2/7: checking the Ollama model ($DEFAULT_MODEL)..."
if [ "${PMA_SKIP_OLLAMA:-0}" != "1" ] && command -v ollama >/dev/null 2>&1 && curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
    if ollama list 2>/dev/null | grep -q "^${DEFAULT_MODEL%%:*}"; then
        log "Model already present."
    else
        log "Downloading model $DEFAULT_MODEL (may take a while depending on your connection)..."
        ollama pull "$DEFAULT_MODEL" || warn "Model download failed — the analysis will continue without AI (retry later: ollama pull $DEFAULT_MODEL)."
    fi
else
    log "Step skipped (PMA_SKIP_OLLAMA=1, Ollama unavailable on this platform, or server unreachable)."
fi

# ---------------------------------------------------------------------------
# 3. Python 3
# ---------------------------------------------------------------------------
log "Step 3/7: checking Python 3..."
PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        major="$("$candidate" -c 'import sys; print(sys.version_info[0])' 2>/dev/null || echo 0)"
        if [ "$major" = "3" ]; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    log "Python 3 not found — installing..."
    case "$PLATFORM" in
        macos)
            if command -v brew >/dev/null 2>&1; then
                brew install python || { err "Failed to install Python via Homebrew."; exit 1; }
            else
                err "Python 3 not found and Homebrew missing. Install Python from https://www.python.org/downloads/ then rerun this script."
                exit 1
            fi
            ;;
        linux)
            if command -v apt-get >/dev/null 2>&1; then
                sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
            elif command -v dnf >/dev/null 2>&1; then
                sudo dnf install -y python3 python3-pip
            elif command -v yum >/dev/null 2>&1; then
                sudo yum install -y python3 python3-pip
            elif command -v pacman >/dev/null 2>&1; then
                sudo pacman -Sy --noconfirm python python-pip
            elif command -v zypper >/dev/null 2>&1; then
                sudo zypper install -y python3 python3-pip
            else
                err "Package manager not automatically recognized. Install Python 3 manually then rerun this script."
                exit 1
            fi
            ;;
        android)
            if command -v pkg >/dev/null 2>&1; then
                pkg install -y python || { err "Failed to install Python via pkg."; exit 1; }
            else
                err "'pkg' command not found (are you running Termux?). Install Python manually: pkg install python"
                exit 1
            fi
            ;;
        *)
            err "Unrecognized platform ($OS_NAME). Install Python 3 manually then rerun this script."
            exit 1
            ;;
    esac
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
fi

if [ -z "$PYTHON_BIN" ]; then
    err "Python 3 still not found after attempting automatic installation. Aborting."
    exit 1
fi
log "Python detected: $("$PYTHON_BIN" --version 2>&1)"

PY_MINOR="$("$PYTHON_BIN" -c 'import sys; print(sys.version_info[1])' 2>/dev/null || echo 0)"
if [ "$PY_MINOR" -lt 10 ] 2>/dev/null; then
    err "Python 3.10+ is required since v0.3.0 (found $("$PYTHON_BIN" --version 2>&1)): the pinned security fixes for Pillow/requests/urllib3 in requirements_frozen.txt dropped Python 3.9 support upstream."
    err "Install a newer Python (e.g. 'brew install python@3.12' on macOS, 'sudo apt-get install python3.12' on Debian/Ubuntu) so it is first on PATH as python3, then rerun this script."
    exit 1
fi

# ---------------------------------------------------------------------------
# 4. Virtual environment + activation
# ---------------------------------------------------------------------------
log "Step 4/7: creating the virtual environment (.venv)..."
if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR" || {
        err "Failed to create the venv (is the 'venv' module installed? on Debian/Ubuntu: sudo apt-get install python3-venv)."
        exit 1
    }
fi

# shellcheck disable=SC1091
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    err "Activation script not found ($VENV_DIR/bin/activate)."
    exit 1
fi
log "Venv active: $(command -v python)"

# ---------------------------------------------------------------------------
# 5. Python dependencies
# ---------------------------------------------------------------------------
log "Step 5/7: installing Python dependencies..."
python -m pip install --upgrade pip --quiet

# Reproducible by default: exact pinned versions. requirements.txt (lower
# bounds only) is a fallback, never the first choice, because two installs
# made a month apart would otherwise resolve to different versions.
if [ -f "$REQ_FROZEN" ]; then
    REQ_FILE="$REQ_FROZEN"
    log "Using pinned versions from requirements_frozen.txt (reproducible install)."
elif [ -f "$REQ_LOOSE" ]; then
    REQ_FILE="$REQ_LOOSE"
    warn "requirements_frozen.txt not found — falling back to requirements.txt (lower bounds only, versions NOT pinned)."
else
    err "Neither requirements_frozen.txt nor requirements.txt found next to install.sh. Aborting."
    exit 1
fi

REQ_ANDROID=""
if [ "$PLATFORM" = "android" ]; then
    # psutil has no Android wheel and fails to build from source —
    # process_analyzer_allinone.py falls back to its own /proc backend.
    # Filter it out of the requirements file instead of hand-listing deps.
    REQ_ANDROID="$TMP_DIR/pma_requirements_android.$$.txt"
    grep -viE '^[[:space:]]*psutil([=<>!~ ]|$)' "$REQ_FILE" > "$REQ_ANDROID"
    REQ_FILE="$REQ_ANDROID"
    log "Android/Termux: psutil removed from the requirements (internal /proc backend will be used)."
fi
log "Running: python -m pip install -r $REQ_FILE"

if ! python -m pip install --quiet -r "$REQ_FILE"; then
    warn "Standard pip failed — retrying with --break-system-packages (externally-managed Python environments, PEP 668)..."
    if ! python -m pip install --quiet --break-system-packages -r "$REQ_FILE"; then
        if [ "$PLATFORM" = "android" ]; then
            err "Failed to install dependencies. On Termux, try the precompiled package if matplotlib fails: pkg install matplotlib"
        else
            err "Failed to install Python dependencies (see pip output above)."
        fi
        [ -n "$REQ_ANDROID" ] && rm -f "$REQ_ANDROID"
        exit 1
    fi
fi
[ -n "$REQ_ANDROID" ] && rm -f "$REQ_ANDROID"
log "Dependencies installed."

# ---------------------------------------------------------------------------
# 6. Compile check (in memory — writes NO .pyc / __pycache__)
# ---------------------------------------------------------------------------
log "Step 6/7: compile check of the main script and plugins/ ..."
if ! python "$SCRIPT_DIR/compile_check.py"; then
    err "Compile check failed — the code as shipped has a syntax error (see above). Not launching."
    exit 1
fi

# ---------------------------------------------------------------------------
# 7. Launch
# ---------------------------------------------------------------------------
if [ "$INSTALL_ONLY" = "1" ]; then
    log "Step 7/7 skipped (--install-only). Install complete and verified."
    log "To run later:  source \"$VENV_DIR/bin/activate\" && python \"$PY_SCRIPT\"   (or just ./install.sh again)"
    exit 0
fi
log "Step 7/7: everything is ready. Launching the analyzer..."
exec python "$PY_SCRIPT" "${FORWARD_ARGS[@]}"
