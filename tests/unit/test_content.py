"""Content contracts: exact authored fixtures and validation diagnostics (AC-02, AC-03, AC-14)."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence

import pytest

from battle_dice.content.loader import ContentError, build_content, load_documents
from battle_dice.core import progression
from battle_dice.core.view import describe_face, die_view
from tests.conftest import content_with, mechanics_content

# (category, power, mana cost, action speed, can_revive) for each physical face, in PRD order.
EXPECTED_DICE: Mapping[str, Sequence[tuple[object, ...]]] = {
    "iron_d6": [("attack", 3, 0, 1, False)] * 2 + [("defense", 3, 0, 2, False)] * 2
    + [("healing", 2, 1, 1, True), ("blank", 0, 0, None, False)],
    "oath_d4": [("attack", 2, 0, 1, False)] + [("defense", 2, 0, 2, False)] * 2 + [("resource", 1, 0, 3, False)],
    "arcane_d6": [("attack", 3, 1, 1, False)] * 2
    + [("healing", 3, 2, 1, True), ("status", 1, 0, 2, False), ("resource", 2, 0, 3, False), ("blank", 0, 0, None, False)],
    "focus_d4": [("resource", 2, 0, 3, False)] * 2 + [("defense", 2, 0, 2, False), ("blank", 0, 0, None, False)],
    "striker_d8": [("attack", 2, 0, 1, False)] * 3 + [("status", 1, 0, 2, False)] * 3
    + [("resource", 1, 0, 3, False), ("blank", 0, 0, None, False)],
    "tools_d4": [("attack", 1, 0, 1, False)] * 2 + [("defense", 2, 0, 2, False), ("blank", 0, 0, None, False)],
    "vanguard_d4": [("attack", 3, 0, 1, False), ("attack", 2, 0, 1, False), ("attack", 2, 0, 1, False), ("blank", 0, 0, None, False)],
    "spark_d4": [("resource", 1, 0, 3, False)] * 2 + [("attack", 1, 0, 1, False), ("blank", 0, 0, None, False)],
    "venom_d4": [("status", 1, 0, 2, False), ("attack", 1, 0, 1, False), ("attack", 1, 0, 1, False), ("blank", 0, 0, None, False)],
}

EXPECTED_CLASSES = {
    #             hp  start speed init mana start corr start rerolls dice row
    "squire": (14, 14, 7, 5, 3, 2, 6, 0, 2, ["iron_d6", "oath_d4"], "front", 1),
    "apprentice": (12, 12, 9, 4, 6, 3, 6, 1, 2, ["arcane_d6", "focus_d4"], "back", 2),
    "scout": (9, 9, 10, 6, 4, 2, 6, 0, 2, ["striker_d8", "tools_d4"], "back", 2),
}

# Shipped encounter table (content 1.3.0, owner-approved class balance change of 2026-11-10).
# party size -> battle -> [(archetype, max HP, speed, damaging action, its power)] in spawn-ID order.
# Base stats in enemies.json: goblin 6 HP / speed 10 / Slash 2; hex adept 7 / 8 / Shadow Bolt 3;
# captain 12 / 9 / Strike 3. Damage (+1) and speed (+2 for sizes 3-5) are as in content 1.2.0; enemy
# health was raised per party size in 1.3.0, together with the class changes (decision log D-21).
G, H, C = "goblin", "hex_adept", "captain"
EXPECTED_ENCOUNTERS = {
    1: {1: [(G, 12, 10, "slash", 3)],
        2: [(C, 18, 9, "strike", 3)]},
    2: {1: [(G, 14, 10, "slash", 3), (H, 18, 8, "shadow_bolt", 4)],
        2: [(C, 25, 9, "strike", 4), (G, 14, 10, "slash", 3)]},
    3: {1: [(G, 10, 12, "slash", 3), (G, 10, 12, "slash", 3), (H, 13, 10, "shadow_bolt", 4)],
        2: [(C, 22, 11, "strike", 4), (G, 10, 12, "slash", 3), (H, 13, 10, "shadow_bolt", 4)]},
    4: {1: [(G, 10, 12, "slash", 3), (G, 10, 12, "slash", 3), (H, 12, 10, "shadow_bolt", 4), (H, 12, 10, "shadow_bolt", 4)],
        2: [(C, 24, 11, "strike", 4), (G, 10, 12, "slash", 3), (G, 10, 12, "slash", 3), (H, 12, 10, "shadow_bolt", 4)]},
    5: {1: [(G, 11, 12, "slash", 3)] * 3 + [(H, 13, 10, "shadow_bolt", 4)] * 2,
        2: [(C, 29, 11, "strike", 4), (G, 11, 12, "slash", 3), (G, 11, 12, "slash", 3), (H, 13, 10, "shadow_bolt", 4),
            (H, 13, 10, "shadow_bolt", 4)]},
}


def shipped_roster(content, size, battle):
    """(archetype, max HP, speed, damaging action, power) for each enemy the shipped content spawns."""
    rows = []
    for enemy in progression.make_enemies(content, size, battle):
        action_id = {"goblin": "slash", "hex_adept": "shadow_bolt", "captain": "strike"}[enemy.archetype_id]
        base = content.enemy_action(enemy.archetype_id, action_id)
        power = enemy.action_overrides.get(action_id, {}).get("power", base.power)
        rows.append((enemy.archetype_id, enemy.max_hp, enemy.speed, action_id, power))
    return rows


@pytest.mark.parametrize("die_id", sorted(EXPECTED_DICE))
def test_die_faces_match_the_authored_tables(content, die_id):
    die = content.die(die_id)
    assert die.size == len(die.faces) == len(EXPECTED_DICE[die_id])
    assert die.size in (4, 6, 8)
    actual = [(f.category, f.power, f.mana_cost, f.action_speed, f.can_revive) for f in die.faces]
    assert actual == EXPECTED_DICE[die_id]


def test_specific_face_rules_text(content):
    iron = content.die("iron_d6")
    assert describe_face(iron.faces[0]) == "3 melee damage"
    assert describe_face(iron.faces[4]) == "heal 2 (revives to 2 HP); costs 1 mana"
    assert describe_face(iron.faces[5]) == "No action"
    arcane = content.die("arcane_d6")
    assert describe_face(arcane.faces[0]) == "3 ranged damage; +1 corruption (self); costs 1 mana"
    assert describe_face(arcane.faces[3]) == "Weaken 1 for 2 activations"
    assert describe_face(arcane.faces[4]) == "-2 corruption (self)"
    assert describe_face(content.die("striker_d8").faces[3]) == "Poison 1 for 2 activations"
    assert describe_face(content.die("vanguard_d4").faces[1]) == "2 melee damage"
    # Ordinary healing is no longer on a shipped die (content 1.3.1); the frozen fixture dice keep Tend.
    assert describe_face(mechanics_content().die("bulwark_d4").faces[2]) == "heal 1 (cannot revive)"
    assert describe_face(content.die("spark_d4").faces[2]) == "1 ranged damage; +1 corruption (self)"


def test_only_rally_and_mend_can_revive_in_starting_fixtures(content):
    revivers = sorted(
        {face.name for die in content.dice.values() for face in die.faces if face.can_revive}
    )
    assert revivers == ["Mend", "Rally"]
    assert not any(f.can_revive for f in content.upgrade_faces.values())


@pytest.mark.parametrize("class_id", sorted(EXPECTED_CLASSES))
def test_class_attributes(content, class_id):
    cls = content.class_def(class_id)
    expected = EXPECTED_CLASSES[class_id]
    actual = (
        cls["max_hp"], cls["start_hp"], cls["speed"], cls["base_initiative"], cls["max_mana"], cls["start_mana"],
        cls["max_corruption"], cls["start_corruption"], cls["rerolls"], cls["starting_dice"], cls["suggested_row"],
        cls["scheduling"]["max_actions"],
    )
    assert actual == expected
    assert cls["dice_capacity"] == 2
    hero = progression.make_hero(content, "h01", class_id, cls["suggested_row"])
    assert (hero.hp, hero.mana, hero.corruption, hero.shields, hero.gauge) == (expected[1], expected[5], expected[7], 0, 0)


def test_scheduling_profiles_are_distinct(content):
    policies = {cid: (c["scheduling"]["policy"], c["scheduling"].get("first_category")) for cid, c in content.classes.items()}
    assert policies == {"squire": ("single", None), "apprentice": ("sequence", "resource"), "scout": ("sequence", "status")}
    assert content.classes["apprentice"]["scheduling"]["second_categories"] == ["attack", "defense", "healing", "status"]
    assert content.classes["scout"]["scheduling"]["second_categories"] == ["attack"]


def test_enemy_archetypes(content):
    stats = {k: (v["row"], v["max_hp"], v["speed"], v["base_initiative"]) for k, v in content.enemies.items()}
    assert stats == {"goblin": ("front", 6, 10, 4), "hex_adept": ("back", 7, 8, 3), "captain": ("front", 12, 9, 5)}
    weights = {k: {a: f.weight for a, f in actions.items()} for k, actions in content.enemy_actions.items()}
    assert weights == {
        "goblin": {"dirty_trick": 1, "slash": 3},
        "hex_adept": {"corrupt_mark": 1, "poison_dart": 1, "shadow_bolt": 2},
        "captain": {"blight_wave": 1, "corrupt_mark": 1, "strike": 3, "war_cry": 1},
    }
    ranges = {k: {a: f.range_type for a, f in actions.items()} for k, actions in content.enemy_actions.items()}
    assert ranges == {
        "goblin": {"dirty_trick": "ranged", "slash": "melee"},
        "hex_adept": {"corrupt_mark": "ranged", "poison_dart": "ranged", "shadow_bolt": "ranged"},
        "captain": {"blight_wave": "ranged", "corrupt_mark": "ranged", "strike": "melee", "war_cry": "self"},
    }
    powers = {k: {a: f.power for a, f in actions.items()} for k, actions in content.enemy_actions.items()}
    assert powers["goblin"]["slash"] == 2 and powers["hex_adept"]["shadow_bolt"] == 3
    assert powers["captain"] == {"blight_wave": 1, "corrupt_mark": 1, "strike": 3, "war_cry": 2}
    for archetype in ("goblin", "hex_adept"):
        for face in content.enemy_actions[archetype].values():
            assert {"basic", "interruptible", "hostile"} <= set(face.tags)
    captain = content.enemy_actions["captain"]
    for action_id in ("strike", "blight_wave", "corrupt_mark"):
        assert {"elite_resistant", "interruptible", "hostile"} <= set(captain[action_id].tags)
    assert "unreactable" in captain["war_cry"].tags and "hostile" not in captain["war_cry"].tags


@pytest.mark.parametrize("size", sorted(EXPECTED_ENCOUNTERS))
def test_encounter_scaling_table(content, size):
    for battle in (1, 2):
        enemies = progression.make_enemies(content, size, battle)
        assert shipped_roster(content, size, battle) == EXPECTED_ENCOUNTERS[size][battle]
        assert [e.id for e in enemies] == [f"b{battle}_e{n:02d}" for n in range(1, len(enemies) + 1)]
        assert all(e.hp == e.max_hp and e.gauge == 0 and e.shields == 0 for e in enemies)
        assert all(e.row == content.enemies[e.archetype_id]["row"] for e in enemies)


def test_balance_changes_live_only_in_the_encounter_table(content):
    # Base archetype stats stay as authored in the PRD; the per-size table carries every adjustment.
    base = {k: (v["max_hp"], v["speed"]) for k, v in content.enemies.items()}
    assert base == {"goblin": (6, 10), "hex_adept": (7, 8), "captain": (12, 9)}
    assert content.balance["ai"] == {"priority_lethal": 100, "priority_setup": 20, "priority_default": 10}
    assert content.reactions["disrupt"]["mana_cost"] == 2
    # Only damaging actions are raised; setup and area actions keep their authored power.
    for size in EXPECTED_ENCOUNTERS:
        for battle in (1, 2):
            for enemy in progression.make_enemies(content, size, battle):
                assert set(enemy.action_overrides) <= {"slash", "shadow_bolt", "strike"}


def test_die_view_shows_every_face_frequency_and_probability(content):
    view = die_view(content.die("iron_d6"))
    assert len(view["faces"]) == 6
    by_name = {g["face"]["name"]: g for g in view["groups"]}
    assert by_name["Guard"]["count"] == 2 and by_name["Guard"]["probability"] == "1/3 (33.3%)"
    assert by_name["Rally"]["probability"] == "1/6 (16.7%)"
    assert sum(g["count"] for g in view["groups"]) == 6
    striker = die_view(content.die("striker_d8"))
    assert {g["face"]["name"]: g["probability"] for g in striker["groups"]}["Shot"] == "3/8 (37.5%)"
    for die in content.dice.values():
        groups = die_view(die)["groups"]
        assert sum(g["count"] for g in groups) == die.size
        assert sorted(n for g in groups for n in g["face_numbers"]) == list(range(1, die.size + 1))


def test_content_hash_is_stable_and_sensitive(content):
    again = build_content(load_documents())
    assert again.content_hash == content.content_hash
    # Compare against the same documents with one value changed. (content_with builds from the
    # frozen-encounter test documents, whose hash differs from the shipped one whatever is changed.)
    documents = load_documents()
    documents["balance"]["shield"]["cap"] = 11
    assert build_content(documents).content_hash != content.content_hash
    reverted = load_documents()
    assert build_content(reverted).content_hash == content.content_hash


def _expect_error(mutate, fragment):
    with pytest.raises(ContentError) as caught:
        content_with(mutate)
    assert any(fragment in problem for problem in caught.value.problems), caught.value.problems


def test_invalid_content_is_rejected_with_clear_diagnostics():
    _expect_error(lambda d: d["dice"]["dice"]["iron_d6"]["faces"].pop(), "declares size 6 but has 5 faces")
    _expect_error(lambda d: d["dice"]["dice"]["iron_d6"]["faces"].__setitem__(0, "nope"), "unknown face 'nope'")
    _expect_error(lambda d: d["dice"]["dice"]["iron_d6"].update(size=10), "dice.json")
    _expect_error(lambda d: d["classes"]["classes"]["squire"].update(starting_dice=["iron_d6", "focus_d4"]), "cannot use die 'focus_d4'")
    _expect_error(lambda d: d["classes"]["classes"]["squire"].update(starting_dice=["iron_d6"]), "exactly dice_capacity")
    _expect_error(lambda d: d["classes"]["classes"]["squire"].update(max_hp="14"), "classes.json")
    _expect_error(lambda d: d["dice"]["face_library"]["sq_strike_2"].update(can_revive=True), "not a Healing face")
    _expect_error(lambda d: d["dice"]["face_library"]["blank"].update(action_speed=1), "blank face")
    _expect_error(lambda d: d["encounters"]["encounters"].pop("4"), "no encounter set for party size 4")
    _expect_error(lambda d: d["encounters"]["encounters"]["1"][0]["enemies"][0].update(archetype="dragon"), "unknown enemy 'dragon'")
    _expect_error(lambda d: d["enemies"]["enemies"]["goblin"]["actions"]["slash"].update(weight=-1), "enemies.json")
    _expect_error(lambda d: d["upgrades"]["reforge_faces"].pop("scout"), "no entry for class 'scout'")
    _expect_error(lambda d: d["enemies"].update(content_version="9.9.9"), "content_version differs")
    _expect_error(lambda d: d["balance"]["upgrades"].update(mandatory_upgrades_per_run=2), "balance.json")


def test_missing_document_is_reported():
    documents = copy.deepcopy(load_documents())
    del documents["dice"]
    with pytest.raises(ContentError) as caught:
        build_content(documents)
    assert "dice.json: document is missing" in caught.value.problems


def test_versions_and_owner_rule_changes_of_1_1_0(content):
    from battle_dice import RULES_VERSION

    assert RULES_VERSION == "1.1.1" and content.content_version == "1.3.1"
    assert {doc["content_version"] for doc in content.documents.values()} == {"1.3.1"}
    assert content.classes["squire"]["passive"]["type"] == "defense_die_bonus"
    assert content.balance["upgrades"]["max_swaps_per_hero"] == 1
    assert "max_swaps_per_run" not in content.balance["upgrades"]
