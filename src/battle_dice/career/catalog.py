"""Read-only questions the career rules ask of the vocation catalog and the shipped content."""

from __future__ import annotations

from typing import Any

from battle_dice.content.loader import Content
from battle_dice.content.vocations import NOVICE, unlock_routes

Json = dict[str, Any]
STAT_KEYS = ("max_hp", "max_mana", "speed")
SHOWN_STATS = ("max_hp", "max_mana", "speed", "base_initiative", "max_corruption")
MASTERED_RANK = 8


class CareerCatalog:
    """The validated catalog plus the shipped content. Novice numbers always come from the shipped classes."""

    def __init__(self, catalog: Json, content: Content):
        self.raw = catalog
        self.content = content
        self.version: str = catalog["baseline"]["content_version"]
        self.vocations: dict[str, Json] = {v["id"]: v for v in catalog["vocations"]}
        self.skills: dict[str, Json] = {s["id"]: s for s in catalog["skills"]}
        self.routes: dict[str, dict[str, Json]] = unlock_routes(catalog)
        self.stat_caps: dict[str, int] = dict(catalog["stat_caps"])
        #: skill id -> (vocation that teaches it, rank at which it is learned)
        self.skill_origin: dict[str, tuple[str, int]] = {
            entry["skill_id"]: (v["id"], entry["rank"]) for v in catalog["vocations"] for entry in v["skills_learned"]
        }

    # -- vocations ---------------------------------------------------------------------------

    def group(self, vocation_id: str) -> str:
        return str(self.vocations[vocation_id]["group"])

    def _definition(self, vocation_id: str) -> Json:
        """Stats and dice of a vocation: the shipped class for a novice, the catalog entry otherwise."""
        vocation = self.vocations[vocation_id]
        return self.content.class_def(vocation["class_id"]) if vocation["group"] == NOVICE else vocation

    def base_stats(self, vocation_id: str) -> dict[str, int]:
        definition = self._definition(vocation_id)
        return {name: int(definition[name]) for name in SHOWN_STATS}

    def inheritance_capacity(self, vocation_id: str) -> int:
        return int(self.vocations[vocation_id]["inheritance_capacity"])

    def starting_dice(self, vocation_id: str) -> list[str]:
        return list(self._definition(vocation_id)["starting_dice"])

    def own_dice(self, vocation_id: str) -> list[str]:
        """The dice made for a vocation: its starting dice and its bench dice."""
        definition = self._definition(vocation_id)
        return [*definition["starting_dice"], *definition["bench_dice"]]

    def family(self, vocation_id: str) -> str | None:
        """The starting class an evolved vocation grew from; ``None`` for a starting class itself."""
        vocation = self.vocations[vocation_id]
        return None if vocation["group"] == NOVICE else str(vocation["upgrade_family"])

    def may_equip(self, vocation_id: str, die_id: str) -> bool:
        """Owner decision of 2026-11-11: a vocation may equip its own dice, plus its family's."""
        if die_id in self.own_dice(vocation_id):
            return True
        family = self.family(vocation_id)
        return family is not None and die_id in self.own_dice(family)

    def die_faces(self, die_id: str) -> list[tuple[str, tuple[str, ...]]]:
        """``(category, tags)`` of every face on a die, shipped or from the catalog."""
        if die_id in self.raw["dice"]:
            library = {**self.content.documents["dice"]["face_library"], **self.raw["face_library"]}
            return [(library[f]["category"], tuple(library[f]["tags"])) for f in self.raw["dice"][die_id]["faces"]]
        return [(face.category, tuple(face.tags)) for face in self.content.die(die_id).faces]

    def is_public(self, vocation_id: str) -> bool:
        vocation = self.vocations[vocation_id]
        return vocation["group"] == NOVICE or vocation["discovery"]["rule"] == "visible_from_start"

    def discovery_signals(self) -> list[tuple[str, str, str]]:
        """``(signal, vocation id, state it leads to)`` for every authored discovery signal."""
        found = []
        for vocation in self.raw["vocations"]:
            for entry in vocation.get("discovery", {}).get("signals", []):
                found.append((signal_name(entry), vocation["id"], entry["state"]))
        return found

    # -- mastery -----------------------------------------------------------------------------

    def thresholds(self, vocation_id: str) -> list[int]:
        return list(self.raw["mastery"]["rank_thresholds_by_group"][self.group(vocation_id)])

    def rank_for(self, vocation_id: str, points: int) -> int:
        """``rank(points, T) = max { r : points >= T[r] }`` (v0.1 section 6.1)."""
        return max(rank for rank, needed in enumerate(self.thresholds(vocation_id), start=1) if points >= needed)

    def threat_floor(self, vocation_id: str, rank: int) -> int:
        return int(self.raw["mastery"]["threat_min_by_group_and_rank"][self.group(vocation_id)][rank - 1])

    def skills_learned_by(self, vocation_id: str, rank: int) -> list[str]:
        return [e["skill_id"] for e in self.vocations[vocation_id]["skills_learned"] if rank >= e["rank"]]


def signal_name(entry: Json) -> str:
    """The text form of a discovery signal, for example ``item_found:jester_mask``."""
    kind = entry["kind"]
    if kind == "mastery_rank":
        return f"{kind}:{entry['vocation_id']}:{entry['rank']}"
    return f"{kind}:{entry.get('item_id') or entry.get('quest_id')}"
