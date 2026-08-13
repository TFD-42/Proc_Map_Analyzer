#!/usr/bin/env python3
"""
analyseur_processus_allinone.py
================================

Version TOUT-EN-UN, pensée pour un utilisateur novice et pour être
packagée avec PyInstaller (--onefile --console). Fusionne dans un seul
fichier : l'analyse des processus système, leurs fichiers liés (exécutable,
cwd, fichiers ouverts) et leurs relations (parent/enfant, fichiers
partagés, connexions réseau), l'enrichissement via un modèle Ollama local,
le rendu PNG statique + HTML 3D interactif, ET un assistant interactif
("wizard") qui remplace le launcher .command séparé.

Multi-plateforme : Windows / macOS / Linux (via psutil, compilable en
exécutable PyInstaller) ET Android/Termux (via un fallback léger basé sur
/proc, psutil n'étant pas installable sur Android — cf. H14/H15/H16). Sur
Termux, PAS de compilation possible (PyInstaller ne cible pas Android) :
lancer directement `python analyseur_processus_allinone.py` après
`pkg install python`.

Deux modes d'exécution :
  - Double-clic / lancement SANS argument -> assistant interactif (2
    questions : nombre max de processus, choix du modèle Ollama détecté),
    puis ouverture automatique des résultats et pause avant fermeture de
    la fenêtre (utile pour un .exe PyInstaller en mode console).
  - Lancement AVEC des arguments -> comportement CLI classique (voir
    --help), pour un usage avancé/scripté/cron, inchangé par rapport à
    l'ancien process_graph_analyzer.py.

Construire l'exécutable (PyInstaller doit être installé, DANS LE MÊME
environnement/venv que psutil/networkx/matplotlib/requests, sinon
PyInstaller ne peut pas les voir pour les embarquer :
pip install pyinstaller) :

    pyinstaller --onefile --console --name AnalyseurProcessus \
        --collect-all psutil \
        --collect-submodules matplotlib \
        analyseur_processus_allinone.py

  --console est nécessaire : l'assistant interactif et la pause avant
  fermeture ont besoin d'une console visible.
  --collect-all psutil est nécessaire : psutil embarque une extension
  compilée spécifique à l'OS (_psutil_osx / _psutil_linux /
  _psutil_windows) que l'analyse statique de PyInstaller ne détecte pas
  toujours automatiquement (observé en pratique sur macOS : l'exécutable
  se lance mais échoue immédiatement avec "module manquant : psutil") ;
  --collect-all force l'inclusion de cette extension binaire.
  --collect-submodules matplotlib : PyInstaller ne détecte pas toujours
  automatiquement tous les sous-modules de matplotlib (backends, etc.).
  Si un AUTRE module signale une erreur "manquant" à l'exécution malgré
  cette commande, la cause la plus fréquente est que ce module n'était
  pas installé dans l'environnement Python utilisé pour LANCER pyinstaller
  (vérifier avec `pip show <module>` dans ce même environnement avant de
  recompiler) — PyInstaller ne peut embarquer que ce qu'il voit installé
  localement au moment du build, pas ce que _check_dependencies()
  installerait à l'exécution d'un .py brut.

Hypothèses posées (aucune précision fournie par l'utilisateur sur ces points) :
  H1. Modèle Ollama par défaut : "llama3.2" (--model pour changer).
  H2. Hôte Ollama par défaut : http://localhost:11434 (--ollama-host).
  H3. Pour éviter un temps d'exécution trop long, seuls les N processus
      les plus consommateurs (CPU + RAM) sont enrichis par défaut
      (--enrich-limit, défaut 25). Utiliser --enrich-all pour tout enrichir.
  H4. Une arête "fichier partagé" n'est tracée que si le fichier est
      ouvert par >= 2 processus, pour limiter le bruit visuel (les fichiers
      ouverts par un seul processus restent dans les données mais ne sont
      pas dessinés comme nœuds séparés).
  H5. Niveaux de risque attendus de l'enrichissement Ollama :
      "faible" / "moyen" / "élevé" / "inconnu" (si le JSON renvoyé par
      Ollama ne suit pas le schéma demandé, on retombe sur "inconnu" et on
      logue un avertissement plutôt que de faire planter le script).
  H6. Si psutil ou l'accès à certains processus est refusé (permissions),
      le processus est simplement ignoré (logué en DEBUG), le script
      continue.
  H7. Connexions réseau : au plus 20 connexions brutes par processus sont
      collectées (--max-conn-per-process), et au plus 300 arêtes de
      connexion au total sont dessinées (--max-conn-total, triées par
      processus le plus actif) pour garder le graphe lisible ; le nombre
      de connexions ignorées est logué, jamais tronqué silencieusement.
      Sur macOS, lister les connexions d'un processus qui n'appartient pas
      à l'utilisateur courant nécessite `sudo` — sans ça, ces processus
      auront simplement 0 connexion visible (pas une erreur).
  H8. Assistant interactif : valeur par défaut de 150 processus max inclus
      dans le graphe (les plus actifs CPU+RAM en priorité, --max-processes
      en CLI pour changer/désactiver). Le nombre de processus enrichis par
      IA est dérivé automatiquement (min(max_processes, 40)) plutôt que de
      poser une 3e question.
  H9. Auto-installation des dépendances manquantes (pip) UNIQUEMENT si le
      script tourne en .py brut (sys.frozen absent). Dans un exécutable
      PyInstaller figé, une dépendance manquante est un bug de build : on
      échoue avec un message clair plutôt que de tenter une installation
      qui n'a pas de sens dans ce contexte (pas forcément de pip/réseau
      sur la machine finale).
  H10. Détection des modèles Ollama via l'API HTTP (GET /api/tags) plutôt
      que via la commande `ollama list`, pour ne pas dépendre du binaire
      `ollama` sur le PATH — seul le SERVEUR Ollama doit être joignable,
      ce qui reste valable depuis un .exe empaqueté.
  H11. Timeout Ollama par défaut : 120s (--timeout), parallélisme par
      défaut : 2 (--max-workers). Un LLM local sert le plus souvent les
      requêtes de génération de façon séquentielle (un seul GPU/CPU) ; une
      forte parallélisation ne fait qu'empiler des requêtes en file
      d'attente sans rien accélérer, et les fait toutes expirer ensemble
      (observé : rafales de timeouts à exactement 30.0s avec l'ancien
      défaut --max-workers=4/--timeout=30). Un appel de "préchauffage" est
      aussi effectué une fois avant la boucle pour charger le modèle en
      mémoire (peut prendre jusqu'à une minute pour un modèle de plusieurs
      Go) sans consommer le budget de temps d'un processus enrichi ; et la
      longueur de chaque réponse générée est plafonnée (num_predict=220)
      pour borner le pire cas de latence par appel.
  H12. Si Ollama n'est pas détecté DU TOUT sur la machine, l'assistant
      propose une installation automatique adaptée à l'OS (Homebrew sur
      macOS, script officiel sur Linux, installeur .exe sur Windows) —
      UNIQUEMENT avec l'accord explicite de l'utilisateur (jamais
      silencieux, car ça installe un logiciel tiers). Si Ollama tourne
      mais qu'aucun modèle n'est installé, l'assistant propose ensuite de
      télécharger le modèle par défaut (llama3:latest, plusieurs Go, cf.
      DEFAULT_OLLAMA_MODEL) via l'API HTTP (POST /api/pull) avec barre de
      progression. Refuser l'une ou l'autre proposition désactive
      simplement l'enrichissement IA, jamais un échec fatal.
  H13. Dans l'assistant novice, seul le graphe 3D interactif (HTML) est
      ouvert automatiquement à la fin — c'est le livrable principal. Le
      PNG et le JSON restent écrits sur disque mais ne sont pas ouverts
      automatiquement (évite d'empiler une visionneuse d'image en plus du
      navigateur).
  H14. Sur Android/Termux (détecté via ANDROID_ROOT/ANDROID_DATA/PREFIX
      contenant "com.termux", ou présence de /system/build.prop), psutil
      est remplacé par un backend maison qui lit directement /proc/<pid>/*
      (même principe que l'implémentation interne de psutil sous Linux).
      Sans root, Android restreint nativement la visibilité aux processus
      de l'utilisateur courant (SELinux / hidepid) — les autres processus
      apparaissent simplement invisibles ou en accès refusé, comme le
      ferait déjà psutil dans la même situation sur un Linux classique :
      ce n'est pas un bug de ce script mais une restriction de l'OS.
  H15. Le CPU% renvoyé par le backend /proc est une MOYENNE depuis le
      démarrage du processus (temps CPU cumulé / âge du processus), pas un
      delta instantané comme psutil (qui nécessite deux échantillons
      espacés dans le temps). Suffisant pour trier/prioriser les
      processus (seul usage qu'en fait ce script), pas pour un monitoring
      temps réel précis — assumé et documenté plutôt que déguisé en
      mesure équivalente à psutil.
  H16. Le backend /proc ne décode que les connexions TCP/UDP IPv4 et les
      sockets UNIX (via /proc/net/tcp, /proc/net/udp, /proc/net/unix
      croisés avec les inodes de /proc/<pid>/fd/*) ; les connexions IPv6
      ne sont pas décodées (limitation acceptée pour rester simple, IPv4
      reste très majoritaire pour ce cas d'usage).
  H17. Le niveau de risque affiché ("niveau_final") N'EST PLUS produit
      uniquement par Ollama. Un moteur de règles déterministe
      (compute_rule_based_risk) calcule d'abord un niveau ("niveau_regles")
      à partir de signaux observables (exécutable hors répertoires
      standards, lancé depuis un répertoire temporaire, exécutable disparu
      du disque, écoute sur toutes les interfaces, cmdline vide, volume
      inhabituel de connexions externes). L'avis Ollama ("niveau_ia"), s'il
      existe, est combiné par ESCALADE UNIQUEMENT : niveau_final = le plus
      élevé des deux, jamais le plus bas — sous-estimer un risque est jugé
      pire que le sur-estimer. Une divergence entre les deux avis est
      tracée explicitement plutôt que masquée.
  H18. Dans le graphe 3D, un processus est marqué "peu intéressant"
      (low_interest, masqué par défaut, togglable) si les trois conditions
      suivantes sont réunies : degré de graphe <= 1 (aucune ou une seule
      relation), cpu+mem < 1.0, ET niveau_final == "faible". Seuils choisis
      pour ne masquer que des processus visiblement inactifs et jamais un
      processus à risque, quelle que soit son activité.
  H19. Sortie par défaut réduite au SEUL graphe 3D interactif (HTML) : ni
      PNG, ni JSON, ni CSV, ni rapport Markdown ne sont écrits sans que
      l'utilisateur les demande explicitement (--png, --json-export,
      --csv-export, --report). L'assistant novice ne pose donc plus qu'une
      seule question de sortie implicite (où écrire le HTML) et ouvre
      directement ce fichier — le rapport reste un Markdown simple (pas de
      dépendance supplémentaire) quand il est demandé en CLI.
  H20. Contrôles caméra du HTML 3D : en plus des boutons à l'écran et de la
      touche R seule (recentrer), Ctrl+R recentre aussi (et bloque le
      rechargement de page par le navigateur), Ctrl++ / Ctrl+= zoome en
      avant, Ctrl+- zoome en arrière (et bloque le zoom navigateur natif) —
      raccourcis clavier explicitement demandés en plus des boutons.
  H21. Détection de conteneur via /proc/<pid>/cgroup (Docker, Podman,
      containerd, Kubernetes) — Linux uniquement, silencieusement absent
      ailleurs. Id de conteneur raccourci à 12 caractères comme docker ps.
  H22. --check-integrity : SHA256 de chaque exécutable, comparé à une base
      de référence JSON (--integrity-db). Une empreinte MODIFIÉE est un
      signal "eleve" et n'écrase JAMAIS la référence (supprimer la base
      pour repartir de zéro après une mise à jour légitime). Fichiers
      > 200 Mo non hachés.
  H23. --config : whitelist/blacklist (YAML simple parsé à la main OU JSON,
      pas de dépendance pyyaml). Motifs fnmatch OU sous-chaîne, comparés au
      nom + exe + cmdline. Whitelist = neutralise uniquement les signaux de
      CHEMIN (jamais réseau/deleted) ; blacklist = "eleve" immédiat.
  H24. --baseline : moyenne/variance glissantes (algorithme de Welford) de
      CPU/RAM par NOM de processus dans un JSON. Anomalie signalée (niveau
      "moyen") si valeur > moyenne + 2 écarts-types, avec au moins 3
      échantillons, un écart-type > 0.05 et une valeur >= 5% (évite le
      bruit des processus quasi inactifs).
  H25. --retry-failed N : seules les raisons d'échec transitoires (timeout,
      Ollama injoignable/saturé, JSON invalide) sont retentées, en SÉRIE
      avec backoff exponentiel 1s/2s/4s (re-paralléliser un serveur saturé
      aggraverait le problème).
  H26. --cache : cache SQLite des enrichissements, clé =
      SHA256(nom+exe+cmdline), TTL 7 jours (--cache-ttl-days). Les échecs
      ne sont jamais mis en cache ; les résultats servis du cache sont
      marqués from_cache pour rester distinguables.
  H27. --plugin : module Python UTILISATEUR chargé explicitement, exposant
      enrich(process_info: dict) -> dict, résultat fusionné sous
      enrichment["plugin"]. Erreurs de plugin loguées, jamais fatales.
  H28. --csv-edges : export des ARÊTES du graphe (source, target, kind,
      labels, niveaux de risque des deux extrémités) pour Gephi/Neo4j.
  H29. Historique automatique des exécutions (sorties/history.json, 50
      snapshots légers max, désactivable par --no-history, jamais alimenté
      en mode --sandbox). --compare sans valeur = comparer à l'exécution
      précédente ; --compare <fichier> accepte un export --json-export ou
      un snapshot d'historique.
  H30. --pid : analyse restreinte au sous-arbre (ancêtres + descendance) du
      processus cible + rapport texte forensique détaillé sur stdout ; le
      HTML reste généré, limité à ce sous-arbre.
  H31. --sandbox : rejoue un fichier JSON au format --json-export au lieu
      de collecter le système (test des règles/config/rendu sans risque).
  H32. --watch : boucle collecte + règles + rendu HTML toutes les
      --interval secondes (minimum 5s), différences affichées entre cycles.
      JAMAIS d'appel Ollama dans la boucle (l'enrichissement IA reste un
      acte one-shot explicite) ; Ctrl+C arrête proprement.
  H33. --preload-model : démarre/installe Ollama si nécessaire, télécharge
      le modèle demandé puis quitte sans analyse (préparation hors-ligne).
  H34. HTML : boutons "copier" (PID, exécutable, commande, kill <pid>,
      SHA256) avec repli execCommand quand navigator.clipboard est absent
      (file://) ; raccourcis Échap (fermer le panneau / quitter la
      recherche), / (rechercher), 1-5 (changer de mode).
  H35. Modèle Ollama par défaut ADAPTÉ À LA MACHINE, même politique dans
      install.sh, install.ps1 et ce script : mini "llama3.2:1b" (~1,3 Go)
      sur Android/Termux (RAM/stockage limités), medium "llama3:latest"
      (~4,7 Go) sur macOS/Windows/Linux — appliqué au défaut de --model
      (llama3.2:1b vs llama3.2) et au téléchargement proposé par
      l'assistant (DEFAULT_OLLAMA_MODEL). Sous Termux, Ollama s'installe
      via le paquet des dépôts Termux (pkg install ollama), jamais via le
      script ollama.com (incompatible Android) — dégradation propre en
      "sans IA" si le paquet est indisponible.

Dépendances : networkx, matplotlib, requests, et psutil PARTOUT SAUF sur
Android/Termux (où il est remplacé par le fallback /proc décrit ci-dessus) :
    pip install networkx matplotlib requests psutil
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import fnmatch
import hashlib
import json
import logging
import os
import platform
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("analyseur_processus_allinone")

# True quand ce script tourne comme exécutable PyInstaller figé (par
# opposition à un lancement `python3 analyseur_processus_allinone.py` brut).
IS_FROZEN = bool(getattr(sys, "frozen", False))


def _pause_before_exit() -> None:
    """Empêche la fenêtre console de se fermer instantanément (essentiel
    pour un .exe PyInstaller --console double-cliqué par un novice)."""
    try:
        input("\nAppuie sur Entrée pour fermer cette fenêtre...")
    except (EOFError, KeyboardInterrupt):
        pass


def _is_android() -> bool:
    """Détecte Android/Termux via plusieurs signaux combinés (H14) — aucun
    n'est garanti seul, donc on les cumule : variables d'environnement
    spécifiques à Android, préfixe Termux, ou présence de la partition
    système /system (absente sur toute autre plateforme POSIX)."""
    if "ANDROID_ROOT" in os.environ or "ANDROID_DATA" in os.environ:
        return True
    if "com.termux" in os.environ.get("PREFIX", ""):
        return True
    return Path("/system/build.prop").exists()


IS_ANDROID = _is_android()


# ---------------------------------------------------------------------------
# Fallback de collecte des processus basé sur /proc (H14) — utilisé
# uniquement quand psutil est indisponible, ce qui est le cas SYSTÉMATIQUE
# sur Android/Termux : psutil ne fournit pas de wheel pour Android et son
# installation depuis les sources est explicitement refusée par son propre
# setup.py ("platform android is not supported"), donc l'auto-installation
# habituelle (H9) ne peut pas résoudre le problème — il faut un backend de
# collecte alternatif plutôt qu'insister sur pip.
#
# Implémentation volontairement minimale : ne couvre que le sous-ensemble
# de l'API psutil.Process réellement utilisé par ce script, en lisant
# directement /proc/<pid>/*. C'est la même technique que celle qu'utilise
# psutil lui-même en interne sous Linux.
# ---------------------------------------------------------------------------

class _FallbackAccessDenied(Exception):
    pass


class _FallbackNoSuchProcess(Exception):
    pass


class _FallbackZombieProcess(Exception):
    pass


_TCP_STATES = {
    "01": "ESTABLISHED", "02": "SYN_SENT", "03": "SYN_RECV", "04": "FIN_WAIT1",
    "05": "FIN_WAIT2", "06": "TIME_WAIT", "07": "CLOSE", "08": "CLOSE_WAIT",
    "09": "LAST_ACK", "0A": "LISTEN", "0B": "CLOSING",
}

# Table inode-de-socket -> infos de connexion, reconstruite une fois par
# collecte (voir _FallbackPsutilModule.process_iter) plutôt qu'une fois par
# processus, pour éviter de reparser /proc/net/* des centaines de fois.
_fallback_inode_map_cache: Optional[dict] = None


def _decode_proc_ipv4_addr(field: str) -> Optional[str]:
    """Décode un champ "hexIP:hexPORT" de /proc/net/{tcp,udp} en
    "a.b.c.d:port" (IPv4 uniquement — H16 : les connexions IPv6 ne sont pas
    décodées par ce fallback, limitation acceptée pour rester simple)."""
    try:
        hexip, hexport = field.split(":")
        raw = bytes.fromhex(hexip)
        ip = ".".join(str(b) for b in raw[::-1])
        port = int(hexport, 16)
        return f"{ip}:{port}"
    except Exception:
        return None


def _build_proc_inode_map() -> dict:
    mapping: dict = {}
    for fname, protocol in (("tcp", "tcp"), ("udp", "udp")):
        try:
            lines = Path(f"/proc/net/{fname}").read_text(errors="replace").splitlines()[1:]
        except Exception:
            continue
        for line in lines:
            parts = line.split()
            if len(parts) < 10:
                continue
            laddr = _decode_proc_ipv4_addr(parts[1])
            raddr = _decode_proc_ipv4_addr(parts[2])
            if raddr in (None, "0.0.0.0:0"):
                raddr = None
            status = _TCP_STATES.get(parts[3], "") if protocol == "tcp" else ""
            mapping[parts[9]] = (protocol, laddr, raddr, status)
    try:
        lines = Path("/proc/net/unix").read_text(errors="replace").splitlines()[1:]
        for line in lines:
            parts = line.split()
            if len(parts) < 7:
                continue
            path = parts[7] if len(parts) > 7 else None
            mapping[parts[6]] = ("unix", path, None, "")
    except Exception:
        pass
    return mapping


class _SimpleConn:
    __slots__ = ("laddr", "raddr", "family", "type", "status")

    def __init__(self, laddr, raddr, family, type_, status):
        self.laddr = laddr
        self.raddr = raddr
        self.family = family
        self.type = type_
        self.status = status


class _SimpleOpenFile:
    __slots__ = ("path",)

    def __init__(self, path):
        self.path = path


class _FallbackProcess:
    """Ré-implémentation minimale, basée sur /proc, du sous-ensemble de
    l'API psutil.Process utilisé par ce script (H14/H15)."""

    def __init__(self, pid: int):
        self.pid = pid
        if not Path(f"/proc/{pid}").is_dir():
            raise _FallbackNoSuchProcess(pid)

    def _proc_path(self, name: str) -> Path:
        return Path(f"/proc/{self.pid}/{name}")

    def _read_text(self, name: str) -> str:
        try:
            return self._proc_path(name).read_text(errors="replace")
        except PermissionError:
            raise _FallbackAccessDenied(self.pid)
        except (FileNotFoundError, ProcessLookupError):
            raise _FallbackNoSuchProcess(self.pid)

    def oneshot(self):
        return contextlib.nullcontext()

    def ppid(self) -> int:
        try:
            after = self._read_text("stat").rsplit(") ", 1)[1].split()
            return int(after[1])
        except (_FallbackAccessDenied, _FallbackNoSuchProcess):
            raise
        except Exception:
            return 0

    def name(self) -> str:
        try:
            return self._read_text("comm").strip()
        except (_FallbackAccessDenied, _FallbackNoSuchProcess):
            raise
        except Exception:
            return f"pid-{self.pid}"

    def username(self) -> Optional[str]:
        try:
            uid = self._proc_path("").stat().st_uid
            import pwd
            return pwd.getpwuid(uid).pw_name
        except Exception:
            return None

    def exe(self) -> Optional[str]:
        try:
            return os.readlink(self._proc_path("exe"))
        except Exception:
            return None

    def cwd(self) -> Optional[str]:
        try:
            return os.readlink(self._proc_path("cwd"))
        except Exception:
            return None

    def cmdline(self) -> list[str]:
        try:
            raw = self._read_text("cmdline")
            return [part for part in raw.split("\x00") if part]
        except (_FallbackAccessDenied, _FallbackNoSuchProcess):
            raise
        except Exception:
            return []

    def cpu_percent(self, interval=None) -> float:
        # Approximation (H15) : %CPU MOYEN depuis le démarrage du processus
        # (temps CPU cumulé / âge du processus), pas un delta instantané
        # comme psutil — suffisant pour trier/prioriser les processus,
        # mais pas pour un monitoring temps réel précis. Documenté plutôt
        # que présenté comme équivalent à la vraie mesure psutil.
        try:
            fields = self._read_text("stat").rsplit(") ", 1)[1].split()
            utime, stime = int(fields[11]), int(fields[12])
            starttime_ticks = int(fields[19])
            clk_tck = os.sysconf("SC_CLK_TCK")
            uptime = float(Path("/proc/uptime").read_text().split()[0])
            process_age = max(uptime - (starttime_ticks / clk_tck), 0.1)
            cpu_seconds = (utime + stime) / clk_tck
            return round(min(cpu_seconds / process_age * 100, 100.0), 2)
        except (_FallbackAccessDenied, _FallbackNoSuchProcess):
            raise
        except Exception:
            return 0.0

    def memory_percent(self) -> float:
        try:
            rss_kb = 0
            for line in self._read_text("status").splitlines():
                if line.startswith("VmRSS:"):
                    rss_kb = int(line.split()[1])
                    break
            total_kb = _fallback_mem_total_kb()
            return round(rss_kb / total_kb * 100, 3) if total_kb else 0.0
        except (_FallbackAccessDenied, _FallbackNoSuchProcess):
            raise
        except Exception:
            return 0.0

    def open_files(self) -> list:
        try:
            entries = list(self._proc_path("fd").iterdir())
        except PermissionError:
            raise _FallbackAccessDenied(self.pid)
        except FileNotFoundError:
            raise _FallbackNoSuchProcess(self.pid)
        results = []
        for entry in entries:
            try:
                target = os.readlink(entry)
            except OSError:
                continue
            if target.startswith("/") and not target.startswith(("/proc", "/dev")):
                results.append(_SimpleOpenFile(target))
        return results

    def net_connections(self, kind: str = "inet") -> list:
        global _fallback_inode_map_cache
        if _fallback_inode_map_cache is None:
            _fallback_inode_map_cache = _build_proc_inode_map()
        try:
            entries = list(self._proc_path("fd").iterdir())
        except PermissionError:
            raise _FallbackAccessDenied(self.pid)
        except FileNotFoundError:
            raise _FallbackNoSuchProcess(self.pid)
        results = []
        for entry in entries:
            try:
                target = os.readlink(entry)
            except OSError:
                continue
            if not target.startswith("socket:["):
                continue
            inode = target[len("socket:["):-1]
            info = _fallback_inode_map_cache.get(inode)
            if not info:
                continue
            protocol, laddr, raddr, status = info
            family = socket.AF_UNIX if protocol == "unix" else socket.AF_INET
            type_ = socket.SOCK_DGRAM if protocol == "udp" else socket.SOCK_STREAM
            results.append(_SimpleConn(laddr=laddr, raddr=raddr, family=family, type_=type_, status=status))
        return results

    # Alias : le code appelant essaie net_connections() puis connections()
    # (compat anciennes versions de psutil) — les deux pointent ici.
    connections = net_connections


def _fallback_mem_total_kb() -> int:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1])
    except Exception:
        pass
    return 0


class _FallbackPsutilModule:
    """Substitut minimal de l'API psutil réellement utilisée par ce script
    (H14), activé uniquement quand le vrai psutil est indisponible."""

    AccessDenied = _FallbackAccessDenied
    NoSuchProcess = _FallbackNoSuchProcess
    ZombieProcess = _FallbackZombieProcess
    Process = _FallbackProcess

    @staticmethod
    def process_iter(attrs=None):
        global _fallback_inode_map_cache
        _fallback_inode_map_cache = None  # invalidé à chaque nouvelle collecte
        try:
            pids = sorted(int(name) for name in os.listdir("/proc") if name.isdigit())
        except Exception:
            pids = []
        for pid in pids:
            try:
                yield _FallbackProcess(pid)
            except _FallbackNoSuchProcess:
                continue


# ---------------------------------------------------------------------------
# Vérification des dépendances (échec explicite plutôt qu'un ImportError brut)
# ---------------------------------------------------------------------------

_REQUIRED_MODULES = (
    ("networkx", "networkx"),
    ("matplotlib", "matplotlib"),
    ("requests", "requests"),
)
if not IS_ANDROID:
    # psutil est requis PARTOUT SAUF sur Android/Termux (H14), où son
    # wheel n'existe pas et sa compilation échoue explicitement — le
    # fallback /proc ci-dessus prend le relais dans ce cas, donc inutile
    # (et voué à l'échec) de tenter de l'installer via pip.
    _REQUIRED_MODULES = (("psutil", "psutil"),) + _REQUIRED_MODULES


def _missing_modules() -> list[str]:
    import importlib.util
    return [pip_name for mod_name, pip_name in _REQUIRED_MODULES if importlib.util.find_spec(mod_name) is None]


def _check_dependencies() -> None:
    """Vérifie la présence des dépendances et, en mode .py brut (H9),
    tente une installation automatique via pip avant d'abandonner."""
    if IS_ANDROID:
        print(
            "Android / Termux détecté : psutil n'est pas disponible sur cette plateforme "
            "(non installable), un mode de collecte allégé basé sur /proc est utilisé à la "
            "place. Le CPU% est une moyenne depuis le démarrage du processus (pas un instantané "
            "temps réel), et Android limite nativement la visibilité aux processus de "
            "l'utilisateur courant — ce sont des restrictions de la plateforme, pas des bugs "
            "(détails : H14/H15 dans l'en-tête du script)."
        )

    missing = _missing_modules()
    if not missing:
        return

    if IS_FROZEN:
        print(f"ERREUR : module(s) manquant(s) dans l'exécutable : {', '.join(missing)}")
        print("Ceci est un bug d'empaquetage (PyInstaller) et ne peut pas se corriger tout seul.")
        print("Recompiler l'exécutable avec --collect-submodules / --collect-all pour le(s) module(s) concerné(s).")
        _pause_before_exit()
        sys.exit(1)

    print(f"Module(s) Python manquant(s) : {', '.join(missing)}")
    print("Installation automatique en cours (pip)...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *missing])
    except subprocess.CalledProcessError:
        # Repli pour les environnements Python "gérés en externe" (PEP 668)
        # qui refusent pip install sans --break-system-packages.
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "--quiet",
                "--break-system-packages", *missing,
            ])
        except subprocess.CalledProcessError as exc:
            print(f"Échec de l'installation automatique : {exc}")
            print(f"Installe manuellement : {sys.executable} -m pip install {' '.join(missing)}")
            if IS_ANDROID:
                print(
                    "Sur Termux, si l'échec concerne matplotlib (dépendances de compilation "
                    "manquantes), essaie plutôt le paquet précompilé : pkg install matplotlib"
                )
            _pause_before_exit()
            sys.exit(1)

    still_missing = _missing_modules()
    if still_missing:
        print(f"Module(s) toujours introuvable(s) après installation : {', '.join(still_missing)}")
        _pause_before_exit()
        sys.exit(1)
    print("Dépendances installées avec succès.\n")


_check_dependencies()

if IS_ANDROID:
    psutil = _FallbackPsutilModule()
else:
    import psutil  # noqa: E402
import networkx as nx  # noqa: E402
import requests  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")  # rendu headless, pas besoin d'affichage
import matplotlib.pyplot as plt  # noqa: E402


# ---------------------------------------------------------------------------
# Modèle de données
# ---------------------------------------------------------------------------

@dataclass
class ProcessInfo:
    pid: int
    ppid: Optional[int]
    name: str
    username: Optional[str]
    exe: Optional[str]
    cwd: Optional[str]
    cmdline: str
    cpu_percent: float
    memory_percent: float
    open_files: list = field(default_factory=list)
    connections: list = field(default_factory=list)  # cf. collect_connections()
    enrichment: Optional[dict] = None  # rempli par enrich_with_ollama()
    collecte_incomplete: list = field(default_factory=list)  # champs non lus (H : visibilité collecte)
    cmdline_vide: bool = False  # True seulement si cmdline() a réussi et renvoyé une liste vide
    risk: dict = field(default_factory=dict)  # rempli par compute_rule_based_risk() / finalize_risk() (H17)
    container: Optional[str] = None  # id/nom du conteneur (Docker/K8s) si détecté via /proc/<pid>/cgroup (H21)
    exe_sha256: Optional[str] = None  # empreinte SHA256 de l'exécutable si --check-integrity (H22)
    integrity_status: Optional[str] = None  # "nouveau" | "identique" | "modifie" | "illisible" (H22)

    @property
    def score(self) -> float:
        """Score simple pour prioriser l'enrichissement (H3)."""
        return self.cpu_percent + self.memory_percent


# ---------------------------------------------------------------------------
# 1. Collecte des processus
# ---------------------------------------------------------------------------

def _addr_to_str(addr) -> Optional[str]:
    """Normalise une adresse psutil (namedtuple ip/port, tuple brut, ou
    chemin de socket UNIX sous forme de str) en une chaîne lisible."""
    if not addr:
        return None
    if isinstance(addr, str):
        return addr
    ip = getattr(addr, "ip", None)
    port = getattr(addr, "port", None)
    if ip is not None:
        return f"{ip}:{port}"
    if isinstance(addr, (tuple, list)) and len(addr) == 2:
        return f"{addr[0]}:{addr[1]}"
    return str(addr)


def _protocol_label(conn) -> str:
    """Déduit un protocole lisible (tcp/udp/unix) d'une connexion psutil."""
    family = getattr(conn, "family", None)
    if family == getattr(socket, "AF_UNIX", object()):
        return "unix"
    if getattr(conn, "type", None) == socket.SOCK_DGRAM:
        return "udp"
    return "tcp"


def _collect_process_connections(p: "psutil.Process", limit: int, issues: Optional[list] = None) -> list[dict]:
    """Récupère jusqu'à `limit` connexions réseau/UNIX d'un processus (H7).

    Repli progressif : `net_connections` (API récente) -> `connections`
    (alias historique) -> kind="all" -> kind="inet" si la plateforme ne
    supporte pas "all". Toute erreur de permission retourne une liste vide
    plutôt que de faire planter la collecte (mais est tracée dans `issues`
    si fourni, cf. visibilité collecte).
    """
    getter = getattr(p, "net_connections", None) or getattr(p, "connections", None)
    if getter is None:
        return []
    raw = None
    for kind in ("all", "inet"):
        try:
            raw = getter(kind=kind)
            break
        except ValueError:
            continue
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError) as exc:
            if issues is not None:
                issues.append(f"connexions: {exc.__class__.__name__}")
            return []
    if not raw:
        return []

    connections = []
    for c in raw[:limit]:
        try:
            connections.append({
                "protocol": _protocol_label(c),
                "laddr": _addr_to_str(c.laddr),
                "raddr": _addr_to_str(c.raddr),
                "status": getattr(c, "status", "") or "",
            })
        except Exception:  # défensif : un enregistrement mal formé ne doit pas tout faire planter
            continue
    return connections


def _detect_container(pid: int) -> Optional[str]:
    """Détecte si un processus tourne dans un conteneur (Docker, Podman,
    containerd, Kubernetes) en lisant /proc/<pid>/cgroup — Linux uniquement
    (H21). Retourne un identifiant court de conteneur, ou None si le
    processus tourne sur l'hôte / si la plateforme ne le permet pas."""
    cgroup_path = Path(f"/proc/{pid}/cgroup")
    try:
        content = cgroup_path.read_text(errors="replace")
    except OSError:
        return None
    for line in content.splitlines():
        low = line.lower()
        for marker in ("docker", "containerd", "podman", "kubepods", "libpod"):
            if marker in low:
                # Le dernier segment du chemin cgroup est en général l'id du
                # conteneur (64 hex) — on le raccourcit à 12 caractères comme
                # le fait `docker ps`.
                tail = line.rsplit("/", 1)[-1].strip()
                for prefix in ("docker-", "crio-", "libpod-"):
                    if tail.startswith(prefix):
                        tail = tail[len(prefix):]
                tail = tail.removesuffix(".scope")
                if len(tail) >= 12 and all(c in "0123456789abcdef" for c in tail[:12]):
                    return f"{marker}:{tail[:12]}"
                return marker
    return None


def collect_processes(min_score: float = 0.0, max_conn_per_process: int = 20) -> list[ProcessInfo]:
    """Recense les processus système accessibles et leurs fichiers liés.

    Les processus dont l'accès est refusé (psutil.AccessDenied) ou qui ont
    disparu entre l'énumération et la lecture (psutil.NoSuchProcess) sont
    ignorés silencieusement (H6) — c'est un comportement normal, pas une
    erreur du script.
    """
    processes: list[ProcessInfo] = []

    # cpu_percent nécessite un premier appel "d'amorçage" par processus pour
    # être significatif ; on fait donc deux passes avec un court intervalle.
    all_procs = list(psutil.process_iter(["pid"]))
    for p in all_procs:
        try:
            p.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(0.15)

    for p in all_procs:
        try:
            issues: list[str] = []
            with p.oneshot():
                pid = p.pid
                ppid = p.ppid()
                name = p.name()
                username = _safe(p.username, label="utilisateur", issues=issues)
                exe = _safe(p.exe, label="exécutable", issues=issues)
                cwd = _safe(p.cwd, label="répertoire de travail", issues=issues)
                cmdline_parts = _safe(p.cmdline, default=None, label="ligne de commande", issues=issues)
                # Vide "réellement" (cmdline() a réussi mais n'a rien renvoyé,
                # cf. compute_rule_based_risk) par opposition à une lecture en
                # échec (déjà tracée dans `issues` ci-dessus, cmdline_parts=None).
                cmdline_vide = cmdline_parts is not None and len(cmdline_parts) == 0
                cmdline = " ".join(cmdline_parts) if cmdline_parts else name
                cpu_percent = p.cpu_percent(None)
                memory_percent = round(p.memory_percent(), 3)

            open_files = []
            try:
                open_files = [f.path for f in p.open_files()]
            except (psutil.AccessDenied, psutil.NoSuchProcess, OSError) as exc:
                # Fréquent (permissions) : on continue sans les fichiers ouverts,
                # mais on le trace (visibilité collecte, cf. plan d'enrichissement).
                issues.append(f"fichiers ouverts: {exc.__class__.__name__}")

            connections = _collect_process_connections(p, limit=max_conn_per_process, issues=issues)

            info = ProcessInfo(
                pid=pid,
                ppid=ppid,
                name=name,
                username=username,
                exe=exe,
                cwd=cwd,
                cmdline=cmdline,
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                open_files=open_files,
                connections=connections,
                collecte_incomplete=issues,
                cmdline_vide=cmdline_vide,
                container=_detect_container(pid),
            )
            if info.score >= min_score:
                processes.append(info)

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            logger.debug("Processus inaccessible ignoré (pid=%s)", getattr(p, "pid", "?"))
            continue
        except Exception as exc:  # défensif : un processus ne doit pas faire planter la collecte
            logger.debug("Erreur inattendue sur un processus, ignoré : %s", exc)
            continue

    logger.info("Processus collectés : %d", len(processes))
    return processes


def _safe(fn, default=None, label: Optional[str] = None, issues: Optional[list] = None):
    """Comme avant, mais trace optionnellement dans `issues` (visibilité
    collecte) quel champ n'a pas pu être lu et pourquoi, au lieu de
    silencieusement retourner `default` sans aucune trace."""
    try:
        return fn()
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError, RuntimeError) as exc:
        if issues is not None and label:
            issues.append(f"{label}: {exc.__class__.__name__}")
        return default


def limit_processes(processes: list[ProcessInfo], max_processes: Optional[int]) -> list[ProcessInfo]:
    """Plafonne le nombre de processus inclus dans le graphe (H8),
    en conservant les plus actifs (CPU+RAM) — jamais une troncature muette :
    le nombre de processus masqués est toujours logué."""
    if not max_processes or max_processes <= 0 or len(processes) <= max_processes:
        return processes
    ranked = sorted(processes, key=lambda p: p.score, reverse=True)
    dropped = len(ranked) - max_processes
    logger.info(
        "Limite --max-processes=%d appliquée : %d processus conservés (les plus actifs), %d masqués.",
        max_processes, max_processes, dropped,
    )
    return ranked[:max_processes]


# ---------------------------------------------------------------------------
# 1ter. Configuration utilisateur whitelist/blacklist (--config, H23)
# ---------------------------------------------------------------------------
# Motifs fnmatch (`*` accepté) comparés, insensibles à la casse, au nom du
# processus, à son exécutable ET à sa ligne de commande. Whitelist : les
# signaux de CHEMIN du moteur de règles sont neutralisés (répertoire
# temporaire / hors répertoires standards) — les signaux réseau et
# "exécutable supprimé" restent actifs, une whitelist ne doit pas rendre
# aveugle. Blacklist : niveau "eleve" immédiat avec signal explicite.
USER_CONFIG: dict = {"whitelist": [], "blacklist": []}


def load_user_config(path: Path) -> dict:
    """Charge un fichier de configuration whitelist/blacklist. Formats
    acceptés : JSON ({"whitelist": [...], "blacklist": [...]}) OU un
    sous-ensemble simple de YAML (clés de premier niveau + listes "- item"),
    parsé à la main pour ne pas ajouter de dépendance pyyaml."""
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("le JSON de configuration doit être un objet")
    except json.JSONDecodeError:
        data = {}
        current_key = None
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            if not line.startswith((" ", "\t", "-")) and line.endswith(":"):
                current_key = line[:-1].strip()
                data[current_key] = []
            elif line.strip().startswith("- ") and current_key:
                item = line.strip()[2:].strip().strip("'\"")
                if item:
                    data[current_key].append(item)
    config = {
        "whitelist": [str(x).lower() for x in data.get("whitelist", []) or []],
        "blacklist": [str(x).lower() for x in data.get("blacklist", []) or []],
    }
    logger.info(
        "Configuration chargée depuis %s : %d motif(s) whitelist, %d motif(s) blacklist.",
        path, len(config["whitelist"]), len(config["blacklist"]),
    )
    return config


def _matches_patterns(p: ProcessInfo, patterns: list[str]) -> Optional[str]:
    """Retourne le premier motif qui matche le nom, l'exécutable ou la
    cmdline du processus (insensible à la casse), sinon None. Un motif sans
    joker est traité comme une recherche de sous-chaîne (plus intuitif pour
    un novice : "ollama" doit matcher "/usr/local/bin/ollama serve")."""
    candidates = [(p.name or "").lower(), (p.exe or "").lower(), (p.cmdline or "").lower()]
    for pattern in patterns:
        has_wildcard = any(c in pattern for c in "*?[")
        for value in candidates:
            if not value:
                continue
            if has_wildcard:
                if fnmatch.fnmatch(value, pattern) or fnmatch.fnmatch(value, pattern + "*"):
                    return pattern
            elif pattern in value:
                return pattern
    return None


# ---------------------------------------------------------------------------
# 1quater. Vérification d'intégrité des exécutables (--check-integrity, H22)
# ---------------------------------------------------------------------------

_INTEGRITY_MAX_BYTES = 200 * 1024 * 1024  # au-delà, on ne hache pas (binaire anormalement gros)


def _sha256_file(path: str) -> Optional[str]:
    try:
        st = os.stat(path)
        if st.st_size > _INTEGRITY_MAX_BYTES:
            return None
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def check_integrity(processes: list[ProcessInfo], db_path: Path) -> None:
    """Calcule le SHA256 de chaque exécutable et le compare à la base de
    référence `db_path` (JSON {chemin: sha256}) construite lors des passages
    précédents. Marque chaque processus : "nouveau" (première fois vu),
    "identique", "modifie" (empreinte différente — signal de risque) ou
    "illisible". La base est mise à jour avec les NOUVEAUX binaires
    uniquement ; une empreinte modifiée n'écrase JAMAIS silencieusement la
    référence (sinon la détection ne servirait à rien) — supprimer le
    fichier de base pour repartir de zéro après une mise à jour légitime."""
    known: dict[str, str] = {}
    if db_path.exists():
        try:
            known = json.loads(db_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Base d'intégrité illisible (%s) — repartira de zéro : %s", db_path, exc)

    # Un même exécutable est partagé par de nombreux processus : hacher une
    # seule fois par chemin, pas une fois par processus.
    exe_paths = {p.exe for p in processes if p.exe and "(deleted)" not in p.exe.lower()}
    hashes: dict[str, Optional[str]] = {}
    for exe in sorted(exe_paths):
        hashes[exe] = _sha256_file(exe)

    n_new = n_same = n_modified = 0
    for p in processes:
        exe = p.exe
        if not exe or exe not in hashes:
            continue
        digest = hashes[exe]
        p.exe_sha256 = digest
        if digest is None:
            p.integrity_status = "illisible"
        elif exe not in known:
            p.integrity_status = "nouveau"
            n_new += 1
        elif known[exe] == digest:
            p.integrity_status = "identique"
            n_same += 1
        else:
            p.integrity_status = "modifie"
            n_modified += 1

    for exe, digest in hashes.items():
        if digest and exe not in known:
            known[exe] = digest

    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text(json.dumps(known, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "Intégrité : %d binaire(s) haché(s) — %d nouveau(x), %d identique(s), %d MODIFIÉ(S). Base : %s",
        len(hashes), n_new, n_same, n_modified, db_path,
    )
    if n_modified:
        logger.warning("%d binaire(s) ont une empreinte DIFFÉRENTE de la référence — vérifier les processus marqués.", n_modified)


# ---------------------------------------------------------------------------
# 1quinquies. Baseline de performance + détection d'anomalies (--baseline, H24)
# ---------------------------------------------------------------------------

def load_baseline(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Baseline illisible (%s) — ignorée : %s", path, exc)
        return {}


def update_baseline(processes: list[ProcessInfo], path: Path) -> None:
    """Met à jour des statistiques glissantes (moyenne/variance de Welford)
    de CPU%% et RAM%% PAR NOM de processus. Chaque exécution avec --baseline
    ajoute un échantillon ; la détection d'anomalie (cf.
    apply_baseline_anomalies) n'a de sens qu'à partir de 3 échantillons."""
    baseline = load_baseline(path)
    for p in processes:
        entry = baseline.setdefault(p.name, {
            "n": 0, "cpu_mean": 0.0, "cpu_m2": 0.0, "mem_mean": 0.0, "mem_m2": 0.0,
        })
        entry["n"] += 1
        for prefix, value in (("cpu", p.cpu_percent), ("mem", p.memory_percent)):
            delta = value - entry[f"{prefix}_mean"]
            entry[f"{prefix}_mean"] += delta / entry["n"]
            entry[f"{prefix}_m2"] += delta * (value - entry[f"{prefix}_mean"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Baseline mise à jour (%d nom(s) de processus suivis) : %s", len(baseline), path)


def _baseline_std(entry: dict, prefix: str) -> float:
    n = entry.get("n", 0)
    if n < 2:
        return 0.0
    return (entry[f"{prefix}_m2"] / (n - 1)) ** 0.5


def baseline_anomaly_signals(p: ProcessInfo, baseline: dict) -> list[str]:
    """Signaux d'anomalie statistique (z-score > 2) par rapport à la
    baseline, par nom de processus. Volontairement conservateur : jamais
    déclenché sous 3 échantillons ni pour un écart-type quasi nul avec une
    valeur absolue faible (un processus stable à 0.1%% qui passe à 0.4%%
    n'est pas une anomalie intéressante)."""
    entry = baseline.get(p.name)
    if not entry or entry.get("n", 0) < 3:
        return []
    signals = []
    for prefix, value, label in (("cpu", p.cpu_percent, "CPU"), ("mem", p.memory_percent, "RAM")):
        std = _baseline_std(entry, prefix)
        mean = entry[f"{prefix}_mean"]
        if std > 0.05 and value > mean + 2 * std and value >= 5.0:
            signals.append(
                f"{label} anormalement élevé vs baseline ({value:.1f}% contre {mean:.1f}% ± {std:.1f}% habituellement)"
            )
    return signals


# ---------------------------------------------------------------------------
# 1bis. Moteur de risque par règles (H17) — déterministe, indépendant
# d'Ollama. Chaque règle déclenchée est tracée nommément (jamais un score
# opaque) ; le niveau produit ici ("niveau_regles") sert de plancher : un
# avis IA plus sévère peut faire monter le niveau final, jamais le faire
# descendre (cf. finalize_risk ci-dessous).
# ---------------------------------------------------------------------------

_STANDARD_EXE_PREFIXES = (
    "/usr/", "/bin/", "/sbin/", "/opt/", "/System/", "/Applications/",
    "/Library/", "/snap/", "/nix/", "c:\\windows", "c:\\program files",
)
_TEMP_EXE_PREFIXES = ("/tmp/", "/var/tmp/", "/dev/shm/", "/private/tmp/")
_RISK_LEVELS = ("faible", "moyen", "eleve")


def _risk_severity(level: Optional[str]) -> int:
    """"inconnu" (ou toute valeur non reconnue) ne fait ni monter ni
    descendre un niveau combiné : traité comme la sévérité la plus basse,
    jamais comme un niveau à part entière qui masquerait un vrai signal."""
    try:
        return _RISK_LEVELS.index(level)
    except ValueError:
        return -1


def _bump(level: str, new_level: str, signal: str, signals: list) -> str:
    """Ne fait JAMAIS redescendre `level` : ne peut que l'élever si
    `new_level` est plus sévère (cf. H17 — sous-estimer un risque est jugé
    pire que le sur-estimer)."""
    signals.append(signal)
    return new_level if _risk_severity(new_level) > _risk_severity(level) else level


def compute_rule_based_risk(p: ProcessInfo, baseline: Optional[dict] = None) -> dict:
    """Calcule un niveau de risque déterministe à partir de signaux
    observables sur le processus (H17), sans dépendre d'Ollama.

    Retourne {"niveau": "faible"|"moyen"|"eleve", "signaux": [...]}. Un
    processus sans aucun signal reste "faible" avec un signal explicite
    "aucun signal détecté par les règles" plutôt qu'un vide ambigu.

    Tient compte, si présents, de la configuration whitelist/blacklist
    (H23), du statut d'intégrité du binaire (H22) et de la baseline de
    performance (H24).
    """
    level = "faible"
    signals: list[str] = []

    # Blacklist utilisateur : niveau élevé immédiat, mais on continue à
    # évaluer les autres règles (leurs signaux restent informatifs).
    blacklist_hit = _matches_patterns(p, USER_CONFIG["blacklist"])
    if blacklist_hit:
        level = _bump(level, "eleve", f"correspond au motif blacklist '{blacklist_hit}' de la configuration", signals)

    # Whitelist utilisateur : neutralise UNIQUEMENT les signaux de chemin
    # (répertoire temporaire / hors standards) — un outil légitime compilé
    # dans /tmp reste whitelistable sans masquer ses signaux réseau.
    whitelist_hit = None if blacklist_hit else _matches_patterns(p, USER_CONFIG["whitelist"])
    if whitelist_hit:
        signals.append(f"whitelisté par la configuration (motif '{whitelist_hit}') : signaux de chemin ignorés")

    exe = (p.exe or "").strip()
    exe_lower = exe.lower()

    # NB : un exe VIDE (pas "(deleted)", juste absent) est le comportement
    # NORMAL de psutil pour les threads noyau (pas de binaire sur disque) —
    # ne JAMAIS le traiter comme un signal, sous peine de marquer "eleve"
    # des dizaines de threads noyau parfaitement légitimes sur toute
    # machine Linux (bruit massif, contraire à l'objectif de ce moteur).
    if exe:
        if "(deleted)" in exe_lower:
            # Signal fort et spécifique à psutil/Linux : le binaire a été
            # supprimé du disque après le lancement du processus — cas
            # classique d'auto-effacement malveillant (mais aussi, plus
            # bénin, d'une mise à jour de paquet sans redémarrage).
            level = _bump(level, "eleve", f"exécutable supprimé du disque après le lancement du processus ({exe})", signals)
        elif exe_lower.startswith(_TEMP_EXE_PREFIXES):
            if not whitelist_hit:
                level = _bump(level, "eleve", f"exécutable lancé depuis un répertoire temporaire ({exe})", signals)
        elif not exe_lower.startswith(_STANDARD_EXE_PREFIXES) and not exe_lower.startswith(("/home/", "/users/")):
            if not whitelist_hit:
                level = _bump(level, "moyen", f"exécutable hors des répertoires système standards ({exe})", signals)

    if p.integrity_status == "modifie":
        level = _bump(level, "eleve", "empreinte SHA256 de l'exécutable DIFFÉRENTE de la référence connue (binaire modifié ?)", signals)

    if baseline:
        for anomaly in baseline_anomaly_signals(p, baseline):
            level = _bump(level, "moyen", anomaly, signals)

    if p.cmdline_vide and exe:
        # Ligne de commande vide ALORS QU'un exécutable réel est présent :
        # rare et inhabituel (les threads noyau, qui ont légitimement une
        # cmdline vide, n'ont justement pas d'exe — donc pas de faux
        # positif ici grâce au `and exe`).
        level = _bump(level, "moyen", "ligne de commande vide malgré un exécutable présent (rare, inhabituel)", signals)

    listening_all_interfaces = any(
        (c.get("laddr") or "").startswith(("0.0.0.0:", "[::]:", ":::")) and c.get("status") == "LISTEN"
        for c in p.connections
    )
    if listening_all_interfaces:
        level = _bump(level, "moyen", "processus en écoute sur toutes les interfaces réseau (0.0.0.0)", signals)

    external_raddrs = {
        c.get("raddr") for c in p.connections
        if c.get("raddr") and not c["raddr"].split(":")[0].startswith(("127.", "::1", "0.0.0.0"))
    }
    if len(external_raddrs) > 10:
        level = _bump(level, "moyen", f"volume inhabituel de connexions externes distinctes ({len(external_raddrs)})", signals)

    if not signals:
        signals.append("aucun signal détecté par les règles")

    return {"niveau": level, "signaux": signals}


def finalize_risk(p: ProcessInfo) -> None:
    """Combine le niveau par règles (déjà posé dans p.risk par
    compute_rule_based_risk) avec l'avis Ollama éventuel (p.enrichment),
    par escalade uniquement (H17). Doit être appelé APRÈS l'enrichissement
    (ou après avoir posé un enrichissement de repli), jamais avant."""
    rules = p.risk or {"niveau": "faible", "signaux": ["aucun signal détecté par les règles"]}
    niveau_ia = None
    justification_ia = ""
    if p.enrichment:
        candidate = p.enrichment.get("niveau_risque")
        if candidate in _RISK_LEVELS:
            niveau_ia = candidate
            justification_ia = p.enrichment.get("justification_risque", "")

    niveau_final = rules["niveau"]
    if niveau_ia is not None and _risk_severity(niveau_ia) > _risk_severity(niveau_final):
        niveau_final = niveau_ia

    p.risk = {
        "niveau_regles": rules["niveau"],
        "signaux_regles": rules["signaux"],
        "niveau_ia": niveau_ia,
        "justification_ia": justification_ia,
        "niveau_final": niveau_final,
        "divergence": niveau_ia is not None and niveau_ia != rules["niveau"],
    }


# ---------------------------------------------------------------------------
# 2. Construction du graphe (parent/enfant + fichiers partagés, H4)
# ---------------------------------------------------------------------------

def build_graph(processes: list[ProcessInfo], max_conn_total: int = 300) -> nx.DiGraph:
    graph = nx.DiGraph()
    pid_to_info = {p.pid: p for p in processes}

    for p in processes:
        graph.add_node(
            f"proc:{p.pid}",
            kind="process",
            pid=p.pid,
            label=p.name,
            cpu=p.cpu_percent,
            mem=p.memory_percent,
            username=p.username,
        )

    # Relations parent -> enfant
    for p in processes:
        if p.ppid in pid_to_info and p.ppid != p.pid:
            graph.add_edge(f"proc:{p.ppid}", f"proc:{p.pid}", kind="parent_of")

    # Fichiers partagés entre >= 2 processus (H4)
    file_to_pids: dict[str, list[int]] = {}
    for p in processes:
        for path in p.open_files:
            file_to_pids.setdefault(path, []).append(p.pid)

    shared_files = {path: pids for path, pids in file_to_pids.items() if len(pids) >= 2}
    logger.info("Fichiers partagés entre plusieurs processus : %d", len(shared_files))

    for path, pids in shared_files.items():
        file_node = f"file:{path}"
        graph.add_node(file_node, kind="file", label=Path(path).name or path, full_path=path)
        for pid in pids:
            graph.add_edge(f"proc:{pid}", file_node, kind="opens")

    # Connexions réseau, colorées par protocole (H7). Plusieurs processus
    # connectés au même point distant convergent vers le même nœud (utile
    # pour repérer une infra partagée : DNS, proxy, base de données...).
    # Priorité aux processus les plus actifs si on dépasse max_conn_total.
    conn_candidates = []
    for p in sorted(processes, key=lambda pr: pr.score, reverse=True):
        for c in p.connections:
            endpoint = c.get("raddr") or c.get("laddr")
            if not endpoint:
                continue
            conn_candidates.append((p.pid, c["protocol"], endpoint, c.get("status", ""), bool(c.get("raddr"))))

    kept = conn_candidates[:max_conn_total]
    dropped = len(conn_candidates) - len(kept)
    if dropped > 0:
        logger.info(
            "Connexions réseau : %d affichées, %d masquées (--max-conn-total=%d) pour garder le graphe lisible.",
            len(kept), dropped, max_conn_total,
        )
    elif kept:
        logger.info("Connexions réseau ajoutées au graphe : %d", len(kept))

    for pid, protocol, endpoint, status, is_remote in kept:
        conn_node = f"conn:{protocol}:{endpoint}"
        if conn_node not in graph:
            graph.add_node(
                conn_node, kind="connection", label=endpoint, protocol=protocol,
                status=status, is_remote=is_remote,
            )
        graph.add_edge(f"proc:{pid}", conn_node, kind=protocol)

    return graph


# ---------------------------------------------------------------------------
# 3. Enrichissement via Ollama local
# ---------------------------------------------------------------------------

ENRICHMENT_SCHEMA_PROMPT = """Tu es un analyste système pédagogue. Voici un processus en cours d'exécution :

Nom : {name}
PID : {pid}
Utilisateur : {username}
Exécutable : {exe}
Répertoire de travail : {cwd}
Ligne de commande : {cmdline}
CPU (%) : {cpu}
Mémoire (%) : {mem}
Nombre de fichiers ouverts : {n_files}
Nombre de connexions réseau : {n_conn}

Réponds UNIQUEMENT avec un objet JSON strict (aucun texte hors du JSON), au format exact :
{{"categorie": "<courte catégorie, ex: navigateur, service systeme, dev-tool, base de donnees, reseau, inconnu>",
  "role_probable": "<une phrase courte décrivant le rôle probable de CE processus précis>",
  "niveau_risque": "<faible|moyen|eleve|inconnu>",
  "justification_risque": "<une phrase courte>",
  "explication_pedagogique": "<2-3 phrases expliquant à un non-expert, de façon générale, ce que fait ce type de processus/programme dans un système d'exploitation>"}}
"""


def _default_enrichment(reason: str) -> dict:
    return {
        "categorie": "inconnu",
        "role_probable": "non enrichi",
        "niveau_risque": "inconnu",
        "justification_risque": reason,
        "explication_pedagogique": "",
    }


# Base de connaissance statique de repli pour le mode "Knowledge" : utilisée
# quand un processus n'a pas été enrichi par Ollama (hors --enrich-limit,
# Ollama indisponible, etc.). Recherche par sous-chaîne insensible à la
# casse sur le nom du processus — volontairement non exhaustive, se contente
# de couvrir les processus système les plus courants (macOS/Linux).
KNOWLEDGE_BASE: dict[str, str] = {
    "kernel_task": "Processus spécial du noyau macOS : ne consomme pas réellement le CPU/RAM affiché, "
                    "il sert de réservoir pour la gestion thermique et énergétique du système.",
    "launchd": "Le tout premier processus (PID 1) sur macOS : démarre et supervise tous les autres "
               "services et démons du système.",
    "systemd": "Le tout premier processus (PID 1) sur la plupart des distributions Linux modernes : "
               "démarre et supervise les services système.",
    "windowserver": "Service macOS responsable du rendu de toutes les fenêtres et de l'affichage à l'écran.",
    "finder": "L'explorateur de fichiers graphique de macOS.",
    "dock": "Gère la barre d'icônes (Dock) de macOS.",
    "mds": "Metadata Server : indexe les fichiers pour la recherche Spotlight sur macOS.",
    "mdworker": "Processus worker de Spotlight qui indexe le contenu des fichiers en arrière-plan.",
    "coreaudiod": "Démon audio central de macOS, gère le son système.",
    "cupsd": "Démon d'impression (CUPS), gère les files d'attente d'impression.",
    "sshd": "Serveur SSH : accepte des connexions distantes sécurisées vers cette machine.",
    "bash": "Interpréteur de commandes (shell) — exécute les commandes tapées dans un terminal.",
    "zsh": "Interpréteur de commandes (shell) — exécute les commandes tapées dans un terminal.",
    "python": "Interpréteur du langage Python — exécute un script ou une application Python.",
    "node": "Runtime JavaScript côté serveur — exécute une application ou un outil Node.js.",
    "docker": "Moteur de conteneurisation — fait tourner des applications isolées dans des conteneurs.",
    "nginx": "Serveur web / reverse proxy léger, sert des pages ou redistribue du trafic HTTP.",
    "chrome": "Processus du navigateur Google Chrome (ou l'un de ses onglets/extensions isolés).",
    "safari": "Processus du navigateur Safari (ou l'un de ses onglets isolés).",
    "code helper": "Processus auxiliaire de Visual Studio Code (extension, terminal intégré, ou rendu).",
    "ollama": "Serveur d'inférence de modèles de langage local — héberge et exécute des LLM sur cette machine.",
}


def lookup_knowledge_base(process_name: str) -> str:
    name = (process_name or "").lower()
    for key, explanation in KNOWLEDGE_BASE.items():
        if key in name:
            return explanation
    return "Aucune information locale pour ce processus. Sans enrichissement Ollama, son rôle exact n'est pas documenté ici."


def call_ollama(
    prompt: str,
    model: str,
    host: str,
    timeout: float = 120.0,
) -> dict:
    """Appelle l'API Ollama locale (/api/generate) et parse la réponse JSON attendue.

    En cas d'échec (Ollama non lancé, timeout, JSON invalide), retourne un
    enrichissement de repli plutôt que de lever une exception (H5/H6) : un
    outil d'analyse système ne doit pas planter parce qu'un LLM local est
    indisponible.
    """
    url = f"{host.rstrip('/')}/api/generate"
    # num_predict plafonne la longueur de la réponse générée (H11) : la
    # réponse attendue est un petit objet JSON de quelques phrases, pas
    # besoin d'autoriser un modèle à générer des centaines de tokens — ça
    # borne le pire cas de latence par appel.
    payload = {
        "model": model, "prompt": prompt, "stream": False, "format": "json",
        "options": {"num_predict": 220},
    }
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        raw_text = resp.json().get("response", "")
        parsed = json.loads(raw_text)
        # Validation minimale du schéma attendu
        for key in ("categorie", "role_probable", "niveau_risque"):
            parsed.setdefault(key, "inconnu")
        parsed.setdefault("explication_pedagogique", "")
        return parsed
    except requests.exceptions.ConnectionError:
        logger.warning("Ollama injoignable sur %s — enrichissement désactivé pour ce processus.", host)
        return _default_enrichment("ollama_indisponible")
    except requests.exceptions.Timeout:
        logger.warning("Timeout Ollama (>%ss) pour le modèle %s.", timeout, model)
        return _default_enrichment("timeout_ollama")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Réponse Ollama non conforme au JSON attendu : %s", exc)
        return _default_enrichment("reponse_json_invalide")
    except Exception as exc:  # défensif
        logger.warning("Erreur inattendue lors de l'appel Ollama : %s", exc)
        return _default_enrichment(f"erreur_inattendue:{exc}")


def check_ollama_available(model: str, host: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Vérifie UNE FOIS, avant de lancer la boucle d'enrichissement, qu'Ollama
    est joignable et que le modèle demandé existe réellement localement.

    Sans ce garde-fou, un modèle mal orthographié (ex: "llama3:lattest" au
    lieu de "llama3:latest") produit la même erreur 404 répétée sur CHAQUE
    processus enrichi — inutile et bruyant sur de grosses machines (des
    centaines de processus). On échoue vite, une seule fois, avec un
    message actionnable (liste des modèles réellement disponibles).
    """
    try:
        resp = requests.get(f"{host.rstrip('/')}/api/tags", timeout=timeout)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        return False, f"Ollama injoignable sur {host} (le serveur est-il lancé ? essayez : ollama serve)"
    except requests.exceptions.Timeout:
        return False, f"Ollama ne répond pas sur {host} (timeout de {timeout}s)"
    except Exception as exc:  # défensif
        return False, f"Erreur en interrogeant Ollama sur {host} : {exc}"

    try:
        available = [m.get("name", "") for m in resp.json().get("models", [])]
    except (ValueError, AttributeError):
        return False, "Réponse inattendue de Ollama sur /api/tags (format non reconnu)."

    # Comparaison tolérante : "llama3" doit matcher un modèle installé sous
    # "llama3:latest".
    model_base = model.split(":")[0]
    if any(name == model or name.split(":")[0] == model_base for name in available):
        return True, ""

    suggestion = (
        f" Modèles disponibles : {', '.join(available)}" if available
        else " Aucun modèle installé localement (essayez : ollama pull <modele>)."
    )
    return False, f"Le modèle '{model}' n'est pas disponible sur {host}.{suggestion}"


def _detect_ollama_models(host: str, timeout: float = 3.0) -> list[str]:
    """Liste les modèles Ollama installés via l'API HTTP (H10) plutôt que
    la commande `ollama list`, pour ne pas dépendre du binaire `ollama` sur
    le PATH (important pour un exécutable PyInstaller). Retourne une liste
    vide (jamais une exception) si Ollama n'est pas joignable."""
    try:
        resp = requests.get(f"{host.rstrip('/')}/api/tags", timeout=timeout)
        resp.raise_for_status()
        return [m.get("name", "") for m in resp.json().get("models", []) if m.get("name")]
    except Exception:
        return []


# Modèle proposé par défaut lors du téléchargement automatique déclenché
# par l'assistant novice quand aucun modèle Ollama n'est installé (H12),
# ADAPTÉ À LA MACHINE (H35, même politique que install.sh/install.ps1) :
# mini sur Android/Termux (RAM et stockage limités sur mobile), medium
# partout ailleurs (macOS / Windows / Linux).
DEFAULT_OLLAMA_MODEL = "llama3.2:1b" if IS_ANDROID else "llama3:latest"

# Défaut de --model, adapté de la même façon : sur Android, viser le mini
# téléchargé par install.sh plutôt qu'un modèle 3B/8B intenable sur mobile.
DEFAULT_MODEL_ARG = "llama3.2:1b" if IS_ANDROID else "llama3.2"


def _ollama_reachable(host: str, timeout: float = 2.0) -> bool:
    try:
        return requests.get(f"{host.rstrip('/')}/api/tags", timeout=timeout).ok
    except Exception:
        return False


def _wait_for_ollama(host: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _ollama_reachable(host, timeout=2.0):
            return True
        time.sleep(1.5)
    return False


def _start_ollama_server(host: str) -> None:
    """Démarre `ollama serve` en arrière-plan si le binaire est présent
    mais que le serveur ne répond pas encore juste après l'installation."""
    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        return
    try:
        kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen([ollama_bin, "serve"], **kwargs)
    except Exception as exc:  # défensif : un échec de démarrage auto n'est pas fatal
        logger.debug("Impossible de démarrer 'ollama serve' automatiquement : %s", exc)


def _install_ollama_macos() -> bool:
    if shutil.which("brew"):
        print("Installation d'Ollama via Homebrew (peut prendre quelques minutes)...")
        try:
            subprocess.check_call(["brew", "install", "ollama"])
            return True
        except subprocess.CalledProcessError as exc:
            print(f"Échec de l'installation via Homebrew : {exc}")
    print("Homebrew indisponible (ou installation échouée) — ouverture de la page de téléchargement officielle...")
    webbrowser.open("https://ollama.com/download/mac")
    _prompt("Installe Ollama depuis la fenêtre ouverte, puis appuie sur Entrée pour continuer", "")
    return shutil.which("ollama") is not None or _ollama_reachable("http://localhost:11434")


def _install_ollama_linux() -> bool:
    print("Installation d'Ollama via le script officiel (peut demander ton mot de passe sudo)...")
    try:
        subprocess.check_call("curl -fsSL https://ollama.com/install.sh | sh", shell=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Échec de l'installation automatique : {exc}")
        print("Installe manuellement : curl -fsSL https://ollama.com/install.sh | sh")
        return False


def _install_ollama_android() -> bool:
    """Installation d'Ollama sous Termux via le paquet officiel des dépôts
    Termux (H35) — le script ollama.com ne fonctionne pas sur Android.
    Dégrade proprement (False) si `pkg` est absent ou si le paquet n'existe
    pas dans cette version de Termux."""
    if shutil.which("pkg") is None:
        print("Commande 'pkg' introuvable (es-tu bien sous Termux ?) — installation impossible.")
        print("Essaie manuellement : pkg install ollama")
        return False
    print("Installation d'Ollama via pkg (Termux)...")
    try:
        subprocess.check_call(["pkg", "install", "-y", "ollama"])
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Échec de l'installation via pkg : {exc}")
        print("Le paquet ollama n'est peut-être pas disponible dans cette version de Termux "
              "(pkg update && pkg install ollama pour réessayer) — l'analyse continuera sans IA.")
        return False


def _install_ollama_windows() -> bool:
    import tempfile
    installer_url = "https://ollama.com/download/OllamaSetup.exe"
    print("Téléchargement de l'installeur Ollama pour Windows...")
    try:
        installer_path = Path(tempfile.gettempdir()) / "OllamaSetup.exe"
        with requests.get(installer_url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(installer_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        print("Lancement de l'installeur (suis les instructions à l'écran)...")
        subprocess.run([str(installer_path)], check=False)
        return shutil.which("ollama") is not None or _ollama_reachable("http://localhost:11434")
    except Exception as exc:
        print(f"Échec du téléchargement/lancement de l'installeur : {exc}")
        print(f"Télécharge-le manuellement : {installer_url}")
        return False


def ensure_ollama_ready(host: str) -> bool:
    """Si Ollama ne répond pas sur `host`, propose (avec l'accord explicite
    de l'utilisateur — jamais silencieusement) une installation automatique
    adaptée à l'OS détecté (H12). Retourne True si Ollama finit par
    répondre, False sinon (l'appelant doit alors désactiver l'IA)."""
    if _ollama_reachable(host):
        return True

    print()
    print("Ollama (le moteur d'IA local) n'est pas détecté sur cette machine.")
    answer = _prompt(
        "L'installer automatiquement maintenant ? (o/n — sinon l'analyse continue sans IA)",
        "o",
    )
    if answer.strip().lower() not in ("o", "oui", "y", "yes"):
        return False

    system = platform.system()
    # Android/Termux AVANT le test "Linux" : platform.system() y renvoie
    # "Linux", mais le script officiel ollama.com ne fonctionne pas sous
    # Termux — c'est le paquet Termux qu'il faut (pkg install ollama).
    if IS_ANDROID:
        installed = _install_ollama_android()
    elif system == "Darwin":
        installed = _install_ollama_macos()
    elif system == "Linux":
        installed = _install_ollama_linux()
    elif system == "Windows":
        installed = _install_ollama_windows()
    else:
        print(f"Installation automatique non prise en charge sur cette plateforme ({system}).")
        print("Installe manuellement depuis https://ollama.com/download")
        return False

    if not installed:
        return False

    if not _ollama_reachable(host):
        _start_ollama_server(host)
        print("Démarrage du serveur Ollama...")
    if not _wait_for_ollama(host, timeout=30.0):
        print("Ollama a été installé mais ne répond pas encore. Relance l'assistant dans quelques instants.")
        return False
    print("Ollama est prêt.")
    return True


def pull_ollama_model(model: str, host: str, timeout: float = 1800.0) -> bool:
    """Télécharge un modèle Ollama via l'API HTTP (POST /api/pull, flux
    streamé) avec affichage de la progression. Timeout généreux par défaut
    (30 min) : un modèle comme llama3:latest fait plusieurs Go et le temps
    de téléchargement dépend entièrement de la connexion de l'utilisateur."""
    url = f"{host.rstrip('/')}/api/pull"
    print(f"Téléchargement du modèle '{model}' (peut prendre plusieurs minutes selon ta connexion)...")
    try:
        with requests.post(url, json={"name": model, "stream": True}, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            last_line = ""
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if data.get("error"):
                    print(f"\nErreur lors du téléchargement : {data['error']}")
                    return False
                status = data.get("status", "")
                if data.get("total") and data.get("completed") is not None:
                    pct = data["completed"] / data["total"] * 100
                    line = f"  {status} — {pct:5.1f}%"
                else:
                    line = f"  {status}"
                if line != last_line:
                    print(f"\r{line}" + " " * 10, end="", flush=True)
                    last_line = line
            print()
        print(f"Modèle '{model}' téléchargé avec succès.")
        return True
    except requests.exceptions.RequestException as exc:
        print(f"\nÉchec du téléchargement du modèle '{model}' : {exc}")
        return False


def _warm_up_ollama(model: str, host: str, timeout: float = 180.0) -> None:
    """Envoie un appel minuscule et jetable AVANT la boucle d'enrichissement,
    pour forcer le chargement du modèle en mémoire une seule fois (H11).

    Sans ça, plusieurs workers du ThreadPoolExecutor sollicitent Ollama en
    même temps pendant qu'il charge encore un modèle de plusieurs Go en
    mémoire (peut prendre de quelques secondes à plus d'une minute) ; comme
    Ollama sert les requêtes de génération de façon largement séquentielle
    en local, ces workers restent en file d'attente et expirent avant même
    d'avoir commencé à générer quoi que ce soit — c'est ce qui produisait
    des timeouts de 30s en rafale sur toute la première vague de requêtes.
    Un échec ici n'est pas fatal : loggé en warning, l'enrichissement réel
    est tenté quand même (le premier appel absorbera alors le chargement).
    """
    logger.info(
        "Chargement du modèle '%s' en mémoire (peut prendre jusqu'à une minute ou plus au premier appel)...",
        model,
    )
    try:
        requests.post(
            f"{host.rstrip('/')}/api/generate",
            json={"model": model, "prompt": "Réponds uniquement OK.", "stream": False, "options": {"num_predict": 5}},
            timeout=timeout,
        )
        logger.info("Modèle chargé — démarrage de l'enrichissement.")
    except Exception as exc:  # défensif : le préchauffage est un confort, pas un pré-requis
        logger.warning("Préchauffage du modèle échoué ou trop long (%s) — l'enrichissement démarre quand même.", exc)


# Raisons de repli qui signifient "l'enrichissement de CE processus a
# échoué de façon possiblement transitoire" — candidates au retry (H25) et
# jamais mises en cache (H26).
_TRANSIENT_ENRICH_REASONS = ("ollama_indisponible", "timeout_ollama", "reponse_json_invalide")


def _enrichment_failed_transiently(enrichment: Optional[dict]) -> bool:
    reason = (enrichment or {}).get("justification_risque", "")
    return reason in _TRANSIENT_ENRICH_REASONS or reason.startswith("erreur_inattendue")


class EnrichmentCache:
    """Cache persistant SQLite des résultats d'enrichissement Ollama (H26).

    Clé = SHA256(nom + exécutable + cmdline) : un même binaire lancé avec
    la même commande a le même rôle d'une exécution à l'autre — inutile de
    payer un appel LLM à chaque fois. TTL configurable (défaut 7 jours).
    Les enrichissements de repli (échec/timeout) ne sont JAMAIS mis en
    cache. Les résultats servis depuis le cache sont marqués
    `from_cache: true` pour rester distinguables dans le graphe."""

    def __init__(self, path: Path, ttl_days: float = 7.0):
        import threading
        self.path = path
        self.ttl_seconds = ttl_days * 86400
        path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + verrou : put() est appelé depuis les
        # threads du ThreadPoolExecutor d'enrichissement, pas seulement
        # depuis le thread principal.
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS enrich_cache (key TEXT PRIMARY KEY, result TEXT NOT NULL, ts REAL NOT NULL)"
            )
            self._conn.commit()
        self.hits = 0

    @staticmethod
    def key_for(p: ProcessInfo) -> str:
        raw = f"{p.name}\x00{p.exe or ''}\x00{p.cmdline or ''}"
        return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()

    def get(self, p: ProcessInfo) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT result, ts FROM enrich_cache WHERE key = ?", (self.key_for(p),)
            ).fetchone()
        if not row:
            return None
        result_json, ts = row
        if time.time() - ts > self.ttl_seconds:
            return None
        try:
            result = json.loads(result_json)
        except json.JSONDecodeError:
            return None
        result["from_cache"] = True
        self.hits += 1
        return result

    def put(self, p: ProcessInfo, enrichment: dict) -> None:
        if _enrichment_failed_transiently(enrichment):
            return
        stored = {k: v for k, v in enrichment.items() if k != "from_cache"}
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO enrich_cache (key, result, ts) VALUES (?, ?, ?)",
                (self.key_for(p), json.dumps(stored, ensure_ascii=False), time.time()),
            )

    def close(self) -> None:
        with contextlib.suppress(Exception), self._lock:
            self._conn.commit()
            self._conn.close()


def apply_plugin(processes: list[ProcessInfo], plugin_path: Path) -> None:
    """Charge un plugin Python utilisateur (H27) exposant une fonction
    `enrich(process_info: dict) -> dict` et fusionne son résultat dans
    p.enrichment["plugin"]. Toute erreur du plugin est loguée, jamais
    fatale — le plugin est du code UTILISATEUR fourni explicitement via
    --plugin, exécuté avec les mêmes droits que le script lui-même."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("analyseur_plugin_utilisateur", plugin_path)
    if spec is None or spec.loader is None:
        logger.error("Plugin illisible : %s", plugin_path)
        return
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        logger.error("Échec du chargement du plugin %s : %s", plugin_path, exc)
        return
    enrich_fn = getattr(module, "enrich", None)
    if not callable(enrich_fn):
        logger.error("Le plugin %s n'expose pas de fonction enrich(process_info) -> dict.", plugin_path)
        return

    n_ok = n_err = 0
    for p in processes:
        info = {
            "pid": p.pid, "ppid": p.ppid, "name": p.name, "username": p.username,
            "exe": p.exe, "cwd": p.cwd, "cmdline": p.cmdline,
            "cpu_percent": p.cpu_percent, "memory_percent": p.memory_percent,
            "connections": p.connections, "container": p.container,
        }
        try:
            result = enrich_fn(info)
            if isinstance(result, dict) and result:
                if p.enrichment is None:
                    p.enrichment = _default_enrichment("plugin_uniquement")
                p.enrichment["plugin"] = result
                n_ok += 1
        except Exception as exc:
            n_err += 1
            logger.debug("Plugin en erreur sur pid=%s : %s", p.pid, exc)
    logger.info("Plugin %s appliqué : %d processus enrichis, %d erreurs.", plugin_path.name, n_ok, n_err)


def enrich_processes(
    processes: list[ProcessInfo],
    model: str,
    host: str,
    enrich_limit: Optional[int],
    max_workers: int = 2,
    timeout: float = 120.0,
    cache: Optional[EnrichmentCache] = None,
    retry_failed: int = 0,
) -> None:
    """Enrichit en place les ProcessInfo les plus significatifs (H3).

    Les appels sont parallélisés (ThreadPoolExecutor) car ce sont des
    requêtes HTTP bloquantes ; max_workers reste modeste par défaut (H11) —
    un LLM local sert le plus souvent les requêtes de façon séquentielle
    (un seul GPU/CPU), donc une forte parallélisation ne fait qu'empiler
    des requêtes en file d'attente sans rien accélérer, et les fait toutes
    expirer ensemble.
    """
    ranked = sorted(processes, key=lambda p: p.score, reverse=True)
    targets = ranked if enrich_limit is None else ranked[:enrich_limit]

    if not targets:
        logger.info("Aucun processus à enrichir.")
        return

    # Cache persistant (H26) : sert d'abord les résultats déjà connus, ne
    # garde comme cibles Ollama que les processus jamais vus / expirés.
    if cache is not None:
        remaining = []
        for p in targets:
            cached = cache.get(p)
            if cached is not None:
                p.enrichment = cached
            else:
                remaining.append(p)
        if cache.hits:
            logger.info("Cache d'enrichissement : %d résultat(s) servi(s) depuis %s.", cache.hits, cache.path)
        targets = remaining
        if not targets:
            logger.info("Tous les processus ciblés étaient en cache — aucun appel Ollama nécessaire.")
            for p in processes:
                if p.enrichment is None:
                    p.enrichment = _default_enrichment("hors_limite_enrichissement")
            return

    ok, message = check_ollama_available(model, host)
    if not ok:
        logger.error("Enrichissement Ollama annulé avant de démarrer : %s", message)
        for p in processes:
            p.enrichment = _default_enrichment("preflight_echec")
        return

    _warm_up_ollama(model, host)

    logger.info(
        "Enrichissement Ollama de %d/%d processus (modèle=%s, host=%s, timeout=%ss, workers=%d)...",
        len(targets), len(processes), model, host, timeout, max_workers,
    )

    def _enrich_one(p: ProcessInfo) -> None:
        prompt = ENRICHMENT_SCHEMA_PROMPT.format(
            name=p.name,
            pid=p.pid,
            username=p.username or "inconnu",
            exe=p.exe or "inconnu",
            cwd=p.cwd or "inconnu",
            cmdline=p.cmdline[:400],
            cpu=p.cpu_percent,
            mem=p.memory_percent,
            n_files=len(p.open_files),
            n_conn=len(p.connections),
        )
        p.enrichment = call_ollama(prompt, model=model, host=host, timeout=timeout)
        if cache is not None and p.enrichment:
            cache.put(p, p.enrichment)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(_enrich_one, targets))

    # Retry des échecs transitoires (H25) : backoff exponentiel 1s, 2s,
    # 4s... entre les passes, en SÉRIE (un échec transitoire signifie
    # souvent qu'Ollama est saturé — re-paralléliser aggraverait le cas).
    for attempt in range(1, max(0, retry_failed) + 1):
        failed = [p for p in targets if _enrichment_failed_transiently(p.enrichment)]
        if not failed:
            break
        backoff = 2 ** (attempt - 1)
        logger.info(
            "Retry %d/%d : %d enrichissement(s) en échec transitoire, nouvelle tentative dans %ds...",
            attempt, retry_failed, len(failed), backoff,
        )
        time.sleep(backoff)
        for p in failed:
            _enrich_one(p)
        recovered = sum(1 for p in failed if not _enrichment_failed_transiently(p.enrichment))
        logger.info("Retry %d/%d terminé : %d/%d récupéré(s).", attempt, retry_failed, recovered, len(failed))

    # Les processus non ciblés reçoivent un enrichissement neutre explicite,
    # pour que le rendu PNG distingue "non analysé" de "analysé sans risque".
    for p in processes:
        if p.enrichment is None:
            p.enrichment = _default_enrichment("hors_limite_enrichissement")


# ---------------------------------------------------------------------------
# 4. Rendu PNG
# ---------------------------------------------------------------------------

RISK_COLORS = {
    "faible": "#4CAF50",
    "moyen": "#FFC107",
    "eleve": "#F44336",
    "inconnu": "#9E9E9E",
}

# Couleurs des arêtes/connexions par "kind" — protocole réseau pour les
# connexions, type de relation pour parent/enfant et fichiers partagés.
# Validées avec le validateur de palette du skill dataviz (mode sombre,
# surface proche de #05070d) : le couple gris initial (#78909C/#607D8B)
# échouait le seuil de distinction "vision normale" (ΔE 6.7, sous le
# plancher de 15) — remplacé par un couple bleu-ardoise / brun-taupe qui
# passe (ΔE 16.3) tout en restant volontairement discret (ce sont des
# liens "structurels" secondaires, pas le canal catégoriel principal).
PROTOCOL_COLORS = {
    "tcp": "#42A5F5",
    "udp": "#FFA726",
    "unix": "#AB47BC",
    "parent_of": "#5A6E82",
    "opens": "#A68A5B",
}
CONNECTION_NODE_COLOR = "#37474F"

# Palette catégorielle pour le mode "Type" (coloration par catégorie de
# processus détectée par Ollama). Ordre fixe validé par le skill dataviz
# (paires adjacentes, mode sombre) : CVD ΔE >= 8.4, vision normale >= 19.3,
# contraste >= 3:1 sur toutes les paires. "inconnu" reste volontairement
# hors palette catégorielle (gris neutre) plutôt que d'inventer une teinte
# supplémentaire pour un "Autre" — cf. règle du skill dataviz.
CATEGORY_COLORS = {
    "navigateur": "#3987E5",
    "service systeme": "#D95926",
    "dev-tool": "#199E70",
    "base de donnees": "#C98500",
    "reseau": "#D55181",
}
CATEGORY_COLOR_UNKNOWN = "#9AA1B2"


def category_color(categorie: Optional[str]) -> str:
    return CATEGORY_COLORS.get((categorie or "").strip().lower(), CATEGORY_COLOR_UNKNOWN)


def render_graph_png(
    graph: nx.DiGraph,
    processes: list[ProcessInfo],
    output_path: Path,
    title: str = "Graphe des processus, fichiers liés, connexions réseau et enrichissement Ollama",
) -> None:
    if graph.number_of_nodes() == 0:
        logger.warning("Graphe vide — aucun PNG généré.")
        return

    pid_to_info = {p.pid: p for p in processes}

    node_colors = []
    node_sizes = []
    labels = {}

    for node, data in graph.nodes(data=True):
        kind = data.get("kind")
        if kind == "process":
            info = pid_to_info.get(data["pid"])
            risk = "inconnu"
            categorie = ""
            if info and info.risk:
                # niveau_final (H17) = règles déterministes combinées par
                # escalade avec l'avis Ollama, PLUS fiable que le seul avis IA.
                risk = info.risk.get("niveau_final", "inconnu")
            if info and info.enrichment:
                categorie = info.enrichment.get("categorie", "")
            node_colors.append(RISK_COLORS.get(risk, RISK_COLORS["inconnu"]))
            node_sizes.append(300 + (data.get("cpu", 0) + data.get("mem", 0)) * 40)
            suffix = f"\n[{categorie}]" if categorie and categorie != "inconnu" else ""
            labels[node] = f"{data['label']}\n(pid {data['pid']}){suffix}"
        elif kind == "connection":
            node_colors.append(PROTOCOL_COLORS.get(data.get("protocol"), CONNECTION_NODE_COLOR))
            node_sizes.append(90)
            labels[node] = data.get("label", node)
        else:  # fichier partagé
            node_colors.append("#607D8B")
            node_sizes.append(150)
            labels[node] = data.get("label", node)

    plt.figure(figsize=(20, 14))
    layout = nx.spring_layout(graph, k=0.6, seed=42, iterations=50)

    edge_colors = [PROTOCOL_COLORS.get(kind, "#999999") for _, _, kind in graph.edges(data="kind")]

    nx.draw_networkx_nodes(graph, layout, node_color=node_colors, node_size=node_sizes, alpha=0.9)
    nx.draw_networkx_edges(graph, layout, edge_color=edge_colors, alpha=0.5, arrows=True, arrowsize=8, width=1.1)
    nx.draw_networkx_labels(graph, layout, labels=labels, font_size=6)

    legend_handles = [
        plt.Line2D([0], [0], marker="o", color="w", label=f"Risque {risk}",
                    markerfacecolor=color, markersize=10)
        for risk, color in RISK_COLORS.items()
    ]
    legend_handles.append(
        plt.Line2D([0], [0], marker="o", color="w", label="Fichier partagé",
                    markerfacecolor="#607D8B", markersize=8)
    )
    legend_handles.append(
        plt.Line2D([0], [0], marker="o", color="w", label="Connexion réseau",
                    markerfacecolor=CONNECTION_NODE_COLOR, markersize=8)
    )
    legend_handles += [
        plt.Line2D([0], [0], color=PROTOCOL_COLORS["parent_of"], lw=2, label="Lien parent → enfant"),
        plt.Line2D([0], [0], color=PROTOCOL_COLORS["opens"], lw=2, label="Ouvre un fichier partagé"),
        plt.Line2D([0], [0], color=PROTOCOL_COLORS["tcp"], lw=2, label="Connexion TCP"),
        plt.Line2D([0], [0], color=PROTOCOL_COLORS["udp"], lw=2, label="Connexion UDP"),
        plt.Line2D([0], [0], color=PROTOCOL_COLORS["unix"], lw=2, label="Socket UNIX"),
    ]
    plt.legend(handles=legend_handles, loc="upper right", fontsize=8)
    plt.title(title, fontsize=14)
    plt.axis("off")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150)
    plt.close()
    logger.info("Graphe PNG écrit : %s", output_path)


# ---------------------------------------------------------------------------
# 5. Rendu interactif 3D (HTML autonome, nœuds cliquables type "système solaire")
# ---------------------------------------------------------------------------
#
# Bibliothèque : 3d-force-graph (three.js embarqué), chargée depuis un CDN
# (unpkg) — cf. règle "External scripts can be imported from a CDN" ; le
# fichier reste un unique .html autonome (CSS/JS applicatifs inline), mais
# nécessite une connexion réseau pour charger la lib au premier affichage.

def build_graph_payload(graph: nx.DiGraph, processes: list[ProcessInfo]) -> dict:
    """Convertit le graphe networkx en structure {nodes, links} consommable
    directement par 3d-force-graph (un objet JS par nœud/arête)."""
    pid_to_info = {p.pid: p for p in processes}
    nodes = []

    for node, data in graph.nodes(data=True):
        kind = data.get("kind")
        if kind == "process":
            info = pid_to_info.get(data["pid"])
            risk_info = (info.risk if info else None) or {}
            risk = risk_info.get("niveau_final", "inconnu")
            categorie = "inconnu"
            role = "non enrichi"
            justification = ""
            explication = ""
            if info and info.enrichment:
                categorie = info.enrichment.get("categorie", "inconnu")
                role = info.enrichment.get("role_probable", "non enrichi")
                justification = info.enrichment.get("justification_risque", "")
                explication = info.enrichment.get("explication_pedagogique", "")
            # Mode "Knowledge" : on préfère l'explication Ollama si le
            # processus a bien été enrichi (explication non vide), sinon on
            # retombe sur la base de connaissance statique locale.
            enriched = bool(explication)
            knowledge_text = explication if enriched else lookup_knowledge_base(data["label"])
            cpu = round(data.get("cpu", 0), 2)
            mem = round(data.get("mem", 0), 2)
            # Nœud "peu intéressant" (H18) : masqué par défaut côté HTML
            # pour réduire la densité visuelle, jamais si un risque réel
            # a été détecté (règles ou IA).
            low_interest = (
                graph.degree(node) <= 1
                and (cpu + mem) < 1.0
                and risk == "faible"
            )
            nodes.append({
                "id": node,
                "type": "process",
                "name": data["label"],
                "pid": data["pid"],
                "ppid": info.ppid if info else None,
                "username": data.get("username"),
                "cpu": cpu,
                "mem": mem,
                "cmdline": (info.cmdline if info else "")[:300],
                "exe": info.exe if info else None,
                "cwd": info.cwd if info else None,
                "n_open_files": len(info.open_files) if info else 0,
                "n_connections": len(info.connections) if info else 0,
                "connections": (info.connections if info else [])[:15],
                "categorie": categorie,
                "role_probable": role,
                "niveau_risque": risk,
                "niveau_risque_regles": risk_info.get("niveau_regles", "inconnu"),
                "signaux_regles": risk_info.get("signaux_regles", []),
                "niveau_risque_ia": risk_info.get("niveau_ia"),
                "risque_divergent": bool(risk_info.get("divergence", False)),
                "justification_risque": justification or risk_info.get("justification_ia", ""),
                "collecte_incomplete": (info.collecte_incomplete if info else []),
                "container": info.container if info else None,
                "exe_sha256": info.exe_sha256 if info else None,
                "integrity_status": info.integrity_status if info else None,
                "low_interest": low_interest,
                "enriched": enriched,
                "knowledge_text": knowledge_text,
                "val": round(max(1.5, (cpu + mem) * 1.2 + 2), 2),
                "color": RISK_COLORS.get(risk, RISK_COLORS["inconnu"]),
            })
        elif kind == "connection":
            protocol = data.get("protocol", "tcp")
            nodes.append({
                "id": node,
                "type": "connection",
                "name": data.get("label", node),
                "protocol": protocol,
                "status": data.get("status", ""),
                "is_remote": bool(data.get("is_remote", False)),
                "knowledge_text": {
                    "tcp": "Connexion TCP : canal fiable et ordonné (web, SSH, bases de données...).",
                    "udp": "Connexion UDP : échange rapide sans garantie de livraison (DNS, streaming, jeux...).",
                    "unix": "Socket UNIX : canal de communication local entre processus sur la même machine.",
                }.get(protocol, ""),
                "val": 1.4,
                "color": PROTOCOL_COLORS.get(protocol, CONNECTION_NODE_COLOR),
            })
        else:  # fichier partagé
            nodes.append({
                "id": node,
                "type": "file",
                "name": data.get("label", node),
                "full_path": data.get("full_path", ""),
                "val": 2,
                "color": "#607D8B",
            })

    links = [
        {"source": u, "target": v, "kind": edata.get("kind", "")}
        for u, v, edata in graph.edges(data=True)
    ]
    return {"nodes": nodes, "links": links}


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8" />
<title>__TITLE__</title>
<style>
  :root {
    --bg: #05070d;
    --panel-bg: rgba(15, 18, 28, 0.92);
    --border: #262b3a;
    --text: #e7e9ee;
    --muted: #9aa1b2;
    --accent: #6c9dff;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: var(--bg); color: var(--text);
               font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; overflow: hidden; }
  #graph { position: absolute; inset: 0; }

  #topbar {
    position: absolute; top: 0; left: 0; right: 0; z-index: 5;
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    padding: 12px 18px; background: linear-gradient(to bottom, rgba(5,7,13,0.95), rgba(5,7,13,0));
    pointer-events: none;
  }
  #topbar * { pointer-events: auto; }
  #title { font-size: 15px; font-weight: 600; letter-spacing: 0.2px; flex-shrink: 0; }
  #modeSelector { display: flex; gap: 6px; flex-shrink: 0; }
  .mode-btn {
    background: var(--panel-bg); border: 1px solid var(--border); color: var(--muted);
    font-size: 11px; padding: 6px 11px; border-radius: 6px; cursor: pointer;
    font-family: inherit; transition: all 0.15s ease;
  }
  .mode-btn:hover { color: var(--text); }
  .mode-btn.active { color: #fff; border-color: var(--accent); background: rgba(108,157,255,0.18); }
  #search {
    background: var(--panel-bg); border: 1px solid var(--border); color: var(--text);
    border-radius: 8px; padding: 7px 12px; font-size: 13px; width: 220px; outline: none;
  }
  #search::placeholder { color: var(--muted); }
  #stats { font-size: 12px; color: var(--muted); margin-left: auto; white-space: nowrap; }

  #legend {
    position: absolute; top: 60px; left: 18px; z-index: 5;
    background: var(--panel-bg); border: 1px solid var(--border); border-radius: 10px;
    padding: 12px 14px; font-size: 12px; min-width: 175px;
  }
  #legend h4 { margin: 10px 0 8px 0; font-size: 11px; text-transform: uppercase; color: var(--muted); letter-spacing: 0.6px; }
  #legend h4:first-child { margin-top: 0; }
  .legend-row { display: flex; align-items: center; gap: 8px; margin: 5px 0; cursor: pointer; user-select: none; }
  .legend-row.disabled { opacity: 0.35; }
  .dot { width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; box-shadow: 0 0 6px currentColor; }
  .line-swatch { width: 16px; height: 2px; flex-shrink: 0; box-shadow: 0 0 4px currentColor; }

  #cameraControls {
    position: absolute; right: 18px; bottom: 18px; z-index: 5;
    display: flex; flex-direction: column; gap: 6px;
  }
  #cameraControls button {
    width: 36px; height: 36px; border-radius: 50%; border: 1px solid var(--border);
    background: var(--panel-bg); color: var(--text); font-size: 16px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; font-family: inherit;
  }
  #cameraControls button:hover { border-color: var(--accent); color: var(--accent); }
  #cameraControls button#recenter { font-size: 14px; }

  #panel {
    position: absolute; top: 0; right: 0; bottom: 0; width: 340px; z-index: 6;
    background: var(--panel-bg); border-left: 1px solid var(--border);
    padding: 18px; overflow-y: auto; transform: translateX(100%);
    transition: transform 0.25s ease; font-size: 13px;
  }
  #panel.open { transform: translateX(0); }
  #panel h3 { margin: 0 0 4px 0; font-size: 16px; }
  #panel .sub { color: var(--muted); font-size: 12px; margin-bottom: 14px; }
  #panel .field { margin-bottom: 10px; }
  #panel .field label { display: block; font-size: 10px; text-transform: uppercase; color: var(--muted);
                         letter-spacing: 0.5px; margin-bottom: 2px; }
  #panel .field .val { word-break: break-word; line-height: 1.4; }
  #panel .risk-badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; }
  #closePanel { position: absolute; top: 14px; right: 14px; background: none; border: none;
                color: var(--muted); font-size: 18px; cursor: pointer; }
  .conn-list { display: flex; flex-direction: column; gap: 4px; margin-top: 4px; }
  .conn-row { font-size: 12px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .proto-tag { font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: 4px; letter-spacing: 0.4px; }
  .proto-tcp { background: #42A5F522; color: #42A5F5; }
  .proto-udp { background: #FFA72622; color: #FFA726; }
  .proto-unix { background: #AB47BC22; color: #AB47BC; }
  .conn-status { color: var(--muted); font-size: 11px; }
  .copy-btn {
    background: none; border: 1px solid var(--border); color: var(--muted);
    font-size: 10px; padding: 1px 7px; border-radius: 5px; cursor: pointer;
    font-family: inherit; margin-left: 6px; vertical-align: middle;
    transition: all 0.15s ease;
  }
  .copy-btn:hover { color: var(--accent); border-color: var(--accent); }
  .copy-btn.copied { color: #4CAF50; border-color: #4CAF50; }

  #hint {
    position: absolute; bottom: 14px; left: 18px; z-index: 5; font-size: 11px; color: var(--muted);
  }
</style>
</head>
<body>
  <div id="graph"></div>

  <div id="topbar">
    <div id="title">__TITLE__</div>
    <div id="modeSelector">
      <button class="mode-btn" data-mode="type">Type</button>
      <button class="mode-btn active" data-mode="securite">Sécurité</button>
      <button class="mode-btn" data-mode="debug">Debug</button>
      <button class="mode-btn" data-mode="info_verbose">Info verbose</button>
      <button class="mode-btn" data-mode="knowledge">Knowledge</button>
    </div>
    <input id="search" type="text" placeholder="Rechercher un élément..." />
    <div id="stats"></div>
  </div>

  <div id="legend">
    <h4>Type de processus</h4>
    <div class="legend-row" data-key="cat_navigateur"><span class="dot" style="background:#3987E5;color:#3987E5"></span>Navigateur</div>
    <div class="legend-row" data-key="cat_service_systeme"><span class="dot" style="background:#D95926;color:#D95926"></span>Service système</div>
    <div class="legend-row" data-key="cat_dev-tool"><span class="dot" style="background:#199E70;color:#199E70"></span>Dev-tool</div>
    <div class="legend-row" data-key="cat_base_de_donnees"><span class="dot" style="background:#C98500;color:#C98500"></span>Base de données</div>
    <div class="legend-row" data-key="cat_reseau"><span class="dot" style="background:#D55181;color:#D55181"></span>Réseau</div>
    <div class="legend-row" data-key="cat_inconnu"><span class="dot" style="background:#9AA1B2;color:#9AA1B2"></span>Inconnu / non catégorisé</div>
    <h4>Niveau de risque</h4>
    <div class="legend-row" data-key="faible"><span class="dot" style="background:#4CAF50;color:#4CAF50"></span>Faible</div>
    <div class="legend-row" data-key="moyen"><span class="dot" style="background:#FFC107;color:#FFC107"></span>Moyen</div>
    <div class="legend-row" data-key="eleve"><span class="dot" style="background:#F44336;color:#F44336"></span>Élevé</div>
    <div class="legend-row" data-key="inconnu"><span class="dot" style="background:#9E9E9E;color:#9E9E9E"></span>Inconnu</div>
    <h4>Connexions réseau</h4>
    <div class="legend-row" data-key="proto_tcp"><span class="line-swatch" style="background:#42A5F5;color:#42A5F5"></span>TCP</div>
    <div class="legend-row" data-key="proto_udp"><span class="line-swatch" style="background:#FFA726;color:#FFA726"></span>UDP</div>
    <div class="legend-row" data-key="proto_unix"><span class="line-swatch" style="background:#AB47BC;color:#AB47BC"></span>UNIX</div>
    <div class="legend-row" data-key="file"><span class="dot" style="background:#607D8B;color:#607D8B"></span>Fichier partagé</div>
    <h4>Affichage</h4>
    <div class="legend-row disabled" data-key="low_interest"><span class="dot" style="background:#546E7A;color:#546E7A"></span>Processus peu actifs (masqués)</div>
  </div>

  <div id="panel">
    <button id="closePanel">✕</button>
    <div id="panelBody"></div>
  </div>

  <div id="cameraControls">
    <button id="zoomIn" title="Zoom avant">+</button>
    <button id="zoomOut" title="Zoom arrière">–</button>
    <button id="recenter" title="Recentrer (R ou Ctrl+R)">⟲</button>
  </div>

  <div id="hint">Clic : sélectionner &nbsp;•&nbsp; glisser : orbiter &nbsp;•&nbsp; molette : zoomer &nbsp;•&nbsp; R : recentrer &nbsp;•&nbsp; Échap : fermer &nbsp;•&nbsp; / : rechercher &nbsp;•&nbsp; 1-5 : modes</div>

  <div id="loadError" style="display:none; position:absolute; inset:0; z-index:10; background:var(--bg);
       align-items:center; justify-content:center; text-align:center; padding:40px;">
    <div style="max-width:420px;">
      <div style="font-size:15px; font-weight:600; margin-bottom:8px;">Impossible de charger la bibliothèque 3D</div>
      <div style="font-size:13px; color:var(--muted); line-height:1.5;">
        Ce fichier a besoin d'une connexion internet pour charger la librairie
        <code>3d-force-graph</code> depuis unpkg.com au premier affichage.
        Vérifiez votre connexion puis rechargez la page.
      </div>
    </div>
  </div>

  <script src="https://unpkg.com/3d-force-graph" onerror="document.getElementById('loadError').style.display='flex'"></script>
  <script>
    if (typeof ForceGraph3D === 'undefined') {
      document.getElementById('loadError').style.display = 'flex';
      throw new Error('3d-force-graph non chargé (pas de connexion internet ?)');
    }
    const GRAPH_DATA = __GRAPH_DATA_JSON__;
    // low_interest masqué par défaut (H18) pour réduire la densité visuelle
    // initiale ; togglable depuis la légende (section "Affichage"), jamais
    // appliqué à un nœud dont le risque final n'est pas "faible".
    const hiddenKeys = new Set(['low_interest']);
    let currentMode = 'securite';
    let lastSelectedNode = null;

    const el = document.getElementById('graph');
    const panel = document.getElementById('panel');
    const panelBody = document.getElementById('panelBody');
    const statsEl = document.getElementById('stats');

    const LINK_COLORS = {
      parent_of: 'rgba(120,144,156,0.45)',
      opens: 'rgba(96,125,139,0.55)',
      tcp: 'rgba(66,165,245,0.7)',
      udp: 'rgba(255,167,38,0.7)',
      unix: 'rgba(171,71,188,0.7)',
    };

    function riskLabel(r) {
      return { faible: 'Faible', moyen: 'Moyen', eleve: 'Élevé', inconnu: 'Inconnu' }[r] || 'Inconnu';
    }
    function riskColor(r) {
      return { faible: '#4CAF50', moyen: '#FFC107', eleve: '#F44336', inconnu: '#9E9E9E' }[r] || '#9E9E9E';
    }

    // Palette catégorielle "Type de processus" — mêmes valeurs que
    // CATEGORY_COLORS côté Python, validées via le skill dataviz.
    const CATEGORY_COLORS = {
      'navigateur': '#3987E5',
      'service systeme': '#D95926',
      'dev-tool': '#199E70',
      'base de donnees': '#C98500',
      'reseau': '#D55181',
    };
    const CATEGORY_COLOR_UNKNOWN = '#9AA1B2';
    function categoryColor(cat) {
      return CATEGORY_COLORS[(cat || '').trim().toLowerCase()] || CATEGORY_COLOR_UNKNOWN;
    }
    function categorySlug(cat) {
      const key = (cat || '').trim().toLowerCase();
      return CATEGORY_COLORS[key] ? key.replace(/\s+/g, '_') : 'inconnu';
    }

    function escapeHtml(s) {
      return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    // Boutons "copier" du panneau (PID, exécutable, commande, commande
    // kill) : accélère le passage à l'investigation dans un terminal.
    // navigator.clipboard peut être indisponible sur file:// selon le
    // navigateur -> repli sur un <textarea> temporaire + execCommand.
    function copyText(text, btn) {
      const done = () => {
        btn.classList.add('copied');
        const old = btn.textContent;
        btn.textContent = 'copié ✓';
        setTimeout(() => { btn.classList.remove('copied'); btn.textContent = old; }, 1200);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
      } else {
        fallbackCopy(text, done);
      }
    }
    function fallbackCopy(text, done) {
      const ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (e) {}
      document.body.removeChild(ta);
    }
    // Les valeurs à copier sont stockées dans un registre indexé plutôt
    // qu'inlinées dans onclick : évite tout échappement fragile de quotes
    // dans du HTML injecté.
    const COPY_REGISTRY = [];
    function copyBtn(value, label) {
      if (value === null || value === undefined || value === '') return '';
      const idx = COPY_REGISTRY.push(String(value)) - 1;
      return `<button class="copy-btn" data-copy-idx="${idx}">${escapeHtml(label || 'copier')}</button>`;
    }
    panelBody.addEventListener('click', (e) => {
      const btn = e.target.closest('.copy-btn');
      if (btn) copyText(COPY_REGISTRY[Number(btn.dataset.copyIdx)] || '', btn);
    });

    // Dégradé vert -> rouge selon l'intensité CPU+RAM, utilisé en mode Debug.
    function heatColor(v) {
      const t = Math.max(0, Math.min(1, v / 60));
      const r = Math.round(76 + t * (244 - 76));
      const g = Math.round(175 - t * (175 - 67));
      const b = Math.round(80 - t * (80 - 54));
      return '#' + [r, g, b].map(x => x.toString(16).padStart(2, '0')).join('');
    }

    function modeNodeColor(n, mode) {
      if (mode === 'type' && n.type === 'process') return categoryColor(n.categorie);
      if (mode === 'debug' && n.type === 'process') return heatColor((n.cpu || 0) + (n.mem || 0));
      if (mode === 'knowledge' && n.type === 'process') return n.enriched ? '#FFD54F' : '#546E7A';
      return n.color;
    }

    function applyNodeColors() {
      const q = document.getElementById('search').value.trim().toLowerCase();
      if (!q) { Graph.nodeColor(n => modeNodeColor(n, currentMode)); return; }
      Graph.nodeColor(n => (n.name || '').toLowerCase().includes(q) ? '#ffffff' : (modeNodeColor(n, currentMode) + '33'));
    }

    // Un nœud peut être filtré depuis PLUSIEURS sections de la légende à la
    // fois (risque ET type, par exemple) — on renvoie donc l'ensemble de ses
    // clés, et un nœud disparaît si AU MOINS UNE est masquée.
    function nodeFilterKeys(node) {
      if (node.type === 'file') return ['file'];
      if (node.type === 'connection') return ['proto_' + node.protocol];
      const keys = [node.niveau_risque || 'inconnu', 'cat_' + categorySlug(node.categorie)];
      if (node.low_interest) keys.push('low_interest');
      return keys;
    }

    function currentGraphData() {
      const nodes = GRAPH_DATA.nodes.filter(n => nodeFilterKeys(n).every(k => !hiddenKeys.has(k)));
      const ids = new Set(nodes.map(n => n.id));
      const links = GRAPH_DATA.links.filter(l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source;
        const t = typeof l.target === 'object' ? l.target.id : l.target;
        return ids.has(s) && ids.has(t);
      });
      return { nodes, links };
    }

    function fmtConnections(conns) {
      if (!conns || !conns.length) return '<div class="val">Aucune</div>';
      return '<div class="conn-list">' + conns.map(c => `
        <div class="conn-row"><span class="proto-tag proto-${c.protocol}">${c.protocol.toUpperCase()}</span>
        ${escapeHtml(c.raddr || c.laddr || '?')}
        <span class="conn-status">${escapeHtml(c.status || '')}</span></div>
      `).join('') + '</div>';
    }

    function panelHeader(node) {
      if (node.type === 'file') return `<h3>${escapeHtml(node.name)}</h3><div class="sub">Fichier partagé</div>`;
      if (node.type === 'connection') {
        return `<h3>${escapeHtml(node.name)}</h3><div class="sub">${node.protocol.toUpperCase()}${node.status ? ' · ' + escapeHtml(node.status) : ''}${node.is_remote ? ' · distant' : ' · local'}</div>`;
      }
      return `<h3>${escapeHtml(node.name)}</h3><div class="sub">PID ${node.pid}${copyBtn(node.pid, 'copier PID')}${node.ppid ? ' · parent ' + node.ppid : ''}${node.username ? ' · ' + escapeHtml(node.username) : ''}${node.container ? ' · conteneur ' + escapeHtml(node.container) : ''}</div>`;
    }

    // Lignes communes "investigation" des panneaux processus : exécutable,
    // commande et prévisualisation kill, chacune avec son bouton copier.
    function investigationRows(node) {
      let rows = '';
      if (node.exe) rows += `<div class="field"><label>Exécutable ${copyBtn(node.exe, 'copier')}</label><div class="val">${escapeHtml(node.exe)}</div></div>`;
      if (node.cmdline) rows += `<div class="field"><label>Commande ${copyBtn(node.cmdline, 'copier')}</label><div class="val">${escapeHtml(node.cmdline)}</div></div>`;
      if (node.pid) rows += `<div class="field"><label>Arrêter ce processus ${copyBtn('kill ' + node.pid, 'copier')}</label><div class="val" style="color:var(--muted)">kill ${node.pid} <span style="font-size:10px">(à coller dans un terminal — vérifier avant d'exécuter)</span></div></div>`;
      if (node.integrity_status) {
        const bad = node.integrity_status === 'modifie';
        rows += `<div class="field"><label>Intégrité du binaire</label><div class="val" style="color:${bad ? '#F44336' : 'inherit'}">${escapeHtml(node.integrity_status)}${node.exe_sha256 ? ' — SHA256 ' + escapeHtml(node.exe_sha256.slice(0, 16)) + '…' + copyBtn(node.exe_sha256, 'copier') : ''}</div></div>`;
      }
      return rows;
    }

    function fmtIncompleteWarning(node) {
      const issues = node.collecte_incomplete || [];
      if (!issues.length) return '';
      return `<div class="field"><label>Collecte incomplète</label><div class="val" style="color:#FFC107">${issues.map(escapeHtml).join(', ')}</div></div>`;
    }

    function renderSecurityPanel(node) {
      if (node.type === 'file') return panelHeader(node) + `<div class="field"><label>Chemin</label><div class="val">${escapeHtml(node.full_path || node.name)}</div></div>`;
      if (node.type === 'connection') {
        return panelHeader(node) + `<div class="field"><label>Nature</label><div class="val">${node.is_remote ? 'Connexion vers un hôte distant' : 'Écoute / connexion locale'}</div></div>`;
      }
      const risk = node.niveau_risque || 'inconnu';
      const riskRegles = node.niveau_risque_regles || 'inconnu';
      const riskIa = node.niveau_risque_ia;
      const conns = node.connections || [];
      const externalConns = conns.filter(c => (c.raddr || '') && !c.raddr.startsWith('127.') && !c.raddr.startsWith('::1') && !c.raddr.startsWith('0.0.0.0'));
      const signaux = node.signaux_regles || [];
      return panelHeader(node) + `
        <div class="field"><label>Niveau de risque final</label>
          <span class="risk-badge" style="background:${riskColor(risk)}22; color:${riskColor(risk)}; border:1px solid ${riskColor(risk)}">${riskLabel(risk)}</span>
          ${node.risque_divergent ? '<span class="risk-badge" style="background:#6C9DFF22; color:#6C9DFF; border:1px solid #6C9DFF; margin-left:6px">avis divergents</span>' : ''}
        </div>
        <div class="field"><label>Règles déterministes (sans IA)</label>
          <span class="risk-badge" style="background:${riskColor(riskRegles)}22; color:${riskColor(riskRegles)}; border:1px solid ${riskColor(riskRegles)}">${riskLabel(riskRegles)}</span>
          <div class="val" style="margin-top:4px">${signaux.map(escapeHtml).join('<br/>')}</div>
        </div>
        ${riskIa ? `<div class="field"><label>Avis Ollama (IA)</label>
          <span class="risk-badge" style="background:${riskColor(riskIa)}22; color:${riskColor(riskIa)}; border:1px solid ${riskColor(riskIa)}">${riskLabel(riskIa)}</span>
        </div>` : ''}
        <div class="field"><label>Justification</label><div class="val">${escapeHtml(node.justification_risque || '—')}</div></div>
        <div class="field"><label>Catégorie</label><div class="val">${escapeHtml(node.categorie || 'inconnu')}</div></div>
        <div class="field"><label>Connexions externes</label><div class="val">${externalConns.length} sur ${node.n_connections || 0} au total</div></div>
        ${externalConns.length ? fmtConnections(externalConns) : ''}
        ${investigationRows(node)}
        ${fmtIncompleteWarning(node)}
      `;
    }

    function renderDebugPanel(node) {
      if (node.type === 'file') return panelHeader(node) + `<div class="field"><label>Chemin complet</label><div class="val">${escapeHtml(node.full_path || node.name)}</div></div>`;
      if (node.type === 'connection') return panelHeader(node) + `<div class="field"><label>ID interne</label><div class="val">${escapeHtml(node.id)}</div></div>`;
      return panelHeader(node) + `
        <div class="field"><label>PID / PPID</label><div class="val">${node.pid} / ${node.ppid ?? '—'}</div></div>
        <div class="field"><label>Utilisateur</label><div class="val">${escapeHtml(node.username || '—')}</div></div>
        <div class="field"><label>CPU / RAM</label><div class="val">${node.cpu}% · ${node.mem}%</div></div>
        <div class="field"><label>Exécutable ${copyBtn(node.exe, 'copier')}</label><div class="val">${escapeHtml(node.exe || '—')}</div></div>
        <div class="field"><label>Répertoire de travail</label><div class="val">${escapeHtml(node.cwd || '—')}</div></div>
        <div class="field"><label>Commande complète ${copyBtn(node.cmdline, 'copier')}</label><div class="val">${escapeHtml(node.cmdline || '—')}</div></div>
        ${node.container ? `<div class="field"><label>Conteneur</label><div class="val">${escapeHtml(node.container)}</div></div>` : ''}
        ${node.integrity_status ? `<div class="field"><label>Intégrité du binaire</label><div class="val" style="color:${node.integrity_status === 'modifie' ? '#F44336' : 'inherit'}">${escapeHtml(node.integrity_status)}</div></div>` : ''}
        <div class="field"><label>Arrêter ce processus ${copyBtn('kill ' + node.pid, 'copier')}</label><div class="val" style="color:var(--muted)">kill ${node.pid}</div></div>
        <div class="field"><label>Fichiers ouverts</label><div class="val">${node.n_open_files ?? 0}</div></div>
        <div class="field"><label>Connexions (${node.n_connections ?? 0})</label>${fmtConnections(node.connections)}</div>
        ${fmtIncompleteWarning(node)}
      `;
    }

    function renderVerbosePanel(node) {
      const skip = new Set(['id', 'color', 'val', 'connections']);
      let rows = '';
      for (const [k, v] of Object.entries(node)) {
        if (skip.has(k) || v === null || v === undefined || v === '') continue;
        rows += `<div class="field"><label>${escapeHtml(k)}</label><div class="val">${escapeHtml(String(v))}</div></div>`;
      }
      if (node.connections && node.connections.length) {
        rows += `<div class="field"><label>connexions</label>${fmtConnections(node.connections)}</div>`;
      }
      return panelHeader(node) + rows;
    }

    function renderKnowledgePanel(node) {
      const text = node.knowledge_text || "Pas d'explication disponible pour cet élément.";
      let badge = '';
      if (node.type === 'process') {
        const c = node.enriched ? '#FFD54F' : '#90A4AE';
        badge = `<div class="field"><span class="risk-badge" style="background:${c}22; color:${c}; border:1px solid ${c}">${node.enriched ? 'Analysé par Ollama' : 'Base de connaissance locale'}</span></div>`;
      }
      return panelHeader(node) + badge + `
        <div class="field"><label>Explication</label><div class="val">${escapeHtml(text)}</div></div>
        ${node.type === 'process' && node.role_probable ? `<div class="field"><label>Rôle probable de ce processus précis</label><div class="val">${escapeHtml(node.role_probable)}</div></div>` : ''}
      `;
    }

    function renderTypePanel(node) {
      if (node.type === 'file') return panelHeader(node) + `<div class="field"><label>Chemin</label><div class="val">${escapeHtml(node.full_path || node.name)}</div></div>`;
      if (node.type === 'connection') return panelHeader(node) + `<div class="field"><label>Protocole</label><div class="val">${node.protocol.toUpperCase()}</div></div>`;
      const cat = node.categorie || 'inconnu';
      const color = categoryColor(cat);
      return panelHeader(node) + `
        <div class="field"><span class="risk-badge" style="background:${color}22; color:${color}; border:1px solid ${color}">${escapeHtml(cat)}</span></div>
        <div class="field"><label>Rôle probable</label><div class="val">${escapeHtml(node.role_probable || 'non enrichi')}</div></div>
        <div class="field"><label>CPU / RAM</label><div class="val">${node.cpu}% · ${node.mem}%</div></div>
      `;
    }

    const PANEL_RENDERERS = {
      type: renderTypePanel,
      securite: renderSecurityPanel,
      debug: renderDebugPanel,
      info_verbose: renderVerbosePanel,
      knowledge: renderKnowledgePanel,
    };

    function showPanel(node) {
      lastSelectedNode = node;
      COPY_REGISTRY.length = 0;  // les boutons de l'ancien panneau n'existent plus
      panelBody.innerHTML = (PANEL_RENDERERS[currentMode] || renderSecurityPanel)(node);
      panel.classList.add('open');
    }

    document.getElementById('closePanel').addEventListener('click', () => panel.classList.remove('open'));

    const Graph = ForceGraph3D()(el)
      .backgroundColor('#05070d')
      .graphData(currentGraphData())
      .nodeId('id')
      .nodeLabel(n => `${n.name}${n.type === 'process' ? ' (pid ' + n.pid + ')' : ''}`)
      .nodeVal('val')
      .nodeColor(n => modeNodeColor(n, currentMode))
      .nodeOpacity(0.95)
      .nodeResolution(20)
      .linkColor(l => LINK_COLORS[l.kind] || 'rgba(150,165,200,0.35)')
      .linkWidth(l => (l.kind === 'tcp' || l.kind === 'udp' || l.kind === 'unix') ? 1.4 : 0.8)
      .linkDirectionalParticles(l => (l.kind === 'opens' || l.kind === 'tcp' || l.kind === 'udp') ? 1 : 0)
      .linkDirectionalParticleWidth(1.2)
      .linkDirectionalParticleSpeed(0.004)
      .onNodeClick(node => {
        showPanel(node);
        const distance = 90;
        const ratio = 1 + distance / Math.hypot(node.x || 1, node.y || 1, node.z || 1);
        Graph.cameraPosition(
          { x: (node.x || 0.1) * ratio, y: (node.y || 0.1) * ratio, z: (node.z || 0.1) * ratio },
          node,
          800
        );
      })
      .onBackgroundClick(() => panel.classList.remove('open'));

    function updateStats() {
      const { nodes, links } = currentGraphData();
      const hiddenCount = GRAPH_DATA.nodes.length - nodes.length;
      statsEl.textContent = `${nodes.length} nœuds affichés · ${links.length} relations`
        + (hiddenCount > 0 ? ` · ${hiddenCount} masqués par les filtres` : '');
    }
    updateStats();

    document.querySelectorAll('.legend-row').forEach(row => {
      row.addEventListener('click', () => {
        const key = row.dataset.key;
        if (hiddenKeys.has(key)) hiddenKeys.delete(key); else hiddenKeys.add(key);
        row.classList.toggle('disabled', hiddenKeys.has(key));
        Graph.graphData(currentGraphData());
        updateStats();
      });
    });

    document.getElementById('search').addEventListener('input', applyNodeColors);

    document.querySelectorAll('.mode-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        currentMode = btn.dataset.mode;
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.toggle('active', b === btn));
        applyNodeColors();
        if (panel.classList.contains('open') && lastSelectedNode) showPanel(lastSelectedNode);
      });
    });

    // Contrôles caméra : zoom avant/arrière déplacent la caméra le long de
    // l'axe origine -> caméra ; recentrer utilise zoomToFit (natif à
    // 3d-force-graph) pour cadrer l'ensemble du graphe visible.
    function zoomBy(factor) {
      const cam = Graph.camera();
      const { x, y, z } = cam.position;
      Graph.cameraPosition({ x: x * factor, y: y * factor, z: z * factor }, undefined, 300);
    }
    function recenter() {
      panel.classList.remove('open');
      Graph.zoomToFit(600, 60);
    }
    document.getElementById('zoomIn').addEventListener('click', () => zoomBy(0.75));
    document.getElementById('zoomOut').addEventListener('click', () => zoomBy(1.35));
    document.getElementById('recenter').addEventListener('click', recenter);
    // Raccourcis clavier (H20) : Ctrl+molette du navigateur zoome la PAGE
    // (pas le graphe) et Ctrl+R recharge la page par défaut — on intercepte
    // ces combinaisons avec preventDefault() pour les rediriger vers les
    // contrôles caméra du graphe à la place. "R" seul reste aussi actif
    // (sans conflit navigateur) pour compatibilité avec l'existant.
    // Raccourcis supplémentaires (H34) : Échap ferme le panneau, / focalise
    // la recherche, 1-5 changent de mode d'affichage — jamais interceptés
    // pendant une saisie dans le champ de recherche.
    const MODE_KEYS = { '1': 'type', '2': 'securite', '3': 'debug', '4': 'info_verbose', '5': 'knowledge' };
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (document.activeElement === document.getElementById('search')) { document.activeElement.blur(); return; }
        panel.classList.remove('open');
        return;
      }
      const typing = document.activeElement && (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA');
      if (typing) return;
      if (e.key === '/' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        document.getElementById('search').focus();
        return;
      }
      if (MODE_KEYS[e.key] && !e.ctrlKey && !e.metaKey && !e.altKey) {
        document.querySelector(`.mode-btn[data-mode="${MODE_KEYS[e.key]}"]`).click();
        return;
      }
      if (e.ctrlKey && (e.key === 'r' || e.key === 'R')) { e.preventDefault(); recenter(); return; }
      if (e.ctrlKey && (e.key === '+' || e.key === '=')) { e.preventDefault(); zoomBy(0.75); return; }
      if (e.ctrlKey && (e.key === '-' || e.key === '_')) { e.preventDefault(); zoomBy(1.35); return; }
      if ((e.key === 'r' || e.key === 'R') && !e.metaKey && !e.ctrlKey) recenter();
    });
  </script>
</body>
</html>
"""


def render_interactive_3d(
    graph: nx.DiGraph,
    processes: list[ProcessInfo],
    output_path: Path,
    title: str = "Graphe 3D interactif des processus (enrichi Ollama)",
) -> None:
    """Génère un HTML autonome avec un graphe 3D interactif façon "système
    solaire" (3d-force-graph / three.js) : nœuds cliquables, zoom/orbite à
    la souris, panneau de détails, filtres par niveau de risque, recherche.

    Nécessite une connexion réseau à l'ouverture du fichier (la lib
    3d-force-graph est chargée depuis unpkg.com, cf. règle CDN pour les
    scripts externes d'artefacts HTML). Aucune donnée n'est envoyée à
    l'extérieur : seul le chargement du script JS est un appel réseau.
    """
    if graph.number_of_nodes() == 0:
        logger.warning("Graphe vide — aucun HTML interactif généré.")
        return

    payload = build_graph_payload(graph, processes)
    # Échappement de "</" -> "<\/" : une cmdline contenant littéralement
    # "</script>" ne doit pas pouvoir casser la balise <script> englobante.
    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = _HTML_TEMPLATE.replace("__TITLE__", title).replace(
        "__GRAPH_DATA_JSON__", payload_json
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info("Graphe 3D interactif écrit : %s", output_path)


# ---------------------------------------------------------------------------
# 5bis. Rapport de synthèse Markdown + export CSV (H19)
# ---------------------------------------------------------------------------

def compute_summary_stats(processes: list[ProcessInfo], graph: nx.DiGraph) -> dict:
    """Agrège les statistiques utilisées par le rapport de synthèse ET par
    le résumé console de l'assistant novice, pour n'avoir qu'un seul
    endroit à faire évoluer si le contenu du résumé change."""
    by_risk: dict[str, int] = {"faible": 0, "moyen": 0, "eleve": 0, "inconnu": 0}
    risky: list[ProcessInfo] = []
    incomplete: list[ProcessInfo] = []
    divergent: list[ProcessInfo] = []
    n_enriched = 0
    n_enrich_failed = 0

    for p in processes:
        niveau = (p.risk or {}).get("niveau_final", "inconnu")
        by_risk[niveau] = by_risk.get(niveau, 0) + 1
        if niveau == "eleve":
            risky.append(p)
        if p.collecte_incomplete:
            incomplete.append(p)
        if (p.risk or {}).get("divergence"):
            divergent.append(p)
        if p.enrichment:
            reason = p.enrichment.get("justification_risque", "")
            if reason in ("ollama_indisponible", "timeout_ollama", "reponse_json_invalide", "preflight_echec", "hors_limite_enrichissement", "enrichissement_desactive") or reason.startswith("erreur_inattendue"):
                n_enrich_failed += 1
            else:
                n_enriched += 1

    top_consumers = sorted(processes, key=lambda p: p.score, reverse=True)[:5]
    external_endpoints = {
        c.get("raddr") for p in processes for c in p.connections
        if c.get("raddr") and not c["raddr"].split(":")[0].startswith(("127.", "::1", "0.0.0.0"))
    }
    shared_files = sum(1 for _, d in graph.nodes(data=True) if d.get("kind") == "file")

    return {
        "total": len(processes),
        "by_risk": by_risk,
        "risky": risky,
        "incomplete": incomplete,
        "divergent": divergent,
        "top_consumers": top_consumers,
        "external_endpoints": sorted(external_endpoints),
        "shared_files": shared_files,
        "n_enriched": n_enriched,
        "n_enrich_failed": n_enrich_failed,
    }


def render_summary_report(stats: dict, meta: dict, output_path: Optional[Path] = None) -> str:
    """Construit le texte Markdown du rapport de synthèse (H19) et l'écrit
    sur disque si `output_path` est fourni. Retourne le texte dans tous les
    cas pour un éventuel affichage console (assistant novice)."""
    lines = [
        "# Rapport de synthèse — analyse des processus",
        "",
        f"- Date d'analyse : {meta.get('date', '?')}",
        f"- Plateforme : {meta.get('platform', '?')}",
        f"- Processus analysés : {stats['total']}",
        f"- Modèle IA utilisé : {meta.get('model') or 'aucun (enrichissement désactivé ou indisponible)'}",
        "",
        "## Répartition du niveau de risque final (règles + IA, escalade uniquement)",
        "",
        f"- Élevé : {stats['by_risk'].get('eleve', 0)}",
        f"- Moyen : {stats['by_risk'].get('moyen', 0)}",
        f"- Faible : {stats['by_risk'].get('faible', 0)}",
        f"- Inconnu : {stats['by_risk'].get('inconnu', 0)}",
        "",
    ]

    if stats["risky"]:
        lines.append("## Processus à risque élevé")
        lines.append("")
        for p in stats["risky"][:30]:
            signaux = "; ".join((p.risk or {}).get("signaux_regles", [])) or "—"
            lines.append(f"- **{p.name}** (pid {p.pid}, {p.username or 'utilisateur inconnu'}) — {signaux}")
        if len(stats["risky"]) > 30:
            lines.append(f"- … et {len(stats['risky']) - 30} autre(s) processus à risque élevé.")
        lines.append("")

    if stats["divergent"]:
        lines.append("## Avis divergents entre règles et IA")
        lines.append("")
        lines.append("Le niveau final retenu est toujours le plus élevé des deux (H17), mais ces divergences méritent un coup d'œil :")
        lines.append("")
        for p in stats["divergent"][:20]:
            r = p.risk or {}
            lines.append(f"- **{p.name}** (pid {p.pid}) — règles : {r.get('niveau_regles')}, IA : {r.get('niveau_ia')}")
        lines.append("")

    lines.append("## Top 5 processus les plus consommateurs (CPU + RAM)")
    lines.append("")
    for p in stats["top_consumers"]:
        lines.append(f"- **{p.name}** (pid {p.pid}) — CPU {p.cpu_percent}% · RAM {p.memory_percent}%")
    lines.append("")

    lines.append("## Réseau et fichiers")
    lines.append("")
    lines.append(f"- Points de terminaison externes distincts observés : {len(stats['external_endpoints'])}")
    lines.append(f"- Fichiers partagés entre plusieurs processus : {stats['shared_files']}")
    lines.append("")

    if stats["incomplete"]:
        lines.append("## Collecte incomplète (permissions / processus disparus)")
        lines.append("")
        lines.append(f"{len(stats['incomplete'])} processus ont au moins un champ non collecté (accès refusé le plus souvent — normal sans droits élevés, cf. H6/H7).")
        lines.append("")

    lines.append("## Enrichissement IA")
    lines.append("")
    lines.append(f"- Processus enrichis avec succès : {stats['n_enriched']}")
    lines.append(f"- Processus non enrichis (hors limite, échec, ou désactivé) : {stats['n_enrich_failed']}")
    lines.append("")
    lines.append("_Rapport généré automatiquement — le niveau de risque final combine un moteur de règles déterministe et, "
                  "s'il est disponible, l'avis d'un modèle Ollama local, par escalade uniquement (H17)._")

    text = "\n".join(lines) + "\n"
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        logger.info("Rapport de synthèse écrit : %s", output_path)
    return text


def export_csv(processes: list[ProcessInfo], output_path: Path) -> None:
    """Exporte les processus collectés/enrichis en CSV (une ligne par
    processus, champs aplatis), en plus du JSON existant, pour ouverture
    directe dans un tableur."""
    import csv

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "pid", "ppid", "name", "username", "exe", "cwd", "cmdline",
        "cpu_percent", "memory_percent", "n_open_files", "n_connections",
        "categorie", "role_probable", "niveau_risque_final",
        "niveau_risque_regles", "signaux_regles", "niveau_risque_ia",
        "risque_divergent", "collecte_incomplete",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in processes:
            risk = p.risk or {}
            enrichment = p.enrichment or {}
            writer.writerow({
                "pid": p.pid,
                "ppid": p.ppid,
                "name": p.name,
                "username": p.username or "",
                "exe": p.exe or "",
                "cwd": p.cwd or "",
                "cmdline": p.cmdline,
                "cpu_percent": p.cpu_percent,
                "memory_percent": p.memory_percent,
                "n_open_files": len(p.open_files),
                "n_connections": len(p.connections),
                "categorie": enrichment.get("categorie", ""),
                "role_probable": enrichment.get("role_probable", ""),
                "niveau_risque_final": risk.get("niveau_final", "inconnu"),
                "niveau_risque_regles": risk.get("niveau_regles", "inconnu"),
                "signaux_regles": "; ".join(risk.get("signaux_regles", [])),
                "niveau_risque_ia": risk.get("niveau_ia") or "",
                "risque_divergent": risk.get("divergence", False),
                "collecte_incomplete": "; ".join(p.collecte_incomplete),
            })
    logger.info("Export CSV écrit : %s", output_path)


def export_csv_edges(graph: "nx.DiGraph", processes: list[ProcessInfo], output_path: Path) -> None:
    """Exporte les RELATIONS du graphe en CSV (H28) — une ligne par arête
    (parent/enfant, fichier partagé, connexion réseau), avec le niveau de
    risque des deux extrémités quand ce sont des processus. Importable tel
    quel dans Gephi / Neo4j / un tableur."""
    import csv

    pid_risk = {p.pid: (p.risk or {}).get("niveau_final", "inconnu") for p in processes}

    def _node_label(node_id: str) -> str:
        data = graph.nodes.get(node_id, {})
        return data.get("label", node_id)

    def _node_risk(node_id: str) -> str:
        data = graph.nodes.get(node_id, {})
        if data.get("kind") == "process":
            return pid_risk.get(data.get("pid"), "inconnu")
        return ""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "target", "kind", "source_label", "target_label", "source_risk", "target_risk"])
        for u, v, edata in graph.edges(data=True):
            writer.writerow([
                u, v, edata.get("kind", ""),
                _node_label(u), _node_label(v),
                _node_risk(u), _node_risk(v),
            ])
    logger.info("Export CSV des relations écrit : %s (%d arêtes)", output_path, graph.number_of_edges())


# ---------------------------------------------------------------------------
# 5ter. Historique des exécutions + comparaison de snapshots (H29)
# ---------------------------------------------------------------------------

HISTORY_MAX_RUNS = 50


def snapshot_from_processes(processes: list[ProcessInfo]) -> dict:
    """Snapshot LÉGER d'une exécution (pas les fichiers ouverts ni les
    connexions détaillées) — suffisant pour comparer deux exécutions :
    apparitions/disparitions de processus, évolutions de risque, CPU/RAM."""
    return {
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": time.time(),
        "n_processes": len(processes),
        "processes": [
            {
                "pid": p.pid,
                "name": p.name,
                "exe": p.exe,
                "cpu_percent": p.cpu_percent,
                "memory_percent": p.memory_percent,
                "niveau_final": (p.risk or {}).get("niveau_final", "inconnu"),
            }
            for p in processes
        ],
    }


def append_history(processes: list[ProcessInfo], history_path: Path) -> Optional[dict]:
    """Ajoute le snapshot de cette exécution à l'historique JSON (plafonné à
    HISTORY_MAX_RUNS entrées, les plus anciennes éjectées) et retourne le
    snapshot PRÉCÉDENT (utile pour --compare sans argument)."""
    history: list[dict] = []
    if history_path.exists():
        try:
            loaded = json.loads(history_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                history = loaded
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Historique illisible (%s) — repartira de zéro : %s", history_path, exc)
    previous = history[-1] if history else None
    history.append(snapshot_from_processes(processes))
    history = history[-HISTORY_MAX_RUNS:]
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    logger.info("Snapshot ajouté à l'historique : %s (%d exécution(s) conservée(s))", history_path, len(history))
    return previous


def _snapshot_key(entry: dict) -> tuple:
    # Un processus est identifié par (pid, nom) : un pid seul peut être
    # réutilisé par l'OS entre deux exécutions espacées.
    return (entry.get("pid"), entry.get("name"))


def compare_snapshots(previous: dict, processes: list[ProcessInfo]) -> str:
    """Compare l'exécution courante à un snapshot précédent et rend un
    rapport texte : nouveaux processus, disparus, changements de niveau de
    risque, plus fortes évolutions CPU/RAM."""
    current = snapshot_from_processes(processes)
    prev_by_key = {_snapshot_key(e): e for e in previous.get("processes", [])}
    curr_by_key = {_snapshot_key(e): e for e in current["processes"]}

    new_keys = [k for k in curr_by_key if k not in prev_by_key]
    gone_keys = [k for k in prev_by_key if k not in curr_by_key]
    common_keys = [k for k in curr_by_key if k in prev_by_key]

    risk_changes = []
    deltas = []
    for k in common_keys:
        prev_e, curr_e = prev_by_key[k], curr_by_key[k]
        if prev_e.get("niveau_final") != curr_e.get("niveau_final"):
            risk_changes.append((curr_e, prev_e.get("niveau_final"), curr_e.get("niveau_final")))
        d_cpu = (curr_e.get("cpu_percent") or 0) - (prev_e.get("cpu_percent") or 0)
        d_mem = (curr_e.get("memory_percent") or 0) - (prev_e.get("memory_percent") or 0)
        if abs(d_cpu) >= 1.0 or abs(d_mem) >= 1.0:
            deltas.append((curr_e, d_cpu, d_mem))
    deltas.sort(key=lambda t: abs(t[1]) + abs(t[2]), reverse=True)

    lines = [
        "=" * 64,
        "COMPARAISON AVEC LE SNAPSHOT PRÉCÉDENT",
        f"  précédent : {previous.get('date', '?')} ({len(prev_by_key)} processus)",
        f"  courant   : {current['date']} ({len(curr_by_key)} processus)",
        "=" * 64,
        "",
        f"Nouveaux processus ({len(new_keys)}) :",
    ]
    for k in sorted(new_keys, key=lambda k: -(curr_by_key[k].get("cpu_percent") or 0))[:25]:
        e = curr_by_key[k]
        lines.append(f"  + pid {e['pid']:>7}  {e['name']}  (risque: {e['niveau_final']}, cpu {e['cpu_percent']}%)")
    if len(new_keys) > 25:
        lines.append(f"  ... et {len(new_keys) - 25} autres")
    lines += ["", f"Processus disparus ({len(gone_keys)}) :"]
    for k in sorted(gone_keys)[:25]:
        e = prev_by_key[k]
        lines.append(f"  - pid {e['pid']:>7}  {e['name']}")
    if len(gone_keys) > 25:
        lines.append(f"  ... et {len(gone_keys) - 25} autres")
    lines += ["", f"Changements de niveau de risque ({len(risk_changes)}) :"]
    for e, old, new in risk_changes:
        lines.append(f"  ~ pid {e['pid']:>7}  {e['name']}  : {old} -> {new}")
    lines += ["", f"Plus fortes évolutions CPU/RAM (seuil ±1 point, top 15 sur {len(deltas)}) :"]
    for e, d_cpu, d_mem in deltas[:15]:
        lines.append(f"  ~ pid {e['pid']:>7}  {e['name']}  cpu {d_cpu:+.1f}%  ram {d_mem:+.1f}%")
    if not risk_changes and not new_keys and not gone_keys and not deltas:
        lines.append("  (aucune différence notable)")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5quater. Rapport forensique d'un seul processus (--pid, H30)
# ---------------------------------------------------------------------------

def filter_process_tree(processes: list[ProcessInfo], target_pid: int) -> list[ProcessInfo]:
    """Réduit la liste au processus cible + tous ses ancêtres + toute sa
    descendance (le sous-arbre pertinent pour une analyse forensique)."""
    by_pid = {p.pid: p for p in processes}
    if target_pid not in by_pid:
        return []
    keep: set[int] = {target_pid}
    # Ancêtres (borne de sécurité contre un cycle ppid corrompu)
    cursor, hops = by_pid[target_pid], 0
    while cursor.ppid in by_pid and cursor.ppid not in keep and hops < 100:
        keep.add(cursor.ppid)
        cursor = by_pid[cursor.ppid]
        hops += 1
    # Descendance (BFS)
    children_of: dict[int, list[int]] = {}
    for p in processes:
        if p.ppid is not None:
            children_of.setdefault(p.ppid, []).append(p.pid)
    frontier = [target_pid]
    while frontier:
        pid = frontier.pop()
        for child in children_of.get(pid, []):
            if child not in keep:
                keep.add(child)
                frontier.append(child)
    return [p for p in processes if p.pid in keep]


def render_pid_report(target: ProcessInfo, tree: list[ProcessInfo]) -> str:
    """Rapport texte détaillé d'UN processus : identité complète, risque et
    signaux, connexions, fichiers ouverts, arbre ancêtres/descendants."""
    risk = target.risk or {}
    by_pid = {p.pid: p for p in tree}
    lines = [
        "=" * 64,
        f"RAPPORT DÉTAILLÉ — {target.name} (pid {target.pid})",
        "=" * 64,
        "",
        f"  Utilisateur        : {target.username or '—'}",
        f"  Exécutable         : {target.exe or '—'}",
        f"  Rép. de travail    : {target.cwd or '—'}",
        f"  Ligne de commande  : {target.cmdline or '—'}",
        f"  CPU / RAM          : {target.cpu_percent}% / {target.memory_percent}%",
        f"  Conteneur          : {target.container or 'non (hôte)'}",
    ]
    if target.exe_sha256:
        lines.append(f"  SHA256 exécutable  : {target.exe_sha256} ({target.integrity_status})")
    lines += [
        "",
        f"  Niveau de risque final : {risk.get('niveau_final', 'inconnu').upper()}",
        f"  Niveau par règles      : {risk.get('niveau_regles', 'inconnu')}",
    ]
    for s in risk.get("signaux_regles", []):
        lines.append(f"    - {s}")
    if risk.get("niveau_ia"):
        lines.append(f"  Avis Ollama            : {risk['niveau_ia']} ({risk.get('justification_ia', '')})")
    enrichment = target.enrichment or {}
    if enrichment.get("role_probable") and enrichment.get("role_probable") != "non enrichi":
        lines += ["", f"  Rôle probable : {enrichment['role_probable']}",
                  f"  Catégorie     : {enrichment.get('categorie', 'inconnu')}"]
    if target.collecte_incomplete:
        lines += ["", "  Collecte incomplète : " + ", ".join(target.collecte_incomplete)]

    lines += ["", f"Connexions réseau ({len(target.connections)}) :"]
    for c in target.connections[:30] or []:
        lines.append(f"  [{c.get('protocol', '?').upper():4}] {c.get('laddr') or '?'} -> {c.get('raddr') or '—'}  {c.get('status', '')}")
    if not target.connections:
        lines.append("  (aucune)")

    lines += ["", f"Fichiers ouverts ({len(target.open_files)}) :"]
    for path in target.open_files[:30]:
        lines.append(f"  {path}")
    if len(target.open_files) > 30:
        lines.append(f"  ... et {len(target.open_files) - 30} autres")
    if not target.open_files:
        lines.append("  (aucun visible — permissions ?)")

    # Chaîne d'ancêtres puis arbre descendant indenté
    ancestors = []
    cursor, hops = target, 0
    while cursor.ppid in by_pid and hops < 100:
        cursor = by_pid[cursor.ppid]
        if cursor.pid in [a.pid for a in ancestors] + [target.pid]:
            break
        ancestors.append(cursor)
        hops += 1
    lines += ["", "Arbre du processus :"]
    for depth, anc in enumerate(reversed(ancestors)):
        lines.append("  " + "  " * depth + f"{anc.name} (pid {anc.pid})")
    depth_target = len(ancestors)

    children_of: dict[int, list[ProcessInfo]] = {}
    for p in tree:
        if p.ppid is not None:
            children_of.setdefault(p.ppid, []).append(p)

    def _walk(p: ProcessInfo, depth: int, visited: set[int]) -> None:
        marker = "  " + "  " * depth + f"{p.name} (pid {p.pid})"
        if p.pid == target.pid:
            marker += "   <== CIBLE"
        lines.append(marker)
        for child in sorted(children_of.get(p.pid, []), key=lambda c: c.pid):
            if child.pid not in visited:
                visited.add(child.pid)
                _walk(child, depth + 1, visited)

    _walk(target, depth_target, {target.pid})
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5quinquies. Mode bac à sable (--sandbox, H31) : rejoue un export JSON
# ---------------------------------------------------------------------------

def load_sandbox_processes(path: Path) -> list[ProcessInfo]:
    """Reconstruit des ProcessInfo depuis un fichier JSON au format de
    --json-export, au lieu de collecter le système réel. Permet de tester
    le moteur de règles / la configuration whitelist-blacklist / le rendu
    sur des données simulées ou capturées ailleurs, sans toucher au
    système. Les champs manquants prennent des valeurs neutres."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Le fichier sandbox doit contenir une LISTE de processus (format --json-export).")
    processes = []
    for entry in data:
        if not isinstance(entry, dict) or "pid" not in entry:
            continue
        processes.append(ProcessInfo(
            pid=int(entry["pid"]),
            ppid=entry.get("ppid"),
            name=str(entry.get("name", f"pid-{entry['pid']}")),
            username=entry.get("username"),
            exe=entry.get("exe"),
            cwd=entry.get("cwd"),
            cmdline=str(entry.get("cmdline", "")),
            cpu_percent=float(entry.get("cpu_percent", 0.0)),
            memory_percent=float(entry.get("memory_percent", 0.0)),
            open_files=list(entry.get("open_files", []) or []),
            connections=list(entry.get("connections", []) or []),
            collecte_incomplete=list(entry.get("collecte_incomplete", []) or []),
            cmdline_vide=not entry.get("cmdline"),
            container=entry.get("container"),
        ))
    logger.info("Mode sandbox : %d processus chargés depuis %s (aucune collecte système).", len(processes), path)
    return processes


# ---------------------------------------------------------------------------
# 6. Ouverture cross-plateforme des résultats
# ---------------------------------------------------------------------------

def open_path_cross_platform(path: Path) -> None:
    """Ouvre un fichier avec l'application par défaut du système, sans
    dépendre de `open` (macOS uniquement, utilisé par les anciens
    launchers .command). Ne fait jamais planter le script : un échec
    d'ouverture automatique est loggé en DEBUG, pas une erreur fatale."""
    try:
        if path.suffix.lower() in (".html", ".htm"):
            webbrowser.open(path.resolve().as_uri())
            return
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        elif sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as exc:  # défensif : l'ouverture auto est un confort, pas un pré-requis
        logger.debug("Impossible d'ouvrir automatiquement %s : %s", path, exc)


# ---------------------------------------------------------------------------
# 7. Assistant interactif (novice) — remplace le launcher .command séparé
# ---------------------------------------------------------------------------

def _prompt(message: str, default: str) -> str:
    try:
        raw = input(f"{message} [{default}] : ").strip()
    except (EOFError, KeyboardInterrupt):
        raw = ""
    return raw or default


def run_wizard() -> argparse.Namespace:
    """Assistant interactif minimal (2 questions), déclenché quand le
    script est lancé sans aucun argument — typiquement un double-clic sur
    l'exécutable PyInstaller par un utilisateur novice (H8)."""
    print("=" * 56)
    print(" Analyseur de processus système — assistant de démarrage")
    print("=" * 56)
    print()
    print("Astuce : pour un usage avancé (options en ligne de commande),")
    print("relance avec --help au lieu de double-cliquer.")
    print()

    raw = _prompt(
        "Nombre maximum de processus à inclure dans le graphe (les plus actifs sont prioritaires)",
        "150",
    )
    try:
        max_processes = int(raw)
        if max_processes <= 0:
            raise ValueError
    except ValueError:
        print(f"Valeur invalide ('{raw}'), utilisation de la valeur par défaut : 150")
        max_processes = 150

    print()
    host = "http://localhost:11434"
    print(f"Recherche des modèles Ollama disponibles ({host})...")
    models = _detect_ollama_models(host)

    if not models:
        # Ollama n'est pas joignable du tout -> proposer une installation
        # automatique adaptée à l'OS (H12), avec accord explicite requis.
        if not _ollama_reachable(host) and ensure_ollama_ready(host):
            models = _detect_ollama_models(host)
        # Soit Ollama tourne déjà sans aucun modèle, soit il vient d'être
        # installé mais reste vide -> proposer le téléchargement direct du
        # modèle par défaut plutôt que de laisser l'utilisateur sans IA.
        if not models and _ollama_reachable(host):
            print("Aucun modèle Ollama installé localement.")
            taille = "~1,3 Go, modèle mini adapté au mobile" if IS_ANDROID else "plusieurs Go"
            answer = _prompt(
                f"Télécharger le modèle par défaut ({DEFAULT_OLLAMA_MODEL}, {taille}) maintenant ? (o/n)",
                "o",
            )
            if answer.strip().lower() in ("o", "oui", "y", "yes"):
                if pull_ollama_model(DEFAULT_OLLAMA_MODEL, host):
                    models = _detect_ollama_models(host)

    model: Optional[str] = None
    if models:
        print("Modèles détectés :")
        for i, m in enumerate(models, start=1):
            print(f"  {i}) {m}")
        print("  0) Aucun (désactiver l'enrichissement IA)")
        raw = _prompt("Quel modèle utiliser ?", "1")
        try:
            choice = int(raw)
        except ValueError:
            choice = 1
        if 1 <= choice <= len(models):
            model = models[choice - 1]
            print(f"Modèle sélectionné : {model}")
        else:
            print("Enrichissement IA désactivé.")
    else:
        print("L'analyse continuera sans enrichissement IA.")
        print("(Pour l'activer plus tard : installe Ollama, lance 'ollama serve', puis "
              f"'ollama pull {DEFAULT_OLLAMA_MODEL}')")

    # H8 : le nombre de processus enrichis par IA est dérivé automatiquement
    # du nombre max de processus plutôt que de poser une 3e question.
    enrich_limit = min(max_processes, 40)

    base_dir = Path(sys.executable).resolve().parent if IS_FROZEN else Path.cwd()
    out_dir = base_dir / "sorties"
    stamp = time.strftime("%Y%m%d_%H%M%S")

    print()
    print(f"Dossier de sortie : {out_dir}")
    print()

    # H19 : l'assistant novice ne produit QUE le graphe 3D interactif — pas
    # de PNG, JSON, CSV ni rapport écrits sur disque par défaut. Pour ces
    # formats, relancer avec les options CLI (--png / --json-export /
    # --csv-export / --report), voir --help.
    return argparse.Namespace(
        output=out_dir / f"process_graph_{stamp}.png",
        html_output=out_dir / f"process_graph_3d_{stamp}.html",
        no_html=False,
        png=False,
        model=model or "llama3.2",
        ollama_host=host,
        enrich_limit=enrich_limit,
        enrich_all=False,
        no_enrich=model is None,
        min_score=0.0,
        max_conn_per_process=20,
        max_conn_total=300,
        max_workers=2,
        timeout=120.0,
        json_export=None,
        csv_export=None,
        report=None,
        verbose=False,
        max_processes=max_processes,
    )


# ---------------------------------------------------------------------------
# 8. Orchestration / CLI
# ---------------------------------------------------------------------------

def run_watch(args: argparse.Namespace) -> int:
    """Mode surveillance continue (H32) : re-collecte périodiquement, ne
    fait tourner QUE la collecte + le moteur de règles (jamais Ollama en
    boucle — l'enrichissement IA reste un acte manuel/one-shot), régénère
    le HTML à chaque cycle et affiche les différences entre cycles
    (nouveaux processus, disparus, changements de risque). Ctrl+C pour
    arrêter proprement."""
    interval = max(5.0, float(getattr(args, "interval", 60.0)))
    baseline = load_baseline(args.baseline_file) if getattr(args, "baseline", False) or args.baseline_file.exists() else {}
    previous_snapshot: Optional[dict] = None
    cycle = 0
    logger.info("Mode surveillance : un cycle toutes les %.0fs (Ctrl+C pour arrêter). Ollama désactivé en boucle.", interval)
    try:
        while True:
            cycle += 1
            cycle_start = time.time()
            processes = collect_processes(min_score=args.min_score, max_conn_per_process=args.max_conn_per_process)
            processes = limit_processes(processes, getattr(args, "max_processes", None))
            if getattr(args, "check_integrity", False):
                check_integrity(processes, args.integrity_db)
            for p in processes:
                p.risk = compute_rule_based_risk(p, baseline=baseline)
                p.enrichment = _default_enrichment("mode_watch_sans_ia")
                finalize_risk(p)
            if getattr(args, "baseline", False):
                update_baseline(processes, args.baseline_file)
                baseline = load_baseline(args.baseline_file)

            graph = build_graph(processes, max_conn_total=args.max_conn_total)
            if not args.no_html:
                render_interactive_3d(graph, processes, args.html_output,
                                      title=f"Surveillance des processus — cycle {cycle}")

            by_risk: dict[str, int] = {}
            for p in processes:
                niveau = (p.risk or {}).get("niveau_final", "inconnu")
                by_risk[niveau] = by_risk.get(niveau, 0) + 1
            print(f"\n[cycle {cycle} — {time.strftime('%H:%M:%S')}] {len(processes)} processus | "
                  f"risque élevé: {by_risk.get('eleve', 0)} · moyen: {by_risk.get('moyen', 0)} · "
                  f"faible: {by_risk.get('faible', 0)}")
            for p in sorted(processes, key=lambda p: p.score, reverse=True)[:5]:
                print(f"    top: {p.name:<28} pid {p.pid:>7}  cpu {p.cpu_percent:5.1f}%  ram {p.memory_percent:5.1f}%")
            if previous_snapshot is not None:
                print(compare_snapshots(previous_snapshot, processes))
            previous_snapshot = snapshot_from_processes(processes)

            elapsed = time.time() - cycle_start
            time.sleep(max(1.0, interval - elapsed))
    except KeyboardInterrupt:
        print(f"\nSurveillance arrêtée après {cycle} cycle(s).")
        return 0


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyse les processus système, leurs fichiers liés et leurs relations, "
                    "enrichit via Ollama local, exporte un graphe PNG."
    )
    parser.add_argument("--output", type=Path, default=Path("process_graph.png"),
                         help="Chemin du PNG de sortie si --png est utilisé (défaut: process_graph.png)")
    parser.add_argument("--html-output", type=Path, default=Path("process_graph_3d.html"),
                         help="Chemin du HTML 3D interactif (défaut: process_graph_3d.html)")
    parser.add_argument("--no-html", action="store_true",
                         help="Désactive la génération du graphe 3D interactif")
    parser.add_argument("--png", action="store_true",
                         help="Génère AUSSI un PNG statique (H19 : désactivé par défaut, "
                              "seul le graphe 3D interactif est produit par défaut)")
    parser.add_argument("--model", default=DEFAULT_MODEL_ARG,
                         help=f"Modèle Ollama à utiliser (défaut: {DEFAULT_MODEL_ARG} — "
                              "mini sur Android/Termux, medium ailleurs)")
    parser.add_argument("--ollama-host", default="http://localhost:11434",
                         help="URL de l'API Ollama (défaut: http://localhost:11434)")
    parser.add_argument("--enrich-limit", type=int, default=25,
                         help="Nombre max de processus enrichis via Ollama, "
                              "triés par consommation CPU+RAM (défaut: 25)")
    parser.add_argument("--enrich-all", action="store_true",
                         help="Enrichit tous les processus collectés (ignore --enrich-limit)")
    parser.add_argument("--no-enrich", action="store_true",
                         help="Désactive complètement l'appel à Ollama")
    parser.add_argument("--min-score", type=float, default=0.0,
                         help="Score minimal (cpu%%+mem%%) pour inclure un processus (défaut: 0)")
    parser.add_argument("--max-processes", type=int, default=None,
                         help="Nombre max de processus inclus dans le graphe, garde les plus actifs "
                              "(défaut : aucune limite en CLI ; 150 dans l'assistant interactif)")
    parser.add_argument("--max-conn-per-process", type=int, default=20,
                         help="Connexions réseau brutes max collectées par processus (défaut: 20)")
    parser.add_argument("--max-conn-total", type=int, default=300,
                         help="Arêtes de connexion max dessinées au total (défaut: 300)")
    parser.add_argument("--max-workers", type=int, default=2,
                         help="Parallélisme des appels Ollama (défaut: 2 — un LLM local sert le plus "
                              "souvent en série, une forte parallélisation ne fait qu'empiler des "
                              "requêtes en file d'attente jusqu'à leur timeout)")
    parser.add_argument("--timeout", type=float, default=120.0,
                         help="Timeout par appel Ollama en secondes (défaut: 120 — un modèle de "
                              "plusieurs milliards de paramètres sur CPU peut être lent)")
    parser.add_argument("--json-export", type=Path, default=None,
                         help="Exporte aussi les données collectées/enrichies en JSON (désactivé par défaut)")
    parser.add_argument("--csv-export", type=Path, default=None,
                         help="Exporte aussi les données en CSV, une ligne par processus (désactivé par défaut)")
    parser.add_argument("--report", type=Path, default=None,
                         help="Écrit un rapport de synthèse Markdown à ce chemin (désactivé par défaut)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Logs DEBUG")

    # --- Modes d'exécution supplémentaires ---
    parser.add_argument("--watch", action="store_true",
                         help="Mode surveillance continue : re-collecte périodiquement (collecte + règles "
                              "uniquement, JAMAIS d'appel Ollama en boucle), affiche les différences entre "
                              "cycles et régénère le HTML. Ctrl+C pour arrêter.")
    parser.add_argument("--interval", type=float, default=60.0,
                         help="Intervalle en secondes entre deux cycles de --watch (défaut: 60)")
    parser.add_argument("--pid", type=int, default=None,
                         help="Analyse forensique d'UN processus : rapport texte détaillé (identité, risque, "
                              "connexions, fichiers, arbre ancêtres+descendants) ; le HTML est restreint à ce sous-arbre")
    parser.add_argument("--compare", type=Path, nargs="?", const=Path("__previous__"), default=None,
                         help="Compare l'exécution courante à un snapshot précédent : chemin d'un export JSON "
                              "(--json-export) OU sans valeur pour comparer à l'exécution précédente de l'historique")
    parser.add_argument("--history-file", type=Path, default=Path("sorties/history.json"),
                         help="Fichier d'historique des snapshots, alimenté automatiquement à chaque exécution "
                              "(défaut: sorties/history.json ; 50 exécutions conservées)")
    parser.add_argument("--no-history", action="store_true",
                         help="Désactive l'enregistrement automatique du snapshot dans l'historique")
    parser.add_argument("--sandbox", type=Path, default=None,
                         help="Mode bac à sable : lit les processus depuis un fichier JSON (format --json-export) "
                              "au lieu du système réel — pour tester règles/config/rendu sans risque")
    parser.add_argument("--preload-model", action="store_true",
                         help="Télécharge/prépare le modèle Ollama (--model) puis quitte, sans analyse — "
                              "pour préparer un usage hors-ligne")

    # --- Analyse et enrichissement ---
    parser.add_argument("--config", type=Path, default=None,
                         help="Fichier de configuration whitelist/blacklist (YAML simple ou JSON) : "
                              "les motifs whitelist neutralisent les signaux de chemin du moteur de règles, "
                              "les motifs blacklist forcent le niveau 'eleve'")
    parser.add_argument("--check-integrity", action="store_true",
                         help="Calcule le SHA256 de chaque exécutable et le compare à la base de référence "
                              "(--integrity-db) ; une empreinte modifiée est un signal de risque 'eleve'")
    parser.add_argument("--integrity-db", type=Path, default=Path("sorties/integrity.json"),
                         help="Base de référence des empreintes SHA256 (défaut: sorties/integrity.json)")
    parser.add_argument("--baseline", action="store_true",
                         help="Ajoute cette exécution à la baseline de performance (CPU/RAM par nom de processus) ; "
                              "dès 3 échantillons, les écarts >2 écarts-types deviennent des signaux de risque")
    parser.add_argument("--baseline-file", type=Path, default=Path("sorties/baseline.json"),
                         help="Fichier de baseline (défaut: sorties/baseline.json)")
    parser.add_argument("--cache", action="store_true",
                         help="Cache persistant SQLite des enrichissements Ollama : un processus identique "
                              "(nom+exe+cmdline) déjà analysé est resservi sans appel LLM")
    parser.add_argument("--cache-file", type=Path, default=Path("sorties/enrich_cache.sqlite3"),
                         help="Fichier du cache d'enrichissement (défaut: sorties/enrich_cache.sqlite3)")
    parser.add_argument("--cache-ttl-days", type=float, default=7.0,
                         help="Durée de validité des entrées du cache en jours (défaut: 7)")
    parser.add_argument("--retry-failed", type=int, default=0, metavar="N",
                         help="Retente jusqu'à N fois les enrichissements en échec transitoire "
                              "(timeout, Ollama saturé), avec backoff exponentiel 1s/2s/4s...")
    parser.add_argument("--plugin", type=Path, default=None,
                         help="Plugin Python utilisateur exposant enrich(process_info: dict) -> dict, "
                              "appliqué à chaque processus après l'enrichissement Ollama")

    # --- Exports supplémentaires ---
    parser.add_argument("--csv-edges", type=Path, default=None,
                         help="Exporte les RELATIONS du graphe en CSV (source, target, kind, risques) — "
                              "importable dans Gephi/Neo4j")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    raw_args = sys.argv[1:] if argv is None else argv
    # Aucun argument -> assistant interactif novice (H8) ; sinon CLI classique.
    wizard_mode = len(raw_args) == 0

    args = run_wizard() if wizard_mode else parse_args(raw_args)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # --preload-model : préparer Ollama + télécharger le modèle, puis
    # quitter — aucune analyse (H33). Utile pour préparer un usage hors-ligne.
    if getattr(args, "preload_model", False):
        if not ensure_ollama_ready(args.ollama_host):
            logger.error("Ollama indisponible — impossible de précharger le modèle.")
            return 1
        ok, message = check_ollama_available(args.model, args.ollama_host)
        if ok:
            logger.info("Le modèle %s est déjà disponible localement — rien à télécharger.", args.model)
            return 0
        logger.info("Téléchargement du modèle %s... (%s)", args.model, message)
        return 0 if pull_ollama_model(args.model, args.ollama_host) else 1

    # Configuration whitelist/blacklist (H23), chargée AVANT tout calcul de
    # risque (y compris en mode watch).
    if getattr(args, "config", None):
        try:
            USER_CONFIG.update(load_user_config(args.config))
        except (OSError, ValueError) as exc:
            logger.error("Configuration illisible (%s) : %s — arrêt.", args.config, exc)
            return 1

    # Mode surveillance continue (H32) : boucle dédiée, jamais d'Ollama.
    if getattr(args, "watch", False):
        return run_watch(args)

    if getattr(args, "sandbox", None):
        try:
            processes = load_sandbox_processes(args.sandbox)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.error("Fichier sandbox illisible (%s) : %s — arrêt.", args.sandbox, exc)
            return 1
    else:
        logger.info("Collecte des processus système...")
        processes = collect_processes(min_score=args.min_score, max_conn_per_process=args.max_conn_per_process)
    if not processes:
        logger.error("Aucun processus collecté (permissions insuffisantes ?). Arrêt.")
        if wizard_mode or IS_FROZEN:
            _pause_before_exit()
        return 1

    processes = limit_processes(processes, getattr(args, "max_processes", None))

    # Mode --pid : réduire l'analyse au sous-arbre du processus cible
    # (ancêtres + descendance) AVANT enrichissement — le rapport texte
    # détaillé est imprimé plus bas, une fois le risque finalisé.
    target_pid = getattr(args, "pid", None)
    if target_pid is not None:
        tree = filter_process_tree(processes, target_pid)
        if not tree:
            logger.error("PID %d introuvable parmi les processus collectés.", target_pid)
            return 1
        logger.info("Mode --pid %d : analyse restreinte à %d processus (cible + ancêtres + descendance).",
                    target_pid, len(tree))
        processes = tree

    # Vérification d'intégrité (H22) AVANT le moteur de règles, pour que le
    # statut "modifie" soit un signal de risque.
    if getattr(args, "check_integrity", False):
        check_integrity(processes, args.integrity_db)

    # Baseline de performance (H24) : les anomalies statistiques deviennent
    # des signaux du moteur de règles dès 3 échantillons enregistrés.
    baseline_file = getattr(args, "baseline_file", Path("sorties/baseline.json"))
    baseline = load_baseline(baseline_file) if (getattr(args, "baseline", False) or baseline_file.exists()) else {}

    # Moteur de règles (H17) : toujours calculé, indépendamment d'Ollama —
    # c'est le plancher du niveau de risque final, jamais l'unique source.
    for p in processes:
        p.risk = compute_rule_based_risk(p, baseline=baseline)

    if getattr(args, "baseline", False):
        update_baseline(processes, baseline_file)

    logger.info("Construction du graphe de relations...")
    graph = build_graph(processes, max_conn_total=args.max_conn_total)
    logger.info("Graphe : %d nœuds, %d arêtes", graph.number_of_nodes(), graph.number_of_edges())

    if args.no_enrich:
        logger.info("Enrichissement Ollama désactivé (--no-enrich).")
        for p in processes:
            p.enrichment = _default_enrichment("enrichissement_desactive")
    else:
        limit = None if args.enrich_all else args.enrich_limit
        cache = None
        if getattr(args, "cache", False):
            cache = EnrichmentCache(args.cache_file, ttl_days=args.cache_ttl_days)
        try:
            enrich_processes(
                processes,
                model=args.model,
                host=args.ollama_host,
                enrich_limit=limit,
                max_workers=args.max_workers,
                timeout=args.timeout,
                cache=cache,
                retry_failed=getattr(args, "retry_failed", 0),
            )
        finally:
            if cache is not None:
                cache.close()

    # Plugin utilisateur (H27), appliqué après l'enrichissement Ollama.
    if getattr(args, "plugin", None):
        apply_plugin(processes, args.plugin)

    # Combine règles + avis IA par escalade uniquement (H17), maintenant que
    # l'enrichissement (ou son repli) a rempli p.enrichment pour chacun.
    for p in processes:
        finalize_risk(p)

    # Historique + comparaison (H29). Le snapshot est enregistré APRÈS
    # finalize_risk pour que les niveaux comparés soient les définitifs.
    previous_from_history = None
    if not getattr(args, "no_history", False) and not getattr(args, "sandbox", None):
        try:
            previous_from_history = append_history(processes, getattr(args, "history_file", Path("sorties/history.json")))
        except OSError as exc:
            logger.warning("Impossible d'écrire l'historique : %s", exc)

    compare_arg = getattr(args, "compare", None)
    if compare_arg is not None:
        previous = None
        if str(compare_arg) == "__previous__":
            previous = previous_from_history
            if previous is None:
                logger.warning("--compare sans argument : aucun snapshot précédent dans l'historique — comparaison ignorée.")
        else:
            try:
                loaded = json.loads(Path(compare_arg).read_text(encoding="utf-8"))
                if isinstance(loaded, list):  # format --json-export
                    previous = {"date": "?", "processes": [
                        {"pid": e.get("pid"), "name": e.get("name"), "exe": e.get("exe"),
                         "cpu_percent": e.get("cpu_percent"), "memory_percent": e.get("memory_percent"),
                         "niveau_final": (e.get("risk") or {}).get("niveau_final", "inconnu")}
                        for e in loaded if isinstance(e, dict)
                    ]}
                elif isinstance(loaded, dict) and "processes" in loaded:  # format snapshot
                    previous = loaded
                else:
                    logger.error("Format de snapshot non reconnu : %s", compare_arg)
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("Snapshot de comparaison illisible (%s) : %s", compare_arg, exc)
        if previous is not None:
            print(compare_snapshots(previous, processes))

    # Mode --pid : rapport texte forensique détaillé du processus cible.
    if target_pid is not None:
        target = next(p for p in processes if p.pid == target_pid)
        print(render_pid_report(target, processes))

    # H19 : sortie par défaut réduite au seul graphe 3D interactif. PNG,
    # JSON, CSV et rapport restent opt-in (options CLI), jamais écrits sans
    # demande explicite.
    if getattr(args, "png", False):
        render_graph_png(graph, processes, args.output)
    if not args.no_html:
        render_interactive_3d(graph, processes, args.html_output)

    if args.json_export:
        export_data = [
            {
                "pid": p.pid,
                "ppid": p.ppid,
                "name": p.name,
                "username": p.username,
                "exe": p.exe,
                "cwd": p.cwd,
                "cmdline": p.cmdline,
                "cpu_percent": p.cpu_percent,
                "memory_percent": p.memory_percent,
                "open_files": p.open_files,
                "connections": p.connections,
                "enrichment": p.enrichment,
                "risk": p.risk,
                "collecte_incomplete": p.collecte_incomplete,
                "container": p.container,
                "exe_sha256": p.exe_sha256,
                "integrity_status": p.integrity_status,
            }
            for p in processes
        ]
        args.json_export.parent.mkdir(parents=True, exist_ok=True)
        args.json_export.write_text(json.dumps(export_data, indent=2, ensure_ascii=False))
        logger.info("Export JSON écrit : %s", args.json_export)

    if getattr(args, "csv_export", None):
        export_csv(processes, args.csv_export)

    if getattr(args, "csv_edges", None):
        export_csv_edges(graph, processes, args.csv_edges)

    if getattr(args, "report", None):
        stats = compute_summary_stats(processes, graph)
        meta = {
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "platform": platform.platform(),
            "model": None if args.no_enrich else args.model,
        }
        render_summary_report(stats, meta, args.report)

    logger.info("Terminé.")

    if wizard_mode:
        print()
        print("Résultat :")
        print(f"  Graphe 3D interactif : {args.html_output}")
        print()
        print("(Pour aussi obtenir un PNG, un export JSON/CSV ou un rapport de "
              "synthèse Markdown : relance avec --png / --json-export / --csv-export / --report, voir --help)")
        print()
        # H13 : le graphe 3D interactif est le livrable principal pour un
        # utilisateur novice -> c'est lui qu'on ouvre automatiquement (le
        # PNG et le JSON restent écrits sur disque, mais pas ouverts, pour
        # ne pas empiler une fenêtre visionneuse d'image en plus du
        # navigateur — l'utilisateur peut toujours ouvrir le PNG lui-même).
        if not args.no_html:
            print("Ouverture du graphe 3D interactif...")
            open_path_cross_platform(args.html_output)

    if wizard_mode or IS_FROZEN:
        _pause_before_exit()

    return 0


if __name__ == "__main__":
    try:
        _exit_code = main()
    except KeyboardInterrupt:
        print("\nInterrompu par l'utilisateur.")
        _exit_code = 130
    except Exception:
        # Filet de sécurité pour un exécutable PyInstaller --console : sans
        # ça, une exception non prévue ferme la fenêtre instantanément et un
        # novice ne voit jamais le message d'erreur.
        import traceback
        print("\n" + "=" * 56)
        print("Une erreur inattendue est survenue :")
        print("=" * 56)
        traceback.print_exc()
        if IS_FROZEN or len(sys.argv) == 1:
            _pause_before_exit()
        _exit_code = 1
    sys.exit(_exit_code)
