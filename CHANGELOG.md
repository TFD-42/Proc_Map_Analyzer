# Changelog

Toutes les évolutions notables de ce projet sont documentées ici.

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), et ce projet suivra le [Semantic Versioning](https://semver.org/spec/v2.0.0.html) une fois une première version taguée.

## [Unreleased]

Aucune release taguée pour l'instant — ce qui suit reflète l'état actuel du développement, pas un diff entre deux versions publiées.

### Added
- Installeurs : modèle Ollama **adapté à la machine** — mini `llama3.2:1b` (~1,3 Go) sur Android/Termux, medium `llama3:latest` (~4,7 Go) sur macOS/Windows/Linux. Ollama est désormais aussi installé sur Android via le paquet Termux (`pkg install ollama`) quand il est disponible, au lieu d'être ignoré. Le script Python applique la même politique à ses défauts (`--model`, téléchargement proposé par l'assistant) et sait installer Ollama via `pkg` sous Termux.
- Mode surveillance continue `--watch --interval N` : re-collecte périodique (collecte + règles uniquement, jamais d'Ollama en boucle), différences affichées entre cycles (nouveaux/disparus/changements de risque), HTML régénéré à chaque cycle.
- Analyse forensique d'un processus `--pid N` : rapport texte détaillé (identité, risque et signaux, connexions, fichiers ouverts, arbre ancêtres + descendance) ; analyse et HTML restreints à ce sous-arbre.
- Historique automatique des exécutions (`sorties/history.json`, 50 snapshots, `--no-history` pour désactiver) et comparaison `--compare` (sans valeur : vs l'exécution précédente ; avec un chemin : vs un export `--json-export`).
- Configuration whitelist/blacklist `--config config.yaml` (YAML simple ou JSON, sans dépendance pyyaml) : la whitelist neutralise les signaux de chemin du moteur de règles, la blacklist force le niveau « élevé ».
- Vérification d'intégrité `--check-integrity` : SHA256 de chaque exécutable comparé à une base de référence (`--integrity-db`) ; une empreinte modifiée devient un signal de risque « élevé ».
- Baseline de performance `--baseline` : statistiques CPU/RAM par nom de processus ; dès 3 échantillons, un écart > 2 écarts-types devient un signal d'anomalie (z-score).
- Cache persistant SQLite des enrichissements Ollama `--cache` (clé nom+exe+cmdline, TTL `--cache-ttl-days`, défaut 7 jours) — les exécutions suivantes resservent les résultats sans appel LLM ; résultats marqués `from_cache`.
- Retry des enrichissements en échec transitoire `--retry-failed N` (backoff exponentiel 1s/2s/4s, en série).
- Système de plugins `--plugin fichier.py` : fonction `enrich(process_info) -> dict` appliquée à chaque processus, résultat fusionné dans l'export.
- Export CSV des relations du graphe `--csv-edges` (source, target, kind, niveaux de risque des deux extrémités) — importable dans Gephi/Neo4j.
- Détection de conteneurs (Docker/Podman/containerd/Kubernetes) via `/proc/<pid>/cgroup` sur Linux, affichée dans le panneau et les exports.
- Préchargement du modèle `--preload-model` : télécharge le modèle Ollama puis quitte, pour préparer un usage hors-ligne.
- Mode bac à sable `--sandbox fichier.json` : rejoue un export JSON au lieu de collecter le système réel (test des règles/config/rendu sans risque).
- HTML 3D : boutons « copier » dans le panneau (PID, exécutable, commande complète, commande `kill`, SHA256) avec repli quand `navigator.clipboard` est indisponible.
- HTML 3D : nouveaux raccourcis clavier — Échap (fermer le panneau), `/` (focus recherche), 1-5 (changer de mode d'affichage).
- Moteur de risque par règles déterministe (`compute_rule_based_risk`), combiné par escalade avec l'avis Ollama optionnel — le niveau de risque affiché ne dépend plus uniquement de l'IA.
- Visibilité explicite de la collecte incomplète par processus (permissions refusées, process disparu) dans le graphe et les exports.
- Filtrage par défaut des processus peu actifs dans le graphe 3D (togglable), pour réduire la densité visuelle.
- Rapport de synthèse Markdown et export CSV, tous deux optionnels (`--report`, `--csv-export`).
- Support Android/Termux via un backend `/proc` fait maison, en remplacement de `psutil` (non installable sur cette plateforme).
- Raccourcis clavier dans le graphe 3D : `Ctrl+R` (recentrer), `Ctrl++` / `Ctrl+-` (zoom), en plus des boutons déjà existants.
- Installeurs `install.sh` (macOS/Linux/Termux) et `install.ps1` (Windows) : installation automatique d'Ollama, du modèle par défaut, de Python, création d'un environnement virtuel, installation des dépendances, puis lancement.
- `PLAN_ENRICHISSEMENT.md` : feuille de route de 25 enrichissements priorisés.
- Mise en place de la gouvernance de dépôt (ce fichier, `SECURITY.md`, `STATUS.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `LICENSE`, `.gitignore`, `requirements.txt`, `.github/`) via `github-repo-bootstrapper`.

### Changed
- Sortie par défaut réduite au seul graphe 3D interactif (HTML) — PNG, JSON, CSV et rapport sont désormais optionnels (`--png`, `--json-export`, `--csv-export`, `--report`) plutôt que générés systématiquement.
- `--collect-all psutil` rendu obligatoire dans la commande de build PyInstaller (corrige un plantage réel à l'exécution sur macOS, module manquant à tort).

### Fixed
- Timeouts Ollama en rafale corrigés par un appel de préchauffage et un parallélisme réduit par défaut.

## [0.0.0] - non taguée

Première version fonctionnelle connue du script tout-en-un (collecte, graphe, enrichissement Ollama, rendu PNG + HTML 3D, assistant interactif), avant le début du suivi formel de ce changelog.
