"""Build the game's sprite set from Kenney's "Tiny Dungeon" pack plus original pixel art.

Usage (from the repository root, with the pack extracted somewhere outside the repo):

    python tools/build_sprites.py PATH/TO/kenney_tiny-dungeon

It copies only the tiles the game uses into ``src/battle_dice/ui/assets/sprites`` under
semantic names, writes one recoloured tile (the goblin), and draws the handful of original
16x16 sprites that the pack does not provide (d4 / d6 / d8 dice, Weaken and Speed Up icons).
The outputs are committed, so players and CI never need the pack itself.

Tiny Dungeon (1.0) is by Kenney (www.kenney.nl), licence Creative Commons Zero (CC0).
"""

from __future__ import annotations

import colorsys
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "src" / "battle_dice" / "ui" / "assets" / "sprites"

#: sprite file name -> Tiny Dungeon tile number
COPIED = {
    "hero_squire": 96,
    "hero_apprentice": 84,
    "hero_scout": 112,
    "enemy_hex_adept": 111,
    "enemy_captain": 87,
    "icon_attack": 104,
    "icon_defense": 102,
    "icon_healing": 115,
    "icon_status": 114,
    "icon_resource": 116,
    "status_poison": 114,
    "marker_downed": 65,
    "chest": 89,
    "tile_floor_a": 48,
    "tile_floor_b": 49,
    "tile_floor_c": 42,
    "tile_wall": 40,
}

#: Goblin Skirmisher: Tiny Dungeon has no goblin, so the tan brute (tile 109) is recoloured green.
GOBLIN_SOURCE_TILE = 109

OUTLINE = (63, 38, 49)
IVORY = (240, 232, 205)
IVORY_SHADE = (196, 182, 150)
PIP = (63, 38, 49)
ORANGE = (240, 150, 70)
ORANGE_DARK = (170, 90, 40)
YELLOW = (250, 215, 90)
YELLOW_DARK = (190, 140, 40)


def load_tile(pack: Path, number: int) -> pygame.Surface:
    return pygame.image.load(str(pack / "Tiles" / f"tile_{number:04d}.png")).convert_alpha()


def recolour_to_green(tile: pygame.Surface) -> pygame.Surface:
    """Shift warm skin tones (hue 15-50 degrees) to green; leave outline, eyes and metal alone."""
    result = tile.copy()
    for x in range(result.get_width()):
        for y in range(result.get_height()):
            r, g, b, a = result.get_at((x, y))
            if a == 0:
                continue
            hue, sat, val = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if 15 / 360 <= hue <= 50 / 360 and sat > 0.25:
                nr, ng, nb = colorsys.hsv_to_rgb(110 / 360, min(1.0, sat * 1.05), val * 0.92)
                result.set_at((x, y), (round(nr * 255), round(ng * 255), round(nb * 255), a))
    return result


def blank() -> pygame.Surface:
    return pygame.Surface((16, 16), pygame.SRCALPHA)


def polygon(surface: pygame.Surface, fill: tuple, points: list[tuple[int, int]], outline: tuple = OUTLINE) -> None:
    pygame.draw.polygon(surface, fill, points)
    pygame.draw.polygon(surface, outline, points, 1)


def die_d4() -> pygame.Surface:
    s = blank()
    polygon(s, IVORY, [(8, 1), (14, 13), (1, 13)])
    pygame.draw.line(s, IVORY_SHADE, (8, 3), (8, 12))  # centre edge of the tetrahedron
    pygame.draw.polygon(s, IVORY_SHADE, [(9, 4), (13, 12), (9, 12)])
    pygame.draw.polygon(s, OUTLINE, [(8, 1), (14, 13), (1, 13)], 1)
    s.set_at((5, 10), PIP)
    return s


def die_d6() -> pygame.Surface:
    s = blank()
    pygame.draw.rect(s, IVORY, (2, 2, 12, 12))
    pygame.draw.rect(s, IVORY_SHADE, (2, 12, 12, 2))
    pygame.draw.rect(s, OUTLINE, (2, 2, 12, 12), 1)
    for corner in ((2, 2), (13, 2), (2, 13), (13, 13)):
        s.set_at(corner, (0, 0, 0, 0))  # rounded corners
    for x, y in ((5, 5), (10, 5), (5, 10), (10, 10), (7, 7), (8, 8)):
        s.set_at((x, y), PIP)
    s.set_at((8, 7), PIP)
    s.set_at((7, 8), PIP)
    return s


def die_d8() -> pygame.Surface:
    s = blank()
    points = [(8, 1), (14, 8), (8, 15), (2, 8)]
    pygame.draw.polygon(s, IVORY, points)
    pygame.draw.polygon(s, IVORY_SHADE, [(3, 9), (13, 9), (8, 14)])  # lower facet in shade
    pygame.draw.polygon(s, OUTLINE, points, 1)
    pygame.draw.line(s, OUTLINE, (3, 8), (13, 8))  # equator of the octahedron
    s.set_at((8, 5), PIP)
    return s


def status_weaken() -> pygame.Surface:
    """A downward arrow: outgoing attack damage is reduced."""
    s = blank()
    points = [(6, 2), (10, 2), (10, 8), (13, 8), (8, 14), (3, 8), (6, 8)]
    polygon(s, ORANGE, points)
    pygame.draw.line(s, ORANGE_DARK, (9, 3), (9, 8))
    pygame.draw.polygon(s, OUTLINE, points, 1)
    return s


def status_speed_up() -> pygame.Surface:
    """A double upward chevron: the action gauge fills faster."""
    s = blank()
    for offset in (0, 6):
        points = [(8, 1 + offset), (14, 7 + offset), (11, 7 + offset), (8, 4 + offset), (5, 7 + offset), (2, 7 + offset)]
        polygon(s, YELLOW, points)
        pygame.draw.line(s, YELLOW_DARK, (9, 4 + offset), (11, 6 + offset))
        pygame.draw.polygon(s, OUTLINE, points, 1)
    return s


ORIGINAL = {
    "die_d4": die_d4,
    "die_d6": die_d6,
    "die_d8": die_d8,
    "status_weaken": status_weaken,
    "status_speed_up": status_speed_up,
}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    pack = Path(argv[1])
    if not (pack / "Tiles").is_dir():
        print(f"'{pack}' does not look like the extracted Tiny Dungeon pack (no Tiles folder).")
        return 2
    pygame.display.init()
    pygame.display.set_mode((16, 16))
    OUT.mkdir(parents=True, exist_ok=True)
    for name, number in sorted(COPIED.items()):
        tile = load_tile(pack, number)
        assert tile.get_size() == (16, 16), (name, tile.get_size())
        pygame.image.save(tile, str(OUT / f"{name}.png"))
    pygame.image.save(recolour_to_green(load_tile(pack, GOBLIN_SOURCE_TILE)), str(OUT / "enemy_goblin.png"))
    for name, draw in sorted(ORIGINAL.items()):
        pygame.image.save(draw(), str(OUT / f"{name}.png"))
    print(f"wrote {len(COPIED) + 1 + len(ORIGINAL)} sprites to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
