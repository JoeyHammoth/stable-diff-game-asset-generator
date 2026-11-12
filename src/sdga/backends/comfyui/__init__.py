"""The ComfyUI adapter. The only package in sdga that knows ComfyUI exists."""

from __future__ import annotations

from .backend import ComfyUIBackend, prompt_id_for
from .client import ComfyUIClient
from .probe import build_profile, combo_options
from .progress import Terminal, WebSocketTracker, parse_event
from .recipe import Recipe, RecipeRegistry, load_recipe, load_recipes

__all__ = [
    "ComfyUIBackend",
    "ComfyUIClient",
    "Recipe",
    "RecipeRegistry",
    "Terminal",
    "WebSocketTracker",
    "build_profile",
    "combo_options",
    "load_recipe",
    "load_recipes",
    "parse_event",
    "prompt_id_for",
]
