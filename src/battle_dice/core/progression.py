"""Encounters, between-battle recovery, the mandatory upgrade and the optional bench swap (sections 11, 12)."""

from __future__ import annotations

import copy
import dataclasses
from typing import TYPE_CHECKING, Any

from battle_dice.content.loader import Content
from battle_dice.core.build import HeroBuild, build_from_class
from battle_dice.core.events import EventType
from battle_dice.core.models import (
    SIDE_ENEMY,
    SIDE_HERO,
    STATE_DOWNED,
    STATE_STANDING,
    STATUS_POISON,
    STATUS_WEAKEN,
    Combatant,
    DieDefinition,
    FaceDefinition,
    to_plain,
)

if TYPE_CHECKING:  # pragma: no cover
    from battle_dice.core.engine import Engine


def ceil_percent(value: int, percent: int) -> int:
    """Integer ``ceil(value * percent / 100)`` without floating point."""
    return -((-value * percent) // 100)


# --------------------------------------------------------------------------------------------
# Combatant construction
# --------------------------------------------------------------------------------------------


def make_hero(content: Content, hero_id: str, class_id: str, row: str) -> Combatant:
    """A hero of a shipped class, as it enters Battle 1."""
    return hero_from_build(content, hero_id, build_from_class(content, class_id), row)


def hero_from_build(content: Content, hero_id: str, build: HeroBuild, row: str) -> Combatant:
    return Combatant(
        id=hero_id,
        side=SIDE_HERO,
        archetype_id=build.vocation_id,
        name=f"{build.name} {hero_id[1:].lstrip('0')}",
        row=row,
        hp=build.start_hp,
        max_hp=build.max_hp,
        shields=0,
        speed=build.speed,
        base_initiative=build.base_initiative,
        gauge=content.balance["timeline"]["start_gauge"],
        mana=build.start_mana,
        max_mana=build.max_mana,
        corruption=build.start_corruption,
        max_corruption=build.max_corruption,
        reaction_charges=content.balance["reactions"]["charges_per_activation"],
        equipped_dice_ids=list(build.starting_dice),
    )


def make_enemies(content: Content, party_size: int, battle: int) -> list[Combatant]:
    """Build the scaled roster. IDs (``b1_e01`` ...) are assigned by archetype, then spawn order."""
    entries = list(enumerate(content.encounter(party_size, battle)))
    entries.sort(key=lambda pair: (pair[1]["archetype"], pair[0]))
    counts: dict[str, int] = {}
    totals: dict[str, int] = {}
    for _, entry in entries:
        totals[entry["archetype"]] = totals.get(entry["archetype"], 0) + 1
    enemies = []
    for number, (_, entry) in enumerate(entries, start=1):
        archetype = entry["archetype"]
        base = content.enemies[archetype]
        overrides = entry.get("overrides", {})
        counts[archetype] = counts.get(archetype, 0) + 1
        suffix = f" {counts[archetype]}" if totals[archetype] > 1 else ""
        max_hp = overrides.get("max_hp", base["max_hp"])
        enemies.append(
            Combatant(
                id=f"b{battle}_e{number:02d}",
                side=SIDE_ENEMY,
                archetype_id=archetype,
                name=f"{base['name']}{suffix}",
                row=base["row"],
                hp=max_hp,
                max_hp=max_hp,
                shields=0,
                speed=overrides.get("speed", base["speed"]),
                base_initiative=base["base_initiative"],
                gauge=content.balance["timeline"]["start_gauge"],
                mana=0,
                max_mana=0,
                corruption=0,
                max_corruption=0,
                action_overrides=copy.deepcopy(overrides.get("actions", {})),
            )
        )
    return enemies


# --------------------------------------------------------------------------------------------
# Recovery (section 11.1)
# --------------------------------------------------------------------------------------------


def apply_recovery(ctx: Engine) -> None:
    combat = ctx.combat
    balance = ctx.content.balance
    heroes = combat.side(SIDE_HERO)
    before = ctx.snap([h.id for h in heroes])
    report = []
    for hero in heroes:
        entry: dict[str, Any] = {"id": hero.id, "hp_before": hero.hp, "was_downed": hero.state == STATE_DOWNED}
        if hero.state == STATE_DOWNED:
            hero.hp = min(hero.max_hp, ceil_percent(hero.max_hp, balance["recovery"]["downed_restore_percent"]))
            hero.state = STATE_STANDING
        else:
            hero.hp = min(hero.max_hp, hero.hp + ceil_percent(hero.max_hp, balance["recovery"]["standing_heal_percent"]))
        hero.shields = 0
        hero.mana = ctx.build(hero.id).max_mana
        hero.status_instances = []
        hero.gauge = balance["timeline"]["start_gauge"]
        hero.reaction_charges = balance["reactions"]["charges_per_activation"]
        entry.update({"hp_after": hero.hp, "mana": hero.mana, "corruption": hero.corruption})
        report.append(entry)
    ctx.emit(EventType.RECOVERY_APPLIED, delta={"heroes": report}, before=before, affected=[h.id for h in heroes])


# --------------------------------------------------------------------------------------------
# Upgrade offers (section 11.2)
# --------------------------------------------------------------------------------------------


def _is_duration_face(face: FaceDefinition) -> bool:
    status = face.status_effect()
    return status is not None and status["status"] in (STATUS_POISON, STATUS_WEAKEN)


def sharpened(face: FaceDefinition, cap: int) -> FaceDefinition | None:
    """+1 power (capped). Poison/Weaken gain +1 duration instead of stack magnitude."""
    if face.is_blank:
        return None
    new_face = copy.deepcopy(face)
    if _is_duration_face(face):
        for effect in new_face.effects:
            if effect["type"] == "apply_status":
                if effect["duration"] >= cap:
                    return None
                effect["duration"] += 1
    else:
        if face.power >= cap:
            return None
        new_face.power += 1
    new_face.id = f"{face.id}+sharpen"
    new_face.name = f"{face.name}+"
    return new_face


def _offer(kind: str, face_index: int, before: FaceDefinition, after: FaceDefinition) -> dict[str, Any]:
    return {
        "kind": kind,
        "face_index": face_index,
        "before": to_plain(before),
        "after": to_plain(after),
    }


def offers_for_die(ctx: Engine, hero: Combatant, die: DieDefinition) -> list[dict[str, Any]]:
    """Three eligible cards: Sharpen, Reforge, Imbue. An ineligible card is replaced by the next valid option."""
    content = ctx.content
    cap = content.balance["upgrades"]["face_power_cap"]
    wanted = content.balance["upgrades"]["offers_per_die"]
    upgrades = content.upgrades
    draws: list[dict[str, Any]] = []

    def rotate(items: list[Any]) -> list[Any]:
        """Deterministically rotate a catalog list using the rewards stream."""
        if len(items) <= 1:
            return list(items)
        value, draw = ctx.draw("rewards", len(items))
        draws.append(draw)
        return items[value:] + items[:value]

    sharpen_pool = []
    for index in rotate(list(range(die.size))):
        new_face = sharpened(die.faces[index], cap)
        if new_face is not None:
            sharpen_pool.append(_offer("sharpen", index, die.faces[index], new_face))

    family = ctx.build(hero.id).upgrade_family
    reforge_faces = rotate([content.upgrade_faces[f] for f in upgrades["reforge_faces"][family]])
    reforge_pool = [
        _offer("reforge", index, die.faces[index], face)
        for index in range(die.size)
        if die.faces[index].is_blank
        for face in reforge_faces
    ]

    imbue_faces = rotate([content.upgrade_faces[f] for f in upgrades["imbue_faces"][family]])
    imbue_pool = [
        _offer("imbue", index, die.faces[index], face)
        for index in rotate(list(range(die.size)))
        for face in imbue_faces
        if die.faces[index].signature() != face.signature()
    ]

    pools = [sharpen_pool, reforge_pool, imbue_pool]
    chosen: list[dict[str, Any]] = [pool.pop(0) for pool in pools if pool]
    # Fill any gap from the remaining catalog options in a fixed order.
    for pool in (imbue_pool, sharpen_pool, reforge_pool):
        while len(chosen) < wanted and pool:
            chosen.append(pool.pop(0))
    chosen = chosen[:wanted]
    kinds = upgrades["kinds"]
    for number, offer in enumerate(chosen, start=1):
        offer["offer_id"] = f"{hero.id}:{die.id}:{number}"
        offer["hero_id"] = hero.id
        offer["die_id"] = die.id
        offer["kind_name"] = kinds[offer["kind"]]["name"]
        offer["summary"] = kinds[offer["kind"]]["summary"]
        offer["rng_draws"] = draws
    return chosen


def generate_offers(ctx: Engine) -> None:
    """Generate every hero/die offer set once, in stable order, from the rewards stream."""
    state = ctx.state
    state.upgrade_offers = {}
    for hero in ctx.combat.side(SIDE_HERO):
        state.upgrade_offers[hero.id] = {}
        for die_id in sorted(hero.equipped_dice_ids):
            state.upgrade_offers[hero.id][die_id] = offers_for_die(ctx, hero, ctx.die_for(hero.id, die_id))
    ctx.emit(
        EventType.UPGRADE_OFFERS_GENERATED,
        delta={
            "offers": {
                hero_id: {die_id: [o["offer_id"] + ":" + o["kind"] for o in offers] for die_id, offers in dice.items()}
                for hero_id, dice in state.upgrade_offers.items()
            }
        },
        rng_stream="rewards",
        rng_draw_index=state.rng["rewards"].draws,
    )


def face_from_plain(raw: dict[str, Any]) -> FaceDefinition:
    names = {f.name for f in dataclasses.fields(FaceDefinition)}
    return FaceDefinition(**{k: copy.deepcopy(v) for k, v in raw.items() if k in names})


def apply_upgrade(ctx: Engine, hero_id: str, die_id: str, offer_id: str) -> str | None:
    """Apply the mandatory upgrade as a new versioned die definition. Returns a rejection reason."""
    state = ctx.state
    hero = ctx.combat.combatants.get(hero_id)
    if hero is None or not hero.is_hero:
        return f"Unknown hero '{hero_id}'."
    if die_id not in hero.equipped_dice_ids:
        return f"{hero.name} does not have die '{die_id}' equipped."
    offers = state.upgrade_offers.get(hero_id, {}).get(die_id, [])
    offer = next((o for o in offers if o["offer_id"] == offer_id), None)
    if offer is None:
        return f"Upgrade '{offer_id}' is not offered for that die."
    old = ctx.die_for(hero_id, die_id)
    new_die = copy.deepcopy(old)
    new_die.faces[offer["face_index"]] = face_from_plain(offer["after"])
    new_die.definition_version = old.definition_version + 1
    if len(new_die.faces) != new_die.size:
        return "Upgrade would change the die size."  # pragma: no cover - invariant
    state.die_overrides.setdefault(hero_id, {})[die_id] = new_die
    record = {
        "hero_id": hero_id,
        "die_id": die_id,
        "offer_id": offer_id,
        "kind": offer["kind"],
        "face_index": offer["face_index"],
        "from_version": old.definition_version,
        "to_version": new_die.definition_version,
    }
    state.upgrades.append(record)
    ctx.emit(
        EventType.UPGRADE_APPLIED,
        actor_id=hero_id,
        delta={**record, "before": offer["before"], "after": offer["after"]},
    )
    return None


def upgraded_die_ids(ctx: Engine, hero_id: str) -> list[str]:
    return sorted(u["die_id"] for u in ctx.state.upgrades if u["hero_id"] == hero_id)


def swap_problem(ctx: Engine, hero_id: str, out_die_id: str, in_die_id: str) -> str | None:
    state = ctx.state
    hero = ctx.combat.combatants.get(hero_id)
    if hero is None or not hero.is_hero:
        return f"Unknown hero '{hero_id}'."
    if state.swaps_used.get(hero_id, 0) >= ctx.content.balance["upgrades"]["max_swaps_per_hero"]:
        return f"{hero.name} has already used its optional swap this run."
    if out_die_id not in hero.equipped_dice_ids:
        return f"{hero.name} does not have die '{out_die_id}' equipped."
    if out_die_id in upgraded_die_ids(ctx, hero_id):
        return "The upgraded die is locked and cannot be swapped out."
    if in_die_id not in state.inventory.get(hero_id, []):
        return f"Die '{in_die_id}' is not on {hero.name}'s bench."
    incoming = ctx.base_die(hero_id, in_die_id)
    if incoming is None or incoming.affinity_class != ctx.build(hero_id).vocation_id:
        return "A hero can only equip dice of its own class."
    return None


def apply_swap(ctx: Engine, hero_id: str, out_die_id: str, in_die_id: str) -> str | None:
    problem = swap_problem(ctx, hero_id, out_die_id, in_die_id)
    if problem:
        return problem
    state = ctx.state
    hero = ctx.combat.combatants[hero_id]
    capacity = ctx.build(hero_id).dice_capacity
    hero.equipped_dice_ids[hero.equipped_dice_ids.index(out_die_id)] = in_die_id
    bench = state.inventory[hero_id]
    bench[bench.index(in_die_id)] = out_die_id
    assert len(hero.equipped_dice_ids) == capacity
    state.swaps_used[hero_id] = state.swaps_used.get(hero_id, 0) + 1
    ctx.emit(
        EventType.DIE_SWAPPED,
        actor_id=hero_id,
        delta={"hero_id": hero_id, "out_die_id": out_die_id, "in_die_id": in_die_id,
               "equipped": list(hero.equipped_dice_ids), "bench": list(bench)},
    )
    return None
