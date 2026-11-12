"""The hard rules from docs/01-architecture.md, enforced rather than merely stated.

If someone imports ComfyUI or hardcodes `D:\\...`, the build fails here. CI running these
tests in an environment without ComfyUI or torch is what makes rule 1 real.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from sdga.backends import FakeBackend, GenerationBackend

SRC = Path(__file__).resolve().parents[1] / "src" / "sdga"

FORBIDDEN_ROOTS = {
    "comfy",
    "nodes",
    "folder_paths",
    "comfy_execution",
    "torch",
    "godot",
}

_ABSOLUTE = re.compile(r'(?<![A-Za-z])[A-Za-z]:[\\/]|"/Users/|"/home/')


def _imports(tree: ast.AST) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module


def test_source_never_imports_comfyui_torch_or_an_engine():
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for lineno, name in _imports(tree):
            if name.split(".")[0] in FORBIDDEN_ROOTS:
                offenders.append(f"{path.relative_to(SRC)}:{lineno} imports {name}")
    assert not offenders, "\n".join(offenders)


def test_source_contains_no_machine_specific_paths():
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _ABSOLUTE.search(line):
                offenders.append(f"{path.relative_to(SRC)}:{lineno}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_fake_backend_is_a_real_implementation_of_the_seam():
    # runtime_checkable Protocols check structure, not inheritance: the fake is an
    # independent implementation, which is exactly what makes it a useful second adapter.
    assert isinstance(FakeBackend(), GenerationBackend)
