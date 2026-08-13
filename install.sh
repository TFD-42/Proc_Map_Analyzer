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
#   5. Python dependencies (pip)
#   6. Launching process_analyzer_allinone.py
#
# Usage:
#   chmod +x install.sh
#   ./install.sh
#
# Arguments passed to this script are forwarded as-is to the Python script
# (e.g. ./install.sh --no-enrich --max-processes 50).
#
# No step fails silently: a failure installing Ollama or the model does not
# interrupt the rest (the analysis works without AI), but the absence of
# Python is fatal (nothing can run without it).

set -uo pipefail  # No -e on purpose: each step handles its own errors

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/process_analyzer_allinone.py"
VENV_DIR="$SCRIPT_DIR/.venv"
OLLAMA_HOST="http://localhost:11434"
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
log "Step 1/5: checking Ollama..."
if command -v ollama >/dev/null 2>&1; then
    log "Ollama already installed ($(command -v ollama))."
else
    case "$PLATFORM" in
        macos)
            if command -v brew >/dev/null 2>&1; then
                log "Installing Ollama via Homebrew (may take a few minutes)..."
                brew install ollama || warn "Homebrew installation of Ollama failed — the analysis will continue without AI."
            else
                warn "Homebrew not found — installing Ollama via the official script..."
                curl -fsSL https://ollama.com/install.sh | sh || warn "Automatic Ollama installation failed — the analysis will continue without AI."
            fi
            ;;
        linux)
            log "Installing Ollama via the official script (may prompt for the sudo password)..."
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
if command -v ollama >/dev/null 2>&1; then
    if ! curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
        log "Starting the Ollama server in the background..."
        nohup ollama serve >/tmp/ollama_serve.log 2>&1 &
        for _ in $(seq 1 15); do
            curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1 && break
            sleep 2
        done
    fi
fi

# ---------------------------------------------------------------------------
# 2. Default Ollama model
# ---------------------------------------------------------------------------
log "Step 2/5: checking the Ollama model ($DEFAULT_MODEL)..."
if command -v ollama >/dev/null 2>&1 && curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
    if ollama list 2>/dev/null | grep -q "^${DEFAULT_MODEL%%:*}"; then
        log "Model already present."
    else
        log "Downloading model $DEFAULT_MODEL (may take a while depending on your connection)..."
        ollama pull "$DEFAULT_MODEL" || warn "Model download failed — the analysis will continue without AI (retry later: ollama pull $DEFAULT_MODEL)."
    fi
else
    log "Step skipped (Ollama unavailable on this platform, or server unreachable)."
fi

# ---------------------------------------------------------------------------
# 3. Python 3
# ---------------------------------------------------------------------------
log "Step 3/5: checking Python 3..."
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

# ---------------------------------------------------------------------------
# 4. Virtual environment + activation
# ---------------------------------------------------------------------------
log "Step 4/5: creating the virtual environment (.venv)..."
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
log "Step 5/5: installing Python dependencies..."
python -m pip install --upgrade pip --quiet

DEPS="networkx matplotlib requests"
if [ "$PLATFORM" != "android" ]; then
    # psutil is not installable on Android — process_analyzer_allinone.py
    # automatically falls back to its own /proc backend in that case.
    DEPS="psutil $DEPS"
fi

# shellcheck disable=SC2086
if ! python -m pip install --quiet $DEPS; then
    warn "Standard pip failed — retrying with --break-system-packages (externally-managed Python environments, PEP 668)..."
    # shellcheck disable=SC2086
    if ! python -m pip install --quiet --break-system-packages $DEPS; then
        if [ "$PLATFORM" = "android" ]; then
            err "Failed to install dependencies. On Termux, try the precompiled package if matplotlib fails: pkg install matplotlib"
        else
            err "Failed to install Python dependencies."
        fi
        exit 1
    fi
fi
log "Dependencies installed."

# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------
log "Everything is ready. Launching the analyzer..."
exec python "$PY_SCRIPT" "$@"
