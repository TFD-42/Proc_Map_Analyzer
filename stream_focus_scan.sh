#!/usr/bin/env bash
#
# stream_focus_scan.sh
# =====================
# Full-filesystem security scan built on process_analyzer_allinone.py's
# --stream-focus-on (H34): walks a directory tree recursively (default: "/",
# the whole disk) instead of live PIDs, and produces the SAME interactive
# 3D HTML graph as the normal process analysis, with Ollama-assisted risk
# flags and the extension-masquerade / entropy / code-cave checks.
#
# Rewritten from an earlier ad-hoc zsh snippet (shlock + lsof + fs_usage
# live-tail on one directory) into a portable bash launcher, because:
#   - shlock is a macOS/BSD-only tool; it does not exist on Linux, so a
#     multi-GPU Linux rig would fail at the very first line.
#   - fs_usage is macOS-only too, with no direct Linux equivalent bundled
#     by default (inotifywait would be a new dependency) -- and it answers
#     a different question ("what's touching this dir right now") than
#     what was asked here ("map the whole filesystem into a 3D graph with
#     AI-assisted risk flags"). Dropped rather than bolted on; the original
#     lsof/fs_usage script is untouched if that live-tail behavior is still
#     wanted separately.
#
# Usage:
#   ./stream_focus_scan.sh                  # interactive menu
#   ./stream_focus_scan.sh --root /Users --ollama-host http://<ollama-host>:11434 \
#       --model llama3.1 --enrich-all --yes
#
# Assumptions made (no further detail provided) -- [Hypothèse], adjust via flags:
#   H1. Scanning "/" is confirmed interactively by default (a whole-disk
#       scan is slow and produces a very large graph); --yes skips the
#       confirmation for unattended/cron use.
#   H2. Pseudo-filesystems (/proc, /sys, /dev, /run, Spotlight/TM volumes)
#       are excluded by process_analyzer_allinone.py itself (H34) -- this
#       launcher does not duplicate that list.
#   H3. --stream-focus-max-files defaults to 200000 here (not unlimited)
#       as a safety cap for a "/" scan; override with --max-files 0 for
#       unlimited.
#   H4. The "rig 6 GPU" requirement is satisfied via --ollama-host pointing
#       at that machine's Ollama server (already a first-class flag of the
#       underlying script) -- no GPU-specific code belongs in this launcher.

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || { echo "Cannot access $SCRIPT_DIR"; exit 1; }

PY_SCRIPT="${GRAPH_SCRIPT:-process_analyzer_allinone.py}"
OUT_DIR="$SCRIPT_DIR/outputs"
STAMP="$(date +%Y%m%d_%H%M%S)"
HTML_OUT="$OUT_DIR/stream_focus_3d_${STAMP}.html"
JSON_OUT="$OUT_DIR/stream_focus_data_${STAMP}.json"
LOCK_DIR="${TMPDIR:-/tmp}/.stream_focus_scan.lock"

# --- defaults, overridable by flags or the interactive menu ---
TARGET_ROOT="/"
OLLAMA_HOST="http://localhost:11434"
MODEL_OVERRIDE=""
ENRICH_MODE="limit"   # limit | all | none
ENRICH_LIMIT="25"
MAX_FILES="200000"
ASSUME_YES=0

# --- portable lock: works identically on macOS and Linux (no shlock/flock
#     dependency), self-heals if the previous holder is dead ---
acquire_lock() {
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    local old_pid
    old_pid="$(cat "$LOCK_DIR/pid" 2>/dev/null)"
    if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
      echo "Une instance de stream_focus_scan.sh tourne déjà (pid $old_pid)." >&2
      exit 1
    fi
    echo "Verrou orphelin détecté (processus $old_pid absent) -- reprise." >&2
    rm -rf "$LOCK_DIR"
    mkdir "$LOCK_DIR" 2>/dev/null || { echo "Impossible d'obtenir le verrou." >&2; exit 1; }
  fi
  echo "$$" > "$LOCK_DIR/pid"
}
release_lock() { rm -rf "$LOCK_DIR" 2>/dev/null; }
trap release_lock EXIT INT TERM

# --- cross-platform "open the result" ---
open_result() {
  local f="$1"
  if command -v open >/dev/null 2>&1; then open "$f" >/dev/null 2>&1
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$f" >/dev/null 2>&1
  else echo "Ouvrez manuellement : $f"
  fi
}

# --- argument parsing (non-interactive path for cron / the GPU rig) ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) TARGET_ROOT="$2"; shift 2 ;;
    --ollama-host) OLLAMA_HOST="$2"; shift 2 ;;
    --model) MODEL_OVERRIDE="$2"; shift 2 ;;
    --enrich-all) ENRICH_MODE="all"; shift ;;
    --no-enrich) ENRICH_MODE="none"; shift ;;
    --enrich-limit) ENRICH_MODE="limit"; ENRICH_LIMIT="$2"; shift 2 ;;
    --max-files) MAX_FILES="$2"; shift 2 ;;
    --yes) ASSUME_YES=1; shift ;;
    -h|--help)
      sed -n '2,45p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1" >&2; exit 1 ;;
  esac
done

echo "======================================================"
echo " Stream Focus Scan — analyse récursive de fichiers (H34)"
echo "======================================================"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 introuvable." >&2
  exit 1
fi
if [[ ! -f "$SCRIPT_DIR/$PY_SCRIPT" ]]; then
  echo "Script introuvable : $SCRIPT_DIR/$PY_SCRIPT" >&2
  exit 1
fi

acquire_lock

# --- interactive menu only when no flags overrode the defaults and stdin
#     is a terminal (kept scriptable for cron/unattended runs) ---
if [[ -t 0 && $ASSUME_YES -eq 0 ]]; then
  read -r -p "Dossier/fichier à analyser (Entrée = '/', tout le disque) : " input_root
  [[ -n "$input_root" ]] && TARGET_ROOT="$input_root"

  echo "Enrichissement Ollama :"
  echo "  1) Limité aux N fichiers les plus significatifs (défaut, N=$ENRICH_LIMIT)"
  echo "  2) Tous les fichiers collectés (lent, coût LLM proportionnel)"
  echo "  3) Aucun (--no-enrich, règles statiques uniquement)"
  read -r -p "Choix [1-3, défaut 1] : " enrich_choice
  case "$enrich_choice" in
    2) ENRICH_MODE="all" ;;
    3) ENRICH_MODE="none" ;;
    *) ENRICH_MODE="limit" ;;
  esac

  read -r -p "Hôte Ollama (Entrée = $OLLAMA_HOST, ex: http://<ip-du-rig>:11434) : " input_host
  [[ -n "$input_host" ]] && OLLAMA_HOST="$input_host"
fi

if [[ "$TARGET_ROOT" == "/" && $ASSUME_YES -eq 0 && -t 0 ]]; then
  read -r -p "Analyser TOUT le disque depuis '/' peut prendre longtemps. Continuer ? [o/N] " confirm
  [[ "$confirm" =~ ^[oOyY]$ ]] || { echo "Annulé."; exit 0; }
fi

if [[ ! -e "$TARGET_ROOT" ]]; then
  echo "Chemin introuvable : $TARGET_ROOT" >&2
  exit 1
fi

# --- Ollama model detection/selection, same convention as
#     Analyze_Processes.command ---
OLLAMA_ARGS=(--ollama-host "$OLLAMA_HOST")
case "$ENRICH_MODE" in
  none)
    OLLAMA_ARGS+=(--no-enrich) ;;
  all)
    OLLAMA_ARGS+=(--enrich-all) ;;
  limit)
    OLLAMA_ARGS+=(--enrich-limit "$ENRICH_LIMIT") ;;
esac

if [[ "$ENRICH_MODE" != "none" ]]; then
  if [[ -n "$MODEL_OVERRIDE" ]]; then
    OLLAMA_ARGS+=(--model "$MODEL_OVERRIDE")
  elif command -v ollama >/dev/null 2>&1 && ollama list >/dev/null 2>&1; then
    DETECTED_MODEL="$(ollama list 2>/dev/null | awk 'NR>1 {print $1; exit}')"
    if [[ -n "$DETECTED_MODEL" ]]; then
      OLLAMA_ARGS+=(--model "$DETECTED_MODEL")
      echo "Modèle Ollama détecté : $DETECTED_MODEL"
    else
      echo "Ollama actif mais aucun modèle disponible -> --no-enrich."
      OLLAMA_ARGS=(--no-enrich)
    fi
  else
    echo "Ollama non détecté sur $OLLAMA_HOST -> --no-enrich."
    OLLAMA_ARGS=(--no-enrich)
  fi
fi

MAX_FILES_ARGS=()
if [[ "$MAX_FILES" != "0" ]]; then
  MAX_FILES_ARGS=(--stream-focus-max-files "$MAX_FILES")
fi

mkdir -p "$OUT_DIR"
echo ""
echo "Cible        : $TARGET_ROOT"
echo "Ollama       : ${OLLAMA_ARGS[*]}"
echo "Plafond      : ${MAX_FILES_ARGS[*]:-illimité}"
echo "------------------------------------------------------"

python3 "$SCRIPT_DIR/$PY_SCRIPT" \
  --stream-focus-on "$TARGET_ROOT" \
  "${MAX_FILES_ARGS[@]}" \
  --html-output "$HTML_OUT" \
  --no-history \
  --json-export "$JSON_OUT" \
  "${OLLAMA_ARGS[@]}"
STATUS=$?
echo "------------------------------------------------------"

if [[ $STATUS -ne 0 ]]; then
  echo "L'analyse a échoué (code $STATUS)." >&2
  exit "$STATUS"
fi

echo "Terminé."
[[ -f "$HTML_OUT" ]] && echo "  Graphe 3D : $HTML_OUT"
[[ -f "$JSON_OUT" ]] && echo "  JSON      : $JSON_OUT"
[[ -f "$HTML_OUT" ]] && open_result "$HTML_OUT"

exit 0
