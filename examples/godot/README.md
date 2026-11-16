# Godot consumer sample

This is an **optional consumer**, not part of the generator or its CI gate. The pipeline never
imports Godot; `sdga adapt` emits deterministic JSON, and this sample turns that JSON into
engine objects at runtime.

It demonstrates:

- a named `walk` clip becoming a real `SpriteFrames` animation with per-clip speed and loop;
- four ninepatch edges applied to a `NinePatchRect`, including asymmetric values;
- the `Music`/`SFX` bus map and loop points from `audio_buses.json`;
- pixel-art import hints (`filter=false`, `mipmaps=false`, lossless compression).

## Run the self-check

From the repository root, generate a bundle and point Godot at it:

```bash
sdga run --project examples
sdga publish --project examples --allow-unreviewed
sdga adapt --project examples --pack examples/packs/<pack_id> \
  --out /tmp/godot-bundle

godot --headless --path examples/godot --script res://import_bundle.gd -- \
  /tmp/godot-bundle
```

Expected output:

```
godot adapter sample: ok (walk 8 frames @ 10 fps, margins 31/7/31/7, buses Music,SFX)
```

The self-check uses a generated placeholder texture because it verifies the data contract. In a
real project, pass the sheet texture to `SdgaBundle.make_sprite_frames`; for an atlas, add one
`AtlasTexture` region per frame instead of reusing one texture.

## Paths

Bundle paths are relative to the **pack**, not the adapter directory. Copy the pack's `assets/`
into the Godot project or resolve each path against the pack root. The adapter intentionally
does not duplicate images, so the pack remains the single source of truth.

`ninepatch.json` reports `mirror`, and margins may differ per edge when the spec opted out of
mirroring. `SpriteFrames` has no ping-pong flag: the adapter expands ping-pong clips into frames
before writing them, so the consumer just plays the list.
