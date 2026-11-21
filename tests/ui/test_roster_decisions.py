"""The owner's three decisions on the roster (D-35, playtest findings R3, R4 and R5), on the real screens.

* R3: a hero can be dismissed from its Career screen, between runs, asked once more.
* R4: a recruit's name does not say a class ("Recruit 1"), because it may be another class the next moment.
* R5: a vocation a hero opened stays open when a slower Mastery pace takes the rank it needed, and the screen says so.
"""

from __future__ import annotations

import pygame
import pytest

from battle_dice.app.controller import AppController, Screen
from tests.conftest import win_battle
from tests.ui.test_evolution_ui import OPENED, Configured, Evolution, close_every_save  # noqa: F401 - the fixture closes the saves
from tests.ui.test_ui_flow import SIZES, font, record_text  # noqa: F401 - font is a fixture

ASK = "Press again to dismiss Recruit 2 for good. Everything it has mastered is lost."


def shown(play, monkeypatch) -> list[str]:
    """Every text of the screen as it is drawn now."""
    with monkeypatch.context() as patch:
        drawn, _ = record_text(patch)
        play.app.frame(0)
    return list(drawn)


def test_a_recruits_name_says_no_class_and_the_screens_say_the_class_beside_it(tmp_path, monkeypatch):
    play = Evolution(tmp_path, recruits=("squire", "scout"))
    assert [(row["name"], row["vocation_name"]) for row in play.ctrl.roster_view()] == [("Recruit 1", "Squire"), ("Recruit 2", "Scout")]
    assert {"1. Recruit 1", "Squire, rank 1", "2. Recruit 2", "Scout, rank 1"} <= set(shown(play, monkeypatch))
    play.click("slot:0:career")
    play.click("career:scout:activate")  # every hero has all three starting classes open
    play.key(pygame.K_ESCAPE)
    texts = shown(play, monkeypatch)
    assert play.ctrl.roster_view()[0]["name"] == "Recruit 1" and "Squire, rank 1" not in texts
    assert any(text.startswith("Recruit 1   Scout, rank 1") for text in texts), "the roster names the class beside the name"


def test_a_hero_in_the_party_is_not_dismissed(tmp_path, monkeypatch):
    play = Evolution(tmp_path)
    play.click("slot:1:career")
    button = play.ui.widget("career:dismiss")
    assert (button.enabled, button.reason) == (False, "Recruit 2 is in the party. Remove it from the party first.")
    assert "Dismiss this hero" in shown(play, monkeypatch)
    play.ctrl.dismiss_hero()  # reached some other way, the game still refuses and says why
    assert play.ctrl.message == button.reason and play.ctrl.message_is_error and len(play.link.state.heroes) == 2


def test_dismissing_asks_once_more_and_then_the_hero_is_gone_for_good(tmp_path, monkeypatch):
    play = Evolution(tmp_path)
    play.click("slot:1:remove")
    play.click("roster:hero_002:career")
    assert play.ui.widget("career:dismiss").enabled and play.ctrl.screen == Screen.CAREER
    play.click("career:dismiss")
    assert play.ctrl.message == ASK and play.ctrl.message_is_error and list(play.link.state.heroes) == ["hero_001", "hero_002"]
    assert "Press again: dismiss" in shown(play, monkeypatch) and "Dismiss this hero" not in shown(play, monkeypatch)
    play.click("career:dismiss")
    assert list(play.link.state.heroes) == ["hero_001"] and play.ctrl.screen == Screen.PARTY_SETUP
    assert play.ctrl.message == "Recruit 2 was dismissed. The roster has 1 of 12 heroes." and not play.ctrl.message_is_error
    assert "roster:hero_002:add" not in play.ui.keys() and [member["hero_id"] for member in play.ctrl.party] == ["hero_001"]
    # The save says the same after the game is closed and opened again.
    play.ctrl.close()
    again = AppController(fixed_seed=11, log_dir=tmp_path / "logs", features=["class_evolution_v1"])
    OPENED.append(again)
    assert list(again.progression.state.heroes) == ["hero_001"] and again.progression.state.dismissed == ["hero_002"]


def test_the_question_ends_when_the_player_does_something_else(tmp_path, monkeypatch):
    play = Evolution(tmp_path)
    play.click("slot:1:remove")
    play.click("roster:hero_002:career")
    play.click("career:dismiss")
    assert play.ctrl.message == ASK
    play.key(pygame.K_ESCAPE)  # back to the party: the question belonged to the Career screen
    play.click("roster:hero_002:career")
    assert "Dismiss this hero" in shown(play, monkeypatch)
    play.click("career:dismiss")
    assert play.ctrl.message == ASK and "hero_002" in play.link.state.heroes, "it asks again; nothing was dismissed"


def test_inside_a_run_nobody_is_dismissed(tmp_path):
    play = Evolution(tmp_path, recruits=("squire", "scout", "apprentice"))
    play.click("slot:2:remove")
    play.ctrl.begin_run()
    engine = play.ctrl.engine
    assert engine is not None
    win_battle(engine)
    play.ctrl.refresh()
    play.app.frame(0)
    assert play.ctrl.screen == Screen.UPGRADE
    for hero_id in ("hero_001", "hero_003"):  # one who fights and one who stayed at home
        play.ctrl.open_career(hero_id)
        play.app.frame(0)
        button = play.ui.widget("career:dismiss")
        assert (button.enabled, button.reason) == (False, "Heroes are dismissed between runs, not during one.")
        play.ctrl.dismiss_hero()
        assert play.ctrl.message == button.reason and len(play.link.state.heroes) == 3
        play.ctrl.close_career()


def test_a_full_roster_says_how_to_make_room_and_dismissing_makes_it(tmp_path):
    play = Evolution(tmp_path, recruits=("squire",) * 12)
    hint = "The roster is full (12 heroes). To make room, dismiss a hero on its Career screen."
    assert play.ui.widget("add:scout").enabled is False and play.ui.widget("add:scout").reason == hint
    play.ctrl.add_hero("scout")
    assert play.ctrl.message == hint and len(play.link.state.heroes) == 12
    play.click("roster:hero_012:career")
    play.click("career:dismiss")
    play.click("career:dismiss")
    assert play.ctrl.message == "Recruit 12 was dismissed. The roster has 11 of 12 heroes." and play.ui.widget("add:scout").enabled
    play.click("add:scout")
    newest = play.ctrl.roster_view()[-1]
    assert (newest["hero_id"], newest["name"], newest["vocation_name"]) == ("hero_013", "Recruit 13", "Scout"), "a number is not given out twice"


def at_very_fast_pace_a_squire_became_a_guardian(tmp_path, size=(1280, 720)) -> Configured:
    """Played through the screens: Class Evolution on, the fastest pace, a Squire mastered and Guardian claimed."""
    play = Configured(tmp_path, fixed_seed=11, size=size)
    play.key(pygame.K_s)
    play.key(pygame.K_3)
    play.click("settings:class_evolution")
    play.key(pygame.K_4)
    while play.ctrl.settings.mastery_pace != "very_fast":
        play.click("settings:mastery_pace")
    play.key(pygame.K_ESCAPE)
    play.key(pygame.K_n)
    play.click("add:squire")
    link = play.ctrl.progression
    top = link.catalog.thresholds("squire")[-1]
    assert link.career.grant_mastery("hero_001", "squire", top, "arranged by the test").accepted
    play.click("slot:0:career")
    play.click("career:guardian:select")
    play.click("career:guardian:claim")
    assert "guardian" in link.state.heroes["hero_001"].unlocked_vocations and play.ctrl.career_view()["selected_note"] == ""
    play.key(pygame.K_ESCAPE)
    return play


def slow_the_pace(play: Configured) -> None:
    play.key(pygame.K_ESCAPE)  # the main menu
    play.key(pygame.K_s)
    play.key(pygame.K_4)
    play.click("settings:mastery_pace")  # very fast -> normal
    assert play.ctrl.settings.mastery_pace == "normal"
    play.key(pygame.K_ESCAPE)
    play.key(pygame.K_n)


def test_a_vocation_opened_at_a_faster_pace_stays_open_and_the_career_screen_says_so(tmp_path, monkeypatch):
    play = at_very_fast_pace_a_squire_became_a_guardian(tmp_path)
    slow_the_pace(play)
    hero = play.ctrl.progression.state.heroes["hero_001"]
    assert hero.rank("squire") < 8, "the slower pace took the rank that opened Guardian"
    assert "guardian" in hero.unlocked_vocations
    play.click("roster:hero_001:career")
    rows = {row["vocation_id"]: row for row in play.ctrl.career_view()["rows"] if row.get("vocation_id")}
    assert rows["guardian"]["note"] == AppController.OPENED_EARLIER and rows["guardian"]["can_activate"] and rows["guardian"]["unlocked"]
    assert [vocation for vocation, row in rows.items() if row["note"]] == ["guardian"], "starting classes and locked vocations carry no note"
    assert "mastered" not in rows["squire"]["status"]
    drawn, shortened = record_text(monkeypatch)
    play.click("career:guardian:select")
    play.app.frame(0)
    said = " ".join(drawn)
    assert "Opened at an earlier Mastery pace." in said and "it stays open" in said and shortened == [], shortened
    play.click("career:guardian:activate")
    assert hero.active_vocation_id == "guardian", "and it can still be made active"
    drawn.clear()
    play.click("career:squire:select")
    play.app.frame(0)
    assert "Opened at an earlier" not in " ".join(drawn)


def test_a_vocation_whose_requirement_is_still_met_carries_no_note(tmp_path):
    play = at_very_fast_pace_a_squire_became_a_guardian(tmp_path)
    play.click("slot:0:career")
    assert all(not row.get("note") for row in play.ctrl.career_view()["rows"])


@pytest.mark.parametrize("size", SIZES)
def test_the_new_button_and_the_note_are_not_cut_off(tmp_path, monkeypatch, font, size):  # noqa: F811
    play = at_very_fast_pace_a_squire_became_a_guardian(tmp_path, size=size)
    slow_the_pace(play)
    drawn, shortened = record_text(monkeypatch)
    assert [member["hero_id"] for member in play.ctrl.party] == ["hero_001"], "a change of pace keeps the party"
    play.click("slot:0:remove")
    play.click("roster:hero_001:career")
    for vocation_id in ("guardian", "squire"):
        play.click(f"career:{vocation_id}:select")
        play.app.frame(0)
    play.click("career:dismiss")
    play.app.frame(0)
    assert "Press again: dismiss" in drawn and shortened == [] and play.app.render_faults == 0, shortened
    play.key(pygame.K_ESCAPE)
    for _ in range(11):
        play.ctrl.add_hero("squire")
    play.app.frame(0)
    play.hover("add:squire")
    play.app.frame(0)
    assert shortened == [] and play.app.render_faults == 0, shortened
