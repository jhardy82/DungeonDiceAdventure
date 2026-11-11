"""The Guardian, the first evolved vocation of the Squire family, under the rules (Phase 4, step A).

Its passive Bulwark is the one thing the engine lacked: +1 shield on a Defense die action that
targets another ally. Never on the Guardian itself, never on a reaction. The numbers are the
catalog's v0.1 numbers; they are measured against the Squire before any of them is changed.
"""

from __future__ import annotations

import pytest

from battle_dice.content.vocations import VocationCatalog, load_catalog, load_vocation_catalog, vocation_gaps
from battle_dice.core import commands as cmd
from battle_dice.core import effects
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType, events_hash, state_hash
from battle_dice.core.models import CombatPhase
from battle_dice.core.replay import export_run, verify
from battle_dice.sim.policies import HeuristicPolicy, RandomPolicy
from tests.conftest import (
    action,
    begin_enemy,
    begin_hero,
    commit,
    events_of,
    finish_activation,
    force_slash,
    ok,
    packaged_content,
    unit,
)
from tests.integration.test_full_runs import play_checked

PARTIES_WITH_A_GUARDIAN = [
    [("guardian", "front")],
    [("guardian", "front"), ("scout", "back")],
    [("guardian", "front"), ("apprentice", "back"), ("ranger", "back")],
    [("guardian", "front"), ("squire", "front"), ("scout", "back"), ("apprentice", "back")],
    [("guardian", "front"), ("guardian", "front"), ("scout", "back"), ("apprentice", "back"), ("ranger", "back")],
]


@pytest.fixture(scope="module")
def catalog() -> VocationCatalog:
    return load_vocation_catalog(packaged_content())


def started(catalog: VocationCatalog, seed: int, members: list[tuple[str, str]]) -> Engine:
    engine = Engine(packaged_content(), catalog)
    ok(engine.do(cmd.START_RUN, seed=seed, party=[{"class_id": c, "row": r} for c, r in members]))
    return engine


def shields_gained(engine: Engine) -> list[dict]:
    return [r for e in events_of(engine, EventType.ACTION_RESOLVED) for r in e.delta["results"] if r["type"] == "shield"]


# --------------------------------------------------------------------------------------------
# The build
# --------------------------------------------------------------------------------------------


def test_the_guardian_build_is_the_catalog_entry(catalog):
    guardian = catalog.build("guardian")
    raw = next(v for v in load_catalog()["vocations"] if v["id"] == "guardian")
    assert vocation_gaps(load_catalog(), raw) == [] and "guardian" not in catalog.unsupported
    assert (guardian.vocation_id, guardian.name, guardian.upgrade_family) == ("guardian", "Guardian", "squire")
    for name in ("max_hp", "start_hp", "speed", "base_initiative", "max_mana", "start_mana", "rerolls", "dice_capacity"):
        assert getattr(guardian, name) == raw[name], name
    assert guardian.starting_dice == ("guardian_d6", "guardian_d4") and guardian.bench_dice == ()
    assert guardian.schedule.label == "Single Commitment" and guardian.schedule.max_actions == 1
    assert guardian.passive == {"id": "bulwark", "name": "Bulwark", "type": "ally_defense_die_bonus", "amount": 1,
                                "summary": guardian.passive["summary"]}
    assert guardian.reaction_id == "rx_guardian_ward" and guardian.reaction["effects"] == [{"type": "shield", "target": "target", "amount": 3}]
    # The shipped Squire is untouched by any of this.
    squire = catalog.build("squire")
    assert squire.passive["type"] == "defense_die_bonus" and squire.reaction_id == "interpose"


# --------------------------------------------------------------------------------------------
# Bulwark: another ally, not itself, not a reaction
# --------------------------------------------------------------------------------------------


def test_bulwark_adds_one_shield_on_another_ally(catalog):
    engine = started(catalog, 1, [("guardian", "front"), ("scout", "back")])
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=1)  # Guard 3 and Heavy Guard 4
    printed = engine.die_for("h01", "guardian_d6").faces[0].power
    commit(engine, action("guardian_d6", "h02"))
    finish_activation(engine)
    (gain,) = shields_gained(engine)
    assert (gain["target"], gain["bonus"], gain["gained"]) == ("h02", 1, printed + 1) == ("h02", 1, 5)
    assert unit(engine, "h02").shields == 5 and unit(engine, "h01").shields == 0


def test_bulwark_adds_nothing_on_the_guardian_itself(catalog):
    engine = started(catalog, 1, [("guardian", "front"), ("scout", "back")])
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=1)
    commit(engine, action("guardian_d6", "h01"))
    finish_activation(engine)
    (gain,) = shields_gained(engine)
    assert (gain["target"], gain["bonus"], gain["gained"]) == ("h01", 0, 4)
    assert unit(engine, "h01").shields == 4


def test_a_squire_in_the_same_party_keeps_its_own_bonus_on_itself(catalog):
    engine = started(catalog, 1, [("guardian", "front"), ("squire", "front")])
    begin_hero(engine, "h02", iron_d6=3, oath_d4=1)  # the Squire's Guard 3
    commit(engine, action("iron_d6", "h02"))
    finish_activation(engine)
    (gain,) = shields_gained(engine)
    assert (gain["target"], gain["bonus"], gain["gained"]) == ("h02", 1, 4)


def test_bulwark_applies_to_defense_dice_only(catalog):
    """Not to the heal on the same die, and not when the roll is an attack."""
    engine = started(catalog, 1, [("guardian", "front"), ("scout", "back")])
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=5)  # Heal 2 (1 mana)
    guardian, ally = unit(engine, "h01"), unit(engine, "h02")
    heal = engine.die_for("h01", "guardian_d6").faces[4]
    guard = engine.die_for("h01", "guardian_d6").faces[0]
    turn = engine.combat.turn
    assert turn is not None
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("guardian_d6", "h02")]))
    intent = engine.combat.turn.plan[0]
    assert effects.shield_bonus(engine, guardian, heal, ally, intent) == 0
    assert effects.shield_bonus(engine, guardian, guard, ally, intent) == 1
    assert effects.shield_bonus(engine, guardian, guard, guardian, intent) == 0
    assert effects.shield_bonus(engine, guardian, guard, ally, None) == 0  # no die action: a reaction


def test_guardian_ward_gives_exactly_its_three_shield(catalog):
    """A reaction is not a Defense die action, so Bulwark adds nothing to it."""
    engine = started(catalog, 1, [("guardian", "front"), ("scout", "back")])
    enemy = engine.combat.side("enemy")[0].id
    force_slash(engine)  # a damaging action: the guard stage only opens against damage
    begin_enemy(engine, enemy)
    assert engine.combat.phase == CombatPhase.GUARD_WINDOW and engine.combat.committed_intent is not None
    assert engine.combat.committed_intent.name == "Slash"
    target = engine.combat.committed_intent.committed_target_ids[0]
    before = unit(engine, target).shields
    ok(engine.do(cmd.USE_REACTION, hero_id="h01", target_id=target))
    used = events_of(engine, EventType.REACTION_USED)[-1]
    assert used.actor_id == "h01" and unit(engine, target).shields == before + 3
    assert [r["gained"] for r in used.delta["results"] if r["type"] == "shield"] == [3]


# --------------------------------------------------------------------------------------------
# The simulated player knows the passive
# --------------------------------------------------------------------------------------------


def test_the_simulated_player_values_a_guard_higher_only_when_there_is_an_ally(catalog):
    policy = HeuristicPolicy()
    alone = started(catalog, 1, [("guardian", "front")])
    paired = started(catalog, 1, [("guardian", "front"), ("scout", "back")])
    values = []
    for engine in (alone, paired):
        guard = engine.die_for("h01", "guardian_d6").faces[0]
        values.append(policy._face_value(engine, unit(engine, "h01"), guard))
    assert values[1] == values[0] + 0.5  # one more shield, at the player's weight of a half per shield
    strike = paired.die_for("h01", "guardian_d6").faces[3]
    assert policy._face_value(paired, unit(paired, "h01"), strike) == policy._face_value(alone, unit(alone, "h01"), strike)


# --------------------------------------------------------------------------------------------
# Whole runs
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(10))
def test_a_party_with_a_guardian_plays_to_an_outcome_with_every_invariant_held(catalog, seed):
    members = PARTIES_WITH_A_GUARDIAN[seed % len(PARTIES_WITH_A_GUARDIAN)]
    policy = HeuristicPolicy() if seed % 2 == 0 else RandomPolicy(seed)
    engine = started(catalog, seed, members)
    assert play_checked(engine, policy) in ("victory", "defeat")
    assert "guardian" in {engine.build(h.id).vocation_id for h in engine.combat.side("hero")}


def test_a_run_with_a_guardian_replays_exactly_and_pins_the_catalog(catalog):
    engine = started(catalog, 4, PARTIES_WITH_A_GUARDIAN[2])
    play_checked(engine, HeuristicPolicy())
    record = export_run(engine)
    assert record["vocation_catalog"] == {"version": catalog.version, "sha256": catalog.sha256}
    again = verify(packaged_content(), record)
    assert (events_hash(again.events), state_hash(again.state)) == (events_hash(engine.events), state_hash(engine.state))
    bonus_seen = [r for r in shields_gained(engine) if r.get("bonus")]
    assert bonus_seen, "over a whole run the Guardian shielded an ally at least once"


def test_without_the_catalog_a_guardian_is_an_unknown_class():
    engine = Engine(packaged_content())
    result = engine.do(cmd.START_RUN, seed=1, party=[{"class_id": "guardian", "row": "front"}])
    assert not result.accepted and "Unknown class 'guardian'" in (result.reason or "")
