"""The step-by-step screen driver that playtesters use (tools/playtest_screen.py).

It must show what is on the screen, do what a player does, and replay a session exactly: a finding
is only worth something if its action list reproduces it.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tests.ui.test_evolution_ui import close_every_save  # noqa: F401 - the fixture closes the saves

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def driver():
    spec = importlib.util.spec_from_file_location("playtest_screen", ROOT / "tools" / "playtest_screen.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(driver, capsys, folder, *arguments) -> tuple[int, str]:  # noqa: ANN001
    code = driver.main(["--session", str(folder), *arguments])
    return code, capsys.readouterr().out


def test_a_session_starts_at_the_main_menu_and_lists_what_can_be_clicked(driver, capsys, tmp_path):
    code, out = run(driver, capsys, tmp_path / "s", "start")
    assert code == 0 and "SCREEN: main_menu" in out and "BATTLE DICE" in out
    assert "menu:new" in out and "label: 'New Run  (N)'" in out and "keys: n" in out
    shot = tmp_path / "s" / "shots" / "0000.png"
    assert f"SCREENSHOT: {shot}" in out and shot.stat().st_size > 1000


def test_keys_and_clicks_play_the_game_and_the_screen_is_printed_panel_by_panel(driver, capsys, tmp_path):
    folder = tmp_path / "s"
    run(driver, capsys, folder, "start")
    code, out = run(driver, capsys, folder, "do", "--full", "key:n", "click:add:squire", "click:add:scout", "key:b", "key:r")
    assert code == 0 and "SCREEN: battle" in out and "actions so far: 5" in out
    assert "Combat log" in out and "Phase: Keep, reroll and plan" in out
    assert "plan:confirm" in out and "DISABLED (No action selected. Choose a die, or Pass.)" in out, "a control that is off says why"
    assert "[panel at x=" in out and "unit:h01" in out
    assert json.loads((folder / "session.json").read_text(encoding="utf-8"))["actions"] == ["key:n", "click:add:squire", "click:add:scout", "key:b", "key:r"]


def test_a_session_replays_exactly(driver, capsys, tmp_path):
    folder = tmp_path / "s"
    run(driver, capsys, folder, "start", "--seed", "500")
    run(driver, capsys, folder, "do", "key:n", "click:add:squire", "click:add:scout", "key:b", "key:r")
    first, second = run(driver, capsys, folder, "look")[1], run(driver, capsys, folder, "look")[1]
    assert first == second and "rolls" in first
    shot = folder / "shots" / "0005.png"
    picture = shot.read_bytes()
    run(driver, capsys, folder, "look")
    assert shot.read_bytes() == picture
    # Another seed gives another battle; the same seed in another session gives the same one.
    other, same = tmp_path / "other", tmp_path / "same"
    for place, seed in ((other, "501"), (same, "500")):
        run(driver, capsys, place, "start", "--seed", seed)
        run(driver, capsys, place, "do", "key:n", "click:add:squire", "click:add:scout", "key:b", "key:r")
    log = lambda text: [line for line in text.splitlines() if " rolls " in line]  # noqa: E731
    assert log(run(driver, capsys, same, "look")[1]) == log(first) != log(run(driver, capsys, other, "look")[1])


def test_an_action_that_cannot_be_done_is_refused_and_the_session_is_unchanged(driver, capsys, tmp_path):
    folder = tmp_path / "s"
    run(driver, capsys, folder, "start")
    code, out = run(driver, capsys, folder, "do", "key:n", "click:no:such:control")
    assert code == 2 and "NOT DONE, the session is unchanged." in out and "no control 'no:such:control' on this screen" in out
    assert "SCREEN: main_menu" in out and json.loads((folder / "session.json").read_text(encoding="utf-8"))["actions"] == []
    for action, said in (("key:f13", "unknown key"), ("wait:soon", "wait needs milliseconds"), ("clickxy:here", "clickxy needs X,Y"), ("dance", "unknown action")):
        code, out = run(driver, capsys, folder, "do", action)
        assert code == 2 and said in out, action


def test_after_an_action_only_what_changed_is_printed_and_nothing_changed_is_said_plainly(driver, capsys, tmp_path):
    folder = tmp_path / "s"
    run(driver, capsys, folder, "start")
    code, out = run(driver, capsys, folder, "do", "key:s")
    assert code == 0 and "SCREEN: settings" in out and "WHAT CHANGED ON THE SCREEN" in out
    assert "-       BATTLE DICE" in out and any(line.startswith("+ ") and "Text size" in line for line in out.splitlines())
    code, out = run(driver, capsys, folder, "do", "key:9")  # a key the Settings screen does not use
    assert code == 0 and "NOTHING CHANGED ON THE SCREEN." in out and "SCREENSHOT:" in out
    code, out = run(driver, capsys, folder, "look")
    assert "WHAT CHANGED" not in out and "Display and comfort" in out, "look prints the whole screen"


def test_undo_takes_actions_back_and_log_lists_them(driver, capsys, tmp_path):
    folder = tmp_path / "s"
    run(driver, capsys, folder, "start")
    run(driver, capsys, folder, "do", "key:s", "key:2", "key:escape", "key:c")
    assert run(driver, capsys, folder, "log")[1].split() == ["1", "key:s", "2", "key:2", "3", "key:escape", "4", "key:c"]
    code, out = run(driver, capsys, folder, "undo", "3")
    assert code == 0 and "SCREEN: settings" in out and "actions so far: 1" in out


def test_a_click_on_a_control_that_is_off_shows_the_games_reason_and_hover_shows_help(driver, capsys, tmp_path):
    folder = tmp_path / "s"
    run(driver, capsys, folder, "start")
    code, out = run(driver, capsys, folder, "do", "--full", "key:n", "click:party:begin")
    assert code == 0 and "SCREEN: party_setup" in out, "the click is sent as a player's click; the game answers"
    begin = next(line for line in out.splitlines() if line.strip().startswith("party:begin"))
    assert "DISABLED (" in begin
    reason = begin.split("DISABLED (", 1)[1].split(")", 1)[0]
    assert reason in out.split("CONTROLS", 1)[0], "the reason is on the screen, in the status bar"
    code, out = run(driver, capsys, folder, "do", "--full", "hover:add:squire")
    assert code == 0 and "[pointer]" in next(line for line in out.splitlines() if line.strip().startswith("add:squire"))


def test_the_help_text_delay_can_be_seen_with_hover_and_wait(driver, capsys, tmp_path):
    folder = tmp_path / "s"
    run(driver, capsys, folder, "start")
    run(driver, capsys, folder, "do", "key:s", "key:2", "click:settings:tooltip_delay")  # None -> Short (350 ms)
    code, out = run(driver, capsys, folder, "do", "--full", "hover:settings:confirm_pass")
    assert code == 0 and "Help text delay: Short." in out and "Click to change it" not in out, "the help waits for the delay"
    code, out = run(driver, capsys, folder, "do", "--full", "wait:400")
    assert "Click to change it, or press Enter while it has the focus ring." in out


def test_a_feature_flag_and_a_window_size_are_part_of_the_session(driver, capsys, tmp_path):
    folder = tmp_path / "s"
    code, out = run(driver, capsys, folder, "start", "--size", "960x540", "--feature", "class_evolution_v1")
    assert code == 0 and "window 960x540" in out
    code, out = run(driver, capsys, folder, "do", "--full", "key:n")
    assert "Roster (0 of 12 heroes)" in out and (folder / "state" / "logs" / "saves").is_dir(), "the save lives inside the session"


def test_without_a_session_the_driver_says_how_to_begin(driver, tmp_path):
    with pytest.raises(SystemExit, match="Begin one with"):
        driver.main(["--session", str(tmp_path / "none"), "look"])
