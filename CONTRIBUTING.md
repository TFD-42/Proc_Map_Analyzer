# Contribuer à Analyseur de processus système

Merci de l'intérêt porté à ce projet. Ce document explique comment s'installer localement et comment les changements sont validés — en restant honnête sur ce qui existe réellement aujourd'hui (pas de suite de tests automatisée pour l'instant, voir plus bas).

## Installation

Le plus simple : utiliser l'installeur fourni, qui gère Ollama, le modèle par défaut, Python, l'environnement virtuel et les dépendances en une seule commande (voir le README, section « Installation automatique ») :

```bash
# macOS / Linux / Android-Termux
chmod +x install.sh && ./install.sh

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File install.ps1
```

Installation manuelle équivalente :

```bash
git clone <URL-du-dépôt>   # une fois ce projet réellement poussé sur GitHub
cd process_graph_tool
python3 -m venv .venv
source .venv/bin/activate   # .venv\Scripts\Activate.ps1 sous Windows
pip install -r requirements.txt   # retirer psutil sur Android/Termux, voir requirements.txt
```

## Valider un changement (pas de suite de tests automatisée pour l'instant)

Il n'existe pas encore de suite de tests unitaires (`pytest`) — c'est un item identifié dans [`PLAN_ENRICHISSEMENT.md`](PLAN_ENRICHISSEMENT.md) (section Maintenance, item 14), volontairement laissé en roadmap plutôt que bâclé. En attendant, tout changement doit au minimum passer :

```bash
# Vérification de syntaxe
python3 -m py_compile analyseur_processus_allinone.py

# Test d'exécution réel, rapide et sans dépendance à Ollama
python3 analyseur_processus_allinone.py --no-enrich --max-processes 30
```

Vérifier ensuite le fichier HTML généré (ouverture dans un navigateur : les 5 modes d'affichage, la légende, la recherche, les raccourcis clavier `Ctrl+R`/`Ctrl+`/`Ctrl-`) avant d'ouvrir une pull request touchant au rendu.

## Style de code

Pas de linter configuré pour l'instant (pas de `ruff`/`flake8` en CI) — rester cohérent avec le style existant du fichier : commentaires et docstrings en français, gestion explicite des erreurs (jamais de `except Exception: pass` silencieux sans commentaire justifiant pourquoi), et documentation des choix de conception non spécifiés par l'utilisateur directement dans la docstring d'en-tête du script (section « Hypothèses posées », `H1`, `H2`, etc.) plutôt que noyés dans les commentaires de fonction.

## Conventions de commit

Pas de convention stricte imposée (pas de `feat:`/`fix:` obligatoire à ce jour) — écrire des messages clairs et à l'impératif, qui expliquent le *pourquoi* du changement, pas seulement le *quoi*.

## Processus de pull request

1. Créer une branche depuis la branche par défaut (`main`).
2. Faire le changement, en gardant `analyseur_processus_allinone.py` comme fichier unique auto-suffisant (c'est une contrainte volontaire du projet, pour rester compilable en un seul exécutable PyInstaller — voir la docstring d'en-tête).
3. Vérifier avec les commandes de la section précédente.
4. Ouvrir une pull request en utilisant le gabarit fourni, en décrivant ce qui change et pourquoi.
5. Une revue et le passage de la CI sont nécessaires avant fusion (voir la configuration de protection de branche, à activer une fois le dépôt poussé sur GitHub).

## Signaler un bug / proposer une fonctionnalité

Utiliser les [gabarits d'issue](.github/ISSUE_TEMPLATE/) une fois le dépôt sur GitHub — ils collectent les informations nécessaires pour trier rapidement.

## Code de conduite

Ce projet suit le [Code de conduite](CODE_OF_CONDUCT.md). En participant, tu acceptes de le respecter.
