"""The Class Evolution vocation catalog: validation, and hero builds from it.

The catalog (``content/class_evolution/vocation_catalog.json``) describes the 14 vocations of
``docs/class_evolution/FDD_v0.2.md``. It is not one of the six content documents and is not part
of the content hash. The game reads it only when the feature gate ``class_evolution_v1`` is on
(:mod:`battle_dice.features`); with the gate off this module is never imported by the game.

**Validation** checks what the JSON Schema cannot: that every id resolves, that new faces, dice,
reactions and vocations follow the rules of the shipped content loader, that the prerequisite graph
can be climbed, and that every rank can be trained.

    python tools/class_evolution/validate_catalog.py            # every wave; open ends are warnings
    python tools/class_evolution/validate_catalog.py --wave 1   # is wave 1 releasable on shipped content?

**Builds.** :func:`load_vocation_catalog` validates the catalog and returns a
:class:`VocationCatalog`, which resolves a vocation id to the :class:`~battle_dice.core.build.HeroBuild`
the rules run on. A vocation that needs anything listed under ``engine_gaps`` is refused by name.

:func:`validate` returns one line per finding. Lines that start with ``warning:`` do not make the
catalog invalid; every other line is a problem. ``main`` prints the lines, then ``OK`` when there
is no problem, and exits 0 or 1.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import jsonschema

import battle_dice
from battle_dice.content.loader import (
    FACE_EFFECT_TYPES,
    REACTION_EFFECT_TYPES,
    Content,
    ContentError,
    build_content,
    canonical_json,
    load_content,
    load_schema,
)
from battle_dice.core.build import BuildNotSupported, EncounterNotPlayable, HeroBuild, build_from_class
from battle_dice.core.models import CATEGORY_BLANK, CATEGORY_HEALING, EXECUTABLE_CATEGORIES

CATALOG_PATH = Path(__file__).resolve().parent / "class_evolution" / "vocation_catalog.json"
SCHEMA_PATH = CATALOG_PATH.with_name("vocation_catalog.schema.json")
WARNING = "warning: "
NOVICE = "novice"
#: Lists whose entries carry an ``id`` that must be unique within the list.
ID_LISTS = ("vocations", "schedules", "passives", "reactions", "skills", "items", "quests", "challenges", "encounters", "engine_gaps")
#: The catalog lists an ``engine_gaps`` entry may point into, by the prefix used in ``used_by``.
GAP_KINDS = {"schedule": "schedules", "passive": "passives", "reaction": "reactions", "skill": "skills"}

Json = dict[str, Any]


# --------------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------------


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> Json:
    counts = Counter(key for key, _ in pairs)
    repeated = sorted(key for key, count in counts.items() if count > 1)
    if repeated:
        raise ValueError(f"duplicate key(s) in one JSON object: {', '.join(repeated)}")
    return dict(pairs)


def load_json(path: Path) -> Json:
    """Read a JSON object, refusing an object that names the same key twice (JSON parsers keep the last)."""
    document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(document, dict):
        raise ValueError(f"{path.name}: the top level must be an object")
    return document


def load_catalog(path: Path = CATALOG_PATH) -> Json:
    return load_json(path)


def load_catalog_schema(path: Path = SCHEMA_PATH) -> Json:
    return load_json(path)


#: The coded lines this validator can report. Each is listed in docs/class_evolution/persistence/error_codes.json.
CONTENT_VALIDATION_CODES = ("TRAINING_DEAD_END", "UNLOCK_DEAD_END")


def problems_only(lines: Iterable[str]) -> list[str]:
    return [line for line in lines if not line.startswith(WARNING)]


def warnings_only(lines: Iterable[str]) -> list[str]:
    return [line for line in lines if line.startswith(WARNING)]


# --------------------------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------------------------


def schema_problems(catalog: Any, schema: Json | None = None) -> list[str]:
    """Draft 2020-12 validation of ``catalog``; one line per violation, in document order."""
    validator = jsonschema.Draft202012Validator(schema if schema is not None else load_catalog_schema())
    problems = []
    for error in sorted(validator.iter_errors(catalog), key=lambda e: [str(p) for p in e.path]):
        location = "/".join(str(p) for p in error.path) or "<root>"
        message = error.message if len(error.message) <= 300 else error.message[:300] + "..."
        problems.append(f"schema: {location}: {message}")
    return problems


def _enum(schema: Json, *path: str) -> list[Any]:
    node: Any = schema
    for key in path:
        node = node[key]
    return list(node["enum"])


def vocabulary_problems(schema: Json) -> list[str]:
    """The catalog schema repeats the game's vocabularies; report any that no longer match the game."""
    game = load_schema()
    face = ("$defs", "face", "properties")
    reaction = ("$defs", "reaction_def", "properties")
    die = ("$defs", "die_def", "properties")
    expected: dict[str, list[Any]] = {
        "category": _enum(game, "$defs", "category"),
        "executable_category": list(EXECUTABLE_CATEGORIES),
        "status_kind": _enum(game, "$defs", "status_kind"),
        "row": _enum(game, "$defs", "row"),
        "target_scope": _enum(game, *face, "target_scope"),
        "range_type": _enum(game, *face, "range_type"),
        "face_tag": _enum(game, *face, "tags", "items"),
        "face_effect_type": list(FACE_EFFECT_TYPES),
        "reaction_effect_type": list(REACTION_EFFECT_TYPES),
        "reaction_stage": _enum(game, *reaction, "stage"),
        "reaction_trigger": _enum(game, *reaction, "trigger"),
        "reaction_target": _enum(game, *reaction, "target"),
        "die_size": _enum(game, *die, "size"),
        "die_role": _enum(game, *die, "role"),
        "shipped_passive_type": _enum(game, "$defs", "class_def", "properties", "passive", "properties", "type"),
    }
    problems = []
    for name, values in expected.items():
        mine = _enum(schema, "$defs", name)
        if sorted(mine, key=str) != sorted(values, key=str):
            problems.append(f"schema vocabulary '{name}' is {mine} but the game uses {values}")
    return problems


# --------------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------------


def _by_id(entries: Sequence[Json]) -> dict[str, Json]:
    return {entry["id"]: entry for entry in entries}


def _new_vocations(catalog: Json) -> list[Json]:
    return [v for v in catalog["vocations"] if v["group"] != NOVICE]


def _shipped_faces(shipped: Content) -> dict[str, Json]:
    return dict(shipped.documents["dice"]["face_library"])


def _resolve_face(catalog: Json, shipped: Content, face_id: str) -> Json | None:
    if face_id in catalog["face_library"]:
        return dict(catalog["face_library"][face_id])
    return _shipped_faces(shipped).get(face_id)


def _resolve_reaction(catalog: Json, shipped: Content, reaction_id: str) -> Json | None:
    """A catalog reaction, or a shipped one (which the engine implements by definition)."""
    for reaction in catalog["reactions"]:
        if reaction["id"] == reaction_id:
            return dict(reaction)
    if reaction_id in shipped.reactions:
        return {**shipped.reactions[reaction_id], "id": reaction_id, "engine_support": "existing"}
    return None


def _prerequisite_leaves(node: Json) -> Iterable[tuple[str, Any]]:
    for kind in ("all", "any"):
        if kind in node:
            for child in node[kind]:
                yield from _prerequisite_leaves(child)
            return
    for kind in ("mastered", "quest", "item", "mastered_count"):
        if kind in node:
            yield kind, node[kind]


# --------------------------------------------------------------------------------------------
# Ids
# --------------------------------------------------------------------------------------------


def _id_problems(catalog: Json, shipped: Content) -> list[str]:
    problems = []
    for name in ID_LISTS:
        counts = Counter(entry["id"] for entry in catalog[name])
        problems += [f"{name}: duplicate id '{key}'" for key, count in sorted(counts.items()) if count > 1]
    upgrade_faces = shipped.documents["upgrades"]["face_library"]
    for face_id, face in catalog["face_library"].items():
        if face_id in _shipped_faces(shipped) or face_id in upgrade_faces:
            problems.append(f"face_library: '{face_id}' redefines a shipped face; use the shipped face by its id instead")
            continue
        rules = {key: value for key, value in face.items() if key != "name"}
        for shipped_id, other in _shipped_faces(shipped).items():
            if rules == {key: value for key, value in other.items() if key != "name"}:
                problems.append(f"face_library: '{face_id}' only renames the shipped face '{shipped_id}'; use that face by its id instead")
    for die_id in catalog["dice"]:
        if die_id in shipped.dice:
            problems.append(f"dice: '{die_id}' redefines a shipped die")
    for reaction in catalog["reactions"]:
        if reaction["id"] in shipped.reactions:
            problems.append(f"reactions: '{reaction['id']}' redefines a shipped reaction; use the shipped reaction by its id instead")
    return problems


# --------------------------------------------------------------------------------------------
# Faces and dice
# --------------------------------------------------------------------------------------------


def face_rule_problems(origin: str, face_id: str, raw: Json) -> list[str]:
    """The die-face rules of the shipped loader.

    ``battle_dice.content.loader`` keeps these rules in ``check_face``, a function nested inside
    ``build_content``, so it cannot be imported and called. This mirrors it rule for rule, and
    :func:`_loader_problems` then runs the same faces through the loader itself, which stays the
    authority: a rule added there is reported even before it is mirrored here.
    """
    problems = []
    blank = raw["category"] == CATEGORY_BLANK
    if blank and (raw["effects"] or raw["action_speed"] is not None or raw["target_scope"] != "none"):
        problems.append(f"{origin}: blank face '{face_id}' must have no effects, speed or target")
    if not blank and (not raw["effects"] or raw["action_speed"] is None):
        problems.append(f"{origin}: executable face '{face_id}' needs effects and an action_speed")
    if raw["can_revive"] and raw["category"] != CATEGORY_HEALING:
        problems.append(f"{origin}: face '{face_id}' is can_revive but is not a Healing face")
    if raw["can_revive"] and not any(e["type"] == "heal" for e in raw["effects"]):
        problems.append(f"{origin}: face '{face_id}' is can_revive but has no heal effect")
    if raw["can_revive"] and any(e["type"] == "heal" and e.get("amount", raw["power"]) < 1 for e in raw["effects"]):
        problems.append(f"{origin}: face '{face_id}' is can_revive but would revive at 0 HP; its heal must be at least 1")
    if not blank and raw["target_scope"] == "none":
        problems.append(f"{origin}: executable face '{face_id}' needs a target scope other than 'none'")
    for effect in raw["effects"]:
        if effect["type"] not in FACE_EFFECT_TYPES:
            problems.append(f"{origin}: face '{face_id}' uses effect '{effect['type']}', which only a reaction can have")
    return problems


def _face_problems(catalog: Json) -> list[str]:
    problems = []
    for face_id, raw in catalog["face_library"].items():
        problems += face_rule_problems("face_library", face_id, raw)
        # The shipped faces all name their reach in their tags; passives and schedules read the tag.
        if raw["range_type"] in ("melee", "ranged") and raw["range_type"] not in raw["tags"]:
            problems.append(f"face_library: face '{face_id}' has range_type '{raw['range_type']}' but not the tag of that name")
    return problems


def _dice_problems(catalog: Json, shipped: Content) -> list[str]:
    problems = []
    vocations = _by_id(_new_vocations(catalog))
    used_faces: set[str] = set()
    for die_id, die in catalog["dice"].items():
        if len(die["faces"]) != die["size"]:
            problems.append(f"dice: die '{die_id}' declares size {die['size']} but has {len(die['faces'])} faces")
        if die["affinity_class"] not in vocations:
            problems.append(f"dice: die '{die_id}' has affinity_class '{die['affinity_class']}', which is not a new vocation")
        for index, face_id in enumerate(die["faces"]):
            used_faces.add(face_id)
            if _resolve_face(catalog, shipped, face_id) is None:
                problems.append(f"dice: die '{die_id}' face {index + 1} references unknown face '{face_id}'")
    for face_id in catalog["face_library"]:
        if face_id not in used_faces:
            problems.append(f"face_library: face '{face_id}' is on no die")
    return problems


# --------------------------------------------------------------------------------------------
# Schedules, passives, reactions
# --------------------------------------------------------------------------------------------


def shipped_policy(schedule: Json) -> str | None:
    """The shipped scheduling policy (single, sequence, free) that behaves exactly like ``schedule``, if any."""
    slots = schedule["slots"]
    every = set(EXECUTABLE_CATEGORIES)
    if len(slots) != schedule["max_actions"] or any("tags_any" in slot for slot in slots):
        return None
    wide = all(set(slot["categories"]) == every for slot in slots)
    if schedule["max_actions"] == 1:
        return "single" if wide else None
    if wide and schedule["order"] == "action_speed" and not schedule["distinct_categories"]:
        return "free"
    if schedule["max_actions"] == 2 and schedule["order"] == "slots":
        first, second = (slot["categories"] for slot in slots)
        if len(first) == 1 and first[0] not in second:
            return "sequence"
    return None


def shipped_scheduling(schedule: Json) -> Json:
    """``schedule`` as a shipped ``scheduling`` block. Only for schedules :func:`shipped_policy` recognises."""
    policy = shipped_policy(schedule)
    if policy is None:
        raise ValueError(f"schedule '{schedule['id']}' has no shipped policy")
    block: Json = {"policy": policy, "label": schedule["label"], "max_actions": schedule["max_actions"], "summary": schedule["summary"]}
    if policy == "sequence":
        block["first_category"] = schedule["slots"][0]["categories"][0]
        block["second_categories"] = list(schedule["slots"][1]["categories"])
    return block


def slot_schedule(schedule_id: str, scheduling: Json) -> Json:
    """A shipped ``scheduling`` block in the catalog's slot model (always ``engine_support: existing``)."""
    every = list(EXECUTABLE_CATEGORIES)
    if scheduling["policy"] == "sequence":
        slots = [{"categories": [scheduling["first_category"]]}, {"categories": list(scheduling["second_categories"])}]
        distinct, order = True, "slots"
    else:
        slots = [{"categories": list(every)} for _ in range(scheduling["max_actions"])]
        distinct, order = False, "action_speed"
    return {"id": schedule_id, "label": scheduling["label"], "summary": scheduling["summary"], "max_actions": scheduling["max_actions"],
            "slots": slots, "distinct_categories": distinct, "order": order, "engine_support": "existing"}


def _schedule_problems(catalog: Json, schema: Json) -> list[str]:
    problems = []
    tags = set(_enum(schema, "$defs", "face_tag"))
    for schedule in catalog["schedules"]:
        origin = f"schedules: '{schedule['id']}'"
        if len(schedule["slots"]) != schedule["max_actions"]:
            problems.append(f"{origin} has {len(schedule['slots'])} slot(s) but max_actions {schedule['max_actions']}")
        for index, slot in enumerate(schedule["slots"]):
            for category in slot["categories"]:
                if category not in EXECUTABLE_CATEGORIES:
                    problems.append(f"{origin} slot {index + 1} uses unknown category '{category}'")
            for tag in slot.get("tags_any", []):
                if tag not in tags:
                    problems.append(f"{origin} slot {index + 1} uses unknown tag '{tag}'")
        if schedule["distinct_categories"] and schedule["max_actions"] > len(EXECUTABLE_CATEGORIES):
            problems.append(f"{origin} asks for more distinct categories than exist")
        policy = shipped_policy(schedule)
        if schedule["engine_support"] == "existing" and policy is None:
            problems.append(f"{origin} is marked existing but no shipped policy (single, sequence, free) behaves like it")
        if schedule["engine_support"] == "new" and policy is not None:
            problems.append(f"{origin} is marked new but the shipped '{policy}' policy already behaves like it")
    return problems


def _attack_faces(catalog: Json, shipped: Content, vocation: Json) -> dict[str, Json]:
    """Every Attack face ``vocation`` can roll.

    On its own dice, on the dice of the starting class it grew from (owner decision of 2026-11-11:
    a vocation may equip its own dice and its family's), and on that family's reforge and imbue tables.
    """
    faces: dict[str, Json] = {}
    for die_id in vocation["starting_dice"] + vocation["bench_dice"]:
        for face_id in catalog["dice"].get(die_id, {}).get("faces", []):
            face = _resolve_face(catalog, shipped, face_id)
            if face is not None:
                faces[face_id] = face
    family = shipped.classes.get(vocation["upgrade_family"], {})
    shipped_faces = _shipped_faces(shipped)
    for die_id in [*family.get("starting_dice", []), *family.get("bench_dice", [])]:
        for face_id in shipped.documents["dice"]["dice"][die_id]["faces"]:
            faces[face_id] = shipped_faces[face_id]
    upgrades = shipped.documents["upgrades"]
    for table in ("reforge_faces", "imbue_faces"):
        for face_id in upgrades[table].get(vocation["upgrade_family"], []):
            faces[face_id] = upgrades["face_library"][face_id]
    return {face_id: face for face_id, face in faces.items() if face["category"] == "attack"}


def _passive_problems(catalog: Json, shipped: Content, schema: Json) -> list[str]:
    problems = []
    shipped_types = set(_enum(schema, "$defs", "shipped_passive_type"))
    schedules = _by_id(catalog["schedules"])
    for passive in catalog["passives"]:
        origin = f"passives: '{passive['id']}'"
        users = [v for v in _new_vocations(catalog) if v["passive_id"] == passive["id"]]
        if passive["engine_support"] == "existing" and passive["type"] not in shipped_types:
            problems.append(f"{origin} is marked existing but type '{passive['type']}' is not a shipped passive type")
        if passive["engine_support"] == "existing" and passive["type"] == "combo_attack_bonus":
            # The engine reads the combo's opener from the sequence policy's first_category.
            for vocation in users:
                schedule = schedules.get(vocation["schedule_id"])
                if schedule is None or schedule["engine_support"] != "existing" or shipped_policy(schedule) != "sequence":
                    problems.append(f"{origin} is marked existing but '{vocation['id']}' does not use a shipped sequence schedule")
        tag = passive.get("attack_tag_invariant")
        for vocation in users if tag else []:
            for face_id, face in sorted(_attack_faces(catalog, shipped, vocation).items()):
                if tag not in face["tags"]:
                    problems.append(f"{origin} needs every Attack face of '{vocation['id']}' tagged '{tag}', but '{face_id}' is not")
    return problems


def reaction_rule_problems(origin: str, raw: Json) -> list[str]:
    """The reaction rules of the shipped loader (mirrored: they are inline in ``build_content``)."""
    problems = []
    for index, effect in enumerate(raw["effects"]):
        kind = effect["type"]
        if kind not in REACTION_EFFECT_TYPES:
            problems.append(f"{origin} uses effect '{kind}', which reactions do not implement")
        elif kind == "interrupt":
            if index != 0:
                problems.append(f"{origin} must list its interrupt effect first")
            for key in ("resisted_damage_reduction", "resisted_magnitude_reduction"):
                if key not in effect:
                    problems.append(f"{origin} interrupt effect needs '{key}'")
        elif effect.get("amount", 0) < 1:
            problems.append(f"{origin} effect '{kind}' needs an amount of at least 1")
    return problems


def _reaction_problems(catalog: Json) -> list[str]:
    problems = []
    for reaction in catalog["reactions"]:
        problems += reaction_rule_problems(f"reactions: '{reaction['id']}'", reaction)
    return problems


# --------------------------------------------------------------------------------------------
# Vocations
# --------------------------------------------------------------------------------------------


def _vocation_problems(catalog: Json, shipped: Content) -> list[str]:
    problems = []
    schedules, passives = _by_id(catalog["schedules"]), _by_id(catalog["passives"])
    skills, challenges = _by_id(catalog["skills"]), _by_id(catalog["challenges"])
    rank_count = catalog["mastery"]["rank_count"]
    timeline = shipped.balance["timeline"]
    class_ids = Counter(v["class_id"] for v in catalog["vocations"] if v["group"] == NOVICE)
    taught = Counter(entry["skill_id"] for v in catalog["vocations"] for entry in v["skills_learned"])

    for vocation in catalog["vocations"]:
        origin = f"vocations: '{vocation['id']}'"
        if vocation["bonus_challenge_id"] not in challenges:
            problems.append(f"{origin} references unknown challenge '{vocation['bonus_challenge_id']}'")
        for entry in vocation["skills_learned"]:
            if entry["skill_id"] not in skills:
                problems.append(f"{origin} teaches unknown skill '{entry['skill_id']}'")
            if entry["rank"] > rank_count:
                problems.append(f"{origin} teaches '{entry['skill_id']}' at rank {entry['rank']}, above rank_count {rank_count}")
        if vocation["group"] == NOVICE:
            if vocation["class_id"] not in shipped.classes:
                problems.append(f"{origin} has class_id '{vocation['class_id']}', which is not a shipped class")
            if class_ids[vocation["class_id"]] > 1:
                problems.append(f"{origin} shares class_id '{vocation['class_id']}' with another novice vocation")
            continue

        if vocation["id"] in shipped.classes:
            problems.append(f"{origin} redefines a shipped class; shipped classes are listed with definition 'shipped'")
        # The same rules the shipped loader applies to a class.
        if len(vocation["starting_dice"]) != vocation["dice_capacity"]:
            problems.append(f"{origin} must start with exactly dice_capacity ({vocation['dice_capacity']}) dice")
        for key, role in (("starting_dice", "starting"), ("bench_dice", "sidegrade")):
            for die_id in vocation[key]:
                die = catalog["dice"].get(die_id)
                if die is None:
                    problems.append(f"{origin} references unknown die '{die_id}'")
                elif die["affinity_class"] != vocation["id"]:
                    problems.append(f"{origin} cannot use die '{die_id}' of class '{die['affinity_class']}'")
                elif die["role"] != role:
                    problems.append(f"{origin} lists die '{die_id}' under {key} but its role is '{die['role']}'")
        listed = vocation["starting_dice"] + vocation["bench_dice"]
        if len(set(listed)) != len(listed):
            problems.append(f"{origin} lists the same die more than once across starting_dice and bench_dice")
        if vocation["start_hp"] > vocation["max_hp"] or vocation["start_mana"] > vocation["max_mana"]:
            problems.append(f"{origin} has a starting value above its maximum")
        if vocation["start_corruption"] > vocation["max_corruption"]:
            problems.append(f"{origin} starting corruption exceeds its maximum")
        if not timeline["min_speed"] <= vocation["speed"] <= timeline["max_speed"]:
            problems.append(f"{origin} speed {vocation['speed']} is outside the timeline's {timeline['min_speed']}..{timeline['max_speed']}")
        # References.
        if vocation["schedule_id"] not in schedules:
            problems.append(f"{origin} references unknown schedule '{vocation['schedule_id']}'")
        elif schedules[vocation["schedule_id"]]["max_actions"] > vocation["dice_capacity"]:
            problems.append(f"{origin} has a schedule of more actions than it has dice")
        if vocation["passive_id"] not in passives:
            problems.append(f"{origin} references unknown passive '{vocation['passive_id']}'")
        reaction = _resolve_reaction(catalog, shipped, vocation["reaction_id"])
        if reaction is None:
            problems.append(f"{origin} references unknown reaction '{vocation['reaction_id']}'")
        if vocation["upgrade_family"] not in shipped.classes:
            problems.append(f"{origin} has upgrade_family '{vocation['upgrade_family']}', which is not a shipped class")

    for die_id in catalog["dice"]:
        if not any(die_id in v["starting_dice"] + v["bench_dice"] for v in _new_vocations(catalog)):
            problems.append(f"dice: die '{die_id}' is used by no vocation")
    for name, key in (("schedules", "schedule_id"), ("passives", "passive_id"), ("reactions", "reaction_id")):
        used = {v[key] for v in _new_vocations(catalog)}
        problems += [f"{name}: '{entry['id']}' is used by no vocation" for entry in catalog[name] if entry["id"] not in used]
    used_challenges = {v["bonus_challenge_id"] for v in catalog["vocations"]}
    problems += [f"challenges: '{c['id']}' is used by no vocation" for c in catalog["challenges"] if c["id"] not in used_challenges]
    for skill in catalog["skills"]:
        if taught[skill["id"]] != 1:
            problems.append(f"skills: '{skill['id']}' must be taught by exactly one vocation, not {taught[skill['id']]}")
    return problems


# --------------------------------------------------------------------------------------------
# Prerequisites, discovery, items, quests
# --------------------------------------------------------------------------------------------


def _reference_problems(catalog: Json) -> list[str]:
    problems = []
    vocations, quests, items = _by_id(catalog["vocations"]), _by_id(catalog["quests"]), _by_id(catalog["items"])
    encounters = _by_id(catalog["encounters"])
    used_quests: set[str] = set()
    used_items: set[str] = set()
    for vocation in _new_vocations(catalog):
        origin = f"vocations: '{vocation['id']}'"
        for kind, value in _prerequisite_leaves(vocation["prerequisite"]):
            if kind == "mastered" and value not in vocations:
                problems.append(f"{origin} prerequisite references unknown vocation '{value}'")
            elif kind == "quest":
                used_quests.add(value)
                if value not in quests:
                    problems.append(f"{origin} prerequisite references unknown quest '{value}'")
            elif kind == "item":
                used_items.add(value)
                if value not in items:
                    problems.append(f"{origin} prerequisite references unknown item '{value}'")
            elif kind == "mastered_count":
                size = sum(1 for v in catalog["vocations"] if v["group"] == value["group"])
                if value["minimum"] > size:
                    problems.append(f"{origin} prerequisite needs {value['minimum']} mastered '{value['group']}' vocations but only {size} exist")
        for signal in vocation["discovery"].get("signals", []):
            if "quest_id" in signal and signal["quest_id"] not in quests:
                problems.append(f"{origin} discovery references unknown quest '{signal['quest_id']}'")
            if "item_id" in signal and signal["item_id"] not in items:
                problems.append(f"{origin} discovery references unknown item '{signal['item_id']}'")
            if "vocation_id" in signal and signal["vocation_id"] not in vocations:
                problems.append(f"{origin} discovery references unknown vocation '{signal['vocation_id']}'")
            if signal.get("rank", 1) > catalog["mastery"]["rank_count"]:
                problems.append(f"{origin} discovery uses rank {signal['rank']}, above rank_count")
    for quest in catalog["quests"]:
        if quest["encounter_id"] not in encounters:
            problems.append(f"quests: '{quest['id']}' references unknown encounter '{quest['encounter_id']}'")
        if quest["id"] not in used_quests:
            problems.append(f"quests: '{quest['id']}' is in no prerequisite")
    for item in catalog["items"]:
        if item["awarded_by_encounter"] not in encounters:
            problems.append(f"items: '{item['id']}' references unknown encounter '{item['awarded_by_encounter']}'")
        if item["id"] not in used_items:
            problems.append(f"items: '{item['id']}' is in no prerequisite")
    return problems


def _dependencies(catalog: Json) -> dict[str, list[str]]:
    """vocation id -> the vocations its prerequisite names with ``mastered`` (known ids only)."""
    known = {v["id"] for v in catalog["vocations"]}
    graph: dict[str, list[str]] = {}
    for vocation in catalog["vocations"]:
        leaves = list(_prerequisite_leaves(vocation.get("prerequisite", {})))
        graph[vocation["id"]] = sorted({value for kind, value in leaves if kind == "mastered" and value in known})
    return graph


def _cycle_problems(catalog: Json) -> list[str]:
    graph = _dependencies(catalog)
    state: dict[str, int] = {}  # 1 = on the current path, 2 = finished
    problems: list[str] = []

    def visit(node: str, path: list[str]) -> None:
        state[node] = 1
        for nxt in graph[node]:
            if state.get(nxt) == 1:
                cycle = path[path.index(nxt):] + [nxt]
                problems.append("prerequisite cycle: " + " -> ".join(cycle))
            elif nxt not in state:
                visit(nxt, path + [nxt])
        state[node] = 2

    for start in graph:
        if start not in state:
            visit(start, [start])
    return problems


def _evaluate(node: Json, catalog: Json, mastered: set[str], obtainable: set[str] | None) -> list[str]:
    """Why ``node`` cannot be satisfied (empty when it can).

    ``mastered`` is the set of vocations a hero may have mastered. ``obtainable`` is the set of
    encounters that can be played; ``None`` means every quest and item is assumed obtainable.
    """
    if "all" in node:
        return [reason for child in node["all"] for reason in _evaluate(child, catalog, mastered, obtainable)]
    if "any" in node:
        routes = [_evaluate(child, catalog, mastered, obtainable) for child in node["any"]]
        return [] if any(not route for route in routes) else [" or ".join("(" + "; ".join(route) + ")" for route in routes)]
    if "mastered" in node:
        if node["mastered"] in mastered:
            return []
        wave = _by_id(catalog["vocations"]).get(node["mastered"], {}).get("wave", "?")
        return [f"'{node['mastered']}' (wave {wave}) cannot be mastered yet"]
    if "mastered_count" in node:
        count = sum(1 for v in catalog["vocations"] if v["group"] == node["mastered_count"]["group"] and v["id"] in mastered)
        wanted = node["mastered_count"]["minimum"]
        return [] if count >= wanted else [f"only {count} of {wanted} '{node['mastered_count']['group']}' vocations can be mastered yet"]
    if "quest" in node:
        source = _by_id(catalog["quests"]).get(node["quest"], {}).get("encounter_id")
        kind, name = "quest", node["quest"]
    else:
        source = _by_id(catalog["items"]).get(node["item"], {}).get("awarded_by_encounter")
        kind, name = "item", node["item"]
    if obtainable is None or source in obtainable:
        return []
    return [f"{kind} '{name}' needs encounter '{source}', which is not shipped"]


def unlock_routes(catalog: Json) -> dict[str, dict[str, Json]]:
    """vocation id -> {route id -> the condition of that route}.

    The one rule for route ids, used by the saved data, the fixtures and later the engine: the
    alternatives of a prerequisite whose top level is ``any`` are the routes ``route_0``,
    ``route_1``, ... in catalog order; every other vocation has the single route ``route_0`` (an
    empty condition for a vocation with no prerequisite). A released catalog may add an alternative
    at the end and may never reorder or remove one, because saved unlocks record the route id.
    """
    routes: dict[str, dict[str, Json]] = {}
    for vocation in catalog["vocations"]:
        prerequisite: Json = vocation.get("prerequisite") or {}
        alternatives = prerequisite["any"] if "any" in prerequisite else [prerequisite]
        routes[vocation["id"]] = {f"route_{index}": alternative for index, alternative in enumerate(alternatives)}
    return routes


def unlockable(catalog: Json, max_wave: int | None = None) -> dict[str, list[str]]:
    """vocation id -> reasons it cannot be unlocked (empty when it can).

    With ``max_wave`` only vocations of that wave or earlier exist and only shipped encounters can
    be played; without it every vocation exists and every quest and item is assumed obtainable.
    """
    pool = [v for v in catalog["vocations"] if max_wave is None or v["wave"] <= max_wave]
    obtainable = None if max_wave is None else {e["id"] for e in catalog["encounters"] if e["source"] in PLAYABLE_SOURCES}
    open_ids = {v["id"] for v in pool if "prerequisite" not in v}
    while True:
        gained = {v["id"] for v in pool
                  if v["id"] not in open_ids and not _evaluate(v["prerequisite"], catalog, open_ids, obtainable)}
        if not gained:
            break
        open_ids |= gained
    return {v["id"]: [] if v["id"] in open_ids else _evaluate(v["prerequisite"], catalog, open_ids, obtainable) for v in pool}


# --------------------------------------------------------------------------------------------
# Mastery rewards
# --------------------------------------------------------------------------------------------


def _always_mastered(node: Json, catalog: Json, seen: frozenset[str] = frozenset()) -> set[str]:
    """Vocations a hero has certainly mastered once ``node`` holds, whichever route was taken."""
    if "all" in node:
        return set[str]().union(*(_always_mastered(child, catalog, seen) for child in node["all"]))
    if "any" in node:
        return set.intersection(*(_always_mastered(child, catalog, seen) for child in node["any"]))
    if "mastered" not in node or node["mastered"] in seen:
        return set()
    vocation = _by_id(catalog["vocations"]).get(node["mastered"])
    if vocation is None:
        return set()
    if "prerequisite" not in vocation:
        return {node["mastered"]}
    return {node["mastered"]} | _always_mastered(vocation["prerequisite"], catalog, seen | {node["mastered"]})


def _mastery_lines(catalog: Json) -> list[str]:
    lines = []
    mastery, caps = catalog["mastery"], catalog["stat_caps"]
    for table in ("rank_thresholds_by_group", "threat_min_by_group_and_rank"):
        for group, values in mastery[table].items():
            if len(values) != mastery["rank_count"]:
                lines.append(f"mastery: {table}/{group} has {len(values)} entries, not rank_count {mastery['rank_count']}")
    for group, values in mastery["rank_thresholds_by_group"].items():
        if values[0] != 0 or any(a >= b for a, b in zip(values, values[1:], strict=False)):
            lines.append(f"mastery: rank_thresholds_by_group/{group} must start at 0 and rise with every rank")
    vocations = _by_id(catalog["vocations"])
    for vocation in catalog["vocations"]:
        earlier = _always_mastered(vocation["prerequisite"], catalog) if "prerequisite" in vocation else set()
        for reward in vocation["mastery_rewards"]:
            stat, amount, cap = reward["stat"], reward["amount"], caps.get(reward["stat"], 0)
            if amount > cap:
                lines.append(f"vocations: '{vocation['id']}' mastery reward +{amount} {stat} exceeds the cap of {cap}")
                continue
            sources = sorted(other for other in earlier if any(r["stat"] == stat for r in vocations[other]["mastery_rewards"]))
            already = sum(r["amount"] for other in sources for r in vocations[other]["mastery_rewards"] if r["stat"] == stat)
            if already >= cap:
                lines.append(
                    f"{WARNING}REWARD_ALWAYS_CLAMPED {vocation['id']} +{amount} {stat}: its prerequisite already grants "
                    f"+{already} {stat} ({', '.join(sources)}) against a cap of {cap}, so this reward always clamps to zero"
                )
    return lines


# --------------------------------------------------------------------------------------------
# Encounters and training
# --------------------------------------------------------------------------------------------


#: Encounter sources a player can actually fight: a shipped battle, or one authored in the catalog.
PLAYABLE_SOURCES = ("shipped", "authored")


def _authored_problems(encounter: Json, shipped: Content) -> list[str]:
    """An authored encounter must have enemies for every party size, and obey the rules of a shipped battle.

    The shipped content loader does the checking: the encounter is put in place of battle 2 in a
    copy of the shipped documents, so an authored fight cannot hold anything a shipped one could not.
    """
    limits = shipped.balance["party"]
    sizes = [str(size) for size in range(limits["min_size"], limits["max_size"] + 1)]
    table = encounter.get("enemies", {})
    if sorted(table) != sorted(sizes):
        return [f"encounters: '{encounter['id']}' is authored but its enemies are not listed for exactly the party sizes {', '.join(sizes)}"]
    documents = copy.deepcopy(shipped.documents)
    for size, battles in documents["encounters"]["encounters"].items():
        next(battle for battle in battles if battle["battle"] == 2)["enemies"] = copy.deepcopy(table[size])
    try:
        build_content(documents)
    except ContentError as error:
        return [f"encounters: '{encounter['id']}': {problem.replace('encounters.json: ', '')}" for problem in error.problems]
    return []


def _encounter_problems(catalog: Json, shipped: Content) -> list[str]:
    problems = []
    claimed: dict[int, str] = {}
    for encounter in catalog["encounters"]:
        if encounter["source"] == "authored":
            problems += _authored_problems(encounter, shipped)
        if encounter["source"] != "shipped":
            continue
        battle = encounter["shipped_ref"]["battle"]
        missing = sorted(size for size, battles in shipped.encounters.items() if battle not in battles)
        if missing or not shipped.encounters:
            problems.append(f"encounters: '{encounter['id']}' is marked shipped but battle {battle} is not shipped for every party size")
        if battle in claimed:
            problems.append(
                f"encounters: '{encounter['id']}' is marked shipped as battle {battle}, which '{claimed[battle]}' already is; "
                "a shipped battle is one encounter with one threat rating"
            )
        claimed.setdefault(battle, encounter["id"])
    return problems


def available_threat(catalog: Json, pool: Iterable[str] | None = None) -> int:
    """The highest threat rating a player can meet; ``-1`` when no encounter is available.

    Owner decision of 2026-11-11 (fixture CE-36): the available encounters are the ones the catalog
    marks ``shipped``, at the ratings the catalog gives them. ``pool`` names the available
    encounters instead, for a check against a planned or a reduced set.
    """
    if pool is None:
        ratings = [e["threat_rating"] for e in catalog["encounters"] if e["source"] in PLAYABLE_SOURCES]
    else:
        wanted = set(pool)
        ratings = [e["threat_rating"] for e in catalog["encounters"] if e["id"] in wanted]
    return max(ratings, default=-1)


def training_dead_ends(catalog: Json, pool: Iterable[str] | None = None) -> list[tuple[Json, int]]:
    """``(vocation, rank)`` pairs where a hero at that rank has no available encounter that still awards mastery."""
    mastery = catalog["mastery"]
    best = available_threat(catalog, pool)
    dead = []
    for vocation in catalog["vocations"]:
        floors = mastery["threat_min_by_group_and_rank"][vocation["group"]]
        for rank in range(1, mastery["rank_count"]):  # the last rank is mastery: nothing left to train
            if floors[rank - 1] > best:
                dead.append((vocation, rank))
    return dead


def training_dead_end_details(catalog: Json, pool: Iterable[str] | None = None) -> list[Json]:
    """Each training dead end as the ``error_details`` of ``TRAINING_DEAD_END``, in catalog order."""
    best = available_threat(catalog, pool)
    floors = catalog["mastery"]["threat_min_by_group_and_rank"]
    return [
        {
            "vocation_id": vocation["id"],
            "vocation_group": vocation["group"],
            "rank": rank,
            "required_threat": floors[vocation["group"]][rank - 1],
            "max_available_threat": best,
        }
        for vocation, rank in training_dead_ends(catalog, pool)
    ]


def _release_lines(catalog: Json, wave: int | None) -> list[str]:
    """Training and unlock dead ends: problems for the waves being released, warnings otherwise."""
    lines = []
    for vocation, rank in training_dead_ends(catalog):
        line = f"TRAINING_DEAD_END {vocation['id']} rank {rank}"
        if wave is None:
            lines.append(WARNING + line)
        elif vocation["wave"] <= wave:
            lines.append(line)
    for vocation in _new_vocations(catalog):
        if wave is not None and vocation["wave"] > wave:
            continue
        # Released as wave N, a vocation must be unlockable from the vocations of waves 0..N alone.
        reasons = unlockable(catalog, vocation["wave"] if wave is None else wave)[vocation["id"]]
        if reasons:
            line = f"UNLOCK_DEAD_END {vocation['id']} wave {vocation['wave']}: {'; '.join(reasons)}"
            lines.append(line if wave is not None else WARNING + line)
    return lines


# --------------------------------------------------------------------------------------------
# Engine gaps
# --------------------------------------------------------------------------------------------


def _gap_problems(catalog: Json, package: Path | None = None) -> list[str]:
    problems = []
    package = package if package is not None else Path(battle_dice.__file__).resolve().parent
    # A standalone build carries the package as compiled modules, with no source files on disk.
    # Whether a named source file exists can only be checked where the sources are.
    sources_present = (package / "__init__.py").is_file()
    covered: set[str] = set()
    for gap in catalog["engine_gaps"]:
        origin = f"engine_gaps: '{gap['id']}'"
        if sources_present and not (package / gap["engine_file"].removeprefix("src/battle_dice/")).is_file():
            problems.append(f"{origin} names engine_file '{gap['engine_file']}', which does not exist")
        for reference in gap["used_by"]:
            kind, _, name = reference.partition(":")
            covered.add(reference)
            if kind == "face":
                if name not in catalog["face_library"]:
                    problems.append(f"{origin} is used_by unknown face '{name}'")
                continue
            entry = _by_id(catalog[GAP_KINDS[kind]]).get(name)
            if entry is None:
                problems.append(f"{origin} is used_by unknown {kind} '{name}'")
            elif entry["engine_support"] == "existing":
                problems.append(f"{origin} is used_by {kind} '{name}', which is marked existing")
    for kind, name in GAP_KINDS.items():
        for entry in catalog[name]:
            if entry["engine_support"] == "new" and f"{kind}:{entry['id']}" not in covered:
                problems.append(f"{name}: '{entry['id']}' is marked new but no engine_gaps entry says what the engine needs")
    return problems


# --------------------------------------------------------------------------------------------
# The shipped loader as referee
# --------------------------------------------------------------------------------------------


def loadable_vocations(catalog: Json, shipped: Content) -> list[Json]:
    """New vocations whose schedule, passive and reaction all have the shape rules 1.1.1 implement."""
    schedules, passives = _by_id(catalog["schedules"]), _by_id(catalog["passives"])
    ready = []
    for vocation in _new_vocations(catalog):
        schedule, passive = schedules.get(vocation["schedule_id"]), passives.get(vocation["passive_id"])
        reaction = _resolve_reaction(catalog, shipped, vocation["reaction_id"])
        parts = (schedule, passive, reaction)
        if all(part is not None and part["engine_support"] == "existing" for part in parts):
            ready.append(vocation)
    return ready


def loader_documents(catalog: Json, shipped: Content) -> Json:
    """The shipped documents plus what the catalog adds in shipped shape.

    Every new face and reaction is added. A vocation is added as a class, with its dice, when
    :func:`loadable_vocations` lists it; the others need a schedule, passive or reaction the
    shipped schema cannot express yet.
    """
    documents: Json = copy.deepcopy(shipped.documents)
    documents["dice"]["face_library"].update(copy.deepcopy(catalog["face_library"]))
    for reaction in catalog["reactions"]:
        documents["classes"]["reactions"][reaction["id"]] = {k: v for k, v in reaction.items() if k not in ("id", "engine_support")}
    schedules, passives = _by_id(catalog["schedules"]), _by_id(catalog["passives"])
    class_keys = ("name", "max_hp", "start_hp", "speed", "base_initiative", "max_mana", "start_mana", "max_corruption",
                  "start_corruption", "rerolls", "dice_capacity", "starting_dice", "bench_dice", "suggested_row")
    for vocation in loadable_vocations(catalog, shipped):
        passive = passives[vocation["passive_id"]]
        entry: Json = {key: copy.deepcopy(vocation[key]) for key in class_keys}
        entry["scheduling"] = shipped_scheduling(schedules[vocation["schedule_id"]])
        entry["passive"] = {k: v for k, v in passive.items() if k not in ("engine_support", "attack_tag_invariant")}
        entry["reaction"] = vocation["reaction_id"]
        documents["classes"]["classes"][vocation["id"]] = entry
        for die_id in vocation["starting_dice"] + vocation["bench_dice"]:
            if die_id in catalog["dice"]:
                documents["dice"]["dice"][die_id] = copy.deepcopy(catalog["dice"][die_id])
        for table in ("reforge_faces", "imbue_faces"):
            documents["upgrades"][table][vocation["id"]] = list(documents["upgrades"][table].get(vocation["upgrade_family"], []))
    return documents


def _loader_problems(catalog: Json, shipped: Content) -> list[str]:
    try:
        build_content(loader_documents(catalog, shipped))
    except ContentError as error:
        return [f"shipped loader: {problem}" for problem in error.problems]
    return []


# --------------------------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------------------------


def _baseline_problems(catalog: Json, shipped: Content) -> list[str]:
    problems = []
    baseline = catalog["baseline"]
    if baseline["content_version"] != shipped.content_version:
        problems.append(f"baseline: catalog was written against content {baseline['content_version']}, shipped is {shipped.content_version}")
    if baseline["rules_version"] != battle_dice.RULES_VERSION:
        problems.append(f"baseline: catalog was written against rules {baseline['rules_version']}, shipped is {battle_dice.RULES_VERSION}")
    return problems


def validate(catalog: dict[str, Any], shipped: Content, wave: int | None = None) -> list[str]:
    """Check ``catalog`` against its schema and the shipped content.

    Returns one line per finding. A line starting with ``warning:`` is not a problem; the catalog
    is valid when :func:`problems_only` of the result is empty. With ``wave`` the vocations of
    that wave and earlier must be trainable and unlockable on shipped content alone, and a dead
    end among them is a problem; without it every such dead end is listed as a warning.
    """
    schema = load_catalog_schema()
    lines = schema_problems(catalog, schema)
    if lines:
        return lines  # the cross-checks below rely on the shape the schema guarantees
    lines += vocabulary_problems(schema)
    lines += _baseline_problems(catalog, shipped)
    lines += _id_problems(catalog, shipped)
    lines += _face_problems(catalog)
    lines += _dice_problems(catalog, shipped)
    lines += _schedule_problems(catalog, schema)
    lines += _passive_problems(catalog, shipped, schema)
    lines += _reaction_problems(catalog)
    lines += _vocation_problems(catalog, shipped)
    lines += _reference_problems(catalog)
    lines += _encounter_problems(catalog, shipped)
    lines += _gap_problems(catalog)
    cycles = _cycle_problems(catalog)
    lines += cycles
    if not cycles:
        lines += [f"vocations: '{vocation_id}' is unreachable: {'; '.join(reasons)}"
                  for vocation_id, reasons in unlockable(catalog).items() if reasons]
    lines += _mastery_lines(catalog)
    if not problems_only(lines):
        # The loader's diagnostics assume resolved ids and legal faces, so it referees last.
        lines += _loader_problems(catalog, shipped)
    if not cycles:
        lines += _release_lines(catalog, wave)
    return lines


# --------------------------------------------------------------------------------------------
# Builds: what the rules engine is handed when the feature gate is on
# --------------------------------------------------------------------------------------------


def vocation_gaps(catalog: Json, vocation: Json) -> list[str]:
    """Ids of the ``engine_gaps`` entries this vocation's schedule, passive, reaction or dice faces need.

    The skill gap is left out: it concerns inherited skills, which no build carries yet.
    """
    needs = {f"schedule:{vocation['schedule_id']}", f"passive:{vocation['passive_id']}", f"reaction:{vocation['reaction_id']}"}
    for die_id in vocation["starting_dice"] + vocation["bench_dice"]:
        needs.update(f"face:{face_id}" for face_id in catalog["dice"].get(die_id, {}).get("faces", []))
    return [gap["id"] for gap in catalog["engine_gaps"] if needs & set(gap["used_by"])]


@dataclasses.dataclass(frozen=True)
class VocationCatalog:
    """The validated catalog as the engine uses it: a source of hero builds (``core.build.BuildSource``)."""

    version: str
    sha256: str
    builds: dict[str, HeroBuild]
    #: vocation id -> the engine gaps that keep it from being played.
    unsupported: dict[str, tuple[str, ...]]
    #: Every encounter the catalog lists: id -> (threat rating, source).
    encounter_list: dict[str, tuple[int, str]] = dataclasses.field(default_factory=dict)
    #: Authored encounters: id -> party size -> the enemies, in the shape of the shipped encounter table.
    authored: dict[str, dict[int, list[Json]]] = dataclasses.field(default_factory=dict)
    #: Shipped battle number -> the encounter id and threat rating the catalog gives it.
    shipped_battles: dict[int, tuple[str, int]] = dataclasses.field(default_factory=dict)

    def known(self, vocation_id: str) -> bool:
        return vocation_id in self.builds or vocation_id in self.unsupported

    # -- core.build.EncounterSource -----------------------------------------------------------

    def has_encounter(self, encounter_id: str) -> bool:
        return encounter_id in self.encounter_list

    def encounter(self, encounter_id: str, party_size: int) -> list[Json]:
        table = self.authored.get(encounter_id)
        if table is None:
            source = self.encounter_list[encounter_id][1]
            reason = "it is a shipped battle of every run" if source == "shipped" else "its enemies have not been authored"
            raise EncounterNotPlayable(f"The encounter '{encounter_id}' cannot be added to a run: {reason}.")
        if party_size not in table:
            raise EncounterNotPlayable(f"The encounter '{encounter_id}' has no enemies for a party of {party_size}.")
        return copy.deepcopy(table[party_size])

    def threat_rating(self, encounter_id: str) -> int:
        return self.encounter_list[encounter_id][0]

    def build(self, vocation_id: str) -> HeroBuild:
        if vocation_id in self.unsupported:
            gaps = ", ".join(self.unsupported[vocation_id])
            raise BuildNotSupported(f"The vocation '{vocation_id}' cannot be played yet: the rules still lack {gaps}.")
        return self.builds[vocation_id]


def load_vocation_catalog(content: Content, path: Path = CATALOG_PATH) -> VocationCatalog:
    """Validate the catalog against ``content`` and resolve every playable vocation to its build.

    Raises :class:`ContentError` when the catalog has a problem (warnings do not count). Novice
    builds are the shipped classes themselves. A new vocation is built by the game's own content
    loader from :func:`loader_documents`, so it obeys every rule shipped content obeys.
    """
    catalog = load_catalog(path)
    problems = problems_only(validate(catalog, content))
    if problems:
        raise ContentError([f"vocation catalog: {problem}" for problem in problems])
    extended = build_content(loader_documents(catalog, content))
    loadable = {vocation["id"] for vocation in loadable_vocations(catalog, content)}
    builds: dict[str, HeroBuild] = {}
    unsupported: dict[str, tuple[str, ...]] = {}
    for vocation in catalog["vocations"]:
        vocation_id = vocation["id"]
        if vocation["group"] == NOVICE:
            builds[vocation_id] = build_from_class(content, vocation["class_id"])
            continue
        gaps = vocation_gaps(catalog, vocation)
        if gaps or vocation_id not in loadable:
            unsupported[vocation_id] = tuple(gaps) or ("a schedule, passive or reaction the rules do not implement",)
            continue
        own_dice = vocation["starting_dice"] + vocation["bench_dice"]
        builds[vocation_id] = dataclasses.replace(
            build_from_class(extended, vocation_id),
            upgrade_family=vocation["upgrade_family"],
            dice={die_id: extended.dice[die_id] for die_id in own_dice},
        )
    digest = hashlib.sha256(canonical_json(catalog).encode("ascii")).hexdigest()
    listed = {e["id"]: (int(e["threat_rating"]), str(e["source"])) for e in catalog["encounters"]}
    authored = {e["id"]: {int(size): enemies for size, enemies in e["enemies"].items()}
                for e in catalog["encounters"] if e["source"] == "authored"}
    shipped_battles = {int(e["shipped_ref"]["battle"]): (e["id"], int(e["threat_rating"]))
                       for e in catalog["encounters"] if e["source"] == "shipped"}
    return VocationCatalog(catalog["catalog_version"], digest, builds, unsupported, listed, authored, shipped_battles)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH, help="catalog file (default: the repository's)")
    parser.add_argument("--wave", type=int, default=None,
                        help="require waves 0..N to be trainable and unlockable on shipped content; without it, dead ends are warnings")
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(args.catalog)
    except (OSError, ValueError) as error:
        print(f"{args.catalog}: {error}")
        return 1
    lines = validate(catalog, load_content(), args.wave)
    for line in warnings_only(lines) + problems_only(lines):
        print(line)
    if problems_only(lines):
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
