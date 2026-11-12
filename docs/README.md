# Documentation

Design documentation for a modular, backend-agnostic game asset generation pipeline.
The implementation lives in `src/sdga/` (see [06-implementation-plan.md](06-implementation-plan.md)).

## Read in this order

| Doc | What it answers | Status |
|---|---|---|
| [01-architecture.md](01-architecture.md) | What are the modules and seams? Why is this separate from ComfyUI and Godot? | proposed |
| [02-domain-model.md](02-domain-model.md) | What do the words mean? What are the core types and invariants? | proposed |
| [03-contracts-and-schemas.md](03-contracts-and-schemas.md) | What exactly is in `sdga.toml`, an asset spec, a recipe, a request, a run record, a pack? | proposed |
| [04-pipeline-stages.md](04-pipeline-stages.md) | What happens in each of the eight stages, with exact algorithms and gate thresholds? | proposed |
| [05-gap-analysis.md](05-gap-analysis.md) | What in the existing guide is wrong, fragile, or missing — and why | research |
| [06-implementation-plan.md](06-implementation-plan.md) | In what order do we build it, and how do we know each step is done? | proposed |
| [07-testing-and-operations.md](07-testing-and-operations.md) | How is it verified and operated? | proposed |
| [stable-diffusion-pixel-art-pipeline.md](stable-diffusion-pixel-art-pipeline.md) | The original end-to-end guide: models, nodes, prompt craft, music layers, Godot setup | reference |

## The one-paragraph summary

A Python package (`sdga`) turns declarative asset specs into an **engine-neutral asset pack** by
driving a *remote* ComfyUI over its HTTP/WebSocket API. It never imports ComfyUI, never requires
Godot, and never hardcodes a path. Everything after the sampler — palette snapping, grid
downscaling, sprite anchoring, 9-slice mirroring, depth→normal conversion, loop crossfading,
validation, packaging — is deterministic, in-repo, and asserted by named gates. Style consistency
is therefore a build failure rather than an aesthetic judgement, and the whole pipeline except the
GPU step runs in CI.

## Conventions used in these docs

- **Must** = enforced in code or CI. **Should** = review-level. **May** = optional.
- Code fences marked `json`/`yaml`/`toml` are schema examples, not illustrative fragments; field
  names match the intended implementation.
- Cross-references use relative links; section anchors are stable.
- Where a claim depends on this machine's ComfyUI install, it says so and names the version
  (0.23.0) and what was checked.
