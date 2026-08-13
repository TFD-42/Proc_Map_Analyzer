#!/usr/bin/env python3
"""
process_graph_analyzer.py
==========================

Analyzes running system processes, their related files (executable,
cwd, open files) and the relationships between them (parent/child,
shared files), enriches each analyzed process via a local Ollama
model, then exports everything as a PNG graph.

Designed for a SINGLE run (one pass = one snapshot of the system).
For periodic monitoring, schedule this script via cron/launchd rather
than encoding a `while True: sleep(N)` loop into it:

    # cron (every 30 minutes):
    */30 * * * * /usr/bin/python3 /path/to/process_graph_analyzer.py \
        --output /var/log/process_graph/$(date +\%Y\%m\%d_\%H\%M).png

Assumptions made (no clarification provided by the user on these points):
  H1. Default Ollama model: "llama3.2" (--model to change it).
  H2. Default Ollama host: http://localhost:11434 (--ollama-host).
  H3. To avoid an excessively long run time, only the N processes with
      the highest consumption (CPU + RAM) are enriched by default
      (--enrich-limit, default 25). Use --enrich-all to enrich everything.
  H4. A "shared file" edge is only drawn if the file is open by >= 2
      processes, to limit visual noise (files opened by a single
      process remain in the data but are not drawn as separate nodes).
  H5. Risk levels expected from Ollama enrichment:
      "low" / "medium" / "high" / "unknown" (if the JSON returned by
      Ollama does not follow the requested schema, it falls back to
      "unknown" and logs a warning instead of crashing the script).
  H6. If psutil or access to certain processes is denied (permissions),
      the process is simply skipped (logged at DEBUG level), the
      script continues.
  H7. Network connections: at most 20 raw connections per process are
      collected (--max-conn-per-process), and at most 300 connection
      edges are drawn in total (--max-conn-total, sorted by the most
      active process) to keep the graph readable; the number of
      dropped connections is logged, never silently truncated.
      On macOS, listing the connections of a process that does not
      belong to the current user requires `sudo` — without it, those
      processes will simply show 0 visible connections (not an error).

Dependencies: psutil, networkx, matplotlib, requests
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
# Dependency check (explicit failure rather than a raw ImportError)
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
            "Missing dependencies: %s\nInstall with: pip install %s",
            ", ".join(missing),
            " ".join(missing),
        )
        sys.exit(1)


_check_dependencies()

import psutil  # noqa: E402
import networkx as nx  # noqa: E402
import requests  # noqa: E402
import matplotlib  # noqa: E402

matplotlib.use("Agg")  # headless rendering, no display needed
import matplotlib.pyplot as plt  # noqa: E402


# ---------------------------------------------------------------------------
# Data model
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
    connections: list = field(default_factory=list)  # see collect_connections()
    enrichment: Optional[dict] = None  # filled in by enrich_with_ollama()

    @property
    def score(self) -> float:
        """Simple score used to prioritize enrichment (H3)."""
        return self.cpu_percent + self.memory_percent


# ---------------------------------------------------------------------------
# 1. Process collection
# ---------------------------------------------------------------------------

def _addr_to_str(addr) -> Optional[str]:
    """Normalizes a psutil address (ip/port namedtuple, raw tuple, or a
    UNIX socket path as a str) into a readable string."""
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
    """Infers a readable protocol (tcp/udp/unix) from a psutil connection."""
    family = getattr(conn, "family", None)
    if family == getattr(socket, "AF_UNIX", object()):
        return "unix"
    if getattr(conn, "type", None) == socket.SOCK_DGRAM:
        return "udp"
    return "tcp"


def _collect_process_connections(p: "psutil.Process", limit: int) -> list[dict]:
    """Retrieves up to `limit` network/UNIX connections for a process (H7).

    Progressive fallback: `net_connections` (recent API) -> `connections`
    (historical alias) -> kind="all" -> kind="inet" if the platform does
    not support "all". Any permission error returns an empty list rather
    than crashing the collection.
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
        except Exception:  # defensive: a malformed record should not crash everything
            continue
    return connections


def collect_processes(min_score: float = 0.0, max_conn_per_process: int = 20) -> list[ProcessInfo]:
    """Lists accessible system processes and their related files.

    Processes whose access is denied (psutil.AccessDenied) or that
    disappeared between enumeration and reading (psutil.NoSuchProcess)
    are silently skipped (H6) — this is normal behavior, not a script
    error.
    """
    processes: list[ProcessInfo] = []

    # cpu_percent requires a first "priming" call per process to be
    # meaningful; we therefore do two passes with a short interval.
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
                # Common (permissions): continue without the open files.
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
            logger.debug("Inaccessible process skipped (pid=%s)", getattr(p, "pid", "?"))
            continue
        except Exception as exc:  # defensive: a single process should not crash the collection
            logger.debug("Unexpected error on a process, skipped: %s", exc)
            continue

    logger.info("Processes collected: %d", len(processes))
    return processes


def _safe(fn, default=None):
    try:
        return fn()
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError, RuntimeError):
        return default


# ---------------------------------------------------------------------------
# 2. Graph construction (parent/child + shared files, H4)
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

    # Parent -> child relations
    for p in processes:
        if p.ppid in pid_to_info and p.ppid != p.pid:
            graph.add_edge(f"proc:{p.ppid}", f"proc:{p.pid}", kind="parent_of")

    # Files shared between >= 2 processes (H4)
    file_to_pids: dict[str, list[int]] = {}
    for p in processes:
        for path in p.open_files:
            file_to_pids.setdefault(path, []).append(p.pid)

    shared_files = {path: pids for path, pids in file_to_pids.items() if len(pids) >= 2}
    logger.info("Files shared across multiple processes: %d", len(shared_files))

    for path, pids in shared_files.items():
        file_node = f"file:{path}"
        graph.add_node(file_node, kind="file", label=Path(path).name or path, full_path=path)
        for pid in pids:
            graph.add_edge(f"proc:{pid}", file_node, kind="opens")

    # Network connections, colored by protocol (H7). Multiple processes
    # connected to the same remote endpoint converge on the same node
    # (useful for spotting shared infrastructure: DNS, proxy, database...).
    # Priority given to the most active processes if max_conn_total is exceeded.
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
            "Network connections: %d shown, %d hidden (--max-conn-total=%d) to keep the graph readable.",
            len(kept), dropped, max_conn_total,
        )
    elif kept:
        logger.info("Network connections added to the graph: %d", len(kept))

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
# 3. Enrichment via local Ollama
# ---------------------------------------------------------------------------

ENRICHMENT_SCHEMA_PROMPT = """You are an educational systems analyst. Here is a process currently running:

Name: {name}
PID: {pid}
User: {username}
Executable: {exe}
Working directory: {cwd}
Command line: {cmdline}
CPU (%): {cpu}
Memory (%): {mem}
Number of open files: {n_files}
Number of network connections: {n_conn}

Reply ONLY with a strict JSON object (no text outside the JSON), in the exact format:
{{"category": "<short category, e.g. browser, system service, dev-tool, database, network, unknown>",
  "probable_role": "<a short sentence describing the probable role of THIS specific process>",
  "risk_level": "<low|medium|high|unknown>",
  "risk_justification": "<a short sentence>",
  "educational_explanation": "<2-3 sentences explaining to a non-expert, in general terms, what this type of process/program does in an operating system>"}}
"""


def _default_enrichment(reason: str) -> dict:
    return {
        "category": "unknown",
        "probable_role": "not enriched",
        "risk_level": "unknown",
        "risk_justification": reason,
        "educational_explanation": "",
    }


# Static fallback knowledge base for "Knowledge" mode: used when a process
# has not been enriched by Ollama (outside --enrich-limit, Ollama
# unavailable, etc.). Case-insensitive substring lookup on the process
# name — deliberately non-exhaustive, only covers the most common system
# processes (macOS/Linux).
KNOWLEDGE_BASE: dict[str, str] = {
    "kernel_task": "Special macOS kernel process: it does not actually consume the CPU/RAM shown, "
                    "it acts as a placeholder for the system's thermal and power management.",
    "launchd": "The very first process (PID 1) on macOS: starts and supervises all other "
               "system services and daemons.",
    "systemd": "The very first process (PID 1) on most modern Linux distributions: "
               "starts and supervises system services.",
    "windowserver": "macOS service responsible for rendering all windows and on-screen display.",
    "finder": "macOS's graphical file explorer.",
    "dock": "Manages the macOS Dock (icon bar).",
    "mds": "Metadata Server: indexes files for Spotlight search on macOS.",
    "mdworker": "Spotlight worker process that indexes file contents in the background.",
    "coreaudiod": "macOS's central audio daemon, manages system sound.",
    "cupsd": "Printing daemon (CUPS), manages print queues.",
    "sshd": "SSH server: accepts secure remote connections to this machine.",
    "bash": "Command interpreter (shell) — executes commands typed in a terminal.",
    "zsh": "Command interpreter (shell) — executes commands typed in a terminal.",
    "python": "Python language interpreter — runs a Python script or application.",
    "node": "Server-side JavaScript runtime — runs a Node.js application or tool.",
    "docker": "Containerization engine — runs isolated applications in containers.",
    "nginx": "Lightweight web server / reverse proxy, serves pages or redistributes HTTP traffic.",
    "chrome": "Google Chrome browser process (or one of its isolated tabs/extensions).",
    "safari": "Safari browser process (or one of its isolated tabs).",
    "code helper": "Visual Studio Code helper process (extension, integrated terminal, or rendering).",
    "ollama": "Local language model inference server — hosts and runs LLMs on this machine.",
}


def lookup_knowledge_base(process_name: str) -> str:
    name = (process_name or "").lower()
    for key, explanation in KNOWLEDGE_BASE.items():
        if key in name:
            return explanation
    return "No local information for this process. Without Ollama enrichment, its exact role is not documented here."


def call_ollama(
    prompt: str,
    model: str,
    host: str,
    timeout: float = 30.0,
) -> dict:
    """Calls the local Ollama API (/api/generate) and parses the expected JSON response.

    On failure (Ollama not running, timeout, invalid JSON), returns a
    fallback enrichment rather than raising an exception (H5/H6): a
    system analysis tool should not crash because a local LLM is
    unavailable.
    """
    url = f"{host.rstrip('/')}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False, "format": "json"}
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        raw_text = resp.json().get("response", "")
        parsed = json.loads(raw_text)
        # Minimal validation of the expected schema
        for key in ("category", "probable_role", "risk_level"):
            parsed.setdefault(key, "unknown")
        parsed.setdefault("educational_explanation", "")
        return parsed
    except requests.exceptions.ConnectionError:
        logger.warning("Ollama unreachable at %s — enrichment disabled for this process.", host)
        return _default_enrichment("ollama_unavailable")
    except requests.exceptions.Timeout:
        logger.warning("Ollama timeout (>%ss) for model %s.", timeout, model)
        return _default_enrichment("ollama_timeout")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Ollama response does not match the expected JSON: %s", exc)
        return _default_enrichment("invalid_json_response")
    except Exception as exc:  # defensive
        logger.warning("Unexpected error during Ollama call: %s", exc)
        return _default_enrichment(f"unexpected_error:{exc}")


def check_ollama_available(model: str, host: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Checks ONCE, before starting the enrichment loop, that Ollama is
    reachable and that the requested model actually exists locally.

    Without this guard, a misspelled model (e.g. "llama3:lattest"
    instead of "llama3:latest") produces the same 404 error repeated
    for EVERY enriched process — useless and noisy on large machines
    (hundreds of processes). We fail fast, once, with an actionable
    message (list of actually available models).
    """
    try:
        resp = requests.get(f"{host.rstrip('/')}/api/tags", timeout=timeout)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        return False, f"Ollama unreachable at {host} (is the server running? try: ollama serve)"
    except requests.exceptions.Timeout:
        return False, f"Ollama is not responding at {host} (timeout of {timeout}s)"
    except Exception as exc:  # defensive
        return False, f"Error querying Ollama at {host}: {exc}"

    try:
        available = [m.get("name", "") for m in resp.json().get("models", [])]
    except (ValueError, AttributeError):
        return False, "Unexpected response from Ollama on /api/tags (unrecognized format)."

    # Tolerant comparison: "llama3" should match a model installed as
    # "llama3:latest".
    model_base = model.split(":")[0]
    if any(name == model or name.split(":")[0] == model_base for name in available):
        return True, ""

    suggestion = (
        f" Available models: {', '.join(available)}" if available
        else " No models installed locally (try: ollama pull <model>)."
    )
    return False, f"Model '{model}' is not available on {host}.{suggestion}"


def enrich_processes(
    processes: list[ProcessInfo],
    model: str,
    host: str,
    enrich_limit: Optional[int],
    max_workers: int = 4,
    timeout: float = 30.0,
) -> None:
    """Enriches the most significant ProcessInfo entries in place (H3).

    Calls are parallelized (ThreadPoolExecutor) since they are blocking
    HTTP requests; max_workers stays modest by default so as not to
    saturate a local model that is already running on a single GPU/CPU.
    """
    ranked = sorted(processes, key=lambda p: p.score, reverse=True)
    targets = ranked if enrich_limit is None else ranked[:enrich_limit]

    if not targets:
        logger.info("No process to enrich.")
        return

    ok, message = check_ollama_available(model, host)
    if not ok:
        logger.error("Ollama enrichment canceled before starting: %s", message)
        for p in processes:
            p.enrichment = _default_enrichment("preflight_failed")
        return

    logger.info(
        "Ollama enrichment of %d/%d processes (model=%s, host=%s)...",
        len(targets), len(processes), model, host,
    )

    def _enrich_one(p: ProcessInfo) -> None:
        prompt = ENRICHMENT_SCHEMA_PROMPT.format(
            name=p.name,
            pid=p.pid,
            username=p.username or "unknown",
            exe=p.exe or "unknown",
            cwd=p.cwd or "unknown",
            cmdline=p.cmdline[:400],
            cpu=p.cpu_percent,
            mem=p.memory_percent,
            n_files=len(p.open_files),
            n_conn=len(p.connections),
        )
        p.enrichment = call_ollama(prompt, model=model, host=host, timeout=timeout)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(_enrich_one, targets))

    # Untargeted processes receive an explicit neutral enrichment, so
    # that the PNG rendering distinguishes "not analyzed" from
    # "analyzed, no risk".
    for p in processes:
        if p.enrichment is None:
            p.enrichment = _default_enrichment("enrichment_limit_exceeded")


# ---------------------------------------------------------------------------
# 4. PNG rendering
# ---------------------------------------------------------------------------

RISK_COLORS = {
    "low": "#4CAF50",
    "medium": "#FFC107",
    "high": "#F44336",
    "unknown": "#9E9E9E",
}

# Edge/connection colors by "kind" — network protocol for connections,
# relation type for parent/child and shared files.
# Validated with the dataviz skill's palette validator (dark mode,
# surface close to #05070d): the initial gray pair (#78909C/#607D8B)
# failed the "normal vision" distinction threshold (ΔE 6.7, below the
# floor of 15) — replaced with a slate-blue / taupe-brown pair that
# passes (ΔE 16.3) while remaining deliberately discreet (these are
# secondary "structural" links, not the main categorical channel).
PROTOCOL_COLORS = {
    "tcp": "#42A5F5",
    "udp": "#FFA726",
    "unix": "#AB47BC",
    "parent_of": "#5A6E82",
    "opens": "#A68A5B",
}
CONNECTION_NODE_COLOR = "#37474F"

# Categorical palette for "Type" mode (coloring by process category
# detected by Ollama). Fixed order validated by the dataviz skill
# (adjacent pairs, dark mode): CVD ΔE >= 8.4, normal vision >= 19.3,
# contrast >= 3:1 on all pairs. "unknown" deliberately stays outside the
# categorical palette (neutral gray) rather than inventing an extra hue
# for an "Other" — cf. the dataviz skill's rule.
CATEGORY_COLORS = {
    "browser": "#3987E5",
    "system service": "#D95926",
    "dev-tool": "#199E70",
    "database": "#C98500",
    "network": "#D55181",
}
CATEGORY_COLOR_UNKNOWN = "#9AA1B2"


def category_color(category: Optional[str]) -> str:
    return CATEGORY_COLORS.get((category or "").strip().lower(), CATEGORY_COLOR_UNKNOWN)


def render_graph_png(
    graph: nx.DiGraph,
    processes: list[ProcessInfo],
    output_path: Path,
    title: str = "Process graph, related files, network connections, and Ollama enrichment",
) -> None:
    if graph.number_of_nodes() == 0:
        logger.warning("Empty graph — no PNG generated.")
        return

    pid_to_info = {p.pid: p for p in processes}

    node_colors = []
    node_sizes = []
    labels = {}

    for node, data in graph.nodes(data=True):
        kind = data.get("kind")
        if kind == "process":
            info = pid_to_info.get(data["pid"])
            risk = "unknown"
            category = ""
            if info and info.enrichment:
                risk = info.enrichment.get("risk_level", "unknown")
                category = info.enrichment.get("category", "")
            node_colors.append(RISK_COLORS.get(risk, RISK_COLORS["unknown"]))
            node_sizes.append(300 + (data.get("cpu", 0) + data.get("mem", 0)) * 40)
            suffix = f"\n[{category}]" if category and category != "unknown" else ""
            labels[node] = f"{data['label']}\n(pid {data['pid']}){suffix}"
        elif kind == "connection":
            node_colors.append(PROTOCOL_COLORS.get(data.get("protocol"), CONNECTION_NODE_COLOR))
            node_sizes.append(90)
            labels[node] = data.get("label", node)
        else:  # shared file
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
        plt.Line2D([0], [0], marker="o", color="w", label=f"Risk {risk}",
                    markerfacecolor=color, markersize=10)
        for risk, color in RISK_COLORS.items()
    ]
    legend_handles.append(
        plt.Line2D([0], [0], marker="o", color="w", label="Shared file",
                    markerfacecolor="#607D8B", markersize=8)
    )
    legend_handles.append(
        plt.Line2D([0], [0], marker="o", color="w", label="Network connection",
                    markerfacecolor=CONNECTION_NODE_COLOR, markersize=8)
    )
    legend_handles += [
        plt.Line2D([0], [0], color=PROTOCOL_COLORS["parent_of"], lw=2, label="Parent → child link"),
        plt.Line2D([0], [0], color=PROTOCOL_COLORS["opens"], lw=2, label="Opens a shared file"),
        plt.Line2D([0], [0], color=PROTOCOL_COLORS["tcp"], lw=2, label="TCP connection"),
        plt.Line2D([0], [0], color=PROTOCOL_COLORS["udp"], lw=2, label="UDP connection"),
        plt.Line2D([0], [0], color=PROTOCOL_COLORS["unix"], lw=2, label="UNIX socket"),
    ]
    plt.legend(handles=legend_handles, loc="upper right", fontsize=8)
    plt.title(title, fontsize=14)
    plt.axis("off")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150)
    plt.close()
    logger.info("PNG graph written: %s", output_path)


# ---------------------------------------------------------------------------
# 5. Interactive 3D rendering (standalone HTML, clickable "solar system"
#    style nodes)
# ---------------------------------------------------------------------------
#
# Library: 3d-force-graph (three.js embedded), loaded from a CDN
# (unpkg) — cf. rule "External scripts can be imported from a CDN"; the
# file remains a single standalone .html (inline application CSS/JS), but
# requires a network connection to load the library on first display.

def build_graph_payload(graph: nx.DiGraph, processes: list[ProcessInfo]) -> dict:
    """Converts the networkx graph into a {nodes, links} structure directly
    consumable by 3d-force-graph (one JS object per node/edge)."""
    pid_to_info = {p.pid: p for p in processes}
    nodes = []

    for node, data in graph.nodes(data=True):
        kind = data.get("kind")
        if kind == "process":
            info = pid_to_info.get(data["pid"])
            risk = "unknown"
            category = "unknown"
            role = "not enriched"
            justification = ""
            explanation = ""
            if info and info.enrichment:
                risk = info.enrichment.get("risk_level", "unknown")
                category = info.enrichment.get("category", "unknown")
                role = info.enrichment.get("probable_role", "not enriched")
                justification = info.enrichment.get("risk_justification", "")
                explanation = info.enrichment.get("educational_explanation", "")
            # "Knowledge" mode: we prefer the Ollama explanation if the
            # process was actually enriched (non-empty explanation),
            # otherwise fall back to the static local knowledge base.
            enriched = bool(explanation)
            knowledge_text = explanation if enriched else lookup_knowledge_base(data["label"])
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
                "category": category,
                "probable_role": role,
                "risk_level": risk,
                "risk_justification": justification,
                "enriched": enriched,
                "knowledge_text": knowledge_text,
                "val": round(max(1.5, (cpu + mem) * 1.2 + 2), 2),
                "color": RISK_COLORS.get(risk, RISK_COLORS["unknown"]),
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
                    "tcp": "TCP connection: a reliable, ordered channel (web, SSH, databases...).",
                    "udp": "UDP connection: fast exchange with no delivery guarantee (DNS, streaming, gaming...).",
                    "unix": "UNIX socket: local communication channel between processes on the same machine.",
                }.get(protocol, ""),
                "val": 1.4,
                "color": PROTOCOL_COLORS.get(protocol, CONNECTION_NODE_COLOR),
            })
        else:  # shared file
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
<html lang="en">
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
      <button class="mode-btn active" data-mode="security">Security</button>
      <button class="mode-btn" data-mode="debug">Debug</button>
      <button class="mode-btn" data-mode="info_verbose">Verbose info</button>
      <button class="mode-btn" data-mode="knowledge">Knowledge</button>
    </div>
    <input id="search" type="text" placeholder="Search for an element..." />
    <div id="stats"></div>
  </div>

  <div id="legend">
    <h4>Process type</h4>
    <div class="legend-row" data-key="cat_browser"><span class="dot" style="background:#3987E5;color:#3987E5"></span>Browser</div>
    <div class="legend-row" data-key="cat_system_service"><span class="dot" style="background:#D95926;color:#D95926"></span>System service</div>
    <div class="legend-row" data-key="cat_dev-tool"><span class="dot" style="background:#199E70;color:#199E70"></span>Dev-tool</div>
    <div class="legend-row" data-key="cat_database"><span class="dot" style="background:#C98500;color:#C98500"></span>Database</div>
    <div class="legend-row" data-key="cat_network"><span class="dot" style="background:#D55181;color:#D55181"></span>Network</div>
    <div class="legend-row" data-key="cat_unknown"><span class="dot" style="background:#9AA1B2;color:#9AA1B2"></span>Unknown / uncategorized</div>
    <h4>Risk level</h4>
    <div class="legend-row" data-key="low"><span class="dot" style="background:#4CAF50;color:#4CAF50"></span>Low</div>
    <div class="legend-row" data-key="medium"><span class="dot" style="background:#FFC107;color:#FFC107"></span>Medium</div>
    <div class="legend-row" data-key="high"><span class="dot" style="background:#F44336;color:#F44336"></span>High</div>
    <div class="legend-row" data-key="unknown"><span class="dot" style="background:#9E9E9E;color:#9E9E9E"></span>Unknown</div>
    <h4>Network connections</h4>
    <div class="legend-row" data-key="proto_tcp"><span class="line-swatch" style="background:#42A5F5;color:#42A5F5"></span>TCP</div>
    <div class="legend-row" data-key="proto_udp"><span class="line-swatch" style="background:#FFA726;color:#FFA726"></span>UDP</div>
    <div class="legend-row" data-key="proto_unix"><span class="line-swatch" style="background:#AB47BC;color:#AB47BC"></span>UNIX</div>
    <div class="legend-row" data-key="file"><span class="dot" style="background:#607D8B;color:#607D8B"></span>Shared file</div>
  </div>

  <div id="panel">
    <button id="closePanel">✕</button>
    <div id="panelBody"></div>
  </div>

  <div id="cameraControls">
    <button id="zoomIn" title="Zoom in">+</button>
    <button id="zoomOut" title="Zoom out">–</button>
    <button id="recenter" title="Recenter (key R)">⟲</button>
  </div>

  <div id="hint">Click: select &nbsp;•&nbsp; drag: orbit &nbsp;•&nbsp; wheel: zoom &nbsp;•&nbsp; R: recenter</div>

  <div id="loadError" style="display:none; position:absolute; inset:0; z-index:10; background:var(--bg);
       align-items:center; justify-content:center; text-align:center; padding:40px;">
    <div style="max-width:420px;">
      <div style="font-size:15px; font-weight:600; margin-bottom:8px;">Unable to load the 3D library</div>
      <div style="font-size:13px; color:var(--muted); line-height:1.5;">
        This file needs an internet connection to load the
        <code>3d-force-graph</code> library from unpkg.com on first display.
        Check your connection then reload the page.
      </div>
    </div>
  </div>

  <script src="https://unpkg.com/3d-force-graph" onerror="document.getElementById('loadError').style.display='flex'"></script>
  <script>
    if (typeof ForceGraph3D === 'undefined') {
      document.getElementById('loadError').style.display = 'flex';
      throw new Error('3d-force-graph not loaded (no internet connection?)');
    }
    const GRAPH_DATA = __GRAPH_DATA_JSON__;
    const hiddenKeys = new Set();
    let currentMode = 'security';
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
      return { low: 'Low', medium: 'Medium', high: 'High', unknown: 'Unknown' }[r] || 'Unknown';
    }
    function riskColor(r) {
      return { low: '#4CAF50', medium: '#FFC107', high: '#F44336', unknown: '#9E9E9E' }[r] || '#9E9E9E';
    }

    // Categorical palette "Process type" — same values as
    // CATEGORY_COLORS on the Python side, validated via the dataviz skill.
    const CATEGORY_COLORS = {
      'browser': '#3987E5',
      'system service': '#D95926',
      'dev-tool': '#199E70',
      'database': '#C98500',
      'network': '#D55181',
    };
    const CATEGORY_COLOR_UNKNOWN = '#9AA1B2';
    function categoryColor(cat) {
      return CATEGORY_COLORS[(cat || '').trim().toLowerCase()] || CATEGORY_COLOR_UNKNOWN;
    }
    function categorySlug(cat) {
      const key = (cat || '').trim().toLowerCase();
      return CATEGORY_COLORS[key] ? key.replace(/\s+/g, '_') : 'unknown';
    }

    function escapeHtml(s) {
      return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    // Green -> red gradient based on CPU+RAM intensity, used in Debug mode.
    function heatColor(v) {
      const t = Math.max(0, Math.min(1, v / 60));
      const r = Math.round(76 + t * (244 - 76));
      const g = Math.round(175 - t * (175 - 67));
      const b = Math.round(80 - t * (80 - 54));
      return '#' + [r, g, b].map(x => x.toString(16).padStart(2, '0')).join('');
    }

    function modeNodeColor(n, mode) {
      if (mode === 'type' && n.type === 'process') return categoryColor(n.category);
      if (mode === 'debug' && n.type === 'process') return heatColor((n.cpu || 0) + (n.mem || 0));
      if (mode === 'knowledge' && n.type === 'process') return n.enriched ? '#FFD54F' : '#546E7A';
      return n.color;
    }

    function applyNodeColors() {
      const q = document.getElementById('search').value.trim().toLowerCase();
      if (!q) { Graph.nodeColor(n => modeNodeColor(n, currentMode)); return; }
      Graph.nodeColor(n => (n.name || '').toLowerCase().includes(q) ? '#ffffff' : (modeNodeColor(n, currentMode) + '33'));
    }

    // A node can be filtered from MULTIPLE legend sections at once (risk
    // AND type, for example) — so we return the full set of its keys, and
    // a node disappears if AT LEAST ONE is hidden.
    function nodeFilterKeys(node) {
      if (node.type === 'file') return ['file'];
      if (node.type === 'connection') return ['proto_' + node.protocol];
      return [node.risk_level || 'unknown', 'cat_' + categorySlug(node.category)];
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
      if (!conns || !conns.length) return '<div class="val">None</div>';
      return '<div class="conn-list">' + conns.map(c => `
        <div class="conn-row"><span class="proto-tag proto-${c.protocol}">${c.protocol.toUpperCase()}</span>
        ${escapeHtml(c.raddr || c.laddr || '?')}
        <span class="conn-status">${escapeHtml(c.status || '')}</span></div>
      `).join('') + '</div>';
    }

    function panelHeader(node) {
      if (node.type === 'file') return `<h3>${escapeHtml(node.name)}</h3><div class="sub">Shared file</div>`;
      if (node.type === 'connection') {
        return `<h3>${escapeHtml(node.name)}</h3><div class="sub">${node.protocol.toUpperCase()}${node.status ? ' · ' + escapeHtml(node.status) : ''}${node.is_remote ? ' · remote' : ' · local'}</div>`;
      }
      return `<h3>${escapeHtml(node.name)}</h3><div class="sub">PID ${node.pid}${node.ppid ? ' · parent ' + node.ppid : ''}${node.username ? ' · ' + escapeHtml(node.username) : ''}</div>`;
    }

    function renderSecurityPanel(node) {
      if (node.type === 'file') return panelHeader(node) + `<div class="field"><label>Path</label><div class="val">${escapeHtml(node.full_path || node.name)}</div></div>`;
      if (node.type === 'connection') {
        return panelHeader(node) + `<div class="field"><label>Nature</label><div class="val">${node.is_remote ? 'Connection to a remote host' : 'Local listen / connection'}</div></div>`;
      }
      const risk = node.risk_level || 'unknown';
      const conns = node.connections || [];
      const externalConns = conns.filter(c => (c.raddr || '') && !c.raddr.startsWith('127.') && !c.raddr.startsWith('::1') && !c.raddr.startsWith('0.0.0.0'));
      return panelHeader(node) + `
        <div class="field"><label>Risk level</label>
          <span class="risk-badge" style="background:${riskColor(risk)}22; color:${riskColor(risk)}; border:1px solid ${riskColor(risk)}">${riskLabel(risk)}</span>
        </div>
        <div class="field"><label>Justification</label><div class="val">${escapeHtml(node.risk_justification || '—')}</div></div>
        <div class="field"><label>Category</label><div class="val">${escapeHtml(node.category || 'unknown')}</div></div>
        <div class="field"><label>External connections</label><div class="val">${externalConns.length} out of ${node.n_connections || 0} total</div></div>
        ${externalConns.length ? fmtConnections(externalConns) : ''}
      `;
    }

    function renderDebugPanel(node) {
      if (node.type === 'file') return panelHeader(node) + `<div class="field"><label>Full path</label><div class="val">${escapeHtml(node.full_path || node.name)}</div></div>`;
      if (node.type === 'connection') return panelHeader(node) + `<div class="field"><label>Internal ID</label><div class="val">${escapeHtml(node.id)}</div></div>`;
      return panelHeader(node) + `
        <div class="field"><label>PID / PPID</label><div class="val">${node.pid} / ${node.ppid ?? '—'}</div></div>
        <div class="field"><label>User</label><div class="val">${escapeHtml(node.username || '—')}</div></div>
        <div class="field"><label>CPU / RAM</label><div class="val">${node.cpu}% · ${node.mem}%</div></div>
        <div class="field"><label>Executable</label><div class="val">${escapeHtml(node.exe || '—')}</div></div>
        <div class="field"><label>Working directory</label><div class="val">${escapeHtml(node.cwd || '—')}</div></div>
        <div class="field"><label>Full command</label><div class="val">${escapeHtml(node.cmdline || '—')}</div></div>
        <div class="field"><label>Open files</label><div class="val">${node.n_open_files ?? 0}</div></div>
        <div class="field"><label>Connections (${node.n_connections ?? 0})</label>${fmtConnections(node.connections)}</div>
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
      const text = node.knowledge_text || "No explanation available for this element.";
      let badge = '';
      if (node.type === 'process') {
        const c = node.enriched ? '#FFD54F' : '#90A4AE';
        badge = `<div class="field"><span class="risk-badge" style="background:${c}22; color:${c}; border:1px solid ${c}">${node.enriched ? 'Analyzed by Ollama' : 'Local knowledge base'}</span></div>`;
      }
      return panelHeader(node) + badge + `
        <div class="field"><label>Explanation</label><div class="val">${escapeHtml(text)}</div></div>
        ${node.type === 'process' && node.probable_role ? `<div class="field"><label>Probable role of this specific process</label><div class="val">${escapeHtml(node.probable_role)}</div></div>` : ''}
      `;
    }

    function renderTypePanel(node) {
      if (node.type === 'file') return panelHeader(node) + `<div class="field"><label>Path</label><div class="val">${escapeHtml(node.full_path || node.name)}</div></div>`;
      if (node.type === 'connection') return panelHeader(node) + `<div class="field"><label>Protocol</label><div class="val">${node.protocol.toUpperCase()}</div></div>`;
      const cat = node.category || 'unknown';
      const color = categoryColor(cat);
      return panelHeader(node) + `
        <div class="field"><span class="risk-badge" style="background:${color}22; color:${color}; border:1px solid ${color}">${escapeHtml(cat)}</span></div>
        <div class="field"><label>Probable role</label><div class="val">${escapeHtml(node.probable_role || 'not enriched')}</div></div>
        <div class="field"><label>CPU / RAM</label><div class="val">${node.cpu}% · ${node.mem}%</div></div>
      `;
    }

    const PANEL_RENDERERS = {
      type: renderTypePanel,
      security: renderSecurityPanel,
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

    statsEl.textContent = `${GRAPH_DATA.nodes.length} nodes · ${GRAPH_DATA.links.length} relations`;

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

    // Camera controls: zoom in/out move the camera along the origin ->
    // camera axis; recenter uses zoomToFit (native to 3d-force-graph) to
    // frame the entire visible graph.
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
    title: str = "Interactive 3D process graph (Ollama-enriched)",
) -> None:
    """Generates a standalone HTML file with an interactive 3D "solar
    system" style graph (3d-force-graph / three.js): clickable nodes,
    mouse zoom/orbit, detail panel, risk-level filters, search.

    Requires a network connection when the file is opened (the
    3d-force-graph library is loaded from unpkg.com, cf. the CDN rule
    for external scripts in HTML artifacts). No data is sent
    externally: only the JS script load is a network call.
    """
    if graph.number_of_nodes() == 0:
        logger.warning("Empty graph — no interactive HTML generated.")
        return

    payload = build_graph_payload(graph, processes)
    # Escaping "</" -> "<\/": a cmdline literally containing "</script>"
    # must not be able to break the enclosing <script> tag.
    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = _HTML_TEMPLATE.replace("__TITLE__", title).replace(
        "__GRAPH_DATA_JSON__", payload_json
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info("Interactive 3D graph written: %s", output_path)


# ---------------------------------------------------------------------------
# 6. Orchestration / CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyzes system processes, their related files and their relationships, "
                    "enriches them via local Ollama, exports a PNG graph."
    )
    parser.add_argument("--output", type=Path, default=Path("process_graph.png"),
                         help="Path to the output PNG (default: process_graph.png)")
    parser.add_argument("--html-output", type=Path, default=Path("process_graph_3d.html"),
                         help="Path to the interactive 3D HTML (default: process_graph_3d.html)")
    parser.add_argument("--no-html", action="store_true",
                         help="Disables generation of the interactive 3D graph")
    parser.add_argument("--no-png", action="store_true",
                         help="Disables generation of the static PNG")
    parser.add_argument("--model", default="llama3.2",
                         help="Ollama model to use (default: llama3.2)")
    parser.add_argument("--ollama-host", default="http://localhost:11434",
                         help="Ollama API URL (default: http://localhost:11434)")
    parser.add_argument("--enrich-limit", type=int, default=25,
                         help="Max number of processes enriched via Ollama, "
                              "sorted by CPU+RAM consumption (default: 25)")
    parser.add_argument("--enrich-all", action="store_true",
                         help="Enriches all collected processes (ignores --enrich-limit)")
    parser.add_argument("--no-enrich", action="store_true",
                         help="Completely disables the call to Ollama")
    parser.add_argument("--min-score", type=float, default=0.0,
                         help="Minimum score (cpu%%+mem%%) to include a process (default: 0)")
    parser.add_argument("--max-conn-per-process", type=int, default=20,
                         help="Max raw network connections collected per process (default: 20)")
    parser.add_argument("--max-conn-total", type=int, default=300,
                         help="Max connection edges drawn in total (default: 300)")
    parser.add_argument("--max-workers", type=int, default=4,
                         help="Parallelism of Ollama calls (default: 4)")
    parser.add_argument("--timeout", type=float, default=30.0,
                         help="Timeout per Ollama call in seconds (default: 30)")
    parser.add_argument("--json-export", type=Path, default=None,
                         help="Also exports the collected/enriched data as JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="DEBUG logs")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    logger.info("Collecting system processes...")
    processes = collect_processes(min_score=args.min_score, max_conn_per_process=args.max_conn_per_process)
    if not processes:
        logger.error("No processes collected (insufficient permissions?). Stopping.")
        return 1

    logger.info("Building the relationship graph...")
    graph = build_graph(processes, max_conn_total=args.max_conn_total)
    logger.info("Graph: %d nodes, %d edges", graph.number_of_nodes(), graph.number_of_edges())

    if args.no_enrich:
        logger.info("Ollama enrichment disabled (--no-enrich).")
        for p in processes:
            p.enrichment = _default_enrichment("enrichment_disabled")
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
        logger.info("JSON export written: %s", args.json_export)

    logger.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
