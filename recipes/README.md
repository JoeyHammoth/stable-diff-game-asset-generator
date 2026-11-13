# Recipes

Graph templates live here: a ComfyUI API-format graph plus a `requires` block and a
declared `output_node`, exported as JSON and hand-annotated with `${slot}` markers.

They are **data**: versioned, diffable, reviewed like code, and never imported. Adding an
asset kind means adding a file here, not changing the pipeline.

| Recipe | Kind | Notes |
|---|---|---|
| `terrain_tile.yaml` | `terrain_tile` | uniform palette-locked tile, `downscale_box` → `palette_snap` |
| `sprite_sheet.yaml` | `sprite_sheet` | authored dw-pose sheet through ControlNet; per-frame trim and feet anchor |
| `sprite_sheet_img2img.yaml` | `sprite_sheet` | same spec, pose encoded and resampled at a partial denoise |
| `ui_element.yaml` | `ui_element` | 9-slice frame, mirrored for bitwise symmetry |
| `icon.yaml` | `icon` | small icon, centred rather than grounded |
| `concept.yaml` | `concept` | reference art: hardened alpha, despeckled, no palette lock |
| `normal_map.yaml` | `normal_map` | height render → `depth_to_normal`; never palette-snapped |

A project pins its own copies (see `examples/recipes/`): recipes are data that a run must be
able to reproduce later, so they are copied in rather than read from this catalog.

A recipe may declare `kind:` when its id is not the kind it serves (the img2img variant does);
the recipe whose id equals the kind always wins as the default.

Format: [../docs/03-contracts-and-schemas.md §3](../docs/03-contracts-and-schemas.md).
