# Politique de sécurité

## Versions supportées

Ce projet n'a pas encore de version taguée (dépôt local, pas encore de premier tag/release). Tant qu'aucune release n'existe, seule la copie de travail actuelle (branche par défaut) est « supportée » — cette section sera remplacée par un vrai tableau de versions dès le premier tag.

## Portée

`analyseur_processus_allinone.py` analyse les processus **de la machine sur laquelle il tourne**, n'envoie aucune donnée collectée à un service externe, et n'ouvre aucun port réseau. Les deux points de contact réseau du projet sont documentés dans le README (section Confidentialité) :

- le chargement de la librairie `3d-force-graph` depuis un CDN public (`unpkg.com`) à l'ouverture du fichier HTML généré ;
- les appels vers un serveur **Ollama** local (`http://localhost:11434` par défaut, configurable).

Une vulnérabilité dans ce projet concernerait typiquement : une exécution de code non prévue via un fichier HTML généré (ex. données de processus mal échappées avant injection dans le HTML/JS), une élévation de privilèges via les installeurs (`install.sh` / `install.ps1`), ou une fuite de données locales (chemins, IP, utilisateur) au-delà de ce qui est documenté.

## Signaler une vulnérabilité

Merci de **ne pas ouvrir d'issue publique** pour un problème de sécurité tant qu'il n'a pas été corrigé.

- **Préféré** : le [signalement privé de vulnérabilités GitHub](https://github.com/TFD-42/Proc_Map_Analyzer/security/advisories/new).
- **Alternative** : contacter le mainteneur en privé via GitHub ([@TFD-42](https://github.com/TFD-42)) — aucun canal email n'est publié pour ce projet.

Merci d'inclure : une description de la vulnérabilité et de son impact potentiel, les étapes de reproduction (ou une preuve de concept), et les mitigations connues le cas échéant.

Ce projet est un projet d'étude/local maintenu de façon best-effort (pas de SLA formel) : compte sur un délai de premier retour de l'ordre de quelques jours plutôt qu'une réponse garantie sous 24h.
