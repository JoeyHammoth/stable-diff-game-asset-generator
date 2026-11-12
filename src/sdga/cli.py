"""Command line surface (docs/03-contracts-and-schemas.md §8).

Exit codes are contract and are produced only by `SdgaError.exit_code`:
0 success · 1 gate/review failure · 2 usage · 3 backend unavailable · 4 schema or config.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__, doctor
from .backends import FakeBackend, GenerationBackend
from .config import Config, load_config
from .errors import EXIT_BACKEND, EXIT_OK, EXIT_USAGE, BackendError, SdgaError
from .planning import build_plan
from .specs import load_specs

# Commands in the documented surface that this phase does not implement yet. Shipping them
# as explicit, named stubs is better than a silent "unknown command" or a half-working run.
STUBS: dict[str, tuple[str, str]] = {
    "run": ("P1", "generate assets through the configured backend"),
    "validate": ("P1", "re-run gates over an existing run or pack"),
    "review": ("P3", "record approve/reject decisions"),
    "publish": ("P1", "write packs/<pack_id>/"),
    "adapt": ("P5", "emit engine hints from a pack"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdga",
        description=(
            "Engine-neutral game asset generation. Resolves declarative asset specs into "
            "generation requests, drives a remote ComfyUI, and publishes asset packs. "
            "Never imports ComfyUI; never needs a game engine."
        ),
    )
    parser.add_argument("--version", action="version", version=f"sdga {__version__}")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--project",
        metavar="DIR",
        default=".",
        help="project directory containing sdga.toml (default: current directory)",
    )

    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    doctor_cmd = sub.add_parser(
        "doctor", parents=[common], help="probe the backend and report what is missing"
    )
    doctor_cmd.add_argument("--json", action="store_true", help="emit the report as JSON")
    doctor_cmd.set_defaults(func=cmd_doctor)

    plan_cmd = sub.add_parser(
        "plan", parents=[common], help="resolve asset specs into generation requests"
    )
    plan_cmd.add_argument(
        "--asset", action="append", default=[], metavar="ID",
        help="plan only this asset id (repeatable)",
    )
    plan_cmd.add_argument(
        "--dry-run", action="store_true",
        help="also print the first resolved request; needs no backend",
    )
    plan_cmd.add_argument(
        "--out", metavar="PATH", help="write plan.json here (default: <project>/plan.json)"
    )
    plan_cmd.set_defaults(func=cmd_plan)

    for name, (phase, description) in STUBS.items():
        stub = sub.add_parser(name, parents=[common], help=f"{description} (phase {phase})")
        stub.set_defaults(func=cmd_stub)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or EXIT_OK)
    except SdgaError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code


def make_backend(config: Config) -> GenerationBackend:
    if config.backend.kind == "fake":
        return FakeBackend()
    raise BackendError(
        "unreachable",
        f"the {config.backend.kind!r} backend is not part of this build",
        remedy=(
            'set [backend] kind = "fake" in sdga.toml; the ComfyUI adapter arrives in '
            "phase P1 (tickets T08-T16)"
        ),
    )


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.project)
    backend = make_backend(config)
    report = doctor.run(config, backend)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(report.render())
    return EXIT_OK if report.ok else EXIT_BACKEND


def cmd_plan(args: argparse.Namespace) -> int:
    config = load_config(args.project)
    specs = load_specs(config)
    plan = build_plan(config, specs, assets=args.asset or None)

    target = Path(args.out) if args.out else config.plan_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(plan.to_json(), encoding="utf-8")

    print(f"planned {len(plan.requests)} request(s) | style {plan.style_hash}")
    for request in plan.requests:
        print(
            f"  {request.asset_id:<30} {request.kind.value:<13} "
            f"seed {request.seed:<11} final {_dims(request.final_size):<9} "
            f"render {_dims(request.size)}"
        )
    print(f"wrote {_display(target, config.root)}")

    if args.dry_run and plan.requests:
        print()
        print("first resolved request (graph binding arrives with recipes, phase P1):")
        print(json.dumps(plan.requests[0].to_dict(), indent=2, sort_keys=True))
    return EXIT_OK


def cmd_stub(args: argparse.Namespace) -> int:
    phase, description = STUBS[args.command]
    print(
        f"sdga: '{args.command}' is not available in this build "
        f"(planned for phase {phase}: {description})",
        file=sys.stderr,
    )
    return EXIT_USAGE


def _dims(size: tuple[int, int] | None) -> str:
    return "n/a" if size is None else f"{size[0]}x{size[1]}"


def _display(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


__all__ = ["build_parser", "main", "make_backend"]
