"""Orchestration: run, validate, and the shared gate context."""

from __future__ import annotations

from .run import (
    RunOutcome,
    execute_job,
    execute_run,
    gate_context,
    gate_names,
    palette_for,
    run_dir_for,
)
from .verify import verify_pack, verify_run

__all__ = [
    "RunOutcome",
    "execute_job",
    "execute_run",
    "gate_context",
    "gate_names",
    "palette_for",
    "run_dir_for",
    "verify_pack",
    "verify_run",
]
