"""Stage 0: doctor (docs/04-pipeline-stages.md §0).

Answers one question before anything expensive happens: will this project actually run on
this backend? It replaces the "it just doesn't work" failure mode with a table that names
the missing node or model file and where to put it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .backends import BackendProfile, GenerationBackend
from .config import Config
from .errors import BackendError

PASS = "pass"
WARN = "warn"
FAIL = "fail"
SKIPPED = "skipped"

# Which ComfyUI folder a loader reads from. Printed so a missing model is actionable.
MODEL_FOLDERS: dict[str, str] = {
    "checkpoints": "models/checkpoints",
    "loras": "models/loras",
    "controlnet": "models/controlnet",
    "vae": "models/vae",
    "clip_vision": "models/clip_vision",
    "ipadapter": "models/ipadapter",
    "animatediff_models": "models/animatediff_models",
    "upscale_models": "models/upscale_models",
}


@dataclass(frozen=True)
class Requirement:
    """What one recipe needs. Phase P1 builds these from `recipes/*.yaml` `requires` blocks."""

    recipe: str
    nodes: tuple[str, ...] = ()
    models: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str = ""
    remedy: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "remedy": self.remedy,
        }


@dataclass(frozen=True)
class Report:
    checks: tuple[Check, ...]
    profile: BackendProfile | None = None

    @property
    def ok(self) -> bool:
        return all(check.status != FAIL for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "profile": None if self.profile is None else self.profile.to_dict(),
            "checks": [check.to_dict() for check in self.checks],
        }

    def render(self) -> str:
        rows: list[tuple[str, str, str]] = [("CHECK", "STATUS", "DETAIL")]
        rows.extend((check.name, check.status, check.detail) for check in self.checks)
        width_name = max(len(row[0]) for row in rows)
        width_status = max(len(row[1]) for row in rows)
        lines = [
            f"{name:<{width_name}}  {status:<{width_status}}  {detail}".rstrip()
            for name, status, detail in rows
        ]
        for check in self.checks:
            if check.remedy and check.status in {FAIL, WARN}:
                lines.append(f"  ! {check.name}: {check.remedy}")
        return "\n".join(lines)


def run(
    config: Config,
    backend: GenerationBackend,
    requirements: Sequence[Requirement] = (),
) -> Report:
    checks: list[Check] = []
    style = config.style

    checks.append(
        Check(
            "config",
            PASS,
            f"{config.project.name} | grid {style.grid} | {len(style.loras)} lora(s)",
        )
    )
    checks.append(
        Check(
            "palette",
            PASS,
            f"{style.palette.path} | {style.palette.colors} colours | "
            f"{_short(style.palette.sha256)}",
        )
    )

    try:
        profile = backend.probe()
    except BackendError as exc:
        checks.append(
            Check(
                "backend",
                FAIL,
                exc.message,
                remedy=exc.remedy or "start the backend, then re-run `sdga doctor`",
            )
        )
        return Report(checks=tuple(checks), profile=None)

    checks.append(
        Check("backend", PASS, f"{profile.kind} {profile.comfyui_version}".strip())
    )
    checks.append(Check("profile", PASS, profile.profile_hash))
    checks.append(_checkpoint_check(config, profile))

    for requirement in requirements:
        checks.append(_requirement_check(requirement, profile))

    for gap in profile.gaps:
        checks.append(
            Check(
                f"gap:{gap.item}",
                FAIL if gap.kind in {"node", "model"} else WARN,
                gap.detail or gap.kind,
                remedy=gap.remedy or None,
            )
        )

    if not requirements:
        checks.append(
            Check("recipes", SKIPPED, "no recipes declared yet (recipe checking lands in P1)")
        )

    return Report(checks=tuple(checks), profile=profile)


def _checkpoint_check(config: Config, profile: BackendProfile) -> Check:
    checkpoint = config.style.checkpoint
    if profile.kind == "fake":
        return Check(
            "checkpoint",
            SKIPPED,
            f"{checkpoint} (not verifiable on the fake backend)",
        )
    if profile.has_model("checkpoints", checkpoint):
        return Check("checkpoint", PASS, checkpoint)
    return Check(
        "checkpoint",
        FAIL,
        f"{checkpoint} is not in the checkpoints combo",
        remedy=f"place {checkpoint} in ComfyUI's {MODEL_FOLDERS['checkpoints']} folder",
    )


def _requirement_check(requirement: Requirement, profile: BackendProfile) -> Check:
    missing_nodes = [node for node in requirement.nodes if not profile.has_node(node)]
    missing_models = [
        (folder, name)
        for folder, names in requirement.models.items()
        for name in names
        if not profile.has_model(folder, name)
    ]

    if not missing_nodes and not missing_models:
        return Check(f"recipe:{requirement.recipe}", PASS, "all requirements present")

    details: list[str] = []
    remedies: list[str] = []
    if missing_nodes:
        details.append("missing node(s): " + ", ".join(sorted(missing_nodes)))
        for node in sorted(missing_nodes):
            remedies.append(
                f"install the custom node pack providing {node}, "
                f"or update recipe {requirement.recipe}"
            )
    if missing_models:
        details.append(
            "missing model(s): "
            + ", ".join(f"{name} ({MODEL_FOLDERS.get(folder, 'models/' + folder)})"
                        for folder, name in missing_models)
        )
        for folder, name in missing_models:
            remedies.append(
                f"place {name} in ComfyUI's {MODEL_FOLDERS.get(folder, 'models/' + folder)} folder"
            )

    return Check(
        f"recipe:{requirement.recipe}",
        FAIL,
        "; ".join(details),
        remedy="; ".join(remedies),
    )


def _short(tagged_hash: str) -> str:
    return tagged_hash[:15] + "..."


__all__ = ["FAIL", "PASS", "SKIPPED", "WARN", "Check", "Report", "Requirement", "run"]
