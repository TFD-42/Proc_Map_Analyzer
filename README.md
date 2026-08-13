# Analyseur de processus système (graphe 3D + IA locale)

[![CI](https://github.com/TFD-42/Proc_Map_Analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/TFD-42/Proc_Map_Analyzer/actions/workflows/ci.yml)
[![Licence: MIT](https://img.shields.io/badge/Licence-MIT-green.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![Plateformes](https://img.shields.io/badge/Plateformes-macOS%20%7C%20Linux%20%7C%20Windows%20%7C%20Android%2FTermux-lightgrey.svg)](#support-android--termux)
[![IA 100%25 locale](https://img.shields.io/badge/IA-100%25%20locale%20(Ollama)-orange.svg)](#intégration-ollama)

> *Interactive 3D process graph analyzer with deterministic risk scoring and local AI enrichment (Ollama) — no data leaves your machine.*

Outil en ligne de commande / assistant graphique qui analyse les processus en cours d'exécution sur une machine, leurs fichiers liés (exécutable, répertoire de travail, fichiers ouverts) et leurs relations (parent → enfant, fichiers partagés, connexions réseau), calcule un niveau de risque **par règles déterministes** (pas seulement par IA, voir [Sécurité : règles + IA](#sécurité--moteur-de-règles--avis-ia)), enrichit chaque processus significatif via un modèle **Ollama local**, puis produit par défaut un **unique livrable : un graphe 3D interactif** ("système solaire" cliquable, `three.js` / `3d-force-graph`) explorable au clic, à la souris ou au clavier (`Ctrl+R` recentre, `Ctrl+`/`Ctrl-` zoome).

PNG statique, export JSON, export CSV et rapport de synthèse Markdown restent disponibles mais **opt-in** (options `--png` / `--json-export` / `--csv-export` / `--report`, voir [Mode ligne de commande](#mode-ligne-de-commande-avancé)) — le mode assistant novice ne produit et n'ouvre que le HTML.

Tout tourne **en local** : la seule requête réseau du script lui-même est le chargement de la librairie 3D depuis un CDN à l'ouverture du fichier HTML (voir [Confidentialité](#confidentialité--vie-privée)), et les appels d'enrichissement vers Ollama restent sur `localhost` par défaut.

**Multi-plateforme** : Windows, macOS, Linux (compilables en exécutable via PyInstaller) et **Android/Termux** (backend de collecte alternatif basé sur `/proc`, voir [Support Android / Termux](#support-android--termux)).

---

## Sommaire

- [Fichiers du projet](#fichiers-du-projet)
- [Installation automatique (recommandé sur une machine vierge)](#installation-automatique-recommandé-sur-une-machine-vierge)
- [Prérequis](#prérequis)
- [Démarrage rapide](#démarrage-rapide)
- [Mode assistant (novice)](#mode-assistant-novice)
- [Mode ligne de commande (avancé)](#mode-ligne-de-commande-avancé)
- [Sécurité : moteur de règles + avis IA](#sécurité--moteur-de-règles--avis-ia)
- [Intégration Ollama](#intégration-ollama)
- [Le graphe 3D interactif](#le-graphe-3d-interactif)
- [Fichiers de sortie](#fichiers-de-sortie)
- [Compiler en exécutable (PyInstaller)](#compiler-en-exécutable-pyinstaller)
- [Support Android / Termux](#support-android--termux)
- [Confidentialité / vie privée](#confidentialité--vie-privée)
- [Limites connues](#limites-connues)
- [Dépannage](#dépannage)
- [Hypothèses de conception](#hypothèses-de-conception)

---

## Fichiers du projet

| Fichier | Rôle |
|---|---|
| `analyseur_processus_allinone.py` | **Script principal**, tout-en-un. Contient l'analyse, le moteur de risque par règles, l'enrichissement Ollama, le rendu HTML/PNG, les exports JSON/CSV/rapport, l'assistant interactif, l'auto-installation des dépendances et d'Ollama. C'est celui à utiliser et à compiler. |
| `process_graph_analyzer.py` | Ancienne version modulaire (sans assistant ni auto-installation), conservée pour un usage scripté/cron plus léger. |
| `Analyser_processus.command` / `Installer_et_lancer.command` | Anciens launchers macOS en bash, avant que l'assistant interactif ne soit intégré directement dans le script Python. Plus nécessaires si tu utilises `analyseur_processus_allinone.py`. |
| `PLAN_ENRICHISSEMENT.md` | Feuille de route des 25 enrichissements identifiés (implémentés + roadmap), organisée par domaine et priorité. |
| `install.sh` | Installeur automatique macOS / Linux / Android-Termux — voir ci-dessous. |
| `install.ps1` | Installeur automatique Windows — voir ci-dessous. |
| `demo_graph.png`, `demo_graph_3d.html`, `demo_data.json` | Exemples de sortie générés pendant le développement. |

## Installation automatique (recommandé sur une machine vierge)

Sur une machine qui n'a **rien d'installé** (ni Python, ni Ollama), les scripts `install.sh` (macOS/Linux/Termux) et `install.ps1` (Windows) automatisent tout, dans cet ordre, en vérifiant à chaque étape ce qui est déjà présent avant de tenter quoi que ce soit :

1. **Ollama** (moteur IA local) — via Homebrew sur macOS, le script officiel sur Linux, `winget` ou l'installeur officiel sur Windows, et le paquet Termux (`pkg install ollama`) sur Android quand il est disponible dans les dépôts.
2. **Modèle Ollama adapté à la machine** — téléchargé via `ollama pull` s'il n'est pas déjà présent :
   - **Android/Termux** : modèle **mini** `llama3.2:1b` (~1,3 Go) — RAM et stockage limités sur mobile ;
   - **macOS / Windows / Linux** : modèle **medium** `llama3:latest` (~4,7 Go).

   Le script Python applique la même politique pour ses propres défauts (`--model` et le téléchargement proposé par l'assistant novice).
3. **Python 3** — via Homebrew/`apt`/`dnf`/`pacman`/`zypper`/`pkg` (Termux) sur macOS/Linux, via `winget` ou l'installeur officiel sur Windows.
4. **Environnement virtuel** (`.venv`) — créé puis activé automatiquement.
5. **Dépendances Python** (`networkx`, `matplotlib`, `requests`, et `psutil` sauf sur Android) — installées dans ce venv.
6. **Lancement** de `analyseur_processus_allinone.py` (les arguments passés à l'installeur sont transmis tels quels au script, ex. `./install.sh --no-enrich`).

Un échec sur Ollama ou le modèle n'interrompt jamais l'installation (l'analyse fonctionne sans IA, avec le moteur de risque par règles) ; un échec sur Python, lui, est fatal puisque rien ne peut tourner sans lui.

**macOS / Linux / Termux :**

```bash
chmod +x install.sh
./install.sh
```

**Windows** (PowerShell — si l'exécution de scripts est bloquée par la politique par défaut) :

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

Ces installeurs touchent le système (installation de logiciels, éventuellement `sudo`/droits administrateur pour Ollama ou Python selon la plateforme) — lis-les avant de les lancer sur une machine sensible, comme pour tout script d'installation automatique récupéré en ligne.

## Prérequis

- **Python 3.9+**
- Dépendances Python : `networkx`, `matplotlib`, `requests`, et `psutil` sur toute plateforme sauf Android/Termux — installées automatiquement au premier lancement si absentes (sauf en exécutable compilé, voir plus bas). Sur Android/Termux, `psutil` est remplacé automatiquement par un backend interne (voir [Support Android / Termux](#support-android--termux)).
- **Ollama** (facultatif) pour l'enrichissement par IA — installé automatiquement si besoin en mode assistant (voir [Intégration Ollama](#intégration-ollama)). Sans Ollama, l'outil fonctionne quand même, simplement sans les descriptions générées par IA.
- Une **connexion internet** est nécessaire uniquement pour : l'installation automatique des dépendances/d'Ollama, le téléchargement d'un modèle Ollama, et l'affichage du graphe 3D (librairie chargée depuis un CDN). L'analyse des processus elle-même ne nécessite aucun accès réseau externe.

## Démarrage rapide

```bash
python3 analyseur_processus_allinone.py
```

Lancé **sans aucun argument**, le script démarre l'assistant interactif (voir ci-dessous). Lancé **avec des options**, il se comporte comme un outil en ligne de commande classique pour un usage avancé ou scripté.

## Mode assistant (novice)

Déclenché automatiquement à un double-clic sur l'exécutable compilé, ou en lançant le script sans argument. Pose au maximum deux à quatre questions selon la situation :

1. **Nombre maximum de processus** à inclure dans le graphe (défaut : 150 — les plus actifs en CPU + RAM sont toujours prioritaires, le reste est simplement exclu du graphe, jamais tronqué silencieusement sans log).
2. **Modèle Ollama** à utiliser pour l'enrichissement :
   - S'il y a des modèles installés localement, ils sont listés par numéro (`0` pour désactiver l'IA).
   - Si Ollama n'est pas détecté du tout, l'assistant propose de l'installer automatiquement (voir [Intégration Ollama](#intégration-ollama)).
   - Si Ollama tourne mais qu'aucun modèle n'est installé, l'assistant propose de télécharger le modèle par défaut (`llama3:latest`).
   - Répondre non à ces deux propositions ne bloque jamais l'analyse : elle continue simplement sans enrichissement IA.

Le nombre de processus réellement enrichis par IA est dérivé automatiquement du nombre max de processus (`min(max_processes, 40)`) pour éviter une troisième question.

En fin d'exécution :
- **seul le graphe 3D HTML est écrit** (`sorties/process_graph_3d_AAAAMMJJ_HHMMSS.html`, à côté du script ou de l'exécutable) et **s'ouvre automatiquement** dans le navigateur par défaut — pas de PNG, JSON, CSV ni rapport en mode assistant (pour ces formats, relancer en ligne de commande avec `--png` / `--json-export` / `--csv-export` / `--report`, voir plus bas) ;
- la fenêtre reste ouverte jusqu'à une touche pressée, pour qu'une console qui se lance par double-clic ne se ferme pas instantanément.

## Mode ligne de commande (avancé)

Utilisé dès qu'au moins un argument est passé au script (`--help` compris) :

```bash
python3 analyseur_processus_allinone.py --help
```

| Option | Défaut | Description |
|---|---|---|
| `--html-output CHEMIN` | `process_graph_3d.html` | Chemin du HTML 3D interactif (généré par défaut) |
| `--no-html` | — | Désactive la génération du graphe 3D (déconseillé, c'est la seule sortie par défaut) |
| `--png` | — | Génère aussi un PNG statique (désactivé par défaut) |
| `--output CHEMIN` | `process_graph.png` | Chemin du PNG, utilisé seulement si `--png` |
| `--json-export CHEMIN` | — | Exporte aussi les données collectées/enrichies/risque en JSON (désactivé par défaut) |
| `--csv-export CHEMIN` | — | Exporte aussi en CSV, une ligne par processus (désactivé par défaut) |
| `--report CHEMIN` | — | Écrit un rapport de synthèse Markdown (désactivé par défaut) |
| `--model NOM` | `llama3.2` | Modèle Ollama à utiliser |
| `--ollama-host URL` | `http://localhost:11434` | URL de l'API Ollama |
| `--enrich-limit N` | `25` | Nombre max de processus enrichis par IA, triés par activité CPU+RAM |
| `--enrich-all` | — | Enrichit tous les processus collectés (ignore `--enrich-limit`) |
| `--no-enrich` | — | Désactive complètement l'appel à Ollama (le risque par règles reste actif) |
| `--min-score N` | `0` | Score minimal (cpu%+mem%) pour inclure un processus |
| `--max-processes N` | aucune limite | Nombre max de processus inclus dans le graphe (garde les plus actifs) |
| `--max-conn-per-process N` | `20` | Connexions réseau brutes max collectées par processus |
| `--max-conn-total N` | `300` | Arêtes de connexion max dessinées au total |
| `--max-workers N` | `2` | Parallélisme des appels Ollama |
| `--timeout N` | `120` | Timeout par appel Ollama, en secondes |
| `-v`, `--verbose` | — | Logs de niveau DEBUG |

### Modes d'exécution supplémentaires

| Option | Défaut | Description |
|---|---|---|
| `--watch` | — | Surveillance continue : re-collecte périodique (collecte + règles uniquement, **jamais** d'Ollama en boucle), différences affichées entre cycles, HTML régénéré. Ctrl+C pour arrêter |
| `--interval N` | `60` | Intervalle en secondes entre deux cycles de `--watch` (minimum 5) |
| `--pid N` | — | Analyse forensique d'**un** processus : rapport texte détaillé + analyse restreinte à son sous-arbre (ancêtres + descendance) |
| `--compare [CHEMIN]` | — | Compare l'exécution courante à un snapshot : sans valeur, à l'exécution précédente de l'historique ; avec un chemin, à un export `--json-export` |
| `--history-file CHEMIN` | `sorties/history.json` | Fichier d'historique alimenté automatiquement (50 snapshots conservés) |
| `--no-history` | — | Désactive l'enregistrement automatique du snapshot |
| `--sandbox CHEMIN` | — | Lit les processus depuis un JSON (format `--json-export`) au lieu du système réel — test des règles/config/rendu sans risque |
| `--preload-model` | — | Télécharge/prépare le modèle Ollama puis quitte (préparation hors-ligne) |

### Analyse et enrichissement avancés

| Option | Défaut | Description |
|---|---|---|
| `--config CHEMIN` | — | Whitelist/blacklist (YAML simple ou JSON) : la whitelist neutralise les signaux de chemin, la blacklist force le niveau « élevé » |
| `--check-integrity` | — | SHA256 de chaque exécutable comparé à une base de référence ; empreinte modifiée = signal « élevé » |
| `--integrity-db CHEMIN` | `sorties/integrity.json` | Base de référence des empreintes |
| `--baseline` | — | Ajoute cette exécution à la baseline CPU/RAM par nom de processus ; dès 3 échantillons, un écart > 2 écarts-types devient un signal d'anomalie |
| `--baseline-file CHEMIN` | `sorties/baseline.json` | Fichier de baseline |
| `--cache` | — | Cache SQLite des enrichissements Ollama : un processus identique déjà analysé est resservi sans appel LLM |
| `--cache-file CHEMIN` | `sorties/enrich_cache.sqlite3` | Fichier du cache |
| `--cache-ttl-days N` | `7` | Durée de validité des entrées du cache |
| `--retry-failed N` | `0` | Retente jusqu'à N fois les enrichissements en échec transitoire (backoff exponentiel) |
| `--plugin CHEMIN` | — | Plugin Python `enrich(process_info: dict) -> dict` appliqué à chaque processus |
| `--csv-edges CHEMIN` | — | Exporte les **relations** du graphe en CSV (importable Gephi/Neo4j) |

Exemple de fichier `--config` (YAML) :

```yaml
whitelist:
  - "/usr/local/go/*"   # motifs fnmatch acceptés
  - "code helper"        # sinon, recherche de sous-chaîne (nom, exe ou cmdline)
  - "ollama"
blacklist:
  - "cryptominer"
  - "/tmp/unknown_*"
```

Exemple de plugin (`mon_plugin.py`) :

```python
def enrich(process_info):
    # process_info : dict (pid, name, exe, cmdline, cpu_percent, connections, container...)
    if process_info.get("cpu_percent", 0) > 80:
        return {"alerte": "consommation CPU critique"}
    return {}
```

Exemples d'utilisation des nouveaux modes :

```bash
# Surveillance continue toutes les 30 s, avec whitelist locale
python3 analyseur_processus_allinone.py --watch --interval 30 --config config.yaml
```

```bash
# Rapport forensique d'un processus suspect
python3 analyseur_processus_allinone.py --pid 1234 --no-enrich
```

```bash
# Analyse complète avec cache IA, retry, intégrité et comparaison à l'exécution précédente
python3 analyseur_processus_allinone.py --cache --retry-failed 3 --check-integrity --compare
```

Exemple pour une exécution planifiée (cron), sans enrichissement IA mais avec un rapport de synthèse et un export CSV horodatés (le HTML est toujours généré) :

```bash
python3 analyseur_processus_allinone.py \
  --no-enrich \
  --html-output "/var/log/process_graph/graph_$(date +%Y%m%d_%H%M).html" \
  --report "/var/log/process_graph/rapport_$(date +%Y%m%d_%H%M).md" \
  --csv-export "/var/log/process_graph/data_$(date +%Y%m%d_%H%M).csv"
```

## Sécurité : moteur de règles + avis IA

Le niveau de risque affiché n'est **plus produit uniquement par l'IA**. Un moteur de règles déterministe (`compute_rule_based_risk`) calcule d'abord un niveau à partir de signaux observables, sans dépendre d'Ollama :

- exécutable lancé depuis un répertoire temporaire (`/tmp`, `/var/tmp`, `/dev/shm`) ;
- exécutable hors des répertoires système standards ;
- exécutable marqué `(deleted)` par le noyau (binaire supprimé du disque après le lancement du processus) ;
- ligne de commande vide alors qu'un exécutable réel est présent (les threads noyau, qui n'ont pas d'exécutable, ne sont jamais concernés par cette règle) ;
- processus en écoute sur toutes les interfaces réseau (`0.0.0.0`) ;
- volume inhabituel de connexions externes distinctes (plus de 10) ;
- correspondance avec un motif **blacklist** de `--config` (niveau « élevé » immédiat) ;
- empreinte SHA256 de l'exécutable différente de la référence connue (avec `--check-integrity`) ;
- CPU ou RAM anormalement élevés par rapport à la baseline du processus (avec `--baseline`, dès 3 échantillons).

Un motif **whitelist** de `--config` neutralise uniquement les signaux de *chemin* (répertoire temporaire / hors répertoires standards) — les signaux réseau, d'intégrité et « exécutable supprimé » restent toujours actifs.

Chaque règle déclenchée est **tracée nommément** (visible dans le panneau "Sécurité" du HTML et dans le rapport/CSV), jamais un score opaque. Si Ollama est disponible, son avis est combiné **par escalade uniquement** : le niveau final retenu est le plus élevé des deux (règles ou IA), jamais le plus bas — sous-estimer un risque est jugé pire que le sur-estimer. Une divergence entre les deux avis est signalée explicitement plutôt que masquée.

**Ce moteur de règles reste un outil pédagogique et d'aide au tri, pas un antivirus ni un EDR** : il n'a aucune base de signatures, ne fait aucune analyse comportementale dans le temps, et peut aussi bien manquer une menace réelle que signaler un faux positif (ex. un outil de développement légitime lancé depuis `/tmp`). À utiliser comme point de départ pour investiguer, pas comme verdict final.

## Intégration Ollama

L'enrichissement demande à un modèle Ollama local de catégoriser chaque processus significatif (catégorie, rôle probable, niveau de risque, justification, explication pédagogique) et retourne un JSON structuré.

**Détection des modèles** : via l'API HTTP (`GET /api/tags`), jamais via la commande `ollama list` — ça évite de dépendre du binaire `ollama` sur le `PATH`, ce qui reste valable une fois le script compilé en exécutable.

**Vérification préalable** : avant de lancer la boucle d'enrichissement, le script vérifie une seule fois que le modèle demandé existe réellement (comparaison tolérante `nom` / `nom:tag`). Un nom de modèle mal orthographié échoue donc immédiatement avec un message clair, plutôt que de produire une erreur répétée sur chaque processus.

**Auto-installation d'Ollama** (assistant uniquement, avec accord explicite — jamais silencieuse) :

| OS | Méthode |
|---|---|
| macOS | `brew install ollama` si Homebrew est disponible, sinon ouverture de la page de téléchargement officielle |
| Linux | script officiel `curl -fsSL https://ollama.com/install.sh \| sh` |
| Windows | téléchargement puis lancement de `OllamaSetup.exe` |

**Téléchargement de modèle** : si Ollama tourne mais qu'aucun modèle n'est installé, le script propose de télécharger `llama3:latest` via `POST /api/pull` (flux streamé, avec barre de progression).

**Fiabilité des appels** : un appel de "préchauffage" (petit prompt jetable) est envoyé une fois avant la boucle pour forcer le chargement du modèle en mémoire — sans ça, plusieurs appels simultanés peuvent tous attendre en file d'attente derrière un modèle encore en cours de chargement et expirer ensemble. Le parallélisme par défaut est volontairement modeste (`--max-workers 2`) car un LLM local sert le plus souvent les requêtes de façon séquentielle (un seul GPU/CPU) : trop de parallélisme n'accélère rien et ne fait qu'empiler des requêtes jusqu'à leur timeout.

## Le graphe 3D interactif

Fichier HTML autonome (CSS/JS embarqués), navigable à la souris (glisser pour orbiter, molette pour zoomer, clic sur un nœud pour le détail). Cinq modes d'affichage, sélectionnables en haut de l'écran :

- **Type** — colore chaque processus par catégorie détectée par l'IA (navigateur, service système, dev-tool, base de données, réseau).
- **Sécurité** (par défaut) — colore par niveau de risque final, panneau détaillé listant le niveau par règles, l'avis IA s'il existe, un badge "avis divergents" en cas de désaccord, les connexions externes, et les éventuels champs de collecte incomplète (permissions refusées).
- **Debug** — dégradé de couleur selon la charge CPU+RAM, panneau avec les champs techniques bruts (PID, exécutable, ligne de commande, connexions).
- **Info verbose** — dump complet de tous les champs connus sur l'élément sélectionné.
- **Knowledge** — explication pédagogique du rôle du processus (générée par Ollama si enrichi, sinon issue d'une petite base de connaissance locale intégrée pour les processus système courants).

Une légende cliquable permet de masquer/afficher des catégories entières, y compris une section "Affichage" avec une entrée **"Processus peu actifs"**, masquée par défaut : un processus à faible degré de connexion, faible CPU+RAM et risque final faible est caché au chargement pour garder le graphe lisible même avec 150 processus — jamais un processus dont le risque n'est pas "faible", quelle que soit son activité. Un champ de recherche met en évidence les nœuds correspondants.

Contrôles caméra (en bas à droite, ou au clavier) :

| Action | Bouton | Clavier |
|---|---|---|
| Zoom avant | `+` | `Ctrl` + `+` |
| Zoom arrière | `–` | `Ctrl` + `-` |
| Recentrer | `⟲` | `R` ou `Ctrl` + `R` |
| Fermer le panneau | `✕` | `Échap` |
| Focus recherche | — | `/` |
| Changer de mode | boutons du haut | `1` à `5` |

Le panneau de détail propose des boutons **« copier »** (PID, chemin de l'exécutable, ligne de commande complète, commande `kill <pid>` prête à coller, SHA256 si `--check-integrity`) pour accélérer le passage à l'investigation dans un terminal — la commande `kill` est seulement copiée, jamais exécutée par la page.

Les liens sont colorés par type de relation : parent → enfant, fichier partagé, et par protocole réseau (TCP/UDP/UNIX) — toutes les couleurs ont été validées pour rester distinguables en daltonisme et en vision normale.

## Fichiers de sortie

| Fichier | Généré par défaut ? | Contenu |
|---|---|---|
| `process_graph_3d_*.html` | **Oui, toujours** (sauf `--no-html`) | Graphe interactif — s'ouvre dans n'importe quel navigateur, aucune installation requise côté destinataire. Nécessite une connexion internet à l'ouverture pour charger la librairie 3D depuis un CDN. Seul fichier ouvert automatiquement en mode assistant. |
| `process_graph_*.png` | Non — option `--png` | Rendu statique du graphe complet, avec légende, pour archivage ou partage rapide. |
| `process_data_*.json` | Non — option `--json-export` | Export brut de toutes les données collectées, du risque (règles + IA) et de l'enrichissement, pour un traitement externe (Excel, base de données, autre script). |
| `*.csv` | Non — option `--csv-export` | Une ligne par processus, champs aplatis (risque final, règles déclenchées, avis IA, collecte incomplète…), pour ouverture directe dans un tableur. |
| `rapport_*.md` | Non — option `--report` | Résumé exécutif en Markdown : répartition des risques, top consommateurs, connexions externes, processus à risque élevé, avis divergents, collecte incomplète, statistiques d'enrichissement IA. |

## Compiler en exécutable (PyInstaller)

```bash
pip install pyinstaller psutil networkx matplotlib requests
pyinstaller --onefile --console --name AnalyseurProcessus \
  --collect-all psutil \
  --collect-submodules matplotlib \
  analyseur_processus_allinone.py
```

L'exécutable est produit dans `dist/`. Points importants :

- **Installe d'abord toutes les dépendances (`pip install psutil networkx matplotlib requests`) dans le MÊME environnement/venv que celui où tu lances `pyinstaller`.** PyInstaller n'embarque que ce qu'il voit installé localement au moment du build — il ne peut pas deviner ce que le script installerait tout seul lors d'un lancement `.py` brut.
- **`--collect-all psutil` est obligatoire**, pas juste recommandé : psutil embarque une extension compilée spécifique à l'OS (`_psutil_osx` / `_psutil_linux` / `_psutil_windows`) que PyInstaller ne détecte pas toujours tout seul. Sans ce flag, l'exécutable compile sans erreur mais plante immédiatement à l'exécution avec `ERREUR : module(s) manquant(s) dans l'exécutable : psutil` (bug rencontré et corrigé — c'est le flag qui règle ça).
- **`--console` est obligatoire** : l'assistant interactif et la pause avant fermeture de fenêtre en ont besoin.
- PyInstaller **ne fait pas de cross-compilation** : la commande doit être lancée sur le même OS que celui visé (compiler sur macOS produit un binaire macOS, etc.).
- Sur un exécutable compilé, une dépendance Python manquante n'est **plus** installée automatiquement (ce serait un bug de build, pas quelque chose à corriger à l'exécution) — le script affiche un message clair et s'arrête proprement à la place, plutôt que de planter sans explication.
- Sur macOS, le binaire non signé sera probablement bloqué par Gatekeeper au premier lancement ("développeur non identifié") : clic droit → Ouvrir, ou `xattr -cr dist/AnalyseurProcessus` dans le Terminal.
- Cette configuration de build (avec `--collect-all psutil`) a été testée avec succès (compilation réelle + exécution réelle contre de vrais processus système, PNG/HTML/JSON générés correctement) sur Linux ; aucune dépendance manquante détectée pour psutil/networkx/matplotlib/requests avec ce jeu de flags. Si un AUTRE module signale une erreur "manquant" à l'exécution, vérifie d'abord qu'il est bien installé dans l'environnement utilisé pour lancer `pyinstaller` avant d'ajouter un `--collect-all` supplémentaire pour lui.

## Support Android / Termux

`psutil` n'a pas de wheel pour Android et son installation depuis les sources échoue explicitement (`platform android is not supported`) — installer PyInstaller ou compiler quoi que ce soit n'y changera rien, ce n'est pas un problème d'environnement mais une limite de la bibliothèque elle-même.

Le script contourne ça automatiquement : sur Android/Termux (détecté via les variables d'environnement Android ou la présence de `/system/build.prop`), `psutil` est remplacé par un backend interne qui lit directement `/proc/<pid>/*` — même principe que ce que fait `psutil` en interne sous Linux. Aucune installation particulière n'est nécessaire, le script détecte la plateforme tout seul et bascule dessus.

**Utilisation sur Termux** :

```bash
pkg install python
python analyseur_processus_allinone.py
```

**Enrichissement IA sur Termux** : les dépôts Termux fournissent un paquet `ollama` — `install.sh` (et l'assistant novice du script) tente de l'installer automatiquement, puis télécharge le modèle **mini** `llama3.2:1b` (~1,3 Go), adapté à la RAM et au stockage d'un mobile (les machines de bureau reçoivent le modèle medium `llama3:latest`). Si le paquet n'est pas disponible dans ta version de Termux, l'analyse continue simplement sans IA :

```bash
pkg install ollama
ollama serve &
ollama pull llama3.2:1b
```

`networkx` et `requests` s'installent normalement via pip. Si l'installation automatique de **matplotlib** échoue (dépendances de compilation manquantes — fréquent sur Termux), utiliser le paquet précompilé à la place :

```bash
pkg install matplotlib
```

**Pas de compilation possible sur Android** : PyInstaller ne cible pas Android/Termux, donc il n'y a pas d'exécutable `.apk`/binaire à produire ici — le script tourne directement via `python analyseur_processus_allinone.py`, exactement comme n'importe quel script Python sous Termux.

**Limites spécifiques à ce mode** (documentées dans le script, H14/H15/H16), toutes liées aux restrictions d'Android lui-même, pas à ce script :
- Sans root, Android limite nativement la visibilité aux processus de l'utilisateur courant (SELinux / `hidepid`) — les processus d'autres applications apparaissent simplement invisibles ou en accès refusé, jamais en erreur.
- Le CPU% est une moyenne depuis le démarrage du processus (temps CPU cumulé ÷ âge du processus), pas un instantané temps réel comme avec `psutil` — suffisant pour prioriser/trier les processus, pas pour un monitoring de charge précis.
- Seules les connexions TCP/UDP **IPv4** et les sockets UNIX sont détectées ; les connexions IPv6 ne sont pas décodées par ce backend allégé.

Ce backend a été testé en conditions réelles (analyse réelle de processus système, détection réelle de connexions réseau via `/proc/net/*`, génération PNG/HTML/JSON complète) sur une machine Linux avec la détection Android forcée — le comportement observé était cohérent avec une collecte `psutil` classique sur la même machine (même ordre de grandeur de processus, PID/PPID/CPU/mémoire corrects).

## Confidentialité / vie privée

- Toute l'analyse (processus, fichiers, connexions) se fait **localement**, aucune donnée n'est envoyée à un service externe par le script lui-même.
- Les appels d'enrichissement vont vers l'URL Ollama configurée (`http://localhost:11434` par défaut) — donc localement, sauf si l'utilisateur configure explicitement un hôte distant via `--ollama-host`.
- Le fichier HTML du graphe 3D charge la librairie de rendu (`3d-force-graph`) depuis un CDN public (`unpkg.com`) à son ouverture — c'est le seul point de contact avec l'extérieur une fois les fichiers générés. Sans connexion, le fichier affiche un message d'erreur explicite plutôt qu'un écran vide.
- Les données de commande (`cmdline`) et autres textes de processus insérés dans le HTML sont échappés pour éviter toute injection de script.

## Limites connues

- Sur macOS, lister les connexions réseau d'un processus qui n'appartient pas à l'utilisateur courant nécessite les droits administrateur (`sudo`) — sans ça, ces processus apparaissent simplement avec 0 connexion visible (pas une erreur).
- Un modèle Ollama volumineux (ex. `llama3:latest`, plusieurs Go) peut prendre du temps à charger en mémoire et à générer une réponse sur du matériel modeste (CPU seul) — les timeouts par défaut ont été calibrés généreusement pour cette raison.
- Le graphe 3D nécessite une connexion internet à l'ouverture (chargement de la librairie de rendu depuis un CDN) ; le PNG et le JSON, eux, sont utilisables entièrement hors-ligne.
- Sur Android/Termux, le CPU% affiché est une moyenne depuis le démarrage du processus (pas un instantané temps réel) et seules les connexions IPv4/UNIX sont détectées — voir [Support Android / Termux](#support-android--termux) pour le détail.

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `Timeout Ollama` répété | Trop de requêtes en parallèle pour un modèle local qui sert en série | Réduire `--max-workers` (déjà à 2 par défaut) et/ou augmenter `--timeout` |
| `404` sur un modèle | Nom de modèle mal orthographié | Vérifier la liste réelle avec `ollama list` ou laisser l'assistant lister les modèles disponibles |
| Erreur "externally-managed-environment" à l'installation des dépendances | Environnement Python protégé (PEP 668) | Le script retente automatiquement avec `--break-system-packages` ; sinon utiliser un environnement virtuel (`python3 -m venv`) |
| Graphe 3D vide / erreur de chargement | Pas de connexion internet au moment de l'ouverture du HTML | Se reconnecter puis recharger la page |
| Fenêtre qui se ferme instantanément (exécutable compilé) | Ne devrait plus arriver — une pause avant fermeture est intégrée | Vérifier que la compilation a bien utilisé `--console` |
| `ERREUR : module(s) manquant(s) dans l'exécutable : psutil` (ou un autre module) au lancement de l'exécutable | PyInstaller n'a pas embarqué l'extension compilée du module (fréquent avec psutil sur macOS), ou le module n'était pas installé dans l'environnement utilisé pour compiler | Recompiler avec `--collect-all psutil` (voir section compilation) ; pour un autre module, vérifier d'abord `pip show <module>` dans l'environnement utilisé pour lancer `pyinstaller` |

## Hypothèses de conception

Le script documente dans son en-tête (docstring, section "Hypothèses posées") toutes les valeurs par défaut choisies en l'absence de précision explicite : modèle et hôte Ollama par défaut, seuils de troncature du graphe (toujours logués, jamais silencieux), comportement en cas de permissions refusées, calibrage des timeouts et du parallélisme Ollama, et conditions de déclenchement de l'assistant interactif versus le mode ligne de commande. Se référer directement au fichier `analyseur_processus_allinone.py` pour le détail exhaustif et à jour.
