"""Engine adapters: optional translators from a pack to one engine's conventions.

Adapters produce **data only**. They read a published pack, write flat JSON, and never invoke
the engine. That is what keeps "no Godot dependency" true while still making a Godot project
importable without hand-transcribing margins and loop points.
"""

from __future__ import annotations

from .godot import AdaptResult, adapt, adapt_godot, build_godot_bundle, read_pack

__all__ = ["AdaptResult", "adapt", "adapt_godot", "build_godot_bundle", "read_pack"]
