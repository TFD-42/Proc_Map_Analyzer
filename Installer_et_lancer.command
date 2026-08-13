#!/usr/bin/env bash
#
# Installer_et_lancer.command
# =============================
# Launcher tout-en-un (macOS, double-clic) pour process_graph_analyzer.py :
#
#   1. Crée un environnement virtuel Python isolé (.venv) à côté de ce
#      fichier — les dépendances sont installées LÀ, jamais dans les
#      site-packages système (ça évite complètement la classe de bugs
#      "externally-managed-environment" / dist-info corrompus rencontrée
#      avec des installations --user globales).
#   2. Installe les dépendances Python dans ce venv (une seule fois,
#      réutilisé aux lancements suivants).
#   3. Détecte les modèles Ollama installés localement (`ollama list`) et
#      demande interactivement lequel utiliser, plutôt que de laisser
#      taper un nom à la main (source du bug précédent : une faute de
#      frappe dans le nom du modèle faisait échouer silencieusement
#      chaque processus enrichi).
#   4. Lance l'analyse et ouvre les résultats automatiquement.
#
# Utilisation : double-clic dans le Finder. Premier lancement : si
# macOS bloque ("développeur non identifié"), clic droit -> Ouvrir, ou
# dans le Terminal : chmod +x Installer_et_lancer.command
#
# Options en ligne de commande (facultatives) :
#   --model NOM      force un modèle Ollama précis (saute le menu)
#   --script CHEMIN  utilise un autre script que process_graph_analyzer.py
#   --full           enrichit TOUS les processus (par défaut : les 25 plus
#                     actifs seulement, cf. H4 ci-dessous)
#   -- ...           tout ce qui suit est transmis tel quel au script Python
#
# Hypothèses posées (aucune précision fournie) :
#   H1. Le script cible s'appelle "process_graph_analyzer.py" et se trouve
#       à côté de ce launcher (sinon : --script <chemin>, ou variable
#       d'environnement GRAPH_SCRIPT).
#   H2. Le venv est créé une seule fois dans ".venv/" à côté de ce
#       launcher et réutilisé ensuite (le premier lancement est plus
#       long, les suivants sont rapides).
#   H3. Si aucun modèle Ollama n'est installé, ou si Ollama n'est pas
#       lancé, l'analyse continue quand même mais sans enrichissement
#       (--no-enrich) plutôt que d'échouer.
#   H4. Par défaut, seuls les 25 processus les plus actifs (CPU+RAM) sont
#       enrichis, pour éviter une analyse de plusieurs centaines d'appels
#       au modèle local (potentiellement très longue) — utiliser --full
#       pour tout enrichir.
#   H5. Sorties horodatées dans "sorties/" à côté de ce launcher, pour ne
#       jamais écraser une analyse précédente.
#
# Compatible avec le bash 3.2 fourni par défaut sur macOS (pas de
# mapfile/readarray, pas d'arrays associatifs).

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || { echo "Impossible d'accéder à $SCRIPT_DIR"; exit 1; }

PY_SCRIPT="${GRAPH_SCRIPT:-process_graph_analyzer.py}"
VENV_DIR="$SCRIPT_DIR/.venv"
OUT_DIR="$SCRIPT_DIR/sorties"
STAMP="$(date +%Y%m%d_%H%M%S)"
PNG_OUT="$OUT_DIR/process_graph_${STAMP}.png"
HTML_OUT="$OUT_DIR/process_graph_3d_${STAMP}.html"
JSON_OUT="$OUT_DIR/process_data_${STAMP}.json"

MODEL_OVERRIDE=""
FULL_ENRICH=0
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
echo " Analyseur de processus — installation + lancement"
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
  echo "ou relance avec : ./Installer_et_lancer.command --script <chemin_vers_le_script>.py"
  pause_and_exit 1
fi

# --- 3. Environnement virtuel (créé une fois, réutilisé ensuite — H2) ---
VENV_PY="$VENV_DIR/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip"

if [[ ! -x "$VENV_PY" ]]; then
  echo "Création de l'environnement virtuel Python (.venv)..."
  if ! python3 -m venv "$VENV_DIR"; then
    echo "Échec de la création du venv."
    pause_and_exit 1
  fi
else
  echo "Environnement virtuel existant réutilisé (.venv)."
fi

if [[ ! -x "$VENV_PIP" ]]; then
  echo "pip manquant dans le venv, réparation (ensurepip)..."
  "$VENV_PY" -m ensurepip --upgrade >/dev/null 2>&1
fi
if [[ ! -x "$VENV_PIP" ]]; then
  echo "Impossible d'obtenir pip dans l'environnement virtuel."
  echo "Vérifie ton installation Python (python3 -m venv doit fonctionner)."
  pause_and_exit 1
fi

# --- 4. Dépendances Python, installées DANS le venv ---
echo "Vérification des dépendances..."
MISSING_STR="$("$VENV_PY" - <<'PYEOF'
import importlib.util
mods = ("psutil", "networkx", "matplotlib", "requests")
missing = [m for m in mods if importlib.util.find_spec(m) is None]
print(" ".join(missing))
PYEOF
)"
read -r -a MISSING_ARR <<< "$MISSING_STR"

if [[ ${#MISSING_ARR[@]} -gt 0 ]]; then
  echo "Installation des dépendances manquantes : ${MISSING_ARR[*]}..."
  "$VENV_PIP" install --upgrade pip >/dev/null 2>&1
  if ! "$VENV_PIP" install "${MISSING_ARR[@]}"; then
    echo "Échec de l'installation des dépendances dans le venv."
    pause_and_exit 1
  fi
  echo "Dépendances installées."
else
  echo "Toutes les dépendances sont déjà présentes dans le venv."
fi

# --- 5. Sélection du modèle Ollama : détection + menu interactif ---
OLLAMA_ARGS=()
if [[ -n "$MODEL_OVERRIDE" ]]; then
  OLLAMA_ARGS+=(--model "$MODEL_OVERRIDE")
  echo "Modèle Ollama forcé : $MODEL_OVERRIDE"

elif command -v ollama >/dev/null 2>&1 && ollama list >/dev/null 2>&1; then
  # Compatible bash 3.2 : pas de mapfile, on remplit le tableau à la main.
  MODEL_LIST=()
  while IFS= read -r line; do
    [[ -n "$line" ]] && MODEL_LIST+=("$line")
  done < <(ollama list 2>/dev/null | awk 'NR>1 {print $1}')

  if [[ ${#MODEL_LIST[@]} -eq 0 ]]; then
    echo "Ollama tourne mais aucun modèle n'est installé -> analyse sans enrichissement."
    echo "(Installe-en un avec : ollama pull llama3)"
    OLLAMA_ARGS+=(--no-enrich)

  elif [[ -t 0 ]]; then
    echo ""
    echo "Modèles Ollama détectés sur cette machine :"
    i=1
    for m in "${MODEL_LIST[@]}"; do
      echo "  $i) $m"
      i=$((i + 1))
    done
    echo "  $i) Aucun (désactiver l'enrichissement IA)"
    echo ""
    read -r -p "Quel modèle utiliser ? [1-$i] (défaut: 1) : " CHOICE
    CHOICE="${CHOICE:-1}"
    if [[ "$CHOICE" =~ ^[0-9]+$ ]] && [[ "$CHOICE" -ge 1 ]] && [[ "$CHOICE" -le ${#MODEL_LIST[@]} ]]; then
      SELECTED_MODEL="${MODEL_LIST[$((CHOICE - 1))]}"
      OLLAMA_ARGS+=(--model "$SELECTED_MODEL")
      echo "Modèle sélectionné : $SELECTED_MODEL"
    else
      echo "Enrichissement IA désactivé."
      OLLAMA_ARGS+=(--no-enrich)
    fi

  else
    # Pas de terminal interactif (lancé depuis un autre script/cron) :
    # on prend le premier modèle disponible plutôt que de bloquer sur un prompt.
    OLLAMA_ARGS+=(--model "${MODEL_LIST[0]}")
    echo "Mode non interactif : modèle choisi automatiquement : ${MODEL_LIST[0]}"
  fi

else
  echo "Ollama non détecté ou non lancé -> analyse sans enrichissement (--no-enrich)."
  echo "(Démarre Ollama avec 'ollama serve' puis relance ce launcher pour avoir l'enrichissement.)"
  OLLAMA_ARGS+=(--no-enrich)
fi

if [[ $FULL_ENRICH -eq 1 ]]; then
  EXTRA_ARGS+=(--enrich-all)
fi

# --- 6. Lancement de l'analyse (dans le venv) ---
mkdir -p "$OUT_DIR"
echo ""
echo "Lancement de l'analyse..."
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
  echo "L'analyse a échoué (code $STATUS) — voir les messages ci-dessus."
  pause_and_exit "$STATUS"
fi

echo "Terminé."
echo "  PNG  : $PNG_OUT"
echo "  HTML : $HTML_OUT"
echo "  JSON : $JSON_OUT"

# --- 7. Ouverture automatique des résultats ---
[[ -f "$HTML_OUT" ]] && open "$HTML_OUT" >/dev/null 2>&1
[[ -f "$PNG_OUT" ]] && open "$PNG_OUT" >/dev/null 2>&1

pause_and_exit 0
