#!/usr/bin/env python3
"""
process_analyzer_allinone.py
================================

ALL-IN-ONE version, designed for a novice user and to be packaged with
PyInstaller (--onefile --console). Merges into a single file: the analysis
of system processes, their related files (executable, cwd, open files) and
their relationships (parent/child, shared files, network connections),
enrichment via a local Ollama model, static PNG rendering + interactive 3D
HTML, AND an interactive assistant ("wizard") that replaces the separate
.command launcher.

Cross-platform: Windows / macOS / Linux (via psutil, compilable into a
PyInstaller executable) AND Android/Termux (via a lightweight fallback
based on /proc, since psutil cannot be installed on Android — see
H14/H15/H16). On Termux, NO compilation is possible (PyInstaller does not
target Android): run `python process_analyzer_allinone.py` directly after
`pkg install python`.

Two execution modes:
  - Double-click / launch WITHOUT arguments -> interactive assistant (2
    questions: max number of processes, choice of the detected Ollama
    model), then automatic opening of the results and a pause before the
    window closes (useful for a PyInstaller .exe in console mode).
  - Launch WITH arguments -> classic CLI behavior (see --help), for
    advanced/scripted/cron usage, unchanged compared to the old
    process_graph_analyzer.py.

Building the executable (PyInstaller must be installed, IN THE SAME
environment/venv as psutil/networkx/matplotlib/requests, otherwise
PyInstaller cannot see them to embed them:
pip install pyinstaller):

    pyinstaller --onefile --console --name ProcessAnalyzer \
        --collect-all psutil \
        --collect-submodules matplotlib \
        process_analyzer_allinone.py

  --console is required: the interactive assistant and the pause before
  closing need a visible console.
  --collect-all psutil is required: psutil embeds an OS-specific compiled
  extension (_psutil_osx / _psutil_linux / _psutil_windows) that
  PyInstaller's static analysis does not always detect automatically
  (observed in practice on macOS: the executable launches but fails
  immediately with "missing module: psutil");
  --collect-all forces the inclusion of this binary extension.
  --collect-submodules matplotlib: PyInstaller does not always
  automatically detect all matplotlib submodules (backends, etc.).
  If ANOTHER module reports a "missing" error at runtime despite this
  command, the most frequent cause is that this module was not installed
  in the Python environment used to RUN pyinstaller (check with
  `pip show <module>` in that same environment before recompiling) —
  PyInstaller can only embed what it sees installed locally at build
  time, not what _check_dependencies() would install when running a raw
  .py file.

Design hypotheses (no details were provided by the user on these points):
  H1. Default Ollama model: "llama3.2" (--model to change it).
  H2. Default Ollama host: http://localhost:11434 (--ollama-host).
  H3. To avoid an overly long execution time, only the N most
      resource-consuming processes (CPU + RAM) are enriched by default
      (--enrich-limit, default 25). Use --enrich-all to enrich everything.
  H4. A "shared file" edge is only drawn if the file is open in >= 2
      processes, to limit visual noise (files opened by a single process
      remain in the data but are not drawn as separate nodes).
  H5. Risk levels expected from the Ollama enrichment:
      "low" / "medium" / "high" / "unknown" (if the JSON returned by
      Ollama does not follow the requested schema, we fall back to
      "unknown" and log a warning instead of crashing the script).
  H6. If psutil or access to certain processes is denied (permissions),
      the process is simply ignored (logged at DEBUG level), the script
      continues.
  H7. Network connections: at most 20 raw connections per process are
      collected (--max-conn-per-process), and at most 300 connection
      edges in total are drawn (--max-conn-total, sorted by most active
      process) to keep the graph readable; the number of ignored
      connections is logged, never silently truncated.
      On macOS, listing the connections of a process that does not belong
      to the current user requires `sudo` — without it, those processes
      will simply show 0 visible connections (not an error).
  H8. Interactive assistant: default of 150 max processes included in the
      graph (the most CPU+RAM active ones first, --max-processes in CLI
      to change/disable). The number of AI-enriched processes is derived
      automatically (min(max_processes, 40)) rather than asking a 3rd
      question.
  H9. Auto-installation of missing dependencies (pip) ONLY when the
      script runs as a raw .py (sys.frozen absent). In a frozen
      PyInstaller executable, a missing dependency is a build bug: we
      fail with a clear message rather than attempting an installation
      that makes no sense in that context (no guaranteed pip/network on
      the target machine).
  H10. Detection of Ollama models via the HTTP API (GET /api/tags) rather
      than via the `ollama list` command, so as not to depend on the
      `ollama` binary being on the PATH — only the Ollama SERVER must be
      reachable, which remains valid from a packaged .exe.
  H11. Default Ollama timeout: 120s (--timeout), default parallelism: 2
      (--max-workers). A local LLM most often serves generation requests
      sequentially (a single GPU/CPU); heavy parallelization only stacks
      requests in a queue without speeding anything up, and makes them
      all time out together (observed: bursts of timeouts at exactly
      30.0s with the old default --max-workers=4/--timeout=30). A
      "warm-up" call is also performed once before the loop to load the
      model into memory (can take up to a minute for a multi-GB model)
      without consuming the time budget of an enriched process; and the
      length of each generated response is capped (num_predict=220) to
      bound the worst-case latency per call.
  H12. If Ollama is not detected AT ALL on the machine, the assistant
      offers an automatic installation suited to the OS (Homebrew on
      macOS, official script on Linux, .exe installer on Windows) —
      ONLY with the user's explicit consent (never silently, since it
      installs third-party software). If Ollama is running but no model
      is installed, the assistant then offers to download the default
      model (llama3:latest, several GB, see DEFAULT_OLLAMA_MODEL) via
      the HTTP API (POST /api/pull) with a progress bar. Declining
      either offer simply disables AI enrichment, never a fatal failure.
  H13. In the novice assistant, only the interactive 3D graph (HTML) is
      opened automatically at the end — it is the main deliverable. The
      PNG and JSON are still written to disk but are not opened
      automatically (avoids stacking an image viewer on top of the
      browser).
  H14. On Android/Termux (detected via ANDROID_ROOT/ANDROID_DATA/PREFIX
      containing "com.termux", or the presence of /system/build.prop),
      psutil is replaced by a homemade backend that directly reads
      /proc/<pid>/* (same principle as psutil's internal implementation
      on Linux). Without root, Android natively restricts visibility to
      the current user's processes (SELinux / hidepid) — other processes
      simply appear invisible or access-denied, exactly as psutil would
      already behave in the same situation on a classic Linux: this is
      not a bug of this script but an OS restriction.
  H15. The CPU% returned by the /proc backend is an AVERAGE since the
      process started (cumulative CPU time / process age), not an
      instantaneous delta like psutil (which requires two samples spaced
      in time). Sufficient to sort/prioritize processes (the only use
      this script makes of it), not for precise real-time monitoring —
      assumed and documented rather than disguised as a measurement
      equivalent to psutil.
  H16. The /proc backend only decodes IPv4 TCP/UDP connections and UNIX
      sockets (via /proc/net/tcp, /proc/net/udp, /proc/net/unix
      cross-referenced with the inodes of /proc/<pid>/fd/*); IPv6
      connections are not decoded (limitation accepted to stay simple,
      IPv4 remains largely dominant for this use case).
  H17. The displayed risk level ("final_level") is NO LONGER produced
      solely by Ollama. A deterministic rule engine
      (compute_rule_based_risk) first computes a level ("rules_level")
      from observable signals (executable outside standard directories,
      launched from a temporary directory, executable gone from disk,
      listening on all interfaces, empty cmdline, unusual volume of
      external connections). The Ollama opinion ("ai_level"), if it
      exists, is combined by ESCALATION ONLY: final_level = the higher
      of the two, never the lower — underestimating a risk is judged
      worse than overestimating it. A divergence between the two
      opinions is traced explicitly rather than hidden.
  H18. In the 3D graph, a process is marked "low interest"
      (low_interest, hidden by default, togglable) if the following
      three conditions are all met: graph degree <= 1 (no or a single
      relation), cpu+mem < 1.0, AND final_level == "low". Thresholds
      chosen to hide only visibly inactive processes and never a risky
      process, whatever its activity.
  H19. Default output reduced to the interactive 3D graph (HTML) ONLY:
      no PNG, JSON, CSV, or Markdown report is written unless the user
      explicitly requests them (--png, --json-export, --csv-export,
      --report). The novice assistant therefore only asks one implicit
      output question (where to write the HTML) and opens that file
      directly — the report remains a simple Markdown (no extra
      dependency) when requested via CLI.
  H20. 3D HTML camera controls: in addition to the on-screen buttons and
      the R key alone (recenter), Ctrl+R also recenters (and blocks the
      browser's page reload), Ctrl++ / Ctrl+= zooms in, Ctrl+- zooms out
      (and blocks the native browser zoom) — keyboard shortcuts
      explicitly requested in addition to the buttons.
  H21. Container detection via /proc/<pid>/cgroup (Docker, Podman,
      containerd, Kubernetes) — Linux only, silently absent elsewhere.
      Container id shortened to 12 characters like docker ps.
  H22. --check-integrity: SHA256 of each executable, compared to a JSON
      reference database (--integrity-db). A MODIFIED fingerprint is a
      "high" signal and NEVER overwrites the reference (delete the
      database to start from scratch after a legitimate update). Files
      > 200 MB are not hashed.
  H23. --config: whitelist/blacklist (simple hand-parsed YAML OR JSON,
      no pyyaml dependency). fnmatch patterns OR substring, compared to
      the name + exe + cmdline. Whitelist = only neutralizes PATH
      signals (never network/deleted); blacklist = immediate "high".
  H24. --baseline: rolling mean/variance (Welford's algorithm) of
      CPU/RAM per process NAME in a JSON. Anomaly reported (level
      "medium") if value > mean + 2 standard deviations, with at least 3
      samples, a standard deviation > 0.05 and a value >= 5% (avoids
      noise from nearly idle processes).
  H25. --retry-failed N: only transient failure reasons (timeout, Ollama
      unreachable/saturated, invalid JSON) are retried, SERIALLY with
      exponential backoff 1s/2s/4s (re-parallelizing a saturated server
      would make the problem worse).
  H26. --cache: SQLite cache of enrichments, key =
      SHA256(name+exe+cmdline), TTL 7 days (--cache-ttl-days). Failures
      are never cached; results served from the cache are marked
      from_cache to remain distinguishable.
  H27. --plugin: USER Python module loaded explicitly, exposing
      enrich(process_info: dict) -> dict, result merged under
      enrichment["plugin"]. Plugin errors are logged, never fatal.
  H28. --csv-edges: export of the graph EDGES (source, target, kind,
      labels, risk levels of both endpoints) for Gephi/Neo4j.
  H29. Automatic run history (outputs/history.json, 50 lightweight
      snapshots max, disabled by --no-history, never fed in --sandbox
      mode). --compare without a value = compare to the previous run;
      --compare <file> accepts a --json-export export or a history
      snapshot.
  H30. --pid: analysis restricted to the subtree (ancestors +
      descendants) of the target process + detailed forensic text report
      on stdout; the HTML is still generated, limited to that subtree.
  H31. --sandbox: replays a JSON file in --json-export format instead of
      collecting the system (test rules/config/rendering risk-free).
  H32. --watch: collection + rules + HTML rendering loop every
      --interval seconds (minimum 5s), differences displayed between
      cycles. NEVER an Ollama call in the loop (AI enrichment remains an
      explicit one-shot act); Ctrl+C stops cleanly.
  H33. --preload-model: starts/installs Ollama if necessary, downloads
      the requested model then exits without any analysis (offline
      preparation).
  H34. HTML: "copy" buttons (PID, executable, command, kill <pid>,
      SHA256) with an execCommand fallback when navigator.clipboard is
      absent (file://); shortcuts Escape (close the panel / leave the
      search), / (search), 1-5 (switch mode).
  H35. Default Ollama model ADAPTED TO THE MACHINE, same policy in
      install.sh, install.ps1 and this script: mini "llama3.2:1b"
      (~1.3 GB) on Android/Termux (limited RAM/storage), medium
      "llama3:latest" (~4.7 GB) on macOS/Windows/Linux — applied to the
      default of --model (llama3.2:1b vs llama3.2) and to the download
      offered by the assistant (DEFAULT_OLLAMA_MODEL). On Termux, Ollama
      is installed via the Termux repository package (pkg install
      ollama), never via the ollama.com script (incompatible with
      Android) — clean degradation to "no AI" if the package is
      unavailable.

Dependencies: networkx, matplotlib, requests, and psutil EVERYWHERE
EXCEPT on Android/Termux (where it is replaced by the /proc fallback
described above):
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

logger = logging.getLogger("process_analyzer_allinone")

# True when this script runs as a frozen PyInstaller executable (as
# opposed to a raw `python3 process_analyzer_allinone.py` launch).
IS_FROZEN = bool(getattr(sys, "frozen", False))


def _pause_before_exit() -> None:
    """Prevents the console window from closing instantly (essential for
    a PyInstaller --console .exe double-clicked by a novice)."""
    try:
        input("\nPress Enter to close this window...")
    except (EOFError, KeyboardInterrupt):
        pass


def _is_android() -> bool:
    """Detects Android/Termux via several combined signals (H14) — none
    is guaranteed on its own, so we accumulate them: Android-specific
    environment variables, the Termux prefix, or the presence of the
    /system partition (absent on any other POSIX platform)."""
    if "ANDROID_ROOT" in os.environ or "ANDROID_DATA" in os.environ:
        return True
    if "com.termux" in os.environ.get("PREFIX", ""):
        return True
    return Path("/system/build.prop").exists()


IS_ANDROID = _is_android()


# ---------------------------------------------------------------------------
# Process collection fallback based on /proc (H14) — used only when psutil
# is unavailable, which is SYSTEMATICALLY the case on Android/Termux:
# psutil provides no wheel for Android and its installation from source is
# explicitly refused by its own setup.py ("platform android is not
# supported"), so the usual auto-installation (H9) cannot solve the
# problem — an alternative collection backend is needed rather than
# insisting on pip.
#
# Deliberately minimal implementation: only covers the subset of the
# psutil.Process API actually used by this script, by reading
# /proc/<pid>/* directly. This is the same technique psutil itself uses
# internally on Linux.
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

# Socket-inode -> connection-info table, rebuilt once per collection (see
# _FallbackPsutilModule.process_iter) rather than once per process, to
# avoid reparsing /proc/net/* hundreds of times.
_fallback_inode_map_cache: Optional[dict] = None


def _decode_proc_ipv4_addr(field: str) -> Optional[str]:
    """Decodes a "hexIP:hexPORT" field from /proc/net/{tcp,udp} into
    "a.b.c.d:port" (IPv4 only — H16: IPv6 connections are not decoded by
    this fallback, limitation accepted to stay simple)."""
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
    """Minimal /proc-based re-implementation of the subset of the
    psutil.Process API used by this script (H14/H15)."""

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
        # Approximation (H15): AVERAGE CPU% since the process started
        # (cumulative CPU time / process age), not an instantaneous delta
        # like psutil — sufficient to sort/prioritize processes, but not
        # for precise real-time monitoring. Documented rather than
        # presented as equivalent to the real psutil measurement.
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

    # Alias: the calling code tries net_connections() then connections()
    # (compat with older psutil versions) — both point here.
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
    """Minimal substitute for the psutil API actually used by this script
    (H14), activated only when the real psutil is unavailable."""

    AccessDenied = _FallbackAccessDenied
    NoSuchProcess = _FallbackNoSuchProcess
    ZombieProcess = _FallbackZombieProcess
    Process = _FallbackProcess

    @staticmethod
    def process_iter(attrs=None):
        global _fallback_inode_map_cache
        _fallback_inode_map_cache = None  # invalidated at each new collection
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
# Dependency check (explicit failure rather than a raw ImportError)
# ---------------------------------------------------------------------------

_REQUIRED_MODULES = (
    ("networkx", "networkx"),
    ("matplotlib", "matplotlib"),
    ("requests", "requests"),
)
if not IS_ANDROID:
    # psutil is required EVERYWHERE EXCEPT on Android/Termux (H14), where
    # its wheel does not exist and its compilation fails explicitly — the
    # /proc fallback above takes over in that case, so trying to install
    # it via pip is pointless (and doomed to fail).
    _REQUIRED_MODULES = (("psutil", "psutil"),) + _REQUIRED_MODULES


def _missing_modules() -> list[str]:
    import importlib.util
    return [pip_name for mod_name, pip_name in _REQUIRED_MODULES if importlib.util.find_spec(mod_name) is None]


def _check_dependencies() -> None:
    """Checks that the dependencies are present and, in raw .py mode (H9),
    attempts an automatic installation via pip before giving up."""
    if IS_ANDROID:
        print(
            "Android / Termux detected: psutil is not available on this platform "
            "(not installable), a lightweight /proc-based collection mode is used instead. "
            "The CPU% is an average since the process started (not a real-time snapshot), "
            "and Android natively limits visibility to the current user's processes — "
            "these are platform restrictions, not bugs "
            "(details: H14/H15 in the script header)."
        )

    missing = _missing_modules()
    if not missing:
        return

    if IS_FROZEN:
        print(f"ERROR: missing module(s) in the executable: {', '.join(missing)}")
        print("This is a packaging bug (PyInstaller) and cannot fix itself.")
        print("Rebuild the executable with --collect-submodules / --collect-all for the affected module(s).")
        _pause_before_exit()
        sys.exit(1)

    print(f"Missing Python module(s): {', '.join(missing)}")
    print("Automatic installation in progress (pip)...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *missing])
    except subprocess.CalledProcessError:
        # Fallback for "externally managed" Python environments (PEP 668)
        # that refuse pip install without --break-system-packages.
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", "--quiet",
                "--break-system-packages", *missing,
            ])
        except subprocess.CalledProcessError as exc:
            print(f"Automatic installation failed: {exc}")
            print(f"Install manually: {sys.executable} -m pip install {' '.join(missing)}")
            if IS_ANDROID:
                print(
                    "On Termux, if the failure concerns matplotlib (missing build "
                    "dependencies), try the precompiled package instead: pkg install matplotlib"
                )
            _pause_before_exit()
            sys.exit(1)

    still_missing = _missing_modules()
    if still_missing:
        print(f"Module(s) still not found after installation: {', '.join(still_missing)}")
        _pause_before_exit()
        sys.exit(1)
    print("Dependencies installed successfully.\n")


_check_dependencies()

if IS_ANDROID:
    psutil = _FallbackPsutilModule()
else:
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
    enrichment: Optional[dict] = None  # filled by enrich_with_ollama()
    incomplete_collection: list = field(default_factory=list)  # fields that could not be read (H: collection visibility)
    cmdline_empty: bool = False  # True only if cmdline() succeeded and returned an empty list
    risk: dict = field(default_factory=dict)  # filled by compute_rule_based_risk() / finalize_risk() (H17)
    container: Optional[str] = None  # container id/name (Docker/K8s) if detected via /proc/<pid>/cgroup (H21)
    exe_sha256: Optional[str] = None  # SHA256 fingerprint of the executable if --check-integrity (H22)
    integrity_status: Optional[str] = None  # "new" | "unchanged" | "modified" | "unreadable" (H22)

    @property
    def score(self) -> float:
        """Simple score to prioritize enrichment (H3)."""
        return self.cpu_percent + self.memory_percent


# ---------------------------------------------------------------------------
# 1. Process collection
# ---------------------------------------------------------------------------

def _addr_to_str(addr) -> Optional[str]:
    """Normalizes a psutil address (ip/port namedtuple, raw tuple, or UNIX
    socket path as a str) into a readable string."""
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


def _collect_process_connections(p: "psutil.Process", limit: int, issues: Optional[list] = None) -> list[dict]:
    """Retrieves up to `limit` network/UNIX connections for a process (H7).

    Progressive fallback: `net_connections` (recent API) -> `connections`
    (historical alias) -> kind="all" -> kind="inet" if the platform does
    not support "all". Any permission error returns an empty list rather
    than crashing the collection (but is traced in `issues` if provided,
    see collection visibility).
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
                issues.append(f"connections: {exc.__class__.__name__}")
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
        except Exception:  # defensive: a malformed record must not crash everything
            continue
    return connections


def _detect_container(pid: int) -> Optional[str]:
    """Detects whether a process runs inside a container (Docker, Podman,
    containerd, Kubernetes) by reading /proc/<pid>/cgroup — Linux only
    (H21). Returns a short container identifier, or None if the process
    runs on the host / if the platform does not allow it."""
    cgroup_path = Path(f"/proc/{pid}/cgroup")
    try:
        content = cgroup_path.read_text(errors="replace")
    except OSError:
        return None
    for line in content.splitlines():
        low = line.lower()
        for marker in ("docker", "containerd", "podman", "kubepods", "libpod"):
            if marker in low:
                # The last segment of the cgroup path is generally the
                # container id (64 hex chars) — shortened to 12 characters
                # like `docker ps` does.
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
    """Enumerates the accessible system processes and their related files.

    Processes whose access is denied (psutil.AccessDenied) or which
    disappeared between enumeration and reading (psutil.NoSuchProcess) are
    silently ignored (H6) — this is normal behavior, not a script error.
    """
    processes: list[ProcessInfo] = []

    # cpu_percent requires a first "priming" call per process to be
    # meaningful; so we do two passes with a short interval.
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
                username = _safe(p.username, label="user", issues=issues)
                exe = _safe(p.exe, label="executable", issues=issues)
                cwd = _safe(p.cwd, label="working directory", issues=issues)
                cmdline_parts = _safe(p.cmdline, default=None, label="command line", issues=issues)
                # "Really" empty (cmdline() succeeded but returned nothing,
                # see compute_rule_based_risk) as opposed to a failed read
                # (already traced in `issues` above, cmdline_parts=None).
                cmdline_empty = cmdline_parts is not None and len(cmdline_parts) == 0
                cmdline = " ".join(cmdline_parts) if cmdline_parts else name
                cpu_percent = p.cpu_percent(None)
                memory_percent = round(p.memory_percent(), 3)

            open_files = []
            try:
                open_files = [f.path for f in p.open_files()]
            except (psutil.AccessDenied, psutil.NoSuchProcess, OSError) as exc:
                # Frequent (permissions): we continue without the open files,
                # but we trace it (collection visibility, see enrichment plan).
                issues.append(f"open files: {exc.__class__.__name__}")

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
                incomplete_collection=issues,
                cmdline_empty=cmdline_empty,
                container=_detect_container(pid),
            )
            if info.score >= min_score:
                processes.append(info)

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            logger.debug("Inaccessible process ignored (pid=%s)", getattr(p, "pid", "?"))
            continue
        except Exception as exc:  # defensive: one process must not crash the collection
            logger.debug("Unexpected error on a process, ignored: %s", exc)
            continue

    logger.info("Processes collected: %d", len(processes))
    return processes


def _safe(fn, default=None, label: Optional[str] = None, issues: Optional[list] = None):
    """Like before, but optionally traces in `issues` (collection
    visibility) which field could not be read and why, instead of
    silently returning `default` without any trace."""
    try:
        return fn()
    except (psutil.AccessDenied, psutil.NoSuchProcess, OSError, RuntimeError) as exc:
        if issues is not None and label:
            issues.append(f"{label}: {exc.__class__.__name__}")
        return default


def limit_processes(processes: list[ProcessInfo], max_processes: Optional[int]) -> list[ProcessInfo]:
    """Caps the number of processes included in the graph (H8), keeping
    the most active ones (CPU+RAM) — never a silent truncation: the
    number of hidden processes is always logged."""
    if not max_processes or max_processes <= 0 or len(processes) <= max_processes:
        return processes
    ranked = sorted(processes, key=lambda p: p.score, reverse=True)
    dropped = len(ranked) - max_processes
    logger.info(
        "Limit --max-processes=%d applied: %d processes kept (the most active), %d hidden.",
        max_processes, max_processes, dropped,
    )
    return ranked[:max_processes]


# ---------------------------------------------------------------------------
# 1ter. User whitelist/blacklist configuration (--config, H23)
# ---------------------------------------------------------------------------
# fnmatch patterns (`*` accepted) compared, case-insensitively, to the
# process name, its executable AND its command line. Whitelist: the rule
# engine's PATH signals are neutralized (temporary directory / outside
# standard directories) — the network and "deleted executable" signals
# remain active, a whitelist must not make us blind. Blacklist: immediate
# "high" level with an explicit signal.
USER_CONFIG: dict = {"whitelist": [], "blacklist": []}


def load_user_config(path: Path) -> dict:
    """Loads a whitelist/blacklist configuration file. Accepted formats:
    JSON ({"whitelist": [...], "blacklist": [...]}) OR a simple subset of
    YAML (top-level keys + "- item" lists), parsed by hand so as not to
    add a pyyaml dependency."""
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("the configuration JSON must be an object")
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
        "Configuration loaded from %s: %d whitelist pattern(s), %d blacklist pattern(s).",
        path, len(config["whitelist"]), len(config["blacklist"]),
    )
    return config


def _matches_patterns(p: ProcessInfo, patterns: list[str]) -> Optional[str]:
    """Returns the first pattern matching the process name, executable or
    cmdline (case-insensitive), otherwise None. A pattern without a
    wildcard is treated as a substring search (more intuitive for a
    novice: "ollama" must match "/usr/local/bin/ollama serve")."""
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
# 1quater. Executable integrity check (--check-integrity, H22)
# ---------------------------------------------------------------------------

_INTEGRITY_MAX_BYTES = 200 * 1024 * 1024  # beyond this, we do not hash (abnormally large binary)


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
    """Computes the SHA256 of each executable and compares it to the
    reference database `db_path` (JSON {path: sha256}) built during
    previous runs. Marks each process: "new" (seen for the first time),
    "unchanged", "modified" (different fingerprint — risk signal) or
    "unreadable". The database is updated with NEW binaries only; a
    modified fingerprint NEVER silently overwrites the reference
    (otherwise the detection would be useless) — delete the database file
    to start from scratch after a legitimate update."""
    known: dict[str, str] = {}
    if db_path.exists():
        try:
            known = json.loads(db_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Unreadable integrity database (%s) — will start from scratch: %s", db_path, exc)

    # The same executable is shared by many processes: hash once per
    # path, not once per process.
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
            p.integrity_status = "unreadable"
        elif exe not in known:
            p.integrity_status = "new"
            n_new += 1
        elif known[exe] == digest:
            p.integrity_status = "unchanged"
            n_same += 1
        else:
            p.integrity_status = "modified"
            n_modified += 1

    for exe, digest in hashes.items():
        if digest and exe not in known:
            known[exe] = digest

    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_text(json.dumps(known, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "Integrity: %d binary(ies) hashed — %d new, %d unchanged, %d MODIFIED. Database: %s",
        len(hashes), n_new, n_same, n_modified, db_path,
    )
    if n_modified:
        logger.warning("%d binary(ies) have a fingerprint DIFFERENT from the reference — check the flagged processes.", n_modified)


# ---------------------------------------------------------------------------
# 1quinquies. Performance baseline + anomaly detection (--baseline, H24)
# ---------------------------------------------------------------------------

def load_baseline(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Unreadable baseline (%s) — ignored: %s", path, exc)
        return {}


def update_baseline(processes: list[ProcessInfo], path: Path) -> None:
    """Updates rolling statistics (Welford mean/variance) of CPU%% and
    RAM%% PER process name. Each run with --baseline adds one sample;
    anomaly detection (see apply_baseline_anomalies) only makes sense
    starting from 3 samples."""
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
    logger.info("Baseline updated (%d process name(s) tracked): %s", len(baseline), path)


def _baseline_std(entry: dict, prefix: str) -> float:
    n = entry.get("n", 0)
    if n < 2:
        return 0.0
    return (entry[f"{prefix}_m2"] / (n - 1)) ** 0.5


def baseline_anomaly_signals(p: ProcessInfo, baseline: dict) -> list[str]:
    """Statistical anomaly signals (z-score > 2) relative to the
    baseline, per process name. Deliberately conservative: never
    triggered under 3 samples nor for a near-zero standard deviation
    with a low absolute value (a process stable at 0.1%% that moves to
    0.4%% is not an interesting anomaly)."""
    entry = baseline.get(p.name)
    if not entry or entry.get("n", 0) < 3:
        return []
    signals = []
    for prefix, value, label in (("cpu", p.cpu_percent, "CPU"), ("mem", p.memory_percent, "RAM")):
        std = _baseline_std(entry, prefix)
        mean = entry[f"{prefix}_mean"]
        if std > 0.05 and value > mean + 2 * std and value >= 5.0:
            signals.append(
                f"{label} abnormally high vs baseline ({value:.1f}% against {mean:.1f}% ± {std:.1f}% usually)"
            )
    return signals


# ---------------------------------------------------------------------------
# 1bis. Rule-based risk engine (H17) — deterministic, independent of
# Ollama. Each triggered rule is traced by name (never an opaque score);
# the level produced here ("rules_level") serves as a floor: a more
# severe AI opinion can raise the final level, never lower it (see
# finalize_risk below).
# ---------------------------------------------------------------------------

_STANDARD_EXE_PREFIXES = (
    "/usr/", "/bin/", "/sbin/", "/opt/", "/System/", "/Applications/",
    "/Library/", "/snap/", "/nix/", "c:\\windows", "c:\\program files",
)
_TEMP_EXE_PREFIXES = ("/tmp/", "/var/tmp/", "/dev/shm/", "/private/tmp/")
_RISK_LEVELS = ("low", "medium", "high")


def _risk_severity(level: Optional[str]) -> int:
    """"unknown" (or any unrecognized value) neither raises nor lowers a
    combined level: treated as the lowest severity, never as a
    full-fledged level that would mask a real signal."""
    try:
        return _RISK_LEVELS.index(level)
    except ValueError:
        return -1


def _bump(level: str, new_level: str, signal: str, signals: list) -> str:
    """NEVER lowers `level`: can only raise it if `new_level` is more
    severe (see H17 — underestimating a risk is judged worse than
    overestimating it)."""
    signals.append(signal)
    return new_level if _risk_severity(new_level) > _risk_severity(level) else level


def compute_rule_based_risk(p: ProcessInfo, baseline: Optional[dict] = None) -> dict:
    """Computes a deterministic risk level from observable signals on the
    process (H17), without depending on Ollama.

    Returns {"level": "low"|"medium"|"high", "signals": [...]}. A process
    without any signal remains "low" with an explicit signal "no signal
    detected by the rules" rather than an ambiguous empty list.

    Takes into account, if present, the whitelist/blacklist configuration
    (H23), the binary's integrity status (H22) and the performance
    baseline (H24).
    """
    level = "low"
    signals: list[str] = []

    # User blacklist: immediate high level, but we keep evaluating the
    # other rules (their signals remain informative).
    blacklist_hit = _matches_patterns(p, USER_CONFIG["blacklist"])
    if blacklist_hit:
        level = _bump(level, "high", f"matches the blacklist pattern '{blacklist_hit}' from the configuration", signals)

    # User whitelist: neutralizes ONLY the path signals (temporary
    # directory / outside standard directories) — a legitimate tool
    # compiled in /tmp remains whitelistable without masking its network
    # signals.
    whitelist_hit = None if blacklist_hit else _matches_patterns(p, USER_CONFIG["whitelist"])
    if whitelist_hit:
        signals.append(f"whitelisted by the configuration (pattern '{whitelist_hit}'): path signals ignored")

    exe = (p.exe or "").strip()
    exe_lower = exe.lower()

    # NB: an EMPTY exe (not "(deleted)", just absent) is psutil's NORMAL
    # behavior for kernel threads (no binary on disk) — NEVER treat it as
    # a signal, at the risk of marking dozens of perfectly legitimate
    # kernel threads as "high" on any Linux machine (massive noise,
    # contrary to this engine's purpose).
    if exe:
        if "(deleted)" in exe_lower:
            # Strong signal specific to psutil/Linux: the binary was
            # deleted from disk after the process launched — classic case
            # of malicious self-deletion (but also, more benignly, of a
            # package update without a restart).
            level = _bump(level, "high", f"executable deleted from disk after the process launched ({exe})", signals)
        elif exe_lower.startswith(_TEMP_EXE_PREFIXES):
            if not whitelist_hit:
                level = _bump(level, "high", f"executable launched from a temporary directory ({exe})", signals)
        elif not exe_lower.startswith(_STANDARD_EXE_PREFIXES) and not exe_lower.startswith(("/home/", "/users/")):
            if not whitelist_hit:
                level = _bump(level, "medium", f"executable outside the standard system directories ({exe})", signals)

    if p.integrity_status == "modified":
        level = _bump(level, "high", "SHA256 fingerprint of the executable DIFFERENT from the known reference (modified binary?)", signals)

    if baseline:
        for anomaly in baseline_anomaly_signals(p, baseline):
            level = _bump(level, "medium", anomaly, signals)

    if p.cmdline_empty and exe:
        # Empty command line WHILE a real executable is present: rare and
        # unusual (kernel threads, which legitimately have an empty
        # cmdline, precisely have no exe — so no false positive here
        # thanks to the `and exe`).
        level = _bump(level, "medium", "empty command line despite a present executable (rare, unusual)", signals)

    listening_all_interfaces = any(
        (c.get("laddr") or "").startswith(("0.0.0.0:", "[::]:", ":::")) and c.get("status") == "LISTEN"
        for c in p.connections
    )
    if listening_all_interfaces:
        level = _bump(level, "medium", "process listening on all network interfaces (0.0.0.0)", signals)

    external_raddrs = {
        c.get("raddr") for c in p.connections
        if c.get("raddr") and not c["raddr"].split(":")[0].startswith(("127.", "::1", "0.0.0.0"))
    }
    if len(external_raddrs) > 10:
        level = _bump(level, "medium", f"unusual volume of distinct external connections ({len(external_raddrs)})", signals)

    if not signals:
        signals.append("no signal detected by the rules")

    return {"level": level, "signals": signals}


def finalize_risk(p: ProcessInfo) -> None:
    """Combines the rule-based level (already set in p.risk by
    compute_rule_based_risk) with the possible Ollama opinion
    (p.enrichment), by escalation only (H17). Must be called AFTER
    enrichment (or after setting a fallback enrichment), never before."""
    rules = p.risk or {"level": "low", "signals": ["no signal detected by the rules"]}
    ai_level = None
    ai_justification = ""
    if p.enrichment:
        candidate = p.enrichment.get("risk_level")
        if candidate in _RISK_LEVELS:
            ai_level = candidate
            ai_justification = p.enrichment.get("risk_justification", "")

    final_level = rules["level"]
    if ai_level is not None and _risk_severity(ai_level) > _risk_severity(final_level):
        final_level = ai_level

    p.risk = {
        "rules_level": rules["level"],
        "rules_signals": rules["signals"],
        "ai_level": ai_level,
        "ai_justification": ai_justification,
        "final_level": final_level,
        "divergence": ai_level is not None and ai_level != rules["level"],
    }


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

    # Parent -> child relationships
    for p in processes:
        if p.ppid in pid_to_info and p.ppid != p.pid:
            graph.add_edge(f"proc:{p.ppid}", f"proc:{p.pid}", kind="parent_of")

    # Files shared between >= 2 processes (H4)
    file_to_pids: dict[str, list[int]] = {}
    for p in processes:
        for path in p.open_files:
            file_to_pids.setdefault(path, []).append(p.pid)

    shared_files = {path: pids for path, pids in file_to_pids.items() if len(pids) >= 2}
    logger.info("Files shared between multiple processes: %d", len(shared_files))

    for path, pids in shared_files.items():
        file_node = f"file:{path}"
        graph.add_node(file_node, kind="file", label=Path(path).name or path, full_path=path)
        for pid in pids:
            graph.add_edge(f"proc:{pid}", file_node, kind="opens")

    # Network connections, colored by protocol (H7). Several processes
    # connected to the same remote endpoint converge on the same node
    # (useful to spot shared infrastructure: DNS, proxy, database...).
    # Priority to the most active processes if we exceed max_conn_total.
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
            "Network connections: %d displayed, %d hidden (--max-conn-total=%d) to keep the graph readable.",
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

ENRICHMENT_SCHEMA_PROMPT = """You are an educational system analyst. Here is a running process:

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

Answer in English, ONLY with a strict JSON object (no text outside the JSON), in this exact format:
{{"category": "<short category, e.g.: browser, system service, dev-tool, database, network, unknown>",
  "probable_role": "<one short sentence describing the probable role of THIS specific process>",
  "risk_level": "<low|medium|high|unknown>",
  "risk_justification": "<one short sentence>",
  "educational_explanation": "<2-3 sentences explaining to a non-expert, in general terms, what this kind of process/program does in an operating system>"}}
"""


def _default_enrichment(reason: str) -> dict:
    return {
        "category": "unknown",
        "probable_role": "not enriched",
        "risk_level": "unknown",
        "risk_justification": reason,
        "educational_explanation": "",
    }


# Static fallback knowledge base for the "Knowledge" mode: used when a
# process has not been enriched by Ollama (outside --enrich-limit, Ollama
# unavailable, etc.). Case-insensitive substring lookup on the process
# name — deliberately non-exhaustive, just covers the most common system
# processes (macOS/Linux).
KNOWLEDGE_BASE: dict[str, str] = {
    "kernel_task": "Special macOS kernel process: it does not really consume the displayed CPU/RAM, "
                    "it serves as a reservoir for the system's thermal and power management.",
    "launchd": "The very first process (PID 1) on macOS: starts and supervises all the other "
               "system services and daemons.",
    "systemd": "The very first process (PID 1) on most modern Linux distributions: "
               "starts and supervises the system services.",
    "windowserver": "macOS service responsible for rendering all windows and the on-screen display.",
    "finder": "The graphical file explorer of macOS.",
    "dock": "Manages the macOS icon bar (Dock).",
    "mds": "Metadata Server: indexes files for Spotlight search on macOS.",
    "mdworker": "Spotlight worker process that indexes file contents in the background.",
    "coreaudiod": "Central macOS audio daemon, manages the system sound.",
    "cupsd": "Printing daemon (CUPS), manages the print queues.",
    "sshd": "SSH server: accepts secure remote connections to this machine.",
    "bash": "Command interpreter (shell) — executes the commands typed in a terminal.",
    "zsh": "Command interpreter (shell) — executes the commands typed in a terminal.",
    "python": "Interpreter for the Python language — executes a Python script or application.",
    "node": "Server-side JavaScript runtime — executes a Node.js application or tool.",
    "docker": "Containerization engine — runs isolated applications inside containers.",
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
    timeout: float = 120.0,
) -> dict:
    """Calls the local Ollama API (/api/generate) and parses the expected JSON response.

    On failure (Ollama not running, timeout, invalid JSON), returns a
    fallback enrichment rather than raising an exception (H5/H6): a
    system analysis tool must not crash because a local LLM is
    unavailable.
    """
    url = f"{host.rstrip('/')}/api/generate"
    # num_predict caps the length of the generated response (H11): the
    # expected response is a small JSON object of a few sentences, no
    # need to allow a model to generate hundreds of tokens — this bounds
    # the worst-case latency per call.
    payload = {
        "model": model, "prompt": prompt, "stream": False, "format": "json",
        "options": {"num_predict": 220},
    }
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
        logger.warning("Ollama unreachable on %s — enrichment disabled for this process.", host)
        return _default_enrichment("ollama_unavailable")
    except requests.exceptions.Timeout:
        logger.warning("Ollama timeout (>%ss) for model %s.", timeout, model)
        return _default_enrichment("ollama_timeout")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Ollama response does not match the expected JSON: %s", exc)
        return _default_enrichment("invalid_json_response")
    except Exception as exc:  # defensive
        logger.warning("Unexpected error during the Ollama call: %s", exc)
        return _default_enrichment(f"unexpected_error:{exc}")


def check_ollama_available(model: str, host: str, timeout: float = 5.0) -> tuple[bool, str]:
    """Checks ONCE, before starting the enrichment loop, that Ollama is
    reachable and that the requested model actually exists locally.

    Without this safeguard, a misspelled model (e.g. "llama3:lattest"
    instead of "llama3:latest") produces the same repeated 404 error on
    EVERY enriched process — useless and noisy on large machines
    (hundreds of processes). We fail fast, once, with an actionable
    message (list of the models actually available).
    """
    try:
        resp = requests.get(f"{host.rstrip('/')}/api/tags", timeout=timeout)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        return False, f"Ollama unreachable on {host} (is the server running? try: ollama serve)"
    except requests.exceptions.Timeout:
        return False, f"Ollama is not responding on {host} (timeout of {timeout}s)"
    except Exception as exc:  # defensive
        return False, f"Error while querying Ollama on {host}: {exc}"

    try:
        available = [m.get("name", "") for m in resp.json().get("models", [])]
    except (ValueError, AttributeError):
        return False, "Unexpected response from Ollama on /api/tags (unrecognized format)."

    # Tolerant comparison: "llama3" must match a model installed as
    # "llama3:latest".
    model_base = model.split(":")[0]
    if any(name == model or name.split(":")[0] == model_base for name in available):
        return True, ""

    suggestion = (
        f" Available models: {', '.join(available)}" if available
        else " No model installed locally (try: ollama pull <model>)."
    )
    return False, f"Model '{model}' is not available on {host}.{suggestion}"


def _detect_ollama_models(host: str, timeout: float = 3.0) -> list[str]:
    """Lists the installed Ollama models via the HTTP API (H10) rather
    than the `ollama list` command, so as not to depend on the `ollama`
    binary being on the PATH (important for a PyInstaller executable).
    Returns an empty list (never an exception) if Ollama is not
    reachable."""
    try:
        resp = requests.get(f"{host.rstrip('/')}/api/tags", timeout=timeout)
        resp.raise_for_status()
        return [m.get("name", "") for m in resp.json().get("models", []) if m.get("name")]
    except Exception:
        return []


# Model offered by default during the automatic download triggered by the
# novice assistant when no Ollama model is installed (H12), ADAPTED TO
# THE MACHINE (H35, same policy as install.sh/install.ps1): mini on
# Android/Termux (limited RAM and storage on mobile), medium everywhere
# else (macOS / Windows / Linux).
DEFAULT_OLLAMA_MODEL = "llama3.2:1b" if IS_ANDROID else "llama3:latest"

# Default for --model, adapted the same way: on Android, target the mini
# model downloaded by install.sh rather than a 3B/8B model untenable on
# mobile.
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
    """Starts `ollama serve` in the background if the binary is present
    but the server is not responding yet right after installation."""
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
    except Exception as exc:  # defensive: an auto-start failure is not fatal
        logger.debug("Could not start 'ollama serve' automatically: %s", exc)


def _install_ollama_macos() -> bool:
    if shutil.which("brew"):
        print("Installing Ollama via Homebrew (may take a few minutes)...")
        try:
            subprocess.check_call(["brew", "install", "ollama"])
            return True
        except subprocess.CalledProcessError as exc:
            print(f"Installation via Homebrew failed: {exc}")
    print("Homebrew unavailable (or installation failed) — opening the official download page...")
    webbrowser.open("https://ollama.com/download/mac")
    _prompt("Install Ollama from the opened window, then press Enter to continue", "")
    return shutil.which("ollama") is not None or _ollama_reachable("http://localhost:11434")


def _install_ollama_linux() -> bool:
    print("Installing Ollama via the official script (may ask for your sudo password)...")
    try:
        subprocess.check_call("curl -fsSL https://ollama.com/install.sh | sh", shell=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Automatic installation failed: {exc}")
        print("Install manually: curl -fsSL https://ollama.com/install.sh | sh")
        return False


def _install_ollama_android() -> bool:
    """Installs Ollama on Termux via the official package from the Termux
    repositories (H35) — the ollama.com script does not work on Android.
    Degrades cleanly (False) if `pkg` is absent or if the package does
    not exist in this version of Termux."""
    if shutil.which("pkg") is None:
        print("Command 'pkg' not found (are you really on Termux?) — installation impossible.")
        print("Try manually: pkg install ollama")
        return False
    print("Installing Ollama via pkg (Termux)...")
    try:
        subprocess.check_call(["pkg", "install", "-y", "ollama"])
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Installation via pkg failed: {exc}")
        print("The ollama package may not be available in this version of Termux "
              "(pkg update && pkg install ollama to retry) — the analysis will continue without AI.")
        return False


def _install_ollama_windows() -> bool:
    import tempfile
    installer_url = "https://ollama.com/download/OllamaSetup.exe"
    print("Downloading the Ollama installer for Windows...")
    try:
        installer_path = Path(tempfile.gettempdir()) / "OllamaSetup.exe"
        with requests.get(installer_url, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            with open(installer_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
        print("Launching the installer (follow the on-screen instructions)...")
        subprocess.run([str(installer_path)], check=False)
        return shutil.which("ollama") is not None or _ollama_reachable("http://localhost:11434")
    except Exception as exc:
        print(f"Failed to download/launch the installer: {exc}")
        print(f"Download it manually: {installer_url}")
        return False


def ensure_ollama_ready(host: str) -> bool:
    """If Ollama does not respond on `host`, offers (with the user's
    explicit consent — never silently) an automatic installation suited
    to the detected OS (H12). Returns True if Ollama ends up responding,
    False otherwise (the caller must then disable AI)."""
    if _ollama_reachable(host):
        return True

    print()
    print("Ollama (the local AI engine) is not detected on this machine.")
    answer = _prompt(
        "Install it automatically now? (y/n — otherwise the analysis continues without AI)",
        "y",
    )
    if answer.strip().lower() not in ("y", "yes"):
        return False

    system = platform.system()
    # Android/Termux BEFORE the "Linux" test: platform.system() returns
    # "Linux" there, but the official ollama.com script does not work on
    # Termux — the Termux package is what's needed (pkg install ollama).
    if IS_ANDROID:
        installed = _install_ollama_android()
    elif system == "Darwin":
        installed = _install_ollama_macos()
    elif system == "Linux":
        installed = _install_ollama_linux()
    elif system == "Windows":
        installed = _install_ollama_windows()
    else:
        print(f"Automatic installation not supported on this platform ({system}).")
        print("Install manually from https://ollama.com/download")
        return False

    if not installed:
        return False

    if not _ollama_reachable(host):
        _start_ollama_server(host)
        print("Starting the Ollama server...")
    if not _wait_for_ollama(host, timeout=30.0):
        print("Ollama was installed but is not responding yet. Relaunch the assistant in a few moments.")
        return False
    print("Ollama is ready.")
    return True


def pull_ollama_model(model: str, host: str, timeout: float = 1800.0) -> bool:
    """Downloads an Ollama model via the HTTP API (POST /api/pull,
    streamed flow) with progress display. Generous default timeout
    (30 min): a model like llama3:latest is several GB and the download
    time depends entirely on the user's connection."""
    url = f"{host.rstrip('/')}/api/pull"
    print(f"Downloading model '{model}' (may take several minutes depending on your connection)...")
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
                    print(f"\nError during the download: {data['error']}")
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
        print(f"Model '{model}' downloaded successfully.")
        return True
    except requests.exceptions.RequestException as exc:
        print(f"\nFailed to download model '{model}': {exc}")
        return False


def _warm_up_ollama(model: str, host: str, timeout: float = 180.0) -> None:
    """Sends a tiny throwaway call BEFORE the enrichment loop, to force
    the model to load into memory only once (H11).

    Without this, several ThreadPoolExecutor workers hit Ollama at the
    same time while it is still loading a multi-GB model into memory
    (which can take from a few seconds to over a minute); since Ollama
    serves generation requests largely sequentially locally, those
    workers stay queued and time out before they even start generating
    anything — this is what produced bursts of 30s timeouts across the
    whole first wave of requests. A failure here is not fatal: logged as
    a warning, the real enrichment is attempted anyway (the first call
    will then absorb the loading).
    """
    logger.info(
        "Loading model '%s' into memory (can take up to a minute or more on the first call)...",
        model,
    )
    try:
        requests.post(
            f"{host.rstrip('/')}/api/generate",
            json={"model": model, "prompt": "Reply with OK only.", "stream": False, "options": {"num_predict": 5}},
            timeout=timeout,
        )
        logger.info("Model loaded — starting enrichment.")
    except Exception as exc:  # defensive: the warm-up is a comfort, not a prerequisite
        logger.warning("Model warm-up failed or took too long (%s) — enrichment starts anyway.", exc)


# Fallback reasons meaning "the enrichment of THIS process failed in a
# possibly transient way" — candidates for retry (H25) and never cached
# (H26).
_TRANSIENT_ENRICH_REASONS = ("ollama_unavailable", "ollama_timeout", "invalid_json_response")


def _enrichment_failed_transiently(enrichment: Optional[dict]) -> bool:
    reason = (enrichment or {}).get("risk_justification", "")
    return reason in _TRANSIENT_ENRICH_REASONS or reason.startswith("unexpected_error")


class EnrichmentCache:
    """Persistent SQLite cache of Ollama enrichment results (H26).

    Key = SHA256(name + executable + cmdline): the same binary launched
    with the same command has the same role from one run to the next —
    no need to pay for an LLM call every time. Configurable TTL (default
    7 days). Fallback enrichments (failure/timeout) are NEVER cached.
    Results served from the cache are marked `from_cache: true` to
    remain distinguishable in the graph."""

    def __init__(self, path: Path, ttl_days: float = 7.0):
        import threading
        self.path = path
        self.ttl_seconds = ttl_days * 86400
        path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + lock: put() is called from the
        # enrichment ThreadPoolExecutor's threads, not only from the main
        # thread.
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
    """Loads a user Python plugin (H27) exposing a function
    `enrich(process_info: dict) -> dict` and merges its result into
    p.enrichment["plugin"]. Any plugin error is logged, never fatal —
    the plugin is USER code provided explicitly via --plugin, executed
    with the same rights as the script itself."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("process_analyzer_user_plugin", plugin_path)
    if spec is None or spec.loader is None:
        logger.error("Unreadable plugin: %s", plugin_path)
        return
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        logger.error("Failed to load plugin %s: %s", plugin_path, exc)
        return
    enrich_fn = getattr(module, "enrich", None)
    if not callable(enrich_fn):
        logger.error("Plugin %s does not expose an enrich(process_info) -> dict function.", plugin_path)
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
                    p.enrichment = _default_enrichment("plugin_only")
                p.enrichment["plugin"] = result
                n_ok += 1
        except Exception as exc:
            n_err += 1
            logger.debug("Plugin error on pid=%s: %s", p.pid, exc)
    logger.info("Plugin %s applied: %d processes enriched, %d errors.", plugin_path.name, n_ok, n_err)


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
    """Enriches in place the most significant ProcessInfo objects (H3).

    Calls are parallelized (ThreadPoolExecutor) since they are blocking
    HTTP requests; max_workers remains modest by default (H11) — a local
    LLM most often serves requests sequentially (a single GPU/CPU), so
    heavy parallelization only stacks requests in a queue without
    speeding anything up, and makes them all time out together.
    """
    ranked = sorted(processes, key=lambda p: p.score, reverse=True)
    targets = ranked if enrich_limit is None else ranked[:enrich_limit]

    if not targets:
        logger.info("No process to enrich.")
        return

    # Persistent cache (H26): serve already-known results first, keep as
    # Ollama targets only the processes never seen / expired.
    if cache is not None:
        remaining = []
        for p in targets:
            cached = cache.get(p)
            if cached is not None:
                p.enrichment = cached
            else:
                remaining.append(p)
        if cache.hits:
            logger.info("Enrichment cache: %d result(s) served from %s.", cache.hits, cache.path)
        targets = remaining
        if not targets:
            logger.info("All targeted processes were cached — no Ollama call needed.")
            for p in processes:
                if p.enrichment is None:
                    p.enrichment = _default_enrichment("outside_enrichment_limit")
            return

    ok, message = check_ollama_available(model, host)
    if not ok:
        logger.error("Ollama enrichment cancelled before starting: %s", message)
        for p in processes:
            p.enrichment = _default_enrichment("preflight_failed")
        return

    _warm_up_ollama(model, host)

    logger.info(
        "Ollama enrichment of %d/%d processes (model=%s, host=%s, timeout=%ss, workers=%d)...",
        len(targets), len(processes), model, host, timeout, max_workers,
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
        if cache is not None and p.enrichment:
            cache.put(p, p.enrichment)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        list(executor.map(_enrich_one, targets))

    # Retry of transient failures (H25): exponential backoff 1s, 2s,
    # 4s... between passes, SERIALLY (a transient failure often means
    # Ollama is saturated — re-parallelizing would make things worse).
    for attempt in range(1, max(0, retry_failed) + 1):
        failed = [p for p in targets if _enrichment_failed_transiently(p.enrichment)]
        if not failed:
            break
        backoff = 2 ** (attempt - 1)
        logger.info(
            "Retry %d/%d: %d enrichment(s) in transient failure, retrying in %ds...",
            attempt, retry_failed, len(failed), backoff,
        )
        time.sleep(backoff)
        for p in failed:
            _enrich_one(p)
        recovered = sum(1 for p in failed if not _enrichment_failed_transiently(p.enrichment))
        logger.info("Retry %d/%d finished: %d/%d recovered.", attempt, retry_failed, recovered, len(failed))

    # Non-targeted processes receive an explicit neutral enrichment, so
    # the PNG rendering distinguishes "not analyzed" from "analyzed
    # without risk".
    for p in processes:
        if p.enrichment is None:
            p.enrichment = _default_enrichment("outside_enrichment_limit")


# ---------------------------------------------------------------------------
# 4. PNG rendering
# ---------------------------------------------------------------------------

RISK_COLORS = {
    "low": "#4CAF50",
    "medium": "#FFC107",
    "high": "#F44336",
    "unknown": "#9E9E9E",
}

# Colors of edges/connections by "kind" — network protocol for the
# connections, relation type for parent/child and shared files.
# Validated with the dataviz skill's palette validator (dark mode,
# surface close to #05070d): the initial gray pair (#78909C/#607D8B)
# failed the "normal vision" distinction threshold (ΔE 6.7, below the
# floor of 15) — replaced by a slate-blue / taupe-brown pair that passes
# (ΔE 16.3) while remaining deliberately discreet (these are secondary
# "structural" links, not the main categorical channel).
PROTOCOL_COLORS = {
    "tcp": "#42A5F5",
    "udp": "#FFA726",
    "unix": "#AB47BC",
    "parent_of": "#5A6E82",
    "opens": "#A68A5B",
}
CONNECTION_NODE_COLOR = "#37474F"

# Categorical palette for the "Type" mode (coloring by process category
# detected by Ollama). Fixed order validated by the dataviz skill
# (adjacent pairs, dark mode): CVD ΔE >= 8.4, normal vision >= 19.3,
# contrast >= 3:1 on all pairs. "unknown" deliberately stays outside the
# categorical palette (neutral gray) rather than inventing an extra hue
# for an "Other" — see the dataviz skill rule.
# NB: only consumed by the JS mirror inside _HTML_TEMPLATE (the "Type"
# mode is HTML-only); kept on the Python side as the canonical, documented
# source of truth for that palette.
CATEGORY_COLORS = {
    "browser": "#3987E5",
    "system service": "#D95926",
    "dev-tool": "#199E70",
    "database": "#C98500",
    "network": "#D55181",
}
CATEGORY_COLOR_UNKNOWN = "#9AA1B2"


def render_graph_png(
    graph: nx.DiGraph,
    processes: list[ProcessInfo],
    output_path: Path,
    title: str = "Graph of processes, related files, network connections and Ollama enrichment",
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
            if info and info.risk:
                # final_level (H17) = deterministic rules combined by
                # escalation with the Ollama opinion, MORE reliable than
                # the AI opinion alone.
                risk = info.risk.get("final_level", "unknown")
            if info and info.enrichment:
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
# 5. Interactive 3D rendering (standalone HTML, clickable "solar system" nodes)
# ---------------------------------------------------------------------------
#
# Library: 3d-force-graph (three.js embedded), loaded from a CDN
# (unpkg) — see the rule "External scripts can be imported from a CDN";
# the file remains a single standalone .html (application CSS/JS inline),
# but requires a network connection to load the lib on first display.

def build_graph_payload(graph: nx.DiGraph, processes: list[ProcessInfo]) -> dict:
    """Converts the networkx graph into a {nodes, links} structure
    directly consumable by 3d-force-graph (one JS object per node/edge)."""
    pid_to_info = {p.pid: p for p in processes}
    nodes = []

    for node, data in graph.nodes(data=True):
        kind = data.get("kind")
        if kind == "process":
            info = pid_to_info.get(data["pid"])
            risk_info = (info.risk if info else None) or {}
            risk = risk_info.get("final_level", "unknown")
            category = "unknown"
            role = "not enriched"
            justification = ""
            explanation = ""
            if info and info.enrichment:
                category = info.enrichment.get("category", "unknown")
                role = info.enrichment.get("probable_role", "not enriched")
                justification = info.enrichment.get("risk_justification", "")
                explanation = info.enrichment.get("educational_explanation", "")
            # "Knowledge" mode: we prefer the Ollama explanation if the
            # process was actually enriched (non-empty explanation),
            # otherwise we fall back to the local static knowledge base.
            enriched = bool(explanation)
            knowledge_text = explanation if enriched else lookup_knowledge_base(data["label"])
            cpu = round(data.get("cpu", 0), 2)
            mem = round(data.get("mem", 0), 2)
            # "Low interest" node (H18): hidden by default on the HTML
            # side to reduce visual density, never if a real risk was
            # detected (rules or AI).
            low_interest = (
                graph.degree(node) <= 1
                and (cpu + mem) < 1.0
                and risk == "low"
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
                "category": category,
                "probable_role": role,
                "risk_level": risk,
                "rules_risk_level": risk_info.get("rules_level", "unknown"),
                "rules_signals": risk_info.get("rules_signals", []),
                "ai_risk_level": risk_info.get("ai_level"),
                "risk_divergent": bool(risk_info.get("divergence", False)),
                "risk_justification": justification or risk_info.get("ai_justification", ""),
                "incomplete_collection": (info.incomplete_collection if info else []),
                "container": info.container if info else None,
                "exe_sha256": info.exe_sha256 if info else None,
                "integrity_status": info.integrity_status if info else None,
                "low_interest": low_interest,
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
                    "tcp": "TCP connection: reliable, ordered channel (web, SSH, databases...).",
                    "udp": "UDP connection: fast exchange without delivery guarantee (DNS, streaming, games...).",
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
      <button class="mode-btn active" data-mode="security">Security</button>
      <button class="mode-btn" data-mode="debug">Debug</button>
      <button class="mode-btn" data-mode="info_verbose">Verbose info</button>
      <button class="mode-btn" data-mode="knowledge">Knowledge</button>
    </div>
    <input id="search" type="text" placeholder="Search for an item..." />
    <button id="exportCsv" class="mode-btn" title="Export the currently displayed nodes as CSV">Export CSV</button>
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
    <h4>Display</h4>
    <div class="legend-row disabled" data-key="low_interest"><span class="dot" style="background:#546E7A;color:#546E7A"></span>Low-activity processes (hidden)</div>
  </div>

  <div id="panel">
    <button id="closePanel">✕</button>
    <div id="panelBody"></div>
  </div>

  <div id="cameraControls">
    <button id="zoomIn" title="Zoom in">+</button>
    <button id="zoomOut" title="Zoom out">–</button>
    <button id="recenter" title="Recenter (R or Ctrl+R)">⟲</button>
  </div>

  <div id="hint">Click: select &nbsp;•&nbsp; drag: orbit &nbsp;•&nbsp; wheel: zoom &nbsp;•&nbsp; R: recenter &nbsp;•&nbsp; Esc: close &nbsp;•&nbsp; /: search &nbsp;•&nbsp; 1-5: modes</div>

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
    // low_interest hidden by default (H18) to reduce the initial visual
    // density; togglable from the legend ("Display" section), never
    // applied to a node whose final risk is not "low".
    const hiddenKeys = new Set(['low_interest']);
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

    // "Process type" categorical palette — same values as
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

    // Panel "copy" buttons (PID, executable, command, kill command):
    // speeds up moving to investigation in a terminal.
    // navigator.clipboard may be unavailable on file:// depending on the
    // browser -> fallback to a temporary <textarea> + execCommand.
    function copyText(text, btn) {
      const done = () => {
        btn.classList.add('copied');
        const old = btn.textContent;
        btn.textContent = 'copied ✓';
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
    // The values to copy are stored in an indexed registry rather than
    // inlined into onclick: avoids any fragile quote escaping in
    // injected HTML.
    const COPY_REGISTRY = [];
    function copyBtn(value, label) {
      if (value === null || value === undefined || value === '') return '';
      const idx = COPY_REGISTRY.push(String(value)) - 1;
      return `<button class="copy-btn" data-copy-idx="${idx}">${escapeHtml(label || 'copy')}</button>`;
    }
    panelBody.addEventListener('click', (e) => {
      const btn = e.target.closest('.copy-btn');
      if (btn) copyText(COPY_REGISTRY[Number(btn.dataset.copyIdx)] || '', btn);
    });

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

    // A node can be filtered from SEVERAL legend sections at once (risk
    // AND type, for example) — so we return the set of its keys, and a
    // node disappears if AT LEAST ONE is hidden.
    function nodeFilterKeys(node) {
      if (node.type === 'file') return ['file'];
      if (node.type === 'connection') return ['proto_' + node.protocol];
      const keys = [node.risk_level || 'unknown', 'cat_' + categorySlug(node.category)];
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

    function csvEscape(value) {
      const s = value === null || value === undefined ? '' : String(value);
      return /[",\\r\\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    }

    function nodeCsvValue(node, col) {
      const v = node[col];
      if (Array.isArray(v)) {
        if (col === 'connections') {
          return v.map(c => `${c.protocol}:${c.raddr || c.laddr || '?'}${c.status ? ' (' + c.status + ')' : ''}`).join('; ');
        }
        return v.join('; ');
      }
      return v === null || v === undefined ? '' : v;
    }

    // Exports exactly the nodes currently on screen: same filter as the 3D
    // view (currentGraphData), so toggling legend rows before exporting
    // scopes the CSV the same way it scopes the graph (e.g. only "Network"
    // checked -> only network-category nodes in the file).
    function exportCsv() {
      const { nodes } = currentGraphData();
      // color/val are render hints; the rest are simulation state that
      // 3d-force-graph mutates directly onto node objects at runtime
      // (position, velocity, its internal three.js object handle).
      const skip = new Set(['color', 'val', 'index', 'x', 'y', 'z', 'vx', 'vy', 'vz', 'fx', 'fy', 'fz', '__threeObj']);
      const columns = ['id', 'type', 'name'];
      const seen = new Set(columns);
      nodes.forEach(n => Object.keys(n).forEach(k => {
        if (skip.has(k) || seen.has(k)) return;
        seen.add(k); columns.push(k);
      }));
      const lines = [columns.map(csvEscape).join(',')];
      nodes.forEach(n => lines.push(columns.map(c => csvEscape(nodeCsvValue(n, c))).join(',')));
      const blob = new Blob([lines.join('\\r\\n')], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `process_graph_export_${new Date().toISOString().replace(/[:.]/g, '-')}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
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
      return `<h3>${escapeHtml(node.name)}</h3><div class="sub">PID ${node.pid}${copyBtn(node.pid, 'copy PID')}${node.ppid ? ' · parent ' + node.ppid : ''}${node.username ? ' · ' + escapeHtml(node.username) : ''}${node.container ? ' · container ' + escapeHtml(node.container) : ''}</div>`;
    }

    // Common "investigation" rows of the process panels: executable,
    // command and kill preview, each with its copy button.
    function investigationRows(node) {
      let rows = '';
      if (node.exe) rows += `<div class="field"><label>Executable ${copyBtn(node.exe, 'copy')}</label><div class="val">${escapeHtml(node.exe)}</div></div>`;
      if (node.cmdline) rows += `<div class="field"><label>Command ${copyBtn(node.cmdline, 'copy')}</label><div class="val">${escapeHtml(node.cmdline)}</div></div>`;
      if (node.pid) rows += `<div class="field"><label>Stop this process ${copyBtn('kill ' + node.pid, 'copy')}</label><div class="val" style="color:var(--muted)">kill ${node.pid} <span style="font-size:10px">(to paste into a terminal — double-check before running)</span></div></div>`;
      if (node.integrity_status) {
        const bad = node.integrity_status === 'modified';
        rows += `<div class="field"><label>Binary integrity</label><div class="val" style="color:${bad ? '#F44336' : 'inherit'}">${escapeHtml(node.integrity_status)}${node.exe_sha256 ? ' — SHA256 ' + escapeHtml(node.exe_sha256.slice(0, 16)) + '…' + copyBtn(node.exe_sha256, 'copy') : ''}</div></div>`;
      }
      return rows;
    }

    function fmtIncompleteWarning(node) {
      const issues = node.incomplete_collection || [];
      if (!issues.length) return '';
      return `<div class="field"><label>Incomplete collection</label><div class="val" style="color:#FFC107">${issues.map(escapeHtml).join(', ')}</div></div>`;
    }

    function renderSecurityPanel(node) {
      if (node.type === 'file') return panelHeader(node) + `<div class="field"><label>Path</label><div class="val">${escapeHtml(node.full_path || node.name)}</div></div>`;
      if (node.type === 'connection') {
        return panelHeader(node) + `<div class="field"><label>Nature</label><div class="val">${node.is_remote ? 'Connection to a remote host' : 'Listening / local connection'}</div></div>`;
      }
      const risk = node.risk_level || 'unknown';
      const rulesRisk = node.rules_risk_level || 'unknown';
      const aiRisk = node.ai_risk_level;
      const conns = node.connections || [];
      const externalConns = conns.filter(c => (c.raddr || '') && !c.raddr.startsWith('127.') && !c.raddr.startsWith('::1') && !c.raddr.startsWith('0.0.0.0'));
      const signals = node.rules_signals || [];
      return panelHeader(node) + `
        <div class="field"><label>Final risk level</label>
          <span class="risk-badge" style="background:${riskColor(risk)}22; color:${riskColor(risk)}; border:1px solid ${riskColor(risk)}">${riskLabel(risk)}</span>
          ${node.risk_divergent ? '<span class="risk-badge" style="background:#6C9DFF22; color:#6C9DFF; border:1px solid #6C9DFF; margin-left:6px">diverging opinions</span>' : ''}
        </div>
        <div class="field"><label>Deterministic rules (without AI)</label>
          <span class="risk-badge" style="background:${riskColor(rulesRisk)}22; color:${riskColor(rulesRisk)}; border:1px solid ${riskColor(rulesRisk)}">${riskLabel(rulesRisk)}</span>
          <div class="val" style="margin-top:4px">${signals.map(escapeHtml).join('<br/>')}</div>
        </div>
        ${aiRisk ? `<div class="field"><label>Ollama opinion (AI)</label>
          <span class="risk-badge" style="background:${riskColor(aiRisk)}22; color:${riskColor(aiRisk)}; border:1px solid ${riskColor(aiRisk)}">${riskLabel(aiRisk)}</span>
        </div>` : ''}
        <div class="field"><label>Justification</label><div class="val">${escapeHtml(node.risk_justification || '—')}</div></div>
        <div class="field"><label>Category</label><div class="val">${escapeHtml(node.category || 'unknown')}</div></div>
        <div class="field"><label>External connections</label><div class="val">${externalConns.length} out of ${node.n_connections || 0} total</div></div>
        ${externalConns.length ? fmtConnections(externalConns) : ''}
        ${investigationRows(node)}
        ${fmtIncompleteWarning(node)}
      `;
    }

    function renderDebugPanel(node) {
      if (node.type === 'file') return panelHeader(node) + `<div class="field"><label>Full path</label><div class="val">${escapeHtml(node.full_path || node.name)}</div></div>`;
      if (node.type === 'connection') return panelHeader(node) + `<div class="field"><label>Internal ID</label><div class="val">${escapeHtml(node.id)}</div></div>`;
      return panelHeader(node) + `
        <div class="field"><label>PID / PPID</label><div class="val">${node.pid} / ${node.ppid ?? '—'}</div></div>
        <div class="field"><label>User</label><div class="val">${escapeHtml(node.username || '—')}</div></div>
        <div class="field"><label>CPU / RAM</label><div class="val">${node.cpu}% · ${node.mem}%</div></div>
        <div class="field"><label>Executable ${copyBtn(node.exe, 'copy')}</label><div class="val">${escapeHtml(node.exe || '—')}</div></div>
        <div class="field"><label>Working directory</label><div class="val">${escapeHtml(node.cwd || '—')}</div></div>
        <div class="field"><label>Full command ${copyBtn(node.cmdline, 'copy')}</label><div class="val">${escapeHtml(node.cmdline || '—')}</div></div>
        ${node.container ? `<div class="field"><label>Container</label><div class="val">${escapeHtml(node.container)}</div></div>` : ''}
        ${node.integrity_status ? `<div class="field"><label>Binary integrity</label><div class="val" style="color:${node.integrity_status === 'modified' ? '#F44336' : 'inherit'}">${escapeHtml(node.integrity_status)}</div></div>` : ''}
        <div class="field"><label>Stop this process ${copyBtn('kill ' + node.pid, 'copy')}</label><div class="val" style="color:var(--muted)">kill ${node.pid}</div></div>
        <div class="field"><label>Open files</label><div class="val">${node.n_open_files ?? 0}</div></div>
        <div class="field"><label>Connections (${node.n_connections ?? 0})</label>${fmtConnections(node.connections)}</div>
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
        rows += `<div class="field"><label>connections</label>${fmtConnections(node.connections)}</div>`;
      }
      return panelHeader(node) + rows;
    }

    function renderKnowledgePanel(node) {
      const text = node.knowledge_text || "No explanation available for this item.";
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
      COPY_REGISTRY.length = 0;  // the buttons of the previous panel no longer exist
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
      statsEl.textContent = `${nodes.length} nodes displayed · ${links.length} relations`
        + (hiddenCount > 0 ? ` · ${hiddenCount} hidden by the filters` : '');
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

    document.getElementById('exportCsv').addEventListener('click', exportCsv);
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
    // frame the whole visible graph.
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
    // Keyboard shortcuts (H20): Ctrl+wheel in the browser zooms the PAGE
    // (not the graph) and Ctrl+R reloads the page by default — we
    // intercept these combinations with preventDefault() to redirect
    // them to the graph's camera controls instead. "R" alone also stays
    // active (no browser conflict) for compatibility with the existing
    // behavior.
    // Additional shortcuts (H34): Escape closes the panel, / focuses the
    // search, 1-5 switch the display mode — never intercepted while
    // typing in the search field.
    const MODE_KEYS = { '1': 'type', '2': 'security', '3': 'debug', '4': 'info_verbose', '5': 'knowledge' };
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
    title: str = "Interactive 3D process graph (Ollama-enriched)",
) -> None:
    """Generates a standalone HTML file with an interactive "solar
    system"-style 3D graph (3d-force-graph / three.js): clickable nodes,
    mouse zoom/orbit, details panel, filters by risk level, search.

    Requires a network connection when opening the file (the
    3d-force-graph lib is loaded from unpkg.com, see the CDN rule for
    external scripts of HTML artifacts). No data is sent outside: only
    the loading of the JS script is a network call.
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
# 5bis. Markdown summary report + CSV export (H19)
# ---------------------------------------------------------------------------

def compute_summary_stats(processes: list[ProcessInfo], graph: nx.DiGraph) -> dict:
    """Aggregates the statistics used by the summary report AND by the
    novice assistant's console summary, so there is only one place to
    update if the summary's content changes."""
    by_risk: dict[str, int] = {"low": 0, "medium": 0, "high": 0, "unknown": 0}
    risky: list[ProcessInfo] = []
    incomplete: list[ProcessInfo] = []
    divergent: list[ProcessInfo] = []
    n_enriched = 0
    n_enrich_failed = 0

    for p in processes:
        level = (p.risk or {}).get("final_level", "unknown")
        by_risk[level] = by_risk.get(level, 0) + 1
        if level == "high":
            risky.append(p)
        if p.incomplete_collection:
            incomplete.append(p)
        if (p.risk or {}).get("divergence"):
            divergent.append(p)
        if p.enrichment:
            reason = p.enrichment.get("risk_justification", "")
            if reason in ("ollama_unavailable", "ollama_timeout", "invalid_json_response", "preflight_failed", "outside_enrichment_limit", "enrichment_disabled") or reason.startswith("unexpected_error"):
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
    """Builds the Markdown text of the summary report (H19) and writes it
    to disk if `output_path` is provided. Returns the text in all cases
    for possible console display (novice assistant)."""
    lines = [
        "# Summary report — process analysis",
        "",
        f"- Analysis date: {meta.get('date', '?')}",
        f"- Platform: {meta.get('platform', '?')}",
        f"- Processes analyzed: {stats['total']}",
        f"- AI model used: {meta.get('model') or 'none (enrichment disabled or unavailable)'}",
        "",
        "## Distribution of the final risk level (rules + AI, escalation only)",
        "",
        f"- High: {stats['by_risk'].get('high', 0)}",
        f"- Medium: {stats['by_risk'].get('medium', 0)}",
        f"- Low: {stats['by_risk'].get('low', 0)}",
        f"- Unknown: {stats['by_risk'].get('unknown', 0)}",
        "",
    ]

    if stats["risky"]:
        lines.append("## High-risk processes")
        lines.append("")
        for p in stats["risky"][:30]:
            signals = "; ".join((p.risk or {}).get("rules_signals", [])) or "—"
            lines.append(f"- **{p.name}** (pid {p.pid}, {p.username or 'unknown user'}) — {signals}")
        if len(stats["risky"]) > 30:
            lines.append(f"- … and {len(stats['risky']) - 30} other high-risk process(es).")
        lines.append("")

    if stats["divergent"]:
        lines.append("## Diverging opinions between rules and AI")
        lines.append("")
        lines.append("The final level kept is always the higher of the two (H17), but these divergences deserve a look:")
        lines.append("")
        for p in stats["divergent"][:20]:
            r = p.risk or {}
            lines.append(f"- **{p.name}** (pid {p.pid}) — rules: {r.get('rules_level')}, AI: {r.get('ai_level')}")
        lines.append("")

    lines.append("## Top 5 most resource-consuming processes (CPU + RAM)")
    lines.append("")
    for p in stats["top_consumers"]:
        lines.append(f"- **{p.name}** (pid {p.pid}) — CPU {p.cpu_percent}% · RAM {p.memory_percent}%")
    lines.append("")

    lines.append("## Network and files")
    lines.append("")
    lines.append(f"- Distinct external endpoints observed: {len(stats['external_endpoints'])}")
    lines.append(f"- Files shared between multiple processes: {stats['shared_files']}")
    lines.append("")

    if stats["incomplete"]:
        lines.append("## Incomplete collection (permissions / vanished processes)")
        lines.append("")
        lines.append(f"{len(stats['incomplete'])} processes have at least one uncollected field (access denied most often — normal without elevated rights, see H6/H7).")
        lines.append("")

    lines.append("## AI enrichment")
    lines.append("")
    lines.append(f"- Processes successfully enriched: {stats['n_enriched']}")
    lines.append(f"- Processes not enriched (outside limit, failure, or disabled): {stats['n_enrich_failed']}")
    lines.append("")
    lines.append("_Report generated automatically — the final risk level combines a deterministic rule engine and, "
                  "if available, the opinion of a local Ollama model, by escalation only (H17)._")

    text = "\n".join(lines) + "\n"
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        logger.info("Summary report written: %s", output_path)
    return text


def export_csv(processes: list[ProcessInfo], output_path: Path) -> None:
    """Exports the collected/enriched processes as CSV (one row per
    process, flattened fields), in addition to the existing JSON, for
    direct opening in a spreadsheet."""
    import csv

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "pid", "ppid", "name", "username", "exe", "cwd", "cmdline",
        "cpu_percent", "memory_percent", "n_open_files", "n_connections",
        "category", "probable_role", "final_risk_level",
        "rules_risk_level", "rules_signals", "ai_risk_level",
        "risk_divergent", "incomplete_collection",
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
                "category": enrichment.get("category", ""),
                "probable_role": enrichment.get("probable_role", ""),
                "final_risk_level": risk.get("final_level", "unknown"),
                "rules_risk_level": risk.get("rules_level", "unknown"),
                "rules_signals": "; ".join(risk.get("rules_signals", [])),
                "ai_risk_level": risk.get("ai_level") or "",
                "risk_divergent": risk.get("divergence", False),
                "incomplete_collection": "; ".join(p.incomplete_collection),
            })
    logger.info("CSV export written: %s", output_path)


def export_csv_edges(graph: "nx.DiGraph", processes: list[ProcessInfo], output_path: Path) -> None:
    """Exports the graph RELATIONS as CSV (H28) — one row per edge
    (parent/child, shared file, network connection), with the risk level
    of both endpoints when they are processes. Importable as-is into
    Gephi / Neo4j / a spreadsheet."""
    import csv

    pid_risk = {p.pid: (p.risk or {}).get("final_level", "unknown") for p in processes}

    def _node_label(node_id: str) -> str:
        data = graph.nodes.get(node_id, {})
        return data.get("label", node_id)

    def _node_risk(node_id: str) -> str:
        data = graph.nodes.get(node_id, {})
        if data.get("kind") == "process":
            return pid_risk.get(data.get("pid"), "unknown")
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
    logger.info("CSV export of the relations written: %s (%d edges)", output_path, graph.number_of_edges())


# ---------------------------------------------------------------------------
# 5ter. Run history + snapshot comparison (H29)
# ---------------------------------------------------------------------------

HISTORY_MAX_RUNS = 50


def snapshot_from_processes(processes: list[ProcessInfo]) -> dict:
    """LIGHTWEIGHT snapshot of a run (not the open files nor the detailed
    connections) — sufficient to compare two runs: process
    appearances/disappearances, risk evolutions, CPU/RAM."""
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
                "final_level": (p.risk or {}).get("final_level", "unknown"),
            }
            for p in processes
        ],
    }


def append_history(processes: list[ProcessInfo], history_path: Path) -> Optional[dict]:
    """Adds this run's snapshot to the JSON history (capped at
    HISTORY_MAX_RUNS entries, oldest ones evicted) and returns the
    PREVIOUS snapshot (useful for --compare without an argument)."""
    history: list[dict] = []
    if history_path.exists():
        try:
            loaded = json.loads(history_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                history = loaded
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Unreadable history (%s) — will start from scratch: %s", history_path, exc)
    previous = history[-1] if history else None
    history.append(snapshot_from_processes(processes))
    history = history[-HISTORY_MAX_RUNS:]
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    logger.info("Snapshot added to the history: %s (%d run(s) kept)", history_path, len(history))
    return previous


def _snapshot_key(entry: dict) -> tuple:
    # A process is identified by (pid, name): a pid alone can be reused
    # by the OS between two runs spaced in time.
    return (entry.get("pid"), entry.get("name"))


def compare_snapshots(previous: dict, processes: list[ProcessInfo]) -> str:
    """Compares the current run to a previous snapshot and renders a text
    report: new processes, vanished ones, risk level changes, biggest
    CPU/RAM evolutions."""
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
        if prev_e.get("final_level") != curr_e.get("final_level"):
            risk_changes.append((curr_e, prev_e.get("final_level"), curr_e.get("final_level")))
        d_cpu = (curr_e.get("cpu_percent") or 0) - (prev_e.get("cpu_percent") or 0)
        d_mem = (curr_e.get("memory_percent") or 0) - (prev_e.get("memory_percent") or 0)
        if abs(d_cpu) >= 1.0 or abs(d_mem) >= 1.0:
            deltas.append((curr_e, d_cpu, d_mem))
    deltas.sort(key=lambda t: abs(t[1]) + abs(t[2]), reverse=True)

    lines = [
        "=" * 64,
        "COMPARISON WITH THE PREVIOUS SNAPSHOT",
        f"  previous: {previous.get('date', '?')} ({len(prev_by_key)} processes)",
        f"  current : {current['date']} ({len(curr_by_key)} processes)",
        "=" * 64,
        "",
        f"New processes ({len(new_keys)}):",
    ]
    for k in sorted(new_keys, key=lambda k: -(curr_by_key[k].get("cpu_percent") or 0))[:25]:
        e = curr_by_key[k]
        lines.append(f"  + pid {e['pid']:>7}  {e['name']}  (risk: {e['final_level']}, cpu {e['cpu_percent']}%)")
    if len(new_keys) > 25:
        lines.append(f"  ... and {len(new_keys) - 25} others")
    lines += ["", f"Vanished processes ({len(gone_keys)}):"]
    for k in sorted(gone_keys)[:25]:
        e = prev_by_key[k]
        lines.append(f"  - pid {e['pid']:>7}  {e['name']}")
    if len(gone_keys) > 25:
        lines.append(f"  ... and {len(gone_keys) - 25} others")
    lines += ["", f"Risk level changes ({len(risk_changes)}):"]
    for e, old, new in risk_changes:
        lines.append(f"  ~ pid {e['pid']:>7}  {e['name']}  : {old} -> {new}")
    lines += ["", f"Biggest CPU/RAM evolutions (threshold ±1 point, top 15 out of {len(deltas)}):"]
    for e, d_cpu, d_mem in deltas[:15]:
        lines.append(f"  ~ pid {e['pid']:>7}  {e['name']}  cpu {d_cpu:+.1f}%  ram {d_mem:+.1f}%")
    if not risk_changes and not new_keys and not gone_keys and not deltas:
        lines.append("  (no notable difference)")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5quater. Forensic report of a single process (--pid, H30)
# ---------------------------------------------------------------------------

def filter_process_tree(processes: list[ProcessInfo], target_pid: int) -> list[ProcessInfo]:
    """Reduces the list to the target process + all its ancestors + all
    its descendants (the relevant subtree for a forensic analysis)."""
    by_pid = {p.pid: p for p in processes}
    if target_pid not in by_pid:
        return []
    keep: set[int] = {target_pid}
    # Ancestors (safety bound against a corrupted ppid cycle)
    cursor, hops = by_pid[target_pid], 0
    while cursor.ppid in by_pid and cursor.ppid not in keep and hops < 100:
        keep.add(cursor.ppid)
        cursor = by_pid[cursor.ppid]
        hops += 1
    # Descendants (BFS)
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
    """Detailed text report of ONE process: full identity, risk and
    signals, connections, open files, ancestors/descendants tree."""
    risk = target.risk or {}
    by_pid = {p.pid: p for p in tree}
    lines = [
        "=" * 64,
        f"DETAILED REPORT — {target.name} (pid {target.pid})",
        "=" * 64,
        "",
        f"  User               : {target.username or '—'}",
        f"  Executable         : {target.exe or '—'}",
        f"  Working directory  : {target.cwd or '—'}",
        f"  Command line       : {target.cmdline or '—'}",
        f"  CPU / RAM          : {target.cpu_percent}% / {target.memory_percent}%",
        f"  Container          : {target.container or 'no (host)'}",
    ]
    if target.exe_sha256:
        lines.append(f"  Executable SHA256  : {target.exe_sha256} ({target.integrity_status})")
    lines += [
        "",
        f"  Final risk level : {risk.get('final_level', 'unknown').upper()}",
        f"  Rule-based level : {risk.get('rules_level', 'unknown')}",
    ]
    for s in risk.get("rules_signals", []):
        lines.append(f"    - {s}")
    if risk.get("ai_level"):
        lines.append(f"  Ollama opinion   : {risk['ai_level']} ({risk.get('ai_justification', '')})")
    enrichment = target.enrichment or {}
    if enrichment.get("probable_role") and enrichment.get("probable_role") != "not enriched":
        lines += ["", f"  Probable role : {enrichment['probable_role']}",
                  f"  Category      : {enrichment.get('category', 'unknown')}"]
    if target.incomplete_collection:
        lines += ["", "  Incomplete collection: " + ", ".join(target.incomplete_collection)]

    lines += ["", f"Network connections ({len(target.connections)}):"]
    for c in target.connections[:30] or []:
        lines.append(f"  [{c.get('protocol', '?').upper():4}] {c.get('laddr') or '?'} -> {c.get('raddr') or '—'}  {c.get('status', '')}")
    if not target.connections:
        lines.append("  (none)")

    lines += ["", f"Open files ({len(target.open_files)}):"]
    for path in target.open_files[:30]:
        lines.append(f"  {path}")
    if len(target.open_files) > 30:
        lines.append(f"  ... and {len(target.open_files) - 30} others")
    if not target.open_files:
        lines.append("  (none visible — permissions?)")

    # Ancestor chain then indented descendant tree
    ancestors = []
    cursor, hops = target, 0
    while cursor.ppid in by_pid and hops < 100:
        cursor = by_pid[cursor.ppid]
        if cursor.pid in [a.pid for a in ancestors] + [target.pid]:
            break
        ancestors.append(cursor)
        hops += 1
    lines += ["", "Process tree:"]
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
            marker += "   <== TARGET"
        lines.append(marker)
        for child in sorted(children_of.get(p.pid, []), key=lambda c: c.pid):
            if child.pid not in visited:
                visited.add(child.pid)
                _walk(child, depth + 1, visited)

    _walk(target, depth_target, {target.pid})
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5quinquies. Sandbox mode (--sandbox, H31): replays a JSON export
# ---------------------------------------------------------------------------

def load_sandbox_processes(path: Path) -> list[ProcessInfo]:
    """Rebuilds ProcessInfo objects from a JSON file in --json-export
    format, instead of collecting the real system. Allows testing the
    rule engine / the whitelist-blacklist configuration / the rendering
    on simulated or elsewhere-captured data, without touching the
    system. Missing fields take neutral values."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("The sandbox file must contain a LIST of processes (--json-export format).")
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
            incomplete_collection=list(entry.get("incomplete_collection", []) or []),
            cmdline_empty=not entry.get("cmdline"),
            container=entry.get("container"),
        ))
    logger.info("Sandbox mode: %d processes loaded from %s (no system collection).", len(processes), path)
    return processes


# ---------------------------------------------------------------------------
# 6. Cross-platform opening of the results
# ---------------------------------------------------------------------------

def open_path_cross_platform(path: Path) -> None:
    """Opens a file with the system's default application, without
    depending on `open` (macOS only, used by the old .command
    launchers). Never crashes the script: an automatic opening failure
    is logged at DEBUG level, not a fatal error."""
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
    except Exception as exc:  # defensive: auto-opening is a comfort, not a prerequisite
        logger.debug("Could not automatically open %s: %s", path, exc)


# ---------------------------------------------------------------------------
# 7. Interactive assistant (novice) — replaces the separate .command launcher
# ---------------------------------------------------------------------------

def _prompt(message: str, default: str) -> str:
    try:
        raw = input(f"{message} [{default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        raw = ""
    return raw or default


def run_wizard() -> argparse.Namespace:
    """Minimal interactive assistant (2 questions), triggered when the
    script is launched without any argument — typically a double-click
    on the PyInstaller executable by a novice user (H8)."""
    print("=" * 56)
    print(" System process analyzer — startup assistant")
    print("=" * 56)
    print()
    print("Tip: for advanced usage (command-line options),")
    print("relaunch with --help instead of double-clicking.")
    print()

    raw = _prompt(
        "Maximum number of processes to include in the graph (the most active have priority)",
        "150",
    )
    try:
        max_processes = int(raw)
        if max_processes <= 0:
            raise ValueError
    except ValueError:
        print(f"Invalid value ('{raw}'), using the default value: 150")
        max_processes = 150

    print()
    host = "http://localhost:11434"
    print(f"Looking for available Ollama models ({host})...")
    models = _detect_ollama_models(host)

    if not models:
        # Ollama is not reachable at all -> offer an automatic
        # installation suited to the OS (H12), explicit consent required.
        if not _ollama_reachable(host) and ensure_ollama_ready(host):
            models = _detect_ollama_models(host)
        # Either Ollama is already running without any model, or it was
        # just installed but remains empty -> offer to directly download
        # the default model rather than leaving the user without AI.
        if not models and _ollama_reachable(host):
            print("No Ollama model installed locally.")
            size = "~1.3 GB, mini model suited to mobile" if IS_ANDROID else "several GB"
            answer = _prompt(
                f"Download the default model ({DEFAULT_OLLAMA_MODEL}, {size}) now? (y/n)",
                "y",
            )
            if answer.strip().lower() in ("y", "yes"):
                if pull_ollama_model(DEFAULT_OLLAMA_MODEL, host):
                    models = _detect_ollama_models(host)

    model: Optional[str] = None
    if models:
        print("Detected models:")
        for i, m in enumerate(models, start=1):
            print(f"  {i}) {m}")
        print("  0) None (disable AI enrichment)")
        raw = _prompt("Which model to use?", "1")
        try:
            choice = int(raw)
        except ValueError:
            choice = 1
        if 1 <= choice <= len(models):
            model = models[choice - 1]
            print(f"Selected model: {model}")
        else:
            print("AI enrichment disabled.")
    else:
        print("The analysis will continue without AI enrichment.")
        print("(To enable it later: install Ollama, run 'ollama serve', then "
              f"'ollama pull {DEFAULT_OLLAMA_MODEL}')")

    # H8: the number of AI-enriched processes is derived automatically
    # from the max number of processes rather than asking a 3rd question.
    enrich_limit = min(max_processes, 40)

    base_dir = Path(sys.executable).resolve().parent if IS_FROZEN else Path.cwd()
    out_dir = base_dir / "outputs"
    stamp = time.strftime("%Y%m%d_%H%M%S")

    print()
    print(f"Output directory: {out_dir}")
    print()

    # H19: the novice assistant produces ONLY the interactive 3D graph —
    # no PNG, JSON, CSV or report written to disk by default. For those
    # formats, relaunch with the CLI options (--png / --json-export /
    # --csv-export / --report), see --help.
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
    """Continuous monitoring mode (H32): periodically re-collects, runs
    ONLY the collection + the rule engine (never Ollama in a loop — AI
    enrichment remains a manual/one-shot act), regenerates the HTML at
    each cycle and displays the differences between cycles (new
    processes, vanished ones, risk changes). Ctrl+C to stop cleanly."""
    interval = max(5.0, float(getattr(args, "interval", 60.0)))
    baseline = load_baseline(args.baseline_file) if getattr(args, "baseline", False) or args.baseline_file.exists() else {}
    previous_snapshot: Optional[dict] = None
    cycle = 0
    logger.info("Monitoring mode: one cycle every %.0fs (Ctrl+C to stop). Ollama disabled in the loop.", interval)
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
                p.enrichment = _default_enrichment("watch_mode_no_ai")
                finalize_risk(p)
            if getattr(args, "baseline", False):
                update_baseline(processes, args.baseline_file)
                baseline = load_baseline(args.baseline_file)

            graph = build_graph(processes, max_conn_total=args.max_conn_total)
            if not args.no_html:
                render_interactive_3d(graph, processes, args.html_output,
                                      title=f"Process monitoring — cycle {cycle}")

            by_risk: dict[str, int] = {}
            for p in processes:
                level = (p.risk or {}).get("final_level", "unknown")
                by_risk[level] = by_risk.get(level, 0) + 1
            print(f"\n[cycle {cycle} — {time.strftime('%H:%M:%S')}] {len(processes)} processes | "
                  f"high risk: {by_risk.get('high', 0)} · medium: {by_risk.get('medium', 0)} · "
                  f"low: {by_risk.get('low', 0)}")
            for p in sorted(processes, key=lambda p: p.score, reverse=True)[:5]:
                print(f"    top: {p.name:<28} pid {p.pid:>7}  cpu {p.cpu_percent:5.1f}%  ram {p.memory_percent:5.1f}%")
            if previous_snapshot is not None:
                print(compare_snapshots(previous_snapshot, processes))
            previous_snapshot = snapshot_from_processes(processes)

            elapsed = time.time() - cycle_start
            time.sleep(max(1.0, interval - elapsed))
    except KeyboardInterrupt:
        print(f"\nMonitoring stopped after {cycle} cycle(s).")
        return 0


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyzes system processes, their related files and their relationships, "
                    "enriches via local Ollama, exports a PNG graph."
    )
    parser.add_argument("--output", type=Path, default=Path("process_graph.png"),
                         help="Path of the output PNG if --png is used (default: process_graph.png)")
    parser.add_argument("--html-output", type=Path, default=Path("process_graph_3d.html"),
                         help="Path of the interactive 3D HTML (default: process_graph_3d.html)")
    parser.add_argument("--no-html", action="store_true",
                         help="Disables the generation of the interactive 3D graph")
    parser.add_argument("--png", action="store_true",
                         help="ALSO generates a static PNG (H19: disabled by default, "
                              "only the interactive 3D graph is produced by default)")
    parser.add_argument("--model", default=DEFAULT_MODEL_ARG,
                         help=f"Ollama model to use (default: {DEFAULT_MODEL_ARG} — "
                              "mini on Android/Termux, medium elsewhere)")
    parser.add_argument("--ollama-host", default="http://localhost:11434",
                         help="URL of the Ollama API (default: http://localhost:11434)")
    parser.add_argument("--enrich-limit", type=int, default=25,
                         help="Max number of processes enriched via Ollama, "
                              "sorted by CPU+RAM consumption (default: 25)")
    parser.add_argument("--enrich-all", action="store_true",
                         help="Enriches all collected processes (ignores --enrich-limit)")
    parser.add_argument("--no-enrich", action="store_true",
                         help="Completely disables the Ollama call")
    parser.add_argument("--min-score", type=float, default=0.0,
                         help="Minimum score (cpu%%+mem%%) to include a process (default: 0)")
    parser.add_argument("--max-processes", type=int, default=None,
                         help="Max number of processes included in the graph, keeps the most active "
                              "(default: no limit in CLI; 150 in the interactive assistant)")
    parser.add_argument("--max-conn-per-process", type=int, default=20,
                         help="Max raw network connections collected per process (default: 20)")
    parser.add_argument("--max-conn-total", type=int, default=300,
                         help="Max connection edges drawn in total (default: 300)")
    parser.add_argument("--max-workers", type=int, default=2,
                         help="Parallelism of the Ollama calls (default: 2 — a local LLM most often "
                              "serves requests serially, heavy parallelization only stacks requests "
                              "in a queue until they time out)")
    parser.add_argument("--timeout", type=float, default=120.0,
                         help="Timeout per Ollama call in seconds (default: 120 — a multi-billion "
                              "parameter model on CPU can be slow)")
    parser.add_argument("--json-export", type=Path, default=None,
                         help="Also exports the collected/enriched data as JSON (disabled by default)")
    parser.add_argument("--csv-export", type=Path, default=None,
                         help="Also exports the data as CSV, one row per process (disabled by default)")
    parser.add_argument("--report", type=Path, default=None,
                         help="Writes a Markdown summary report to this path (disabled by default)")
    parser.add_argument("-v", "--verbose", action="store_true", help="DEBUG logs")

    # --- Additional execution modes ---
    parser.add_argument("--watch", action="store_true",
                         help="Continuous monitoring mode: periodically re-collects (collection + rules "
                              "only, NEVER an Ollama call in the loop), displays the differences between "
                              "cycles and regenerates the HTML. Ctrl+C to stop.")
    parser.add_argument("--interval", type=float, default=60.0,
                         help="Interval in seconds between two --watch cycles (default: 60)")
    parser.add_argument("--pid", type=int, default=None,
                         help="Forensic analysis of ONE process: detailed text report (identity, risk, "
                              "connections, files, ancestors+descendants tree); the HTML is restricted to this subtree")
    parser.add_argument("--compare", type=Path, nargs="?", const=Path("__previous__"), default=None,
                         help="Compares the current run to a previous snapshot: path of a JSON export "
                              "(--json-export) OR no value to compare to the previous run from the history")
    parser.add_argument("--history-file", type=Path, default=Path("outputs/history.json"),
                         help="Snapshot history file, fed automatically at each run "
                              "(default: outputs/history.json; 50 runs kept)")
    parser.add_argument("--no-history", action="store_true",
                         help="Disables the automatic recording of the snapshot in the history")
    parser.add_argument("--sandbox", type=Path, default=None,
                         help="Sandbox mode: reads the processes from a JSON file (--json-export format) "
                              "instead of the real system — to test rules/config/rendering risk-free")
    parser.add_argument("--preload-model", action="store_true",
                         help="Downloads/prepares the Ollama model (--model) then exits, without analysis — "
                              "to prepare for offline usage")

    # --- Analysis and enrichment ---
    parser.add_argument("--config", type=Path, default=None,
                         help="Whitelist/blacklist configuration file (simple YAML or JSON): "
                              "whitelist patterns neutralize the rule engine's path signals, "
                              "blacklist patterns force the 'high' level")
    parser.add_argument("--check-integrity", action="store_true",
                         help="Computes the SHA256 of each executable and compares it to the reference "
                              "database (--integrity-db); a modified fingerprint is a 'high' risk signal")
    parser.add_argument("--integrity-db", type=Path, default=Path("outputs/integrity.json"),
                         help="Reference database of the SHA256 fingerprints (default: outputs/integrity.json)")
    parser.add_argument("--baseline", action="store_true",
                         help="Adds this run to the performance baseline (CPU/RAM per process name); "
                              "from 3 samples on, deviations >2 standard deviations become risk signals")
    parser.add_argument("--baseline-file", type=Path, default=Path("outputs/baseline.json"),
                         help="Baseline file (default: outputs/baseline.json)")
    parser.add_argument("--cache", action="store_true",
                         help="Persistent SQLite cache of the Ollama enrichments: an identical process "
                              "(name+exe+cmdline) already analyzed is served again without an LLM call")
    parser.add_argument("--cache-file", type=Path, default=Path("outputs/enrich_cache.sqlite3"),
                         help="Enrichment cache file (default: outputs/enrich_cache.sqlite3)")
    parser.add_argument("--cache-ttl-days", type=float, default=7.0,
                         help="Validity duration of the cache entries in days (default: 7)")
    parser.add_argument("--retry-failed", type=int, default=0, metavar="N",
                         help="Retries up to N times the enrichments in transient failure "
                              "(timeout, saturated Ollama), with exponential backoff 1s/2s/4s...")
    parser.add_argument("--plugin", type=Path, default=None,
                         help="User Python plugin exposing enrich(process_info: dict) -> dict, "
                              "applied to each process after the Ollama enrichment")

    # --- Additional exports ---
    parser.add_argument("--csv-edges", type=Path, default=None,
                         help="Exports the graph RELATIONS as CSV (source, target, kind, risks) — "
                              "importable into Gephi/Neo4j")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    raw_args = sys.argv[1:] if argv is None else argv
    # No argument -> novice interactive assistant (H8); otherwise classic CLI.
    wizard_mode = len(raw_args) == 0

    args = run_wizard() if wizard_mode else parse_args(raw_args)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # --preload-model: prepare Ollama + download the model, then exit —
    # no analysis (H33). Useful to prepare for offline usage.
    if getattr(args, "preload_model", False):
        if not ensure_ollama_ready(args.ollama_host):
            logger.error("Ollama unavailable — cannot preload the model.")
            return 1
        ok, message = check_ollama_available(args.model, args.ollama_host)
        if ok:
            logger.info("Model %s is already available locally — nothing to download.", args.model)
            return 0
        logger.info("Downloading model %s... (%s)", args.model, message)
        return 0 if pull_ollama_model(args.model, args.ollama_host) else 1

    # Whitelist/blacklist configuration (H23), loaded BEFORE any risk
    # computation (including in watch mode).
    if getattr(args, "config", None):
        try:
            USER_CONFIG.update(load_user_config(args.config))
        except (OSError, ValueError) as exc:
            logger.error("Unreadable configuration (%s): %s — stopping.", args.config, exc)
            return 1

    # Continuous monitoring mode (H32): dedicated loop, never Ollama.
    if getattr(args, "watch", False):
        return run_watch(args)

    if getattr(args, "sandbox", None):
        try:
            processes = load_sandbox_processes(args.sandbox)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.error("Unreadable sandbox file (%s): %s — stopping.", args.sandbox, exc)
            return 1
    else:
        logger.info("Collecting system processes...")
        processes = collect_processes(min_score=args.min_score, max_conn_per_process=args.max_conn_per_process)
    if not processes:
        logger.error("No process collected (insufficient permissions?). Stopping.")
        if wizard_mode or IS_FROZEN:
            _pause_before_exit()
        return 1

    processes = limit_processes(processes, getattr(args, "max_processes", None))

    # --pid mode: reduce the analysis to the target process's subtree
    # (ancestors + descendants) BEFORE enrichment — the detailed text
    # report is printed further down, once the risk is finalized.
    target_pid = getattr(args, "pid", None)
    if target_pid is not None:
        tree = filter_process_tree(processes, target_pid)
        if not tree:
            logger.error("PID %d not found among the collected processes.", target_pid)
            return 1
        logger.info("Mode --pid %d: analysis restricted to %d processes (target + ancestors + descendants).",
                    target_pid, len(tree))
        processes = tree

    # Integrity check (H22) BEFORE the rule engine, so the "modified"
    # status is a risk signal.
    if getattr(args, "check_integrity", False):
        check_integrity(processes, args.integrity_db)

    # Performance baseline (H24): statistical anomalies become rule
    # engine signals as soon as 3 samples are recorded.
    baseline_file = getattr(args, "baseline_file", Path("outputs/baseline.json"))
    baseline = load_baseline(baseline_file) if (getattr(args, "baseline", False) or baseline_file.exists()) else {}

    # Rule engine (H17): always computed, independently of Ollama — it
    # is the floor of the final risk level, never the sole source.
    for p in processes:
        p.risk = compute_rule_based_risk(p, baseline=baseline)

    if getattr(args, "baseline", False):
        update_baseline(processes, baseline_file)

    logger.info("Building the relation graph...")
    graph = build_graph(processes, max_conn_total=args.max_conn_total)
    logger.info("Graph: %d nodes, %d edges", graph.number_of_nodes(), graph.number_of_edges())

    if args.no_enrich:
        logger.info("Ollama enrichment disabled (--no-enrich).")
        for p in processes:
            p.enrichment = _default_enrichment("enrichment_disabled")
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

    # User plugin (H27), applied after the Ollama enrichment.
    if getattr(args, "plugin", None):
        apply_plugin(processes, args.plugin)

    # Combine rules + AI opinion by escalation only (H17), now that the
    # enrichment (or its fallback) has filled p.enrichment for each one.
    for p in processes:
        finalize_risk(p)

    # History + comparison (H29). The snapshot is recorded AFTER
    # finalize_risk so the compared levels are the definitive ones.
    previous_from_history = None
    if not getattr(args, "no_history", False) and not getattr(args, "sandbox", None):
        try:
            previous_from_history = append_history(processes, getattr(args, "history_file", Path("outputs/history.json")))
        except OSError as exc:
            logger.warning("Could not write the history: %s", exc)

    compare_arg = getattr(args, "compare", None)
    if compare_arg is not None:
        previous = None
        if str(compare_arg) == "__previous__":
            previous = previous_from_history
            if previous is None:
                logger.warning("--compare without an argument: no previous snapshot in the history — comparison skipped.")
        else:
            try:
                loaded = json.loads(Path(compare_arg).read_text(encoding="utf-8"))
                if isinstance(loaded, list):  # --json-export format
                    previous = {"date": "?", "processes": [
                        {"pid": e.get("pid"), "name": e.get("name"), "exe": e.get("exe"),
                         "cpu_percent": e.get("cpu_percent"), "memory_percent": e.get("memory_percent"),
                         "final_level": (e.get("risk") or {}).get("final_level", "unknown")}
                        for e in loaded if isinstance(e, dict)
                    ]}
                elif isinstance(loaded, dict) and "processes" in loaded:  # snapshot format
                    previous = loaded
                else:
                    logger.error("Unrecognized snapshot format: %s", compare_arg)
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("Unreadable comparison snapshot (%s): %s", compare_arg, exc)
        if previous is not None:
            print(compare_snapshots(previous, processes))

    # --pid mode: detailed forensic text report of the target process.
    if target_pid is not None:
        target = next(p for p in processes if p.pid == target_pid)
        print(render_pid_report(target, processes))

    # H19: default output reduced to the interactive 3D graph only. PNG,
    # JSON, CSV and report remain opt-in (CLI options), never written
    # without an explicit request.
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
                "incomplete_collection": p.incomplete_collection,
                "container": p.container,
                "exe_sha256": p.exe_sha256,
                "integrity_status": p.integrity_status,
            }
            for p in processes
        ]
        args.json_export.parent.mkdir(parents=True, exist_ok=True)
        args.json_export.write_text(json.dumps(export_data, indent=2, ensure_ascii=False))
        logger.info("JSON export written: %s", args.json_export)

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

    logger.info("Done.")

    if wizard_mode:
        print()
        print("Result:")
        print(f"  Interactive 3D graph: {args.html_output}")
        print()
        print("(To also get a PNG, a JSON/CSV export or a Markdown summary "
              "report: relaunch with --png / --json-export / --csv-export / --report, see --help)")
        print()
        # H13: the interactive 3D graph is the main deliverable for a
        # novice user -> it is the one we open automatically (the PNG
        # and JSON are still written to disk, but not opened, so as not
        # to stack an image viewer window on top of the browser — the
        # user can always open the PNG themselves).
        if not args.no_html:
            print("Opening the interactive 3D graph...")
            open_path_cross_platform(args.html_output)

    if wizard_mode or IS_FROZEN:
        _pause_before_exit()

    return 0


if __name__ == "__main__":
    try:
        _exit_code = main()
    except KeyboardInterrupt:
        print("\nInterrupted by the user.")
        _exit_code = 130
    except Exception:
        # Safety net for a PyInstaller --console executable: without it,
        # an unforeseen exception closes the window instantly and a
        # novice never sees the error message.
        import traceback
        print("\n" + "=" * 56)
        print("An unexpected error occurred:")
        print("=" * 56)
        traceback.print_exc()
        if IS_FROZEN or len(sys.argv) == 1:
            _pause_before_exit()
        _exit_code = 1
    sys.exit(_exit_code)
