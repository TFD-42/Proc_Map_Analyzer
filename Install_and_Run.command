#!/usr/bin/env bash
#
# Install_and_Run.command
# =============================
# All-in-one launcher (macOS, double-click) for process_analyzer_allinone.py:
#
#   1. Creates an isolated Python virtual environment (.venv) next to this
#      file — dependencies are installed THERE, never in the system
#      site-packages (this completely avoids the class of bugs
#      "externally-managed-environment" / corrupted dist-info encountered
#      with global --user installs).
#   2. Installs the Python dependencies into this venv (once,
#      reused on subsequent launches).
#   3. Detects locally installed Ollama models (`ollama list`) and
#      interactively asks which one to use, rather than requiring a
#      hand-typed name (the source of a previous bug: a typo in the
#      model name would silently cause every enriched process to fail).
#   4. Runs the analysis and opens the results automatically.
#
# Usage: double-click in Finder. On first launch, if macOS blocks it
# ("unidentified developer"), right-click -> Open, or in Terminal:
# chmod +x Install_and_Run.command
#
# Command-line options (optional):
#   --model NAME     forces a specific Ollama model (skips the menu)
#   --script PATH    uses a script other than process_analyzer_allinone.py
#   --full           enriches ALL processes (default: only the 25 most
#                     active ones, see H4 below)
#   -- ...           everything after this is passed as-is to the Python script
#
# Assumptions made (no further detail provided):
#   H1. The target script is named "process_analyzer_allinone.py" and is
#       located next to this launcher (otherwise: --script <path>, or the
#       GRAPH_SCRIPT environment variable).
#   H2. The venv is created once in ".venv/" next to this
#       launcher and reused afterward (the first launch is longer,
#       subsequent ones are fast).
#   H3. If no Ollama model is installed, or if Ollama is not
#       running, the analysis continues anyway without enrichment
#       (--no-enrich) rather than failing.
#   H4. By default, only the 25 most active processes (CPU+RAM) are
#       enriched, to avoid an analysis involving several hundred calls
#       to the local model (potentially very slow) — use --full
#       to enrich everything.
#   H5. Outputs are timestamped in "outputs/" next to this launcher, so
#       a previous analysis is never overwritten.
#
# Compatible with the bash 3.2 shipped by default on macOS (no
# mapfile/readarray, no associative arrays).

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || { echo "Cannot access $SCRIPT_DIR"; exit 1; }

PY_SCRIPT="${GRAPH_SCRIPT:-process_analyzer_allinone.py}"
VENV_DIR="$SCRIPT_DIR/.venv"
OUT_DIR="$SCRIPT_DIR/outputs"
STAMP="$(date +%Y%m%d_%H%M%S)"
PNG_OUT="$OUT_DIR/process_graph_${STAMP}.png"
HTML_OUT="$OUT_DIR/process_graph_3d_${STAMP}.html"
JSON_OUT="$OUT_DIR/process_data_${STAMP}.json"

MODEL_OVERRIDE=""
FULL_ENRICH=0
EXTRA_ARGS=()

pause_and_exit() {
  echo ""
  read -n 1 -s -r -p "Press any key to close this window..."
  echo ""
  exit "${1:-1}"
}

# --- Minimal argument parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)
      MODEL_OVERRIDE="$2"; shift 2 ;;
    --script)
      PY_SCRIPT="$2"; shift 2 ;;
    --full)
      FULL_ENRICH=1; shift ;;
    --)
      shift
      EXTRA_ARGS+=("$@")
      break ;;
    *)
      EXTRA_ARGS+=("$1"); shift ;;
  esac
done

echo "======================================================"
echo " Process Analyzer — install + run"
echo "======================================================"

# --- 1. Is python3 available? ---
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found on this machine."
  echo "Install Apple's developer tools: xcode-select --install"
  pause_and_exit 1
fi

# --- 2. Is the target script present? ---
if [[ ! -f "$SCRIPT_DIR/$PY_SCRIPT" ]]; then
  echo "Script not found: $SCRIPT_DIR/$PY_SCRIPT"
  echo "Place process_analyzer_allinone.py next to this launcher,"
  echo "or rerun with: ./Install_and_Run.command --script <path_to_the_script>.py"
  pause_and_exit 1
fi

# --- 3. Virtual environment (created once, reused afterward — H2) ---
VENV_PY="$VENV_DIR/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip"

if [[ ! -x "$VENV_PY" ]]; then
  echo "Creating the Python virtual environment (.venv)..."
  if ! python3 -m venv "$VENV_DIR"; then
    echo "Failed to create the venv."
    pause_and_exit 1
  fi
else
  echo "Reusing existing virtual environment (.venv)."
fi

if [[ ! -x "$VENV_PIP" ]]; then
  echo "pip missing in the venv, repairing (ensurepip)..."
  "$VENV_PY" -m ensurepip --upgrade >/dev/null 2>&1
fi
if [[ ! -x "$VENV_PIP" ]]; then
  echo "Unable to obtain pip in the virtual environment."
  echo "Check your Python installation (python3 -m venv must work)."
  pause_and_exit 1
fi

# --- 4. Python dependencies, installed INSIDE the venv ---
echo "Checking dependencies..."
MISSING_STR="$("$VENV_PY" - <<'PYEOF'
import importlib.util
mods = ("psutil", "networkx", "matplotlib", "requests")
missing = [m for m in mods if importlib.util.find_spec(m) is None]
print(" ".join(missing))
PYEOF
)"
read -r -a MISSING_ARR <<< "$MISSING_STR"

if [[ ${#MISSING_ARR[@]} -gt 0 ]]; then
  echo "Installing missing dependencies: ${MISSING_ARR[*]}..."
  "$VENV_PIP" install --upgrade pip >/dev/null 2>&1
  if ! "$VENV_PIP" install "${MISSING_ARR[@]}"; then
    echo "Failed to install dependencies in the venv."
    pause_and_exit 1
  fi
  echo "Dependencies installed."
else
  echo "All dependencies are already present in the venv."
fi

# --- 5. Ollama model selection: detection + interactive menu ---
OLLAMA_ARGS=()
if [[ -n "$MODEL_OVERRIDE" ]]; then
  OLLAMA_ARGS+=(--model "$MODEL_OVERRIDE")
  echo "Ollama model forced: $MODEL_OVERRIDE"

elif command -v ollama >/dev/null 2>&1 && ollama list >/dev/null 2>&1; then
  # Compatible with bash 3.2: no mapfile, we fill the array by hand.
  MODEL_LIST=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && MODEL_LIST+=("$line")
  done < <(ollama list 2>/dev/null | awk 'NR>1 {print $1}')

  if [[ ${#MODEL_LIST[@]} -eq 0 ]]; then
    echo "Ollama is running but no model is installed -> analysis without enrichment."
    echo "(Install one with: ollama pull llama3)"
    OLLAMA_ARGS+=(--no-enrich)

  elif [[ -t 0 ]]; then
    echo ""
    echo "Ollama models detected on this machine:"
    i=1
    for m in "${MODEL_LIST[@]}"; do
      echo "  $i) $m"
      i=$((i + 1))
    done
    echo "  $i) None (disable AI enrichment)"
    echo ""
    read -r -p "Which model to use? [1-$i] (default: 1): " CHOICE
    CHOICE="${CHOICE:-1}"
    if [[ "$CHOICE" =~ ^[0-9]+$ ]] && [[ "$CHOICE" -ge 1 ]] && [[ "$CHOICE" -le ${#MODEL_LIST[@]} ]]; then
      SELECTED_MODEL="${MODEL_LIST[$((CHOICE - 1))]}"
      OLLAMA_ARGS+=(--model "$SELECTED_MODEL")
      echo "Selected model: $SELECTED_MODEL"
    else
      echo "AI enrichment disabled."
      OLLAMA_ARGS+=(--no-enrich)
    fi

  else
    # No interactive terminal (launched from another script/cron):
    # use the first available model rather than blocking on a prompt.
    OLLAMA_ARGS+=(--model "${MODEL_LIST[0]}")
    echo "Non-interactive mode: model chosen automatically: ${MODEL_LIST[0]}"
  fi

else
  echo "Ollama not detected or not running -> analysis without enrichment (--no-enrich)."
  echo "(Start Ollama with 'ollama serve' then rerun this launcher to get enrichment.)"
  OLLAMA_ARGS+=(--no-enrich)
fi

if [[ $FULL_ENRICH -eq 1 ]]; then
  EXTRA_ARGS+=(--enrich-all)
fi

# --- 6. Running the analysis (inside the venv) ---
mkdir -p "$OUT_DIR"
echo ""
echo "Running the analysis..."
echo "------------------------------------------------------"
"$VENV_PY" "$SCRIPT_DIR/$PY_SCRIPT" \
  --output "$PNG_OUT" \
  --html-output "$HTML_OUT" \
  --json-export "$JSON_OUT" \
  "${OLLAMA_ARGS[@]}" \
  "${EXTRA_ARGS[@]}"
STATUS=$?
echo "------------------------------------------------------"

if [[ $STATUS -ne 0 ]]; then
  echo "The analysis failed (code $STATUS) — see the messages above."
  pause_and_exit "$STATUS"
fi

echo "Done."
echo "  PNG  : $PNG_OUT"
echo "  HTML : $HTML_OUT"
echo "  JSON : $JSON_OUT"

# --- 7. Automatically opening the results ---
[[ -f "$HTML_OUT" ]] && open "$HTML_OUT" >/dev/null 2>&1
[[ -f "$PNG_OUT" ]] && open "$PNG_OUT" >/dev/null 2>&1

pause_and_exit 0
