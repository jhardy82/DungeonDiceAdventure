"""The class-evolution vocation catalog (v0.2): a specification, not loaded by the game.

These tests keep the catalog honest against the shipped content: it validates, it cannot restate
or drift from the novice classes, its "existing" claims load in the shipped loader, and the
validator rejects each kind of mistake the v0.1 schema let through.
"""

from __future__ import annotations

import copy
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from battle_dice.content.loader import Content, ContentError, build_content, load_content
from battle_dice.core.build import EncounterNotPlayable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from class_evolution import validate_catalog as vc  # noqa: E402

CATALOG_PATH = ROOT / "src" / "battle_dice" / "content" / "class_evolution" / "vocation_catalog.json"
SCHEMA_PATH = CATALOG_PATH.with_name("vocation_catalog.schema.json")

Json = dict[str, Any]

#: Ranks at which a hero has no shipped encounter left that awards mastery (shipped threat tops out at 3).
#: With the authored threat-4 encounter (Phase 4, step B) the highest available threat is 4. What still
#: cannot be trained needs threat 5: the upper ranks of the capstones and of the Dragon Knight.
TRAINING_DEAD_ENDS: dict[str, list[int]] = {
    "champion": [4, 5, 6, 7], "archmage": [4, 5, 6, 7],
    "hero": [4, 5, 6, 7], "dragon_knight": [4, 5, 6, 7],
}
#: The same without the threat-4 encounter, as it was before step B (highest threat 3).
DEAD_ENDS_AT_THREAT_3: dict[str, list[int]] = {
    "guardian": [7],
    "spellblade": [7], "ranger": [7],
    "duelist": [7], "arcanist": [7], "shadowbinder": [7],
    "champion": [1, 2, 3, 4, 5, 6, 7], "archmage": [1, 2, 3, 4, 5, 6, 7],
    "hero": [1, 2, 3, 4, 5, 6, 7], "trickster": [6, 7], "dragon_knight": [1, 2, 3, 4, 5, 6, 7],
}
#: Release order: every vocation comes after the vocations its prerequisite names.
WAVES = {0: ["squire", "apprentice", "scout"], 1: ["guardian"], 2: ["spellblade", "ranger"],
         3: ["duelist", "arcanist", "shadowbinder"], 4: ["champion", "archmage"], 5: ["hero", "trickster", "dragon_knight"]}


@pytest.fixture(scope="module")
def shipped() -> Content:
    return load_content()


@pytest.fixture(scope="module")
def pristine() -> Json:
    return vc.load_catalog(CATALOG_PATH)


@pytest.fixture
def catalog(pristine: Json) -> Json:
    return copy.deepcopy(pristine)


def by_id(entries: list[Json], wanted: str) -> Json:
    return next(entry for entry in entries if entry["id"] == wanted)


def dead_end_lines(vocations: list[str]) -> list[str]:
    return [f"TRAINING_DEAD_END {v} rank {rank}" for v in vocations for rank in TRAINING_DEAD_ENDS.get(v, [])]


# -- (a) schema ----------------------------------------------------------------------------------


def test_schema_is_a_valid_draft_2020_12_schema() -> None:
    schema = vc.load_catalog_schema(SCHEMA_PATH)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    jsonschema.Draft202012Validator.check_schema(schema)


def test_catalog_validates_against_the_schema(pristine: Json) -> None:
    assert vc.schema_problems(pristine, vc.load_catalog_schema(SCHEMA_PATH)) == []


def test_schema_vocabularies_match_the_game() -> None:
    schema = vc.load_catalog_schema(SCHEMA_PATH)
    assert vc.vocabulary_problems(schema) == []
    schema["$defs"]["face_tag"]["enum"].append("draconic")
    assert any("face_tag" in problem for problem in vc.vocabulary_problems(schema))


# -- (b) cross-checks ----------------------------------------------------------------------------


def test_catalog_has_no_problems(pristine: Json, shipped: Content) -> None:
    lines = vc.validate(pristine, shipped)
    assert vc.problems_only(lines) == []
    assert all(line.startswith("warning: ") for line in lines)


def test_rewards_that_always_clamp_to_zero_are_warnings(pristine: Json, shipped: Content) -> None:
    clamped = [line for line in vc.validate(pristine, shipped) if "REWARD_ALWAYS_CLAMPED" in line]
    # Arcanist needs a mastered Apprentice (+1 mana, cap 1); Ranger needs a mastered Scout (+1 speed, cap 1).
    assert sorted(line.split()[2] for line in clamped) == ["arcanist", "ranger"]
    assert all(line.startswith("warning: ") and "always clamps to zero" in line for line in clamped)


def test_catalog_shape_and_counts(pristine: Json) -> None:
    assert pristine["catalog_version"] == "0.4.0"  # 0.3.0: the Guardian is playable; 0.4.0: its skill Field Medic works in battle
    assert pristine["baseline"] == {"rules_version": "1.1.1", "content_version": "1.3.1"}
    assert {wave: [v["id"] for v in pristine["vocations"] if v["wave"] == wave] for wave in WAVES} == WAVES
    assert len(pristine["face_library"]) == 12 and len(pristine["dice"]) == 23
    assert Counter(s["engine_support"] for s in pristine["schedules"]) == {"existing": 5, "new": 5}
    assert Counter(p["engine_support"] for p in pristine["passives"]) == {"existing": 3, "new": 8}
    assert Counter(r["engine_support"] for r in pristine["reactions"]) == {"existing": 7, "new": 1}
    assert len(pristine["skills"]) == 14 and len(pristine["challenges"]) == 14 and len(pristine["engine_gaps"]) == 14


# -- novices are read from the shipped content, never restated ------------------------------------


def test_novices_only_point_at_shipped_classes(pristine: Json, shipped: Content) -> None:
    novices = [v for v in pristine["vocations"] if v["group"] == "novice"]
    assert sorted(v["class_id"] for v in novices) == sorted(shipped.classes)
    for vocation in novices:
        assert set(vocation) == {"id", "group", "wave", "definition", "class_id", "inheritance_capacity", "mastery_rewards",
                                 "skills_learned", "bonus_challenge_id"}
        assert vocation["definition"] == "shipped" and vocation["wave"] == 0
    shipped_ids = set(shipped.dice) | set(shipped.reactions) | set(shipped.documents["dice"]["face_library"])
    assert not shipped_ids & (set(pristine["dice"]) | set(pristine["face_library"]) | {r["id"] for r in pristine["reactions"]})


def test_numbers_copied_from_novice_content_follow_content_1_3_0(pristine: Json, shipped: Content) -> None:
    faces = shipped.documents["dice"]["face_library"]
    # Strike and Jab are used by id, so the new dice get the shipped 3 and 2, not v0.1's 2 and 1.
    assert pristine["dice"]["guardian_d6"]["faces"].count("sq_strike_3") == 1 and faces["sq_strike_3"]["power"] == 3
    assert "sq_jab_2" in pristine["dice"]["guardian_d4"]["faces"] and faces["sq_jab_2"]["power"] == 2
    # Reactions that copy a novice reaction's cost.
    for reaction in pristine["reactions"]:
        novice = {"guard": "interpose", "resource": "grounding", "interrupt": "disrupt"}[reaction["stage"]]
        assert reaction["mana_cost"] == shipped.reactions[novice]["mana_cost"], reaction["id"]
    # Reactions identical to a novice one are that novice reaction.
    reaction_of = {v["id"]: v["reaction_id"] for v in pristine["vocations"] if v["group"] != "novice"}
    assert (reaction_of["spellblade"], reaction_of["shadowbinder"], reaction_of["ranger"]) == ("interpose", "grounding", "disrupt")


def test_every_die_face_resolves_and_every_die_is_full(pristine: Json, shipped: Content) -> None:
    known = set(pristine["face_library"]) | set(shipped.documents["dice"]["face_library"])
    for die_id, die in pristine["dice"].items():
        assert len(die["faces"]) == die["size"], die_id
        assert set(die["faces"]) <= known, die_id


# -- schedules -----------------------------------------------------------------------------------


def test_the_shipped_policies_are_expressible_as_slot_schedules(shipped: Content) -> None:
    for class_id, definition in shipped.classes.items():
        scheduling = definition["scheduling"]
        schedule = vc.slot_schedule(class_id, scheduling)
        assert schedule["engine_support"] == "existing"
        assert vc.shipped_policy(schedule) == scheduling["policy"]
        assert vc.shipped_scheduling(schedule) == scheduling  # nothing is lost on the way back
    free = {"policy": "free", "label": "Free", "max_actions": 2, "summary": "Any two actions."}
    assert vc.shipped_scheduling(vc.slot_schedule("free", free)) == free


def test_schedule_engine_support_matches_the_shipped_policies(pristine: Json, shipped: Content) -> None:
    policies = {s["id"]: vc.shipped_policy(s) for s in pristine["schedules"]}
    assert policies == {
        "single_commitment": "single", "status_then_attack": "sequence", "resource_then_attack": "sequence",
        "defense_then_attack": "sequence", "status_then_resource_or_attack": "sequence",
        "defense_or_status_then_attack": None, "resource_then_spell_or_heal": None,
        "resource_then_attack_then_support": None, "two_distinct_categories": None, "trickster_two_step": None,
    }
    for schedule in pristine["schedules"]:
        assert (schedule["engine_support"] == "existing") == (policies[schedule["id"]] is not None)
    # The Guardian and the Ranger keep their parent's exact policy.
    guardian, squire = by_id(pristine["schedules"], "single_commitment"), shipped.classes["squire"]["scheduling"]
    ranger, scout = by_id(pristine["schedules"], "status_then_attack"), shipped.classes["scout"]["scheduling"]
    assert {**vc.shipped_scheduling(guardian), "label": "", "summary": ""} == {**squire, "label": "", "summary": ""}
    assert {**vc.shipped_scheduling(ranger), "label": "", "summary": ""} == {**scout, "label": "", "summary": ""}


# -- the shipped loader accepts everything that claims to be expressible --------------------------


def test_new_faces_reactions_and_loadable_vocations_pass_the_shipped_loader(pristine: Json, shipped: Content) -> None:
    assert [v["id"] for v in vc.loadable_vocations(pristine, shipped)] == ["guardian", "spellblade", "ranger"]
    content = build_content(vc.loader_documents(pristine, shipped))
    assert {"guardian", "spellblade", "ranger"} <= set(content.classes)
    assert content.classes["guardian"]["passive"]["type"] == "ally_defense_die_bonus"
    assert set(pristine["face_library"]) <= set(content.documents["dice"]["face_library"])
    assert {r["id"] for r in pristine["reactions"]} <= set(content.reactions)
    assert [face.name for face in content.die("ranger_d8").faces][:2] == ["Aimed Shot", "Shot"]


def test_face_rules_mirror_the_shipped_loader(shipped: Content) -> None:
    """Each face the mirror rejects is rejected by the loader too, and for the same reason."""
    good = copy.deepcopy(shipped.documents["dice"]["face_library"]["sq_rally"])
    broken: dict[str, Json] = {
        "no effects": {**good, "effects": []},
        "no speed": {**good, "action_speed": None},
        "revive on attack": {**good, "category": "attack"},
        "revive without heal": {**good, "effects": [{"type": "shield", "target": "target"}]},
        "revive at zero": {**good, "effects": [{"type": "heal", "target": "target", "amount": 0}]},
        "no target": {**good, "target_scope": "none"},
        "blank with effects": {**good, "category": "blank", "can_revive": False},
        "reaction effect": {**good, "can_revive": False, "category": "status",
                            "effects": [{"type": "interrupt", "resisted_damage_reduction": 1, "resisted_magnitude_reduction": 1}]},
    }
    assert vc.face_rule_problems("x", "good", good) == []
    for label, face in broken.items():
        mirrored = vc.face_rule_problems("dice.json", "probe", face)
        assert mirrored, label
        documents = copy.deepcopy(shipped.documents)
        documents["dice"]["face_library"]["probe"] = face
        with pytest.raises(ContentError) as caught:
            build_content(documents)
        assert sorted(mirrored) == sorted(caught.value.problems), label


# -- (c) training and unlock reachability, wave by wave -------------------------------------------


def not_authored(catalog: Json) -> Json:
    """The catalog as it was before the threat-4 encounter was authored."""
    encounter = by_id(catalog["encounters"], "training_04")
    del encounter["enemies"]
    encounter["source"] = "to_author"
    return catalog


def test_wave_1_is_fully_trainable_because_the_threat_4_encounter_is_authored(catalog: Json, pristine: Json, shipped: Content) -> None:
    """The Guardian's last rank-up needs threat 4. Shipped battles stop at 3; the authored third battle supplies it."""
    assert vc.problems_only(vc.validate(pristine, shipped, wave=0)) == []
    assert vc.problems_only(vc.validate(pristine, shipped, wave=1)) == []
    assert vc.available_threat(pristine) == 4
    without = not_authored(catalog)
    assert vc.available_threat(without) == 3
    assert vc.problems_only(vc.validate(without, shipped, wave=1)) == ["TRAINING_DEAD_END guardian rank 7"]
    by_vocation: dict[str, list[int]] = {}
    for vocation, rank in vc.training_dead_ends(without):
        by_vocation.setdefault(vocation["id"], []).append(rank)
    assert by_vocation == DEAD_ENDS_AT_THREAT_3


def test_training_and_unlock_dead_ends_by_wave(pristine: Json, shipped: Content) -> None:
    released: list[str] = []
    for wave in sorted(WAVES):
        released += WAVES[wave]
        problems = vc.problems_only(vc.validate(pristine, shipped, wave=wave))
        assert [p for p in problems if p.startswith("TRAINING_DEAD_END")] == dead_end_lines(released), wave
        unlock = sorted(p.split()[1] for p in problems if p.startswith("UNLOCK_DEAD_END"))
        # No vocation is released before its prerequisites. The Trickster needs an encounter nobody can play yet;
        # the Dragon Knight's item comes from the threat-4 encounter, which is authored.
        assert unlock == {0: [], 1: [], 2: [], 3: [], 4: [], 5: ["trickster"]}[wave], wave
        assert len(problems) == len(dead_end_lines(released)) + len(unlock), wave


def test_without_a_wave_every_dead_end_is_a_warning(pristine: Json, shipped: Content) -> None:
    lines = vc.validate(pristine, shipped)
    everyone = [v for wave in sorted(WAVES) for v in WAVES[wave]]
    assert [line for line in lines if "TRAINING_DEAD_END" in line] == ["warning: " + line for line in dead_end_lines(everyone)]
    assert sorted(line.split()[2] for line in lines if "UNLOCK_DEAD_END" in line) == ["trickster"]


def test_the_authored_encounter_has_enemies_for_every_party_size_and_loads(pristine: Json, shipped: Content) -> None:
    encounter = by_id(pristine["encounters"], "training_04")
    assert (encounter["source"], encounter["threat_rating"]) == ("authored", 4)
    assert sorted(encounter["enemies"]) == ["1", "2", "3", "4", "5"]
    # Its line-up keeps the v0.1 idea where the party is big enough: two captains and a hex adept.
    assert [[e["archetype"] for e in encounter["enemies"][size]] for size in ("1", "2", "3")] == [
        ["captain"], ["captain", "hex_adept"], ["captain", "captain", "hex_adept"]]
    assert all(e["archetype"] in shipped.enemies for row in encounter["enemies"].values() for e in row)
    loaded = vc.load_vocation_catalog(shipped)
    assert loaded.has_encounter("training_04") and loaded.threat_rating("training_04") == 4
    assert loaded.encounter("training_04", 3) == encounter["enemies"]["3"]
    assert loaded.shipped_battles == {1: ("training_01", 1), 2: ("training_03", 3)}
    loaded.encounter("training_04", 3)[0]["archetype"] = "changed"  # a copy: the catalog cannot be altered through it
    assert loaded.encounter("training_04", 3)[0]["archetype"] == "captain"
    for encounter_id, reason in (("training_05", "have not been authored"), ("training_01", "shipped battle of every run")):
        with pytest.raises(EncounterNotPlayable, match=reason):
            loaded.encounter(encounter_id, 3)
    with pytest.raises(EncounterNotPlayable, match="no enemies for a party of 9"):
        loaded.encounter("training_04", 9)
    assert not loaded.has_encounter("nowhere")


# -- (d) seeded violations -----------------------------------------------------------------------


def _vocation(catalog: Json, vocation_id: str) -> Json:
    return by_id(catalog["vocations"], vocation_id)


def five_faced_d6(c: Json) -> None:
    c["dice"]["guardian_d6"]["faces"].pop()


def unknown_face_id(c: Json) -> None:
    c["dice"]["guardian_d6"]["faces"][0] = "no_such_face"


def prerequisite_cycle(c: Json) -> None:
    _vocation(c, "guardian")["prerequisite"] = {"mastered": "champion"}


def reward_above_cap(c: Json) -> None:
    _vocation(c, "guardian")["mastery_rewards"][0]["amount"] = 3


def reaction_stage_counter(c: Json) -> None:
    by_id(c["reactions"], "rx_guardian_ward")["stage"] = "counter"


def unknown_schedule_category(c: Json) -> None:
    by_id(c["schedules"], "defense_then_attack")["slots"][0]["categories"] = ["movement"]


def novice_redefined_with_stats(c: Json) -> None:
    _vocation(c, "squire").update(max_hp=14, speed=7)


def face_with_reaction_only_effect(c: Json) -> None:
    c["face_library"]["ce_heavy_guard_4"]["effects"] = [
        {"type": "interrupt", "resisted_damage_reduction": 2, "resisted_magnitude_reduction": 1}]


def duplicate_id(c: Json) -> None:
    c["schedules"].append(copy.deepcopy(c["schedules"][0]))


def missing_upgrade_family(c: Json) -> None:
    del _vocation(c, "guardian")["upgrade_family"]


def unknown_effect_type(c: Json) -> None:
    c["face_library"]["ce_heal_2"]["effects"][0]["type"] = "teleport"


def unshipped_encounter_marked_shipped(c: Json) -> None:
    del by_id(c["encounters"], "training_04")["enemies"]
    by_id(c["encounters"], "training_04").update(source="shipped", shipped_ref={"battle": 2})


def authored_encounter_without_enemies(c: Json) -> None:
    del by_id(c["encounters"], "training_04")["enemies"]


def unauthored_encounter_with_enemies(c: Json) -> None:
    by_id(c["encounters"], "training_05")["enemies"] = by_id(c["encounters"], "training_04")["enemies"]


def authored_encounter_missing_a_party_size(c: Json) -> None:
    del by_id(c["encounters"], "training_04")["enemies"]["4"]


def authored_encounter_with_an_unknown_enemy(c: Json) -> None:
    by_id(c["encounters"], "training_04")["enemies"]["2"][0]["archetype"] = "dragon"


def authored_encounter_overriding_an_unknown_action(c: Json) -> None:
    by_id(c["encounters"], "training_04")["enemies"]["2"][0]["overrides"]["actions"] = {"breath": {"power": 9}}


def authored_encounter_with_an_enemy_that_cannot_act(c: Json) -> None:
    by_id(c["encounters"], "training_04")["enemies"]["1"][0]["overrides"]["actions"] = {
        name: {"weight": 0} for name in ("blight_wave", "corrupt_mark", "strike", "war_cry")}


def shipped_encounter_without_a_battle(c: Json) -> None:
    by_id(c["encounters"], "training_05")["source"] = "shipped"


def third_shipped_battle(c: Json) -> None:
    by_id(c["encounters"], "training_05").update(source="shipped", shipped_ref={"battle": 3})


def upgrade_family_not_shipped(c: Json) -> None:
    _vocation(c, "guardian")["upgrade_family"] = "paladin"


def novice_class_not_shipped(c: Json) -> None:
    _vocation(c, "scout")["class_id"] = "ranger"


def shipped_face_redefined(c: Json) -> None:
    c["face_library"]["sq_strike_3"] = copy.deepcopy(c["face_library"]["ce_aimed_shot_3"])


def shipped_face_copied_under_a_new_id(c: Json) -> None:
    c["face_library"]["ce_aimed_shot_3"].update(power=2)  # now Shot (sc_shot_2) in everything but name


def schedule_falsely_existing(c: Json) -> None:
    by_id(c["schedules"], "defense_or_status_then_attack")["engine_support"] = "existing"


def new_passive_without_a_gap(c: Json) -> None:
    c["engine_gaps"] = [gap for gap in c["engine_gaps"] if gap["id"] != "passive_attack_after_category_bonus"]


def new_passive_type_marked_existing(c: Json) -> None:
    by_id(c["passives"], "riposte")["engine_support"] = "existing"


def melee_face_on_a_ranged_only_vocation(c: Json) -> None:
    c["dice"]["ranger_d4"]["faces"][1] = "sq_jab_2"


def revive_on_an_attack_face(c: Json) -> None:
    c["face_library"]["ce_aimed_shot_3"]["can_revive"] = True


def wrong_number_of_starting_dice(c: Json) -> None:
    _vocation(c, "guardian")["dice_capacity"] = 3


def starting_mana_above_maximum(c: Json) -> None:
    _vocation(c, "guardian")["start_mana"] = 4


def unknown_prerequisite_vocation(c: Json) -> None:
    _vocation(c, "guardian")["prerequisite"] = {"mastered": "page"}


def unknown_skill(c: Json) -> None:
    _vocation(c, "guardian")["skills_learned"][0]["skill_id"] = "guardian_taunt"


def stale_baseline(c: Json) -> None:
    c["baseline"]["content_version"] = "1.2.1"


def unknown_top_level_key(c: Json) -> None:
    c["actions"] = {}


SEEDED: list[tuple[Callable[[Json], None], str]] = [
    (five_faced_d6, "die 'guardian_d6' declares size 6 but has 5 faces"),
    (unknown_face_id, "references unknown face 'no_such_face'"),
    (prerequisite_cycle, "prerequisite cycle: guardian -> champion -> guardian"),
    (reward_above_cap, "mastery reward +3 max_hp exceeds the cap of 2"),
    (reaction_stage_counter, "'counter' is not one of"),
    (unknown_schedule_category, "'movement' is not one of"),
    (novice_redefined_with_stats, "Additional properties are not allowed ('max_hp', 'speed' were unexpected)"),
    (face_with_reaction_only_effect, "'interrupt' is not one of"),
    (duplicate_id, "schedules: duplicate id 'single_commitment'"),
    (missing_upgrade_family, "'upgrade_family' is a required property"),
    (unknown_effect_type, "'teleport' is not one of"),
    (unshipped_encounter_marked_shipped, "'training_04' is marked shipped as battle 2, which 'training_03' already is"),
    (authored_encounter_without_enemies, "'enemies' is a required property"),
    (unauthored_encounter_with_enemies, "encounters/4"),
    (authored_encounter_missing_a_party_size, "'training_04' is authored but its enemies are not listed for exactly the party sizes 1, 2, 3, 4, 5"),
    (authored_encounter_with_an_unknown_enemy, "'training_04': party size 2 uses unknown enemy 'dragon'"),
    (authored_encounter_overriding_an_unknown_action, "overrides unknown action 'breath' of enemy 'captain'"),
    (authored_encounter_with_an_enemy_that_cannot_act, "leaves enemy 'captain' with no action of positive weight"),
    (shipped_encounter_without_a_battle, "'shipped_ref' is a required property"),
    (third_shipped_battle, "3 is not one of [1, 2]"),
    (upgrade_family_not_shipped, "upgrade_family 'paladin', which is not a shipped class"),
    (novice_class_not_shipped, "class_id 'ranger', which is not a shipped class"),
    (shipped_face_redefined, "'sq_strike_3' redefines a shipped face"),
    (shipped_face_copied_under_a_new_id, "'ce_aimed_shot_3' only renames the shipped face 'sc_shot_2'"),
    (schedule_falsely_existing, "is marked existing but no shipped policy"),
    (new_passive_without_a_gap, "'riposte' is marked new but no engine_gaps entry"),
    (new_passive_type_marked_existing, "'new' was expected"),
    (melee_face_on_a_ranged_only_vocation, "needs every Attack face of 'ranger' tagged 'ranged', but 'sq_jab_2' is not"),
    (revive_on_an_attack_face, "face 'ce_aimed_shot_3' is can_revive but is not a Healing face"),
    (wrong_number_of_starting_dice, "must start with exactly dice_capacity (3) dice"),
    (starting_mana_above_maximum, "has a starting value above its maximum"),
    (unknown_prerequisite_vocation, "prerequisite references unknown vocation 'page'"),
    (unknown_skill, "teaches unknown skill 'guardian_taunt'"),
    (stale_baseline, "catalog was written against content 1.2.1, shipped is 1.3.1"),
    (unknown_top_level_key, "Additional properties are not allowed ('actions' was unexpected)"),
]


@pytest.mark.parametrize(("mutate", "expected"), SEEDED, ids=[mutate.__name__ for mutate, _ in SEEDED])
def test_seeded_violation_is_rejected(mutate: Callable[[Json], None], expected: str, catalog: Json, shipped: Content) -> None:
    mutate(catalog)
    problems = vc.problems_only(vc.validate(catalog, shipped))
    assert any(expected in problem for problem in problems), problems


def test_a_repeated_json_key_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "catalog.json"
    path.write_text('{"catalog_version": "0.2.0", "dice": {"a_d4": 1, "a_d4": 2}}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate key"):
        vc.load_catalog(path)
    assert vc.main(["--catalog", str(path)]) == 1


# -- command line --------------------------------------------------------------------------------


def test_main_prints_ok_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert vc.main([]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[-1] == "OK" and all(line.startswith("warning: ") for line in out[:-1])


def test_main_reports_a_dead_end_of_the_wave_asked_for_and_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    assert vc.main(["--wave", "1"]) == 0  # the first wave is trainable since the threat-4 encounter is authored
    assert capsys.readouterr().out.splitlines()[-1] == "OK"
    assert vc.main(["--wave", "4"]) == 1  # the capstones still need a threat-5 encounter
    out = capsys.readouterr().out.splitlines()
    assert "TRAINING_DEAD_END champion rank 4" in out and "TRAINING_DEAD_END archmage rank 7" in out and "OK" not in out
    assert vc.main(["--wave", "0"]) == 0
