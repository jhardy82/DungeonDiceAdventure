"""T04_apprentice_channel: mana Resource action before a costed spell; atomic failure when the channel is invalid."""

from battle_dice.core import commands as cmd
from battle_dice.core.events import state_hash
from battle_dice.core.models import CombatPhase
from tests.conftest import (
    action,
    begin_hero,
    commit,
    events_of,
    last_event,
    rejected,
    resolve_hero,
    start,
    step,
    step_to,
    unit,
)


def test_t04_channel_then_cast_in_one_activation():
    engine = start("apprentice")
    hero = unit(engine, "h01")
    hero.mana = 0
    begin_hero(engine, "h01", arcane_d6=1, focus_d4=1)
    resolve_hero(engine, action("arcane_d6", "b1_e01"), action("focus_d4"))
    assert [e.delta["name"] for e in events_of(engine, "action_resolved")] == ["Channel", "Arcane Bolt"]
    assert hero.mana == 1  # 0 + 2 channelled - 1 spent
    assert hero.corruption == 2  # starts at 1, the spell adds 1
    assert unit(engine, "b1_e01").hp == 3
    assert events_of(engine, "action_resolved")[1].delta["mana_spent"] == 1


def test_t04_spell_without_mana_is_rejected_atomically():
    engine = start("apprentice")
    unit(engine, "h01").mana = 0
    begin_hero(engine, "h01", arcane_d6=1, focus_d4=3)  # Arcane Bolt + Ward: no channel available
    before = (state_hash(engine.state), len(engine.events))
    rejected(engine.do(cmd.SET_ACTION_PLAN, actions=[action("arcane_d6", "b1_e01")]), "needs 1 mana")
    rejected(
        engine.do(cmd.SET_ACTION_PLAN, actions=[action("focus_d4", "h01"), action("arcane_d6", "b1_e01")]),
        "only allowed as resource first",
    )
    assert (state_hash(engine.state), len(engine.events)) == before


def test_t04_cast_cannot_inherit_mana_it_did_not_receive():
    engine = start("apprentice")
    hero = unit(engine, "h01")
    hero.mana = 0
    begin_hero(engine, "h01", arcane_d6=1, focus_d4=1)
    commit(engine, action("focus_d4"), action("arcane_d6", "b1_e01"))
    step_to(engine, CombatPhase.ACTION_RESOLVE)
    step(engine)  # Channel resolves: +2 mana
    assert hero.mana == 2
    hero.mana = 0  # arrange: the channelled mana is gone before the spell is revalidated
    corruption_before = hero.corruption
    step(engine)
    cancelled = last_event(engine, "action_cancelled")
    assert cancelled.delta["name"] == "Arcane Bolt" and "insufficient mana" in cancelled.delta["reason"]
    assert cancelled.delta["cost_spent"] == 0
    # Atomic: no cost, no damage, no rider corruption.
    assert (hero.mana, hero.corruption, unit(engine, "b1_e01").hp) == (0, corruption_before, 6)
