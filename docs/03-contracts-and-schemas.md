# Contracts and Schemas

> Every format in this document is versioned with `schema`. Readers must reject unknown
> major schema numbers. All paths are relative to the **project root** (`[project].root`),
> never absolute, never `D:\...`.

---

## 1. `sdga.toml` — project and style configuration

One file. TOML because it supports comments and does not punish trailing commas.

```toml
schema = 1

[project]
name = "mygame"
root = "."
asset_globs = ["assets/**/*.yaml"]
recipes_dir = "recipes"             # this project's pinned recipe set
runs_dir = "runs"
packs_dir = "packs"
cache_dir = ".sdga/cache"

[style]
name = "mygame"
trigger_token = "ProjectMyGameStyle"
grid = 32                          # final pixel grid edge
generation_size = [512, 512]       # render size before downscale
palette = "palettes/endesga32.gpl"    # .gpl, or a .png whose distinct colours are the palette
palette_colors = 32
checkpoint = "sd_v1-5.safetensors"
seed_policy = "derived"            # fixed | derived | random
positive_anchors = [
  "ProjectMyGameStyle", "flat colors", "clean pixel art",
  "crisp outlines", "limited color palette", "orthogonal view",
  "2d sprite", "retro game art",
]
negative_anchors = [
  "photorealistic", "blurry", "gradient", "smooth shading",
  "3d render", "watermark", "text", "anti-aliasing", "low quality",
]

[[style.loras]]
name = "my_game_style.safetensors"
strength_model = 0.85
strength_clip = 0.85

[backend]
kind = "comfyui"                   # comfyui | fake
url = "http://127.0.0.1:8188"
ws_url = "ws://127.0.0.1:8188/ws"
timeout_s = 900
poll_interval_s = 0.5
max_concurrency = 1                # one GPU: single-flight unless you know better
retry = { attempts = 2, backoff_s = 5.0 }

[pack]
id_template = "{project}-{date}-{seq}"
require_review = true
include_raw = false

[gates]
on_fail = "reject"                 # reject | warn
[gates.thresholds]
max_unique_colors = 32
seam_edge_ratio = 1.5
audio_peak_dbfs = -3.0
```

### What the Style Contract hash covers

Exactly `[style]` in full, plus the palette file's content hash. **Not** `[backend]`, `[pack]`,
`[gates]`, `[project]` — and **not** recipe versions: those enter `request_hash`, so bumping a
recipe regenerates at the same seed instead of reshuffling every asset. `run.json` records the
recipe map separately for provenance.

Rationale: changing `max_concurrency` or a gate threshold must not invalidate generated art;
changing an anchor word or the LoRA strength must.

---

## 2. `assets/*.yaml` — Asset Specs

One file may declare several assets. Validation runs at load time: unknown keys are errors, not
warnings (a typo'd `refernces:` must not silently produce an unreferenced asset).

```yaml
schema: 1
defaults:
  params: { steps: 25, cfg: 7.0, sampler: euler_ancestral, scheduler: karras }

assets:
  - id: terrain/moss_stone
    kind: terrain_tile
    prompt: >-
      seamless tileable mossy cobblestone floor, top-down 2d game tile,
      dark grey and green tones, flat, no gradients
    size: [32, 32]
    references:
      style_anchor: concepts/cleaned/dungeon_floor.png
    params: { denoise: 1.0 }
    gates: { seamless_tile: error }

  - id: char/ranger_walk
    kind: sprite_sheet
    prompt: >-
      full body forest ranger walking cycle, brown leather armor,
      green hooded cloak, side view, transparent background
    size: [32, 32]          # per cell
    frames: 8
    layout: { cols: 8, rows: 1 }
    references:
      style_anchor: concepts/cleaned/ranger_front.png
      pose: style/skeletons/walk_8frame.png
    candidates: 4
    params: { steps: 28, cfg: 7.5 }
    gates: { frames: error, alpha_required: error, frames_aligned: error }

  - id: ui/button_normal
    kind: ui_element
    prompt: >-
      rounded stone button, empty center, no text, 9-slice friendly frame
    size: [64, 16]
    references:
      wireframe: style/wireframes/button_64x16.png
    gates: { symmetry_9patch: error, alpha_required: error }

  - id: terrain/moss_stone_normal
    kind: normal_map
    depends_on: [terrain/moss_stone]
    size: [32, 32]
    params: { height_strength: 2.0, flip_g: false }
    gates: { normal_map_valid: error }
```

### Field rules

| Field | Rule |
|---|---|
| `id` | `^[a-z0-9_]+(/[a-z0-9_]+)+$`, unique across all files |
| `kind` | must be a known Asset Kind |
| `size` | final size in **pixels**; for `sprite_sheet` it is the **cell** size |
| `frames` | required iff kind produces an animation |
| `layout.cols * layout.rows` | must equal `frames` |
| `references.*` | role must be a known role; path must exist at plan time |
| `depends_on` | ids must exist; the graph must be acyclic (checked) |
| `params` | merged over `defaults.params`; unknown keys passed through to `${params.*}` |

---

## 3. `recipes/<kind>.yaml` — graph templates

A recipe is data: a ComfyUI graph in API format with `${slot}` markers, plus the declarations the
probe needs. It never contains business logic.

```yaml
schema: 1
id: terrain_tile
version: 3
graph: terrain_tile.graph.json
output_node: "12"

requires:
  nodes:
    - CheckpointLoaderSimple
    - LoraLoader
    - CLIPTextEncode
    - EmptyLatentImage
    - KSampler
    - VAEDecode
    - SaveImage
  models:
    checkpoints: ["${style.checkpoint}"]
    loras: ["${style.loras[0].name}"]

slots:
  required: [positive, negative, seed, width, height]
  optional: [style_anchor]
```

`terrain_tile.graph.json` (API format, `Save (API Format)` export, hand-edited to add markers):

```json
{
  "1": { "class_type": "CheckpointLoaderSimple",
         "inputs": { "ckpt_name": "${style.checkpoint}" } },
  "2": { "class_type": "LoraLoader",
         "inputs": { "model": ["1", 0], "clip": ["1", 1],
                     "lora_name": "${style.loras[0].name}",
                     "strength_model": "${style.loras[0].strength_model}",
                     "strength_clip": "${style.loras[0].strength_clip}" } },
  "3": { "class_type": "CLIPTextEncode",
         "inputs": { "clip": ["2", 1], "text": "${positive}" } },
  "4": { "class_type": "CLIPTextEncode",
         "inputs": { "clip": ["2", 1], "text": "${negative}" } },
  "5": { "class_type": "EmptyLatentImage",
         "inputs": { "width": "${width}", "height": "${height}", "batch_size": 1 } },
  "6": { "class_type": "KSampler",
         "inputs": { "model": ["2", 0], "positive": ["3", 0], "negative": ["4", 0],
                     "latent_image": ["5", 0], "seed": "${seed}",
                     "steps": "${params.steps}", "cfg": "${params.cfg}",
                     "sampler_name": "${params.sampler}",
                     "scheduler": "${params.scheduler}",
                     "denoise": "${params.denoise}" } },
  "7": { "class_type": "VAEDecode", "inputs": { "samples": ["6", 0], "vae": ["1", 2] } },
  "12": { "class_type": "SaveImage",
          "inputs": { "images": ["7", 0], "filename_prefix": "${filename_prefix}" } }
}
```

### Binder rules

1. Walk the graph; any string of the form `${expr}` is a slot.
2. `expr` resolves against a flat context: request fields, `style.*`, `params.*`, `filename_prefix`.
3. **A missing slot value is a hard error** at plan time (`SlotResolutionError`), not a `null`
   passed to ComfyUI.
4. Types are preserved: a slot that resolves to a number is emitted as a JSON number, not a string.
5. After binding, every `["node", slot]` link is validated to reference an existing node id —
   catching hand-edits that orphan a node.
6. Value-only slots may not appear in `class_type`. (Prevents a spec from choosing which nodes run.)

**Why markers rather than node-number patching.** Node ids are an artefact of graph editing; a
marker survives renumbering, is visible in a diff, and makes the set of parameters a recipe
accepts self-documenting. It also makes the fake backend trivial: the binder runs for it too, so
slot-resolution bugs are caught without a GPU.

---

## 4. `GenerationRequest` — the wire form

This is the only thing a backend receives. It is written to `runs/<id>/run.json` verbatim, so it
doubles as the reproduction recipe.

```json
{
  "schema": 1,
  "request_id": "sha256:6f1c…",
  "asset_id": "terrain/moss_stone",
  "kind": "terrain_tile",
  "recipe": "terrain_tile@3",
  "backend": "comfyui",
  "positive": "ProjectMyGameStyle, flat colors, … , seamless tileable mossy cobblestone floor, …",
  "negative": "photorealistic, blurry, gradient, …",
  "size": [512, 512],
  "seed": 2749810337,
  "refs": [
    { "role": "style_anchor", "path": "concepts/cleaned/dungeon_floor.png",
      "sha256": "sha256:ab12…", "backend_handle": "dungeon_floor.png" }
  ],
  "params": { "steps": 25, "cfg": 7.0, "sampler": "euler_ancestral",
              "scheduler": "karras", "denoise": 1.0 },
  "style_hash": "sha256:9d3f…",
  "output_node": "12",
  "graph": { "…": "bound ComfyUI prompt graph, exactly as submitted" }
}
```

`request_hash` is `sha256` over the canonical JSON of everything **except** `request_id`,
`graph`, and `refs[].backend_handle` (upload names are volatile). `request_hash` is the cache key;
a cache hit requires an identical hash **and** an identical `profile_hash`.

---

## 5. `run.json`

```json
{
  "schema": 1,
  "run_id": "20261113-041502-a7c1",
  "started": "2026-11-13T04:15:02Z",
  "finished": "2026-11-13T04:22:41Z",
  "status": "partial",
  "tool": { "name": "sdga", "version": "0.1.0", "python": "3.11.9" },
  "style": { "name": "mygame", "contract_hash": "sha256:9d3f…" },
  "profile": {
    "kind": "comfyui", "url": "http://127.0.0.1:8188",
    "comfyui_version": "0.23.0", "pytorch_version": "2.6.0+cu124",
    "devices": [{ "name": "NVIDIA GeForce RTX 4070 Ti", "vram_total": 12803203072 }],
    "profile_hash": "sha256:1p4k…"
  },
  "recipes": { "terrain_tile": "3", "sprite_sheet": "2" },
  "jobs": [
    {
      "asset_id": "terrain/moss_stone",
      "request_hash": "sha256:c0d3…",
      "seed": 2749810337,
      "status": "accepted",
      "cached": false,
      "timings": { "queued_s": 0.2, "executed_s": 41.7, "postprocess_s": 0.14 },
      "raw": [{ "path": "runs/20261113-041502-a7c1/raw/terrain__moss_stone.png",
                "sha256": "sha256:77aa…" }],
      "postprocess": ["downscale_box", "palette_snap", "alpha_hard"],
      "gates": [
        { "gate": "dimensions_exact", "status": "pass", "value": [32, 32] },
        { "gate": "palette_conformance", "status": "pass", "value": 27 },
        { "gate": "seamless_tile", "status": "pass", "value": 1.08,
          "threshold": 1.5 }
      ],
      "review": { "status": "approved", "by": "joe", "at": "2026-11-13T04:30:00Z" }
    }
  ]
}
```

A job with `status: rejected` keeps its `gates` so the reason is auditable.

---

## 6. `pack.json`

```json
{
  "schema": 1,
  "pack_id": "mygame-2026-11-13-01",
  "created": "2026-11-13T04:35:10Z",
  "style": { "name": "mygame", "contract_hash": "sha256:9d3f…",
             "grid": 32, "palette": { "path": "palettes/endesga32.gpl",
                                      "colors": 32, "sha256": "sha256:31bb…" } },
  "generator": { "tool": "sdga", "version": "0.1.0", "backend": "comfyui",
                 "profile_hash": "sha256:1p4k…" },
  "assets": [
    {
      "id": "terrain/moss_stone",
      "kind": "terrain_tile",
      "files": [
        { "path": "assets/terrain/moss_stone.png", "role": "albedo",
          "sha256": "sha256:4e21…", "width": 32, "height": 32,
          "format": "png", "bytes": 1183 }
      ],
      "engine": { "tile": { "size": [32, 32], "seamless": true } },
      "checks": [
        { "gate": "palette_conformance", "status": "pass", "value": 27 },
        { "gate": "seamless_tile", "status": "pass", "value": 1.08 }
      ],
      "provenance": { "run_id": "20261113-041502-a7c1",
                      "request_hash": "sha256:c0d3…", "seed": 2749810337,
                      "recipe": "terrain_tile@3",
                      "created": "2026-11-13T04:16:02Z" }
    }
  ]
}
```

`engine` is **advisory**. Consumers may ignore it. It exists so the pack carries the facts an
engine needs (tile size, seamlessness, 9-slice margins, frame layout, loop points) without the
producer knowing which engine reads it.

---

## 7. Error model

Backends do not raise arbitrary exceptions across the seam. They return one of a closed set:

| Kind | Meaning | Retryable | Recorded |
|---|---|---|---|
| `unreachable` | TCP/HTTP failed | yes | yes |
| `rejected_graph` | `/prompt` returned 400 + `node_errors` | no | full body |
| `execution_error` | node raised (WS `execution_error`) | once, if OOM | node, message |
| `timeout` | no terminal event within `timeout_s` | yes | last progress |
| `missing_capability` | probe found a node/model absent | no | which one, where to install |
| `bad_output` | success but no image at `output_node` | no | history body |
| `cancelled` | user or watchdog | no | — |

`execution_error` payloads include `node_id`, `node_type`, and `exception_message`; these are
copied verbatim into the job record. "CUDA out of memory" is detected by substring and triggers a
single retry with `max_concurrency` forced to 1 and `--lowvram` advice printed.

---

## 8. CLI surface

```
sdga doctor                     # probe backend, validate recipes, list gaps
sdga plan  [--asset ID…]        # resolve specs → requests; print or write plan.json (no backend)
sdga run   [--asset ID…] [--dry-run] [--resume] [--force] [--candidates N]
sdga validate [PACK|RUN]        # re-run gates over existing files; no backend needed
sdga review  [--asset ID] [--approve|--reject] [--note]
sdga publish [--run ID]         # write packs/<pack_id>/
sdga palette extract IMAGE [--colors N] [--out PATH] [--force]
                                # author the palette file from an image; .gpl or .png
sdga adapt   --engine godot     # optional: emit engine hints from a pack
```

Exit codes: `0` success, `1` gate/review failure, `2` usage error, `3` backend unavailable,
`4` schema/validation error. Scripts depend on these, so they are part of the contract.

`--dry-run` writes `plan.json` and prints the fully bound graph for the first asset. This is the
primary way to develop a recipe: it needs no GPU and no ComfyUI.

`palette extract` is the one command that *writes* style data. It samples an authored image down to
at most `--colors` colours (default: `[style] palette_colors`), writes `.gpl` or `.png` according to
`--out`, and refuses to replace an existing file without `--force` because every seed is derived
from the palette bytes. It is a one-time authoring step, **never part of the asset chain**: the
pipeline only ever snaps to the palette file that is checked in. Extraction is deterministic
(grouping in OKLab, weighted by pixel count, ordered by count then RGB) and only ever returns
colours present in the image, so it cannot invent a colour the art does not contain.

---

## 9. Versioning

- `schema` bumps only on breaking change; additive fields do not bump.
- Readers ignore unknown fields but **error** on unknown `schema` major.
- `pack.json` readers must treat `assets` as unordered; producers sort by id for stable diffs.
- `run.json` is never migrated in place. Old runs keep their schema; `sdga validate` reads both
  while the old format is supported, and support is dropped only on a major release.
