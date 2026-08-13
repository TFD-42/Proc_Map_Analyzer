#!/usr/bin/env bash
#
# install.sh — installe automatiquement TOUT ce qu'il faut pour faire tourner
# analyseur_processus_allinone.py sur une machine vierge (macOS, Linux, ou
# Android/Termux), puis lance le script.
#
# Ordre des étapes (chacune vérifie d'abord si c'est déjà présent, et ne
# réinstalle rien inutilement) :
#   1. Ollama (moteur IA local) — y compris sur Android/Termux (paquet `pkg
#      install ollama`) quand il est disponible dans les dépôts Termux
#   2. Un modèle Ollama ADAPTÉ À LA MACHINE :
#        - Android/Termux : modèle MINI  (llama3.2:1b, ~1,3 Go) — RAM et
#          stockage limités sur mobile
#        - macOS / Linux  : modèle MEDIUM (llama3:latest, ~4,7 Go)
#      (Windows, géré par install.ps1, reçoit aussi le medium)
#   3. Python 3
#   4. Création + activation d'un environnement virtuel (.venv)
#   5. Dépendances Python (pip)
#   6. Lancement de analyseur_processus_allinone.py
#
# Usage :
#   chmod +x install.sh
#   ./install.sh
#
# Les arguments passés à ce script sont transmis tels quels au script Python
# (ex: ./install.sh --no-enrich --max-processes 50).
#
# Aucune étape n'est silencieuse en cas d'échec : un échec d'installation
# d'Ollama ou du modèle n'interrompt pas le reste (l'analyse fonctionne sans
# IA), mais l'absence de Python est fatale (rien ne peut tourner sans lui).

set -uo pipefail  # Pas de -e volontairement : chaque étape gère elle-même ses erreurs

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SCRIPT="$SCRIPT_DIR/analyseur_processus_allinone.py"
VENV_DIR="$SCRIPT_DIR/.venv"
OLLAMA_HOST="http://localhost:11434"
# Modèles par taille de machine — le choix effectif est fait après la
# détection de plateforme, cf. plus bas.
MODEL_MINI="llama3.2:1b"      # ~1,3 Go — Android/Termux (RAM/stockage limités)
MODEL_MEDIUM="llama3:latest"  # ~4,7 Go — macOS/Linux

log()  { printf '\n\033[1;34m[install]\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m[attention]\033[0m %s\n' "$1"; }
err()  { printf '\033[1;31m[erreur]\033[0m %s\n' "$1" >&2; }

if [ ! -f "$PY_SCRIPT" ]; then
    err "analyseur_processus_allinone.py introuvable à côté de ce script ($SCRIPT_DIR)."
    err "Place install.sh dans le même dossier que analyseur_processus_allinone.py puis relance."
    exit 1
fi

# ---------------------------------------------------------------------------
# 0. Détection de la plateforme (même logique que le script Python, pour
#    rester cohérent : Android/Termux n'a ni Ollama ni psutil disponibles).
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
log "Plateforme détectée : $PLATFORM"

# Modèle Ollama adapté à la machine : mini sur Android (RAM/stockage
# limités), medium partout ailleurs.
if [ "$PLATFORM" = "android" ]; then
    DEFAULT_MODEL="$MODEL_MINI"
    log "Modèle IA retenu pour cette machine : $DEFAULT_MODEL (mini, ~1,3 Go — adapté au mobile)"
else
    DEFAULT_MODEL="$MODEL_MEDIUM"
    log "Modèle IA retenu pour cette machine : $DEFAULT_MODEL (medium, ~4,7 Go)"
fi

# ---------------------------------------------------------------------------
# 1. Ollama
# ---------------------------------------------------------------------------
log "Étape 1/5 : vérification d'Ollama..."
if command -v ollama >/dev/null 2>&1; then
    log "Ollama déjà installé ($(command -v ollama))."
else
    case "$PLATFORM" in
        macos)
            if command -v brew >/dev/null 2>&1; then
                log "Installation d'Ollama via Homebrew (peut prendre quelques minutes)..."
                brew install ollama || warn "Échec de l'installation Homebrew d'Ollama — l'analyse continuera sans IA."
            else
                warn "Homebrew introuvable — installation d'Ollama via le script officiel..."
                curl -fsSL https://ollama.com/install.sh | sh || warn "Échec de l'installation automatique d'Ollama — l'analyse continuera sans IA."
            fi
            ;;
        linux)
            log "Installation d'Ollama via le script officiel (peut demander le mot de passe sudo)..."
            curl -fsSL https://ollama.com/install.sh | sh || warn "Échec de l'installation automatique d'Ollama — l'analyse continuera sans IA."
            ;;
        android)
            # Termux fournit désormais un paquet ollama dans ses dépôts —
            # on tente, et on dégrade proprement si indisponible (anciennes
            # versions de Termux, dépôt non synchronisé...).
            if command -v pkg >/dev/null 2>&1; then
                log "Installation d'Ollama via pkg (Termux)..."
                pkg install -y ollama || warn "Paquet ollama indisponible dans ce Termux — l'enrichissement IA restera désactivé, l'analyse fonctionnera quand même (moteur de risque par règles toujours actif)."
            else
                warn "Commande 'pkg' introuvable (Termux ?) — Ollama non installé, l'analyse continuera sans IA."
            fi
            ;;
        *)
            warn "Plateforme non reconnue ($OS_NAME) — installe Ollama manuellement depuis https://ollama.com/download si tu veux l'enrichissement IA."
            ;;
    esac
fi

# Démarre le serveur quel que soit l'OS dès que le binaire ollama existe
# (y compris Termux, où le paquet vient peut-être d'être installé).
if command -v ollama >/dev/null 2>&1; then
    if ! curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
        log "Démarrage du serveur Ollama en arrière-plan..."
        nohup ollama serve >/tmp/ollama_serve.log 2>&1 &
        for _ in $(seq 1 15); do
            curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1 && break
            sleep 2
        done
    fi
fi

# ---------------------------------------------------------------------------
# 2. Modèle Ollama par défaut
# ---------------------------------------------------------------------------
log "Étape 2/5 : vérification du modèle Ollama ($DEFAULT_MODEL)..."
if command -v ollama >/dev/null 2>&1 && curl -fsS "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
    if ollama list 2>/dev/null | grep -q "^${DEFAULT_MODEL%%:*}"; then
        log "Modèle déjà présent."
    else
        log "Téléchargement du modèle $DEFAULT_MODEL (peut prendre du temps selon ta connexion)..."
        ollama pull "$DEFAULT_MODEL" || warn "Échec du téléchargement du modèle — l'analyse continuera sans IA (relance plus tard : ollama pull $DEFAULT_MODEL)."
    fi
else
    log "Étape ignorée (Ollama indisponible sur cette plateforme ou serveur injoignable)."
fi

# ---------------------------------------------------------------------------
# 3. Python 3
# ---------------------------------------------------------------------------
log "Étape 3/5 : vérification de Python 3..."
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
    log "Python 3 introuvable — installation..."
    case "$PLATFORM" in
        macos)
            if command -v brew >/dev/null 2>&1; then
                brew install python || { err "Échec de l'installation de Python via Homebrew."; exit 1; }
            else
                err "Python 3 introuvable et Homebrew absent. Installe Python depuis https://www.python.org/downloads/ puis relance ce script."
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
                err "Gestionnaire de paquets non reconnu automatiquement. Installe Python 3 manuellement puis relance ce script."
                exit 1
            fi
            ;;
        android)
            if command -v pkg >/dev/null 2>&1; then
                pkg install -y python || { err "Échec de l'installation de Python via pkg."; exit 1; }
            else
                err "Commande 'pkg' introuvable (es-tu bien sous Termux ?). Installe Python manuellement : pkg install python"
                exit 1
            fi
            ;;
        *)
            err "Plateforme non reconnue ($OS_NAME). Installe Python 3 manuellement puis relance ce script."
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
    err "Python 3 toujours introuvable après tentative d'installation automatique. Abandon."
    exit 1
fi
log "Python détecté : $("$PYTHON_BIN" --version 2>&1)"

# ---------------------------------------------------------------------------
# 4. Environnement virtuel + activation
# ---------------------------------------------------------------------------
log "Étape 4/5 : création de l'environnement virtuel (.venv)..."
if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR" || {
        err "Échec de la création du venv (le module 'venv' est-il installé ? sur Debian/Ubuntu : sudo apt-get install python3-venv)."
        exit 1
    }
fi

# shellcheck disable=SC1091
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    err "Script d'activation introuvable ($VENV_DIR/bin/activate)."
    exit 1
fi
log "Venv actif : $(command -v python)"

# ---------------------------------------------------------------------------
# 5. Dépendances Python
# ---------------------------------------------------------------------------
log "Étape 5/5 : installation des dépendances Python..."
python -m pip install --upgrade pip --quiet

DEPS="networkx matplotlib requests"
if [ "$PLATFORM" != "android" ]; then
    # psutil n'est pas installable sur Android — analyseur_processus_allinone.py
    # bascule automatiquement sur son propre backend /proc dans ce cas.
    DEPS="psutil $DEPS"
fi

# shellcheck disable=SC2086
if ! python -m pip install --quiet $DEPS; then
    warn "Échec via pip standard — nouvelle tentative avec --break-system-packages (environnements Python 'gérés en externe', PEP 668)..."
    # shellcheck disable=SC2086
    if ! python -m pip install --quiet --break-system-packages $DEPS; then
        if [ "$PLATFORM" = "android" ]; then
            err "Échec de l'installation des dépendances. Sur Termux, essaie le paquet précompilé si matplotlib échoue : pkg install matplotlib"
        else
            err "Échec de l'installation des dépendances Python."
        fi
        exit 1
    fi
fi
log "Dépendances installées."

# ---------------------------------------------------------------------------
# Lancement
# ---------------------------------------------------------------------------
log "Tout est prêt. Lancement de l'analyseur..."
exec python "$PY_SCRIPT" "$@"
