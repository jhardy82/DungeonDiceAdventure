"""T05_reaction_stages: Guard -> Resource -> Interrupt -> enemy, with correct usage and charge accounting."""

from battle_dice.core import commands as cmd
from battle_dice.core.models import CombatPhase
from battle_dice.core.view import snapshot
from tests.conftest import (
    add_status,
    begin_enemy,
    begin_hero,
    captain_content,
    enemy_acts,
    events_of,
    finish_activation,
    force_slash,
    last_event,
    ok,
    rejected,
    skip_reactions,
    start,
    step,
    unit,
)


def _party():
    engine = start("squire", "apprentice", "scout")  # two goblins (b1_e01, b1_e02) and a hex adept (b1_e03)
    force_slash(engine, "h01")
    return engine


def test_t05_full_stage_sequence_with_all_three_archetypes():
    engine = _party()
    squire, apprentice, scout = unit(engine, "h01"), unit(engine, "h02"), unit(engine, "h03")
    squire.corruption = 2
    begin_enemy(engine, "b1_e01")
    assert engine.combat.phase == CombatPhase.GUARD_WINDOW
    assert engine.combat.committed_intent.name == "Slash"  # intent is committed before any reaction

    view = snapshot(engine)["reaction"]
    assert view["stage"] == "guard"
    assert [(o["hero_id"], o["name"], o["eligible"], o["mana_cost"]) for o in view["options"]] == [("h01", "Interpose", True, 1)]

    ok(engine.do(cmd.USE_REACTION, hero_id="h01", target_id="h01"))
    assert (squire.shields, squire.mana, squire.reaction_charges) == (2, 1, 0)
    assert engine.combat.phase == CombatPhase.RESOURCE_WINDOW

    rejected(engine.do(cmd.USE_REACTION, hero_id="h01", target_id="h01"), "no resource reaction")  # stages never reopen
    # A rejected command restores the pre-command state copy, so re-read the combatants.
    squire, apprentice, scout = unit(engine, "h01"), unit(engine, "h02"), unit(engine, "h03")
    ok(engine.do(cmd.USE_REACTION, hero_id="h02", target_id="h01"))
    assert (squire.corruption, apprentice.mana, apprentice.reaction_charges) == (1, 4, 0)
    assert engine.combat.phase == CombatPhase.INTERRUPT_WINDOW

    ok(engine.do(cmd.USE_REACTION, hero_id="h03"))
    assert (scout.mana, scout.reaction_charges) == (1, 0)
    assert engine.combat.committed_intent.cancelled
    assert engine.combat.phase == CombatPhase.ENEMY_RESOLVE
    finish_activation(engine)

    # The interrupt skipped enemy resolution, but earlier Guard/Resource effects are not rolled back.
    assert (squire.hp, squire.shields, squire.corruption) == (14, 2, 1)
    cancelled = last_event(engine, "action_cancelled")
    assert cancelled.actor_id == "b1_e01" and cancelled.delta["cost_spent"] == 0
    tracked = ("intent_revealed", "reaction_stage_opened", "reaction_used", "intent_cancelled", "action_cancelled")
    order = [e.type for e in engine.events if e.type in tracked]
    assert order == [
        "intent_revealed", "reaction_stage_opened", "reaction_used", "reaction_stage_opened", "reaction_used",
        "reaction_stage_opened", "reaction_used", "intent_cancelled", "action_cancelled",
    ]
    assert [e.delta["stage"] for e in events_of(engine, "reaction_stage_opened")] == ["guard", "resource", "interrupt"]


def test_t05_charges_are_spent_until_each_heros_next_activation():
    engine = _party()
    squire = unit(engine, "h01")
    begin_enemy(engine, "b1_e01")
    ok(engine.do(cmd.USE_REACTION, hero_id="h01", target_id="h01"))
    ok(engine.do(cmd.USE_REACTION, hero_id="h02", target_id="h01"))
    ok(engine.do(cmd.USE_REACTION, hero_id="h03"))
    finish_activation(engine)

    # A second enemy acts before any hero: nobody has a charge, so every stage is skipped automatically.
    begin_enemy(engine, "b1_e02")
    assert engine.combat.phase == CombatPhase.ENEMY_RESOLVE
    skipped = [e.delta for e in events_of(engine, "reaction_stage_skipped")][-3:]
    assert [s["stage"] for s in skipped] == ["guard", "resource", "interrupt"]
    assert all(s["reason"] == "no eligible reaction" for s in skipped)
    finish_activation(engine)
    assert (squire.shields, squire.hp) == (0, 14)  # the Slash consumed the earlier Interpose shield

    begin_hero(engine, "h01", iron_d6=6, oath_d4=1)
    assert squire.reaction_charges == 1  # refreshed at the start of its own activation
    assert last_event(engine, "reaction_charge_refreshed").actor_id == "h01"
    assert unit(engine, "h03").reaction_charges == 0  # the Scout has not acted yet


def test_t05_skipping_stages_advances_to_resolution():
    engine = _party()
    begin_enemy(engine, "b1_e01")
    stages = []
    while engine.combat.phase in CombatPhase.STAGE_BY_WINDOW:
        stages.append(engine.combat.reaction_stage)
        ok(engine.do(cmd.SKIP_REACTION_STAGE))
    assert stages == ["guard", "resource", "interrupt"]
    assert engine.combat.phase == CombatPhase.ENEMY_RESOLVE
    finish_activation(engine)
    assert unit(engine, "h01").hp == 12
    assert all(h.reaction_charges == 1 for h in engine.combat.side("hero"))


def test_t05_disabled_reactions_explain_why():
    engine = _party()
    unit(engine, "h01").mana = 0
    unit(engine, "h03").mana = 0
    begin_enemy(engine, "b1_e01")
    assert engine.combat.phase == CombatPhase.RESOURCE_WINDOW  # Guard was unavailable and auto-skipped
    rejected(engine.do(cmd.USE_REACTION, hero_id="h01", target_id="h01"), "no resource reaction")
    ok(engine.do(cmd.SKIP_REACTION_STAGE))
    assert engine.combat.phase == CombatPhase.ENEMY_RESOLVE  # Interrupt unaffordable: skipped

    from battle_dice.core import reactions

    guard = reactions.stage_options(engine, "guard")[0]
    assert guard["eligible"] is False and guard["reason"] == "Needs 1 mana (has 0)."
    interrupt = reactions.stage_options(engine, "interrupt")[0]
    assert interrupt["reason"] == "Needs 1 mana (has 0)."

    back_row = start("squire:back", "scout")
    force_slash(back_row)
    begin_enemy(back_row, "b1_e01")
    assert back_row.combat.committed_intent.name == "Slash"  # a damaging intent, so only the row rule blocks Interpose
    option = reactions.stage_options(back_row, "guard")[0]
    assert option["reason"] == "Must be in the front row."


def test_t05_grounding_needs_a_possible_resource_change():
    engine = _party()
    apprentice = unit(engine, "h02")
    apprentice.mana = apprentice.max_mana  # mana cannot rise, and the target has no corruption
    begin_enemy(engine, "b1_e01")
    ok(engine.do(cmd.SKIP_REACTION_STAGE))  # leave Guard
    assert engine.combat.phase == CombatPhase.INTERRUPT_WINDOW  # Resource stage was skipped as unavailable
    from battle_dice.core import reactions

    assert reactions.stage_options(engine, "resource")[0]["reason"] == "No resource change is possible."


def test_t05_interpose_protects_exactly_one_target_of_an_area_attack():
    engine = start("squire", "apprentice", "scout", content=captain_content(3))
    add_status(engine, "b1_e01", "speed_up", stacks=2)  # War Cry already active, so it is not chosen
    begin_enemy(engine, "b1_e01", action_roll=0)  # Blight Wave
    intent = engine.combat.committed_intent
    assert intent.name == "Blight Wave" and intent.committed_target_ids == ["h01", "h02", "h03"]
    rejected(engine.do(cmd.USE_REACTION, hero_id="h01"), "choose which targeted ally")
    ok(engine.do(cmd.USE_REACTION, hero_id="h01", target_id="h02"))
    assert [unit(engine, h).shields for h in ("h01", "h02", "h03")] == [0, 2, 0]
    skip_reactions(engine)
    finish_activation(engine)
    assert [unit(engine, h).hp for h in ("h01", "h02", "h03")] == [13, 9, 9]
    assert unit(engine, "h02").shields == 1


def test_t05_duplicate_classes_hold_independent_reaction_state():
    engine = start("scout", "scout")
    begin_enemy(engine, "b1_e01")
    assert engine.combat.phase == CombatPhase.INTERRUPT_WINDOW
    ok(engine.do(cmd.USE_REACTION, hero_id="h01"))
    finish_activation(engine)
    assert (unit(engine, "h01").reaction_charges, unit(engine, "h02").reaction_charges) == (0, 1)
    begin_enemy(engine, "b1_e02")
    rejected(engine.do(cmd.USE_REACTION, hero_id="h01"), "no reaction charge")
    ok(engine.do(cmd.USE_REACTION, hero_id="h02"))
    assert engine.combat.committed_intent.cancelled


def test_t05_reactions_do_not_open_reaction_windows_and_self_buffs_are_not_reactable():
    engine = start("squire", "apprentice", "scout", content=captain_content(3))
    begin_enemy(engine, "b1_e01", action_roll=0)  # War Cry is the only priority-20 action
    assert engine.combat.committed_intent.name == "War Cry"
    assert engine.combat.phase == CombatPhase.ENEMY_RESOLVE
    assert events_of(engine, "reaction_stage_opened") == []
    assert last_event(engine, "reaction_stage_skipped").delta == {"stage": "all", "reason": "enemy action is not reactable"}
    rejected(engine.do(cmd.USE_REACTION, hero_id="h03"), "not allowed during")
    step(engine)
    assert unit(engine, "b1_e01").stacks_of("speed_up") == 2

    depth = _party()
    enemy_acts(depth, "b1_e01")
    used = events_of(depth, "reaction_used")
    assert used == []  # skipped stages produce no nested windows or stray reactions
