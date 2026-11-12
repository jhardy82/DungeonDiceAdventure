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
from tests.conftest import win_battle
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
    assert play.ctrl.message == "That cannot be done during a run." and play.ctrl.message_is_error
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
