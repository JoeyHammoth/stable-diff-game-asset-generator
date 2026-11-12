# Testing and Operations

---

## 1. What is worth testing

The system has one external seam (`GenerationBackend`) and a large body of pure functions. That
shape dictates the strategy:

| Layer | How it is tested | Speed |
|---|---|---|
| Domain types, hashing | pure unit tests | ms |
| Planning (prompts, seeds, sizes) | unit + golden `plan.json` | ms |
| Postprocess ops | golden-file + property tests | ms |
| Gates | table-driven, one failing fixture per gate | ms |
| Recipe binder | unit tests over graph JSON | ms |
| Backend contract | **recorded** HTTP/WS fixtures, replayed | ms |
| ComfyUI adapter (live) | one smoke test, `@pytest.mark.gpu`, opt-in | minutes |
| End-to-end | `FakeBackend` → pack, determinism diff | seconds |

**Never tested:** whether the model produced *good art*. That is the review stage, and it is
human. Testing aesthetics automates the wrong thing.

---

## 2. Fixtures

Committed, tiny, and hand-made so a failure is unambiguous:

```
tests/fixtures/
├── images/
│   ├── tile_seamless_32.png        # passes seamless_tile (value ≈ 1.0)
│   ├── tile_non_seamless_32.png    # fails at ratio ≫ 1.5
│   ├── palette_exact_32.png        # only Endesga-32 colours
│   ├── palette_drift_32.png        # 3 off-palette colours → conformance fail
│   ├── walk_8f_32.png              # aligned feet, passes frames_aligned
│   ├── walk_8f_bob_32.png          # feet drift 3 px → fails
│   ├── walk_8f_empty_frame.png     # one transparent cell → error, not skip
│   ├── button_asym_64x16.png       # fails symmetry_9patch
│   ├── sphere_depth.png            # valid height field for depth_to_normal
│   └── depth_as_normal.png         # the source-guide bug → fails normal_map_valid
├── audio/
│   ├── loop_good_32s.wav           # tail/head already compatible
│   ├── loop_discontinuous.wav      # produces the source-guide swap-halves failure
│   └── clip_-0.1db.wav             # fails audio_clip
└── backend/
    ├── object_info.json            # recorded from ComfyUI 0.23.0
    ├── system_stats.json
    ├── history_success.json
    ├── history_multisave.json      # two SaveImage nodes → proves output_node selection
    └── prompt_400_node_errors.json
```

Three fixtures exist specifically to pin the gap-analysis findings: `walk_8f_bob`,
`depth_as_normal`, and `loop_discontinuous`. If someone "simplifies" the code back to the source
guide's approach, these fail.

---

## 3. The property tests that matter

Fast, high-value, and hard to fake:

1. **`palette_snap` is idempotent.** `snap(snap(x)) == snap(x)` for random images.
2. **`palette_snap` never invents a colour.** `set(unique(snap(x))) ⊆ palette`.
3. **`plan` is byte-stable.** Two runs, identical input ⇒ identical `plan.json`.
4. **Seeds are independent.** Adding an unrelated asset does not change any existing seed.
5. **Style-hash scope.** Changing `[backend].max_concurrency` keeps the hash; changing one anchor
   changes it.
6. **Recipe binder is type-preserving.** A numeric slot yields a JSON number, not `"512"`.
7. **Pack is byte-identical on republish** (excluding `created`, `pack_id`).
8. **`frame_grid` round-trips.** Split then reassemble with no pixel change.
9. **`loop_crossfade` output length** equals `L - fade`, and the wrap delta is under the gate
   threshold for a compatible input.
10. **Gate determinism.** Same file + spec ⇒ same result, twice, no ordering dependence.

---

## 4. Contract tests for the ComfyUI adapter

Do not mock the client. Replay recorded traffic through a local HTTP server so the client's real
serialisation, URL building, and error mapping are exercised.

```python
def test_prompt_400_is_rejected_graph(replay_server):
    replay_server.queue("/prompt", status=400,
                        body=load("prompt_400_node_errors.json"))
    err = backend.submit(request)          # raises BackendError
    assert err.kind == "rejected_graph"
    assert "KSampler" in err.detail["node_errors"]
    assert not err.retryable
```

Six contract tests cover the whole external surface:

| Test | Pins |
|---|---|
| `submit` sends supplied `prompt_id` | idempotency / resume depends on it |
| 400 → `rejected_graph`, not retried | no infinite retry on a graph bug |
| binary WS frame then completion | the source guide's `json.loads` bug |
| `execution_error` → terminal `failed` | no hang |
| `history_multisave` picks declared node | not `images[0]` |
| socket disconnect → falls back to polling | WS is an optimisation |

`object_info.json` doubles as the capability-probe fixture. A test deletes a node from it and
asserts `doctor` names the missing node **and** the recipe that needs it.

---

## 5. CI

```
python -m pip install -e ".[dev]"
ruff check .                       # lint, src and tests
ruff format --check .              # formatting is checked, not just linted
mypy                               # src/sdga; sdga.model is strict (see pyproject)
pytest -m "not slow and not gpu"   # no network, no GPU, no torch
sdga plan    --project examples && git diff --exit-code examples/plan.json
sdga run     --project examples --asset terrain/moss_stone
sdga publish --project examples --allow-unreviewed
sdga validate --project examples "$(ls -d examples/packs/* | head -1)"
```

`.github/workflows/ci.yml` runs exactly this list. The example project selects the fake
backend through `[backend] kind = "fake"` in its `sdga.toml`; there is deliberately no
`--backend` flag, because the backend is a project property rather than a per-command one.

Two properties make CI meaningful:

- **The environment has no ComfyUI and no torch.** Any accidental import of `comfy` fails here,
  which is how rule 1 in the architecture is enforced rather than merely stated.
- **The determinism step is a real diff**, not a hash print. If `plan.json` or a packed artifact
  changes, the build fails and shows what changed.

Nightly (optional, self-hosted GPU runner): one real generation per asset kind, then
`sdga validate`. This is the only place model/node drift is observed before a human hits it.

---

## 6. Operating the thing

### 6.1 Runbook

| Symptom | Diagnosis | Action |
|---|---|---|
| `doctor` says unreachable | ComfyUI not started, or bound to `127.0.0.1` on another host | Start it, or use `--listen` and the LAN URL |
| `missing_capability: <node>` | Custom node pack absent or renamed | Install the pack, or update the recipe's `requires` |
| `missing_capability: <model>` | File absent from the loader's folder | `doctor` prints which folder (checkpoints vs loras) |
| `rejected_graph` | Our bug, usually a renamed input | The 400 body is in `run.json`; fix the recipe |
| Repeated `execution_error` on one asset | Prompt/model interaction, or VRAM | Try fewer candidates / lower size; check VRAM in profile |
| Gate `palette_conformance` fails | `palette_snap` skipped, or a non-sRGB source | Check the chain order in the spec |
| Gate `seamless_tile` fails | Generated without circular padding and no tile op | Add `tile_offset_blend` or fix the recipe |
| Asset "missing" from a pack | Unapproved, rejected, or failed job | `sdga status` and the gate reasons in `run.json` |
| Second run regenerates everything | Style contract changed (expected) or cache deleted | Compare `contract_hash` in the two runs |

### 6.2 Disk growth

`runs/` grows by the full raw output of every generation and is never pruned automatically.
Retention is a deliberate command:

```
sdga gc --keep-runs 20 --keep-packs all --dry-run
```

Raw artifacts of *published* assets are kept forever (they are the audit trail); raw artifacts of
rejected and superseded candidates are the first to go. Cache is always safe to delete.

### 6.3 Upgrading models or ComfyUI

Changing a checkpoint, LoRA, node pack, or ComfyUI version changes `profile_hash`, which
invalidates the cache by design. The safe sequence:

1. `sdga doctor` → record the new profile.
2. `sdga run --asset <one representative asset of each kind> --no-cache` into a scratch pack.
3. Diff the gates: a *passing* asset whose gate values move materially is a style drift signal
   even if it still passes.
4. Run `sdga validate` on the previous pack to confirm the old one still verifies.
5. Only then run the full pack with the new profile. Never regenerate a shipped pack in place —
   publish a new `pack_id`.

### 6.4 Secrets and network

There are none. The backend URL is the only network endpoint; it is configurable and defaults to
loopback. No telemetry, no model downloads at runtime (models are ComfyUI's responsibility). A
pack contains art, hashes, and prompts — treat prompts as public when choosing what to generate.

---

## 7. Observability

- **`run.json` is the log.** Structured, complete, and replayable. Console output is a summary of
  it, never the source of truth.
- **Progress** is one line per job: `[3/40] terrain/moss_stone … running (12s, step 14/25)`.
- **A failed gate prints the measurement**, not just the name: `seamless_tile 4.31 > 1.5`.
- **Exit codes are contract** (see [03-contracts-and-schemas.md §8](03-contracts-and-schemas.md)):
  scripts distinguish "art rejected" (1) from "backend down" (3).
