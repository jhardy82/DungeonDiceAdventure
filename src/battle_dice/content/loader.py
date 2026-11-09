"""Content layer: load, schema-validate and cross-check the versioned fixtures.

Invalid content is rejected with clear diagnostics *before* a run can start (section 6.2,
"Atomicity"). The loaded :class:`Content` object is immutable by convention and is never copied
with the authoritative state.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema

from battle_dice.core.models import CATEGORY_BLANK, CATEGORY_HEALING, DieDefinition, FaceDefinition

DOCUMENTS = ("balance", "classes", "dice", "enemies", "encounters", "upgrades")
_SCHEMA_DEFS = {
    "balance": "balance_file",
    "classes": "classes_file",
    "dice": "dice_file",
    "enemies": "enemies_file",
    "encounters": "encounters_file",
    "upgrades": "upgrades_file",
}


class ContentError(ValueError):
    """Raised when content fails schema or cross-reference validation."""

    def __init__(self, problems: list[str]):
        self.problems = list(problems)
        super().__init__("Invalid content:\n  - " + "\n  - ".join(self.problems))


def _read_packaged(folder: str, name: str) -> Any:
    text = resources.files("battle_dice.content").joinpath(folder, name).read_text(encoding="utf-8")
    return json.loads(text)


def load_schema() -> dict[str, Any]:
    return _read_packaged("schemas", "battle_dice.schema.json")


def load_documents(directory: str | Path | None = None) -> dict[str, Any]:
    """Read the raw JSON documents, from the packaged fixtures or from ``directory``."""
    documents: dict[str, Any] = {}
    for name in DOCUMENTS:
        if directory is None:
            documents[name] = _read_packaged("data", f"{name}.json")
        else:
            documents[name] = json.loads((Path(directory) / f"{name}.json").read_text(encoding="utf-8"))
    return documents


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _make_face(face_id: str, raw: dict[str, Any]) -> FaceDefinition:
    return FaceDefinition(
        id=face_id,
        name=raw["name"],
        category=raw["category"],
        power=raw["power"],
        target_scope=raw["target_scope"],
        range_type=raw["range_type"],
        action_speed=raw["action_speed"],
        mana_cost=raw["mana_cost"],
        effects=copy.deepcopy(raw["effects"]),
        can_revive=raw["can_revive"],
        tags=list(raw["tags"]),
        weight=raw.get("weight", 0),
        random_target=raw.get("random_target", False),
    )


@dataclass
class Content:
    """Validated, cross-referenced game content."""

    content_version: str
    content_hash: str
    balance: dict[str, Any]
    classes: dict[str, dict[str, Any]]
    reactions: dict[str, dict[str, Any]]
    dice: dict[str, DieDefinition]
    enemies: dict[str, dict[str, Any]]
    enemy_actions: dict[str, dict[str, FaceDefinition]]
    encounters: dict[int, dict[int, list[dict[str, Any]]]]
    upgrades: dict[str, Any]
    upgrade_faces: dict[str, FaceDefinition]
    documents: dict[str, Any] = field(repr=False, default_factory=dict)

    # -- lookups -----------------------------------------------------------------------------

    def class_def(self, class_id: str) -> dict[str, Any]:
        return self.classes[class_id]

    def die(self, die_id: str) -> DieDefinition:
        return self.dice[die_id]

    def enemy_action(self, archetype_id: str, action_id: str) -> FaceDefinition:
        return self.enemy_actions[archetype_id][action_id]

    def encounter(self, party_size: int, battle: int) -> list[dict[str, Any]]:
        return self.encounters[party_size][battle]

    def status_cap(self, kind: str) -> int:
        return int(self.balance["statuses"][kind]["stack_cap"])


def build_content(documents: dict[str, Any]) -> Content:
    """Validate raw documents and build a :class:`Content`. Raises :class:`ContentError`."""
    problems: list[str] = []
    schema = load_schema()

    for name in DOCUMENTS:
        if name not in documents:
            problems.append(f"{name}.json: document is missing")
            continue
        validator = jsonschema.Draft202012Validator({**schema, "$ref": f"#/$defs/{_SCHEMA_DEFS[name]}"})
        for error in sorted(validator.iter_errors(documents[name]), key=lambda e: list(map(str, e.path))):
            location = "/".join(str(p) for p in error.path) or "<root>"
            problems.append(f"{name}.json: {location}: {error.message}")
    if problems:
        raise ContentError(problems)

    versions = {name: documents[name]["content_version"] for name in DOCUMENTS}
    if len(set(versions.values())) != 1:
        problems.append(f"content_version differs between documents: {versions}")

    balance = documents["balance"]
    classes = documents["classes"]["classes"]
    reactions = documents["classes"]["reactions"]
    face_library = documents["dice"]["face_library"]
    upgrades = documents["upgrades"]

    # -- dice --------------------------------------------------------------------------------
    def check_face(origin: str, face_id: str, raw: dict[str, Any]) -> None:
        blank = raw["category"] == CATEGORY_BLANK
        if blank and (raw["effects"] or raw["action_speed"] is not None or raw["target_scope"] != "none"):
            problems.append(f"{origin}: blank face '{face_id}' must have no effects, speed or target")
        if not blank and (not raw["effects"] or raw["action_speed"] is None):
            problems.append(f"{origin}: executable face '{face_id}' needs effects and an action_speed")
        if raw["can_revive"] and raw["category"] != CATEGORY_HEALING:
            problems.append(f"{origin}: face '{face_id}' is can_revive but is not a Healing face")
        if raw["can_revive"] and not any(e["type"] == "heal" for e in raw["effects"]):
            problems.append(f"{origin}: face '{face_id}' is can_revive but has no heal effect")

    for face_id, raw in face_library.items():
        check_face("dice.json", face_id, raw)

    dice: dict[str, DieDefinition] = {}
    for die_id, raw in documents["dice"]["dice"].items():
        if len(raw["faces"]) != raw["size"]:
            problems.append(f"dice.json: die '{die_id}' declares size {raw['size']} but has {len(raw['faces'])} faces")
        if raw["affinity_class"] not in classes:
            problems.append(f"dice.json: die '{die_id}' has unknown affinity_class '{raw['affinity_class']}'")
        faces = []
        for index, face_ref in enumerate(raw["faces"]):
            if face_ref not in face_library:
                problems.append(f"dice.json: die '{die_id}' face {index + 1} references unknown face '{face_ref}'")
                continue
            faces.append(_make_face(face_ref, face_library[face_ref]))
        dice[die_id] = DieDefinition(
            id=die_id,
            name=raw["name"],
            affinity_class=raw["affinity_class"],
            size=raw["size"],
            faces=faces,
            definition_version=raw["definition_version"],
            role=raw["role"],
        )

    # -- classes -----------------------------------------------------------------------------
    for class_id, raw in classes.items():
        origin = f"classes.json: class '{class_id}'"
        if len(raw["starting_dice"]) != raw["dice_capacity"]:
            problems.append(f"{origin} must start with exactly dice_capacity ({raw['dice_capacity']}) dice")
        for key, role in (("starting_dice", "starting"), ("bench_dice", "sidegrade")):
            for die_id in raw[key]:
                die = dice.get(die_id)
                if die is None:
                    problems.append(f"{origin} references unknown die '{die_id}'")
                elif die.affinity_class != class_id:
                    problems.append(f"{origin} cannot use die '{die_id}' of class '{die.affinity_class}'")
                elif die.role != role:
                    problems.append(f"{origin} lists die '{die_id}' under {key} but its role is '{die.role}'")
        if raw["start_hp"] > raw["max_hp"] or raw["start_mana"] > raw["max_mana"]:
            problems.append(f"{origin} has a starting value above its maximum")
        if raw["start_corruption"] > raw["max_corruption"]:
            problems.append(f"{origin} starting corruption exceeds its maximum")
        if raw["reaction"] not in reactions:
            problems.append(f"{origin} references unknown reaction '{raw['reaction']}'")
        if raw["scheduling"]["policy"] == "single" and raw["scheduling"]["max_actions"] != 1:
            problems.append(f"{origin} uses the single policy but max_actions is not 1")
        if raw["passive"]["type"] == "spell_damage_at_corruption" and "threshold" not in raw["passive"]:
            problems.append(f"{origin} passive needs a threshold")

    # -- enemies -----------------------------------------------------------------------------
    enemies = documents["enemies"]["enemies"]
    enemy_actions: dict[str, dict[str, FaceDefinition]] = {}
    for archetype_id, raw in enemies.items():
        enemy_actions[archetype_id] = {}
        for action_id in sorted(raw["actions"]):
            action = raw["actions"][action_id]
            check_face(f"enemies.json: enemy '{archetype_id}'", action_id, action)
            if action["category"] == CATEGORY_BLANK:
                problems.append(f"enemies.json: enemy '{archetype_id}' action '{action_id}' cannot be blank")
            enemy_actions[archetype_id][action_id] = _make_face(action_id, action)
        if not any(a["weight"] > 0 for a in raw["actions"].values()):
            problems.append(f"enemies.json: enemy '{archetype_id}' has no action with a positive weight")

    # -- encounters --------------------------------------------------------------------------
    encounters: dict[int, dict[int, list[dict[str, Any]]]] = {}
    raw_encounters = documents["encounters"]["encounters"]
    for size in range(balance["party"]["min_size"], balance["party"]["max_size"] + 1):
        if str(size) not in raw_encounters:
            problems.append(f"encounters.json: no encounter set for party size {size}")
    for size_key, battles in raw_encounters.items():
        encounters[int(size_key)] = {}
        if sorted(b["battle"] for b in battles) != [1, 2]:
            problems.append(f"encounters.json: party size {size_key} must define battles 1 and 2 exactly once")
        for battle in battles:
            for entry in battle["enemies"]:
                archetype = entry["archetype"]
                if archetype not in enemies:
                    problems.append(f"encounters.json: party size {size_key} uses unknown enemy '{archetype}'")
                    continue
                for action_id in entry.get("overrides", {}).get("actions", {}):
                    if action_id not in enemies[archetype]["actions"]:
                        problems.append(
                            f"encounters.json: party size {size_key} overrides unknown action "
                            f"'{action_id}' of enemy '{archetype}'"
                        )
            encounters[int(size_key)][battle["battle"]] = copy.deepcopy(battle["enemies"])

    # -- upgrades ----------------------------------------------------------------------------
    upgrade_faces: dict[str, FaceDefinition] = {}
    for face_id, raw in upgrades["face_library"].items():
        check_face("upgrades.json", face_id, raw)
        if raw["category"] == CATEGORY_BLANK:
            problems.append(f"upgrades.json: catalog face '{face_id}' cannot be blank")
        if raw["power"] > balance["upgrades"]["face_power_cap"]:
            problems.append(f"upgrades.json: catalog face '{face_id}' exceeds the face power cap")
        upgrade_faces[face_id] = _make_face(face_id, raw)
    for key in ("reforge_faces", "imbue_faces"):
        for class_id in classes:
            if class_id not in upgrades[key]:
                problems.append(f"upgrades.json: {key} has no entry for class '{class_id}'")
        for class_id, face_ids in upgrades[key].items():
            if class_id not in classes:
                problems.append(f"upgrades.json: {key} lists unknown class '{class_id}'")
            for face_id in face_ids:
                if face_id not in upgrades["face_library"]:
                    problems.append(f"upgrades.json: {key}/{class_id} references unknown face '{face_id}'")

    if problems:
        raise ContentError(problems)

    digest = hashlib.sha256(canonical_json({name: documents[name] for name in DOCUMENTS}).encode()).hexdigest()
    return Content(
        content_version=balance["content_version"],
        content_hash=digest,
        balance=copy.deepcopy(balance),
        classes=copy.deepcopy(classes),
        reactions=copy.deepcopy(reactions),
        dice=dice,
        enemies=copy.deepcopy(enemies),
        enemy_actions=enemy_actions,
        encounters=encounters,
        upgrades=copy.deepcopy(upgrades),
        upgrade_faces=upgrade_faces,
        documents=copy.deepcopy(documents),
    )


def load_content(directory: str | Path | None = None) -> Content:
    """Load and validate content from the packaged fixtures (default) or a directory."""
    return build_content(load_documents(directory))
