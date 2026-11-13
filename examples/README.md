# Example project

A minimal project: four asset specs, one palette, and the reference images they bind.
It is what `tests/test_examples.py` uses to prove that `plan` stays byte-stable, and what
CI runs the documented `sdga plan --dry-run examples/` check against.

```
examples/
├── sdga.toml                  # project + style + backend + gates
├── assets/world.yaml          # terrain tile and its normal map
├── assets/char_ui.yaml        # sprite sheet and UI button
├── palettes/example16.png     # 16-colour placeholder, 8x2 swatch grid (replace it)
├── concepts/cleaned/          # style anchors
├── style/skeletons/           # pose reference (authored, not detector output)
├── style/wireframes/          # UI wireframe
└── plan.json                  # generated, committed on purpose: CI diffs it
```

Run it with no GPU and no ComfyUI:

```bash
sdga doctor --project examples
sdga plan   --project examples --dry-run
```

Regenerate `plan.json` after changing a spec, and commit it:

```bash
sdga plan --project examples
```

The palette is a `.png` swatch grid rather than a `.gpl`, so the example project covers the
image loader path (`read_palette`) as well as the text one; each opaque pixel is one colour,
in scan order. The backend is `fake`, so anything past `plan` waits for phase P1. The reference images are
procedural placeholders: they exist so path and hashing logic is exercised, not because they
are good art.
