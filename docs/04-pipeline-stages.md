# Pipeline Stages

> One pass of `sdga run` is eight stages. Each stage has a single responsibility, a defined
> input and output, and a failure behaviour. Stages 1–2 and 4–6 need no backend and no GPU.

```
0 doctor ─► 1 plan ─► 2 resolve ─► 3 submit/collect ─► 4 postprocess ─► 5 gate ─► 6 review ─► 7 publish ─► 8 adapt
             ▲                                  │
             └────────── resume ─────────────────┘
```

---

## 0. doctor

**In:** config, recipes. **Out:** `BackendProfile` + a report. **Fails when:** a recipe requires a
node or model the backend does not have.

Runs `probe()`: `GET /object_info`, `GET /system_stats`. Produces:

- node presence per recipe (`object_info[cls]` exists)
- model presence per loader — combo inputs enumerate on-disk options, so
  `"sd_v1-5.safetensors" in object_info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]`
- flagged nodes (`deprecated`, `experimental`)
- input-shape drift: every `${expr}` in the graph must resolve to a path that still exists in
  `object_info[cls].input.required` or `.optional`
- VRAM, ComfyUI version, torch version

Output is one table plus a `profile_hash`. `doctor` is also the first thing CI runs against a
recorded profile fixture, so a recipe that silently depends on a renamed node fails the build.

---

## 1. plan

**In:** `assets/*.yaml`, `sdga.toml`, palette, references. **Out:** `[GenerationRequest]`.

Steps, in this exact order (order matters for cache stability and prompt reproducibility):

1. **Load and validate specs.** Unknown keys error. Ids unique. `depends_on` acyclic. Every
   referenced file exists.
2. **Assemble prompts.** `", ".join(positive_anchors) + ", " + spec.prompt`. Anchors always
   precede the subject — that is the convention the LoRA was trained under. Negative is either
   the spec's full override or `", ".join(negative_anchors)`. Never string-concatenate a
   negative onto the default; override is all-or-nothing.
3. **Resolve size.** `size` is final pixels; the backend render size is
   `generation_size` for `concept`/`terrain_tile`/`ui_element`, and
   `cell * frames_scaling` for sheets. Assert `final % grid == 0`.
4. **Derive the seed.** `derived`: `int.from_bytes(sha256(f"{asset_id}|{style_hash}|{candidate_index}").digest()[:4], "big")`.
   This makes the seed a pure function of identity, so adding an unrelated asset never changes
   an existing asset's output. `random` seeds are generated once and stored in `plan.json`.
5. **Resolve references by role.** Content-hash each file. De-duplicate identical bytes across
   assets so the same palette/pose uploads once.
6. **Bind the recipe.** Load recipe + graph, bind `${slots}`, validate node links, assert the
   `output_node` exists and is an output node.
7. **Compute `request_hash`.** Canonical JSON (sorted keys, no whitespace) over the body minus
   volatile fields.
8. **Write `plan.json`** (also printed by `--dry-run`).

`plan` is deterministic and side-effect-free: same inputs, byte-identical `plan.json`. That
property is what makes cache hits, regression diffs, and `--dry-run` review possible.

---

## 2. resolve (cache)

**In:** requests. **Out:** requests partitioned into `hits` (artifact already on disk) and
`misses`.

A hit requires **all** of:

- `request_hash` present in the cache index
- `profile_hash` equal to the current one
- the cached file's `sha256` still matches the index (catches hand-edited artifacts)

On a hit, copy (or hard-link) the raw artifact into the new run and mark `cached: true`. No
backend call. `--force` ignores the cache; `--no-cache` neither reads nor writes it.

Cache is a flat directory + a JSON index. It must be safe to delete at any time.

---

## 3. submit / collect

**In:** requests. **Out:** raw artifacts + terminal status per job.

### Submission

```
POST /prompt  { "prompt": <bound graph>, "client_id": <stable per-process uuid>,
                "prompt_id": <request-derived uuid5> }
→ 200 { "prompt_id", "number", "node_errors" }
→ 400 { "error", "node_errors" }        ← graph bug; never retried
```

`prompt_id` is supplied by us, derived as `uuid5(NAMESPACE, request_hash)`. ComfyUI honours a
caller-supplied id (`prompt_id = json_data.get("prompt_id", uuid4())`), which gives us:

- **idempotency** — re-submitting after a crash reuses the same history entry
- **correlation** — a job is traceable across process restarts and log files
- **resume** — `sdga run --resume` re-reads run.json, and for any job in `submitting`/`running`
  asks `GET /history/<prompt_id>` first; if it completed, fetch instead of regenerating

### Progress

`GET /history/<prompt_id>` is polled at `poll_interval_s` as the source of truth. The WebSocket
(`/ws?clientId=…`) is used only for responsive progress and early error detection.

Events that must be handled:

| Event | Handling |
|---|---|
| `executing {node, prompt_id}` | update progress; `node == null` **and** matching prompt_id ⇒ terminal |
| `executed {node, output}` | note node outputs (partial results) |
| `execution_error {node_id, node_type, exception_message}` | terminal failure, recorded verbatim |
| `progress` | progress only |
| binary frame | **ignore** — these are preview JPEGs; a naive `json.loads(recv())` crashes here |
| disconnect | fall back to polling; never assume failure |

Polling-only operation must work with the WebSocket disabled. Treat the socket as an
optimisation, not a requirement.

### Collection

- Take the artifact from `history[prompt_id]["outputs"][output_node]["images"][0]` — the recipe
  declares which node, so batches and multiple savers cannot be confused.
- `GET /view?filename=&subfolder=&type=output` → write to `runs/<id>/raw/<asset-slug>.png`.
- Hash it, record dimensions, and verify it is a decodable image **before** post-processing.
- If the declared output node produced nothing, fail the job with `bad_output`.

### Ordering and concurrency

`max_concurrency` defaults to 1. With one GPU, submitting two jobs at once does not make either
faster and does make OOM more likely. Concurrency > 1 is supported (each job is independent) but
must be an explicit opt-in.

---

## 4. postprocess

**In:** raw artifact. **Out:** postprocessed artifact(s). Pure functions, declared as an ordered
chain per asset kind. Every op is independently testable with a fixture and a golden output.

| Op | Algorithm | Notes |
|---|---|---|
| `downscale_box` | `Image.resize(target, BOX)` | **Default.** Averages the render before snapping; preserves structure |
| `downscale_nearest` | `Image.resize(target, NEAREST)` | Only when the render is already grid-aligned and hard-edged |
| `palette_snap` | nearest palette colour in OKLab, per unique RGB, via LUT; alpha preserved; un-premultiply first if source is premultiplied | The colour lock. See §4.1 |
| `alpha_hard` | `alpha = where(alpha >= 128, 255, 0)` | Pixel art has binary alpha; removes fringe |
| `alpha_trim` | crop to `alpha > 0` bbox | Before centring |
| `center_anchor` | translate so that the bbox's `(center_x, bottom)` lands on the cell's `(center_x, bottom - 1)`, or `center` mode | `feet` default for characters — see §4.2 |
| `frame_grid` | split by declared `layout.cols/rows`; assert `sheet_w == cols*cell_w` | Never infer cols from width |
| `ninepatch_mirror` | mirror left→right, top→bottom | Guarantees symmetry; compute and record margins |
| `tile_offset_blend` | roll by `(w/2, h/2)`, crossfade a `band` px seam with smoothstep | Seamless fallback without circular sampling |
| `tile_mirror` | 2×2 mirror | Always seamless, obviously symmetric; use only for organic textures |
| `depth_to_normal` | blur σ=1 → Sobel gradients → `n = normalize([-gx*s, -gy*s, 1])` → `rgb = n*0.5+0.5` | Depth ≠ normal. See §4.3 |
| `pad_to_grid` | pad/crop to a multiple of `grid`, anchored per kind | Prevents 31×32 assets |
| `despeckle` | remove isolated pixels whose 4-neighbours all differ, below `min_area` | Optional; off by default |

Chains per kind (defaults, overridable in spec):

```yaml
concept:        [downscale_box, alpha_hard, despeckle, pad_to_grid]
terrain_tile:   [downscale_box, palette_snap, alpha_hard, pad_to_grid]
sprite_sheet:   [frame_grid, alpha_hard, alpha_trim, center_anchor, palette_snap, pad_to_grid]
ui_element:     [downscale_box, palette_snap, alpha_hard, ninepatch_mirror]
icon:           [downscale_box, palette_snap, alpha_hard, center_anchor]
normal_map:     [downscale_box, depth_to_normal, pad_to_grid]
```

### 4.1 Palette snapping, precisely

1. Load the palette from `.gpl` or `.png`. Palettes are data files with a content hash; the hash
   goes into the manifest so a consumer can prove which palette was enforced.
2. Convert palette and image to OKLab (sRGB → linear → LMS → OKLab). Nearest-neighbour in OKLab
   matches perceived distance far better than RGB, and avoids the classic "dark green snaps to
   black" failure.
3. Build a LUT over the **unique** colours in the image (after downscale: typically < 600).
4. Write back, preserving alpha exactly. Do not composite against white — that creates halos on
   transparent edges.
5. Idempotent by construction: snapping a snapped image is a no-op. Assert this in a test.

The palette itself is chosen once, by hand: `sdga palette extract` samples an authored image into
a `.gpl`/`.png`, a human reviews it, and the result is committed. Extraction is **not** an op and
never runs per asset — a palette derived per image is the opposite of a lock, and would let each
asset drift onto its own colours.

### 4.2 Why `feet` anchoring, not bbox centring

The source guide centres each frame by its bounding-box midpoint. For a walk cycle that makes the
character *bob*: the bbox grows when legs are apart and shrinks when together, so the midpoint
moves even though the character did not. Anchoring `(center_x, bottom)` to a fixed line keeps the
ground contact stable. `center` remains available for icons and objects with no feet.

Guard: if the bbox is empty, the frame is all-transparent — that is an error, not a silent skip
(the source script `continue`s, producing a frame that silently holds the previous pose).

### 4.3 Depth → normal, precisely

A depth map is a height field; a normal map is its gradient, re-encoded. Skia/Godot 2D expect:

```
h  = blur(depth, σ=1) normalized to [0,1]
gx = sobel_x(h);  gy = sobel_y(h)
n  = normalize([ -gx * strength, -gy * strength, 1.0 ])
out = (n * 0.5 + 0.5) * 255
```

Encoding a depth map as a normal texture (what the source guide's workflow does) makes every
pixel point almost straight at the camera — lighting will look flat and wrong. `flip_g` is exposed
because Godot's 2D normal convention differs from the OpenGL convention used by most generators;
verify once with a `normal_sphere` fixture and then trust the flag.

---

## 5. gate

**In:** postprocessed artifact + spec. **Out:** `[GateResult]`. Deterministic; no backend.

| Gate | Check | Default |
|---|---|---|
| `dimensions_exact` | `w, h == spec.size` (per cell for sheets) | error |
| `grid_divisible` | `w % grid == 0 and h % grid == 0` | error |
| `frame_count` | `len(frames) == spec.frames`; sheet dims match `layout` | error |
| `frames_aligned` | anchor y-coordinate within ±1 px across frames | error |
| `palette_conformance` | `set(unique_rgb) ⊆ palette`; value = count | error |
| `max_unique_colors` | `len(unique_rgb) <= threshold` | error |
| `alpha_required` | alpha channel exists; `mean(alpha==0) > 0.05` | error |
| `binary_alpha` | every alpha ∈ {0, 255} (after `alpha_hard`) | error |
| `seamless_tile` | `edge_diff / interior_diff <= ratio`. `edge_diff = mean|I[:,0]-I[:,-1]| + mean|I[0,:]-I[-1,:]|`; `interior_diff` = same measure on randomly sampled interior adjacent lines | error, 1.5 |
| `symmetry_9patch` | `I == mirror(I)` bitwise; margins declared and `2*max(margin) < edge` | error |
| `normal_map_valid` | mean encoded z > 0.5; `abs(‖rgb*2-1‖ - 1) < 0.05` for >99% of pixels; no zero pixels | error |
| `aa_suspect` | fraction of pixel pairs with `0 < Δ < 3` (near-identical neighbours indicating anti-aliasing) above 0.15 | warn |
| `audio_peak` | `peak_dbfs` within ±0.5 of target | error |
| `audio_loop_seam` | `|x[-1] - x[0]| <= 3 * median(|diff(x)|)` and wrap-window RMS within 3 dB of interior RMS | error |
| `audio_clip` | `count(|x| >= 1.0) == 0` | error |
| `beat_alignment` | `len(x)` within 1 sample of `bars * beats * 60 / bpm * sr` | error |

Gates never repair. If `palette_conformance` fails it means `palette_snap` was skipped or a
non-sRGB profile slipped through — fix the chain, not the gate.

`warn` results are recorded and do not block publishing. `error` results mark the job `rejected`
and exclude the asset from the pack.

---

## 6. review

**In:** gated assets. **Out:** `approved | rejected | superseded` per asset.

Machine gates cannot judge "does this look like the character". Review is the human gate:

- `sdga review` writes to `run.json` (append-only history of decisions, not a mutable field)
- a `review.html` contact sheet is generated per run, with reference and result side by side
- `require_review = true` means unpublished-but-approved-nothing is the default state — publishing
  is an explicit act

For agent-driven workflows, review is where a human clicks; everything before it is automatable.

---

## 7. publish

**In:** approved assets from one or more runs. **Out:** `packs/<pack_id>/`.

1. Refuse if two assets share an id.
2. Copy files to `assets/<namespace>/<name>[_role].<ext>`. Roles: `albedo`, `normal`, `mask`,
   `loop`, `melody`.
3. Write `pack.json` with sorted assets, computed checks, provenance.
4. Write `MANIFEST.sha256` and `LICENSES.md` (palette + model + font licenses).
5. Packs are immutable: `publish` always creates a new `pack_id` from `id_template`.

Publishing is the only operation that produces something an engine reads. Nothing else in the
pipeline writes outside `runs/` and `.sdga/`.

---

## 8. adapt (optional)

`sdga adapt --engine godot` reads a pack and emits engine hints as data:

- a `godot_import.json` mapping files to import settings (`filter=false`, `mipmaps=false`,
  compression per kind)
- `NinePatchRect` margins from `engine.ui.margins`
- an `AnimatedSprite2D` `SpriteFrames` descriptor (`frame size`, `cols`, `fps`)
- an audio bus map from `engine.audio.bus`

It does **not** write `.tscn` files, does not require Godot, and is off unless invoked. A separate
Godot-side importer (out of scope for this repo) consumes these files.

---

## 9. Resume, retries, and idempotency

| Situation | Behaviour |
|---|---|
| Process killed mid-run | `run.json` retains job states; `--resume` re-plans, reuses cache hits, and for in-flight jobs checks `/history/<prompt_id>` before re-submitting |
| Backend down at start | Fail before submitting anything (stage 0) |
| Backend dies mid-run | Jobs in `running` become `timeout`; retried per `retry.attempts` |
| OOM | One retry with concurrency forced to 1, then `failed` with a printed remedy |
| Repeat invocation, nothing changed | All hits; no backend calls; pack is byte-identical |
| Same asset, different candidate count | Different seeds for indices ≥ old count; earlier candidates are cache hits |

Byte-identical republish is a testable property and a CI check: run the fake backend twice, diff
the two `pack.json` files with `created`/`pack_id` excluded.

---

## 10. The audio path

Same eight stages, different backend and ops. Two sub-pipelines:

**SFX (one-shot)**

```
plan: prompt + duration + sample rate
→ backend: audiogen ← optional, local model
→ postprocess: trim_silence, loudness_normalize(-3 dBFS), fade_edges(5 ms)
→ gates: audio_peak, audio_clip, duration_exact
```

**Music (leitmotif-derived)**

```
1. leitmotif/*.mid  ── transform ──► per-track MIDI (scale, tempo, fragment, transpose)
2. MIDI ── fluidsynth + soundfont ──► melody WAV  (deterministic, no AI)
3. melody WAV + prompt ── backend ──► backing stem (AI, texture only)
4. melody WAV + backing stem ── mix ──► full track   ← authored melody is sample-exact
5. loop_crossfade to bar-aligned length
6. gates: beat_alignment, audio_loop_seam, audio_peak
```

Step 4 is the important deviation from the source guide: the melody is **mixed in**, not
conditioned for. See [05-gap-analysis.md](05-gap-analysis.md#f-music-pipeline-specifically). This is what makes "one
leitmotif across every track" a guarantee instead of a hope.

Loop length must satisfy `duration_s = bars * beats_per_bar * 60 / bpm`, and the loop op shortens
the file by the crossfade length, so the plan must solve for `L = target + fade`.

---

## 11. Determinism, honestly

What is guaranteed:

- `plan.json` is byte-identical for identical inputs.
- Postprocess and gates are deterministic across machines.
- Same seed + same graph + same model files + same backend version ⇒ same output **on the same
  GPU and driver**. Across hardware, sampler kernels differ and outputs drift.
- Cache keys include `profile_hash`, so a driver/model change invalidates rather than silently
  mixing.

Do not claim more than this. `run.json` records the profile precisely so that "reproducible" is
always qualified by "on this profile".
