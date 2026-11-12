"""Field Medic in battle (Class Evolution Phase 4, step E).

Mastering the Guardian teaches Field Medic. Equipped, it lets a Healing face that cannot revive
bring a downed ally back at 1 HP, once per encounter, for 1 more mana. Owner decision of
2026-11-11 (D-27): it works in battle in the first slice.
"""

from __future__ import annotations

import pytest

from battle_dice.content.vocations import VocationCatalog, load_vocation_catalog
from battle_dice.core import commands as cmd
from battle_dice.core import skills
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType, events_hash, state_hash
from battle_dice.core.models import STATE_DOWNED, STATE_STANDING, to_plain
from battle_dice.core.replay import export_run, verify
from battle_dice.core.view import hero_turn_view
from tests.conftest import (
    action,
    begin_hero,
    commit,
    down,
    events_of,
    finish_activation,
    ok,
    packaged_content,
    unit,
)

HEAL = 5  # the Heal 2 face of guardian_d6 (1-based): a heal that cannot revive, 1 mana


@pytest.fixture(scope="module")
def catalog() -> VocationCatalog:
    return load_vocation_catalog(packaged_content())


def started(catalog: VocationCatalog, equipped: bool = True, seed: int = 4, third: bool = False) -> Engine:
    """A Guardian (with Field Medic equipped, or not) and a Scout."""
    hero = {"hero_id": "hero_001", "skills": [skills.FIELD_MEDIC] if equipped else []}
    party = [{"class_id": "guardian", "row": "front", "hero": hero}, {"class_id": "scout", "row": "back", "hero": {"hero_id": "hero_002"}}]
    engine = Engine(packaged_content(), catalog)
    params: dict = {"seed": seed, "party": party}
    if third:
        params["encounters"] = ["training_04"]
    ok(engine.do(cmd.START_RUN, **params))
    return engine


def die_option(engine: Engine, die_id: str) -> dict:
    view = hero_turn_view(engine)
    assert view is not None
    return next(d for d in view["dice"] if d["die_id"] == die_id)


def with_a_downed_scout(catalog: VocationCatalog, mana: int = 2, **kwargs) -> Engine:
    engine = started(catalog, **kwargs)
    down(engine, "h02")
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=HEAL)
    unit(engine, "h01").mana = mana
    return engine


def test_the_guardians_heal_cannot_revive_on_its_own(catalog):
    engine = with_a_downed_scout(catalog, equipped=False)
    heal = engine.die_for("h01", "guardian_d6").faces[HEAL - 1]
    assert heal.category == "healing" and not heal.can_revive and heal.mana_cost == 1
    result = engine.do(cmd.SET_ACTION_PLAN, actions=[action("guardian_d6", "h02")])
    assert not result.accepted and result.code == "TARGET_DOWNED" and "revival-capable" in (result.reason or "")
    option = die_option(engine, "guardian_d6")
    assert "h02" not in option["eligible_target_ids"]


def test_with_field_medic_the_heal_revives_a_downed_ally_to_one_hp_for_one_more_mana(catalog):
    engine = with_a_downed_scout(catalog)
    option = die_option(engine, "guardian_d6")
    assert option["eligible_target_ids"] == ["h01", "h02"], "the downed ally is offered as a target"
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("guardian_d6", "h02")]))
    intent = engine.combat.turn.plan[0]
    assert intent.costs == {"mana": 2} and skills.FIELD_MEDIC_TAG in intent.tags and intent.name == "Heal (Field Medic)"
    ok(engine.do(cmd.COMMIT_ACTION_PLAN))
    finish_activation(engine)
    guardian, scout = unit(engine, "h01"), unit(engine, "h02")
    assert (scout.state, scout.hp) == (STATE_STANDING, 1) and guardian.mana == 0
    assert guardian.skill_uses == {skills.FIELD_MEDIC: 1}
    resolved = [e for e in events_of(engine, EventType.ACTION_RESOLVED) if e.actor_id == "h01"][-1]
    assert resolved.delta["name"] == "Heal (Field Medic)" and resolved.delta["mana_spent"] == 2
    assert [(r["type"], r["target"], r["healed"], r["revived"]) for r in resolved.delta["results"]] == [("heal", "h02", 1, True)]
    assert [e.delta["id"] for e in events_of(engine, EventType.HERO_REVIVED)] == ["h02"]


def test_it_works_once_per_encounter(catalog):
    engine = with_a_downed_scout(catalog)
    commit(engine, action("guardian_d6", "h02"))
    finish_activation(engine)
    down(engine, "h02")
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=HEAL)
    unit(engine, "h01").mana = 3
    assert not skills.field_medic_ready(engine, unit(engine, "h01"), engine.die_for("h01", "guardian_d6").faces[HEAL - 1])
    result = engine.do(cmd.SET_ACTION_PLAN, actions=[action("guardian_d6", "h02")])
    assert not result.accepted and result.code == "TARGET_DOWNED"
    assert unit(engine, "h02").state == STATE_DOWNED


def test_it_is_ready_again_in_the_next_battle(catalog):
    engine = with_a_downed_scout(catalog)
    commit(engine, action("guardian_d6", "h02"))
    finish_activation(engine)
    assert unit(engine, "h01").skill_uses == {skills.FIELD_MEDIC: 1}
    win_battle_as_guardian(engine)
    offer = next(o for dice in engine.state.upgrade_offers.values() for die in dice.values() for o in die)
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id=offer["hero_id"], die_id=offer["die_id"], offer_id=offer["offer_id"]))
    ok(engine.do(cmd.ADVANCE_PHASE))
    assert engine.state.encounter_index == 1 and unit(engine, "h01").skill_uses == {}


def win_battle_as_guardian(engine: Engine) -> None:
    """Arrange: every enemy but one is gone, and the Guardian's Strike finishes the last."""
    foes = engine.combat.side("enemy")
    for foe in foes[1:]:
        foe.hp, foe.state = 0, "defeated"
    foes[0].hp, foes[0].shields = 1, 0
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=4)  # Strike
    commit(engine, action("guardian_d6", foes[0].id))
    while engine.state.phase == "battle" and not engine.needs_input():
        ok(engine.do(cmd.ADVANCE_PHASE))


def test_too_little_mana_for_the_revival_is_refused_for_the_mana(catalog):
    """The situation of fixture CE-29: the target is legal through the skill, so the mana check is the one that fails."""
    engine = with_a_downed_scout(catalog, mana=1)  # the heal itself costs 1; the revival costs 2
    before = state_hash(engine.state)
    result = engine.do(cmd.SET_ACTION_PLAN, actions=[action("guardian_d6", "h02")])
    assert not result.accepted and result.code == "INSUFFICIENT_MANA" and "needs 2 mana but only 1" in (result.reason or "")
    assert state_hash(engine.state) == before and unit(engine, "h02").state == STATE_DOWNED and unit(engine, "h01").skill_uses == {}
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("guardian_d6", "h01")]))  # on a standing ally the heal is the plain heal
    assert engine.combat.turn.plan[0].costs == {"mana": 1} and skills.FIELD_MEDIC_TAG not in engine.combat.turn.plan[0].tags


def test_on_a_standing_ally_the_face_is_what_it_always_was_and_the_skill_stays_ready(catalog):
    engine = started(catalog)
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=HEAL)
    unit(engine, "h02").hp = 3
    commit(engine, action("guardian_d6", "h02"))
    finish_activation(engine)
    assert unit(engine, "h02").hp == 5 and unit(engine, "h01").mana == 1 and unit(engine, "h01").skill_uses == {}


def test_a_face_that_already_revives_or_is_not_a_heal_is_not_changed(catalog):
    engine = started(catalog)
    guardian = unit(engine, "h01")
    plain_heal, guard, strike = (engine.die_for("h01", "guardian_d6").faces[i] for i in (HEAL - 1, 0, 3))
    rally = packaged_content().die("iron_d6").faces[4]
    assert skills.field_medic_ready(engine, guardian, plain_heal)
    assert not any(skills.field_medic_ready(engine, guardian, face) for face in (guard, strike, rally))
    changed = skills.as_field_medic(plain_heal)
    assert (changed.can_revive, changed.mana_cost, changed.effects) == (True, 2, [{**plain_heal.effects[0], "amount": 1}])
    assert plain_heal.can_revive is False and plain_heal.mana_cost == 1, "the die's own face is not altered"
    assert skills.KNOWN == (skills.FIELD_MEDIC,)


def test_a_skill_the_rules_do_not_know_changes_nothing(catalog):
    party = [{"class_id": "guardian", "row": "front", "hero": {"hero_id": "hero_001", "skills": ["scout_marksman"]}},
             {"class_id": "scout", "row": "back"}]
    engine = Engine(packaged_content(), catalog)
    ok(engine.do(cmd.START_RUN, seed=4, party=party))
    down(engine, "h02")
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=HEAL)
    assert engine.do(cmd.SET_ACTION_PLAN, actions=[action("guardian_d6", "h02")]).code == "TARGET_DOWNED"


def test_a_run_that_never_uses_the_skill_hashes_as_it_always_did(catalog):
    """The use counter is left out of the plain state while it is empty; once used, it is part of the state."""
    engine = with_a_downed_scout(catalog)
    assert "skill_uses" not in to_plain(unit(engine, "h01"))
    commit(engine, action("guardian_d6", "h02"))
    finish_activation(engine)
    assert to_plain(unit(engine, "h01"))["skill_uses"] == {skills.FIELD_MEDIC: 1}
    assert "skill_uses" not in to_plain(unit(engine, "h02"))


def test_a_run_with_a_field_medic_revival_replays_exactly(catalog):
    engine = with_a_downed_scout(catalog)
    commit(engine, action("guardian_d6", "h02"))
    finish_activation(engine)
    # ``down`` and the forced rolls are arrangements outside the command log, so replay the log on a twin
    # arranged the same way and compare, then check that an unarranged run with the skill verifies from its record.
    plain = started(catalog)
    from battle_dice.sim.policies import HeuristicPolicy, play_run

    play_run(plain, HeuristicPolicy())
    record = export_run(plain)
    assert record["commands"][0]["params"]["party"][0]["hero"]["skills"] == [skills.FIELD_MEDIC]
    again = verify(packaged_content(), record)
    assert (events_hash(again.events), state_hash(again.state)) == (events_hash(plain.events), state_hash(plain.state))


def kept_plan(engine: Engine) -> list[dict]:
    """What the informed simulated player would do with the roll in front of it."""
    from battle_dice.sim.policies import HeuristicPolicy

    hero, turn = engine._active_hero()
    return HeuristicPolicy()._best_plan(engine, hero, turn)[0]


def test_the_simulated_player_revives_with_field_medic_when_it_can_pay(catalog):
    engine = with_a_downed_scout(catalog, mana=2)
    assert {"die_id": "guardian_d6", "target_ids": ["h02"]} in kept_plan(engine)
    poor = with_a_downed_scout(catalog, mana=1)
    assert all(a["target_ids"] != ["h02"] for a in kept_plan(poor)), "it never proposes a plan the rules would refuse"
    without = with_a_downed_scout(catalog, mana=2, equipped=False)
    assert all(a["target_ids"] != ["h02"] for a in kept_plan(without))


def test_one_plan_cannot_hold_two_field_medic_revivals(catalog):
    """No hero of today can plan two heals in one activation; a later vocation with the skill may. The rule is there already."""
    import dataclasses

    party = [{"class_id": "guardian", "row": "front", "hero": {"hero_id": "hero_001", "skills": [skills.FIELD_MEDIC]}},
             {"class_id": "scout", "row": "back"}, {"class_id": "apprentice", "row": "back"}]
    engine = Engine(packaged_content(), catalog)
    ok(engine.do(cmd.START_RUN, seed=4, party=party))
    build = engine.build("h01")
    two_actions = {"policy": "free", "label": "Two heals", "summary": "Two actions per activation.", "max_actions": 2}
    engine._builds["h01"] = dataclasses.replace(build, scheduling=two_actions)
    heal = engine.die_for("h01", "guardian_d6").faces[HEAL - 1]
    small = engine.die_for("h01", "guardian_d4")
    engine.state.die_overrides.setdefault("h01", {})["guardian_d4"] = dataclasses.replace(small, faces=[heal, *small.faces[1:]])
    down(engine, "h02")
    down(engine, "h03")
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=HEAL)
    unit(engine, "h01").mana = 3
    twice = engine.do(cmd.SET_ACTION_PLAN, actions=[action("guardian_d6", "h02"), action("guardian_d4", "h03")])
    assert not twice.accepted and twice.code == "TARGET_DOWNED" and twice.reason == "Field Medic can revive once per encounter."
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("guardian_d6", "h02"), action("guardian_d4", "h01")]))
    assert [(i.name, i.costs["mana"]) for i in engine.combat.turn.plan] == [("Heal (Field Medic)", 2), ("Heal", 1)]


def test_the_catalog_and_the_rules_agree_on_which_skills_work_in_battle(catalog):
    """A skill is marked ``existing`` in the catalog exactly when the rules of battle know it."""
    from battle_dice.content.vocations import load_catalog

    raw = load_catalog()
    supported = sorted(skill["id"] for skill in raw["skills"] if skill["engine_support"] == "existing")
    assert supported == sorted(skills.KNOWN) == ["guardian_field_medic"]
    gap = next(gap for gap in raw["engine_gaps"] if gap["id"] == "inherited_skills")
    assert "skill:guardian_field_medic" not in gap["used_by"] and "skill:squire_anchor" in gap["used_by"]
