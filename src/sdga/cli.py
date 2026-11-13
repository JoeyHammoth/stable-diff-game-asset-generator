"""Command line surface (docs/03-contracts-and-schemas.md §8).

Exit codes are contract and are produced only by `SdgaError.exit_code`:
0 success · 1 gate/review failure · 2 usage · 3 backend unavailable · 4 schema or config.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__, doctor
from .backends import FakeBackend, GenerationBackend
from .backends.comfyui import ComfyUIBackend, load_recipes
from .config import Config, load_config
from .errors import (
    EXIT_BACKEND,
    EXIT_FAILURE,
    EXIT_OK,
    EXIT_USAGE,
    SdgaError,
    UsageError,
)
from .pack import publish
from .palettes import extract_palette, write_palette
from .pipeline import execute_run, run_dir_for, verify_pack, verify_run
from .planning import build_plan
from .review import record_review
from .specs import load_specs

# Still ahead of this build. Named explicitly so the gap is visible, not silent.
STUBS: dict[str, tuple[str, str]] = {
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
        "--asset",
        action="append",
        default=[],
        metavar="ID",
        help="plan only this asset id (repeatable)",
    )
    plan_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="also print the first resolved request, with its bound graph",
    )
    plan_cmd.add_argument(
        "--out", metavar="PATH", help="write plan.json here (default: <project>/plan.json)"
    )
    plan_cmd.set_defaults(func=cmd_plan)

    run_cmd = sub.add_parser("run", parents=[common], help="generate, postprocess, and gate assets")
    run_cmd.add_argument(
        "--asset",
        action="append",
        default=[],
        metavar="ID",
        help="run only this asset id (repeatable)",
    )
    run_cmd.add_argument(
        "--dry-run", action="store_true", help="print bound graphs without generating"
    )
    run_cmd.set_defaults(func=cmd_run)

    publish_cmd = sub.add_parser(
        "publish", parents=[common], help="write packs/<pack_id>/ from a run"
    )
    publish_cmd.add_argument("--run", dest="run_id", default=None, help="run id (default: latest)")
    publish_cmd.add_argument(
        "--allow-unreviewed",
        action="store_true",
        help="publish accepted assets without review decisions (review lands in P3)",
    )
    publish_cmd.set_defaults(func=cmd_publish)

    validate_cmd = sub.add_parser(
        "validate", parents=[common], help="re-run gates over a pack or run; no backend needed"
    )
    validate_cmd.add_argument("target", nargs="?", default=None, help="path to a pack directory")
    validate_cmd.add_argument("--run", dest="run_id", default=None, help="validate a run instead")
    validate_cmd.add_argument("--json", action="store_true", help="emit rows as JSON")
    validate_cmd.set_defaults(func=cmd_validate)

    review_cmd = sub.add_parser(
        "review", parents=[common], help="approve or reject a run's assets; writes review.html"
    )
    review_cmd.add_argument("--run", dest="run_id", default=None, help="run id (default: latest)")
    review_cmd.add_argument(
        "--asset",
        action="append",
        default=[],
        metavar="ID",
        help="asset id to decide (repeatable; default: every accepted asset)",
    )
    decision = review_cmd.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", action="store_true", help="accept these assets")
    decision.add_argument("--reject", action="store_true", help="reject these assets")
    review_cmd.add_argument("--note", default=None, help="why, for the record")
    review_cmd.set_defaults(func=cmd_review)

    palette_cmd = sub.add_parser("palette", help="author the project palette (a one-time step)")
    palette_sub = palette_cmd.add_subparsers(
        dest="palette_command", required=True, metavar="COMMAND"
    )
    extract_cmd = palette_sub.add_parser(
        "extract",
        parents=[common],
        help="sample an authored image into the project's palette file",
    )
    extract_cmd.add_argument("image", metavar="IMAGE", help="concept or reference image to sample")
    extract_cmd.add_argument(
        "--colors",
        type=int,
        default=None,
        metavar="N",
        help="how many colours to sample (default: [style] palette_colors)",
    )
    extract_cmd.add_argument(
        "--out",
        metavar="PATH",
        help="write here, .gpl or .png (default: [style] palette)",
    )
    extract_cmd.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing palette file (changes every seed)",
    )
    extract_cmd.set_defaults(func=cmd_palette_extract)

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
        # The fake has no uploads: references are hashed at plan time and never sent.
        # The fake reports the models the style actually asks for, so doctor is telling
        # the truth about this project rather than about a hardcoded fixture.
        style = config.style
        return FakeBackend(
            models={
                "checkpoints": (style.checkpoint,),
                "loras": tuple(lora.name for lora in style.loras),
            }
        )
    # The project root lets the adapter upload references by content address (T17).
    return ComfyUIBackend(config.backend, project_root=config.root)


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.project)
    backend = make_backend(config)
    recipes = load_recipes(config)
    report = doctor.run(config, backend, recipes.requirements(config.style))
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(report.render())
    return EXIT_OK if report.ok else EXIT_BACKEND


def cmd_plan(args: argparse.Namespace) -> int:
    config = load_config(args.project)
    specs = load_specs(config)
    plan = build_plan(config, specs, assets=args.asset or None, recipes=load_recipes(config))

    target = Path(args.out) if args.out else config.plan_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(plan.to_json(), encoding="utf-8")

    print(f"planned {len(plan.requests)} request(s) | style {plan.style_hash}")
    for request in plan.requests:
        print(
            f"  {request.asset_id:<30} {request.kind.value:<13} "
            f"seed {request.seed:<11} final {_dims(request.final_size):<9} "
            f"render {_dims(request.size):<9} {request.recipe or 'no recipe'}"
        )
    print(f"wrote {_display(target, config.root)}")

    if args.dry_run and plan.requests:
        print()
        print("first resolved request (graph bound from its recipe):")
        print(json.dumps(plan.requests[0].to_dict(), indent=2, sort_keys=True))
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.project)
    backend = make_backend(config)
    outcome = execute_run(config, backend, assets=args.asset or None, dry_run=args.dry_run)
    if args.dry_run:
        return EXIT_OK

    print(
        f"run {outcome.run_id}: {outcome.status} "
        f"({outcome.accepted} accepted, {outcome.rejected} rejected, "
        f"{outcome.failed} failed, {outcome.superseded} superseded)"
    )
    print(f"wrote {_display(outcome.run_dir / 'run.json', config.root)}")
    print(f"review sheet: {_display(outcome.run_dir / 'review.html', config.root)}")
    return EXIT_OK if outcome.status == "complete" else EXIT_FAILURE


def cmd_publish(args: argparse.Namespace) -> int:
    config = load_config(args.project)
    run_dir = run_dir_for(config, args.run_id)
    result = publish(config, run_dir, allow_unreviewed=args.allow_unreviewed)
    print(f"published {result.pack_id} with {len(result.asset_ids)} asset(s)")
    print(f"wrote {_display(result.path, config.root)}")
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    config = load_config(args.project)
    recipes = load_recipes(config)

    if args.run_id:
        ok, rows = verify_run(config, run_dir_for(config, args.run_id), recipes)
    else:
        if not args.target:
            raise UsageError(
                "validate needs a pack path or --run <run_id>",
                remedy="for example: sdga validate packs/example-2026-11-13-01",
            )
        target = Path(args.target)
        if not target.is_absolute() and not target.exists():
            target = config.root / target
        ok, rows = verify_pack(config, target, recipes)

    if args.json:
        print(json.dumps({"ok": ok, "rows": rows}, indent=2, sort_keys=True))
    else:
        print(f"{'ASSET':<30} {'GATE':<22} {'STATUS':<7} VALUE")
        for row in rows:
            print(f"{row['asset_id']:<30} {row['gate']:<22} {row['status']:<7} {row.get('value')}")
        print("ok" if ok else "FAILED")
    return EXIT_OK if ok else EXIT_FAILURE


def cmd_review(args: argparse.Namespace) -> int:
    config = load_config(args.project)
    run_dir = run_dir_for(config, args.run_id)
    decision = "approved" if args.approve else "rejected"

    targets = list(args.asset)
    if not targets:
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        targets = sorted(
            {str(job["asset_id"]) for job in record.get("jobs", []) if job.get("status") == "accepted"}
        )
        if not targets:
            raise UsageError(
                "this run has no accepted assets to review",
                remedy="fix the failing gates, then run again",
            )

    for asset_id in targets:
        record_review(config, run_dir, asset_id, decision, note=args.note)
        print(f"{asset_id}: {decision}")
    print(f"wrote {_display(run_dir / 'review.html', config.root)}")
    return EXIT_OK


def cmd_palette_extract(args: argparse.Namespace) -> int:
    config = load_config(args.project)

    source = Path(args.image)
    if not source.is_absolute() and not source.exists():
        source = config.root / args.image
    if not source.is_file():
        raise UsageError(
            f"no image at {args.image}",
            remedy="pass a path to a concept or reference image, e.g. concepts/cleaned/floor.png",
        )

    wanted = args.colors if args.colors is not None else config.style.palette.colors
    if not 1 <= wanted <= 256:
        raise UsageError(f"--colors must be between 1 and 256, got {wanted}")

    target = Path(args.out) if args.out else config.root / config.style.palette.path
    if target.exists() and not args.force:
        raise UsageError(
            f"{_display(target, config.root)} already exists",
            remedy="pass --force to replace it; every seed is derived from the palette bytes",
        )

    colours = extract_palette(source, wanted)
    write_palette(target, colours, name=target.stem, source=source.name)

    print(f"extracted {len(colours)} colour(s) from {source.name}")
    print(f"wrote {_display(target, config.root)}")
    declared = config.style.palette.colors
    if len(colours) != declared:
        print(
            f"note: [style] palette_colors is {declared}; set it to {len(colours)}, "
            f"or re-run with --colors {declared}"
        )
    print("review the palette, then run `sdga plan` and commit plan.json: seeds change")
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
