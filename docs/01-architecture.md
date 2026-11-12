# Architecture

> Status: **proposed** — this document, together with
> [03-contracts-and-schemas.md](03-contracts-and-schemas.md) and
> [06-implementation-plan.md](06-implementation-plan.md), is the specification for the
> first implementation. It supersedes the structural advice in
> [stable-diffusion-pixel-art-pipeline.md](stable-diffusion-pixel-art-pipeline.md),
> which is retained as the *domain reference* (models, nodes, prompt craft, Godot setup).

---

## 1. The problem with the current shape

The source guide describes a working pipeline, but it is not a *system*. Everything lives in
one game project folder, every script hardcodes `D:\GameProject\...`, and the generation
logic is entangled with three things it should not know about:

| Entanglement | Consequence |
|---|---|
| Python scripts that assume a local ComfyUI checkout | Cannot run against a remote/GPU box, cannot test without a GPU |
| Node class names (`PaletteMatch`, `MakeImageTile`) treated as fixed API | One custom-node rename breaks every workflow, with no way to detect it up front |
| Output paths inside the Godot project (`res/art/...`) | The asset factory cannot be versioned, reviewed, or reused across games |
| `images[0]` from `/history` as "the output" | Silently picks the wrong image when a graph has batches or multiple savers |
| No record of what produced an asset | Regenerating a rejected asset is impossible to reproduce |

The design below fixes this by putting a hard seam around each of those three external
systems: **ComfyUI**, **the Stable Diffusion model stack**, and **Godot**.

---

## 2. Non-goals and hard rules

These are enforced by review and (where possible) by CI, not by convention alone.

1. **No ComfyUI import.** Nothing in `src/sdga/` may `import comfy`, `import nodes`, or add a
   ComfyUI directory to `sys.path`. ComfyUI is reachable only over HTTP/WebSocket. CI runs the
   test suite in an environment where ComfyUI is not installed.
2. **No engine dependency.** No Godot binary, no `.tscn` authoring, no GDScript execution.
   Godot is a *consumer* of a published asset pack. Engine-specific output is optional,
   generated as data, and off by default.
3. **No machine-specific paths.** No absolute paths in code or config. All paths resolve
   relative to a declared project root or come from config.
4. **No unverifiable dependency.** A recipe may not assume a node or model exists. It declares
   what it needs; the backend probe verifies it before submission (see §6).
5. **No untracked generation.** Every produced file is described by a manifest entry carrying
   its provenance. Files that are not in a manifest are not part of the pack.

---

## 3. Layering

```
┌──────────────────────────────────────────────────────────────────────┐
│  cli / api          sdga plan | run | validate | publish | doctor    │
├──────────────────────────────────────────────────────────────────────┤
│  pipeline           orchestration: plan → run → postprocess →        │
│                     validate → publish. Owns job state & retries.    │
├──────────────────────────────────────────────────────────────────────┤
│  planning           AssetSpec → GenerationRequest[]                  │
│                     seed derivation · cache key · dependency order   │
├──────────────────────────────────────────────────────────────────────┤
│  model              pure domain types (no I/O)                       │
│                     StyleContract · AssetSpec · GenerationRequest    │
│                     Artifact · RunRecord · PackManifest              │
├──────────────────────────────────────────────────────────────────────┤
│  postprocess        pure array→array transforms (PIL/numpy)          │
│  validate           pure checks over Postprocessed artifacts         │
├──────────────────────────────────────────────────────────────────────┤
│  backends           ┌─────────────┐   ┌──────────────┐              │
│                     │ comfyui     │   │ fake         │  ← the ONE   │
│                     │ (HTTP/WS)   │   │ (fixtures)   │    real seam │
│                     └─────────────┘   └──────────────┘              │
└──────────────────────────────────────────────────────────────────────┘
        ▲                                        ▲
        │ HTTP/WS, out of process                │ files only
   ┌────┴─────┐                            ┌─────┴──────┐
   │ ComfyUI  │  ← any host, any version  │ Godot (or  │
   │ + models │    pinned by capability    │ any engine)│
   └──────────┘    manifest                └────────────┘
```

**Direction of dependency is strictly downward.** `postprocess` and `validate` never import
`backends`. `model` imports nothing from the project. This is what makes the pipeline testable
on a laptop with no GPU and no ComfyUI.

---

## 4. The single seam

There is exactly one place in the codebase where behaviour varies by external system, and
exactly one thing a test double has to implement:

```python
class GenerationBackend(Protocol):
    def probe(self) -> BackendProfile:
        """Report identity + capabilities. Cheap; safe to call often."""

    def submit(self, request: GenerationRequest) -> JobHandle:
        """Queue one generation. Must not block on completion."""

    def poll(self, handle: JobHandle) -> JobStatus:
        """Return pending | running(progress) | succeeded(artifacts) | failed(error)."""

    def cancel(self, handle: JobHandle) -> None: ...

    def fetch(self, artifact: ArtifactRef, dest: Path) -> Path: ...
```

Everything else — prompt assembly, palette snapping, downscaling, centring, seam checks, loop
padding, manifests — is a pure function over files or arrays and is tested directly.

Two adapters justify the seam: `ComfyUIBackend` (real) and `FakeBackend` (fixtures). A third
(`ReplayBackend`, which re-serves a recorded run) comes free once the run record format exists,
and is what makes regression tests possible after model upgrades.

> Design note (deep module): `submit` takes the *semantic* request, not a node graph. Graph
> construction lives inside the ComfyUI adapter. Adding an asset kind changes a recipe file,
> not the pipeline. Adding a backend changes one package, not the recipes.

---

## 5. Data flow

```
 assets/*.yaml  ─┐
 style.toml     ─┼─► plan() ─► GenerationRequest ─► backend.submit ─► raw artifact
 palette files  ─┘        │                                              │
                          │                                              ▼
                          │                                    postprocess ops
                          │                                    (ordered, declared
                          │                                     per asset kind)
                          │                                              │
                          │                                              ▼
                          │                                          validate
                          │                                              │
                          ▼                                              ▼
                    RunRecord (json)  ◄────────────────────────  PackManifest
                    runs/<id>/                                  packs/<id>/
```

Three artifacts on disk, each with a single owner:

| Artifact | Owner | Immutable? | Purpose |
|---|---|---|---|
| `runs/<run_id>/run.json` | pipeline | yes | provenance: request, style hash, seed, backend profile, recipe hash, gate results |
| `runs/<run_id>/raw/*` | backend | yes | exactly what the backend returned, untouched |
| `packs/<pack_id>/` | pack | yes (new id per publish) | what an engine consumes: files + `pack.json` |

`run.json` is the unit of reproducibility. `pack.json` is the unit of consumption. Keeping them
separate means you can re-publish an old pack, or validate a run without publishing it.

---

## 6. Capability probing (the fix for brittle node names)

The source guide hardcodes node class names and model filenames. Any of these can be missing,
renamed, or shadowed by a different custom-node pack. ComfyUI's `/object_info` already answers
every question we need, so we ask it instead of assuming:

- **node present?** `"<Class>" in object_info`
- **model present?** combo inputs enumerate their options on disk, so
  `"sd_v1-5.safetensors" in object_info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]`
- **input shape changed?** compare `input.required` keys against the recipe's bound paths
- **deprecated/experimental?** `object_info[cls].get("deprecated") / .get("experimental")`
- **server identity?** `/system_stats` → `system.comfyui_version`, `system.pytorch_version`,
  `devices[].vram_total`
- **is it busy?** `/queue` → `queue_running`, `queue_pending`

`probe()` returns a `BackendProfile` that is written into `run.json`. Two runs with different
profiles are not comparable, and the pipeline refuses to claim reproducibility across them.

`sdga doctor` runs the probe against every recipe and prints a table of missing nodes, missing
model files (with the ComfyUI folder each belongs in), and recipes that will fail. This runs in
under a second and replaces the "it just doesn't work" failure mode.

---

## 7. Where each style layer is enforced

The source doc lists seven style-enforcement layers. Splitting them by *owner* is the key
modularity decision — most of them should not live inside ComfyUI at all:

| Layer | Enforced by | Why there |
|---|---|---|
| Neural style (LoRA) | ComfyUI graph | Must be in the sampler |
| Prompt anchors | `planning` | Deterministic string assembly, unit-testable |
| Composition (IP-Adapter) | ComfyUI graph | Must be in the sampler |
| Pose (ControlNet) | ComfyUI graph | Must be in the sampler |
| **Palette** | **postprocess** | Deterministic, testable, backend-independent |
| **Resolution grid** | **postprocess** | Same |
| **Alpha / transparency** | postprocess | Same |
| **Engine render settings** | engine adapter (data) | Advisory output, not our process |

Moving palette matching and downscaling out of ComfyUI removes the dependency on
`PaletteMatch`-style custom nodes entirely, makes the result identical for any backend, and
turns "did the style hold?" from a visual judgement into an assertion.

Corollary: **generation is allowed to be imprecise; post-processing must be exact.** Everything
after the sampler is deterministic and asserted. Everything before it is best-effort and
recorded.

---

## 8. Repository layout

```
stable-diff-game-asset-generator/
├── README.md
├── pyproject.toml                 # package: sdga · entry point: sdga
├── docs/                          # this documentation set
├── src/sdga/
│   ├── cli.py                     # argparse/typer surface; no business logic
│   ├── config.py                  # style.toml + project.toml loading, path resolution
│   ├── model/                     # domain types only, no I/O
│   ├── planning/                  # spec → requests, seeds, cache keys
│   ├── pipeline/                  # orchestration, run records, resume
│   ├── backends/
│   │   ├── base.py                # Protocol + shared types
│   │   ├── comfyui/               # http client, graph binder, probe, recipe loader
│   │   └── fake.py                # deterministic fixture backend
│   ├── postprocess/               # one module per op family
│   ├── validate/                  # one module per gate family
│   ├── pack/                      # manifest, publish, provenance
│   ├── audio/                     # leitmotif transform, stem plan, loop engineering
│   └── adapters/                  # optional engine adapters (godot.py), off by default
├── recipes/                       # data: graph templates + `requires` blocks
├── palettes/                      # checked-in palettes (.gpl/.png) + licenses
├── examples/                      # a minimal example project
└── tests/{unit,contract,fixtures}
```

`recipes/` and `palettes/` are data. They are versioned, diffable, and reviewed like code but
never imported.

---

## 9. Runtime topology

```
 sdga (any host)  ──HTTP──►  ComfyUI (GPU host)      # one config line
                  ──WS────►  /ws?clientId=…          # progress + errors
      │
      └── files ──────────►  packs/<id>/             # consumed by engine or CI artifacts
```

Supported topologies with no code change:

- **Same box** — `backend.url = "http://127.0.0.1:8188"` (default)
- **GPU box on LAN** — `backend.url = "http://192.168.1.50:8188"` (requires `--listen`)
- **CI without GPU** — `backend.kind = "fake"`; exercises the whole pipeline to the pack
- **Human review box** — `sdga validate packs/<id>` runs with no backend at all

---

## 10. Failure containment

| Failure | Where it surfaces | Behaviour |
|---|---|---|
| ComfyUI not running | `probe()` | `doctor`/`plan` fail fast with the URL it tried |
| Node/model missing | `probe()` | Names the recipe, the missing node, the folder to install into |
| Invalid graph | `POST /prompt` → 400 + `node_errors` | Recorded verbatim in `run.json`; no retry (it is a bug, not a flake) |
| Node raises during execution | WS `execution_error` | Recorded; job marked failed; asset excluded from pack |
| VRAM OOM | `execution_error` | Retried once with a queued/serialised request; then failed |
| Backend dies mid-run | WS disconnect / poll timeout | Resume by re-submitting with the same `prompt_id` |
| Gate failure (e.g. palette drift) | `validate` | Asset marked `rejected`; pack omits it; run marked `partial` |
| Wrong image picked | `output_node` declared per recipe | Not possible by construction |

The resume path is why the backend must accept a caller-supplied `prompt_id`: ComfyUI treats
`prompt_id` as idempotent-ish input (`prompt_id = json_data.get("prompt_id", uuid4())`), so a
restarted orchestrator can re-submit the identical job and pick up the same history entry
instead of generating a second, different asset.

---

## 11. Extension points

| I want to… | Touch |
|---|---|
| Add an asset kind | `recipes/<kind>.yaml` + an `AssetKind` entry + postprocess chain + gates |
| Change a model or node | `style.toml` / recipe `requires`; no Python |
| Add a backend (SD.Next, a hosted API) | one package implementing `GenerationBackend` |
| Add an engine | one module in `adapters/`, consuming `pack.json` |
| Add a validation rule | one function in `validate/` registered by asset kind |
| Add a postprocess op | one function in `postprocess/`, referenced by name in the chain |

No extension requires editing the pipeline or the CLI.

---

## 12. Why not the alternatives

- **A ComfyUI custom-node pack.** Would put our logic inside ComfyUI's process, pin us to its
  Python environment, and make it impossible to test without a GPU. It also cannot own
  post-generation validation or packaging, which is where most of the value is.
- **A Godot editor plugin.** Couples asset production to a running editor, cannot run in CI,
  and would put generation code into the game repo the user explicitly wants to keep clean.
- **A monolithic script per asset type** (as in the source guide). Repeated 200-line scripts
  with hardcoded paths; each bug must be fixed N times. The `deletion test` fails: delete one
  and the complexity reappears in the caller.
- **An LLM-in-the-loop composer.** Tempting for prompt writing, but non-deterministic and
  unversionable. Prompt assembly stays deterministic string templating; an LLM may later
  *propose* `assets/*.yaml`, which is then reviewed and committed like any other data.
