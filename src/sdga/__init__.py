"""sdga — an engine-neutral game asset generation pipeline.

Nothing in this package imports ComfyUI (docs/01-architecture.md, rule 1). ComfyUI is a
remote service reached over HTTP, and every step after the sampler is deterministic Python
that lives in this repository.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
