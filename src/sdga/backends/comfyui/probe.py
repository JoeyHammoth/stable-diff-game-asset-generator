"""Capability probing (docs/04-pipeline-stages.md §0, docs/01 §6).

ComfyUI already knows what it can do: `/object_info` enumerates every node class and, for
combo inputs, the model files actually on disk. Asking beats assuming, and it turns a
renamed node or a missing checkpoint into a table row instead of a stack trace.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..base import BackendProfile, DeviceInfo

# folder -> (loader class, input name). These are the loaders the recipes use.
FOLDER_INPUTS: Mapping[str, tuple[str, str]] = {
    "checkpoints": ("CheckpointLoaderSimple", "ckpt_name"),
    "loras": ("LoraLoader", "lora_name"),
    "vae": ("VAELoader", "vae_name"),
    "controlnet": ("ControlNetLoader", "control_net_name"),
    "upscale_models": ("UpscaleModelLoader", "model_name"),
    "clip_vision": ("CLIPVisionLoader", "clip_name"),
    "ipadapter": ("IPAdapterModelLoader", "ipadapter_file"),
}


def _input_spec(object_info: Mapping[str, Any], node: str, key: str) -> Any:
    entry = object_info.get(node)
    if not isinstance(entry, dict):
        return None
    inputs = entry.get("input") or {}
    for section in ("required", "optional"):
        table = inputs.get(section)
        if isinstance(table, dict) and key in table:
            return table[key]
    return None


def combo_options(object_info: Mapping[str, Any], node: str, key: str) -> tuple[str, ...]:
    """A combo input's options are `[list_of_values, {...}]`; anything else yields ()."""
    spec = _input_spec(object_info, node, key)
    if isinstance(spec, list) and spec and isinstance(spec[0], list):
        return tuple(str(option) for option in spec[0])
    return ()


def build_profile(
    object_info: Mapping[str, Any],
    system_stats: Mapping[str, Any] | None = None,
    *,
    url: str = "",
) -> BackendProfile:
    stats = system_stats or {}
    system = stats.get("system") or {}
    devices = tuple(
        DeviceInfo(
            name=str(device.get("name", "unknown")),
            vram_total=int(device.get("vram_total") or 0),
        )
        for device in stats.get("devices") or []
        if isinstance(device, dict)
    )

    models: dict[str, tuple[str, ...]] = {}
    for folder, (loader, key) in FOLDER_INPUTS.items():
        options = combo_options(object_info, loader, key)
        if options:
            models[folder] = options

    return BackendProfile(
        kind="comfyui",
        url=url,
        comfyui_version=str(system.get("comfyui_version", "")),
        pytorch_version=str(system.get("pytorch_version", "")),
        devices=devices,
        nodes=frozenset(str(name) for name in object_info),
        models=models,
    )


__all__ = ["FOLDER_INPUTS", "build_profile", "combo_options"]
