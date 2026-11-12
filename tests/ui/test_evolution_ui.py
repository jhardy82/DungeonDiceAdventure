"""The screens that make Class Evolution playable (Phase 4, step D).

With the feature gate on the app opens a save, the party is made of saved heroes, a hero has a
career screen, and after Battle 2 the player stops with a victory or fights on. With the gate off
none of it exists and no save file is made.
"""

from __future__ import annotations

import subprocess
import sys

import pygame
import pytest

from battle_dice.app.controller import AppController, Screen, default_save_dir
from battle_dice.career.model import MasteryRow
from battle_dice.core import commands as cmd
from battle_dice.features import CLASS_EVOLUTION
from battle_dice.sim.policies import HeuristicPolicy
from battle_dice.ui import screens
from battle_dice.ui.app import GameApp
from tests.conftest import begin_hero, down, unit, win_battle
from tests.ui.test_ui_flow import SIZES, Play, font, record_text  # noqa: F401 - font is a fixture

OPENED: list[AppController] = []


@pytest.fixture(autouse=True)
def close_every_save():
    """Each game a test opens holds a save file open; close them all when the test is over."""
    yield
    while OPENED:
        OPENED.pop().close()


class Evolution(Play):
    """A headless game with the Class Evolution gate on and its save in the test's own folder."""

    def __init__(self, tmp_path, recruits=("squire", "scout"), seed=11, size=(1280, 720)):
        self.ctrl = AppController(fixed_seed=seed, log_dir=tmp_path / "logs", features=[CLASS_EVOLUTION])
        OPENED.append(self.ctrl)
        self.app = GameApp(self.ctrl, size=size, headless=True, animations=False)
        self.app.fast = True
        self.ctrl.new_run()
        for class_id in recruits:
            self.ctrl.add_hero(class_id)
        self.app.frame(0)

    @property
    def link(self):
        return self.ctrl.progression

    def to_the_decision(self):
        """Win both shipped battles, so the run waits for: stop, or fight on."""
        self.ctrl.begin_run()
        engine = self.ctrl.engine
        assert engine is not None
        win_battle(engine)
        offer = next(o for dice in engine.state.upgrade_offers.values() for die in dice.values() for o in die)
        assert engine.do(cmd.CHOOSE_UPGRADE, hero_id=offer["hero_id"], die_id=offer["die_id"], offer_id=offer["offer_id"]).accepted
        assert engine.do(cmd.ADVANCE_PHASE).accepted
        win_battle(engine)
        self.ctrl.refresh()
        self.app.frame(0)
        assert self.ctrl.screen == Screen.CONTINUE


def master(play: Evolution, hero_id: str, vocation_id: str) -> None:
    """Arranged: the hero has mastered a vocation (14 points for a starting class)."""
    top = play.link.catalog.thresholds(vocation_id)[-1]
    play.link.state.heroes[hero_id].mastery[vocation_id] = MasteryRow(vocation_id, 8, top)


# --------------------------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------------------------


def test_with_the_gate_off_there_is_no_save_and_the_party_setup_is_the_old_one(tmp_path):
    play = Play(tmp_path, ["squire"])
    assert play.ctrl.progression is None and play.ctrl.progression_error is None
    assert not list(tmp_path.rglob("*.sqlite*"))
    keys = play.ui.keys()
    assert "add:squire" in keys and not [key for key in keys if key.startswith("roster:") or key.endswith(":career")]
    assert play.ctrl.party == [{"class_id": "squire", "row": "front"}]


def test_with_the_gate_off_the_save_code_is_never_imported(tmp_path):
    """A fresh interpreter: creating the game and starting a run loads neither the save module nor SQLite."""
    code = (
        "import os, sys\n"
        "os.environ['SDL_VIDEODRIVER'] = 'dummy'; os.environ['SDL_AUDIODRIVER'] = 'dummy'\n"
        "from battle_dice.app.controller import AppController\n"
        f"ctrl = AppController(fixed_seed=1, log_dir=r'{tmp_path / 'logs'}')\n"
        "ctrl.new_run(); ctrl.add_hero('squire'); ctrl.begin_run()\n"
        "assert ctrl.engine is not None and ctrl.progression is None\n"
        "print(sorted(m for m in sys.modules if m in ('sqlite3', 'battle_dice.app.progression', 'battle_dice.career.store')))\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert done.stdout.strip().splitlines()[-1] == "[]"
    assert not list(tmp_path.rglob("*.sqlite*"))


def test_with_the_gate_on_the_save_is_opened_where_the_caller_keeps_its_files(tmp_path, monkeypatch):
    """A redirected log folder keeps its save inside itself; only the default log folder has the save beside it."""
    play = Evolution(tmp_path, recruits=())
    assert play.link is not None and play.link.path == tmp_path / "logs" / "saves" / "profile.sqlite" and play.link.path.is_file()
    assert default_save_dir(tmp_path / "logs") == tmp_path / "logs" / "saves"
    monkeypatch.delenv("BATTLE_DICE_LOG_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert default_save_dir() == tmp_path / "saves"  # from source: ./logs and ./saves side by side
    monkeypatch.setenv("BATTLE_DICE_SAVE_DIR", str(tmp_path / "elsewhere"))
    assert default_save_dir(tmp_path / "logs") == default_save_dir() == tmp_path / "elsewhere"
    other = AppController(fixed_seed=1, log_dir=tmp_path / "x", features=[CLASS_EVOLUTION], save_dir=tmp_path / "chosen")
    OPENED.append(other)
    assert other.progression.path == tmp_path / "chosen" / "profile.sqlite"


def test_a_save_that_cannot_be_opened_leaves_a_working_game_without_saved_heroes(tmp_path):
    blocked = tmp_path / "not_a_folder"
    blocked.write_text("a file where the save folder should be")
    ctrl = AppController(fixed_seed=1, log_dir=tmp_path / "logs", features=[CLASS_EVOLUTION], save_dir=blocked)
    OPENED.append(ctrl)
    assert ctrl.progression is None and "could not be opened" in (ctrl.progression_error or "")
    app = GameApp(ctrl, headless=True, animations=False)
    ctrl.new_run()
    ctrl.add_hero("squire")
    app.frame(0)
    assert ctrl.party == [{"class_id": "squire", "row": "front"}] and "add:squire" in app.ui.keys()
    ctrl.begin_run()
    assert ctrl.screen == Screen.BATTLE and app.render_faults == 0


# --------------------------------------------------------------------------------------------
# Party setup with saved heroes
# --------------------------------------------------------------------------------------------


def test_number_keys_recruit_heroes_into_the_party_and_they_are_saved(tmp_path):
    play = Evolution(tmp_path, recruits=())
    for key in (pygame.K_1, pygame.K_2, pygame.K_3):
        play.key(key)
    assert play.ctrl.party == [
        {"class_id": "squire", "row": "front", "hero_id": "hero_001"},
        {"class_id": "apprentice", "row": "back", "hero_id": "hero_002"},
        {"class_id": "scout", "row": "back", "hero_id": "hero_003"}]
    assert [row["name"] for row in play.ctrl.roster_view()] == ["Squire 1", "Apprentice 2", "Scout 3"]
    assert all(row["in_party"] for row in play.ctrl.roster_view())
    assert play.link.store.conn.execute("SELECT COUNT(*) FROM hero").fetchone()[0] == 3
    assert "Recruited Scout 3" in play.ctrl.message


def test_a_hero_can_leave_the_party_and_come_back_from_the_roster(tmp_path):
    play = Evolution(tmp_path)
    assert play.ui.widget("roster:hero_001:add").enabled is False and play.ui.widget("roster:hero_001:add").reason == "Already in the party."
    play.click("slot:0:remove")
    assert [m["hero_id"] for m in play.ctrl.party] == ["hero_002"] and len(play.link.state.heroes) == 2
    play.click("roster:hero_001:add")
    assert [m["hero_id"] for m in play.ctrl.party] == ["hero_002", "hero_001"]
    play.click("slot:1:row")
    assert play.ctrl.party[1]["row"] == "back" and "Squire 1 moves to the back row" in play.ctrl.message


def test_a_hero_is_in_the_party_once_however_it_is_asked_for(tmp_path):
    play = Evolution(tmp_path)
    play.ctrl.add_saved_hero("hero_001")  # asked for directly, past the disabled button
    assert [m["hero_id"] for m in play.ctrl.party] == ["hero_001", "hero_002"]
    assert play.ctrl.message == "That hero is already in the party." and play.ctrl.message_is_error


def test_each_slot_opens_the_career_of_its_own_hero(tmp_path):
    play = Evolution(tmp_path)
    play.click("slot:1:career")
    assert play.ctrl.screen == Screen.CAREER and play.ctrl.career_hero == "hero_002"
    assert play.ctrl.career_view()["name"] == "Scout 2" and play.ctrl.career_view()["active_vocation_id"] == "scout"
    play.click("career:back")
    play.click("roster:hero_001:career")
    assert play.ctrl.career_hero == "hero_001"


def test_the_self_check_walks_the_whole_flow_and_leaves_no_file_behind(tmp_path, monkeypatch, capsys):
    """``--smoke-test --feature class_evolution_v1``: recruit, career screen, three battles, awards in the save."""
    from battle_dice.__main__ import run_smoke_test

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BATTLE_DICE_SAVE_DIR", raising=False)
    monkeypatch.delenv("BATTLE_DICE_LOG_DIR", raising=False)
    report = tmp_path / "report.txt"
    assert run_smoke_test(str(report), frozenset({CLASS_EVOLUTION})) == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert line.startswith("SMOKE TEST OK") and "features=class_evolution_v1" in line
    assert "'career'" in line and "'continue'" in line and "'outcome'" in line
    assert " evolved_run=victory" in line or " evolved_run=defeat" in line, "a run with a Guardian from the catalog was played too"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["report.txt"]  # its logs and its save were in its own temporary folder


def test_the_sixth_recruit_waits_in_the_roster_and_the_thirteenth_is_refused(tmp_path):
    play = Evolution(tmp_path, recruits=["scout"] * 6)
    assert len(play.ctrl.party) == 5 and len(play.link.state.heroes) == 6 and "waits in the roster" in play.ctrl.message
    assert play.ui.widget("roster:hero_006:add").reason == "The party already has 5 heroes."
    for _ in range(6):
        play.ctrl.add_hero("squire")
    play.app.frame(0)
    assert len(play.link.state.heroes) == 12 and play.ui.widget("add:squire").enabled is False
    assert play.ui.widget("add:squire").reason == "The roster is full (12 heroes)."
    play.ctrl.recruit("scout")
    assert len(play.link.state.heroes) == 12 and "The roster is full (12 heroes)" in play.ctrl.message and play.ctrl.message_is_error


def test_a_run_with_saved_heroes_starts_with_their_snapshots_and_the_third_battle(tmp_path):
    play = Evolution(tmp_path)
    play.click("party:begin")
    engine = play.ctrl.engine
    assert play.ctrl.screen == Screen.BATTLE and engine.state.run_id == "run-0001-11" and engine.battle_count == 3
    assert [member.get("hero_id") for member in engine.state.party] == ["hero_001", "hero_002"]
    assert [engine.combat.combatants[h].name for h in ("h01", "h02")] == ["Squire 1", "Scout 2"]
    assert play.link.state.run.phase == "battle"
    play.ctrl.third_battle = False
    play.ctrl.abandon_to_party()
    play.app.frame(0)
    assert play.link.state.run.phase == "defeat"  # the abandoned run is closed in the save
    play.click("party:begin")
    assert play.ctrl.engine.battle_count == 2 and play.ctrl.engine.state.run_id == "run-0002-11"


def test_leaving_a_run_frees_the_roster_again(tmp_path):
    play = Evolution(tmp_path)
    play.click("party:begin")
    play.ctrl.recruit("scout")
    assert "between runs" in play.ctrl.message and len(play.link.state.heroes) == 2
    play.ctrl.abandon_to_menu()
    play.ctrl.new_run()
    play.ctrl.recruit("scout")
    assert len(play.link.state.heroes) == 3 and not play.ctrl.message_is_error


# --------------------------------------------------------------------------------------------
# The career screen
# --------------------------------------------------------------------------------------------


def test_the_career_screen_lists_every_public_vocation_and_two_anonymous_entries(tmp_path):
    play = Evolution(tmp_path)
    play.click("slot:0:career")
    assert play.ctrl.screen == Screen.CAREER
    view = play.ctrl.career_view()
    assert [row.get("vocation_id") for row in view["rows"]][:4] == ["squire", "apprentice", "scout", "guardian"]
    assert [row["label"] for row in view["rows"] if row["kind"] != "vocation"] == ["???", "???"]
    by_id = {row["vocation_id"]: row for row in view["rows"] if row["kind"] == "vocation"}
    assert by_id["squire"]["status"] == "Active: rank 1, 0/1 to the next" and not by_id["squire"]["can_activate"]
    assert by_id["scout"]["status"] == "Unlocked: rank 1, 0/1 to the next" and by_id["scout"]["can_activate"]
    assert (by_id["guardian"]["status"], by_id["guardian"]["needs"]) == ("Locked", "Needs: master Squire (now rank 1).")
    claim = play.ui.widget("career:guardian:claim")
    assert claim.enabled is False and claim.reason == "Needs: master Squire (now rank 1)."
    assert play.ui.widget("career:squire:activate").reason == "This is the active vocation."
    text = " ".join(str(value) for row in view["rows"] for value in row.values())
    assert "Trickster" not in text and "Dragon" not in text  # a hidden vocation shows nothing but ???
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.screen == Screen.PARTY_SETUP and play.ctrl.career_hero is None


def test_a_mastered_squire_claims_the_guardian_becomes_one_and_fights_as_one(tmp_path):
    play = Evolution(tmp_path)
    master(play, "hero_001", "squire")
    play.click("slot:0:career")
    assert play.ui.widget("career:guardian:claim").enabled is True
    play.click("career:guardian:claim")
    assert "guardian" in play.link.state.heroes["hero_001"].unlocked_vocations and "has unlocked Guardian" in play.ctrl.message
    assert play.ctrl.career_view()["selected"] == "guardian"
    play.click("career:guardian:activate")
    assert play.link.state.heroes["hero_001"].active_vocation_id == "guardian" and "is now a Guardian" in play.ctrl.message
    play.click("career:back")
    assert play.ctrl.party[0] == {"class_id": "guardian", "row": "front", "hero_id": "hero_001"}
    assert (play.ctrl.roster_view()[0]["vocation_name"], play.ctrl.roster_view()[0]["rank"]) == ("Guardian", 1)
    play.click("party:begin")
    engine = play.ctrl.engine
    hero = engine.combat.combatants["h01"]
    assert engine.build("h01").vocation_id == "guardian" and hero.max_hp == 18  # 17, and +1 for the mastered Squire
    assert hero.equipped_dice_ids == ["guardian_d6", "guardian_d4"] and play.app.render_faults == 0


def test_selecting_a_locked_vocation_spells_out_what_it_needs(tmp_path, monkeypatch):
    play = Evolution(tmp_path)
    play.click("slot:0:career")
    drawn, _ = record_text(monkeypatch)
    play.click("career:champion:select")
    play.app.frame(0)
    view = play.ctrl.career_view()
    needs = view["selected_needs"]
    # The Champion is in the catalog but the rules cannot run it yet: the screen says so, and what it would need.
    assert needs.startswith("Not in this version yet. Needs: master Guardian (now rank 0); master Duelist") and needs in drawn
    champion = next(row for row in view["rows"] if row.get("vocation_id") == "champion")
    assert (champion["status"], champion["playable"], champion["can_claim"]) == ("Coming later", False, False)
    assert play.ui.widget("career:champion:claim").enabled is False and play.app.render_faults == 0
    assert play.ctrl.playable("guardian") and play.ctrl.playable("ranger") and play.ctrl.playable("squire")
    assert not play.ctrl.playable("hero") and not play.ctrl.playable("paladin")


def test_a_hero_cannot_claim_or_change_during_a_run(tmp_path):
    play = Evolution(tmp_path)
    master(play, "hero_001", "squire")
    play.click("party:begin")
    play.ctrl.open_career("hero_001")
    play.app.frame(0)
    view = play.ctrl.career_view()
    assert view["in_run"] and not any(row["can_claim"] or row["can_activate"] for row in view["rows"])
    assert play.ui.widget("career:guardian:claim").enabled is False
    play.ctrl.claim_vocation("guardian")  # sent anyway: the career rules refuse it
    assert play.ctrl.message == play.ctrl.CHANGE_LOCKED and play.ctrl.message_is_error
    assert play.ui.widget("career:guardian:claim").reason == play.ctrl.CHANGE_LOCKED
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.screen == Screen.BATTLE  # back to where the player was


# --------------------------------------------------------------------------------------------
# Awards, and stop or fight on
# --------------------------------------------------------------------------------------------


def test_winning_a_battle_shows_what_each_hero_earned(tmp_path):
    play = Evolution(tmp_path)
    play.ctrl.begin_run()
    assert play.ctrl.engine is not None
    win_battle(play.ctrl.engine)
    play.ctrl.refresh()
    assert play.ctrl.screen == Screen.UPGRADE
    assert play.ctrl.awards_view() == ["Squire 1 +1, now rank 2.", "Scout 2 +1, now rank 2."]
    assert [row["rank"] for row in play.ctrl.roster_view()] == [2, 2]


def test_after_battle_two_the_player_may_stop_with_a_victory(tmp_path):
    play = Evolution(tmp_path)
    play.to_the_decision()
    keys = play.ui.keys()
    assert "continue:fight" in keys and "continue:stop" in keys and play.app.render_faults == 0
    view = play.ctrl.continue_view()
    assert (view["encounter_id"], view["threat_rating"], view["battle"]) == ("training_04", 4, 2)
    assert view["awards"] == ["Squire 1 +1, now rank 3.", "Scout 2 +1, now rank 3."]
    play.click("continue:stop")
    assert play.ctrl.screen == Screen.OUTCOME and play.ctrl.engine.state.outcome == "victory"
    assert len(play.ctrl.engine.state.battle_records) == 2 and play.link.state.run.phase == "victory"
    assert play.ctrl.log_path is not None and play.ctrl.log_path.exists()


def test_or_fight_on_into_the_third_battle(tmp_path):
    play = Evolution(tmp_path)
    play.to_the_decision()
    play.key(pygame.K_f)
    engine = play.ctrl.engine
    assert engine is not None
    assert play.ctrl.screen == Screen.BATTLE and engine.combat.encounter_id == "training_04" and engine.state.encounter_index == 2
    assert "Battle 3 begins" in play.ctrl.message
    policy = HeuristicPolicy()
    while not engine.finished():
        policy.act(engine) if engine.needs_input() else engine.do(cmd.ADVANCE_PHASE)
    play.ctrl.refresh()
    play.app.frame(0)
    assert play.ctrl.screen == Screen.OUTCOME and play.app.render_faults == 0
    assert play.link.state.run.phase == engine.state.outcome
    third = [a for a in play.link.last_awards if a["battle"] == 3]
    assert len(third) == 2 and all(a["encounter_id"] == "training_04" for a in third)


def test_the_award_line_says_what_was_earned_or_why_nothing_was():
    line = AppController.award_line
    base = {"name": "Brakka", "rank_before": 3, "rank_after": 3, "skills_learned": [], "denial_reason": None}
    assert line({**base, "base_points": 1, "challenge_points": 0}) == "Brakka +1."
    assert line({**base, "base_points": 1, "challenge_points": 1, "rank_after": 4}) == "Brakka +2 with the bonus, now rank 4."
    assert line({**base, "base_points": 1, "challenge_points": 0, "rank_after": 8, "skills_learned": ["Guardian Field Medic"]}) == \
        "Brakka +1, now rank 8, learned Guardian Field Medic."
    assert line({**base, "base_points": 0, "challenge_points": 0, "denial_reason": "UNDER_THREAT_CAP"}) == \
        "Brakka +0 (this battle is too easy for its rank)."
    assert line({**base, "base_points": 0, "challenge_points": 0, "denial_reason": "ENCOUNTER_NOT_WON"}) == "Brakka +0 (the battle was lost)."
    assert line({**base, "base_points": 0, "challenge_points": 0, "denial_reason": "ALREADY_MASTERED"}) == "Brakka +0 (its vocation is mastered)."


# --------------------------------------------------------------------------------------------
# Drawing: every size and font, and a fault leaves a usable screen
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("size", SIZES)
def test_no_text_is_cut_off_on_the_new_screens(tmp_path, monkeypatch, font, size):  # noqa: F811
    play = Evolution(tmp_path, recruits=("squire", "apprentice", "scout", "squire", "scout"), size=size)
    master(play, "hero_001", "squire")
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    assert "Roster (5 of 12 heroes)" in drawn and shortened == [], shortened
    play.ctrl.open_career("hero_001")
    for vocation_id in ("squire", "guardian", "champion", "hero", "ranger"):
        play.ctrl.select_career_vocation(vocation_id)
        play.app.frame(0)
    assert shortened == [], shortened
    play.ctrl.close_career()
    play.to_the_decision()
    play.app.frame(0)
    assert "BATTLE 2 WON" in drawn and shortened == [], shortened
    play.ctrl.end_run_with_victory()
    play.app.frame(0)
    assert play.ctrl.screen == Screen.OUTCOME and play.app.render_faults == 0
    assert "Mastery from the last battle" in drawn and "Squire 1 +0 (its vocation is mastered)." in drawn
    award_lines = play.ctrl.awards_view()
    assert len(award_lines) == 5 and not set(award_lines) & set(shortened)


@pytest.mark.parametrize(("screen", "function"), [(Screen.CAREER, "draw_career"), (Screen.CONTINUE, "draw_continue"),
                                                 (Screen.PARTY_SETUP, "draw_roster_setup")])
def test_a_fault_while_drawing_a_new_screen_reaches_the_error_screen(tmp_path, monkeypatch, screen, function):
    play = Evolution(tmp_path)
    if screen == Screen.CAREER:
        play.ctrl.open_career("hero_001")
    elif screen == Screen.CONTINUE:
        play.to_the_decision()

    def boom(*args, **kwargs):
        raise RuntimeError("simulated drawing fault")

    monkeypatch.setattr(screens, function, boom)
    play.app.frame(0)
    assert play.app.render_faults == 1 and play.ctrl.screen == Screen.ERROR and "simulated drawing fault" in play.ctrl.error_text
    play.click("error:menu")
    assert play.ctrl.screen == Screen.MAIN_MENU


# --------------------------------------------------------------------------------------------
# Settings: the demo's configuration
# --------------------------------------------------------------------------------------------


class Configured(Play):
    """A headless game with a settings file of its own, started from the main menu."""

    def __init__(self, tmp_path, settings=None, size=(1280, 720), **controller):
        self.file = tmp_path / "settings.json"
        self.ctrl = AppController(log_dir=tmp_path / "logs", settings=settings, settings_path=self.file, **controller)
        OPENED.append(self.ctrl)
        self.app = GameApp(self.ctrl, size=size, headless=True, animations=False)
        self.app.fast = True
        self.app.frame(0)

    def saved(self) -> dict:
        import json

        return json.loads(self.file.read_text(encoding="utf-8"))


def test_the_main_menu_opens_the_settings_and_escape_returns(tmp_path):
    play = Configured(tmp_path)
    play.key(pygame.K_s)
    assert play.ctrl.screen == Screen.SETTINGS and play.ctrl.settings_tab == "comfort" and "settings:window_size" in play.ui.keys()
    # Owner decision D-31: four groups, player settings first, the demo's aids last; the seed is not a setting any more.
    assert [(row["group"], row["key"]) for row in play.ctrl.settings_view()] == [
        ("comfort", "window_size"), ("comfort", "animation"), ("aids", "controls"), ("evolution", "class_evolution"),
        ("demo", "mastery_pace"), ("demo", "demo_preset"), ("demo", "roster_limit"), ("demo", "third_battle")]
    assert [group for group, _title in play.ctrl.SETTINGS_GROUPS] == ["comfort", "aids", "evolution", "demo"]
    assert "settings:class_evolution" not in play.ui.keys(), "a group shows its own rows only"
    play.key(pygame.K_3)
    assert play.ctrl.settings_tab == "evolution" and {"settings:class_evolution", "settings:reset"} <= set(play.ui.keys())
    play.click("settings:tab:demo")
    assert play.ctrl.settings_tab == "demo" and "settings:mastery_pace" in play.ui.keys() and "settings:window_size" not in play.ui.keys()
    play.ctrl.select_settings_tab("no such group")
    assert play.ctrl.settings_tab == "demo", "a group that does not exist is not shown"
    assert not play.file.exists(), "looking at the settings writes nothing"
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.screen == Screen.MAIN_MENU


def test_class_evolution_can_be_switched_on_and_off_from_inside_the_game(tmp_path):
    play = Configured(tmp_path)
    assert play.ctrl.progression is None and play.ctrl.vocations is None
    play.key(pygame.K_s)
    needs = "Switch Class Evolution on first."
    play.click("settings:tab:demo")
    assert play.ui.widget("settings:third_battle").reason == needs and play.ui.widget("settings:mastery_pace").enabled is False
    play.click("settings:tab:evolution")
    assert play.ui.widget("settings:reset").enabled is False
    play.click("settings:class_evolution")
    assert play.saved()["class_evolution"] is True and play.ctrl.message == "Class Evolution: On."
    link = play.ctrl.progression
    assert link is not None and link.path == tmp_path / "logs" / "saves" / "profile.sqlite" and link.path.is_file()
    play.click("settings:tab:demo")
    assert play.ctrl.vocations is not None and play.ui.widget("settings:third_battle").enabled is True
    play.key(pygame.K_ESCAPE)
    play.key(pygame.K_n)
    assert "add:squire" in play.ui.keys()
    play.key(pygame.K_1)  # with Class Evolution on, the key recruits a saved Squire
    assert [m["hero_id"] for m in play.ctrl.party] == ["hero_001"]
    # Off again: the shipped game, the old party setup, and nothing of the save is held open.
    play.ctrl.to_main_menu()
    play.ctrl.open_settings()
    play.ctrl.select_settings_tab("evolution")
    play.app.frame(0)
    play.click("settings:class_evolution")
    assert play.saved()["class_evolution"] is False and play.ctrl.progression is None and play.ctrl.vocations is None
    assert play.ctrl.party == [] and play.ctrl.features == frozenset()
    play.ctrl.close_settings()
    play.ctrl.new_run()
    play.app.frame(0)
    play.key(pygame.K_1)  # and with it off the same key adds a plain Squire, as it always did
    assert play.ctrl.party == [{"class_id": "squire", "row": "front"}] and not [k for k in play.ui.keys() if k.startswith("roster:")]
    assert not [k for k in play.ui.keys() if k.endswith(":career")]
    # On once more: the hero recruited before is still in the save.
    play.ctrl.to_main_menu()
    play.ctrl.open_settings()
    play.ctrl.change_setting("class_evolution")
    assert [row["name"] for row in play.ctrl.roster_view()] == ["Squire 1"]


def test_every_setting_moves_to_its_next_value_is_saved_and_takes_effect(tmp_path):
    from battle_dice.settings import Settings

    play = Configured(tmp_path, settings=Settings(class_evolution=True))
    play.ctrl.open_settings()
    play.ctrl.select_settings_tab("demo")
    play.app.frame(0)
    play.click("settings:third_battle")
    assert play.saved()["third_battle"] is False and play.ctrl.third_battle is False
    play.click("settings:mastery_pace")
    assert play.saved()["mastery_pace"] == "fast" and play.ctrl.progression.mastery_pace == "fast"
    assert play.ctrl.progression.catalog.thresholds("squire")[-1] == 7
    play.click("settings:roster_limit")
    assert play.saved()["roster_limit"] == 24 and play.ctrl.progression.career.service.roster_limit == 24
    play.click("settings:demo_preset")
    assert play.saved()["demo_preset"] == "squire_near_mastery" and play.ctrl.roster_view() == [], "a preset is for a new profile"
    assert play.ui.widget("settings:seed") is None, "the seed is chosen on the New Run screen"
    play.click("settings:tab:comfort")
    play.click("settings:animation")
    play.app.frame(0)
    assert play.saved()["animation"] is False and play.app.ui.anim.enabled is False
    play.click("settings:animation")
    play.app.frame(0)
    assert play.app.ui.anim.enabled is True
    play.click("settings:window_size")
    play.app.frame(0)
    assert play.saved()["window_size"] == "1600x900" and play.app.surface.get_size() == (1600, 900)
    # The file a second game reads is the one this one wrote.
    from battle_dice import settings as module

    again, problems = module.load(play.file)
    assert problems == [] and (again.mastery_pace, again.roster_limit, again.window_size) == ("fast", 24, "1600x900")


def test_a_run_uses_the_settings(tmp_path):
    from battle_dice.settings import Settings

    play = Configured(tmp_path, settings=Settings(class_evolution=True, third_battle=False, seed=77, demo_preset="guardian_unlocked"))
    assert [(row["name"], row["vocation_name"]) for row in play.ctrl.roster_view()] == [
        ("Squire 1", "Guardian"), ("Scout 2", "Scout"), ("Apprentice 3", "Apprentice")]
    play.ctrl.new_run()
    play.ctrl.add_saved_hero("hero_001")
    play.ctrl.add_saved_hero("hero_002")
    play.ctrl.begin_run()
    engine = play.ctrl.engine
    assert engine is not None and engine.state.seed == 77 and engine.battle_count == 2  # the fixed seed; no third battle
    assert engine.build("h01").vocation_id == "guardian" and engine.combat.combatants["h01"].max_hp == 18


def test_the_save_folder_comes_from_a_flag_then_the_settings_then_the_usual_place(tmp_path):
    from battle_dice.settings import Settings

    chosen = Configured(tmp_path / "a", settings=Settings(class_evolution=True, save_dir=str(tmp_path / "my saves")))
    assert chosen.ctrl.progression.path == tmp_path / "my saves" / "profile.sqlite" and chosen.ctrl.progression.path.is_file()
    flagged = Configured(tmp_path / "b", settings=Settings(class_evolution=True, save_dir=str(tmp_path / "ignored")), save_dir=tmp_path / "flag")
    assert flagged.ctrl.progression.path == tmp_path / "flag" / "profile.sqlite" and not (tmp_path / "ignored").exists()
    usual = Configured(tmp_path / "c", settings=Settings(class_evolution=True))
    assert usual.ctrl.progression.path == tmp_path / "c" / "logs" / "saves" / "profile.sqlite"


def test_a_launch_flag_wins_over_the_settings_file_and_cannot_be_switched_off_inside(tmp_path):
    from battle_dice.settings import Settings

    play = Configured(tmp_path, settings=Settings(class_evolution=False, seed=5), features=[CLASS_EVOLUTION], fixed_seed=9)
    assert play.ctrl.progression is not None and play.ctrl.fixed_seed == 9
    rows = {row["key"]: row for row in play.ctrl.settings_view()}
    assert rows["class_evolution"]["value"] == "On (launch flag)" and "launch flag" in rows["class_evolution"]["reason"]
    play.ctrl.open_settings()
    play.ctrl.select_settings_tab("evolution")
    play.app.frame(0)
    assert play.ui.widget("settings:class_evolution").enabled is False
    play.ctrl.change_setting("class_evolution")  # sent anyway: refused with the reason
    assert play.ctrl.message == "Switched on by a launch flag for this session." and play.ctrl.progression is not None
    play.ctrl.close_settings()
    play.ctrl.new_run()
    play.app.frame(0)
    seed = play.ui.widget("party:seed")
    assert seed.enabled is False and seed.reason == "Set by a launch flag for this session." and play.ctrl.seed_view()["label"] == "Dice seed: 9"
    play.ctrl.toggle_seed()
    assert play.ctrl.seed_entry is None and play.ctrl.fixed_seed == 9 and play.ctrl.message_is_error


def test_resetting_the_profile_asks_twice_and_starts_again_from_the_chosen_start(tmp_path):
    from battle_dice.settings import Settings

    play = Configured(tmp_path, settings=Settings(class_evolution=True))
    play.ctrl.recruit("scout")
    play.ctrl.recruit("scout")
    assert len(play.ctrl.roster_view()) == 2
    play.ctrl.open_settings()
    play.ctrl.select_settings_tab("evolution")
    play.app.frame(0)
    play.click("settings:reset")
    assert play.ctrl.reset_confirm and len(play.ctrl.roster_view()) == 2 and "Press Reset again" in play.ctrl.message
    play.click("settings:tab:demo")  # anything else cancels the question
    play.click("settings:demo_preset")
    assert not play.ctrl.reset_confirm and len(play.ctrl.roster_view()) == 2
    play.click("settings:tab:evolution")
    play.click("settings:reset")
    play.click("settings:reset")
    assert not play.ctrl.reset_confirm and play.ctrl.message == "A new profile was made (3 heroes)."
    assert [(row["name"], row["rank"]) for row in play.ctrl.roster_view()] == [("Squire 1", 7), ("Scout 2", 1), ("Apprentice 3", 1)]
    assert play.ctrl.party == [] and play.ctrl.progression.path.is_file()


def test_with_class_evolution_off_there_is_no_profile_to_reset(tmp_path):
    play = Configured(tmp_path)
    play.ctrl.reset_profile()
    assert play.ctrl.message_is_error and "no profile to reset" in play.ctrl.message and not list(tmp_path.rglob("*.sqlite"))


def test_problems_in_the_settings_file_are_shown_on_the_main_menu(tmp_path, monkeypatch):
    from battle_dice import settings as module

    file = tmp_path / "settings.json"
    file.write_text('{"window_size": "640x480", "mastery_pace": "fast"}', encoding="utf-8")
    loaded, problems = module.load(file)
    ctrl = AppController(log_dir=tmp_path / "logs", settings=loaded, settings_path=file)
    OPENED.append(ctrl)
    ctrl.settings_problems = problems
    app = GameApp(ctrl, headless=True, animations=False)
    drawn, shortened = record_text(monkeypatch)
    app.frame(0)
    assert problems == ["settings.json: window_size must be one of 960x540, 1280x720, 1600x900, 1920x1080; the default is used."]
    assert problems[0] in drawn and problems[0] not in shortened and loaded.mastery_pace == "fast"


@pytest.mark.parametrize("size", SIZES)
def test_no_text_is_cut_off_on_the_settings_screen_and_the_main_menu(tmp_path, monkeypatch, font, size):  # noqa: F811
    from battle_dice.settings import Settings

    play = Configured(tmp_path, settings=Settings(class_evolution=True), size=size)
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    assert "Settings  (S)" in drawn and shortened == [], shortened
    play.ctrl.open_settings()
    for group, keys in (("demo", ("mastery_pace", "mastery_pace", "demo_preset", "demo_preset", "demo_preset", "third_battle", "roster_limit")),
                        ("comfort", ("animation", "animation")), ("aids", ()), ("evolution", ())):
        play.ctrl.select_settings_tab(group)
        play.app.frame(0)
        for key in keys:
            play.ctrl.change_setting(key)
            play.app.frame(0)
    play.ctrl.reset_profile()
    play.app.frame(0)
    play.ctrl.reset_settings()
    play.app.frame(0)
    # Paths are as long as the machine makes them; everything the game itself words must fit.
    worded = [text for text in shortened if not text.startswith(("Saved in ", "Save file: "))]
    assert "Press again to delete every hero" in drawn and "Press again: all settings to defaults" in drawn and worded == [], worded
    assert all(f"{n}. {title}" in drawn for n, (_group, title) in enumerate(play.ctrl.SETTINGS_GROUPS, start=1))
    # The New Run screen with its seed control, at rest and while a seed of full length is typed.
    play.ctrl.close_settings()
    play.ctrl.new_run()
    play.app.frame(0)
    play.ctrl.toggle_seed()
    for digit in "18446744073709551615":
        play.ctrl.seed_key(digit)
    play.app.frame(0)
    play.ctrl.confirm_seed()
    play.app.frame(0)
    worded = [text for text in shortened if not text.startswith(("Saved in ", "Save file: "))]
    assert "Dice seed: random" in drawn and "Seed: 18446744073709551615_" in drawn and "Dice seed: 18446744073709551615" in drawn
    assert worded == [], worded
    assert play.app.render_faults == 0


def test_a_fault_while_drawing_the_settings_reaches_the_error_screen(tmp_path, monkeypatch):
    play = Configured(tmp_path)
    play.ctrl.open_settings()

    def boom(*args, **kwargs):
        raise RuntimeError("simulated drawing fault")

    monkeypatch.setattr(screens, "draw_settings", boom)
    play.app.frame(0)
    assert play.app.render_faults == 1 and play.ctrl.screen == Screen.ERROR


# --------------------------------------------------------------------------------------------
# Skills: the build panel of the career screen, and Field Medic in a battle (Phase 4, step E)
# --------------------------------------------------------------------------------------------


def medic_game(tmp_path, size=(1280, 720), preset="guardian_mastered") -> Configured:
    """A game whose new profile starts with a mastered Guardian (Field Medic equipped), a Scout and an Apprentice."""
    from battle_dice.settings import Settings

    play = Configured(tmp_path, settings=Settings(class_evolution=True, demo_preset=preset), size=size, fixed_seed=11)
    play.ctrl.new_run()
    play.app.frame(0)
    return play


def in_a_battle_with_a_downed_scout(play: Configured, mana: int = 2):
    """The Guardian and the Scout fight; the Scout is down and the Guardian has rolled its Heal."""
    for hero_id in ("hero_001", "hero_002"):
        play.ctrl.add_saved_hero(hero_id)
    play.ctrl.begin_run()
    engine = play.ctrl.engine
    assert engine is not None
    down(engine, "h02")
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=5)
    unit(engine, "h01").mana = mana
    play.ctrl.refresh()
    play.app.frame(0)
    return engine


def heal_die(play: Configured) -> dict:
    view = play.ctrl._turn_view()
    assert view is not None
    return next(d for d in view["dice"] if d["die_id"] == "guardian_d6")


def test_k_shows_the_heros_skills_and_what_each_one_is(tmp_path, monkeypatch):
    play = medic_game(tmp_path)
    play.ctrl.open_career("hero_001")
    play.app.frame(0)
    drawn, shortened = record_text(monkeypatch)
    play.key(pygame.K_k)
    assert play.ctrl.career_tab == "skills" and play.ctrl.screen == Screen.CAREER
    view = play.ctrl.skills_view()
    assert (view["used"], view["capacity"], view["vocation_name"], view["in_run"]) == (0, 4, "Guardian", False)
    rows = {row["skill_id"]: row for row in view["rows"]}
    medic, anchor = rows["guardian_field_medic"], rows["squire_anchor"]
    assert (medic["equipped"], medic["cost"], medic["taught_by"], medic["in_battle"], medic["can_unequip"]) == (True, 0, "Guardian", True, True)
    assert (anchor["equipped"], anchor["cost"], anchor["in_battle"], anchor["can_equip"]) == (False, 1, False, False)
    assert anchor["reason"] == "Not in this version yet: the rules of battle do not know this skill."
    assert "Capacity used: 0 of 4 as a Guardian" in drawn and anchor["reason"] in drawn and "EQUIPPED" in drawn
    assert play.ui.widget("skill:squire_anchor:equip").enabled is False
    assert play.ui.widget("skill:squire_anchor:equip").reason == anchor["reason"]
    assert shortened == [] and play.app.render_faults == 0
    play.key(pygame.K_k)
    assert play.ctrl.career_tab == "vocation" and play.ui.widget("skill:squire_anchor:equip") is None
    play.key(pygame.K_k)
    play.click("career:scout:select")
    assert play.ctrl.career_tab == "vocation", "choosing a vocation shows that vocation"
    play.key(pygame.K_k)
    assert play.ctrl.career_tab == "skills"
    play.ctrl.close_career()
    play.ctrl.open_career("hero_002")
    assert play.ctrl.career_tab == "vocation", "a career opens on the vocations, whatever was shown last"
    play.ctrl.toggle_career_skills()
    play.app.frame(0)
    assert play.ctrl.skills_view()["rows"] == [] and any(text.startswith("This hero has learned no skill yet.") for text in drawn)
    assert play.app.render_faults == 0


def test_a_skill_is_taken_off_and_equipped_again_and_the_save_keeps_it(tmp_path):
    play = medic_game(tmp_path)
    hero = play.ctrl.progression.state.heroes["hero_001"]
    assert hero.equipped_skills == {0: "guardian_field_medic"}
    play.ctrl.open_career("hero_001")
    play.app.frame(0)
    play.key(pygame.K_k)
    play.click("skill:guardian_field_medic:unequip")
    assert hero.equipped_skills == {} and play.ctrl.message == "Squire 1 has taken off Guardian Field Medic."
    assert play.ui.widget("skill:guardian_field_medic:unequip") is None
    play.click("skill:guardian_field_medic:equip")
    assert hero.equipped_skills == {0: "guardian_field_medic"} and play.ctrl.message == "Squire 1 has equipped Guardian Field Medic."
    play.click("career:back")
    play.ctrl.add_saved_hero("hero_001")
    assert play.ctrl.progression.party_entry("hero_001", "front")["hero"]["skills"] == ["guardian_field_medic"]
    events = [row[0] for row in play.ctrl.progression.store.conn.execute(
        "SELECT event_type FROM progression_event_log WHERE event_type IN ('SkillEquipped', 'SkillUnequipped') ORDER BY event_seq")]
    assert events == ["SkillEquipped", "SkillUnequipped", "SkillEquipped"]  # the preset's, then the two clicks


def test_a_heros_skills_cannot_change_during_a_run(tmp_path):
    play = medic_game(tmp_path)
    for hero_id in ("hero_001", "hero_002"):
        play.ctrl.add_saved_hero(hero_id)
    play.ctrl.begin_run()
    play.ctrl.open_career("hero_001")
    play.ctrl.toggle_career_skills()
    play.app.frame(0)
    button = play.ui.widget("skill:guardian_field_medic:unequip")
    assert button.enabled is False and button.reason == "A hero's skills cannot change during a run."
    play.ctrl.unequip_skill("guardian_field_medic")  # sent anyway: the career rules refuse it
    assert play.ctrl.message == "A hero's skills cannot change during a run." and play.ctrl.message_is_error
    assert play.ctrl.progression.state.heroes["hero_001"].equipped_skills == {0: "guardian_field_medic"}


def test_a_refused_skill_command_says_why(tmp_path, monkeypatch):
    play = medic_game(tmp_path)
    link = play.ctrl.progression
    play.ctrl.open_career("hero_001")
    assert link.change("hero_001", "squire").accepted  # a Squire has capacity 2; Field Medic needs 3 away from the Guardian
    assert link.state.heroes["hero_001"].equipped_skills == {}
    medic = next(row for row in play.ctrl.skills_view()["rows"] if row["skill_id"] == "guardian_field_medic")
    assert (medic["cost"], medic["can_equip"], medic["reason"]) == (3, False, "Needs 3 capacity; 2 of 2 is free.")
    play.ctrl.equip_skill("guardian_field_medic")
    assert play.ctrl.message == "Squire 1 has too little capacity for Guardian Field Medic." and play.ctrl.message_is_error
    assert link.change("hero_001", "guardian").accepted
    monkeypatch.setattr(type(link.career.service), "skill_has_a_face", lambda *args, **kwargs: False)
    medic = next(row for row in play.ctrl.skills_view()["rows"] if row["skill_id"] == "guardian_field_medic")
    assert medic["reason"] == "None of this hero's dice has a face the skill can work on." and not medic["can_equip"]
    play.ctrl.equip_skill("guardian_field_medic")
    assert play.ctrl.message == "None of Squire 1's dice has a face Guardian Field Medic can work on."


def test_field_medic_is_offered_on_the_die_and_revives_the_downed_ally(tmp_path, monkeypatch):
    play = medic_game(tmp_path)
    drawn, shortened = record_text(monkeypatch)
    engine = in_a_battle_with_a_downed_scout(play)
    assert engine.build("h01").skills == ("guardian_field_medic",)
    die = heal_die(play)
    assert (die["skill_note"], die["skill_target_ids"], die["eligible_target_ids"]) == ("Field Medic: revive at 5 HP", ["h02"], ["h01", "h02"])
    assert "Field Medic: revive at 5 HP" in drawn and "Field Medic: revive at 5 HP" not in shortened
    play.click("die:guardian_d6:use")
    assert play.ctrl.message == "Choose a target for Heal (Esc cancels). Field Medic: revive at 5 HP (once per battle)."
    play.click("unit:h02")
    assert play.ctrl.draft == [{"die_id": "guardian_d6", "target_ids": ["h02"]}] and not play.ctrl.message_is_error
    assert any(text.startswith("1. Heal (Field Medic) -> Scout 2") and "1 mana" in text for text in drawn), "the plan names the revival and its cost"
    play.ctrl.confirm_plan()
    for _ in range(40):
        if unit(engine, "h02").state == "standing":
            break
        play.ctrl.refresh()
        play.app.frame(0)
        if engine.needs_input():
            break
        assert engine.do(cmd.ADVANCE_PHASE).accepted
    scout, guardian = unit(engine, "h02"), unit(engine, "h01")
    assert (scout.state, scout.hp, guardian.mana) == ("standing", 5, 1) and guardian.skill_uses == {"guardian_field_medic": 1}
    assert play.app.render_faults == 0 and not [text for text in shortened if "Field Medic" in text]


def test_too_little_mana_for_the_revival_is_said_in_the_plan(tmp_path):
    play = medic_game(tmp_path)
    in_a_battle_with_a_downed_scout(play, mana=0)
    play.click("die:guardian_d6:use")
    play.click("unit:h02")
    assert play.ctrl.message == "Heal (Field Medic) needs 1 mana but only 0 will be available." and play.ctrl.message_is_error
    assert play.ui.widget("plan:confirm").enabled is False


def test_without_the_skill_the_downed_ally_is_not_a_target(tmp_path):
    play = medic_game(tmp_path)
    assert play.ctrl.progression.unequip_skill("hero_001", "guardian_field_medic").accepted
    in_a_battle_with_a_downed_scout(play)
    die = heal_die(play)
    assert die["skill_note"] is None and die["eligible_target_ids"] == ["h01"]
    play.click("die:guardian_d6:use")
    play.click("unit:h02")
    assert play.ctrl.draft == [] and play.ctrl.message_is_error


def test_an_evolved_hero_is_drawn_with_the_picture_of_the_class_it_grew_from(tmp_path, monkeypatch):
    play = medic_game(tmp_path)
    assert play.ctrl.sprite_class("guardian") == "squire" and play.ctrl.sprite_class("scout") == "scout"
    assert play.ctrl.sprite_class("goblin_skirmisher") == "goblin_skirmisher", "an enemy is its own picture"
    asked: list[str] = []
    original = type(play.ui.assets).combatant_key

    def recorded(self, archetype):
        asked.append(archetype)
        return original(self, archetype)

    monkeypatch.setattr(type(play.ui.assets), "combatant_key", recorded)
    in_a_battle_with_a_downed_scout(play)
    assert "guardian" not in asked and "squire" in asked, "the battle screen never asks for a picture that does not exist"


@pytest.mark.parametrize("size", SIZES)
def test_no_text_is_cut_off_on_the_skills_panel_or_with_field_medic_in_battle(tmp_path, monkeypatch, font, size):  # noqa: F811
    play = medic_game(tmp_path, size=size)
    drawn, shortened = record_text(monkeypatch)
    play.ctrl.open_career("hero_001")
    play.app.frame(0)
    play.ctrl.toggle_career_skills()
    play.app.frame(0)
    play.ctrl.unequip_skill("guardian_field_medic")
    play.app.frame(0)
    play.ctrl.equip_skill("guardian_field_medic")
    play.ctrl.close_career()
    play.ctrl.open_career("hero_003")
    play.ctrl.toggle_career_skills()
    play.app.frame(0)
    play.ctrl.close_career()
    assert "Skills  (K)" in drawn and "Vocation  (K)" in drawn and shortened == [], shortened
    in_a_battle_with_a_downed_scout(play)
    play.click("die:guardian_d6:use")
    play.click("unit:h02")
    # The battle screen shortens some long names under the widest font, as it always did; what Field Medic adds must fit.
    added = [text for text in drawn if "Field Medic" in text]
    assert "Field Medic: revive at 5 HP" in added and any(text.startswith("1. Heal (Field Medic)") for text in added)
    assert not [text for text in shortened if "Field Medic" in text], shortened
    assert play.app.render_faults == 0


def test_a_guardian_chooses_its_upgrade_and_the_screen_names_its_die(tmp_path, monkeypatch):
    """The upgrade screen and the combat log name an evolved hero's dice, which are not in the shipped content."""
    from battle_dice.core.view import combat_log

    play = medic_game(tmp_path)
    for hero_id in ("hero_002", "hero_001"):  # the Scout leads, so the arranged win is the Scout's
        play.ctrl.add_saved_hero(hero_id)
    play.ctrl.begin_run()
    engine = play.ctrl.engine
    assert engine is not None and engine.build("h02").vocation_id == "guardian"
    win_battle(engine)
    play.ctrl.refresh()
    play.app.frame(0)
    assert play.ctrl.screen == Screen.UPGRADE
    drawn, _ = record_text(monkeypatch)
    play.click("up:hero:h02")
    play.click("up:die:guardian_d6")
    play.click("up:offer:0")
    play.ctrl.apply_upgrade()
    play.app.frame(0)
    assert engine.state.phase == "equipment" and "guardian_d6" in engine.state.die_overrides["h02"]
    assert play.ctrl.screen == Screen.UPGRADE and play.app.render_faults == 0, play.ctrl.error_text
    assert any("was applied to Squire 1's Guardian d6" in text for text in drawn)
    assert play.ctrl.die_name("h02", "guardian_d4") == "Guardian d4" and play.ctrl.die_name("h01", "striker_d8") == "Striker d8"
    assert any("Guardian d6" in line for line in combat_log(engine)) and not any("guardian_d6" in line for line in combat_log(engine))


# --------------------------------------------------------------------------------------------
# A vocation change inside a run (acceptance case CE-19)
# --------------------------------------------------------------------------------------------


def after_battle_one_with_a_squire_who_may_be_a_guardian(tmp_path, size=(1280, 720)) -> Configured:
    """hero_001 has the Guardian unlocked and fights as a Squire; with the Scout it has won Battle 1."""
    play = medic_game(tmp_path, size=size, preset="guardian_unlocked")
    assert play.ctrl.progression.change("hero_001", "squire").accepted
    for hero_id in ("hero_001", "hero_002"):
        play.ctrl.add_saved_hero(hero_id)
    play.ctrl.begin_run()
    engine = play.ctrl.engine
    assert engine is not None and engine.build("h01").vocation_id == "squire"
    win_battle(engine)
    play.ctrl.refresh()
    play.app.frame(0)
    assert play.ctrl.screen == Screen.UPGRADE
    return play


def test_before_the_upgrade_a_hero_becomes_a_guardian_from_the_upgrade_screen(tmp_path, monkeypatch):
    play = after_battle_one_with_a_squire_who_may_be_a_guardian(tmp_path)
    engine = play.ctrl.engine
    drawn, shortened = record_text(monkeypatch)
    assert play.ctrl.change_window_open() and play.ctrl.saved_hero_of("h01") == "hero_001" and play.ctrl.saved_hero_of("h09") is None
    assert play.ctrl.saved_hero_of("h02") == "hero_002"
    play.app.frame(0)
    assert "Career  (C)" in drawn and "change vocation before the upgrade" in drawn
    play.click("up:hero:h02")  # the button is for the hero that is selected
    play.key(pygame.K_c)
    assert play.ctrl.screen == Screen.CAREER and play.ctrl.career_hero == "hero_002"
    play.key(pygame.K_ESCAPE)
    play.click("up:hero:h01")
    play.click("up:offer:0")  # a card for the Squire's die is selected; it will not exist after the change
    assert play.ctrl.upgrade_offer is not None and play.ctrl.upgrade_die == "iron_d6"
    play.key(pygame.K_c)
    assert play.ctrl.screen == Screen.CAREER and play.ctrl.career_hero == "hero_001"
    view = play.ctrl.career_view()
    assert (view["in_run"], view["open_now"], view["fighting"], view["locked"]) == (True, True, True, "")
    assert any(text.startswith("Before the upgrade is chosen this hero may take another vocation.") for text in drawn)
    button = play.ui.widget("career:guardian:activate")
    assert button.enabled is True and button.tooltip == "The hero fights on as this vocation at once."
    hp = engine.combat.combatants["h01"].hp
    play.click("career:guardian:activate")
    fighter = engine.combat.combatants["h01"]
    assert (fighter.archetype_id, fighter.max_hp, fighter.equipped_dice_ids) == ("guardian", 18, ["guardian_d6", "guardian_d4"])
    assert fighter.hp == -((-hp * 18) // 15), "health is carried over in proportion, rounded up"
    assert play.ctrl.progression.state.heroes["hero_001"].active_vocation_id == "guardian"
    assert play.ctrl.message.startswith("Squire 1 is now a Guardian and fights on as one.") and not play.ctrl.message_is_error
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.screen == Screen.UPGRADE and (play.ctrl.upgrade_hero, play.ctrl.upgrade_die, play.ctrl.upgrade_offer) == ("h01", "guardian_d6", None)
    assert play.ui.widget("up:die:guardian_d6") is not None and play.ui.widget("up:die:iron_d6") is None
    assert [offer["die_id"] for offer in play.ctrl.current_offers()] == ["guardian_d6"] * 3
    play.click("up:offer:0")
    play.ctrl.apply_upgrade()
    play.app.frame(0)
    assert engine.state.phase == "equipment" and "guardian_d6" in engine.state.die_overrides["h01"]
    assert play.app.render_faults == 0 and not play.ctrl.change_window_open()
    # Once the upgrade is chosen the career can be looked at, and nothing can be changed.
    assert "the upgrade is chosen: look only" in drawn
    play.click("up:career")
    again = play.ui.widget("career:squire:activate")
    assert again.enabled is False and again.reason == play.ctrl.CHANGE_LOCKED and play.ctrl.CHANGE_LOCKED in drawn
    play.ctrl.change_vocation("squire")  # sent anyway: the career rules refuse it
    assert play.ctrl.message == play.ctrl.CHANGE_LOCKED and play.ctrl.message_is_error
    assert engine.build("h01").vocation_id == "guardian" and shortened == [], shortened
    play.key(pygame.K_ESCAPE)
    play.key(pygame.K_RETURN)  # Start Battle 2
    assert engine.state.encounter_index == 1 and play.ctrl.screen == Screen.BATTLE and play.app.render_faults == 0
    assert engine.combat.combatants["h01"].archetype_id == "guardian"


def test_a_hero_outside_the_party_may_change_in_that_moment_too(tmp_path):
    play = after_battle_one_with_a_squire_who_may_be_a_guardian(tmp_path)
    engine = play.ctrl.engine
    commands = len(engine.command_log)
    play.ctrl.open_career("hero_003")
    play.app.frame(0)
    view = play.ctrl.career_view()
    assert (view["open_now"], view["fighting"]) == (True, False)
    assert play.ui.widget("career:scout:activate").tooltip == "The hero fights as this vocation from the next run on."
    play.click("career:scout:activate")
    assert play.ctrl.progression.state.heroes["hero_003"].active_vocation_id == "scout" and play.ctrl.message == "Apprentice 3 is now a Scout."
    assert len(engine.command_log) == commands, "the run is not touched"


def test_a_change_the_run_refuses_is_said_and_undone(tmp_path, monkeypatch):
    play = after_battle_one_with_a_squire_who_may_be_a_guardian(tmp_path)
    link = play.ctrl.progression
    monkeypatch.setattr(link, "change_in_run", lambda engine, hero_id, vocation_id: (link.preview(hero_id, vocation_id), "simulated refusal"))
    play.ctrl.open_career("hero_001")
    play.ctrl.change_vocation("guardian")
    assert play.ctrl.message == "The run refused the change: simulated refusal" and play.ctrl.message_is_error


def test_without_class_evolution_the_upgrade_screen_has_no_career_button(tmp_path):
    play = Play(tmp_path, ("squire", "scout"))
    play.ctrl.begin_run()
    engine = play.ctrl.engine
    assert engine is not None
    win_battle(engine)
    play.ctrl.refresh()
    play.app.frame(0)
    assert play.ctrl.screen == Screen.UPGRADE and play.ui.widget("up:career") is None
    assert play.ctrl.saved_hero_of("h01") is None and cmd.CHANGE_VOCATION not in engine.permissible_commands()


@pytest.mark.parametrize("size", SIZES)
def test_no_text_is_cut_off_around_a_change_inside_a_run(tmp_path, monkeypatch, font, size):  # noqa: F811
    play = after_battle_one_with_a_squire_who_may_be_a_guardian(tmp_path, size=size)
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    play.ctrl.open_career("hero_001")
    play.app.frame(0)
    play.ctrl.change_vocation("guardian")
    play.app.frame(0)
    play.ctrl.close_career()
    play.app.frame(0)
    play.ctrl.open_career("hero_003")
    play.app.frame(0)
    play.ctrl.close_career()
    play.ctrl.select_offer(play.ctrl.current_offers()[0]["offer_id"])
    play.ctrl.apply_upgrade()
    play.app.frame(0)
    play.ctrl.open_career("hero_001")
    play.app.frame(0)
    assert "Career  (C)" in drawn and play.ctrl.CHANGE_LOCKED in drawn
    assert shortened == [] and play.app.render_faults == 0, shortened


# --------------------------------------------------------------------------------------------
# The second moment for a change: the decision to stop or fight on (owner decision of 2026-11-12)
# --------------------------------------------------------------------------------------------


def at_the_decision_with_a_squire_who_may_be_a_guardian(tmp_path, size=(1280, 720)) -> Configured:
    play = after_battle_one_with_a_squire_who_may_be_a_guardian(tmp_path, size=size)
    engine = play.ctrl.engine
    assert engine is not None
    play.click("up:offer:0")
    play.ctrl.apply_upgrade()
    play.ctrl.start_next_battle()
    win_battle(engine)
    play.ctrl.refresh()
    play.app.frame(0)
    assert play.ctrl.screen == Screen.CONTINUE and "iron_d6" in engine.state.die_overrides["h01"]
    return play


def test_before_stopping_or_fighting_on_a_hero_becomes_a_guardian(tmp_path, monkeypatch):
    play = at_the_decision_with_a_squire_who_may_be_a_guardian(tmp_path)
    engine = play.ctrl.engine
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    view = play.ctrl.continue_view()
    assert [(h["id"], h["saved_hero_id"], h["vocation_name"]) for h in view["heroes"]] == [("h01", "hero_001", "Squire"), ("h02", "hero_002", "Scout")]
    assert play.ctrl.change_window_open() and play.ui.widget("continue:career:h02") is not None
    play.click("continue:career:h02")
    assert play.ctrl.career_hero == "hero_002"
    play.key(pygame.K_ESCAPE)
    play.key(pygame.K_c)  # the first hero's career
    assert play.ctrl.screen == Screen.CAREER and play.ctrl.career_hero == "hero_001"
    career = play.ctrl.career_view()
    assert (career["open_now"], career["fighting"], career["deciding"]) == (True, True, True)
    assert any(text.startswith("Before you stop or fight on this hero may take another vocation.") for text in drawn)
    hp = engine.combat.combatants["h01"].hp
    play.click("career:guardian:activate")
    fighter = engine.combat.combatants["h01"]
    assert (fighter.archetype_id, fighter.max_hp, fighter.equipped_dice_ids) == ("guardian", 18, ["guardian_d6", "guardian_d4"])
    assert fighter.hp == -((-hp * 18) // 15) and "h01" not in engine.state.die_overrides
    assert play.ctrl.message == "Squire 1 is now a Guardian and fights on as one. Its health and mana were carried over."
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.screen == Screen.CONTINUE and play.ctrl.continue_view()["heroes"][0]["vocation_name"] == "Guardian"
    assert "Guardian" in drawn and play.app.render_faults == 0 and shortened == [], shortened
    # The upgrade of Battle 1 was on a die the hero no longer holds: it is still named, not looked up in vain.
    assert play.ctrl.die_name("h01", "iron_d6") == "Iron d6" and play.ctrl.die_name("h01", "no_such_die") == "No such die"
    play.key(pygame.K_f)
    assert play.ctrl.screen == Screen.BATTLE and engine.state.encounter_index == 2
    assert engine.combat.combatants["h01"].archetype_id == "guardian" and play.app.render_faults == 0
    play.ctrl.open_career("hero_001")
    play.app.frame(0)
    assert play.ui.widget("career:squire:activate").reason == play.ctrl.CHANGE_LOCKED


@pytest.mark.parametrize("size", SIZES)
def test_no_text_is_cut_off_at_the_decision_with_its_career_buttons(tmp_path, monkeypatch, font, size):  # noqa: F811
    play = at_the_decision_with_a_squire_who_may_be_a_guardian(tmp_path, size=size)
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    play.ctrl.open_career("hero_001")
    play.app.frame(0)
    play.ctrl.change_vocation("guardian")
    play.app.frame(0)
    play.ctrl.close_career()
    play.app.frame(0)
    assert "Career" in drawn and "Guardian" in drawn and shortened == [], shortened
    assert play.app.render_faults == 0


# --------------------------------------------------------------------------------------------
# The configuration as the owner decided it (D-31): groups, reset to defaults, Settings from the
# pause menu, and the dice seed on the New Run screen
# --------------------------------------------------------------------------------------------


def test_the_controls_help_opens_from_the_settings_and_comes_back_there(tmp_path):
    play = Configured(tmp_path)
    play.key(pygame.K_s)
    play.key(pygame.K_2)
    assert play.ctrl.settings_tab == "aids"
    play.click("settings:controls")
    assert play.ctrl.screen == Screen.CONTROLS and not play.file.exists(), "opening the help changes no setting"
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.screen == Screen.SETTINGS and play.ctrl.settings_tab == "aids"
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.screen == Screen.MAIN_MENU
    play.key(pygame.K_c)  # from the main menu the help still returns to the main menu
    assert play.ctrl.screen == Screen.CONTROLS
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.screen == Screen.MAIN_MENU


def test_all_settings_return_to_their_defaults_when_asked_twice(tmp_path):
    from battle_dice.settings import Settings

    custom = Settings(class_evolution=True, third_battle=False, animation=False, seed=77, window_size="1600x900", roster_limit=24,
                      mastery_pace="fast", demo_preset="guardian_unlocked", save_dir=str(tmp_path / "my saves"))
    play = Configured(tmp_path, settings=custom)
    assert len(play.ctrl.roster_view()) == 3
    play.ctrl.open_settings()
    play.app.frame(0)
    play.click("settings:defaults")
    assert play.ctrl.defaults_confirm and play.ctrl.message_is_error and play.ctrl.settings.mastery_pace == "fast"
    assert not play.file.exists(), "the question changes nothing"
    play.click("settings:tab:demo")  # anything else cancels the question
    assert not play.ctrl.defaults_confirm
    play.click("settings:defaults")
    play.click("settings:defaults")
    play.app.frame(0)
    now = play.ctrl.settings
    assert now == Settings(save_dir=str(tmp_path / "my saves")), "every setting is the default; the save folder is a place, not a preference"
    assert play.saved()["mastery_pace"] == "normal" and play.saved()["class_evolution"] is False and play.saved()["seed"] is None
    assert play.ctrl.progression is None and play.ctrl.fixed_seed is None and play.ctrl.third_battle is True
    assert play.app.surface.get_size() == (1280, 720) and play.app.ui.anim.enabled is True
    assert play.ctrl.message == "Every setting is back to its default."
    assert (tmp_path / "my saves" / "profile.sqlite").is_file(), "the saved heroes are kept"
    play.click("settings:tab:evolution")
    play.click("settings:class_evolution")
    assert len(play.ctrl.roster_view()) == 3, "and they are there when Class Evolution is switched on again"


def test_the_settings_open_from_the_pause_menu_and_what_would_end_the_run_is_locked(tmp_path):
    from battle_dice.settings import Settings

    play = Configured(tmp_path, settings=Settings(class_evolution=True, demo_preset="guardian_unlocked"), fixed_seed=11)
    play.ctrl.new_run()
    for hero_id in ("hero_001", "hero_002"):
        play.ctrl.add_saved_hero(hero_id)
    play.ctrl.begin_run()
    engine = play.ctrl.engine
    revision = engine.revision
    play.app.frame(0)
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.paused and play.ui.widget("pause:settings") is not None
    play.key(pygame.K_s)
    assert play.ctrl.screen == Screen.SETTINGS and play.ctrl.settings_in_run and not play.ctrl.paused
    # Display and comfort apply at once, inside the run.
    play.click("settings:animation")
    assert play.ctrl.settings.animation is False and play.app.ui.anim.enabled is False and play.ctrl.engine is engine
    # Everything that would close the save, and with it the run, is locked and says why.
    for group, keys in (("evolution", ("class_evolution", "reset")), ("demo", ("mastery_pace", "demo_preset", "roster_limit", "third_battle"))):
        play.click(f"settings:tab:{group}")
        for key in keys:
            widget = play.ui.widget(f"settings:{key}")
            assert widget.enabled is False and widget.reason == play.ctrl.RUN_LOCKED, key
    assert play.ui.widget("settings:defaults").reason == play.ctrl.RUN_LOCKED and play.ui.widget("settings:defaults").enabled is False
    for send in (lambda: play.ctrl.change_setting("class_evolution"), lambda: play.ctrl.change_setting("mastery_pace"),
                 play.ctrl.reset_profile, play.ctrl.reset_settings):
        send()  # sent anyway: each is refused
        assert play.ctrl.message == play.ctrl.RUN_LOCKED and play.ctrl.message_is_error
    assert play.ctrl.engine is engine and play.ctrl.progression is not None and len(play.ctrl.roster_view()) == 3
    assert play.ctrl.settings.class_evolution is True and play.ctrl.settings.mastery_pace == "normal"
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.screen == Screen.BATTLE and play.ctrl.paused and not play.ctrl.settings_in_run, "back in the pause menu"
    play.key(pygame.K_ESCAPE)
    assert not play.ctrl.paused and engine.revision == revision, "nothing advanced while the settings were open"
    assert play.app.render_faults == 0


def test_the_dice_seed_is_typed_on_the_new_run_screen(tmp_path):
    play = Configured(tmp_path)
    play.key(pygame.K_n)
    assert play.ctrl.seed_view() == {"label": "Dice seed: random", "hint": "press D to type a seed", "entering": False, "seed": None, "reason": None}
    play.key(pygame.K_1)  # a Squire joins, as always
    assert len(play.ctrl.party) == 1
    play.key(pygame.K_d)
    assert play.ctrl.seed_entry == "" and play.ctrl.seed_view()["label"] == "Seed: _"
    for key in (pygame.K_1, pygame.K_2, pygame.K_KP3, pygame.K_KP0, pygame.K_b, pygame.K_n):  # letters are not digits
        play.key(key)
    assert play.ctrl.seed_entry == "1230" and len(play.ctrl.party) == 1, "while a seed is typed the number keys add no hero"
    assert play.ctrl.screen == Screen.PARTY_SETUP and play.ctrl.engine is None, "and B does not begin the run"
    play.key(pygame.K_BACKSPACE)
    play.key(pygame.K_RETURN)
    assert play.ctrl.seed_entry is None and play.ctrl.fixed_seed == 123 and play.saved()["seed"] == 123
    assert play.ctrl.message == "Dice seed: 123. Every run uses it until you change it." and play.ctrl.seed_view()["label"] == "Dice seed: 123"
    play.key(pygame.K_2)
    assert len(play.ctrl.party) == 2, "after the entry the keys are the screen's again"
    play.key(pygame.K_b)
    assert play.ctrl.engine is not None and play.ctrl.engine.state.seed == 123
    # A second game reads the seed from the file; D switches back to a random one.
    from battle_dice import settings as module

    assert module.load(play.file)[0].seed == 123
    play.ctrl.to_main_menu()
    play.app.frame(0)
    play.key(pygame.K_n)
    play.key(pygame.K_d)
    assert play.ctrl.fixed_seed is None and play.saved()["seed"] is None and play.ctrl.message == "Dice seed: a new one each run."


def test_a_seed_entry_can_be_cancelled_left_or_finished_by_beginning(tmp_path):
    play = Configured(tmp_path)
    play.key(pygame.K_n)
    play.key(pygame.K_1)
    play.key(pygame.K_d)
    play.key(pygame.K_7)
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.seed_entry is None and play.ctrl.fixed_seed is None and play.ctrl.screen == Screen.PARTY_SETUP, "Esc ends the entry, not the screen"
    play.key(pygame.K_d)
    play.key(pygame.K_RETURN)  # nothing typed: a random seed
    assert play.ctrl.seed_entry is None and play.ctrl.fixed_seed is None
    play.key(pygame.K_d)
    for digit in "99999999999999999999":  # twenty nines: more than a seed can be
        play.ctrl.seed_key(digit)
    play.ctrl.seed_key("5")  # a twenty-first digit is not taken
    assert play.ctrl.seed_entry == "9" * 20
    play.key(pygame.K_RETURN)
    assert play.ctrl.fixed_seed is None and play.ctrl.message_is_error and "from 0 to 18446744073709551615" in play.ctrl.message
    play.key(pygame.K_d)
    play.key(pygame.K_4)
    play.click("party:back")  # leaving the screen ends the entry: the keys of the main menu work
    play.key(pygame.K_s)
    assert play.ctrl.screen == Screen.SETTINGS and play.ctrl.seed_entry is None
    play.key(pygame.K_ESCAPE)
    play.key(pygame.K_n)
    play.key(pygame.K_d)
    play.key(pygame.K_5)
    play.click("party:begin")  # a seed still being typed counts as entered
    assert play.ctrl.engine is not None and play.ctrl.engine.state.seed == 5 and play.ctrl.seed_entry is None
