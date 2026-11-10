# Art credits

Every image the game ships is listed in `manifest.json` with its source.

## Third-party art

| Pack | Author | Licence | Source |
|------|--------|---------|--------|
| Tiny Dungeon (1.0) | Kenney (www.kenney.nl) | Creative Commons Zero (CC0 1.0) | https://kenney.nl/assets/tiny-dungeon |

CC0 means the pack may be used for any purpose without permission or attribution. This credit
is given anyway. Only the tiles the game uses are included (18 files); the pack's own
`License.txt` states: "License: (Creative Commons Zero, CC0)
http://creativecommons.org/publicdomain/zero/1.0/".

Files taken from Tiny Dungeon, renamed: `hero_squire`, `hero_apprentice`, `hero_scout`,
`enemy_hex_adept`, `enemy_captain`, `icon_attack`, `icon_defense`, `icon_healing`,
`icon_status`, `icon_resource`, `status_poison`, `marker_downed`, `chest`, `tile_floor_a`,
`tile_floor_b`, `tile_floor_c`, `tile_wall`.

Modified from Tiny Dungeon: `enemy_goblin` is tile 109 with its skin tones recoloured green
(the pack has no goblin).

## Original art

Drawn for this project by `tools/build_sprites.py`, in the same 16x16 format: `die_d4`,
`die_d6`, `die_d8`, `status_weaken`, `status_speed_up`.

## Rebuilding

`python tools/build_sprites.py PATH/TO/kenney_tiny-dungeon` regenerates every sprite from an
extracted copy of the pack.
