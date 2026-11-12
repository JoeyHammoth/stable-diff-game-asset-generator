# Palettes

Shared, licensed palettes (`.gpl`). A project usually keeps its own palette beside its
`sdga.toml`; this directory is for palettes several projects share.

Two rules, both enforced by gates rather than goodwill:

1. **One palette per pack.** Every published asset must use a colour from the pack's
   palette file (reference `[style] palette`). Per-image palettes are what makes AI
   pixel art drift.
2. **Record the licence.** Each palette file gets a sibling note naming its source and
   terms, because palettes are creative works too.

Empty in phase P0. The example project ships a clearly-labelled placeholder in
`examples/palettes/`.
