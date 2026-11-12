"""The README's tour of the first slice, played through the screens as it is written.

Two runs, each started from the main menu's Settings. A battle is won by arrangement (the tour
does not depend on the dice); everything a reader is told to click or press is clicked or pressed.
"""

from __future__ import annotations

from pathlib import Path

import pygame
import pytest

from battle_dice.app.controller import Screen
from battle_dice.core import commands as cmd
from battle_dice.core.models import RunPhase
from tests.conftest import begin_hero, down, finish_activation, unit, win_battle
from tests.ui.test_evolution_ui import Configured, close_every_save  # noqa: F401 - the fixture closes the saves

README = Path(__file__).resolve().parents[2] / "README.md"


def start_a_profile(play: Configured, preset_label: str) -> None:
    """Main menu, Settings: Class Evolution on, the start chosen, the profile reset (pressed twice), New Run."""
    assert play.ctrl.screen == Screen.MAIN_MENU
    play.key(pygame.K_s)
    assert play.ctrl.screen == Screen.SETTINGS
    if not play.ctrl.settings.class_evolution:
        play.click("settings:class_evolution")
    for _ in range(4):
        if next(row for row in play.ctrl.settings_view() if row["key"] == "demo_preset")["value"] == preset_label:
            break
        play.click("settings:demo_preset")
    assert next(row for row in play.ctrl.settings_view() if row["key"] == "demo_preset")["value"] == preset_label
    play.click("settings:reset")
    play.click("settings:reset")
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.screen == Screen.MAIN_MENU
    play.key(pygame.K_n)
    assert play.ctrl.screen == Screen.PARTY_SETUP and len(play.ctrl.roster_view()) == 3


def win_the_battle_as(play: Configured, hero: str, **faces: int) -> None:
    """Arranged: one enemy is left at 1 HP and ``hero`` finishes it with the die named first in ``faces``."""
    engine = play.ctrl.engine
    assert engine is not None
    foes = engine.combat.side("enemy")
    for foe in foes[1:]:
        foe.hp, foe.state = 0, "defeated"
    foes[0].hp, foes[0].shields = 1, 0
    begin_hero(engine, hero, **faces)
    die_id = next(iter(faces))
    assert engine.do(cmd.SET_ACTION_PLAN, actions=[{"die_id": die_id, "target_ids": [foes[0].id]}]).accepted
    assert engine.do(cmd.COMMIT_ACTION_PLAN).accepted
    while engine.state.phase == RunPhase.BATTLE and not engine.needs_input() and not engine.finished():
        assert engine.do(cmd.ADVANCE_PHASE).accepted
    play.ctrl.refresh()
    play.app.frame(0)


def test_the_tour_is_in_the_readme():
    text = README.read_text(encoding="utf-8")
    for phrase in ("### A tour of the slice in two runs", "A Guardian with Field Medic", "A Guardian at rank 1",
                   "Reset the saved profile", "Field Medic: revive at 5 HP", "Fight On (F)", "Career (C)", "Make active", "Begin Encounter (B)"):
        assert phrase in text, phrase


def test_run_one_field_medic_and_the_third_battle(tmp_path):
    play = Configured(tmp_path, fixed_seed=11)
    start_a_profile(play, "A Guardian with Field Medic")
    for hero_id in ("hero_001", "hero_002", "hero_003"):  # step 1: the roster's rows put heroes into the party
        play.click(f"roster:{hero_id}:add")
    assert [member["class_id"] for member in play.ctrl.party] == ["guardian", "scout", "apprentice"]
    play.click("slot:0:career")  # step 2
    play.key(pygame.K_k)
    field_medic = next(row for row in play.ctrl.skills_view()["rows"] if row["skill_id"] == "guardian_field_medic")
    assert field_medic["equipped"] and play.ui.widget("skill:guardian_field_medic:unequip") is not None
    play.key(pygame.K_ESCAPE)
    play.key(pygame.K_b)  # step 3
    engine = play.ctrl.engine
    assert engine is not None and play.ctrl.screen == Screen.BATTLE
    down(engine, "h02")
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=5)
    unit(engine, "h01").mana = 2
    play.ctrl.refresh()
    play.app.frame(0)
    die = next(d for d in play.ctrl._turn_view()["dice"] if d["die_id"] == "guardian_d6")  # type: ignore[index]
    assert die["skill_note"] == "Field Medic: revive at 5 HP"
    play.click("die:guardian_d6:use")
    play.click("unit:h02")
    play.ctrl.confirm_plan()
    finish_activation(engine)
    assert (unit(engine, "h02").state, unit(engine, "h02").hp) == ("standing", 5)
    win_the_battle_as(play, "h01", guardian_d6=4, guardian_d4=3)  # step 4
    assert play.ctrl.screen == Screen.UPGRADE
    play.click("up:offer:0")
    play.click("up:apply")
    play.key(pygame.K_RETURN)
    assert play.ctrl.screen == Screen.BATTLE and engine.state.encounter_index == 1
    win_the_battle_as(play, "h01", guardian_d6=4, guardian_d4=3)
    assert play.ctrl.screen == Screen.CONTINUE
    play.key(pygame.K_f)
    assert play.ctrl.screen == Screen.BATTLE and engine.state.encounter_index == 2 and engine.combat.encounter_id == "training_04"
    assert play.app.render_faults == 0


def test_run_two_becoming_a_guardian_inside_a_run(tmp_path):
    play = Configured(tmp_path, fixed_seed=11)
    start_a_profile(play, "A Guardian at rank 1")
    play.click("roster:hero_001:add")  # step 1
    play.click("slot:0:career")
    play.click("career:squire:select")
    play.click("career:squire:activate")
    assert play.ctrl.message == "Squire 1 is now a Squire."
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.party[0]["class_id"] == "squire"
    play.click("roster:hero_002:add")  # step 2
    play.key(pygame.K_b)
    engine = play.ctrl.engine
    assert engine is not None and engine.build("h01").vocation_id == "squire"
    win_battle(engine)
    play.ctrl.refresh()
    play.app.frame(0)
    assert play.ctrl.screen == Screen.UPGRADE
    play.key(pygame.K_c)  # step 3
    play.click("career:guardian:select")
    play.click("career:guardian:activate")
    assert play.ctrl.message.startswith("Squire 1 is now a Guardian and fights on as one.")
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.screen == Screen.UPGRADE  # step 4
    assert [offer["die_id"] for offer in play.ctrl.current_offers()] == ["guardian_d6"] * 3
    play.click("up:offer:0")
    play.click("up:apply")
    play.key(pygame.K_RETURN)
    assert play.ctrl.screen == Screen.BATTLE and engine.state.encounter_index == 1
    assert engine.combat.combatants["h01"].archetype_id == "guardian" and play.app.render_faults == 0


@pytest.mark.parametrize("seed", [11, 12, 13])
def test_a_whole_run_with_a_guardian_is_drawn_on_every_screen_without_a_fault(tmp_path, seed):
    """The simulated player plays a Guardian party from the first roll to the outcome, and every step is drawn.

    A run with an evolved hero once failed on the upgrade screen, and no test had played one through.
    """
    from battle_dice.settings import Settings
    from battle_dice.sim.policies import HeuristicPolicy

    play = Configured(tmp_path, settings=Settings(class_evolution=True, demo_preset="guardian_mastered"), fixed_seed=seed)
    play.ctrl.new_run()
    for hero_id in ("hero_001", "hero_002", "hero_003"):
        play.ctrl.add_saved_hero(hero_id)
    play.ctrl.begin_run()
    engine = play.ctrl.engine
    assert engine is not None and engine.build("h01").skills == ("guardian_field_medic",)
    policy, seen = HeuristicPolicy(), set()
    for _ in range(20000):
        if engine.finished():
            break
        if engine.needs_input():
            policy.act(engine)
        else:
            assert engine.do(cmd.ADVANCE_PHASE).accepted
        play.ctrl.refresh()
        play.app.frame(0)
        seen.add(play.ctrl.screen)
        assert play.app.render_faults == 0 and play.ctrl.screen != Screen.ERROR, play.ctrl.error_text
    assert engine.finished() and play.ctrl.screen == Screen.OUTCOME
    assert Screen.BATTLE in seen and (Screen.UPGRADE in seen or engine.state.outcome == "defeat")
    if len(engine.state.battle_records) >= 2 and engine.state.battle_records[1]["outcome"] == "victory":
        assert Screen.CONTINUE in seen
    saved = play.ctrl.progression.state.run
    assert saved is not None and saved.phase == engine.state.outcome, "the run's result reached the save"
