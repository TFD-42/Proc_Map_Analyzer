#!/usr/bin/env bash
#
# Analyze_Processes.command
# ===========================
# Double-click launcher (macOS) for process_graph_analyzer.py:
# checks/installs Python dependencies, detects a locally available
# Ollama model, runs the analysis, then automatically opens the
# interactive 3D graph and the PNG in their default applications.
#
# Usage:
#   - Double-click in Finder (macOS opens it in Terminal.app).
#   - Or from the command line:
#       ./Analyze_Processes.command [--model NAME] [--script path.py] [-- <script options>]
#
# Assumptions made (no further detail provided):
#   H1. The target script is named "process_graph_analyzer.py" and is
#       located in the SAME folder as this launcher (otherwise: --script <path>,
#       or the GRAPH_SCRIPT environment variable).
#   H2. If no --model is specified, the first model listed by
#       `ollama list` is used.
#   H3. If Ollama is not installed, not running, or has no model
#       available, the analysis continues anyway but WITHOUT enrichment
#       (--no-enrich) rather than failing.
#   H4. Outputs are timestamped in an "outputs/" folder next to this
#       launcher, so a previous analysis is never overwritten.
#
# First launch on macOS: Gatekeeper may block a downloaded script. If
# needed: right-click this file -> "Open", or in Terminal:
# chmod +x Analyze_Processes.command

set -o pipefail

# --- Move into the launcher's folder, regardless of where it's launched from ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || { echo "Cannot access $SCRIPT_DIR"; exit 1; }

PY_SCRIPT="${GRAPH_SCRIPT:-process_graph_analyzer.py}"
OUT_DIR="$SCRIPT_DIR/outputs"
STAMP="$(date +%Y%m%d_%H%M%S)"
PNG_OUT="$OUT_DIR/process_graph_${STAMP}.png"
HTML_OUT="$OUT_DIR/process_graph_3d_${STAMP}.html"
JSON_OUT="$OUT_DIR/process_data_${STAMP}.json"

MODEL_OVERRIDE=""
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
    --)
      shift
      EXTRA_ARGS+=("$@")
      break ;;
    *)
      EXTRA_ARGS+=("$1"); shift ;;
  esac
done

echo "======================================================"
echo " Process Analyzer — launcher"
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
  echo "Place process_graph_analyzer.py next to this launcher,"
  echo "or rerun with: ./Analyze_Processes.command --script <path_to_the_script>.py"
  pause_and_exit 1
fi

# --- 3. Python dependencies: detection then installation if needed ---
echo "Checking Python dependencies..."
MISSING_STR="$(python3 - <<'PYEOF'
import importlib.util
mods = ("psutil", "networkx", "matplotlib", "requests")
missing = [m for m in mods if importlib.util.find_spec(m) is None]
print(" ".join(missing))
PYEOF
)"
read -r -a MISSING_ARR <<< "$MISSING_STR"

if [[ ${#MISSING_ARR[@]} -gt 0 ]]; then
  echo "Missing dependencies: ${MISSING_ARR[*]} — installing..."
  PIP_ERR_LOG="$(mktemp)"
  python3 -m pip install --user "${MISSING_ARR[@]}" >"$PIP_ERR_LOG" 2>&1
  PIP_STATUS=$?
  if [[ $PIP_STATUS -ne 0 ]] && grep -qi "externally-managed-environment" "$PIP_ERR_LOG"; then
    echo "Externally-managed Python environment detected, retrying with --break-system-packages..."
    python3 -m pip install --user --break-system-packages "${MISSING_ARR[@]}" >"$PIP_ERR_LOG" 2>&1
    PIP_STATUS=$?
  fi
  if [[ $PIP_STATUS -ne 0 ]]; then
    echo "Failed to install dependencies:"
    cat "$PIP_ERR_LOG"
    rm -f "$PIP_ERR_LOG"
    echo "Install them manually: python3 -m pip install --user ${MISSING_ARR[*]}"
    pause_and_exit 1
  fi
  rm -f "$PIP_ERR_LOG"
  echo "Dependencies installed."
else
  echo "All Python dependencies are already present."
fi

# --- 4. Ollama detection + model selection ---
OLLAMA_ARGS=()
if [[ -n "$MODEL_OVERRIDE" ]]; then
  OLLAMA_ARGS+=(--model "$MODEL_OVERRIDE")
  echo "Ollama model forced: $MODEL_OVERRIDE"
elif command -v ollama >/dev/null 2>&1 && ollama list >/dev/null 2>&1; then
  DETECTED_MODEL="$(ollama list 2>/dev/null | awk 'NR>1 {print $1; exit}')"
  if [[ -n "$DETECTED_MODEL" ]]; then
    OLLAMA_ARGS+=(--model "$DETECTED_MODEL")
    echo "Ollama model automatically detected: $DETECTED_MODEL"
  else
    echo "Ollama is running but no model is available (ollama list is empty) -> analysis without enrichment."
    OLLAMA_ARGS+=(--no-enrich)
  fi
else
  echo "Ollama not detected or not running -> analysis without enrichment (--no-enrich)."
  echo "(Start Ollama with 'ollama serve' then rerun this launcher to get enrichment.)"
  OLLAMA_ARGS+=(--no-enrich)
fi

# --- 5. Running the analysis ---
mkdir -p "$OUT_DIR"
echo ""
echo "Running the analysis..."
echo "------------------------------------------------------"
python3 "$SCRIPT_DIR/$PY_SCRIPT" \
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

# --- 6. Automatically opening the results ---
[[ -f "$HTML_OUT" ]] && open "$HTML_OUT" >/dev/null 2>&1
[[ -f "$PNG_OUT" ]] && open "$PNG_OUT" >/dev/null 2>&1

pause_and_exit 0
