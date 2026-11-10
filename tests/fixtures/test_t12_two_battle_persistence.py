"""T12_two_battle_persistence: recovery, mana refill, corruption carry, shield/status clearing."""

from battle_dice.core import commands as cmd
from battle_dice.core.engine import run_until_input
from battle_dice.core.models import CombatPhase, RunPhase
from tests.conftest import add_status, down, events_of, last_event, ok, start, unit, win_battle


def _arrange_and_win():
    engine = start("squire", "apprentice", "scout")
    squire, apprentice, scout = unit(engine, "h01"), unit(engine, "h02"), unit(engine, "h03")
    squire.hp, squire.shields, squire.mana, squire.corruption = 5, 4, 0, 2
    down(engine, "h02")
    apprentice.corruption, apprentice.mana = 3, 0
    scout.shields, scout.mana, scout.gauge = 2, 0, 77
    add_status(engine, "h03", "poison")
    add_status(engine, "h03", "weaken")
    add_status(engine, "h03", "speed_up", stacks=2)
    scout.reaction_charges = 0
    win_battle(engine)
    return engine


def test_t12_recovery_table_is_applied_exactly():
    engine = _arrange_and_win()
    assert engine.state.phase == RunPhase.UPGRADE and engine.combat.outcome == "victory"
    squire, apprentice, scout = unit(engine, "h01"), unit(engine, "h02"), unit(engine, "h03")
    # Standing heroes heal ceil(30% of max HP); downed heroes stand at ceil(50% of max HP).
    assert squire.hp == 5 + 5  # ceil(14 * 0.30) = 5
    assert (apprentice.state, apprentice.hp) == ("standing", 5)  # ceil(9 * 0.50) = 5
    assert scout.hp == 10  # capped at max
    assert [h.max_hp for h in (squire, apprentice, scout)] == [14, 9, 10]
    assert [h.shields for h in (squire, apprentice, scout)] == [0, 0, 0]
    assert [h.mana for h in (squire, apprentice, scout)] == [3, 6, 4]  # refilled to class maximum
    assert [h.corruption for h in (squire, apprentice, scout)] == [2, 3, 0]  # corruption persists
    assert scout.status_instances == [] and scout.gauge == 0 and scout.reaction_charges == 1
    report = last_event(engine, "recovery_applied").delta["heroes"]
    assert [(r["id"], r["was_downed"], r["hp_after"]) for r in report] == [("h01", False, 10), ("h02", True, 5), ("h03", False, 10)]


def test_t12_state_carries_into_battle_two():
    engine = _arrange_and_win()
    offer = engine.state.upgrade_offers["h01"]["iron_d6"][0]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="iron_d6", offer_id=offer["offer_id"]))
    ok(engine.do(cmd.ADVANCE_PHASE))
    assert engine.state.phase == RunPhase.BATTLE and engine.state.encounter_index == 1
    assert engine.combat.encounter_id == "p3_b2" and engine.combat.timeline_tick == 0
    roster = events_of(engine, "battle_started")[-1].delta["roster"]
    assert [(r["id"], r["archetype"]) for r in roster if r["side"] == "enemy"] == [
        ("b2_e01", "captain"), ("b2_e02", "goblin"), ("b2_e03", "hex_adept"),
    ]
    heroes = engine.combat.side("hero")
    assert [(h.hp, h.mana, h.corruption, h.shields, h.gauge) for h in heroes] == [
        (10, 3, 2, 0, 0), (5, 6, 3, 0, 0), (10, 4, 0, 0, 0),
    ]
    assert all(c.gauge == 0 for c in engine.combat.combatants.values())
    assert engine.die_for("h01", "iron_d6").definition_version == 2  # the upgrade persists into Battle 2
    seqs = [e.seq for e in engine.events]
    assert seqs == list(range(1, len(seqs) + 1))  # one continuous event sequence across both battles

    run_until_input(engine)
    while engine.combat.phase != CombatPhase.HERO_ROLL:
        ok(engine.do(cmd.SKIP_REACTION_STAGE))
        run_until_input(engine)
    assert engine.combat.turn.rerolls_remaining == 2  # per-activation rerolls reset to the class baseline


def test_t12_formation_can_change_between_battles_only():
    engine = _arrange_and_win()
    ok(engine.do(cmd.SET_FORMATION, hero_id="h03", row="front"))
    assert unit(engine, "h03").row == "front"
    assert [m["row"] for m in engine.state.party] == ["front", "back", "front"]
    offer = engine.state.upgrade_offers["h01"]["iron_d6"][0]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="iron_d6", offer_id=offer["offer_id"]))
    ok(engine.do(cmd.SET_FORMATION, hero_id="h03", row="back"))
    ok(engine.do(cmd.ADVANCE_PHASE))
    assert not engine.do(cmd.SET_FORMATION, hero_id="h03", row="front").accepted
