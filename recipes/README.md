# Recipes

Graph templates live here: a ComfyUI API-format graph plus a `requires` block and a
declared `output_node`, exported as JSON and hand-annotated with `${slot}` markers.

They are **data**: versioned, diffable, reviewed like code, and never imported. Adding an
asset kind means adding a file here, not changing the pipeline.

Empty in phase P0. The first recipe (`terrain_tile`) lands with ticket T12.

Format: [../docs/03-contracts-and-schemas.md §3](../docs/03-contracts-and-schemas.md).
