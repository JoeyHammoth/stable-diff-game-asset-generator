# stable-diff-game-asset-generator

A modular, backend-agnostic asset pipeline that turns declarative asset specs into an
**engine-neutral asset pack** — pixel-art tiles, sprite sheets, UI frames, normal maps, SFX, and a
leitmotif-derived soundtrack — by driving a ComfyUI server over its HTTP/WebSocket API.

It is deliberately separate from both ends of the problem:

- **Not part of ComfyUI.** Nothing in this repo imports ComfyUI. It is a client of a remote
  ComfyUI (same machine, a GPU box on the LAN, or a recorded fixture server in CI).
- **Not part of Godot.** It emits a pack (`pack.json` + files + provenance). An engine importer —
  a separate concern — consumes it. No Godot binary is required to generate or validate art.

Everything after the sampler is deterministic and versioned here: palette locking, grid
downscaling, sprite anchoring, 9-slice symmetry, depth→normal conversion, loop crossfading,
validation gates, and packaging. That is what makes style consistency a build failure instead of
an opinion.

## Status

**Design complete; implementation not yet started.** Start at
[docs/README.md](docs/README.md).

| | |
|---|---|
| Architecture | [docs/01-architecture.md](docs/01-architecture.md) |
| Domain model | [docs/02-domain-model.md](docs/02-domain-model.md) |
| Formats & contracts | [docs/03-contracts-and-schemas.md](docs/03-contracts-and-schemas.md) |
| Pipeline stages & gates | [docs/04-pipeline-stages.md](docs/04-pipeline-stages.md) |
| Review of the source guide | [docs/05-gap-analysis.md](docs/05-gap-analysis.md) |
| Build order | [docs/06-implementation-plan.md](docs/06-implementation-plan.md) |
| Testing & operations | [docs/07-testing-and-operations.md](docs/07-testing-and-operations.md) |

The original end-to-end guide (model choices, ComfyUI setup, prompt craft, music layers, Godot
configuration) is retained as the domain reference:
[docs/stable-diffusion-pixel-art-pipeline.md](docs/stable-diffusion-pixel-art-pipeline.md).

## Non-goals

- Authoring or running game code.
- Bundling or downloading models, node packs, or a ComfyUI checkout.
- Judging whether art is *good* — that is the human review stage, recorded per asset.
- Being a general-purpose image tool. If a feature does not end up in `pack.json`, it is out of
  scope.

## License

See [LICENSE](LICENSE).
