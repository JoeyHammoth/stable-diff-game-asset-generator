from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _project import make_project  # noqa: E402


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A complete, valid project on disk."""
    return make_project(tmp_path)
