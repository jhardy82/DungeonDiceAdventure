# The save-database script moved into the game package

`progression.sql` (the approved 24-table schema, FDD v0.2) is now package data, because the game
creates save files from it:

- `src/battle_dice/career/schema/progression.sql`

The code that reads and writes a save is `src/battle_dice/career/store.py`. The reference checks
still run from here:

```
python tools/class_evolution/check_persistence.py
```

`example_profile.json` and `error_codes.json` stay in this folder: they are specification, not
something the game loads.
