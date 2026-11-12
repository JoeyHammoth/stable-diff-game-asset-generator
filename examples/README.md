# Example project

A minimal project: four asset specs, one palette, and the reference images they bind.
It is what `tests/test_examples.py` uses to prove that `plan` stays byte-stable, and what
CI runs the documented `sdga plan --dry-run examples/` check against.

```
examples/
├── sdga.toml                  # project + style + backend + gates
├── assets/world.yaml          # terrain tile and its normal map
├── assets/char_ui.yaml        # sprite sheet and UI button
├── palettes/example16.gpl     # placeholder palette (replace with a licensed one)
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

The backend is `fake`, so anything past `plan` waits for phase P1. The reference images are
procedural placeholders: they exist so path and hashing logic is exercised, not because they
are good art.
