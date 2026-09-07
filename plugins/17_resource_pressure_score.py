"""Replaces a crude "cpu > 80 => alert" with a graded 0-100 resource
pressure score blending CPU and memory, plus a label -- so a process at
82% CPU / 1% mem and one at 45% CPU / 60% mem both surface instead of
only the first, and so the panel can sort/filter by score instead of a
boolean.
"""
from __future__ import annotations

_CPU_WEIGHT = 0.7
_MEM_WEIGHT = 0.3


def _label(score):
    if score >= 90:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 40:
        return "moderate"
    return "low"


def enrich(process_info):
    cpu = min(process_info.get("cpu_percent") or 0.0, 100.0)
    mem = min(process_info.get("memory_percent") or 0.0, 100.0)
    score = round(cpu * _CPU_WEIGHT + mem * _MEM_WEIGHT, 1)
    return {"resource_pressure_score": score, "label": _label(score)}
