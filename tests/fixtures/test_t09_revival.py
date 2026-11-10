"""T09_revival: Rally and Mend legal; ordinary Heal illegal for downed; gauge reset after revival."""

from battle_dice.core import commands as cmd
from battle_dice.core import reactions, timeline
from tests.conftest import (
    action,
    add_status,
    begin_enemy,
    begin_hero,
    down,
    force_slash,
    last_event,
    rejected,
    resolve_hero,
    start,
    unit,
)


def test_t09_squire_rally_revives_to_two_hp_with_gauge_reset():
    engine = start("squire", "apprentice", "scout")
    scout = unit(engine, "h03")
    down(engine, "h03")
    add_status(engine, "h03", "weaken")
    begin_hero(engine, "h01", iron_d6=5, oath_d4=1)
    unit(engine, "h03").gauge = 60  # arrange: stale gauge from before it was downed
    resolve_hero(engine, action("iron_d6", "h03"))
    assert (scout.state, scout.hp, scout.gauge) == ("standing", 2, 0)
    assert unit(engine, "h01").mana == 1
    assert scout.stacks_of("weaken") == 1  # revival does not cleanse statuses
    assert last_event(engine, "hero_revived").delta == {"id": "h03", "hp": 2}
    timeline.tick(engine.combat, engine.content.balance)
    assert scout.gauge == 13  # resumes accumulating on the next tick


def test_t09_apprentice_mend_revives_to_three_hp():
    engine = start("squire", "apprentice", "scout")
    down(engine, "h01")
    begin_hero(engine, "h02", arcane_d6=3, focus_d4=4)
    resolve_hero(engine, action("arcane_d6", "h01"))
    squire = unit(engine, "h01")
    assert (squire.state, squire.hp, squire.gauge) == ("standing", 3, 0)
    assert unit(engine, "h02").mana == 1  # 3 - 2


def test_t09_revival_needs_mana_and_a_standing_caster():
    engine = start("squire", "apprentice")
    down(engine, "h01")
    unit(engine, "h02").mana = 1
    begin_hero(engine, "h02", arcane_d6=3, focus_d4=3)
    rejected(engine.do(cmd.SET_ACTION_PLAN, actions=[action("arcane_d6", "h01")]), "needs 2 mana")


def test_t09_ordinary_healing_cannot_target_a_downed_ally():
    engine = start("squire", "scout")
    unit(engine, "h01").equipped_dice_ids = ["bulwark_d4", "iron_d6"]
    down(engine, "h02")
    begin_hero(engine, "h01", bulwark_d4=3, iron_d6=6)
    reason = rejected(engine.do(cmd.SET_ACTION_PLAN, actions=[action("bulwark_d4", "h02")]), "downed")
    assert "revival-capable" in reason
    unit(engine, "h01").hp = 10
    resolve_hero(engine, action("bulwark_d4", "h01"))
    assert unit(engine, "h01").hp == 11  # ordinary healing still works on a standing ally


def test_t09_scout_has_no_revival_and_downed_heroes_cannot_react(content):
    scout_faces = [f for die_id in ("striker_d8", "tools_d4", "venom_d4") for f in content.die(die_id).faces]
    assert not any(f.can_revive for f in scout_faces)

    engine = start("squire", "squire", "scout")
    force_slash(engine, "h01")
    force_slash(engine, "h02")
    down(engine, "h01")
    down(engine, "h03")
    begin_enemy(engine, "b1_e01")
    guard = {o["hero_id"]: o for o in reactions.stage_options(engine, "guard")}
    assert guard["h01"]["reason"] == "Downed heroes cannot react." and guard["h02"]["eligible"]
    assert reactions.stage_options(engine, "interrupt")[0]["reason"] == "Downed heroes cannot react."
    assert engine.combat.committed_intent.committed_target_ids == ["h02"]  # downed heroes are not targeted
