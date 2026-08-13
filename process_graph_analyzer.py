#!/usr/bin/env python3
"""
process_graph_analyzer.py
==========================

Analyse les processus système en cours d'exécution, leurs fichiers liés
(exécutable, cwd, fichiers ouverts) et les relations entre eux
(parent/enfant, fichiers partagés), enrichit chaque processus analysé via
un modèle Ollama local, puis exporte le tout sous forme de graphe PNG.

Conçu pour une exécution UNIQUE (une passe = un instantané du système).
Pour un suivi périodique, planifier ce script via cron/launchd plutôt que
d'y encoder une boucle `while True: sleep(N)` :

    # cron (toutes les 30 minutes) :
    */30 * * * * /usr/bin/python3 /chemin/vers/process_graph_analyzer.py \
        --output /var/log/process_graph/$(date +\%Y\%m\%d_\%H\%M).png

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

Dépendances : psutil, networkx, matplotlib, requests
    pip install psutil networkx matplotlib requests
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import socket
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("process_graph_analyzer")


# ---------------------------------------------------------------------------
# Vérification des dépendances (échec explicite plutôt qu'un ImportError brut)
# ---------------------------------------------------------------------------

def _check_dependencies() -> None:
    missing = []
    for module_name, pip_name in (
        ("psutil", "psutil"),
        ("networkx", "networkx"),
        ("matplotlib", "matplotlib"),
        ("requests", "requests"),
    ):
        try:
            __import__(module_name)
        except ImportError:
            missing.append(pip_name)
    if missing:
        logger.error(
            "Dépendances manquantes : %s\nInstaller avec : pip install %s",
            ", ".join(missing),
            " ".join(missing),
        )
        sys.exit(1)


_check_dependencies()

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


def _collect_process_connections(p: "psutil.Process", limit: int) -> list[dict]:
    """Récupère jusqu'à `limit` connexions réseau/UNIX d'un processus (H7).

    Repli progressif : `net_connections` (API récente) -> `connections`
    (alias historique) -> kind="all" -> kind="inet" si la plateforme ne
    supporte pas "all". Toute erreur de permission retourne une liste vide
    plutôt que de faire planter la collecte.
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
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
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
            with p.oneshot():
                pid = p.pid
                ppid = p.ppid()
                name = p.name()
                username = _safe(p.username)
                exe = _safe(p.exe)
                cwd = _safe(p.cwd)
                cmdline = " ".join(_safe(p.cmdline, default=[]) or []) or name
                cpu_percent = p.cpu_percent(None)
                memory_percent = round(p.memory_percent(), 3)

            open_files = []
            try:
                open_files = [f.path for f in p.open_files()]
            except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
                # Fréquent (permissions) : on continue sans les fichiers ouverts.
                pass

            connections = _collect_process_connections(p, limit=max_conn_per_process)

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


def _safe(fn, default=None):
    try:
        return fn()
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError, RuntimeError):
        return default


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
    timeout: float = 30.0,
) -> dict:
    """Appelle l'API Ollama locale (/api/generate) et parse la réponse JSON attendue.

    En cas d'échec (Ollama non lancé, timeout, JSON invalide), retourne un
    enrichissement de repli plutôt que de lever une exception (H5/H6) : un
    outil d'analyse système ne doit pas planter parce qu'un LLM local est
    indisponible.
    """
    url = f"{host.rstrip('/')}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False, "format": "json"}
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


def enrich_processes(
    processes: list[ProcessInfo],
    model: str,
    host: str,
    enrich_limit: Optional[int],
    max_workers: int = 4,
    timeout: float = 30.0,
) -> None:
    """Enrichit en place les ProcessInfo les plus significatifs (H3).

    Les appels sont parallélisés (ThreadPoolExecutor) car ce sont des
    requêtes HTTP bloquantes ; max_workers reste modeste par défaut pour ne
    pas saturer un modèle local qui tourne déjà sur un seul GPU/CPU.
    """
    ranked = sorted(processes, key=lambda p: p.score, reverse=True)
    targets = ranked if enrich_limit is None else ranked[:enrich_limit]

    if not targets:
        logger.info("Aucun processus à enrichir.")
        return

    ok, message = check_ollama_available(model, host)
    if not ok:
        logger.error("Enrichissement Ollama annulé avant de démarrer : %s", message)
        for p in processes:
            p.enrichment = _default_enrichment("preflight_echec")
        return

    logger.info(
        "Enrichissement Ollama de %d/%d processus (modèle=%s, host=%s)...",
        len(targets), len(processes), model, host,
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(_enrich_one, targets))

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
            if info and info.enrichment:
                risk = info.enrichment.get("niveau_risque", "inconnu")
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
            risk = "inconnu"
            categorie = "inconnu"
            role = "non enrichi"
            justification = ""
            explication = ""
            if info and info.enrichment:
                risk = info.enrichment.get("niveau_risque", "inconnu")
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
                "justification_risque": justification,
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
  </div>

  <div id="panel">
    <button id="closePanel">✕</button>
    <div id="panelBody"></div>
  </div>

  <div id="cameraControls">
    <button id="zoomIn" title="Zoom avant">+</button>
    <button id="zoomOut" title="Zoom arrière">–</button>
    <button id="recenter" title="Recentrer (touche R)">⟲</button>
  </div>

  <div id="hint">Clic : sélectionner &nbsp;•&nbsp; glisser : orbiter &nbsp;•&nbsp; molette : zoomer &nbsp;•&nbsp; R : recentrer</div>

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
    const hiddenKeys = new Set();
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
      return [node.niveau_risque || 'inconnu', 'cat_' + categorySlug(node.categorie)];
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
      return `<h3>${escapeHtml(node.name)}</h3><div class="sub">PID ${node.pid}${node.ppid ? ' · parent ' + node.ppid : ''}${node.username ? ' · ' + escapeHtml(node.username) : ''}</div>`;
    }

    function renderSecurityPanel(node) {
      if (node.type === 'file') return panelHeader(node) + `<div class="field"><label>Chemin</label><div class="val">${escapeHtml(node.full_path || node.name)}</div></div>`;
      if (node.type === 'connection') {
        return panelHeader(node) + `<div class="field"><label>Nature</label><div class="val">${node.is_remote ? 'Connexion vers un hôte distant' : 'Écoute / connexion locale'}</div></div>`;
      }
      const risk = node.niveau_risque || 'inconnu';
      const conns = node.connections || [];
      const externalConns = conns.filter(c => (c.raddr || '') && !c.raddr.startsWith('127.') && !c.raddr.startsWith('::1') && !c.raddr.startsWith('0.0.0.0'));
      return panelHeader(node) + `
        <div class="field"><label>Niveau de risque</label>
          <span class="risk-badge" style="background:${riskColor(risk)}22; color:${riskColor(risk)}; border:1px solid ${riskColor(risk)}">${riskLabel(risk)}</span>
        </div>
        <div class="field"><label>Justification</label><div class="val">${escapeHtml(node.justification_risque || '—')}</div></div>
        <div class="field"><label>Catégorie</label><div class="val">${escapeHtml(node.categorie || 'inconnu')}</div></div>
        <div class="field"><label>Connexions externes</label><div class="val">${externalConns.length} sur ${node.n_connections || 0} au total</div></div>
        ${externalConns.length ? fmtConnections(externalConns) : ''}
      `;
    }

    function renderDebugPanel(node) {
      if (node.type === 'file') return panelHeader(node) + `<div class="field"><label>Chemin complet</label><div class="val">${escapeHtml(node.full_path || node.name)}</div></div>`;
      if (node.type === 'connection') return panelHeader(node) + `<div class="field"><label>ID interne</label><div class="val">${escapeHtml(node.id)}</div></div>`;
      return panelHeader(node) + `
        <div class="field"><label>PID / PPID</label><div class="val">${node.pid} / ${node.ppid ?? '—'}</div></div>
        <div class="field"><label>Utilisateur</label><div class="val">${escapeHtml(node.username || '—')}</div></div>
        <div class="field"><label>CPU / RAM</label><div class="val">${node.cpu}% · ${node.mem}%</div></div>
        <div class="field"><label>Exécutable</label><div class="val">${escapeHtml(node.exe || '—')}</div></div>
        <div class="field"><label>Répertoire de travail</label><div class="val">${escapeHtml(node.cwd || '—')}</div></div>
        <div class="field"><label>Commande complète</label><div class="val">${escapeHtml(node.cmdline || '—')}</div></div>
        <div class="field"><label>Fichiers ouverts</label><div class="val">${node.n_open_files ?? 0}</div></div>
        <div class="field"><label>Connexions (${node.n_connections ?? 0})</label>${fmtConnections(node.connections)}</div>
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

    statsEl.textContent = `${GRAPH_DATA.nodes.length} nœuds · ${GRAPH_DATA.links.length} relations`;

    document.querySelectorAll('.legend-row').forEach(row => {
      row.addEventListener('click', () => {
        const key = row.dataset.key;
        if (hiddenKeys.has(key)) hiddenKeys.delete(key); else hiddenKeys.add(key);
        row.classList.toggle('disabled', hiddenKeys.has(key));
        Graph.graphData(currentGraphData());
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
    document.addEventListener('keydown', (e) => {
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
# 6. Orchestration / CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyse les processus système, leurs fichiers liés et leurs relations, "
                    "enrichit via Ollama local, exporte un graphe PNG."
    )
    parser.add_argument("--output", type=Path, default=Path("process_graph.png"),
                         help="Chemin du PNG de sortie (défaut: process_graph.png)")
    parser.add_argument("--html-output", type=Path, default=Path("process_graph_3d.html"),
                         help="Chemin du HTML 3D interactif (défaut: process_graph_3d.html)")
    parser.add_argument("--no-html", action="store_true",
                         help="Désactive la génération du graphe 3D interactif")
    parser.add_argument("--no-png", action="store_true",
                         help="Désactive la génération du PNG statique")
    parser.add_argument("--model", default="llama3.2",
                         help="Modèle Ollama à utiliser (défaut: llama3.2)")
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
    parser.add_argument("--max-conn-per-process", type=int, default=20,
                         help="Connexions réseau brutes max collectées par processus (défaut: 20)")
    parser.add_argument("--max-conn-total", type=int, default=300,
                         help="Arêtes de connexion max dessinées au total (défaut: 300)")
    parser.add_argument("--max-workers", type=int, default=4,
                         help="Parallélisme des appels Ollama (défaut: 4)")
    parser.add_argument("--timeout", type=float, default=30.0,
                         help="Timeout par appel Ollama en secondes (défaut: 30)")
    parser.add_argument("--json-export", type=Path, default=None,
                         help="Exporte aussi les données collectées/enrichies en JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="Logs DEBUG")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    logger.info("Collecte des processus système...")
    processes = collect_processes(min_score=args.min_score, max_conn_per_process=args.max_conn_per_process)
    if not processes:
        logger.error("Aucun processus collecté (permissions insuffisantes ?). Arrêt.")
        return 1

    logger.info("Construction du graphe de relations...")
    graph = build_graph(processes, max_conn_total=args.max_conn_total)
    logger.info("Graphe : %d nœuds, %d arêtes", graph.number_of_nodes(), graph.number_of_edges())

    if args.no_enrich:
        logger.info("Enrichissement Ollama désactivé (--no-enrich).")
        for p in processes:
            p.enrichment = _default_enrichment("enrichissement_desactive")
    else:
        limit = None if args.enrich_all else args.enrich_limit
        enrich_processes(
            processes,
            model=args.model,
            host=args.ollama_host,
            enrich_limit=limit,
            max_workers=args.max_workers,
            timeout=args.timeout,
        )

    if not args.no_png:
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
            }
            for p in processes
        ]
        args.json_export.parent.mkdir(parents=True, exist_ok=True)
        args.json_export.write_text(json.dumps(export_data, indent=2, ensure_ascii=False))
        logger.info("Export JSON écrit : %s", args.json_export)

    logger.info("Terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
