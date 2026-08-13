# Plan d'enrichissement — analyseur_processus_allinone.py

Ce document reprend le diagnostic fourni (8 domaines) et le décline en 25 enrichissements concrets, priorisés. La logique reste celle du diagnostic : passer de l'accumulation de capacités à la fiabilité des résultats, la réduction du bruit, la traçabilité des décisions et l'aide concrète au diagnostic.

Chaque item indique son statut : **[Implémenté]** = déjà dans `analyseur_processus_allinone.py` à la date de ce document, **[Roadmap]** = proposé, pas encore fait.

## Sécurité — Très haute priorité

Constat du diagnostic : le niveau de risque est produit par le modèle IA, donc trop dépendant de l'IA et insuffisamment fondé sur des règles observables.

1. **[Implémenté]** Moteur de règles déterministe pour le niveau de risque (`compute_rule_based_risk`), indépendant de l'IA : exécutable hors répertoires standards, lancé depuis un répertoire temporaire (`/tmp`, `/var/tmp`, `/dev/shm`, `%TEMP%`), exécutable disparu du disque, écoute sur toutes les interfaces (`0.0.0.0`/`::`), ligne de commande vide alors que le process tourne, volume inhabituel de connexions externes distinctes. Chaque règle déclenchée est tracée (`signaux_regles`), jamais un score opaque.
2. **[Implémenté]** L'avis Ollama devient un second avis annoté séparément (`niveau_ia` vs `niveau_regles`) : le niveau final affiché est le plus élevé des deux (`niveau_final`, combinaison "escalade seulement" — sous-estimer un risque est pire que le sur-estimer). Un badge "avis divergents" apparaît si l'IA et les règles ne s'accordent pas.
3. **[Roadmap]** Liste blanche/liste noire configurable (YAML/JSON externe) de processus connus (navigateurs, éditeurs, daemons système) pour réduire encore le bruit du scoring sans dépendre de l'IA.
4. **[Roadmap]** Historique des changements de risque par processus entre deux exécutions successives (comparaison avec la capture précédente dans `sorties/`) pour repérer une dérive dans le temps plutôt qu'un instantané isolé.

## Collecte — Très haute priorité

Constat du diagnostic : bonne couverture générale, mais mesures parfois incomplètes sans visibilité claire.

5. **[Implémenté]** Statut de collecte explicite par processus (`collecte_incomplete`) : chaque champ qui n'a pas pu être lu (permission refusée, process disparu entre l'énumération et la lecture) est tracé nommément au lieu de silencieusement devenir `None`/`0`/liste vide. Visible dans le panneau Debug/Info verbose du HTML.
6. **[Roadmap]** Retry léger et ciblé sur les processus dont le PID disparaît pendant la collecte (au lieu d'un simple skip), avec compteur dédié dans le rapport de synthèse ("N processus éphémères manqués").
7. **[Roadmap]** Détection et flag explicite des processus zombies dans le graphe (nœud visuellement distinct), au lieu de les traiter silencieusement comme des processus normaux ou de les faire disparaître de la collecte.
8. **[Roadmap]** Mode "watch" : ré-exécution périodique légère et configurable qui ne fait que la collecte + le scoring par règles (jamais l'IA) pour détecter les changements en continu sans surcharge de calcul ni dépendance réseau.

## Graphe — Très haute priorité

Constat du diagnostic : parent/enfant, fichiers partagés et connexions réseau bien modélisés, mais graphe potentiellement dense et difficile à interpréter.

9. **[Implémenté]** Filtrage par défaut des nœuds "peu intéressants" dans le HTML 3D : un processus à faible degré de connexion, faible CPU+RAM et risque final faible est masqué par défaut (togglable depuis la légende, section "Affichage"), pour que le graphe initial reste lisible même avec 150 processus.
10. **[Roadmap]** Regroupement (clustering) des processus enfants identiques (ex. 50 threads/workers d'un même parent) en un nœud agrégé dépliable, plutôt que 50 nœuds individuels.
11. **[Roadmap]** Mode "diff" : comparer deux captures (avant/après, ou deux exécutions) et surligner dans le graphe les processus apparus, disparus ou dont le risque a changé.
12. **[Roadmap]** Édition de la disposition (layout) : proposer un mode "hiérarchique" (arborescence parent/enfant) en alternative au layout force-directed actuel, plus lisible pour l'arbre de processus pur.

## Maintenance — Très haute priorité

Constat du diagnostic : script monolithique de plus de 2000 lignes, tests et évolutions difficiles.

13. **[Roadmap]** Découpage du fichier en modules (`collecte.py`, `graphe.py`, `ia.py`, `export.py`, `ui_html.py`, `cli.py`) avec un point d'entrée qui les assemble — en conservant un mode "build single-file" (concaténation automatique) pour ne pas casser la distribution PyInstaller `--onefile`, qui a besoin d'un seul fichier source pratique à pointer.
14. **[Roadmap]** Suite de tests unitaires (pytest) sur les fonctions pures et déterministes : parsing `/proc`, `compute_rule_based_risk`, `build_graph`, sérialisation JSON/CSV — cible réaliste avant tout refactor, car ce sont les fonctions les moins couplées à l'environnement.
15. **[Roadmap]** Configuration centralisée (dataclass `Config` unique) regroupant les constantes aujourd'hui éparpillées (`RISK_COLORS`, seuils, timeouts par défaut) pour réduire les points de modification lors d'un changement de comportement.
16. **[Roadmap]** CI minimale (lint + `py_compile` + tests pytest) sur chaque modification, même en l'absence de dépôt git formel aujourd'hui — préparatoire à une éventuelle publication.

## Export — Haute priorité

Constat du diagnostic : absence de rapport synthétique, historique et formats analytiques.

17. **[Implémenté]** Rapport de synthèse Markdown généré à chaque exécution (`--report`, activé par défaut) : nombre de processus par niveau de risque final, top 5 consommateurs CPU+RAM, connexions externes distinctes, liste des processus à risque élevé avec justification, processus à collecte incomplète, statistiques d'enrichissement IA (modèle, nombre enrichi, échecs). Lisible sans ouvrir le HTML — utile en particulier en usage CLI/cron.
18. **[Implémenté]** Export CSV (`--csv-export`) en plus du JSON existant, pour ouverture directe dans un tableur (une ligne par processus, champs aplatis).
19. **[Roadmap]** Historique des exécutions : chaque run horodaté dans `sorties/`, avec un petit index HTML généré listant les runs précédents pour comparaison rapide (lien direct vers chaque rapport/graphe).

## IA locale — Haute priorité

Constat du diagnostic : préflight, warm-up, JSON et repli en cas d'erreur déjà en place, mais risque de résultats non vérifiés ou coûteux.

20. **[Roadmap]** Validation stricte du JSON retourné par Ollama via un schéma explicite (ex. `jsonschema`), avec UN retry automatique en cas de sortie non conforme (prompt légèrement reformulé) avant le repli sur l'enrichissement par défaut.
21. **[Roadmap]** Cache des enrichissements par empreinte de processus (hash de nom+chemin+cmdline) pour éviter de ré-interroger l'IA à chaque exécution sur les mêmes binaires connus déjà vus lors d'une exécution précédente.
22. **[Roadmap]** Affichage du coût réel de l'enrichissement dans le rapport de synthèse (temps total, nombre d'appels, modèle utilisé, nombre d'échecs/timeouts).

## Interface HTML 3D — Haute priorité

Constat du diagnostic : bon prototype, mais peu d'actions de diagnostic et d'accessibilité.

23. **[Roadmap]** Panneau d'actions par processus : bouton "copier PID", "copier chemin exécutable", "copier ligne de commande complète" — aucune action réseau automatique, uniquement du copier-coller local.
24. **[Roadmap]** Mode accessibilité : navigation clavier complète du graphe et du panneau, contrastes vérifiés, table HTML alternative au rendu 3D pour lecteurs d'écran.
25. **[Roadmap]** Export direct depuis l'UI du sous-ensemble actuellement filtré/visible (JSON/CSV), pour ne pas devoir relancer une analyse complète juste pour extraire une vue filtrée.

## Résumé des choix de cette itération (Phase 1)

Implémentés dans cette passe, en couvrant les 4 domaines classés "Très haute priorité" plus une partie de "Haute" :

- Sécurité : items 1, 2
- Collecte : item 5
- Graphe : item 9
- Export : items 17, 18

Volontairement laissés en roadmap : le découpage modulaire du fichier (item 13) et les tests unitaires (item 14), qui sont les changements à plus fort risque de régression et les plus longs à valider correctement — mieux vaut les traiter dans une itération dédiée, une fois cette base fonctionnelle re-testée en conditions réelles.
