"""Stage 6: review (docs/04-pipeline-stages.md §6).

Machine gates cannot answer "does this look like the character". Review is the human gate:
decisions are appended to `run.json` rather than overwriting a status, and the contact sheet
is written as data (`review.html`) so a reviewer can compare reference and result without a
running pipeline.

The HTML is deliberately self-contained: relative paths, no scripts, no external assets. It
is a review artifact, not a UI.
"""

from __future__ import annotations

import html
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Config
from .errors import SdgaError

APPROVED = "approved"
REJECTED = "rejected"
SUPERSEDED = "superseded"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _display(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def record_review(
    config: Config,
    run_dir: Path,
    asset_id: str,
    decision: str,
    *,
    note: str | None = None,
    by: str = "human",
) -> dict[str, Any]:
    """Append a decision to `run.json` and stamp the asset's jobs with the latest one."""
    if decision not in (APPROVED, REJECTED):
        raise SdgaError(
            f"unknown review decision {decision!r}",
            remedy="use --approve or --reject",
        )
    path = run_dir / "run.json"
    if not path.is_file():
        raise SdgaError(f"no run.json in {run_dir}", remedy="pass --run <run_id>")
    record = json.loads(path.read_text(encoding="utf-8"))

    jobs = [job for job in record.get("jobs", []) if job.get("asset_id") == asset_id]
    if not jobs:
        known = ", ".join(sorted({str(job.get("asset_id")) for job in record.get("jobs", [])}))
        raise SdgaError(
            f"{asset_id!r} is not in run {record.get('run_id')}",
            remedy=f"assets in this run: {known}",
        )

    entry: dict[str, Any] = {
        "asset_id": asset_id,
        "status": decision,
        "by": by,
        "at": _now(),
    }
    if note:
        entry["note"] = note
    record.setdefault("reviews", []).append(entry)

    for job in jobs:
        if job.get("status") in {"accepted", SUPERSEDED}:
            job["review"] = {key: value for key, value in entry.items() if key != "asset_id"}

    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_contact_sheet(config, run_dir, record)
    return record


def write_contact_sheet(config: Config, run_dir: Path, record: Mapping[str, Any]) -> Path:
    """Write `review.html`: every asset with its references beside its result.

    Side by side is the whole point: a gate can tell you the palette held, but only a human
    can see that the sprite came back as a red panda.
    """
    jobs = list(record.get("jobs", []))
    rows: list[str] = []
    for job in sorted(
        jobs, key=lambda entry: (str(entry.get("asset_id")), entry.get("candidate", 0))
    ):
        status = job.get("status")
        post = (job.get("post") or [{}])[0].get("path")
        result = (
            f'<img src="{html.escape(_relative(post, run_dir, config.root))}" alt="result">'
            if post
            else "—"
        )
        refs = (
            "".join(
                f'<figure><img src="{html.escape(_relative(ref.get("path"), run_dir, config.root))}" '
                f'alt="{html.escape(str(ref.get("role")))}">'
                f"<figcaption>{html.escape(str(ref.get('role')))}</figcaption></figure>"
                for ref in job.get("refs", [])
            )
            or "<span class=missing>no references</span>"
        )
        review = (job.get("review") or {}).get("status", "pending")
        gates = job.get("gates", [])
        gate_text = (
            ", ".join(f"{gate.get('gate')}: {gate.get('status')}" for gate in gates) or "no gates"
        )
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(str(job.get('asset_id')))}</code>"
            f"<div class=meta>candidate {job.get('candidate', 0)} · seed "
            f"{html.escape(str(job.get('seed')))}<br>{html.escape(gate_text)}</div></td>"
            f"<td class=refs>{refs}</td>"
            f"<td>{result}</td>"
            f"<td><span class=status-{html.escape(str(status))}>{html.escape(str(status))}</span><br>"
            f"<span class=meta>{html.escape(review)}</span></td>"
            "</tr>"
        )

    document = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>sdga review — run {html.escape(str(record.get("run_id")))}</title>
<style>
  body {{ font: 14px/1.5 system-ui, sans-serif; margin: 2rem; background: #14161a; color: #e6e6e6; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border-bottom: 1px solid #2b3038; padding: 0.6rem; text-align: left; vertical-align: top; }}
  img {{ image-rendering: pixelated; max-width: 220px; background: #0b0d10; }}
  td.refs {{ max-width: 380px; }}
  figure {{ display: inline-block; margin: 0 0.5rem 0 0; }}
  figcaption, .meta {{ color: #9aa4b2; font-size: 12px; }}
  .missing {{ color: #b26b6b; }}
  .status-accepted {{ color: #79c07a; }}
  .status-rejected, .status-failed {{ color: #d0716b; }}
  .status-superseded {{ color: #9aa4b2; }}
</style>
<h1>Run {html.escape(str(record.get("run_id")))}</h1>
<p class=meta>status {html.escape(str(record.get("status")))} · review decisions are appended to
run.json · <code>sdga review --run {html.escape(str(record.get("run_id")))} --asset ID
--approve|--reject</code></p>
<table>
<thead><tr><th>Asset</th><th>Reference</th><th>Result</th><th>Status</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
</html>
"""
    target = run_dir / "review.html"
    target.write_text(document, encoding="utf-8")
    return target


def _relative(path: object, run_dir: Path, root: Path) -> str:
    """A path usable from `run_dir/review.html`, which sits two levels inside the project."""
    text = str(path or "")
    if not text:
        return ""
    candidate = Path(text)
    target = candidate if candidate.is_absolute() else root / candidate
    try:
        return Path(os.path.relpath(target, run_dir)).as_posix()
    except ValueError:  # different drives on Windows
        return target.as_posix()


__all__ = [
    "APPROVED",
    "REJECTED",
    "SUPERSEDED",
    "record_review",
    "write_contact_sheet",
]
