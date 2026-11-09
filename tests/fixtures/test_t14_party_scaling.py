"""T14_party_scaling: all five party-size encounter configurations load and terminate."""

import pytest

from battle_dice.core import commands as cmd
from battle_dice.core.models import RunPhase
from battle_dice.sim.policies import HeuristicPolicy, play_run
from tests.conftest import enemies, ok, start, win_battle
from tests.unit.test_content import EXPECTED_ENCOUNTERS

PARTIES = {
    1: ("squire",),
    2: ("squire", "scout"),
    3: ("squire", "apprentice", "scout"),
    4: ("squire", "squire", "apprentice", "scout"),
    5: ("squire", "squire", "apprentice", "apprentice", "scout"),
}


@pytest.mark.parametrize("size", sorted(PARTIES))
def test_t14_both_battles_use_the_exact_roster_for_the_party_size(size):
    battle1, battle2, captain_hp, strike = EXPECTED_ENCOUNTERS[size]
    engine = start(*PARTIES[size])
    assert engine.combat.encounter_id == f"p{size}_b1"
    assert [e.archetype_id for e in enemies(engine)] == battle1
    win_battle(engine)
    offers = engine.state.upgrade_offers["h01"]
    die_id = sorted(offers)[0]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id=die_id, offer_id=offers[die_id][0]["offer_id"]))
    ok(engine.do(cmd.ADVANCE_PHASE))
    assert engine.combat.encounter_id == f"p{size}_b2"
    foes = enemies(engine)
    assert [e.archetype_id for e in foes] == battle2
    assert (foes[0].hp, foes[0].max_hp) == (captain_hp, captain_hp)
    assert engine.enemy_action(foes[0], "strike").power == strike
    win_battle(engine)
    assert engine.state.phase == RunPhase.VICTORY and engine.state.outcome == "victory"


@pytest.mark.parametrize("size", sorted(PARTIES))
def test_t14_every_party_size_terminates_under_play(size):
    engine = start(*PARTIES[size], seed=100 + size)
    outcome = play_run(engine, HeuristicPolicy())
    assert outcome in ("victory", "defeat")
    assert engine.finished()
    assert not engine.do(cmd.ADVANCE_PHASE).accepted
