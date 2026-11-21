"""Rules 1.1.2 on the screens (owner decision D-34): a change of vocation back and forth gains nothing.

The playtester's steps: on the upgrade screen, Career, Guardian, Squire, Guardian, Squire ... Under rules
1.1.1 a hero at 12 of 15 health stood at 18 of 18 after four changes.
"""

from __future__ import annotations

import pygame

from battle_dice.app.controller import Screen
from tests.conftest import unit, win_battle
from tests.ui.test_evolution_ui import close_every_save  # noqa: F401 - the fixture closes the saves
from tests.ui.test_playtest_evolution import a_squire_that_can_become_a_guardian, engine_of


def test_changing_back_and_forth_on_the_upgrade_screen_gains_no_health(tmp_path):
    play = a_squire_that_can_become_a_guardian(tmp_path)
    engine = engine_of(play)
    hero = unit(engine, "h01")
    win_battle(engine)
    hero.hp = hero.max_hp - 3
    play.ctrl.refresh()
    play.app.frame(0)
    assert play.ctrl.screen == Screen.UPGRADE
    play.key(pygame.K_c)
    as_squire = (hero.hp, hero.max_hp, hero.mana, hero.max_mana)
    as_guardian = None
    for _ in range(4):
        play.click("career:guardian:select")
        promised = play.ctrl.career_view()["change_preview"]
        play.click("career:guardian:activate")
        now = (hero.hp, hero.max_hp, hero.mana, hero.max_mana)
        as_guardian = as_guardian or now
        assert now == as_guardian, "every time a Guardian with what the first change gave"
        assert f"-> {now[0]}/{now[1]}" in promised, "and the screen had said so before"
        play.click("career:squire:select")
        back = play.ctrl.career_view()["change_preview"]
        assert f"HP {now[0]}/{now[1]} -> {as_squire[0]}/{as_squire[1]}" in back, "the way back is shown as what it is"
        play.click("career:squire:activate")
        assert (hero.hp, hero.max_hp, hero.mana, hero.max_mana) == as_squire, "a Squire again with exactly what it had"
    assert as_guardian is not None and as_guardian[0] < as_guardian[1], "the missing health is still missing"
