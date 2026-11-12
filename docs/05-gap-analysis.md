# Gap Analysis: What Holds Up, What Doesn't

> Review of [stable-diffusion-pixel-art-pipeline.md](stable-diffusion-pixel-art-pipeline.md),
> checked against this machine's actual ComfyUI install (0.23.0) and the relevant upstream
> behaviour. Each finding is classified, evidenced, and given a resolution. Nothing here is
> changed in the source document — it stays as the domain reference, and this file is the
> correction layer.

---

## Method

Three kinds of check:

1. **Node-class existence** — extracted `NODE_CLASS_MAPPINGS` from every installed pack and
   grepped for every `class_type` the guide uses.
2. **API-contract behaviour** — read `ComfyUI/server.py` and `execution.py` at the endpoints and
   events the guide relies on.
3. **Algorithm review** — re-derived the maths in the guide's shipped scripts (sprite centring,
   model mirroring, palette extraction, loop engineering, scale snapping).

Severity: **S1** = will not run / produces wrong files; **S2** = silently degrades quality or
reproducibility; **S3** = friction, hardening, or documentation debt.

---

## A. Things that will not run as written

### A1 · `PaletteMatch` does not exist — S1

The guide's central style-lock chain is `[VAE Decode] → Palette Match → Downscale → Save`, with
`PaletteMatch` attributed to "ComfyUI-Essentials".

**Evidence:** no node class matching `Palette*` exists in `comfyui_essentials`,
`comfyui_controlnet_aux`, `comfyui_ipadapter_plus`, `comfyui-animatediff-evolved`,
`comfyui-layerdiffuse`, `ComfyUI-post-processing-nodes`, or `ComfyUI-VFI`. The closest primitives
found anywhere are `KMeansQuantize` / `Quantize`, which reduce an image to *N* clusters — they do
not match a supplied palette file, and clustering produces different colours per image, which is
the opposite of a palette lock.

**Resolution:** move palette enforcement into our own postprocess (`palette_snap`, OKLab
nearest-neighbour against a `.gpl`/`.png` palette). Deterministic, testable, backend-independent,
and it makes palette conformance a gate (`palette_conformance`) rather than an assumption. This is
[04-pipeline-stages.md §4.1](04-pipeline-stages.md).

### A2 · `MakeImageTile` does not exist — S1

The terrain pipeline depends on it for seamlessness.

**Resolution:** seamlessness is not a node problem. Two supported paths: (a) generate with
circular/asymmetric padding so the VAE sees wrapped edges, then crop; (b) post-process with
`tile_offset_blend` (roll-by-half + crossfade) or `tile_mirror`. Both are ours, both are gated by
`seamless_tile`. Note in the docs that (b) trades symmetry for seamlessness and (a) is preferred
for organic textures.

### A3 · Wrong class names for VFI and LayerDiffuse — S1

| Guide says | Actually installed |
|---|---|
| `RIFE_VFI` | `RIFEInterpolation` |
| "LayerDiffuse Alpha" node | `LayeredDiffusionApply` (and `LayeredDiffusionDecodeRGBA`) |

**Resolution:** class names live in recipe files, and every recipe declares `requires.nodes`. The
probe fails at `doctor`/`plan` time with the exact missing name instead of at generation time with
a 400 from `/prompt`. This is the structural fix that makes A1–A3 a class of problem that cannot
recur silently.

### A4 · `generate_normal_map` produces a depth map called `_normal.png` — S1

The guide feeds the albedo into `MiDaS-DepthMapPreprocessor` and saves the result as the normal
map. A depth map is a scalar height field; a normal map is a 2-component gradient encoded in RGB.
Every pixel of a depth-as-normal texture points nearly straight at the camera, so `PointLight2D`
lighting will be flat and subtly wrong rather than obviously broken — the worst failure mode.

**Resolution:** `depth_to_normal` op with the Sobel derivation, plus `normal_map_valid` gate
(mean encoded z, unit-length check, no zero pixels), plus a `normal_sphere` fixture and an explicit
`flip_g` flag for Godot's 2D convention.
See [04-pipeline-stages.md §4.3](04-pipeline-stages.md).

### A5 · `make_seamless_loop.py` does not make a seamless loop — S1

The script splits at the midpoint, swaps halves, then applies a fade *at the new midpoint*.

Two errors:

1. **Wrong seam.** Swapping `A|B` into `B|A` makes the new centre continuous (it is the original
   midpoint, which was already continuous) and leaves the **loop wrap** — `A`'s end into `B`'s
   start — exactly as discontinuous as before. That boundary is the one the listener hears on
   repeat.
2. **Attenuating a continuous point.** The fade is applied where the audio was already continuous,
   so it produces an audible dip in the middle of the loop and nothing at the wrap.

**Resolution:** overlap-add crossfade of the tail into the head:

```
L  = target_length + fade_length          # solve for L from bars/beats/bpm
h  = orig[L-fade : L]                      # tail
o  = orig[0 : fade]                        # head
out = concat( crossfade(h, o), orig[fade : L] )   # length L - fade
```

with an equal-power (`sin/cos`) curve to hold perceived loudness constant through the fade. Then
gate it: `audio_loop_seam` compares `|x[-1]-x[0]|` against the median first difference and
compares wrap-window RMS against interior RMS. See
[04-pipeline-stages.md §10](04-pipeline-stages.md).

### A6 · `json.loads(ws.recv())` hangs or crashes — S1

`WorkflowBuilder.wait_for_completion` decodes **every** WebSocket frame as JSON. ComfyUI sends
binary preview frames during sampling, so this raises immediately on the first preview. The
`generate_factory.py` variant guards on `isinstance(out, str)` but has no exit path for
`execution_error`, so a failed node loops forever with no timeout.

**Resolution:** treat the socket as an optimisation, poll `/history/<prompt_id>` as the source of
truth, ignore binary frames, handle `execution_error`, and impose `timeout_s`. Contract in
[03-contracts-and-schemas.md §7](03-contracts-and-schemas.md).

---

## B. Correct but fragile

### B1 · `images[0]` from `/history` — S2

The guide takes the first image of the first output node. Any graph with a batch, a preview saver,
or two `SaveImage` nodes publishes the wrong file, silently.

**Resolution:** recipes declare `output_node`. Collection reads that node only; missing output is
`bad_output`, not "pick another".

### B2 · Nearest-neighbour downscale as the default — S2

`scale_by 0.0625` with `Nearest` on a 512 px AI render gives a 32 px image that is a point-sample
of a noisy field: broken outlines, lost 1-px details, random colour jumps. Nearest is the right
*resampling for pixel art that is already pixel art*; it is the wrong filter for a continuous-tone
render.

**Resolution:** `downscale_box` as default (area-average then palette-snap), `downscale_nearest`
available when the source is already grid-aligned, and `aa_suspect` as a warn-level gate so the
difference is visible rather than a matter of taste.

### B3 · Sprite centring by bbox midpoint — S2

`center_sprite_sheet.py` centres each frame on its alpha bounding box midpoint. In a walk cycle the
bbox height changes per frame, so the midpoint moves and the character bobs vertically. The script
also `continue`s on an empty frame, silently leaving a blank cell that the engine will display as a
missing pose, and it infers `cols` from sheet width while assuming `cell_size` — two truths that
can disagree.

**Resolution:** `feet` anchor (bottom-centre) as default, `center_anchor` as the op, empty-frame as
an error, and `layout.cols/rows` declared in the asset spec with an assertion.
See [04-pipeline-stages.md §4.2](04-pipeline-stages.md).

### B4 · 9-patch symmetry without margins — S2

`enforce_9patch_symmetry.py` mirrors halves correctly, but Godot's `NinePatchRect` needs
`patch_margin_left/top/right/bottom`. A perfectly symmetric texture with default margins stretches
the wrong region. The guide never sets them.

**Resolution:** `.tres` margins are data; margins are declared in the spec, validated
(`2*max(margin) < edge`), and carried in `pack.json` as `engine.ui.margins`.

### B5 · `snap_to_scale` snaps semitones, not scale degrees — S2

`transform_leitmotif.py` transposes then snaps to the nearest scale semitone. Snapping *pitch
classes* collapses intervals and produces unisons and repeated notes, which reads as a broken
melody rather than a transposed one. It also ignores the source's own key (root is hardcoded to
middle C), and the tempo loop is a no-op (`for … : pass`) while note times are divided by
`tempo_multiplier` — double-counting tempo.

**Resolution:** rewrite the transform as degree-preserving: map each note to a **scale degree** in
the source key, then re-realise that degree in the target scale, preserving interval direction.
Derive the source key from the MIDI (key signature / pitch-class histogram) instead of assuming C.
Handle tempo once, explicitly.

### B6 · RIFE interpolation on pixel art — S2

Doubling frames with a learned interpolator invents sub-pixel colours and soft edges, which the
palette snap then has to destroy — and destroying them reintroduces stutter. The net effect is
extra compute for a worse result.

**Resolution:** generate at the target frame count, or duplicate frames with nearest-neighbour
scaling. RIFE is kept available for *concept* animation review, not for shipped sprite sheets.

### B7 · OpenPose detection on pixel art — S2

`OpenposePreprocessor` runs a learned detector trained on photographs. On a 32 px sprite it
usually finds nothing or a hallucinated skeleton. The guide assumes detector quality it will not
get.

**Resolution:** three viable paths, in order of reliability for a pixel game:
1. **Cutout animation** — generate one sprite per body part/pose set and animate with bones in the
   engine. No frame-to-frame consistency problem at all.
2. **Authored pose images** — hand-draw stick-figure/dw-pose PNGs and feed them to ControlNet
   directly as the conditioning image (no detector). Deterministic and reviewable.
3. **Per-frame img2img** — fixed seed, same style anchor, pose image per frame, then enforce
   alignment in post (`frames_aligned` gate).

The pipeline supports all three because the recipe binds references by **role** (`pose`), not by
node. The plan should default to (2) for characters and treat (3) as experimental.

---

## C. Missing capabilities

These are absent from the source guide entirely. Each is a stage or a field in the new design, not
a patch.

| # | Missing | Consequence | Where it now lives |
|---|---|---|---|
| C1 | **Provenance / run records** | Cannot reproduce, audit, or compare an asset; re-rolling after rejection is guesswork | `run.json`, `GenerationRequest` |
| C2 | **Caching** | Re-running an unchanged project regenerates every asset (hours of GPU) | stage 2 `resolve` |
| C3 | **Resume** | A crash 40 assets into 60 loses the run | `prompt_id = uuid5(request_hash)`, `--resume` |
| C4 | **Idempotent seeds** | Adding an asset perturbs others' seeds if seeds are counter-based | `seed_policy = derived` from `sha256(id|style|index)` |
| C5 | **Validation gates** | "Does the palette hold?" is a human eyeball; drift ships | stage 5, 16 gates |
| C6 | **Review state** | No record of what a human approved; publishing is implicit | stage 6, `review` CLI |
| C7 | **Candidate selection** | One shot per asset; re-roll means re-running by hand | `candidates: N` + promote/reject |
| C8 | **Engine-neutral pack** | Assets are written straight into `res/`, so the factory can't be reused or versioned separately | `pack.json` |
| C9 | **Concurrency/queue control** | Parallel scripts fight over one GPU | `max_concurrency`, single flight |
| C10 | **Error taxonomy** | Failures are tracebacks; a bad graph looks like a flaky network | closed error set (§7) |
| C11 | **Capability probing** | Node renames are discovered at generation time | stage 0 `doctor` |
| C12 | **Config without hardcoded paths** | Everything assumes `D:\GameProject` and a local ComfyUI | `sdga.toml` + relative paths |
| C13 | **Audio loop verification** | Loops are assumed good until someone hears a click | `audio_loop_seam` gate |
| C14 | **Licence tracking** | Palette/model/soundfont licences are unrecorded, which blocks shipping | `LICENSES.md` in pack |

---

## D. Quality and tuning concerns

### D1 · LoRA training configuration will overfit — S2

Proposed: 15–30 images, rank 32 / alpha 16, 20 epochs, lr 1e-4, batch 1, 512².

Baking a *style* with 15 images at rank 32 and 20 epochs typically memorises compositions and
backgrounds — the classic symptom is that every asset contains the same rock. Rank and epochs are
the wrong dials to push first.

**Resolution for the plan:** rank 8–16, alpha = rank/2, 8–12 repeats, 10 epochs max, and evaluate
at epochs 5/10 by sampling three unseen prompts. Keep the dataset *flat and uncluttered* (no
compositions you don't want repeated). Captions lead with the trigger token and describe **style
and material only**, never content that should vary. If the style will not hold at rank 8, the
problem is dataset consistency, not rank.

### D2 · 512² training for a 32 px target — S3

Not wrong (style transfers across scale), but the LoRA learns rendering detail that the 32 px
pipeline then discards. Acceptable; just don't expect the LoRA to teach crispness. Crispness comes
from `palette_snap` + `downscale_box` + binary alpha.

### D3 · Palette extraction with K-Means per image — S2

`extract_palette` clusters each concept image into 32 colours and the guide suggests feeding that
into the pipeline. Per-image palettes are the *opposite* of a palette lock: every asset gets a
different 32 colours.

**Resolution:** the project has exactly **one** palette (or a small, named, versioned set —
`day`, `night`, `cave`). Extraction is an authoring aid for *choosing* that palette, run once, and
committed. Never per-asset, never silently regenerated.

### D4 · Prompt anchoring via string concatenation — S3

`inject_prompt_into_workflow` prepends global anchors to whatever is in the node. It is fine, but
it means the graph is the source of truth for prompts, which makes review impossible.

**Resolution:** prompts are assembled in `plan` (deterministic, diffable, reviewable in
`plan.json`); the graph only receives the finished string. This also makes prompt A/B tests a diff.

### D5 · `dither: "false"` as a string — S3

Minor, but a real example of the class of bug that a schema catches: typed slots, not strings.

---

## E. Legal and provenance

### E1 · "Open-source games" for training data — S2, blocking for a shipped game

The guide suggests harvesting screenshots from open-source/public-domain games for LoRA training.
Open-source *code* does not license art. Most game asset licences forbid ML training or derivative
distribution, and a trained LoRA that reproduces a distinctive character silhouette is a
derivative-work risk regardless of the code licence.

**Resolution for the plan:** train only on art we own or that is explicitly licensed for ML use
(CC0/CC-BY with the licence recorded, or commissioned). `LICENSES.md` in the pack records the
provenance of every training image and palette. If a look is wanted from a reference game, hire
the reference as *inspiration for a human artist*, not as training data. This is a product
decision, not an engineering one, but it must be made before the first LoRA.

### E2 · Model and soundfont licences unrecorded — S3

SDXL/SD1.5, AnimateDiff, the pixel LoRAs, `GeneralUser GS`, and the fonts are all separately
licensed, some with output restrictions. The pack must state what produced it.

---

## F. Music pipeline, specifically

### M1 · Style-transfer prompt anchoring is the right idea — keep it

`CORE_SONIC_IDENTITY` + per-biome modifier is genuinely good design: it separates invariant
sonic DNA from variable texture, which is exactly the same principle as visual style anchors. No
change.

### M2 · `generate_with_chroma` does not preserve a melody — S2

MusicGen-Melody conditions on **chroma** (pitch-class energy over time), not on notes. Passing a
biome MIDI variation as `melody_wav` gives the model a harmonic suggestion, then it invents its
own melody, rhythm, and phrasing on top. The output will share broad tonality and will *not*
sound like "the same tune in a different key" — which is the entire promise of the section.

**Resolution:** **mix the authored melody in afterwards.** Render the transformed MIDI with
FluidSynth (already required for the pipeline), generate only the *backing bed* with a prompt that
explicitly says "no lead melody", then mix melody over bed with a fixed gain and a shared
reverb. The leitmotif is then sample-exact across every track by construction, and the AI is doing
what it is good at (texture, instrumentation, harmony). This also eliminates the need for
candidate rerolls when the model drifts off the tune. See
[04-pipeline-stages.md §10](04-pipeline-stages.md).

### M3 · Duration/loop arithmetic is inconsistent — S2

`BIOME_DURATION` mixes 32 s and 64 s and the guide claims both are "clean" at every biome's BPM
without solving the equation. At 90 BPM, 32 s is 12 bars (clean); at 140 BPM, 32 s is 18.67 bars
(not clean). The stated formula is right; the applied values are not all checked against it.

**Resolution:** the plan solves `length = bars*beats*60/bpm` and asserts it, then adds the loop
crossfade length. `beat_alignment` gates it.

### M4 · Audacity's scripting pipe is Windows-unreliable and untestable — S3

Two named pipes, `time.sleep`, and no error propagation; the wrapper returns strings on failure and
the caller ignores them. It also cannot be run in CI.

**Resolution:** implement the audio post chain in Python with `soundfile` + `numpy` (gain,
fades, crossfade, LUFS via `pyloudnorm`). Keep Audacity/REAPER as optional human tools, not as a
pipeline dependency. Every op becomes a pure function over `(samples, sr)` and gets a fixture test.

---

## G. What survives unchanged

Worth stating explicitly, because the corrections are numerous and the foundation is sound:

- **The layer model** (neural / colour / composition / motion / resolution / engine / audio) is the
  right decomposition. It only needs each layer assigned to a *different owner*.
- **Recipe-style prompt formulas** per asset kind (`[style], [subject], [view], [background],
  [lighting]`) — good, and worth encoding as prompt templates rather than prose.
- **LoRA + IP-Adapter + ControlNet together** is the correct three-way lock, and the stated weight
  ranges (IP-Adapter 0.7–0.85, ControlNet 0.85 until 0.8 of the schedule) are sensible starting
  points.
- **`CORE_SONIC_IDENTITY` + biome modifier** as a two-part prompt, and the *ambient bed + surfacing
  melody layer* playback idea — the latter is a genuinely good game-audio pattern.
- **Godot's Nearest texture filter as the single most important render setting** — correct.
- **`MASTER_FPS` as a shared animation clock** — correct, and rarer than it should be.
- **The asset-type taxonomy** (concept → sprite/terrain/UI/normal → audio) and the implied
  dependency order (concept art first, as the IP-Adapter anchor for everything else) — correct and
  now encoded as `depends_on`.

---

## Severity summary

| Severity | Count | Theme |
|---|---|---|
| S1 (broken) | 6 | Five node-name/algorithm errors plus a WebSocket decoder that cannot survive real traffic |
| S2 (degrades silently) | 12 | Wrong resampling, drifting sprites, un-verifiable loops, overfit LoRA, per-image palettes, licensing |
| S3 (friction) | 5 | 512² training for a 32 px target, string-typed config, prompt assembly inside the graph, missing licence tracking, untestable Audacity tooling |
| Missing outright | 14 | Provenance, cache, resume, gates, review, packs, probing, error taxonomy |

None of these invalidate the approach. All of them are addressed by one structural change: **a
backend-agnostic pipeline that owns everything after the sampler, and asserts it.**
