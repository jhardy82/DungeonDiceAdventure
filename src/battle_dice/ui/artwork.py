"""Sprite loading and crisp pixel-art scaling for the presentation layer.

Sprites are 16x16 pixel art. They are only ever scaled by whole numbers with nearest-neighbour
sampling, so pixels stay square and sharp at every window size, while panels and text keep the
UI's fractional scaling. Files are read through ``importlib.resources``, exactly like the JSON
content, so they work from source and inside a packaged build.
"""

from __future__ import annotations

import io
import json
from importlib import resources
from typing import Any

import pygame

PLACEHOLDER_COLOUR = (200, 60, 200)


class AssetStore:
    def __init__(self) -> None:
        root = resources.files("battle_dice.ui").joinpath("assets")
        self._root = root
        self.manifest: dict[str, Any] = json.loads(root.joinpath("manifest.json").read_text(encoding="utf-8"))
        self.tile_size: int = int(self.manifest["tile_size"])
        self._base: dict[str, pygame.Surface] = {}
        self._scaled: dict[tuple[str, int, str], pygame.Surface] = {}
        self.missing: set[str] = set()

    # -- lookup ------------------------------------------------------------------------------

    def keys(self) -> list[str]:
        return sorted(self.manifest["sprites"])

    def combatant_key(self, archetype_id: str) -> str | None:
        return self.manifest["combatants"].get(archetype_id)

    def category_key(self, category: str) -> str | None:
        return self.manifest["categories"].get(category)

    def status_key(self, kind: str) -> str | None:
        return self.manifest["statuses"].get(kind)

    def die_key(self, size: int) -> str | None:
        return self.manifest["dice"].get(str(size))

    # -- loading -----------------------------------------------------------------------------

    def base(self, key: str) -> pygame.Surface | None:
        """The unscaled sprite, or ``None`` when the key or file is missing (never raises)."""
        if key in self._base:
            return self._base[key]
        if key in self.missing:
            return None
        entry = self.manifest["sprites"].get(key)
        try:
            if entry is None:
                raise KeyError(key)
            data = self._root.joinpath("sprites", entry["file"]).read_bytes()
            surface = pygame.image.load(io.BytesIO(data), entry["file"])
            surface = surface.convert_alpha() if pygame.display.get_surface() is not None else surface
        except (KeyError, OSError, pygame.error):
            self.missing.add(key)
            return None
        self._base[key] = surface
        return surface

    def load_all(self) -> int:
        """Load every sprite in the manifest. Returns how many loaded successfully."""
        return sum(1 for key in self.keys() if self.base(key) is not None)

    def scaled(self, key: str, scale: int, variant: str = "") -> pygame.Surface | None:
        """The sprite enlarged by a whole number. ``variant`` may be ``"grey"`` for downed units."""
        scale = max(1, int(scale))
        cache_key = (key, scale, variant)
        if cache_key in self._scaled:
            return self._scaled[cache_key]
        base = self.base(key)
        if base is None:
            return None
        surface = base if scale == 1 else pygame.transform.scale_by(base, scale)
        if variant == "grey":
            surface = pygame.transform.grayscale(surface)
        self._scaled[cache_key] = surface
        return surface

    @staticmethod
    def fit_scale(base_size: tuple[int, int], slot_size: tuple[int, int]) -> int:
        """Largest whole-number scale at which the sprite fits the slot (at least 1)."""
        width, height = base_size
        return max(1, min(slot_size[0] // max(1, width), slot_size[1] // max(1, height)))
