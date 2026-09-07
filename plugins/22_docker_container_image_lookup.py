"""If the process is containerized and the `docker` CLI is available,
enriches with the image name/tag via `docker inspect` -- turning a bare
container id into something readable. Read-only (inspect never mutates
anything), best-effort (silently no-ops if docker isn't installed, isn't
running, or the id isn't a container docker itself knows about -- e.g.
podman/containerd-managed containers). Uses a LIST of subprocess
arguments, never a shell string, so the container id can't be
interpreted as shell syntax.
"""
from __future__ import annotations

import json
import shutil
import subprocess


def enrich(process_info):
    container = process_info.get("container")
    if not container or not shutil.which("docker"):
        return {}
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{json .Config.Image}}", container],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    try:
        image = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return {}
    return {"container_image": image}
