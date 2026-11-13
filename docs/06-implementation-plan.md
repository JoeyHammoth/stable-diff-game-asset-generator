# Implementation Plan

> The build order for the system described in
> [01-architecture.md](01-architecture.md). Tickets are a **task graph**, not a list: each names
> its blockers, so the frontier is always explicit. Every ticket has an acceptance criterion that
> can be checked without judgement.

---

## 1. Sequencing principle

**Build the half that needs no GPU first.** Roughly 60% of this system — config, planning,
contracts, postprocessing, gates, packing, resume, CLI — is pure Python and fully testable on a
laptop. If that half is solid, the GPU half becomes small and debuggable.

The order is therefore:

1. **Contracts and fakes** before real backends. A fake backend forces the seam to be real.
2. **One asset kind end-to-end** before breadth. A terrain tile proves the whole pipeline;
   adding seven more kinds afterwards is data.
3. **Gates before volume.** Generating 200 assets you can't verify is worse than 10 you can.
4. **Audio last.** It shares the skeleton but adds a second backend family and a second domain.
   Doing it before the visual pipeline is proven doubles the unknowns.

---

## 2. Phases

| Phase | Theme | Exit criterion | Rough effort |
|---|---|---|---|
| **P0** | Foundation, no GPU | `plan` + `doctor` work against a fake backend; `plan.json` is byte-stable | 4–5 d |
| **P1** | ComfyUI + first asset | One real 32×32 seamless tile, gated and published | 6–8 d |
| **P2** | Sprite / UI / refs | Walk sheet with stable ground contact, 9-slice UI, valid normal map | 8–10 d |
| **P3** | Run hygiene | Kill mid-run → resume with zero duplicate generations; second run all cache hits | 4–5 d |
| **P4** | Audio | 8 tracks from one leitmotif, beat-aligned, seam-gated | 8–10 d |
| **P5** | Engine + CI | CI runs the fake pipeline end-to-end on a GPU-less runner | 4–5 d |

Total ≈ 34–43 dev-days. P0–P1 alone (≈ 10–13 d) is a usable tool for terrain and UI.

---

## 3. Task graph

Sizes: **S** ≤ 1 d · **M** 1–2 d · **L** 3–5 d. `←` lists blockers.

### P0 · Foundation

| # | Ticket | Size | ← | Acceptance |
|---|---|---|---|---|
| T01 | Package skeleton: `pyproject.toml`, `src/sdga`, entry point, exit-code contract, `--help` text | S | — | `pip install -e .` then `sdga` prints usage; unknown flag exits 2 |
| T02 | Domain types + canonical JSON + `sha256` helpers + `StyleContract` hashing | M | T01 | Two `StyleContract`s differing only in `pack.*` hash equal; differing in an anchor hash differ |
| T03 | `sdga.toml` loader + `assets/*.yaml` loader + strict validation with file/line in errors | M | T02 | Typo'd key (`refernces`) fails with the file, line, and a suggestion |
| T04 | `GenerationBackend` Protocol, `BackendProfile`, job state machine, `FakeBackend` (deterministic fixture output) | M | T02 | Same request through `FakeBackend` twice → identical artifact hash |
| T05 | `plan` stage: prompt assembly, size resolution, seed derivation, reference hashing, `plan.json` | M | T03, T04 | Running `plan` twice produces byte-identical `plan.json`; adding one asset leaves others' seeds unchanged |
| T06 | Test harness: fixture images/audio, golden-file helper, pytest markers (`slow`, `gpu`) | S | T01 | `pytest -m "not slow"` passes with no network and no GPU |
| T07 | `doctor` for `FakeBackend` + report table + `profile_hash` | S | T04 | Missing requirement appears in the table with recipe + remedy |

**P0 gate:** `sdga plan --dry-run` on `examples/` writes a `plan.json` a human can review, and
CI asserts it is stable across two runs.

### P1 · ComfyUI adapter and the first real asset

| # | Ticket | Size | ← | Acceptance |
|---|---|---|---|---|
| T08 | HTTP client: `/prompt` (caller-supplied `prompt_id`), `/history/{id}`, `/view`, `/upload/image` | M | T04 | Contract tests replay recorded HTTP bodies; 400 `node_errors` maps to `rejected_graph` with the body preserved |
| T09 | Progress: WS listener (binary-safe, reconnect, timeout) + polling fallback | M | T08 | Test feeds a binary preview frame then `executing{node:null}`; no exception, terminal detected twice |
| T10 | Recipe loader + `${slot}` binder + typed resolution + link validation | M | T02 | Missing slot → `SlotResolutionError` at plan time; orphaned link → validation error; numbers stay numbers |
| T11 | Capability probe: `/object_info` + `/system_stats`; node presence, model combo membership, input drift, VRAM | M | T08 | Removing a model file from the recorded profile makes `doctor` name the file and the folder it belongs in |
| T12 | `terrain_tile` recipe (graph JSON exported, markers added) + params plumbing | M | T10, T11 | Graph binds for three different `params` sets; `output_node` validated |
| T13 | Postprocess ops: `downscale_box`, `downscale_nearest`, `palette_snap`, `alpha_hard`, `pad_to_grid` | M | T06 | Golden files match; `palette_snap` is idempotent (property test); unique colours ≤ palette size |
| T14 | Gates: `dimensions_exact`, `grid_divisible`, `palette_conformance`, `max_unique_colors`, `alpha_required`, `binary_alpha`, `seamless_tile` | M | T13 | A 33×32 fixture fails dimensions; a deliberately non-tiling fixture fails `seamless_tile`; a palette-exact fixture passes all |
| T15 | Pack writer: layout, `pack.json`, `MANIFEST.sha256`, `LICENSES.md`, immutable ids | S | T14 | Publishing twice yields two ids with byte-identical `assets` (modulo `created`/`pack_id`) |
| T16 | Wire `run` end-to-end against a live local ComfyUI | M | T08–T15 | One moss tile generated, gated, published; `run.json` replays the exact graph |

**P1 gate:** `sdga run --asset terrain/moss_stone` on a real backend produces a 32×32 tile that
passes every gate, and `sdga validate packs/<id>` re-confirms it with the backend stopped.

### P2 · Sprite sheets, UI, references, normals

| # | Ticket | Size | ← | Acceptance |
|---|---|---|---|---|
| T17 | Reference resolution: content hash, cross-asset dedupe, role→backend handle, upload once | M | T08 | Two assets sharing a style anchor upload it once; handle is not part of `request_hash` |
| T18 | `sprite_sheet` recipe + `frame_grid` + `alpha_trim` + `center_anchor(feet)` + `frames_aligned` | L | T13, T17 | 8-frame walk: all frames' bottom rows within ±1 px; empty frame is an error, not a skip |
| T19 | Pose references: authored dw-pose sheet path (default) + optional per-frame img2img variant | M | T18 | Both paths produce a bound graph from the same spec by changing only the recipe |
| T20 | `ui_element` recipe + `ninepatch_mirror` + margins + `symmetry_9patch` gate | M | T13 | Output is bitwise symmetric; declared margins satisfy `2*max(margin) < edge`; margins reach `pack.json` |
| T21 | `concept` recipe + reference-cleaning ops (bg removal optional, palette snap, palette *extract* as an authoring command) | M | T13 | `sdga palette extract` writes a `.gpl` or `.png`; it is a one-time authoring tool, never in the asset chain |
| T22 | `normal_map` kind: `depth_to_normal` + `normal_map_valid` + `normal_sphere` fixture + `flip_g` | M | T13 | Sphere fixture validates; depth-passthrough fixture **fails** the gate (regression guard) |
| T23 | `candidates: N` + promote/reject + `review` CLI + `review.html` contact sheet | M | T15 | 4 candidates → exactly one promoted; contact sheet renders ref and result side by side |
| T24 | `ui_element` icons (`icon` kind), `alpha_trim`/`center` variant | S | T20 | 16×16 icon with binary alpha and exact palette |

**P2 gate:** a character walk sheet, a UI button, and a normal map for the tile — all in one pack,
all gated, all with provenance.

### P3 · Run hygiene

| # | Ticket | Size | ← | Acceptance |
|---|---|---|---|---|
| T25 | Cache index + `resolve` stage + `--force` / `--no-cache` | M | T15 | Second identical run: 0 backend calls, artifacts hard-linked; corrupt a cached file → cache miss |
| T26 | Resume: `prompt_id = uuid5(request_hash)`, `/history` check for in-flight jobs, `--resume` | M | T08, T25 | `SIGKILL` mid-run then `--resume` completes with no duplicate generations |
| T27 | Retries + OOM detection + single retry at concurrency 1 + printed remedy | S | T08 | Recorded `execution_error` "CUDA out of memory" triggers exactly one retry, then `failed` |
| T28 | Concurrency limiter + `/queue` introspection + `sdga status` | S | T08 | `max_concurrency=2` never has >2 in flight; `status` shows running/pending |
| T29 | Standalone `validate` over pack or run, `--json` output | S | T14 | Exits 1 on a gate failure; JSON is stable and diffable |

**P3 gate:** kill-and-resume test is automated; second full run is all cache hits; a corrupted
cache entry is detected and regenerated.

### P4 · Audio

| # | Ticket | Size | ← | Acceptance |
|---|---|---|---|---|
| T30 | `AudioBackend` Protocol + `FluidSynthBackend` (deterministic MIDI→WAV) + soundfont config | M | T04 | Same MIDI twice → identical WAV bytes; missing soundfont is `missing_capability` |
| T31 | Leitmotif model: MIDI load, key detection, degree-preserving transform, per-track plan | L | T30 | Transposition preserves interval contort; source key detected from MIDI, not assumed C |
| T32 | Audio ops: `loop_crossfade` (tail→head, equal-power), `loudness_normalize`, `trim_silence`, `fade_edges` | M | T06 | Sine fixture loops with `|x[-1]-x[0]|` below the median-difference threshold; the source guide's swap-halves method **fails** this gate (regression guard) |
| T33 | Audio gates: `beat_alignment`, `audio_loop_seam`, `audio_peak`, `audio_clip` | S | T32 | Wrong bar count fails `beat_alignment`; a clipped file fails `audio_clip` |
| T34 | Track plan: solve `bars*beats*60/bpm` for length, add crossfade, generate bed-only, mix authored melody at fixed gain | M | T31, T33 | 8 tracks share the identically-timed melody; each bed prompt forbids a lead melody |
| T35 | SFX path: prompt + duration + post + gates (AI backend optional) | S | T32 | A 0.3 s UI click passes peak/clip/duration gates |

**P4 gate:** all eight biome tracks derived from one `leitmotif_core.mid`, all beat-aligned, all
seam-gated, published with loop points.

### P5 · Engine adapter and CI

| # | Ticket | Size | ← | Acceptance |
|---|---|---|---|---|
| T36 | `adapt --engine godot`: import hints, margins, SpriteFrames descriptor, audio bus map | M | T15, T23 | Adapter output is schema-validated data; no Godot binary invoked |
| T37 | `examples/` project: one tile, one sprite, one UI element, one track, all fake-backend generated | S | T36 | `sdga run` in `examples/` on a clean machine produces a valid pack |
| T38 | CI: ruff, mypy (strict on `model/`), unit + contract tests, fake end-to-end, pack determinism diff | M | T29, T37 | CI has no torch, no ComfyUI, no GPU, and still runs the whole pipeline |

---

## 4. Frontier: what to start on Monday

```
Day 1–2   T01, T02          (independent, parallelisable)
Day 3–4   T03 ‖ T04         (both depend on T02, not on each other)
Day 5     T05, T06          (T05 needs T03+T04; T06 can start earlier)
Day 6     T07               (needs T04)
────────────────────────── P0 gate ──────────────────────────
Day 7–9   T08 ‖ T10         (HTTP client and recipe binder are independent)
Day 10    T09, T11          (the two hard-to-test parts: reconnection, probe)
Day 11–13 T12 → T13 → T14 → T15 → T16
```

T03 and T04 in parallel; T08 and T10 in parallel. Everything else is close to serial because each
step is verified by the one before it.

---

## 5. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| ComfyUI custom nodes churn (renames, API changes) | High | Medium | Probe + `requires` + recipes as data; a rename is a one-line data edit caught at `doctor` |
| LoRA never holds style (D1/D2 in the gap analysis) | Medium | High | P1 uses a stock pixel LoRA to prove the pipeline; the custom LoRA is a separate, evaluated track with epoch checkpoints at 5/10 |
| OpenPose/pixel-art detection fails (B7) | High | High | Authored pose sheets as the default path; cutout animation as the documented fallback |
| Determinism claims overstated (hardware drift) | Medium | Medium | `profile_hash` in the cache key; "reproducible on this profile" language everywhere |
| Audio swallows the schedule | Medium | High | Audio is P4, behind a working visual pack. It shares the skeleton, so it cannot block P0–P3 |
| Review becomes the bottleneck | Medium | Medium | Contact sheet per run; `require_review` configurable; candidates reduce re-rolls |
| Licensing blocks distribution (E1) | Medium | Blocking | Decide dataset provenance **before** training; `LICENSES.md` in every pack; no scraper in the repo |
| Scope creep into a general-purpose asset DCC | Medium | High | The README states the non-goals; "is it a pack output?" is the gate for every feature |

---

## 6. Definition of done (whole project)

1. A fresh clone runs `pip install -e .` and `sdga doctor` reports a clear, actionable table.
2. `sdga run` on the example project produces a pack that a Godot project can consume without
   manual renaming.
3. Every published file has provenance resolvable to a `run.json` job.
4. `sdga validate` re-verifies a pack with the backend stopped.
5. Killing a run and resuming it produces the same pack as an uninterrupted run.
6. CI proves 1–5 with no GPU and no ComfyUI installed.
7. The gap analysis's S1 findings each have a regression test that would fail if the fix were
   reverted (empty frame, depth-as-normal, swap-halves loop, binary WS frame, wrong output node).

---

## 7. Working method

- **TDD at the seam.** Tests cross `GenerationBackend` and pure functions; nothing tests internals.
  `FakeBackend` is written before `ComfyUIBackend` and never deleted.
- **Records over mocks.** Prefer recorded `/object_info`, `/history`, and HTTP bodies as fixtures
  over hand-written mocks that drift from reality.
- **One asset kind per pull request.** Breadth comes from data once the kind-specific ops and gates
  exist.
- **A gate or it didn't happen.** Any new postprocess op ships with the gate that detects its
  absence.
- **No absolute paths, ever.** A PR containing `D:\` or `C:\` fails review.
