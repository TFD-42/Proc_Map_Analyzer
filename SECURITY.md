# Security Policy

## Supported Versions

This project does not yet have a tagged version (local repository, no first tag/release yet). Until a release exists, only the current working copy (default branch) is "supported" — this section will be replaced with a real version table once the first tag exists.

## Scope

`process_analyzer_allinone.py` analyzes processes **on the machine it runs on**, sends no collected data to any external service, and opens no network port. The project's two network touchpoints are documented in the README (Privacy section):

- loading the `3d-force-graph` library from a public CDN (`unpkg.com`) when the generated HTML file is opened;
- calls to a local **Ollama** server (`http://localhost:11434` by default, configurable).

A vulnerability in this project would typically involve: unintended code execution via a generated HTML file (e.g., process data improperly escaped before injection into HTML/JS), privilege escalation via the installers (`install.sh` / `install.ps1`), or a leak of local data (paths, IPs, username) beyond what is documented.

## Reporting a Vulnerability

Please **do not open a public issue** for a security problem until it has been fixed.

- **Preferred**: [GitHub private vulnerability reporting](https://github.com/TFD-42/Proc_Map_Analyzer/security/advisories/new).
- **Alternative**: contact the maintainer privately via GitHub ([@TFD-42](https://github.com/TFD-42)) — no email channel is published for this project.

Please include: a description of the vulnerability and its potential impact, reproduction steps (or a proof of concept), and known mitigations if any.

This is a study/local project maintained on a best-effort basis (no formal SLA): expect an initial response time on the order of a few days rather than a guaranteed 24-hour reply.
