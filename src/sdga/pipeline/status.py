"""`sdga status`: what the backend is running and where the last run got to.

This is a read-only command. It asks the backend for its queue (best effort — an unreachable
server is reported, not raised) and summarises the newest `run.json`, including how many
planned requests never started, which is the difference between "failed" and "still going"
after a kill.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..backends.base import GenerationBackend
from ..config import Config
from ..errors import BackendError, SdgaError
from .run import run_dir_for

JOB_STATES = ("accepted", "rejected", "failed", "superseded")


@dataclass(frozen=True)
class StatusReport:
    backend: dict[str, Any]
    run: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {"schema": 1, "backend": self.backend, "run": self.run}

    def render(self) -> str:
        lines: list[str] = []
        backend = self.backend
        lines.append(f"BACKEND  {backend.get('kind')}  {backend.get('url', '')}".rstrip())
        if "error" in backend:
            lines.append(f"  queue unavailable: {backend['error']}")
        else:
            lines.append(
                f"  queue: {backend.get('running', 0)} running, {backend.get('pending', 0)} pending"
            )

        if self.run is None:
            lines.append("RUN      none yet - `sdga run` generates the first one")
            return "\n".join(lines)

        run = self.run
        counts = run["counts"]
        summary = ", ".join(f"{counts[state]} {state}" for state in JOB_STATES)
        lines.append(f"RUN      {run['run_id']}  {run['status']}  ({summary})")
        not_started = int(run.get("not_started") or 0)
        if not_started:
            lines.append(
                f"  {not_started} of {run['planned']} planned request(s) not started - "
                f"`sdga run --resume {run['run_id']}` continues this run"
            )
        for job in run["jobs"]:
            candidate = f" (candidate {job['candidate']})" if job["candidate"] else ""
            lines.append(f"  {job['asset_id']:<30} {job['status']}{candidate}")
        return "\n".join(lines)


def _backend_report(config: Config, backend: GenerationBackend) -> dict[str, Any]:
    url = "fake://local" if backend.kind == "fake" else config.backend.url
    report: dict[str, Any] = {"kind": backend.kind, "url": url}
    try:
        queue = backend.queue()
    except BackendError as exc:
        report["error"] = exc.detail
        return report
    report["running"] = len(queue.running)
    report["pending"] = len(queue.pending)
    report["running_ids"] = list(queue.running)
    report["pending_ids"] = list(queue.pending)
    return report


def _run_report(config: Config, run_id: str | None) -> dict[str, Any] | None:
    try:
        run_dir = run_dir_for(config, run_id)
    except SdgaError:
        if run_id:
            raise
        return None
    record: Mapping[str, Any] = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    jobs = list(record.get("jobs") or [])
    counts = {state: 0 for state in JOB_STATES}
    for job in jobs:
        status = str(job.get("status"))
        if status in counts:
            counts[status] += 1
    planned = int(record.get("planned") or len(jobs))
    return {
        "run_id": record.get("run_id") or run_dir.name,
        "status": record.get("status"),
        "planned": planned,
        "not_started": max(0, planned - len(jobs)),
        "counts": counts,
        "jobs": [
            {
                "asset_id": job.get("asset_id"),
                "status": job.get("status"),
                "candidate": int(job.get("candidate") or 0),
            }
            for job in sorted(
                jobs, key=lambda item: (str(item.get("asset_id")), item.get("candidate"))
            )
        ],
    }


def collect(
    config: Config, backend: GenerationBackend, *, run_id: str | None = None
) -> StatusReport:
    return StatusReport(
        backend=_backend_report(config, backend),
        run=_run_report(config, run_id),
    )


__all__ = ["JOB_STATES", "StatusReport", "collect"]
