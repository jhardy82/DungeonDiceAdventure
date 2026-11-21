"""A saved hero changes its vocation inside a run (Class Evolution Phase 4, acceptance case CE-19).

After a battle's recovery and before the mandatory upgrade is chosen, a hero may take another
vocation it has unlocked. Its health and mana are carried over by the career rule, it gets the
new vocation's dice, and the upgrade is then chosen for a die it will fight with.
"""

from __future__ import annotations

import pytest

from battle_dice.content.vocations import VocationCatalog, load_vocation_catalog
from battle_dice.core import commands as cmd
from battle_dice.core.build import convert_pool
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType, events_hash, state_hash
from battle_dice.core.models import RunPhase
from battle_dice.core.replay import export_run, verify
from battle_dice.core.view import combat_log, describe_event
from battle_dice.sim.policies import HeuristicPolicy, play_run
from tests.conftest import (
    action,
    begin_hero,
    commit,
    events_of,
    finish_activation,
    ok,
    packaged_content,
    unit,
    win_battle,
)

GUARDIAN = {"hero_id": "hero_001", "name": "Aldric", "stats": {"max_hp": 18, "max_mana": 3, "speed": 6}}


@pytest.fixture(scope="module")
def catalog() -> VocationCatalog:
    return load_vocation_catalog(packaged_content())


def after_battle_one(catalog: VocationCatalog, seed: int = 11, saved: bool = True, third: bool = False) -> Engine:
    """A Squire and a Scout have won Battle 1: the run waits for the mandatory upgrade."""
    squire = {"class_id": "squire", "row": "front"}
    if saved:
        squire["hero"] = {"hero_id": "hero_001", "name": "Aldric"}  # type: ignore[assignment]
    party = [squire, {"class_id": "scout", "row": "back", "hero": {"hero_id": "hero_002"}}]
    engine = Engine(packaged_content(), catalog)
    params: dict = {"seed": seed, "party": party}
    if third:
        params["encounters"] = ["training_04"]
    ok(engine.do(cmd.START_RUN, **params))
    win_battle(engine)
    assert engine.state.phase == RunPhase.UPGRADE
    return engine


def become_guardian(engine: Engine, **overrides):
    return engine.do(cmd.CHANGE_VOCATION, **{"hero_id": "h01", "class_id": "guardian", "hero": GUARDIAN, **overrides})


def test_the_pool_rule_rounds_up_caps_and_never_revives():
    assert convert_pool(10, 14, 18) == 13  # ceil(10 * 18 / 14)
    assert convert_pool(14, 14, 18) == 18 and convert_pool(1, 14, 18) == 2
    assert convert_pool(18, 18, 14) == 14 and convert_pool(9, 18, 14) == 7
    assert convert_pool(0, 14, 18) == 0 and convert_pool(-3, 14, 18) == 0 and convert_pool(5, 0, 18) == 0
    assert convert_pool(2, 3, 3) == 2
    assert convert_pool(20, 14, 18) == 18, "never above the new maximum, whatever it is given"


def test_a_saved_hero_becomes_a_guardian_between_recovery_and_the_upgrade(catalog):
    engine = after_battle_one(catalog)
    assert cmd.CHANGE_VOCATION in engine.permissible_commands()
    squire = unit(engine, "h01")
    hp, mana = squire.hp, squire.mana
    assert (squire.archetype_id, squire.max_hp, squire.equipped_dice_ids) == ("squire", 14, ["iron_d6", "oath_d4"])
    old_offers = engine.state.upgrade_offers["h01"]
    scout_offers = engine.state.upgrade_offers["h02"]
    draws = engine.state.rng["rewards"].draws

    ok(become_guardian(engine))

    guardian = unit(engine, "h01")
    assert (guardian.archetype_id, guardian.name, guardian.max_hp, guardian.max_mana, guardian.speed) == ("guardian", "Aldric", 18, 3, 6)
    assert guardian.hp == convert_pool(hp, 14, 18) and guardian.mana == convert_pool(mana, 3, 3)
    assert guardian.equipped_dice_ids == ["guardian_d6", "guardian_d4"] and engine.state.inventory["h01"] == []
    build = engine.build("h01")
    assert (build.vocation_id, build.hero_id, build.passive["type"]) == ("guardian", "hero_001", "ally_defense_die_bonus")
    assert engine.state.party[0] == {"id": "h01", "class_id": "guardian", "row": "front", "hero_id": "hero_001"}
    # The offers are for the dice the hero will fight with, drawn anew from the same stream; the Scout's stay.
    assert sorted(engine.state.upgrade_offers["h01"]) == ["guardian_d4", "guardian_d6"] and old_offers != engine.state.upgrade_offers["h01"]
    assert engine.state.upgrade_offers["h02"] == scout_offers and engine.state.rng["rewards"].draws > draws
    assert engine.state.phase == RunPhase.UPGRADE, "the mandatory upgrade is still to be chosen"
    event = events_of(engine, EventType.VOCATION_CHANGED)[-1]
    assert (event.delta["from"], event.delta["to"], event.delta["hero_id"], event.delta["dice"]) == ("squire", "guardian", "hero_001", ["guardian_d6", "guardian_d4"])
    assert event.delta["hp"] == [hp, guardian.hp] and event.delta["max_hp"] == [14, 18]
    text = describe_event(event, {"h01": "Aldric"})
    assert text == f"Aldric is now a Guardian: HP {hp}/14 -> {guardian.hp}/18, mana {mana}/3 -> {guardian.mana}/3, new dice and new upgrade offers."


def test_the_log_does_not_credit_an_earlier_bonus_to_the_new_passive(catalog):
    """As a Squire the hero shielded itself with Steadfast. Once it is a Guardian the log must not call that Bulwark."""
    party = [{"class_id": "squire", "row": "front", "hero": {"hero_id": "hero_001", "name": "Aldric"}},
             {"class_id": "scout", "row": "back", "hero": {"hero_id": "hero_002"}}]
    engine = Engine(packaged_content(), catalog)
    ok(engine.do(cmd.START_RUN, seed=11, party=party))
    begin_hero(engine, "h01", iron_d6=3, oath_d4=4)  # Guard
    commit(engine, action("iron_d6", "h01"))
    finish_activation(engine)
    assert sum("(incl. +1 Steadfast)" in line for line in combat_log(engine)) == 1
    win_battle(engine)
    ok(become_guardian(engine))
    log = combat_log(engine)
    assert sum("Aldric gains 4 shield (incl. +1 bonus)" in line for line in log) == 1
    assert not any("Bulwark" in line or "Steadfast" in line for line in log)


def test_the_upgrade_is_then_chosen_on_a_guardian_die_and_the_run_goes_on(catalog):
    """Fixture CE-19: the upgrade goes on a die of the new vocation, and that die is then locked against a swap."""
    engine = after_battle_one(catalog)
    ok(become_guardian(engine))
    offer = engine.state.upgrade_offers["h01"]["guardian_d6"][0]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="guardian_d6", offer_id=offer["offer_id"]))
    assert engine.state.phase == RunPhase.EQUIPMENT and "guardian_d6" in engine.state.die_overrides["h01"]
    from battle_dice.core import progression

    assert progression.upgraded_die_ids(engine, "h01") == ["guardian_d6"]
    again = become_guardian(engine, class_id="squire", hero={"hero_id": "hero_001"})
    assert not again.accepted and "before the upgrade is chosen" in (again.reason or ""), "one change, before the upgrade"
    ok(engine.do(cmd.ADVANCE_PHASE))
    assert engine.state.encounter_index == 1 and unit(engine, "h01").archetype_id == "guardian"
    assert unit(engine, "h01").equipped_dice_ids == ["guardian_d6", "guardian_d4"]
    play_run(engine, HeuristicPolicy())
    assert engine.finished()


def test_the_upgraded_die_of_the_new_vocation_cannot_be_swapped_out(catalog):
    """The second half of CE-19: the die that carries the mandatory upgrade stays equipped."""
    engine = after_battle_one(catalog)
    ok(become_guardian(engine, hero={**GUARDIAN, "bench": ["vanguard_d4"]}))
    assert engine.state.inventory["h01"] == ["vanguard_d4"]
    offer = engine.state.upgrade_offers["h01"]["guardian_d6"][0]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="guardian_d6", offer_id=offer["offer_id"]))
    locked = engine.do(cmd.SWAP_DIE, hero_id="h01", out_die_id="guardian_d6", in_die_id="vanguard_d4")
    assert not locked.accepted and locked.reason == "The upgraded die is locked and cannot be swapped out."
    assert unit(engine, "h01").equipped_dice_ids == ["guardian_d6", "guardian_d4"]


def test_the_run_and_the_career_rules_name_their_commands_differently():
    """``ChangeVocation`` is the career rules' command (may the hero?); the run is told with another name."""
    from battle_dice.career import service

    assert service.CHANGE == "ChangeVocation" and cmd.CHANGE_VOCATION == "ChangeVocationInRun"
    assert service.CHANGE not in cmd.COMMAND_TYPES


def test_an_upgrade_stays_with_a_die_the_hero_keeps_and_leaves_with_one_it_gives_up(catalog):
    """No hero has an upgrade before the one change it may make today; the rule is there for when one can."""
    engine = after_battle_one(catalog)
    content = packaged_content()
    engine.state.die_overrides["h01"] = {"iron_d6": content.die("iron_d6"), "vanguard_d4": content.die("vanguard_d4")}
    ok(become_guardian(engine, hero={**GUARDIAN, "bench": ["vanguard_d4"]}))
    assert sorted(engine.state.die_overrides["h01"]) == ["vanguard_d4"]
    other = after_battle_one(catalog)
    other.state.die_overrides["h01"] = {"iron_d6": content.die("iron_d6")}
    ok(become_guardian(other))
    assert "h01" not in other.state.die_overrides


def test_an_old_upgrade_offer_is_void_after_the_change(catalog):
    engine = after_battle_one(catalog)
    stale = engine.state.upgrade_offers["h01"]["iron_d6"][0]
    ok(become_guardian(engine))
    refused = engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="iron_d6", offer_id=stale["offer_id"])
    assert not refused.accepted and engine.state.phase == RunPhase.UPGRADE


def test_mana_is_carried_over_not_refilled(catalog):
    """Recovery refills mana, so the hero is at its maximum when it changes; spent mana must stay spent all the same."""
    engine = after_battle_one(catalog)
    unit(engine, "h01").mana = 1
    ok(become_guardian(engine))
    assert (unit(engine, "h01").mana, unit(engine, "h01").max_mana) == (1, 3)
    wider = after_battle_one(catalog)
    unit(wider, "h01").mana = 1
    ok(wider.do(cmd.CHANGE_VOCATION, hero_id="h01", class_id="apprentice", hero={"hero_id": "hero_001"}))
    apprentice = unit(wider, "h01")
    assert apprentice.max_mana == wider.build("h01").max_mana > 3
    assert apprentice.mana == convert_pool(1, 3, apprentice.max_mana) < apprentice.max_mana
    assert wider.events[-1].delta["mana"] == [1, apprentice.mana] and wider.events[-1].delta["max_mana"] == [3, apprentice.max_mana]


def test_a_change_that_fails_half_way_leaves_the_old_build(catalog, monkeypatch):
    """The builds live beside the run's state; a refusal puts them back with it."""
    from battle_dice.core import progression
    from battle_dice.core.commands import CommandRejected

    engine = after_battle_one(catalog)
    before = (state_hash(engine.state), engine.build("h01"), len(engine.events))

    def no_offers(*args, **kwargs):
        raise CommandRejected("simulated: no offers can be drawn")

    monkeypatch.setattr(progression, "offers_for_die", no_offers)
    refused = become_guardian(engine)
    assert not refused.accepted and refused.reason == "simulated: no offers can be drawn"
    assert (state_hash(engine.state), engine.build("h01"), len(engine.events)) == before
    assert engine.build("h01").vocation_id == "squire" and unit(engine, "h01").equipped_dice_ids == ["iron_d6", "oath_d4"]


def test_a_hero_that_is_down_stays_down(catalog):
    engine = after_battle_one(catalog)
    hero = unit(engine, "h01")
    hero.hp, hero.state = 0, "downed"
    ok(become_guardian(engine))
    assert (unit(engine, "h01").hp, unit(engine, "h01").state, unit(engine, "h01").max_hp) == (0, "downed", 18)


def test_it_can_change_back_before_the_upgrade(catalog):
    engine = after_battle_one(catalog)
    ok(become_guardian(engine))
    ok(engine.do(cmd.CHANGE_VOCATION, hero_id="h01", class_id="squire", hero={"hero_id": "hero_001", "name": "Aldric"}))
    hero = unit(engine, "h01")
    assert (hero.archetype_id, hero.max_hp, hero.equipped_dice_ids) == ("squire", 14, ["iron_d6", "oath_d4"])
    assert engine.state.inventory["h01"] == ["vanguard_d4"] and sorted(engine.state.upgrade_offers["h01"]) == ["iron_d6", "oath_d4"]
    assert [e.delta["to"] for e in events_of(engine, EventType.VOCATION_CHANGED)] == ["guardian", "squire"]


@pytest.mark.parametrize(("change", "reason"), [
    ({"hero_id": "h09"}, "Unknown hero 'h09'."),
    ({"hero": {"hero_id": "hero_777"}}, "The snapshot is of 'hero_777', not of the hero in that slot."),
    ({"class_id": "squire", "hero": {"hero_id": "hero_001", "name": "Aldric"}}, "Aldric is already a Squire."),
    ({"class_id": "dragon_rider"}, "Unknown class 'dragon_rider'."),
    ({"class_id": "champion"}, "champion"),  # in the catalog, but the rules cannot run it yet
    ({"hero": {**GUARDIAN, "stats": {"max_hp": 5}}}, "hero_001: max_hp 5 is below the 17 of a Guardian."),
    ({"hero": {**GUARDIAN, "dice": ["guardian_d6"]}}, "hero_001: a Guardian takes 2 dice into a run, not 1."),
])
def test_what_cannot_be_done_is_refused_and_changes_nothing(catalog, change, reason):
    engine = after_battle_one(catalog)
    before = (state_hash(engine.state), len(engine.events), engine.build("h01"), engine.revision)
    result = become_guardian(engine, **change)
    assert not result.accepted and reason in (result.reason or "")
    assert (state_hash(engine.state), len(engine.events), engine.build("h01"), engine.revision) == before
    assert unit(engine, "h01").archetype_id == "squire"


def test_only_a_saved_hero_can_change_and_only_in_the_upgrade_phase(catalog):
    plain = after_battle_one(catalog, saved=False)
    refused = become_guardian(plain)
    assert not refused.accepted and refused.reason == "Only a saved hero can change its vocation."
    engine = Engine(packaged_content(), catalog)
    ok(engine.do(cmd.START_RUN, seed=11, party=[{"class_id": "squire", "row": "front", "hero": {"hero_id": "hero_001"}},
                                                 {"class_id": "scout", "row": "back"}]))
    assert cmd.CHANGE_VOCATION not in engine.permissible_commands()
    in_battle = become_guardian(engine)
    assert not in_battle.accepted and "only between battles" in (in_battle.reason or "")
    shipped = Engine(packaged_content())
    ok(shipped.do(cmd.START_RUN, seed=11, party=[{"class_id": "squire", "row": "front"}, {"class_id": "scout", "row": "back"}]))
    win_battle(shipped)
    assert shipped.permissible_commands() == [cmd.CHOOSE_UPGRADE, cmd.SET_FORMATION], "a run of shipped classes offers what it always did"


@pytest.mark.parametrize("params", [
    {"hero_id": "h01", "class_id": "guardian"},
    {"hero_id": "h01", "class_id": "guardian", "hero": {"name": "No id"}},
    {"hero_id": "h01", "class_id": 7, "hero": GUARDIAN},
    {"hero_id": "h01", "class_id": "guardian", "hero": {**GUARDIAN, "stats": {"luck": 3}}},
    {"hero_id": "h01", "class_id": "guardian", "hero": GUARDIAN, "row": "front"},
])
def test_a_malformed_command_is_refused_before_the_rules_see_it(catalog, params):
    engine = after_battle_one(catalog)
    result = engine.do(cmd.CHANGE_VOCATION, **params)
    assert not result.accepted and cmd.CHANGE_VOCATION in (result.reason or "")
    assert unit(engine, "h01").archetype_id == "squire"


def played_to_the_upgrade(catalog: VocationCatalog, seed: int) -> Engine | None:
    """A real run (every decision a command) up to the mandatory upgrade; ``None`` when Battle 1 is lost."""
    party = [{"class_id": "squire", "row": "front", "hero": {"hero_id": "hero_001", "name": "Aldric"}},
             {"class_id": "scout", "row": "back", "hero": {"hero_id": "hero_002"}}]
    engine = Engine(packaged_content(), catalog)
    ok(engine.do(cmd.START_RUN, seed=seed, party=party, encounters=["training_04"]))
    policy = HeuristicPolicy()
    while not engine.finished() and engine.state.phase != RunPhase.UPGRADE:
        if engine.needs_input():
            policy.act(engine)
        else:
            ok(engine.do(cmd.ADVANCE_PHASE))
    return None if engine.finished() else engine


def test_a_run_with_a_change_replays_from_its_record_and_names_the_catalog(catalog):
    engine = next(e for e in (played_to_the_upgrade(catalog, seed) for seed in range(11, 20)) if e is not None)
    ok(become_guardian(engine))
    play_run(engine, HeuristicPolicy())
    assert engine.finished()
    record = export_run(engine)
    assert record["vocation_catalog"] == {"version": catalog.version, "sha256": catalog.sha256}
    changes = [c for c in record["commands"] if c["type"] == cmd.CHANGE_VOCATION]
    assert len(changes) == 1 and changes[0]["params"]["hero"] == GUARDIAN, "the snapshot is in the log"
    again = verify(packaged_content(), record)
    assert (events_hash(again.events), state_hash(again.state)) == (events_hash(engine.events), state_hash(engine.state))
    assert again.build("h01").vocation_id == "guardian"


def test_a_run_started_with_shipped_classes_names_the_catalog_once_a_hero_evolves(catalog):
    engine = after_battle_one(catalog)
    assert engine.vocation_catalog_pin is None
    ok(become_guardian(engine))
    assert engine.vocation_catalog_pin == {"version": catalog.version, "sha256": catalog.sha256}


# --------------------------------------------------------------------------------------------
# The second moment: the decision to stop or fight on (owner decision of 2026-11-12)
# --------------------------------------------------------------------------------------------


def at_the_decision(catalog: VocationCatalog) -> Engine:
    """Battles 1 and 2 are won, the Squire's Iron d6 carries the upgrade: the run waits for stop or fight on."""
    engine = after_battle_one(catalog, third=True)
    offer = engine.state.upgrade_offers["h01"]["iron_d6"][0]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="iron_d6", offer_id=offer["offer_id"]))
    ok(engine.do(cmd.ADVANCE_PHASE))
    win_battle(engine)
    assert engine.state.phase == RunPhase.CONTINUE and "iron_d6" in engine.state.die_overrides["h01"]
    return engine


def test_at_the_decision_to_stop_or_fight_on_a_hero_may_change_and_no_upgrade_is_dealt(catalog):
    engine = at_the_decision(catalog)
    assert engine.permissible_commands() == [cmd.CONTINUE_RUN, cmd.END_RUN, cmd.SET_FORMATION, cmd.CHANGE_VOCATION]
    squire = unit(engine, "h01")
    hp, mana = squire.hp, squire.mana
    offers, draws = engine.state.upgrade_offers, engine.state.rng["rewards"].draws
    ok(become_guardian(engine))
    guardian = unit(engine, "h01")
    assert (guardian.archetype_id, guardian.max_hp, guardian.equipped_dice_ids) == ("guardian", 18, ["guardian_d6", "guardian_d4"])
    assert guardian.hp == convert_pool(hp, 14, 18) and guardian.mana == convert_pool(mana, 3, 3)
    assert engine.state.upgrade_offers == offers and engine.state.rng["rewards"].draws == draws, "no cards are dealt at this moment"
    assert "h01" not in engine.state.die_overrides, "the upgraded Iron d6 left, and its upgrade with it"
    assert engine.state.phase == RunPhase.CONTINUE
    event = events_of(engine, EventType.VOCATION_CHANGED)[-1]
    assert event.delta["offers"] == {} and (event.delta["from"], event.delta["to"]) == ("squire", "guardian")
    assert describe_event(event, {"h01": "Aldric"}).endswith(f"mana {mana}/3 -> {guardian.mana}/3, new dice.")
    ok(engine.do(cmd.CONTINUE_RUN))
    assert engine.state.encounter_index == 2 and unit(engine, "h01").archetype_id == "guardian"
    assert unit(engine, "h01").equipped_dice_ids == ["guardian_d6", "guardian_d4"]
    in_battle = become_guardian(engine, class_id="squire", hero={"hero_id": "hero_001"})
    assert not in_battle.accepted and "only between battles" in (in_battle.reason or "")
    play_run(engine, HeuristicPolicy())
    assert engine.finished()


def test_a_run_may_also_end_with_its_victory_after_a_change_at_the_decision(catalog):
    engine = at_the_decision(catalog)
    ok(become_guardian(engine))
    ok(engine.do(cmd.END_RUN))
    assert engine.finished() and engine.state.outcome == "victory" and engine.build("h01").vocation_id == "guardian"


def test_a_run_of_shipped_classes_is_offered_nothing_new_at_the_decision(catalog):
    engine = Engine(packaged_content(), catalog)
    ok(engine.do(cmd.START_RUN, seed=11, party=[{"class_id": "squire", "row": "front"}, {"class_id": "scout", "row": "back"}], encounters=["training_04"]))
    win_battle(engine)
    offer = engine.state.upgrade_offers["h01"]["iron_d6"][0]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="iron_d6", offer_id=offer["offer_id"]))
    ok(engine.do(cmd.ADVANCE_PHASE))
    win_battle(engine)
    assert engine.permissible_commands() == [cmd.CONTINUE_RUN, cmd.END_RUN, cmd.SET_FORMATION]


def test_a_really_played_run_with_a_change_at_the_decision_replays(catalog):
    for seed in range(11, 40):
        engine = played_to_the_upgrade(catalog, seed)
        if engine is None:
            continue
        policy = HeuristicPolicy()
        while not engine.finished() and engine.state.phase != RunPhase.CONTINUE:
            if engine.needs_input():
                policy.act(engine)
            else:
                ok(engine.do(cmd.ADVANCE_PHASE))
        if not engine.finished():
            break
    else:
        raise AssertionError("no seed reached the decision")
    ok(become_guardian(engine))
    play_run(engine, HeuristicPolicy())
    record = export_run(engine)
    again = verify(packaged_content(), record)
    assert (events_hash(again.events), state_hash(again.state)) == (events_hash(engine.events), state_hash(engine.state))
    assert [c["type"] for c in record["commands"]].count(cmd.CHANGE_VOCATION) == 1 and again.build("h01").vocation_id == "guardian"


# --------------------------------------------------------------------------------------------
# Rules 1.1.2 (owner decision D-34): a change back and forth gains nothing
# --------------------------------------------------------------------------------------------

AS_SQUIRE = {"hero_id": "hero_001", "name": "Aldric"}


def change(engine: Engine, class_id: str):
    return engine.do(cmd.CHANGE_VOCATION, hero_id="h01", class_id=class_id, hero=GUARDIAN if class_id == "guardian" else AS_SQUIRE)


def pools(engine: Engine) -> tuple[int, int, int, int]:
    hero = unit(engine, "h01")
    return hero.hp, hero.max_hp, hero.mana, hero.max_mana


def test_changing_back_and_forth_does_not_heal(catalog):
    """Found by a playtester: 12/15 became 18/18 by changing four times. Each change rounded up from the last result."""
    engine = after_battle_one(catalog)
    hero = unit(engine, "h01")
    hero.hp, hero.mana = 10, 1  # of 14 and 3
    start = pools(engine)
    ok(change(engine, "guardian"))
    as_guardian = pools(engine)
    assert as_guardian == (convert_pool(10, 14, 18), 18, convert_pool(1, 3, 3), 3) == (13, 18, 1, 3)
    for _ in range(4):
        ok(change(engine, "squire"))
        assert pools(engine) == start, "back as a Squire the hero has exactly what it had"
        ok(change(engine, "guardian"))
        assert pools(engine) == as_guardian, "and as a Guardian what the first change gave it"
    # Under rules 1.1.1 the second round already gave 13/18 -> 11/14 -> 15/18.
    assert convert_pool(convert_pool(13, 18, 14), 14, 18) == 15 > 13


def test_the_window_remembers_what_the_hero_had_and_forgets_it_when_it_closes(catalog):
    engine = after_battle_one(catalog)
    hero = unit(engine, "h01")
    hero.hp, hero.mana = 10, 1
    assert engine.state.change_base == {}
    ok(change(engine, "guardian"))
    assert engine.state.change_base == {"h01": {"hp": 10, "max_hp": 14, "mana": 1, "max_mana": 3}}
    ok(change(engine, "squire"))
    assert engine.state.change_base["h01"]["hp"] == 10, "the first change of the window sets it; later ones do not move it"
    ok(change(engine, "guardian"))
    offer = engine.state.upgrade_offers["h01"]["guardian_d6"][0]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="guardian_d6", offer_id=offer["offer_id"]))
    assert engine.state.change_base == {}, "the upgrade is chosen: the window is closed"


def test_each_window_starts_from_the_health_of_its_own_moment(catalog):
    engine = at_the_decision(catalog)
    hero = unit(engine, "h01")
    hero.hp = 7
    assert engine.state.change_base == {}
    ok(change(engine, "guardian"))
    assert pools(engine)[:2] == (convert_pool(7, 14, 18), 18) and engine.state.change_base["h01"]["hp"] == 7
    ok(change(engine, "squire"))
    assert pools(engine)[:2] == (7, 14)
    ok(change(engine, "guardian"))
    ok(engine.do(cmd.CONTINUE_RUN))
    assert engine.state.phase == RunPhase.BATTLE and engine.state.change_base == {}


def test_ending_the_run_at_the_decision_also_closes_the_window(catalog):
    engine = at_the_decision(catalog)
    ok(change(engine, "guardian"))
    assert engine.state.change_base
    ok(engine.do(cmd.END_RUN))
    assert engine.state.change_base == {}


def test_a_run_without_a_change_has_the_state_it_always_had(catalog):
    """The new field is absent from the hashed state while it is empty, so no run without a change hashes differently."""
    from battle_dice.core.models import to_plain

    engine = after_battle_one(catalog)
    assert "change_base" not in to_plain(engine.state)
    health = unit(engine, "h01").hp
    ok(change(engine, "guardian"))
    assert to_plain(engine.state)["change_base"] == {"h01": {"hp": health, "max_hp": 14, "mana": 3, "max_mana": 3}}


def test_the_preview_and_the_change_agree_after_a_change_back(catalog):
    engine = after_battle_one(catalog)
    unit(engine, "h01").hp = 10
    ok(change(engine, "guardian"))
    ok(change(engine, "squire"))
    promised = engine.pools_after_change("h01", 18, 3)
    ok(change(engine, "guardian"))
    assert promised["hp"] == [10, 13] and pools(engine)[:2] == (promised["hp"][1], 18)
    assert events_of(engine, EventType.VOCATION_CHANGED)[-1].delta["hp"] == [10, 13]


def test_a_run_with_changes_back_and_forth_replays_from_its_record(catalog):
    engine = next(e for e in (played_to_the_upgrade(catalog, seed) for seed in range(11, 20)) if e is not None)
    for class_id in ("guardian", "squire", "guardian"):
        ok(change(engine, class_id))
    play_run(engine, HeuristicPolicy())
    assert engine.finished()
    record = export_run(engine)
    assert [c["params"]["class_id"] for c in record["commands"] if c["type"] == cmd.CHANGE_VOCATION] == ["guardian", "squire", "guardian"]
    again = verify(packaged_content(), record)
    assert (events_hash(again.events), state_hash(again.state)) == (events_hash(engine.events), state_hash(engine.state))


def test_mana_is_converted_from_what_the_hero_had_too(catalog):
    """A Squire with 1 of 3 mana, a Scout (4 mana at most) and back: under rules 1.1.1 it came back with 2."""
    engine = after_battle_one(catalog)
    unit(engine, "h01").mana = 1
    ok(change(engine, "scout"))
    assert pools(engine)[2:] == (convert_pool(1, 3, 4), 4) == (2, 4)
    ok(change(engine, "squire"))
    assert pools(engine)[2:] == (1, 3) and convert_pool(2, 4, 3) == 2, "not the 2 that rounding up twice would give"
