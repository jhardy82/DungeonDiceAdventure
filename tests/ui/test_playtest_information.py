"""Missing information and small layout faults: fixes for the playtest of 2026-11-21, batch 5 (owner decision D-34)."""

from __future__ import annotations

import pygame
import pytest

from battle_dice.app.controller import Screen
from battle_dice.core.engine import Engine
from battle_dice.core.view import combat_log, describe_event, snapshot
from battle_dice.ui import screens, toolkit
from tests.conftest import (
    begin_enemy,
    captain_content,
    enemies,
    enemy_acts,
    events_of,
    force_slash,
    packaged_content,
    start,
    unit,
    win_battle,
)
from tests.ui.test_evolution_ui import Configured, Evolution, close_every_save  # noqa: F401 - the fixture closes the saves
from tests.ui.test_ui_flow import Play, record_text

SIZES = pytest.mark.parametrize("size", [(1280, 720), (960, 540)], ids=["1280x720", "960x540"])
#: Fonts of very different widths, as other machines have them. () is pygame's own font.
FONTS = pytest.mark.parametrize("fonts", [("dejavusans",), (), ("liberationmono",), ("dejavuserif",), ("liberationsans",)],
                                ids=lambda fonts: fonts[0] if fonts else "pygame")


def engine_of(play: Play) -> Engine:
    engine = play.ctrl.engine
    assert engine is not None
    return engine


# --------------------------------------------------------------------------------------------
# M3: why no reaction prompt came, or why it began at a later stage
# --------------------------------------------------------------------------------------------


def test_the_log_says_when_no_hero_could_react():
    engine = start("squire", content=packaged_content())
    force_slash(engine)
    unit(engine, "h01").mana = 0  # Interpose costs 1 mana
    enemy_acts(engine, enemies(engine)[0].id)
    log = combat_log(engine)
    assert "No hero could react to this enemy action." in log
    assert not any("stage" in line and "No hero" in line for line in log), "three stages passed are one plain sentence"
    intends = next(index for index, line in enumerate(log) if " intends " in line)
    assert log[intends + 1] == "No hero could react to this enemy action.", "right after the action is revealed"


def test_the_log_says_when_an_enemy_action_cannot_be_reacted_to():
    engine = start("scout", content=captain_content(1))
    captain = enemies(engine)[0]
    begin_enemy(engine, captain.id)
    assert engine.combat.committed_intent is not None and engine.combat.committed_intent.name == "War Cry"
    assert "No reaction: this enemy action cannot be reacted to." in combat_log(engine)


def test_a_prompt_that_begins_at_a_later_stage_says_which_stages_had_nothing_to_offer(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire", "apprentice"])
    play.begin()
    engine = engine_of(play)
    force_slash(engine)
    unit(engine, "h01").mana = 0   # no Interpose: the Guard stage has nothing to offer
    for hero_id in ("h01", "h02"):
        unit(engine, hero_id).corruption = 2  # Grounding has something to do: the Resource stage opens
    play.until(lambda: play.ui.widget("react:h02") is not None and play.ui.widget("react:h02").enabled)
    view = play.ctrl.view()["reaction"]
    assert (view["stage"], view["stage_number"], view["passed"]) == ("resource", 2, ["guard"])
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert "Reaction window: stage 2 of 3: Resource   (Guard: no hero could react)" in drawn
    assert "No hero could react in the Guard stage." in combat_log(engine)


def test_a_prompt_that_begins_at_the_first_stage_shows_the_order_of_the_stages(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"])
    play.begin()
    force_slash(engine_of(play))
    play.until(lambda: play.ui.widget("react:h01") is not None and play.ui.widget("react:h01").enabled)
    assert play.ctrl.view()["reaction"]["passed"] == []
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert "Reaction window: stage 1 of 3: Guard   (Guard -> Resource -> Interrupt -> enemy action)" in drawn


# --------------------------------------------------------------------------------------------
# M9: what the recovery gave
# --------------------------------------------------------------------------------------------


def test_the_recovery_is_given_in_numbers(tmp_path):
    play = Play(tmp_path, ["squire", "scout"])
    play.begin()
    engine = engine_of(play)
    unit(engine, "h02").hp = 3
    win_battle(engine)
    play.ctrl.refresh()
    play.app.frame(0)
    assert play.ctrl.screen == Screen.UPGRADE
    recovered = play.ctrl.recovery_view()
    assert recovered["h02"][0] == 3 and recovered["h02"][1] == unit(engine, "h02").hp > 3
    line = next(line for line in combat_log(engine) if line.startswith("Recovery: "))
    assert f"Scout 2 3 -> {recovered['h02'][1]} HP" in line and "partly" not in line
    assert line.endswith("Mana refilled, shields and statuses cleared. Corruption persists.")
    tip = play.ui.widget("up:hero:h02").tooltip or ""
    assert f"Recovery: 3 -> {recovered['h02'][1]} HP" in tip and "partly" not in tip


def test_a_hero_that_was_down_is_marked_in_the_recovery_line():
    engine = start("squire", "scout", content=packaged_content())
    from tests.conftest import down

    down(engine, "h02")
    win_battle(engine)
    line = next(line for line in combat_log(engine) if line.startswith("Recovery: "))
    assert f"Scout 2 0 -> {unit(engine, 'h02').hp} HP (was down)" in line and "Squire 1" in line and "(was down)" not in line.split("Scout 2")[0]


# --------------------------------------------------------------------------------------------
# M5, M6, M7, M11: what the screens say
# --------------------------------------------------------------------------------------------


@SIZES
@FONTS
def test_both_party_screens_say_what_size_and_rows_change(tmp_path, monkeypatch, size, fonts):
    monkeypatch.setattr(toolkit, "FONT_CANDIDATES", fonts)
    for name, play in (("shipped", Play(tmp_path / "a", ["squire"], size=size)), ("saved heroes", Evolution(tmp_path / "b", size=size))):
        drawn, shortened = record_text(monkeypatch)
        play.app.frame(0)
        monkeypatch.undo()
        monkeypatch.setattr(toolkit, "FONT_CANDIDATES", fonts)
        assert play.ctrl.screen == Screen.PARTY_SETUP, name
        assert screens.PARTY_NOTE in drawn and screens.PARTY_NOTE not in shortened, name
    assert "more and tougher enemies" in screens.PARTY_NOTE and "front row" in screens.PARTY_NOTE


def test_the_controls_help_explains_the_shorthand_of_the_board(tmp_path, monkeypatch):
    board = dict(screens.CONTROLS_TEXT)["Reading the board"]
    for word in ("a tick is one step", "Initiative breaks a tie", "'speed' on a die face", "'v1' after a die", "'React 1' is a reaction charge"):
        assert word in board, word
    play = Play(tmp_path, ["squire"])
    play.ctrl.show_controls()
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    shown = next(text for text in drawn if "'React 1' is a reaction charge" in text)
    assert shown not in shortened and "{" not in shown


def test_the_outcome_screen_says_how_to_play_the_seed_again_in_the_games_own_terms(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"], seed=11)
    play.begin()
    from tests.conftest import down

    down(engine_of(play), "h01")
    play.ctrl.settings.confirm_pass = False
    play.until(lambda: False)
    assert play.ctrl.screen == Screen.OUTCOME
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    line = "Seed 11. To play the same dice again: New Run, Dice seed (D), type 11."
    assert line in drawn and line not in shortened and not any("--seed" in text for text in drawn)


def test_small_wordings(tmp_path):
    play = Play(tmp_path, [])
    assert (play.ui.widget("add:apprentice").tooltip or "").startswith("Add an Apprentice (")
    assert (play.ui.widget("add:squire").tooltip or "").startswith("Add a Squire (")
    configured = Configured(tmp_path / "c")
    configured.ctrl.open_settings()
    configured.app.frame(0)
    assert configured.ui.widget("settings:high_contrast").tooltip == "Click to change it, or press Enter while it has the focus ring."
    assert (configured.ui.widget("settings:defaults").tooltip or "").endswith("Asked once more.")


def test_an_enemys_area_attack_is_said_to_hit_the_heroes():
    engine = start("scout", content=captain_content(1))
    captain = next(c for c in snapshot(engine)["combatants"] if c["side"] == "enemy")
    wave = next(a for a in captain["actions"] if a["name"] == "Blight Wave")
    assert wave["text"] == "1 ranged damage to all heroes"
    hero = start("squire", content=packaged_content())
    assert not any("heroes" in face["text"] for c in snapshot(hero)["combatants"] if c["side"] == "hero" for die in c["dice"] for face in die["faces"])


def test_a_resisted_interrupt_names_only_what_it_changed():
    engine = start("scout", content=captain_content(1))
    captain = enemies(engine)[0]
    from battle_dice.core import commands as cmd
    from battle_dice.core.events import EventType
    from battle_dice.core.models import CombatPhase
    from tests.conftest import finish_activation, ok, skip_reactions

    for _ in range(40):
        begin_enemy(engine, captain.id)
        if engine.combat.committed_intent.name == "Strike" and engine.combat.phase == CombatPhase.INTERRUPT_WINDOW:
            break
        skip_reactions(engine)
        finish_activation(engine)
        unit(engine, "h01").hp, unit(engine, "h01").mana = unit(engine, "h01").max_hp, unit(engine, "h01").max_mana
    else:
        raise AssertionError("the captain never used Strike with Disrupt available")
    ok(engine.do(cmd.USE_REACTION, hero_id="h01", target_id=None))
    event = events_of(engine, EventType.INTENT_WEAKENED)[-1]
    line = describe_event(event, {})
    assert line == "Strike resists the interrupt but is weakened (-2 damage)." and "-0" not in line


# --------------------------------------------------------------------------------------------
# L7: a long path keeps its end
# --------------------------------------------------------------------------------------------


def test_a_long_path_keeps_its_end(tmp_path):
    play = Play(tmp_path, ["squire"])
    ui = play.ui
    short = screens.path_text(ui, "Save file: ", "C:/saves/profile.sqlite", 13, 656)
    assert short == "Save file: C:/saves/profile.sqlite"
    long_path = "C:/Users/someone/AppData/Local/BattleDice/" + "a_very_long_folder_name/" * 12 + "saves/profile.sqlite"
    shown = screens.path_text(ui, "Save file: ", long_path, 13, 656)
    assert shown.startswith("Save file: ...") and shown.endswith("saves/profile.sqlite") and ui.text_width(shown, 13) <= 656
    assert len(shown) > len("Save file: ...profile.sqlite"), "as much of the path as fits"


# --------------------------------------------------------------------------------------------
# A3: a class can be read by keyboard before a hero of it is added
# --------------------------------------------------------------------------------------------


def test_the_class_sheet_follows_the_add_button_that_is_focused_or_pointed_at(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"])
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert "Class: Squire" in drawn, "with nothing looked at: the selected hero's class"
    for _ in range(40):  # the focus ring, by Tab alone
        if play.ui.focus_key == "add:apprentice":
            break
        play.key(pygame.K_TAB)
    assert play.ui.focus_key == "add:apprentice"
    drawn.clear()
    play.app.frame(0)
    assert "Class: Apprentice" in drawn and "Class: Squire" not in drawn
    assert len(play.ctrl.party) == 1, "reading a class adds nobody"
    play.ui.focus_key = None
    play.hover("add:scout")
    drawn.clear()
    play.app.frame(0)
    assert "Class: Scout" in drawn


# --------------------------------------------------------------------------------------------
# S4: a bench swap is asked for once more
# --------------------------------------------------------------------------------------------


def test_every_bench_swap_is_asked_for_once_more(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"])
    play.begin()
    engine = engine_of(play)
    win_battle(engine)
    play.ctrl.refresh()
    play.app.frame(0)
    play.click("up:offer:0")
    play.click("up:apply")
    hero = unit(engine, "h01")
    free = next(die_id for die_id in hero.equipped_dice_ids if die_id not in engine.state.die_overrides.get("h01", {}) and engine.die_for("h01", die_id).size <= 4)
    key = f"up:swap:h01:{free}"
    assert play.ui.widget(key) is not None and play.ui.widget(key).enabled
    play.click(key)
    assert free in hero.equipped_dice_ids, "the first press only asks"
    assert play.ctrl.message.endswith("A swap cannot be undone. Press the same swap again to confirm.")
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert any(text.startswith("Press again: give up ") for text in drawn)
    play.click(key)
    assert free not in hero.equipped_dice_ids and play.ctrl.message == "Die swapped."


# --------------------------------------------------------------------------------------------
# Three cases the deliberate breaks showed were not tested
# --------------------------------------------------------------------------------------------


def test_the_same_face_reads_by_whose_it_is():
    from battle_dice.core.view import describe_face, face_view

    engine = start("scout", content=captain_content(1))
    wave = engine.enemy_action(enemies(engine)[0], "blight_wave")
    assert describe_face(wave) == face_view(wave)["text"] == "1 ranged damage to all enemies", "as a hero's face it would hit the enemies"
    assert describe_face(wave, by_enemy=True) == face_view(wave, by_enemy=True)["text"] == "1 ranged damage to all heroes"


def test_the_stages_passed_are_those_of_the_enemy_action_under_way_only(tmp_path):
    play = Play(tmp_path, ["squire", "apprentice"])
    play.begin()
    engine = engine_of(play)
    force_slash(engine)
    unit(engine, "h01").mana = 0
    for hero_id in ("h01", "h02"):
        unit(engine, hero_id).corruption = 2
    play.until(lambda: play.ui.widget("react:h02") is not None and play.ui.widget("react:h02").enabled)
    first = engine.combat.committed_intent.id
    assert play.ctrl.view()["reaction"]["passed"] == ["guard"]
    play.key(pygame.K_a)  # no reaction to this one
    for hero_id in ("h01", "h02"):
        hero = unit(engine, hero_id)
        hero.hp, hero.mana, hero.corruption = hero.max_hp, hero.max_mana, 2
    play.until(lambda: play.ui.widget("react:h01") is not None and play.ui.widget("react:h01").enabled
               and engine.combat.committed_intent.id != first)
    reaction = play.ctrl.view()["reaction"]
    assert (reaction["stage"], reaction["passed"]) == ("guard", []), "the Guard stage of the earlier action is not this one's"


def test_a_stage_the_player_skipped_is_said_as_skipped(tmp_path):
    play = Play(tmp_path, ["squire"])
    play.begin()
    engine = engine_of(play)
    force_slash(engine)
    play.until(lambda: play.ui.widget("react:h01") is not None and play.ui.widget("react:h01").enabled)
    before = len(combat_log(engine))
    play.key(pygame.K_s)
    since = combat_log(engine)[before:]
    assert "Guard stage skipped." in since, "the player's own choice, in the player's words"
    assert "No hero could react in the Guard stage." not in since and "No hero could react to this enemy action." not in since
