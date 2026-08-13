# Scan de secrets — /home/claude/process_graph_tool

Périmètre : tous les fichiers texte du dossier (`analyseur_processus_allinone.py`, `process_graph_analyzer.py`, `README.md`, `PLAN_ENRICHISSEMENT.md`, `Analyser_processus.command`, `Installer_et_lancer.command`, `install.sh`, `install.ps1`, `demo_data.json`, `demo_graph_3d.html`), plus une recherche dédiée de fichiers à risque par nature (`.env`, `*.pem`, `*.key`, `id_rsa*`, `credentials.json`).

Note : ce dossier n'est toujours pas un dépôt git (`git status` → `fatal: not a git repository`), donc l'analyse porte sur l'ensemble des fichiers du répertoire plutôt que sur `git ls-files`. Mise à jour de la précédente passe (12/08, 12:48) : ajoute au périmètre `install.sh` et `install.ps1`, nouveaux depuis.

## Secrets détectés (valeurs jamais affichées en clair)

**Aucun** — recherche par pattern (clés AWS `AKIA...`, clés `sk-...`, tokens GitHub `ghp_...`, tokens Slack `xox...`, blocs `-----BEGIN PRIVATE KEY-----`, variables `*_KEY`/`*_SECRET`/`*_TOKEN`/`*_PASSWORD`/`*_CREDENTIAL` assignées à une valeur) sur le code source, les installeurs et la documentation : aucune correspondance. `install.sh`/`install.ps1` ne font que télécharger des installeurs officiels publics (Ollama, Python) et n'embarquent aucun identifiant.

## Faux positifs écartés

| Fichier | Pattern matché | Pourquoi ce n'est pas un vrai secret |
|---|---|---|
| `secret-scan-report.md` (version précédente) | `AKIA...`, `sk-...`, `ghp_...`, `xox...` | Ce sont les motifs de recherche eux-mêmes, cités en toutes lettres dans le rapport pour décrire la méthode — pas des valeurs trouvées dans le code. |

## Constat hors gabarit : données réelles capturées dans les fichiers de démo (toujours présent, non résolu)

Rappel de la passe précédente, statut inchangé — `demo_data.json` et `demo_graph_3d.html` contiennent toujours de vraies données issues de cette machine de développement (deux adresses IP publiques réellement observées, un nom d'utilisateur système réel, des chemins d'exécutables internes réels). Ce n'est pas un secret exploitable au sens classique, mais publier ces fichiers tels quels contredit l'angle « tout reste local » du projet. Détail complet dans l'historique de ce rapport (non reproduit ici pour éviter de re-disperser la donnée) ou en relisant les fichiers concernés directement.

**Recommandation inchangée** : régénérer ces trois fichiers de démo (`demo_data.json`, `demo_graph_3d.html`, `demo_graph.png`) avec des données anonymisées avant toute publication publique, ou les exclure d'un futur dépôt git via `.gitignore`.

## Fichiers à risque non trackés dans .gitignore

Toujours pas de `.gitignore` (pas encore de dépôt git). Si `github-repo-bootstrapper` est utilisé pour initialiser le dépôt, prévoir d'y exclure au minimum :

| Fichier / motif | Recommandation |
|---|---|
| `sorties/` | Dossier de sortie horodaté généré à chaque exécution (HTML/PNG/JSON/CSV réels de la machine de l'utilisateur) — ne doit jamais être commité. |
| `.venv/` | Environnement virtuel créé par `install.sh` / `install.ps1` — local à chaque machine. |
| `build/`, `dist/`, `*.spec` | Artefacts PyInstaller. |
| `__pycache__/`, `*.pyc` | Cache Python (déjà présent dans ce dossier de travail). |
| `demo_data.json`, `demo_graph_3d.html`, `demo_graph.png` | À régénérer avec des données propres avant publication (voir ci-dessus) plutôt qu'à exclure définitivement — ce sont des exemples utiles au projet. |

## Résumé

Aucun secret/identifiant exploitable trouvé dans le code, les installeurs ou la documentation, y compris dans les deux nouveaux scripts `install.sh`/`install.ps1`. Le seul point d'attention reste, inchangé depuis la passe précédente, le contenu des trois fichiers de démo qui reflètent une vraie exécution sur cette machine de développement — à régénérer proprement avant toute publication publique ou avant d'utiliser `github-repo-bootstrapper`/`github-repo-promoter` pour préparer un dépôt destiné à être public.
