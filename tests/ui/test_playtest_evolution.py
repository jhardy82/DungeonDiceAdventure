"""What the Class Evolution screens say: fixes for the playtest of 2026-11-21, batch 3 (owner decision D-34).

- What a won battle earned is on the upgrade screen, not only in a status line that the next message replaces.
- The career screen gives the hero's own numbers, and what a change of vocation would do before it is done.
- Nothing about a hero changes silently.
"""

from __future__ import annotations

import pygame
import pytest

from battle_dice.app.controller import Screen
from battle_dice.core.build import convert_pool
from battle_dice.core.engine import Engine
from battle_dice.core.view import combat_log, hero_turn_view
from battle_dice.settings import Settings
from tests.conftest import begin_hero, down, finish_activation, unit, win_battle
from tests.ui.test_demo_tour import start_a_profile
from tests.ui.test_evolution_ui import Configured, Evolution, close_every_save, master  # noqa: F401 - the fixture closes the saves
from tests.ui.test_ui_flow import Play, record_text


def engine_of(play: Play) -> Engine:
    engine = play.ctrl.engine
    assert engine is not None
    return engine


def dice_of(play: Play) -> list[dict]:
    """The rolled dice of the acting hero, in the order the battle screen lists them."""
    turn = hero_turn_view(engine_of(play))
    assert turn is not None
    return turn["dice"]


def after_battle_one(play: Play) -> None:
    play.ctrl.begin_run()
    win_battle(engine_of(play))
    play.ctrl.refresh()
    play.app.frame(0)
    assert play.ctrl.screen == Screen.UPGRADE


# --------------------------------------------------------------------------------------------
# D3: mastery earned, on the upgrade screen
# --------------------------------------------------------------------------------------------


def test_the_upgrade_screen_says_what_the_battle_earned(tmp_path, monkeypatch):
    play = Evolution(tmp_path)
    after_battle_one(play)
    earned = "Mastery: Squire 1 +1, now rank 2.  Scout 2 +1, now rank 2."
    assert play.ctrl.mastery_line() == earned
    # The status line carries it together with what to do next, so the one no longer replaces the other.
    assert play.ctrl.message == f"Battle 1 won. {earned} Choose one dice upgrade (required)."
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    assert earned in drawn and earned not in shortened
    play.click("up:offer:0")  # the line stays while the player works on the screen
    play.click("up:apply")
    drawn.clear()
    play.app.frame(0)
    assert earned in drawn


@pytest.mark.parametrize("size", [(1280, 720), (960, 540)], ids=["1280x720", "960x540"])
def test_what_five_heroes_earned_is_shown_whole(tmp_path, monkeypatch, size):
    """One line is too short for five heroes: the text then takes two lines, and is never cut."""
    play = Evolution(tmp_path, recruits=("squire", "scout", "apprentice", "squire", "scout"), size=size)
    after_battle_one(play)
    line = play.ctrl.mastery_line()
    assert line.count("+1") == 5
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    assert line in drawn and line not in shortened


def test_without_class_evolution_the_upgrade_screen_is_as_it_was(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire", "scout"])
    after_battle_one(play)
    assert play.ctrl.mastery_line() == "" and play.ctrl.message == "Battle 1 won. Choose one dice upgrade (required)."
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert not any(text.startswith("Mastery") for text in drawn)


# --------------------------------------------------------------------------------------------
# D11: the roster's title
# --------------------------------------------------------------------------------------------


def test_the_roster_title_stays_true_when_the_roster_size_is_lowered(tmp_path, monkeypatch):
    play = Configured(tmp_path, settings=Settings(class_evolution=True, roster_limit=12))
    for _ in range(7):
        play.ctrl.recruit("squire")
    play.ctrl.new_run()
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert "Roster (7 of 12 heroes)" in drawn
    play.ctrl.to_main_menu()
    play.ctrl.open_settings()
    for _ in range(3):
        if play.ctrl.settings.roster_limit == 6:
            break
        play.ctrl.change_setting("roster_limit")
    assert play.ctrl.settings.roster_limit == 6
    play.ctrl.close_settings()
    play.ctrl.new_run()
    drawn.clear()
    play.app.frame(0)
    assert len(play.ctrl.roster_view()) == 7, "nobody is lost"
    assert "Roster (7 heroes; the roster size is now 6)" in drawn and not any("7 of 6" in text for text in drawn)


# --------------------------------------------------------------------------------------------
# D12: the hero's own numbers on the career screen
# --------------------------------------------------------------------------------------------


def test_the_career_screen_gives_the_heros_own_numbers(tmp_path, monkeypatch):
    play = Configured(tmp_path, fixed_seed=11)
    start_a_profile(play, "A Guardian at rank 1")
    link = play.ctrl.progression
    hero = link.state.heroes["hero_001"]
    bonus = link.career.service.permanent_stat_bonus(hero)
    own = link.career.service.effective_stats(hero, "guardian")
    base = link.catalog.base_stats("guardian")
    assert bonus["max_hp"] > 0 and own["max_hp"] == base["max_hp"] + bonus["max_hp"], "this hero has more health than the vocation's own"
    play.ctrl.open_career("hero_001")
    play.ctrl.select_career_vocation("guardian")
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    numbers = next(text for text in drawn if text.startswith("HP "))
    assert numbers.startswith(f"HP {own['max_hp']} ({base['max_hp']} +{bonus['max_hp']} mastery)   Speed ") and numbers not in shortened
    # A hero without such a bonus sees the vocation's numbers and no remark.
    play.ctrl.close_career()
    play.ctrl.open_career("hero_002")
    drawn.clear()
    play.app.frame(0)
    plain = next(text for text in drawn if text.startswith("HP "))
    assert "mastery" not in plain


# --------------------------------------------------------------------------------------------
# M8: a change of vocation is shown before it is made, and said in numbers afterwards
# --------------------------------------------------------------------------------------------


def a_squire_that_can_become_a_guardian(tmp_path) -> Configured:
    play = Configured(tmp_path, fixed_seed=11)
    start_a_profile(play, "A Guardian at rank 1")
    play.click("roster:hero_001:add")
    play.click("slot:0:career")
    play.click("career:squire:select")
    assert play.ctrl.career_view()["change_preview"] == "", "outside a run there is nothing to carry over"
    play.click("career:squire:activate")
    play.key(pygame.K_ESCAPE)
    play.click("roster:hero_002:add")
    play.key(pygame.K_b)
    return play


def test_the_career_screen_shows_what_a_change_would_do_and_the_change_does_exactly_that(tmp_path, monkeypatch):
    play = a_squire_that_can_become_a_guardian(tmp_path)
    engine = engine_of(play)
    hero = unit(engine, "h01")
    win_battle(engine)
    hero.hp = hero.max_hp - 3
    play.ctrl.refresh()
    play.app.frame(0)
    play.key(pygame.K_c)
    assert play.ctrl.career_view()["change_preview"] == "", "the active vocation: nothing would change"
    play.click("career:guardian:select")
    link = play.ctrl.progression
    own = link.career.service.effective_stats(link.state.heroes["hero_001"], "guardian")
    hp_after = convert_pool(hero.hp, hero.max_hp, own["max_hp"])
    mana_after = convert_pool(hero.mana, hero.max_mana, own["max_mana"])
    preview = play.ctrl.career_view()["change_preview"]
    assert preview == (f"If made active now: HP {hero.hp}/{hero.max_hp} -> {hp_after}/{own['max_hp']}, "
                       f"mana {hero.mana}/{hero.max_mana} -> {mana_after}/{own['max_mana']}. "
                       "It fights on with the dice below. Bench die: none.")
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    assert preview in drawn and preview not in shortened
    play.click("career:guardian:activate")
    assert (hero.hp, hero.max_hp, hero.mana, hero.max_mana) == (hp_after, own["max_hp"], mana_after, own["max_mana"])
    assert play.ctrl.message == (f"Squire 1 is now a Guardian and fights on as one: HP {hp_after}/{own['max_hp']}, "
                                 f"mana {mana_after}/{own['max_mana']}, dice Guardian d6, Guardian d4, bench die none. "
                                 "Choose the upgrade for its new dice.")
    assert play.ctrl.career_view()["change_preview"] == ""
    # Back to the Squire: its bench die is named, so it does not vanish or come back silently.
    play.click("career:squire:select")
    assert play.ctrl.career_view()["change_preview"].endswith("Bench die: Vanguard d4.")


def test_no_preview_while_a_change_is_not_possible(tmp_path):
    play = a_squire_that_can_become_a_guardian(tmp_path)
    assert play.ctrl.screen == Screen.BATTLE
    play.ctrl.open_career("hero_001")
    play.ctrl.select_career_vocation("guardian")
    view = play.ctrl.career_view()
    assert view["change_preview"] == "" and not view["open_now"]


def test_a_units_panel_names_its_vocation_when_its_name_does_not(tmp_path, monkeypatch):
    play = a_squire_that_can_become_a_guardian(tmp_path)
    engine = engine_of(play)
    win_battle(engine)
    play.ctrl.refresh()
    play.app.frame(0)
    play.key(pygame.K_c)
    play.click("career:guardian:select")
    play.click("career:guardian:activate")
    play.key(pygame.K_ESCAPE)
    play.click("up:offer:0")
    play.click("up:apply")
    play.key(pygame.K_RETURN)
    assert play.ctrl.screen == Screen.BATTLE and unit(engine, "h01").name == "Squire 1"
    play.to_input()
    play.hover("unit:h01")
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert "Inspect: Squire 1, Guardian" in drawn
    play.hover("unit:h02")
    drawn.clear()
    play.app.frame(0)
    assert "Inspect: Scout 2" in drawn, "a name that says the vocation is not said twice"


# --------------------------------------------------------------------------------------------
# K5: Die 1 is the larger die for every vocation
# --------------------------------------------------------------------------------------------


def test_die_one_is_the_larger_die_for_a_guardian_as_for_a_squire(tmp_path):
    play = Configured(tmp_path, fixed_seed=11)
    start_a_profile(play, "A Guardian at rank 1")
    play.click("roster:hero_001:add")
    play.click("roster:hero_002:add")
    play.key(pygame.K_b)
    engine = engine_of(play)
    assert engine.build("h01").vocation_id == "guardian"
    unit(engine, "h01").equipped_dice_ids = ["guardian_d4", "guardian_d6"]  # the order the catalog lists them in
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=1)
    play.ctrl.refresh()
    play.app.frame(0)
    assert [(die["die_id"], die["die_size"]) for die in dice_of(play)] == [("guardian_d6", 6), ("guardian_d4", 4)]
    assert play.ui.widget("die:guardian_d6:use").hotkeys == (pygame.K_1,) and play.ui.widget("die:guardian_d4:use").hotkeys == (pygame.K_2,)
    assert play.ui.widget("die:guardian_d6:keep").hotkeys == (pygame.K_z,)
    assert [die["size"] for die in next(c for c in play.ctrl.view()["combatants"] if c["id"] == "h01")["dice"]] == [6, 4]
    play.key(pygame.K_1)
    if play.ctrl.targeting_die is not None:
        play.key(pygame.K_1)
    assert [action["die_id"] for action in play.ctrl.draft] == ["guardian_d6"]


def test_the_order_of_the_shipped_classes_is_unchanged(tmp_path):
    for class_id, dice in (("squire", ["iron_d6", "oath_d4"]), ("apprentice", ["arcane_d6", "focus_d4"]), ("scout", ["striker_d8", "tools_d4"])):
        play = Play(tmp_path / class_id, [class_id])
        play.begin()
        play.to_roll_prompt()
        play.key(pygame.K_r)
        assert [die["die_id"] for die in dice_of(play)] == dice


# --------------------------------------------------------------------------------------------
# M10: Field Medic
# --------------------------------------------------------------------------------------------


def test_a_die_that_may_revive_through_field_medic_does_not_say_that_it_cannot(tmp_path, monkeypatch):
    play = Configured(tmp_path, fixed_seed=11)
    start_a_profile(play, "A Guardian with Field Medic")
    for hero_id in ("hero_001", "hero_002"):
        play.click(f"roster:{hero_id}:add")
    play.key(pygame.K_b)
    engine = engine_of(play)
    play.ui.anim.enabled = False  # no tumbling dice: the card shows its face at once
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=5)  # Heal
    unit(engine, "h01").mana = 2
    play.ctrl.refresh()
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    printed = "heal 2 (cannot revive); costs 1 mana"
    before = drawn.count(printed)  # on the die card, and in the list of the die's faces beside it
    assert before >= 1 and "Field Medic: revive at 5 HP" not in drawn, "with nobody down the face is an ordinary heal"
    down(engine, "h02")
    play.ctrl.refresh()
    drawn.clear()
    play.app.frame(0)
    # The die card no longer says both "cannot revive" and "revive at 5 HP".
    assert "Field Medic: revive at 5 HP" in drawn and "heal 2; costs 1 mana" in drawn and drawn.count(printed) == before - 1
    play.click("die:guardian_d6:use")
    play.click("unit:h02")
    play.ctrl.confirm_plan()
    finish_activation(engine)
    assert any(line.endswith("is revived at 5 HP (its gauge starts over; statuses it had stay).") for line in combat_log(engine))


# --------------------------------------------------------------------------------------------
# Three cases the deliberate breaks showed were not tested
# --------------------------------------------------------------------------------------------


def test_no_preview_once_the_run_is_over(tmp_path):
    """The run's heroes are still there on the outcome screen; a change then is for the next run, with nothing to carry over."""
    play = Evolution(tmp_path)
    master(play, "hero_001", "squire")
    play.to_the_decision()
    play.click("continue:stop")
    assert play.ctrl.screen == Screen.OUTCOME and play.ctrl.engine is not None
    assert play.link.claim("hero_001", "guardian").accepted
    play.ctrl.open_career("hero_001")
    play.ctrl.select_career_vocation("guardian")
    view = play.ctrl.career_view()
    guardian = next(row for row in view["rows"] if row.get("vocation_id") == "guardian")
    assert guardian["can_activate"] and not view["in_run"] and view["change_preview"] == ""


def test_a_heros_dice_are_named_in_the_order_the_battle_lists_them(tmp_path):
    play = Configured(tmp_path, fixed_seed=11)
    start_a_profile(play, "A Guardian at rank 1")
    play.click("roster:hero_001:add")
    play.key(pygame.K_b)
    hero = unit(engine_of(play), "h01")
    hero.equipped_dice_ids = ["guardian_d4", "guardian_d6"]
    assert play.ctrl.dice_as_listed("h01") == ["Guardian d6", "Guardian d4"]
    hero.equipped_dice_ids = ["guardian_d6", "guardian_d4"]
    assert play.ctrl.dice_as_listed("h01") == ["Guardian d6", "Guardian d4"]


@pytest.mark.parametrize("size", [(1280, 720), (960, 540)], ids=["1280x720", "960x540"])
def test_a_long_account_of_what_was_earned_is_set_smaller_not_cut(tmp_path, monkeypatch, size):
    play = Evolution(tmp_path, recruits=("squire", "scout", "apprentice", "squire", "scout"), size=size)
    after_battle_one(play)
    names = ("Squire 1", "Scout 2", "Apprentice 3", "Squire 4", "Scout 5")
    long = "Mastery: " + "  ".join(f"{name} +2 with the bonus, now rank 3{', learned Field Medic' if name.startswith('Squire') else ''}." for name in names)
    assert len(play.ui.wrap_lines(long, 716, 14)) > 2, "at the size of a short line this would need three lines"
    monkeypatch.setattr(play.ctrl, "mastery_line", lambda: long)
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    assert long in drawn and long not in shortened
