# Domain Model

> Vocabulary for this project. Use these terms exactly — in docs, in code, in commit messages.
> Where a term is deliberately narrow, the rejected alternatives are listed so they don't creep back.

---

## 1. Glossary

**Project** — A directory containing `sdga.toml`, `assets/`, and optional `palettes/`. One project
produces one or more packs. It has no relationship to an engine project; the two may live in
separate repositories.
_Avoid_: "game folder", "repo" (ambiguous with this repo).

**Pack** — A published, immutable, engine-neutral directory of asset files plus a manifest.
The only thing an engine ever consumes.
_Avoid_: "export", "build", "output folder".

**Asset** — One addressable art unit that a game refers to by identity, e.g.
`terrain/moss_stone` or `ui/button_normal`. An asset owns one or more **files** (albedo,
normal, mask) and exactly one manifest entry.
_Avoid_: "sprite" (too narrow), "image" (an asset may be audio).

**Asset Kind** — The category that determines everything downstream of a prompt:
which **recipe** builds it, which **postprocess chain** runs, which **gates** apply, and which
engine hints it carries. Kinds are a closed set, extended deliberately.
Current set: `concept`, `terrain_tile`, `sprite_sheet`, `ui_element`, `icon`, `normal_map`,
`sfx`, `music_track`.

**Asset Spec** — The declarative, human-authored description of one asset in `assets/*.yaml`:
kind, id, prompt fragment, parameters, references, acceptance thresholds. The spec is data and is
reviewed like code. It is *not* the full prompt — style anchors are added by the pipeline.

**Style Contract** — The immutable bundle of everything that must be identical across every asset
in a pack: style trigger token, palette, pixel grid, model/LoRA references, positive and negative
anchors, seed policy. Identified by a **content hash**. If the hash changes, every cached result
is invalid by definition.
_Avoid_: "style config" (that's the file; the contract is the resolved, hashed value).

**Recipe** — A data template that turns a **GenerationRequest** into a backend-specific graph.
Stored as a graph JSON (API format) with `${slot}` markers plus a `requires` block and a declared
output node. Recipes are versioned data, never imported code.

**GenerationRequest** — A fully resolved, self-contained instruction to a backend. Everything
needed to reproduce the output is present: prompts, negative, size, seed, references, recipe id
and hash, style contract hash, sampler parameters. A request is immutable and hashable; its hash
is the **cache key**.
_Avoid_: "job spec", "params".

**Seed** — The sampler seed, governed by a **Seed Policy**: `fixed` (from the spec), `derived`
(sha256 of asset id + style contract hash, folded to 32 bits), or `random` (generated and
recorded). `derived` is the default because it makes re-runs stable and diffs meaningful.

**Reference Image** — An input image with an explicit **role**: `style_anchor`, `pose`,
`wireframe`, `albedo`, `palette`, or `mask`. Roles matter: a recipe binds references by role, not
by filename, so an asset spec never names a node.

**Backend** — Any system that can satisfy a GenerationRequest. `comfyui` and `fake` exist on day
one. A backend is described by a **Capability Profile**.

**Capability Profile** — What a backend reported at probe time: identity and version, node classes
present, model files available per loader, device VRAM, and any declared gaps. Recorded in every
run; two runs with different profiles are not comparable.

**Job** — One GenerationRequest plus its state: `pending → submitting → running → fetched →
postprocessed → gated → accepted | rejected | failed`. Jobs are the unit of retry and resume.

**Run** — One invocation of `sdga run`. Owns a `run_id`, a `run.json`, a set of jobs, and the raw
artifacts. A run may be `complete`, `partial`, or `failed`.

**Artifact** — A file returned by a backend, before post-processing. **Postprocessed Artifact** is
what a postprocess chain produced. **Published File** is what ended up in a pack. All three are
distinct, and provenance chains them.

**Gate** — A named, deterministic check with a threshold, producing `pass | fail | warn` plus a
measured value. Gates are what make "the style held" an assertion instead of an opinion.

**Review** — A human decision recorded against an asset: `approved | rejected | superseded`, with
an optional note. Publishing excludes anything unapproved when `[pack].require_review = true`.

**Variant** — One of N candidates generated for the same asset id (`candidates: N` in the spec).
Exactly one is promoted; the rest are retained in the run for audit and never published.

**Adapter** — An optional translator from a Pack to one engine's conventions (for Godot: import
settings, `.tres`/`NinePatchRect` margin hints, an audio bus map). Adapters produce **data only**
and never run the engine.

**Leitmotif** — The authored melodic DNA (a short MIDI phrase) plus the declared set of
musical transformations that derive every track in the soundtrack from it. Reference images have
an analogue here: the leitmotif is the *style anchor* of the music layer.

---

## 2. Core types

Types are shown as their resolved form. Optional fields are marked `?`.

### StyleContract

| Field | Type | Notes |
|---|---|---|
| `name` | str | Human label, e.g. `mygame` |
| `trigger_token` | str | The LoRA token, e.g. `ProjectMyGameStyle` |
| `grid` | int | Target pixel grid edge, e.g. `32` |
| `generation_size` | [int, int] | Render size before downscale, e.g. `[512, 512]` |
| `palette` | PaletteRef | Path + color count + hash |
| `checkpoint` | str | e.g. `sd_v1-5.safetensors` |
| `loras` | [LoraRef] | name + model/clip strengths |
| `positive_anchors` | [str] | Ordered; joined with `", "` |
| `negative_anchors` | [str] | Ordered |
| `seed_policy` | SeedPolicy | `derived` default |
| `contract_hash` | str | `sha256:` over the canonical serialisation of the above |

### AssetSpec

| Field | Type | Notes |
|---|---|---|
| `id` | str | `namespace/name`, stable identity, no extension |
| `kind` | AssetKind | Selects recipe, chain, gates |
| `prompt` | str | Fragment only — anchors are appended |
| `negative?` | str | Overrides the contract's negative anchors entirely |
| `size` | [int, int] | Final size in grid units or pixels (kind-dependent) |
| `frames?` | int | For `sprite_sheet` |
| `references?` | [ReferenceImage] | role → path |
| `params?` | map | Passed to the recipe as `${params.*}` |
| `gates?` | map | Per-asset threshold overrides |
| `candidates?` | int | Default 1 |
| `depends_on?` | [str] | Asset ids this one consumes (e.g. a normal map's albedo) |
| `seed?` | int | Only with `seed_policy = fixed` |

### GenerationRequest

| Field | Type | Notes |
|---|---|---|
| `request_id` | str | Deterministic: hash of the body |
| `asset_id` | str | |
| `kind` | AssetKind | |
| `recipe` | `${id}@${hash}` | Exact recipe version |
| `positive` | str | Fully assembled prompt |
| `negative` | str | |
| `size` | [int, int] | Backend render size |
| `seed` | int | Resolved |
| `refs` | [ResolvedRef] | role → uploaded backend handle + content hash |
| `params` | map | Flattened: steps, cfg, sampler, scheduler, denoise, lora strengths |
| `style_hash` | str | |
| `output_node` | str | Node id whose image is *the* artifact |
| `backend` | str | `comfyui` / `fake` |
| `request_hash` | str | Cache key over the canonical body |

### RunRecord (`run.json`)

| Field | Type | Notes |
|---|---|---|
| `schema` | int | `1` |
| `run_id` | str | ULID or `YYYYMMDD-HHMMSS-<rand>` |
| `started`, `finished` | ISO8601 | |
| `tool` | {name, version, python} | |
| `profile` | CapabilityProfile | Backend identity + gaps |
| `style` | {name, contract_hash} | |
| `recipes` | map | recipe id → hash used |
| `jobs` | [JobRecord] | request, seed, timings, artifacts, gate results, review |
| `status` | enum | `complete \| partial \| failed` |

### PackManifest (`pack.json`)

| Field | Type | Notes |
|---|---|---|
| `schema` | int | `1` |
| `pack_id` | str | Immutable id; republishing creates a new one |
| `created` | ISO8601 | |
| `style` | {name, contract_hash, grid, palette} | |
| `generator` | {tool, version, backend, profile_hash} | |
| `assets` | [PackAsset] | Sorted by id |

### PackAsset

| Field | Type | Notes |
|---|---|---|
| `id` | str | |
| `kind` | AssetKind | |
| `files` | [FileEntry] | path, role, sha256, width, height, format, bytes |
| `engine?` | map | Advisory hints, e.g. `{tile:{size:[32,32],seamless:true}}` |
| `checks` | [GateResult] | The evidence that it met spec |
| `provenance` | Provenance | run_id, request_hash, seed, recipe, created |

---

## 3. Relationships

```
Project 1──* AssetSpec ──1 AssetKind ──1 Recipe
   │            │                          │
   │            │  (resolved against)      │
   │            ▼                          ▼
   │      GenerationRequest ──────────► Backend
   │            │                          │
   │            ▼                          ▼
   │           Job ────────────────► Artifact (raw)
   │            │                          │
   │            ▼                          ▼
   │     postprocess chain ──► Postprocessed Artifact ──► gates
   │                                                       │
   └── StyleContract ──(hash)──► RunRecord ◄────────────────┘
                                     │
                                     ▼
                             Review ──► Pack ──► PackManifest ──► Adapter
```

---

## 4. Invariants

These are asserted in code (and in tests), not just documented.

1. **One asset id, one manifest entry.** A pack containing two entries with the same `id` is
   invalid; the publisher refuses to write it.
2. **Every published file has provenance** resolvable to a `run.json` job. A pack with an
   untraceable file is invalid.
3. **A request is self-contained.** Given only a `GenerationRequest` and the referenced model
   files, a backend can reproduce the output. No request reads ambient state.
4. **The style hash covers every style-affecting input** and nothing else. Adding a `[pack]`
   option must not invalidate the cache; changing an anchor must.
5. **Immutable directories.** `runs/<id>/` and `packs/<id>/` are never modified after the run
   finishes or the pack is published. Corrections produce new ids.
6. **A gate never mutates an artifact.** Gates measure; postprocessing changes. Anything that
   changes pixels must be a declared step in the chain, in order, and recorded.
7. **Failure is contained to a job.** One failed asset yields a `partial` run and a pack that
   omits it; it never yields a pack containing a half-finished file.
8. **No silent downgrade.** If a gate is skipped (e.g. `seamless_tile` on a non-tile kind), the
   result records `skipped`, never `pass`.

---

## 5. Rejected terms

| Rejected | Why |
|---|---|
| "Sprite" for any image asset | Terrain tiles and UI frames are not sprites; the word hides kind-specific rules |
| "Workflow" | Overloaded: means a ComfyUI graph, our recipe, and the user's process. Say **recipe** (ours) or **graph** (ComfyUI's) |
| "Config" | Ambiguous between `sdga.toml` (file), StyleContract (resolved), and request params. Name the specific one |
| "Export" | Implies a one-way dump. Say **publish** (creates a pack) |
| "Model" | Collides with ML models. Say **domain type** or name the type |
