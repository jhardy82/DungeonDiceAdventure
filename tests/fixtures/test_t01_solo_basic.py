"""T01_solo_basic: 1 Squire versus 1 Goblin, correct gauge and melee rules."""

from battle_dice.core import commands as cmd
from battle_dice.core.engine import run_until_input
from battle_dice.core.models import CombatPhase
from tests.conftest import action, events_of, ok, resolve_hero, roll, skip_reactions, start, unit


def test_t01_roster_is_one_goblin_for_a_solo_party():
    engine = start("squire")
    roster = events_of(engine, "battle_started")[0].delta["roster"]
    assert [(r["id"], r["archetype"], r["row"], r["hp"]) for r in roster] == [
        ("b1_e01", "goblin", "front", 6),
        ("h01", "squire", "front", 14),
    ]


def test_t01_gauge_sequence_and_melee_exchange():
    engine = start("squire")
    activations: list[tuple[int, str]] = []
    while len(activations) < 4:
        run_until_input(engine)
        phase = engine.combat.phase
        if phase == CombatPhase.HERO_ROLL:
            roll(engine, iron_d6=1, oath_d4=1)
            resolve_hero(engine, action("iron_d6", "b1_e01"))
        elif phase in CombatPhase.STAGE_BY_WINDOW:
            skip_reactions(engine)
        activations = [(e.tick, e.actor_id) for e in events_of(engine, "activation_started")]
    # Goblin speed 10 reaches 100 at tick 10; Squire speed 7 reaches 105 at tick 15 and keeps 5 overflow.
    assert activations[:4] == [(10, "b1_e01"), (15, "h01"), (20, "b1_e01"), (29, "h01")]
    first_hero = [e for e in events_of(engine, "activation_started") if e.actor_id == "h01"][0]
    assert first_hero.delta["gauge_after"] == 5
    # The Goblin opened with Dirty Trick (Weaken), so the first Strike dealt 2 - 1 = 1.
    strikes = [e for e in events_of(engine, "action_resolved") if e.actor_id == "h01"]
    assert strikes[0].delta["results"][0]["effective"] == 1
    assert unit(engine, "b1_e01").hp < 6


def test_t01_melee_reaches_a_lone_back_row_hero():
    engine = start("squire:back")
    run_until_input(engine)
    skip_reactions(engine)
    run_until_input(engine)
    hero = unit(engine, "h01")
    assert hero.row == "back"
    assert hero.stacks_of("weaken") == 1  # the Goblin opened with its ranged Dirty Trick
    ok(engine.do(cmd.ROLL_DICE))
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[]))
    ok(engine.do(cmd.COMMIT_ACTION_PLAN))
    # Second Goblin activation: Weaken is present, so Slash (melee) is in the tier. Force it.
    engine.force_draws("enemy", [1])
    run_until_input(engine)
    skip_reactions(engine)
    run_until_input(engine)
    slash = [e for e in events_of(engine, "action_resolved") if e.delta["name"] == "Slash"]
    assert slash and slash[0].delta["target_ids"] == ["h01"]  # no standing front row: melee reaches the back row
    assert unit(engine, "h01").hp == 12
