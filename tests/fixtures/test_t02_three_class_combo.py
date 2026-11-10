"""T02_three_class_combo: Squire, Apprentice, Scout: distinct action scheduling and seeded dice."""

from battle_dice.core import commands as cmd
from battle_dice.core.engine import run_until_input
from battle_dice.core.models import CombatPhase
from battle_dice.core.view import snapshot
from tests.conftest import action, begin_hero, events_of, ok, resolve_hero, start, unit


def test_t02_each_class_schedules_differently_in_one_battle():
    engine = start("squire", "apprentice", "scout")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    resolve_hero(engine, action("iron_d6", "b1_e01"))
    begin_hero(engine, "h02", arcane_d6=1, focus_d4=1)
    resolve_hero(engine, action("focus_d4"), action("arcane_d6", "b1_e01"))
    begin_hero(engine, "h03", striker_d8=4, tools_d4=1)
    resolve_hero(engine, action("striker_d8", "b1_e02"), action("tools_d4", "b1_e02"))

    committed = {e.actor_id: e.delta["actions"] for e in events_of(engine, "plan_committed")}
    assert [len(committed[h]) for h in ("h01", "h02", "h03")] == [1, 2, 2]
    assert [a["category"] for a in committed["h02"]] == ["resource", "attack"]
    assert [a["category"] for a in committed["h03"]] == ["status", "attack"]
    assert unit(engine, "b1_e01").hp == 6 - 2 - 3
    assert unit(engine, "b1_e02").hp == 6 - 2 and unit(engine, "b1_e02").stacks_of("poison") == 1

    profiles = {c["id"]: (c["scheduling"]["label"], c["scheduling"]["max_actions"]) for c in snapshot(engine)["combatants"] if c["side"] == "hero"}
    assert profiles == {"h01": ("Single Commitment", 1), "h02": ("Channel and Cast", 2), "h03": ("Exploit Combo", 2)}


def test_t02_seeded_dice_are_identical_across_runs():
    def first_rolls(seed):
        engine = start("squire", "apprentice", "scout", seed=seed)
        rolls: dict[str, dict[str, int]] = {}
        while len(rolls) < 3:
            run_until_input(engine)
            if engine.combat.phase == CombatPhase.HERO_ROLL:
                ok(engine.do(cmd.ROLL_DICE))
                active = engine.combat.active_combatant_id
                assert active is not None
                rolls.setdefault(active, dict(engine.combat.turn.rolled))
                ok(engine.do(cmd.SET_ACTION_PLAN, actions=[]))
                ok(engine.do(cmd.COMMIT_ACTION_PLAN))
            else:
                ok(engine.do(cmd.SKIP_REACTION_STAGE))
        return rolls

    assert first_rolls(2026) == first_rolls(2026)
    assert set(first_rolls(2026)) == {"h01", "h02", "h03"}
