#!/usr/bin/env bash
#
# Analyser_processus.command
# ===========================
# Launcher double-clic (macOS) pour process_graph_analyzer.py :
# vérifie/installe les dépendances Python, détecte un modèle Ollama
# disponible localement, lance l'analyse, puis ouvre automatiquement
# le graphe 3D interactif et le PNG dans les applications par défaut.
#
# Utilisation :
#   - Double-clic dans le Finder (macOS l'ouvre dans Terminal.app).
#   - Ou en ligne de commande :
#       ./Analyser_processus.command [--model NOM] [--script chemin.py] [-- <options du script>]
#
# Hypothèses posées (aucune précision fournie) :
#   H1. Le script cible s'appelle "process_graph_analyzer.py" et se trouve
#       dans le MÊME dossier que ce launcher (sinon : --script <chemin>,
#       ou variable d'env GRAPH_SCRIPT).
#   H2. Si aucun --model n'est précisé, on prend le premier modèle listé
#       par `ollama list`.
#   H3. Si Ollama n'est pas installé, pas lancé, ou n'a aucun modèle
#       disponible, l'analyse continue quand même mais SANS enrichissement
#       (--no-enrich) plutôt que d'échouer.
#   H4. Les sorties sont horodatées dans un dossier "sorties/" à côté de ce
#       launcher, pour ne jamais écraser une analyse précédente.
#
# Premier lancement sur macOS : la Gatekeeper peut bloquer un script
# téléchargé. Si besoin : clic droit sur ce fichier -> "Ouvrir", ou dans le
# Terminal : chmod +x Analyser_processus.command

set -o pipefail

# --- Se placer dans le dossier du launcher, quel que soit l'endroit d'où il est lancé ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || { echo "Impossible d'accéder à $SCRIPT_DIR"; exit 1; }

PY_SCRIPT="${GRAPH_SCRIPT:-process_graph_analyzer.py}"
OUT_DIR="$SCRIPT_DIR/sorties"
STAMP="$(date +%Y%m%d_%H%M%S)"
PNG_OUT="$OUT_DIR/process_graph_${STAMP}.png"
HTML_OUT="$OUT_DIR/process_graph_3d_${STAMP}.html"
JSON_OUT="$OUT_DIR/process_data_${STAMP}.json"

MODEL_OVERRIDE=""
EXTRA_ARGS=()

pause_and_exit() {
  echo ""
  read -n 1 -s -r -p "Appuie sur une touche pour fermer cette fenêtre..."
  echo ""
  exit "${1:-1}"
}

# --- Parsing minimal des arguments ---
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
echo " Analyseur de processus — launcher"
echo "======================================================"

# --- 1. Python3 disponible ? ---
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 introuvable sur cette machine."
  echo "Installe les outils de développement Apple : xcode-select --install"
  pause_and_exit 1
fi

# --- 2. Script cible présent ? ---
if [[ ! -f "$SCRIPT_DIR/$PY_SCRIPT" ]]; then
  echo "Script introuvable : $SCRIPT_DIR/$PY_SCRIPT"
  echo "Place process_graph_analyzer.py à côté de ce launcher,"
  echo "ou relance avec : ./Analyser_processus.command --script <chemin_vers_le_script>.py"
  pause_and_exit 1
fi

# --- 3. Dépendances Python : détection puis installation si besoin ---
echo "Vérification des dépendances Python..."
MISSING_STR="$(python3 - <<'PYEOF'
import importlib.util
mods = ("psutil", "networkx", "matplotlib", "requests")
missing = [m for m in mods if importlib.util.find_spec(m) is None]
print(" ".join(missing))
PYEOF
)"
read -r -a MISSING_ARR <<< "$MISSING_STR"

if [[ ${#MISSING_ARR[@]} -gt 0 ]]; then
  echo "Dépendances manquantes : ${MISSING_ARR[*]} — installation en cours..."
  PIP_ERR_LOG="$(mktemp)"
  python3 -m pip install --user "${MISSING_ARR[@]}" >"$PIP_ERR_LOG" 2>&1
  PIP_STATUS=$?
  if [[ $PIP_STATUS -ne 0 ]] && grep -qi "externally-managed-environment" "$PIP_ERR_LOG"; then
    echo "Environnement Python géré en externe détecté, nouvelle tentative avec --break-system-packages..."
    python3 -m pip install --user --break-system-packages "${MISSING_ARR[@]}" >"$PIP_ERR_LOG" 2>&1
    PIP_STATUS=$?
  fi
  if [[ $PIP_STATUS -ne 0 ]]; then
    echo "Échec de l'installation des dépendances :"
    cat "$PIP_ERR_LOG"
    rm -f "$PIP_ERR_LOG"
    echo "Installe-les manuellement : python3 -m pip install --user ${MISSING_ARR[*]}"
    pause_and_exit 1
  fi
  rm -f "$PIP_ERR_LOG"
  echo "Dépendances installées."
else
  echo "Toutes les dépendances Python sont déjà présentes."
fi

# --- 4. Détection Ollama + choix du modèle ---
OLLAMA_ARGS=()
if [[ -n "$MODEL_OVERRIDE" ]]; then
  OLLAMA_ARGS+=(--model "$MODEL_OVERRIDE")
  echo "Modèle Ollama forcé : $MODEL_OVERRIDE"
elif command -v ollama >/dev/null 2>&1 && ollama list >/dev/null 2>&1; then
  DETECTED_MODEL="$(ollama list 2>/dev/null | awk 'NR>1 {print $1; exit}')"
  if [[ -n "$DETECTED_MODEL" ]]; then
    OLLAMA_ARGS+=(--model "$DETECTED_MODEL")
    echo "Modèle Ollama détecté automatiquement : $DETECTED_MODEL"
  else
    echo "Ollama tourne mais aucun modèle disponible (ollama list vide) -> analyse sans enrichissement."
    OLLAMA_ARGS+=(--no-enrich)
  fi
else
  echo "Ollama non détecté ou non lancé -> analyse sans enrichissement (--no-enrich)."
  echo "(Démarre Ollama avec 'ollama serve' puis relance ce launcher pour avoir l'enrichissement.)"
  OLLAMA_ARGS+=(--no-enrich)
fi

# --- 5. Lancement de l'analyse ---
mkdir -p "$OUT_DIR"
echo ""
echo "Lancement de l'analyse..."
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
  echo "L'analyse a échoué (code $STATUS) — voir les messages ci-dessus."
  pause_and_exit "$STATUS"
fi

echo "Terminé."
echo "  PNG  : $PNG_OUT"
echo "  HTML : $HTML_OUT"
echo "  JSON : $JSON_OUT"

# --- 6. Ouverture automatique des résultats ---
[[ -f "$HTML_OUT" ]] && open "$HTML_OUT" >/dev/null 2>&1
[[ -f "$PNG_OUT" ]] && open "$PNG_OUT" >/dev/null 2>&1

pause_and_exit 0
