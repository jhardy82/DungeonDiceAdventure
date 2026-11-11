# The vocation catalog moved into the game package

The catalog and its schema are now package data, because the game loads them when the feature gate
`class_evolution_v1` is on:

- `src/battle_dice/content/class_evolution/vocation_catalog.json`
- `src/battle_dice/content/class_evolution/vocation_catalog.schema.json`

The validator and the code that turns a vocation into a hero build are in
`src/battle_dice/content/vocations.py`. Run the validator with:

```
python tools/class_evolution/validate_catalog.py
```

The design is in `../FDD_v0.2.md`.
