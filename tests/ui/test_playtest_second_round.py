"""What the second playtest by AI players found (2026-11-21, four roles, the build after D-35), fixed here.

The findings are in ``docs/PLAYTEST_TEAM_2026-11-21.md``, section 7. One weakness showed in three reports:
a "press again" question stayed open while the player did something else, so one later press dismissed a
hero, started a new run or reset every setting. The first group of tests is that one mechanism.
"""

from __future__ import annotations

import pygame
import pytest

from battle_dice.app.controller import AppController, Screen
from battle_dice.core.view import action_forecast, combat_log, hero_turn_view, with_article
from battle_dice.phone import screens as phone
from battle_dice.ui import screens
from tests.conftest import add_status, unit
from tests.ui.test_evolution_ui import OPENED, Configured, Evolution, close_every_save  # noqa: F401 - the fixture closes the saves
from tests.ui.test_playtest_keys import at_the_outcome, engine_of, reacting
from tests.ui.test_roster_decisions import shown, slow_the_pace
from tests.ui.test_ui_flow import SIZES, Play, font, record_text  # noqa: F401 - font is a fixture

RETRY = "Press Retry again to start a new run with this party. This result will be gone."


def rolled_die(play: Play, die_id: str) -> dict:
    """The acting hero's rolled die as the battle screen shows it."""
    turn = hero_turn_view(engine_of(play))
    assert turn is not None
    return next(die for die in turn["dice"] if die["die_id"] == die_id)


def face_number(play: Play, die_id: str, face_name: str) -> int:
    """The 1-based face of the acting hero's die that has this name."""
    engine = engine_of(play)
    faces = engine.die_for(play.combat.turn.hero_id, die_id).faces
    return next(index for index, face in enumerate(faces, start=1) if face.name == face_name)


# --------------------------------------------------------------------------------------------
# A question that waits for a second press ends when the player does anything else
# --------------------------------------------------------------------------------------------


def test_the_mechanism_itself_one_control_one_question(tmp_path):
    ctrl = AppController(log_dir=tmp_path / "logs")
    ctrl.noticed_input("a")
    assert ctrl._ask_once("x", "Press again.") is False and ctrl.asked("x") and ctrl.question_open()
    ctrl.noticed_input("a")
    assert ctrl._ask_once("x", "Press again.") is True and not ctrl.question_open()
    # Another control in between: the question is over, and its text leaves the status bar.
    ctrl.noticed_input("a")
    ctrl._ask_once("x", "Press again.")
    ctrl.noticed_input("b")
    assert not ctrl.asked("x") and ctrl.message == ""
    # A key no control answers to (None) ends it as well.
    ctrl.noticed_input("a")
    ctrl._ask_once("x", "Press again.")
    ctrl.noticed_input(None)
    assert not ctrl.asked("x")
    # A newer message is not wiped when an old question ends.
    ctrl.noticed_input("a")
    ctrl._ask_once("x", "Press again.")
    ctrl.message, ctrl.message_serial = "Something newer.", ctrl.message_serial + 1
    ctrl.noticed_input("b")
    assert ctrl.message == "Something newer."


def test_a_question_does_not_wait_for_ever(tmp_path):
    ctrl = AppController(log_dir=tmp_path / "logs")
    ctrl._ask_once("x", "Press again.")
    ctrl.pass_time(AppController.QUESTION_MS - 1)
    assert ctrl.asked("x")
    ctrl.pass_time(1)
    assert not ctrl.asked("x") and ctrl.message == ""
    ctrl.pass_time(60_000)  # nothing is open: time passing does nothing
    assert ctrl._ask_once("x", "Press again.") is False, "the next press asks again"


def test_every_kind_of_question_ends_the_same_way(tmp_path):
    """The reset to defaults, the profile reset and the die swap kept flags of their own; they lapse like the rest."""
    ctrl = AppController(log_dir=tmp_path / "logs")
    for arm in ("defaults_confirm", "reset_confirm", "swap_confirm"):
        ctrl.noticed_input("its:button")
        setattr(ctrl, arm, ("h01", "a", "b") if arm == "swap_confirm" else True)
        ctrl._question_opened()
        assert ctrl.question_open()
        ctrl.noticed_input("another:button")
        assert not ctrl.question_open() and not getattr(ctrl, arm), arm


@pytest.mark.parametrize("something_else", ["another key", "tab", "time"])
def test_the_retry_question_ends_when_the_player_does_something_else(tmp_path, something_else):
    """Breaker, F1: after ten seconds, Tab, and a key nothing answers to, one R still started a new run."""
    play = Play(tmp_path, ["squire"])
    at_the_outcome(play)
    engine = play.ctrl.engine
    play.key(pygame.K_r)
    assert play.ctrl.message == RETRY and play.ctrl.asked("retry")
    if something_else == "another key":
        play.key(pygame.K_x)
    elif something_else == "tab":
        play.key(pygame.K_TAB)
    else:
        play.app.frame(AppController.QUESTION_MS)
    assert not play.ctrl.asked("retry") and play.ctrl.message == ""
    play.key(pygame.K_r)
    assert play.ctrl.screen == Screen.OUTCOME and play.ctrl.engine is engine and play.ctrl.message == RETRY, "it asks again; the result is kept"
    play.key(pygame.K_r)
    assert play.ctrl.screen == Screen.BATTLE, "two presses in a row still do it"


def test_resting_the_pointer_elsewhere_and_a_short_wait_do_not_end_a_question(tmp_path):
    play = Play(tmp_path, ["squire"])
    at_the_outcome(play)
    play.key(pygame.K_r)
    play.hover("out:menu")
    play.app.frame(2000)
    assert play.ctrl.asked("retry")
    play.key(pygame.K_r)
    assert play.ctrl.screen == Screen.BATTLE


@pytest.mark.parametrize("something_else", ["career:scout:select", "career:tab", "tab"])
def test_an_armed_dismiss_asks_again_after_anything_else_on_the_career_screen(tmp_path, monkeypatch, something_else):
    """Roster auditor, F1: selecting another vocation or opening Skills left Dismiss armed; the next press dismissed."""
    play = Evolution(tmp_path)
    play.click("slot:1:remove")
    play.click("roster:hero_002:career")
    play.click("career:dismiss")
    assert play.ctrl.asked("dismiss:hero_002")
    if something_else == "tab":
        play.key(pygame.K_TAB)
    else:
        play.click(something_else)
    assert not play.ctrl.asked("dismiss:hero_002") and "Dismiss this hero" in shown(play, monkeypatch)
    play.click("career:dismiss")
    assert "hero_002" in play.link.state.heroes and play.ctrl.asked("dismiss:hero_002"), "asked again, nobody dismissed"
    play.click("career:dismiss")
    assert "hero_002" not in play.link.state.heroes


def test_the_defaults_question_and_the_profile_question_are_never_open_together(tmp_path):
    """Breaker, F2: both stood open at once, and one later click reset every setting."""
    play = Configured(tmp_path)
    play.key(pygame.K_s)
    play.key(pygame.K_3)
    play.click("settings:class_evolution")
    play.click("settings:defaults")
    assert play.ctrl.defaults_confirm
    play.click("settings:reset")
    assert play.ctrl.reset_confirm and not play.ctrl.defaults_confirm
    play.click("settings:reset")  # "Keep the heroes (cancel)"
    assert not play.ctrl.reset_confirm and play.ctrl.message == "Nothing was deleted. Your saved heroes are kept."
    play.click("settings:defaults")
    assert play.ctrl.settings.class_evolution and play.ctrl.defaults_confirm, "one click only asks"
    play.click("settings:reset")
    assert play.ctrl.reset_confirm and not play.ctrl.defaults_confirm
    play.click("settings:defaults")
    assert play.ctrl.defaults_confirm and not play.ctrl.reset_confirm, "and the other way round"
    play.click("settings:defaults")
    assert not play.ctrl.settings.class_evolution and play.ctrl.message == "Every setting is back to its default."


def test_the_two_settings_questions_close_each_other_also_without_a_screen(tmp_path):
    """The rule is the controller's own: a front end that names no controls (a test, a script) gets it too."""
    ctrl = AppController(log_dir=tmp_path / "logs", features=["class_evolution_v1"], save_dir=tmp_path / "saves")
    OPENED.append(ctrl)
    ctrl.reset_settings()
    assert ctrl.defaults_confirm
    ctrl.reset_profile()
    assert ctrl.reset_confirm and not ctrl.defaults_confirm
    ctrl.reset_settings()
    assert ctrl.defaults_confirm and not ctrl.reset_confirm


def test_the_profile_question_keeps_its_own_confirm_button_and_lapses_with_time(tmp_path):
    play = Configured(tmp_path)
    play.key(pygame.K_s)
    play.key(pygame.K_3)
    play.click("settings:class_evolution")
    play.key(pygame.K_n) if False else None
    link = play.ctrl.progression
    assert link.recruit("squire").accepted
    play.click("settings:reset")
    play.app.frame(AppController.QUESTION_MS)
    assert not play.ctrl.reset_confirm and "settings:reset:confirm" not in play.ui.keys(), "the delete button is not left standing"
    play.click("settings:reset")
    play.click("settings:reset:confirm")  # another control, but the one that answers this question
    assert len(play.ctrl.progression.state.heroes) == 0 and "A new profile was made" in play.ctrl.message


def test_a_click_on_a_reactions_ally_asks_like_its_number_key_does(tmp_path):
    """Breaker, F3: by key the second reaction asked "Press again"; a click on its ally button spent it at once."""
    play = reacting(tmp_path)
    combat = play.combat
    play.key(pygame.K_1)  # Interpose: the first reaction on this enemy action
    assert len(combat.reactions_used) == 1 and "react:h02:h01" in play.ui.keys(), "Grounding offers two allies"
    play.click("react:h02:h01")
    assert len(combat.reactions_used) == 1
    assert play.ctrl.message == "A reaction was just used on this enemy action. Press again to use Grounding on Squire 1 as well."
    play.click("react:h02:h01")
    assert len(combat.reactions_used) == 2


def test_an_ally_chosen_after_its_row_is_the_second_of_two_presses_and_is_not_asked_for_again(tmp_path):
    """Row, then ally: the two presses are the deliberate choice. Only an ally button pressed on its own is asked for."""
    play = reacting(tmp_path)
    play.key(pygame.K_1)  # Interpose: a reaction was just used on this enemy action
    assert len(play.combat.reactions_used) == 1
    play.ctrl.reaction_hero = "h02"  # as after the row of a reaction that has several allies to choose from
    play.ctrl.choose_reaction_target("h02", "h01")
    assert len(play.combat.reactions_used) == 2 and not play.ctrl.question_open()


def test_the_phone_layer_names_the_control_too(tmp_path):
    ctrl = AppController(log_dir=tmp_path / "logs", touch=True)
    phone.act(ctrl, "menu:new")
    assert ctrl._input_source == "menu:new"


def test_an_armed_abandon_button_still_says_where_it_leads(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire", "scout"])
    play.begin()
    play.click("battle:menu")
    play.click("pause:menu")
    texts = shown(play, monkeypatch)
    assert "Press again: abandon, main menu" in texts and "Abandon Run: Change Party" in texts


# --------------------------------------------------------------------------------------------
# Keys and the focus ring
# --------------------------------------------------------------------------------------------


def test_b_is_not_back_on_the_career_screen_because_b_begins_the_encounter_behind_it(tmp_path):
    """Keyboard player, F1: C, B, B from the party screen started a run."""
    play = Evolution(tmp_path)
    play.key(pygame.K_c)
    assert play.ctrl.screen == Screen.CAREER
    play.key(pygame.K_b)
    assert play.ctrl.screen == Screen.CAREER and play.ctrl.engine is None
    play.key(pygame.K_k)  # the Skills tab has a Back button of its own
    play.key(pygame.K_b)
    assert play.ctrl.screen == Screen.CAREER and play.ctrl.career_tab == "skills"
    play.click("career:guardian:select")  # and so has the page of a vocation that cannot be played yet
    play.click("career:spellblade:select")
    play.key(pygame.K_b)
    assert play.ctrl.screen == Screen.CAREER
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.screen == Screen.PARTY_SETUP


def test_the_focus_ring_moves_to_a_neighbour_when_its_control_goes_away(tmp_path):
    """Keyboard player, F2: after "Remove" there was no ring, and every removal began again from the top."""
    play = Evolution(tmp_path, recruits=("squire", "scout", "apprentice"))
    play.ui.focus_key = "slot:2:remove"
    play.key(pygame.K_RETURN)
    assert len(play.ctrl.party) == 2 and play.ui.focus_key == "slot:1:remove"
    play.key(pygame.K_RETURN)
    assert len(play.ctrl.party) == 1 and play.ui.focus_key == "slot:0:remove"
    # On another screen nothing carries over.
    play.ui.focus_key = "party:back"
    play.key(pygame.K_RETURN)
    assert play.ctrl.screen == Screen.MAIN_MENU and play.ui.focus_key is None


def test_the_ring_is_not_carried_to_another_screen_that_happens_to_share_a_control():
    from battle_dice.ui.toolkit import UI

    def frame(ui: UI, keys: tuple[str, ...]) -> None:
        ui.begin(pygame.Surface((1280, 720)))
        for position, key in enumerate(keys):
            ui.button(key, 10, 10 + position * 50, 100, 40, key, lambda: None)
        ui.end()

    ui = UI()
    frame(ui, ("back", "a", "b", "c"))
    ui.focus_key = "c"
    frame(ui, ("back", "a", "b"))  # the same screen without "c": the ring goes to its neighbour
    assert ui.focus_key == "b"
    frame(ui, ("back", "x", "y", "z"))  # another screen: "back" is there too, but most controls are new
    assert ui.focus_key is None


def test_no_die_button_names_a_number_key_while_the_numbers_belong_to_the_targets(tmp_path, monkeypatch):
    """Keyboard player, F3: "Use (2)" stood beside "TARGET 2" while 2 picked the target."""
    play = Play(tmp_path, ["scout", "squire"])
    play.begin()
    play.to_roll_prompt()
    assert unit(engine_of(play), play.combat.turn.hero_id).archetype_id == "scout"
    play.roll_faces(striker_d8=face_number_after_roll(play, "striker_d8", "Shot"), tools_d4=face_number_after_roll(play, "tools_d4", "Quick Shot"))
    assert "(1)" in shown(play, monkeypatch) and "(2)" in shown(play, monkeypatch)
    play.key(pygame.K_1)
    assert play.ctrl.targeting_die == "striker_d8"
    texts = shown(play, monkeypatch)
    assert "(Esc)" in texts and "(1)" not in texts and "(2)" not in texts


def face_number_after_roll(play: Play, die_id: str, face_name: str) -> int:
    return face_number(play, die_id, face_name)


def test_the_planned_die_says_remove_from_the_plan_without_asking_for_a_click(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    play.roll_faces(iron_d6=face_number(play, "iron_d6", "Strike"))
    play.key(pygame.K_1)
    texts = shown(play, monkeypatch)
    assert "Remove" in texts and "from the plan" in texts and "(click)" not in texts
    assert "Party (choose a hero to inspect)" in screens.draw_party_setup.__code__.co_consts


def test_controls_has_its_key_in_the_pause_menu_as_on_the_main_menu(tmp_path):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.click("battle:menu")
    play.key(pygame.K_c)
    assert play.ctrl.pause_help


# --------------------------------------------------------------------------------------------
# What the screen says
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("corruption", "note"), [
    (0, "-0 corruption (Apprentice 1 has no corruption)"), (1, "-1 corruption (Apprentice 1 has 1 corruption)"), (2, ""), (5, "")])
def test_cleanse_says_what_it_will_really_remove(tmp_path, corruption, note):
    """Strategist, F1: "-2 corruption (self)" with no "Now" line, and the log then said "loses 0 corruption"."""
    play = Play(tmp_path, ["apprentice"])
    play.begin()
    play.to_roll_prompt()
    hero = unit(engine_of(play), "h01")
    hero.corruption = corruption
    play.roll_faces(arcane_d6=face_number(play, "arcane_d6", "Cleanse"), focus_d4=face_number(play, "focus_d4", "Blank"))
    assert rolled_die(play, "arcane_d6")["forecast"]["note"] == note
    face = engine_of(play).die_for("h01", "arcane_d6").faces[play.combat.turn.rolled["arcane_d6"]]
    assert action_forecast(engine_of(play), hero, face)["note"] == "", "without an intent nothing is predicted, as for the other amounts"
    play.click("die:arcane_d6:use")
    play.key(pygame.K_RETURN)
    play.until(lambda: any("loses" in line for line in combat_log(engine_of(play))))
    assert f"Apprentice 1 loses {min(corruption, 2)} corruption" in " ".join(combat_log(engine_of(play)))


def test_a_reactions_log_line_gives_its_amounts(tmp_path):
    """Strategist, F6: "reacts with Grounding on Squire 1." and nothing about the mana or the corruption."""
    play = reacting(tmp_path)
    play.key(pygame.K_1)
    play.click("react:h02:h01")
    play.click("react:h02:h01")
    log = combat_log(engine_of(play))
    assert "Squire 1 reacts with Interpose on Squire 1 (-1 mana): Squire 1 gains 2 shield." in log
    assert "Apprentice 2 reacts with Grounding on Squire 1: Squire 1 loses 1 corruption; Apprentice 2 gains 1 mana." in log


def test_a_statuss_time_is_said_from_where_the_unit_stands_in_its_activation(tmp_path, monkeypatch):
    """Strategist, F5: "2 activations left" during an activation whose poison damage had already landed."""
    play = Play(tmp_path, ["squire", "scout"])
    play.begin()
    play.to_roll_prompt()
    engine = engine_of(play)
    acting = play.combat.turn.hero_id
    other = "h02" if acting == "h01" else "h01"
    for hero_id in (acting, other):
        unit(engine, hero_id).status_instances.clear()
        add_status(engine, hero_id, "poison", remaining=2)
    play.hover(f"unit:{acting}")
    assert "Poison x1, this activation and 1 more: " in " ".join(shown(play, monkeypatch))
    play.hover(f"unit:{other}")
    assert "Poison x1, 2 activations left: " in " ".join(shown(play, monkeypatch))
    unit(engine, acting).status_instances.clear()
    add_status(engine, acting, "poison", remaining=1)
    play.hover(f"unit:{acting}")
    assert "Poison x1, this activation only: " in " ".join(shown(play, monkeypatch))


@pytest.mark.parametrize("size", SIZES)
def test_a_long_now_line_takes_two_lines_on_the_die_card_and_is_not_cut(tmp_path, monkeypatch, font, size):  # noqa: F811
    """Strategist, F4: "Now +3 shield (Steadfast +1, Squire 1 has 9 of at ..." on the card."""
    play = Play(tmp_path, ["squire"], size=size)
    play.begin()
    play.to_roll_prompt()
    unit(engine_of(play), "h01").shields = 9
    play.roll_faces(iron_d6=face_number(play, "iron_d6", "Guard"))
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    note = rolled_die(play, "iron_d6")["forecast"]["note"]
    assert note == "+3 shield (Steadfast +1, Squire 1 has 9 of at most 12)"
    assert not [text for text in shortened if "shield" in text], shortened
    assert "at most 12)" in " ".join(drawn)


def test_a_recruits_card_in_battle_says_its_class_and_a_named_hero_is_not_said_twice(tmp_path, monkeypatch):
    """Roster auditor, F3: with names that say no class, the cards told recruits apart by their pictures only."""
    play = Evolution(tmp_path)
    play.ctrl.begin_run()
    play.to_input()
    texts = shown(play, monkeypatch)
    assert "Recruit 1, Squire" in texts and "Recruit 2, Scout" in texts
    plain = Play(tmp_path / "plain", ["squire", "scout"])
    plain.begin()
    plain.to_input()
    texts = shown(plain, monkeypatch)
    assert "Squire 1" in texts and "Squire 1, Squire" not in texts


def test_the_career_title_names_the_class_beside_the_name(tmp_path, monkeypatch):
    play = Evolution(tmp_path)
    play.click("slot:1:career")
    assert "Career: Recruit 2, Scout" in shown(play, monkeypatch)
    play.click("career:apprentice:activate")
    assert "Career: Recruit 2, Apprentice" in shown(play, monkeypatch)
    assert play.ctrl.message == "Recruit 2 is now an Apprentice."
    play.key(pygame.K_k)
    assert "Capacity used: 0 of 2 as an Apprentice" in shown(play, monkeypatch)


def test_a_or_an():
    assert [with_article(noun) for noun in ("Squire", "Apprentice", "Archmage", "Guardian")] == ["a Squire", "an Apprentice", "an Archmage", "a Guardian"]


def test_a_roster_over_its_new_size_says_how_many_must_go(tmp_path):
    """Roster auditor, F6: 12 heroes, size 6, and the game said "The roster is full (6 heroes). ... dismiss a hero"."""
    play = Evolution(tmp_path, recruits=("squire",) * 4)
    play.link.career.service.roster_limit = 2
    play.app.frame(0)
    said = "The roster has 4 heroes and its size is now 2. To recruit, dismiss 3 heroes on their Career screens, or raise the roster size in Settings."
    assert play.ui.widget("add:scout").reason == said
    play.ctrl.add_hero("scout")
    assert play.ctrl.message == said and len(play.link.state.heroes) == 4
    play.link.career.service.roster_limit = 4
    play.app.frame(0)
    assert play.ui.widget("add:scout").reason == "The roster is full (4 heroes). To make room, dismiss a hero on its Career screen."


def test_the_pace_setting_says_both_directions_and_the_skills_tab_says_what_stays(tmp_path, monkeypatch):
    """Roster auditor, F2 and F7: skills stayed without a word, and the help named the faster direction only."""
    play = Configured(tmp_path, fixed_seed=11)
    play.key(pygame.K_s)
    play.key(pygame.K_3)
    play.click("settings:class_evolution")
    play.key(pygame.K_4)
    row = next(r for r in play.ctrl.settings_view() if r["key"] == "mastery_pace")
    assert row["help"] == "Points a rank needs. Faster raises ranks, slower lowers them; opened vocations and skills stay."
    while play.ctrl.settings.mastery_pace != "very_fast":
        play.click("settings:mastery_pace")
    while next(r for r in play.ctrl.settings_view() if r["key"] == "demo_preset")["value"] != "A Guardian with Field Medic":
        play.click("settings:demo_preset")
    play.key(pygame.K_3)
    play.click("settings:reset")
    play.click("settings:reset:confirm")
    play.key(pygame.K_ESCAPE)
    play.key(pygame.K_n)
    play.click("roster:hero_001:add")
    play.click("slot:0:career")
    play.key(pygame.K_k)
    skills = {r["skill_id"]: r["earlier_pace"] for r in play.ctrl.skills_view()["rows"]}
    assert skills == {"squire_anchor": False, "guardian_field_medic": False}
    assert "earlier Mastery pace" not in " ".join(shown(play, monkeypatch))
    play.key(pygame.K_ESCAPE)
    slow_the_pace(play)
    assert [member["hero_id"] for member in play.ctrl.party] == ["hero_001"], "the party outlives a change of pace"
    play.click("slot:0:career")
    play.key(pygame.K_k)
    skills = {r["skill_id"]: r["earlier_pace"] for r in play.ctrl.skills_view()["rows"]}
    assert skills == {"squire_anchor": False, "guardian_field_medic": True}, "the Guardian is no longer at the rank that teaches Field Medic"
    assert "A skill learned at an earlier Mastery pace stays learned." in " ".join(shown(play, monkeypatch))


def test_switching_class_evolution_still_empties_the_party(tmp_path):
    play = Configured(tmp_path)
    play.key(pygame.K_s)
    play.key(pygame.K_3)
    play.click("settings:class_evolution")
    play.ctrl.new_run()
    play.ctrl.add_hero("squire")
    assert len(play.ctrl.party) == 1
    play.ctrl.open_settings()
    play.ctrl.select_settings_tab("evolution")
    play.app.frame(0)
    play.click("settings:class_evolution")
    assert play.ctrl.party == [] and play.ctrl.progression is None


def test_the_party_note_says_what_is_true(tmp_path):
    """Strategist, F8: "more and tougher enemies"; each enemy of a larger party is not tougher."""
    met = {}
    for party in (["squire", "scout"], ["squire", "scout", "apprentice"], ["squire", "scout", "apprentice", "squire", "scout"]):
        play = Play(tmp_path / str(len(party)), party)
        play.begin()
        enemies = [u for u in play.combat.combatants.values() if not u.is_hero]
        met[len(party)] = (len(enemies), max(u.max_hp for u in enemies))
    assert [met[size][0] for size in (2, 3, 5)] == [2, 3, 5], "more heroes meet more enemies"
    assert met[3][1] < met[2][1] and met[5][1] < met[2][1], "and no single enemy is tougher than a pair of heroes meets"
    assert screens.PARTY_NOTE.startswith("More heroes meet more enemies.")


def test_one_legal_ally_is_picked_and_named_like_one_legal_enemy(tmp_path):
    """Breaker, F4: a lone hero's shield die still asked "Choose a target" for the only one there was."""
    play = Play(tmp_path, ["scout"])
    play.begin()
    play.to_roll_prompt()
    play.roll_faces(striker_d8=face_number(play, "striker_d8", "Blank"), tools_d4=face_number(play, "tools_d4", "Cover"))
    play.key(pygame.K_2)
    assert play.ctrl.targeting_die is None and play.ctrl.draft == [{"die_id": "tools_d4", "target_ids": ["h01"]}]
    assert play.ctrl.message.startswith("Cover aims at Scout 1, the only legal target.")


def test_the_seed_entry_says_why_it_refuses_and_stays_open_for_a_correction(tmp_path):
    """Breaker, F6: digits after the 20th vanished without a word, and a number too large closed the entry."""
    play = Configured(tmp_path)
    play.key(pygame.K_n)
    play.key(pygame.K_d)
    for _ in range(AppController.SEED_DIGITS):
        play.key(pygame.K_9)
    play.key(pygame.K_9)
    assert play.ctrl.seed_entry == "9" * 20 and play.ctrl.message == "A seed has at most 20 digits. Enter sets it, Esc cancels."
    play.key(pygame.K_x)
    assert play.ctrl.seed_entry == "9" * 20 and play.ctrl.message == "A seed is made of digits. Enter sets it, Esc cancels."
    play.key(pygame.K_RETURN)
    assert play.ctrl.seed_entry == "9" * 20 and play.ctrl.message.endswith("Shorten it, or press Esc."), "still being typed"
    for _ in range(3):
        play.key(pygame.K_BACKSPACE)
    play.key(pygame.K_RETURN)
    assert play.ctrl.seed_entry is None and play.ctrl.fixed_seed == int("9" * 17)
