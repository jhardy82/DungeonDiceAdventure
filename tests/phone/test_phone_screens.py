"""The phone app's screens as data (walking skeleton, owner decision D-33).

The tests play through ``screen`` and ``act`` alone: what a toolkit will draw, and the taps it will send.
"""

from __future__ import annotations

import re
import subprocess
import sys

import pytest

from battle_dice.app import selfcheck
from battle_dice.app.controller import AppController, Screen
from battle_dice.phone import screens as phone


def controller(tmp_path, seed: int = 11) -> AppController:
    return AppController(fixed_seed=seed, log_dir=tmp_path / "logs")


def ids(view: dict) -> list[str]:
    return [action["id"] for action in phone._all_actions(view)]


def tap_through_a_battle(ctrl: AppController, limit: int = 3000) -> list[str]:
    """Play as someone who taps what is offered: a target, else a die, else the main button, else Pass."""
    taps: list[str] = []
    for _ in range(limit):
        view = phone.screen(ctrl)
        if view["screen"] != "battle":
            return taps
        offered = [action for action in phone._all_actions(view) if action["enabled"]]
        target = next((a for a in offered if a["id"].startswith("target:")), None)
        use = next((a for a in offered if a["id"].startswith("use:") and a["label"] == "Use"), None)
        main = next((a for a in view["actions"] if a["primary"] and a["enabled"]), None)
        choice = target or (use if not ctrl.draft else None) or main or next(a for a in offered if a["id"] == "pass")
        taps.append(choice["id"])
        phone.act(ctrl, choice["id"])
    raise AssertionError("the battle did not end")


def test_the_menu_leads_to_the_party_and_the_party_to_a_battle(tmp_path):
    ctrl = controller(tmp_path)
    menu = phone.screen(ctrl)
    assert (menu["screen"], ids(menu)) == ("menu", ["menu:new"]) and menu["actions"][0]["primary"]
    phone.act(ctrl, "menu:new")
    party = phone.screen(ctrl)
    assert party["screen"] == "party" and party["title"] == "Party: 0 of 5 heroes"
    begin = next(a for a in party["actions"] if a["id"] == "party:begin")
    assert not begin["enabled"] and begin["reason"], "a button that is off says why"
    phone.act(ctrl, "party:begin")
    assert ctrl.screen == Screen.PARTY_SETUP and ctrl.message == begin["reason"] and ctrl.message_is_error
    for class_id in ("squire", "scout"):
        phone.act(ctrl, f"party:add:{class_id}")
    party = phone.screen(ctrl)
    assert [card["title"] for card in party["groups"][0]["cards"]] == ["1. Squire", "2. Scout"]
    phone.act(ctrl, "party:remove:0")
    assert [member["class_id"] for member in ctrl.party] == ["scout"]
    phone.act(ctrl, "party:add:squire")
    phone.act(ctrl, "party:begin")
    battle = phone.screen(ctrl)
    assert battle["screen"] == "battle" and battle["title"] == "Battle 1 of 2"
    assert [group["title"] for group in battle["groups"][:2]] == ["Enemies", "Heroes"]
    assert ctrl.waiting_for_player(), "after a tap the game has run on until it needs the player"


def test_a_whole_battle_can_be_played_by_taps_alone(tmp_path):
    ctrl = controller(tmp_path)
    phone.act(ctrl, "menu:new")
    for class_id in ("squire", "apprentice", "scout"):
        phone.act(ctrl, f"party:add:{class_id}")
    phone.act(ctrl, "party:begin")
    taps = tap_through_a_battle(ctrl)
    kinds = {tap.split(":")[0] for tap in taps}
    assert {"roll", "use", "confirm"} <= kinds, kinds
    after = phone.screen(ctrl)
    assert after["screen"] == "after_battle" and ids(after) == ["to_menu"]
    assert ctrl.engine is not None and ctrl.engine.state.battle_records[0]["battle"] == 1
    phone.act(ctrl, "to_menu")
    assert phone.screen(ctrl)["screen"] == "menu"


def test_a_tap_that_is_not_offered_changes_nothing(tmp_path):
    ctrl = controller(tmp_path)
    phone.act(ctrl, "roll")
    assert ctrl.screen == Screen.MAIN_MENU and ctrl.message == "That is not possible on this screen." and ctrl.message_is_error
    phone.act(ctrl, "menu:new")
    phone.act(ctrl, "party:add:squire")
    phone.act(ctrl, "party:begin")
    before = len(ctrl.engine.events)
    phone.act(ctrl, "confirm")  # nothing is planned: either not offered yet, or offered and off with its reason
    assert len(ctrl.engine.events) == before and ctrl.message_is_error


def test_the_dice_show_the_plans_prediction_and_a_target_is_chosen_by_a_tap_on_its_card(tmp_path):
    ctrl = controller(tmp_path)
    phone.act(ctrl, "menu:new")
    for class_id in ("scout", "squire"):
        phone.act(ctrl, f"party:add:{class_id}")
    phone.act(ctrl, "party:begin")
    for _ in range(200):
        view = phone.screen(ctrl)
        turn = ctrl.view().get("hero_turn")
        if turn and turn["hero_id"] == "h01" and not turn["rolled"]:
            break
        offered = [a for a in view["actions"] if a["enabled"]]
        phone.act(ctrl, next(a for a in offered if a["id"] in ("skip_all", "roll", "pass"))["id"])
    else:
        raise AssertionError("the Scout never came up")
    phone.act(ctrl, "roll")
    ctrl.engine.combat.turn.rolled.update({"striker_d8": 0, "tools_d4": 3})  # Shot and Blank
    view = phone.screen(ctrl)
    dice = next(group for group in view["groups"] if group["tone"] == "die")
    assert [card["title"] for card in dice["cards"]] == ["Striker d8: Shot", "Tools d4: Blank"]
    assert dice["cards"][0]["tap"]["enabled"] and not dice["cards"][1]["tap"]["enabled"] and dice["cards"][1]["tap"]["reason"]
    phone.act(ctrl, "use:striker_d8")
    view = phone.screen(ctrl)
    targets = [card["tap"]["id"] for group in view["groups"] for card in group["cards"] if card["tap"] and card["tap"]["id"].startswith("target:")]
    assert len(targets) >= 2 and ids(view).count("cancel_target") == 1
    phone.act(ctrl, targets[0])
    view = phone.screen(ctrl)
    dice = next(group for group in view["groups"] if group["tone"] == "die")
    assert "In the plan" in dice["cards"][0]["lines"] and dice["cards"][0]["tap"]["label"] == "Remove"
    assert next(a for a in view["actions"] if a["id"] == "confirm")["enabled"]


@pytest.mark.parametrize(("said", "shown"), [
    ("Rolled. Reroll (R) rerolls every die you have not kept; Keep (Z, X) holds a die. Then choose actions.",
     "Rolled. Reroll rerolls every die you have not kept; Keep holds a die. Then choose actions."),
    ("Squire 1 is up. Roll the dice (R).", "Squire 1 is up. Roll the dice."),
    ("Choose a target for Strike (Esc cancels).", "Choose a target for Strike."),
    ("Strike aims at Goblin Skirmisher, the only legal target. Plan is legal.", "Strike aims at Goblin Skirmisher, the only legal target. Plan is legal."),
    ("Now deals 2 (Weaken -1).", "Now deals 2 (Weaken -1)."),
])
def test_messages_lose_their_key_hints_and_nothing_else(said, shown):
    assert phone.touch_wording(said) == shown


def test_the_screen_free_self_check_plays_a_run_and_reads_the_save_back(tmp_path):
    result = selfcheck.run(tmp_path)
    assert result["outcome"] in ("victory", "defeat") and result["battles"] >= 1 and result["heroes_saved"] == 3
    assert result["save_read_back"] is True and (tmp_path / "saves" / "profile.sqlite").is_file()
    line = selfcheck.report_line(result)
    assert line.startswith("BATTLE DICE SELF-CHECK OK: outcome=") and "save_read_back=True" in line


def test_the_self_check_gives_the_same_answer_on_every_start(tmp_path):
    """Found on the emulator: the app's second start reported a failed check, because the first one's heroes
    were still in the save. A check must start from nothing each time, and must not pile up files."""
    first = selfcheck.run(tmp_path / "check")
    logs = sorted(path.name for path in (tmp_path / "check" / "logs").rglob("*") if path.is_file())
    second = selfcheck.run(tmp_path / "check")
    assert second == first and second["heroes_saved"] == 3
    assert sorted(path.name for path in (tmp_path / "check" / "logs").rglob("*") if path.is_file()) == logs, "the files do not pile up"


def test_a_check_that_was_cut_short_does_not_spoil_the_next_one(tmp_path, monkeypatch):
    """A phone app can be closed while the check runs. What that leaves behind is cleared too."""
    with monkeypatch.context() as patch:
        patch.setattr(selfcheck, "STEP_LIMIT", 5)
        with pytest.raises(selfcheck.SelfCheckFailed, match="the run did not finish"):
            selfcheck.run(tmp_path)
    assert selfcheck.run(tmp_path)["heroes_saved"] == 3


def test_the_self_check_never_empties_a_folder_that_is_not_its_own(tmp_path):
    """It removes what an earlier check left. A player's save must never be taken for that."""
    game = AppController(log_dir=tmp_path / "logs", features=[selfcheck.CLASS_EVOLUTION], save_dir=tmp_path / "saves")
    try:
        game.new_run()
        game.add_hero("squire")
    finally:
        game.close()
    save = tmp_path / "saves" / "profile.sqlite"
    before = save.read_bytes()
    with pytest.raises(selfcheck.SelfCheckFailed, match="not the self-check's. Give the self-check a folder of its own"):
        selfcheck.run(tmp_path)
    assert save.read_bytes() == before and not (tmp_path / selfcheck.MARKER).exists()


def test_neither_the_self_check_nor_the_phone_screens_load_pygame(tmp_path):
    """The phone has no pygame. A fresh interpreter proves that nothing here asks for it."""
    code = (
        "import sys, pathlib\n"
        "from battle_dice.app import selfcheck\n"
        "from battle_dice.app.controller import AppController\n"
        "from battle_dice.phone import screens as phone\n"
        f"folder = pathlib.Path({str(tmp_path)!r})\n"
        "result = selfcheck.run(folder / 'check')\n"
        "ctrl = AppController(fixed_seed=3, log_dir=folder / 'logs')\n"
        "phone.act(ctrl, 'menu:new'); phone.act(ctrl, 'party:add:squire'); phone.act(ctrl, 'party:begin'); phone.screen(ctrl)\n"
        "print('pygame' in sys.modules, result['pygame_loaded'])\n"
    )
    done = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True, check=True)
    assert done.stdout.split() == ["False", "False"], done.stdout + done.stderr


def test_a_self_check_that_finds_a_fault_says_which(tmp_path, monkeypatch):
    monkeypatch.setattr(selfcheck, "STEP_LIMIT", 5)
    with pytest.raises(selfcheck.SelfCheckFailed, match="the run did not finish"):
        selfcheck.run(tmp_path)


# --------------------------------------------------------------------------------------------
# The check of a built APK (android/tools/check_apk.py)
# --------------------------------------------------------------------------------------------


def _elf64(alignments: list[int]) -> bytes:
    """A minimal 64-bit library header with one loadable part per alignment."""
    import struct

    header = bytearray(64)
    header[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<Q", header, 0x20, 64)                # where the program headers begin
    struct.pack_into("<HH", header, 0x36, 56, len(alignments))  # their size and number
    parts = b""
    for alignment in alignments:
        part = bytearray(56)
        struct.pack_into("<I", part, 0, 1)                  # a loadable part
        struct.pack_into("<Q", part, 0x30, alignment)
        parts += bytes(part)
    return bytes(header) + parts


def test_the_apk_check_reads_size_processor_types_and_page_alignment(tmp_path, capsys):
    import importlib.util
    import zipfile
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("check_apk", Path(__file__).resolve().parents[2] / "android" / "tools" / "check_apk.py")
    assert spec is not None and spec.loader is not None
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    assert tool.load_alignments(_elf64([0x4000, 0x4000])) == [0x4000, 0x4000] and tool.load_alignments(b"not a library") == []
    good, bad = tmp_path / "good.apk", tmp_path / "bad.apk"
    for path, alignment in ((good, 0x4000), (bad, 0x1000)):
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as apk:
            apk.writestr("lib/arm64-v8a/libapp.so", _elf64([alignment]))
            apk.writestr("lib/x86_64/libapp.so", _elf64([0x4000]))
            apk.writestr("classes.dex", b"dex")
    found = tool.check(good)
    assert (found["abis"], found["libraries"], found["not_16k_inside"], found["not_16k_in_the_apk"]) == (["arm64-v8a", "x86_64"], 2, [], [])
    assert tool.check(bad)["not_16k_inside"] == ["lib/arm64-v8a/libapp.so (4096)"]
    assert tool.main([str(good)]) == 0 and "pages_16k=yes" in capsys.readouterr().out
    assert tool.main([str(bad)]) == 0 and "pages_16k=NO" in capsys.readouterr().out
    assert tool.main([]) == 2


# --------------------------------------------------------------------------------------------
# The emulator script (android/tools/emulator_check.sh), run against a stand-in for adb
# --------------------------------------------------------------------------------------------
# The stand-in keeps the device's state in files: how often the app was started, which way the screen is
# turned, and the device log of each start. A screenshot is a picture header of the size the screen has.
FAKE_ADB = r"""#!/usr/bin/env bash
state="$FAKE_ADB_STATE"
start="$(cat "$state/starts")"
case "$*" in
  "install -r "*) echo Success ;;
  "shell pm list packages -3") cat "$state/packages" ;;
  "shell am force-stop "*|"logcat -c") ;;
  "shell monkey "*) echo $(( start + 1 )) > "$state/starts" ;;
  "logcat -d")
    cat "$state/log_$start" 2>/dev/null || true
    if [ "$(cat "$state/turned")" = 1 ]; then cat "$state/log_${start}_turned" 2>/dev/null || true; fi ;;
  "exec-out screencap -p")
    if [ "$(cat "$state/turned")" = 1 ]; then printf '\x89PNG\r\n\x1a\n\0\0\0\rIHDR\0\0\x0c\x30\0\0\x05\xa0'
    else printf '\x89PNG\r\n\x1a\n\0\0\0\rIHDR\0\0\x05\xa0\0\0\x0c\x30'; fi ;;
  "shell settings put system user_rotation "*) echo "$*" >> "$state/settings"; [ -f "$state/stuck" ] || echo "$6" > "$state/turned" ;;
  "emu sensor set acceleration 9.81:0:0") echo "$*" >> "$state/settings"; [ -f "$state/stuck" ] || echo 1 > "$state/turned" ;;
  "emu sensor set acceleration 0:9.81:0") echo "$*" >> "$state/settings"; echo 0 > "$state/turned" ;;
  "shell settings put "*|"shell cmd window user-rotation lock "*) echo "$*" >> "$state/settings" ;;
  "shell settings get system "*) echo 0 ;;
  "shell dumpsys window displays") printf '  mDisplayRotation=ROTATION_0\n  size of the display\n  mLastOrientation=-1\n' ;;
  *) echo "the stand-in for adb does not know: $*" >&2; exit 9 ;;
esac
"""
STAMP = "11-21 07:47:38.870  2563  2840 I flet.python: "
UPRIGHT = STAMP + "BATTLE DICE SCREEN: layout=upright width=411 height=891"
SIDEWAYS = STAMP + "BATTLE DICE SCREEN: layout=sideways width=891 height=411"
PASSED = UPRIGHT + "\n" + STAMP + "BATTLE DICE SELF-CHECK OK: outcome=victory battles=3"
FAILED = UPRIGHT + "\n" + STAMP + "BATTLE DICE SELF-CHECK FAILED: SelfCheckFailed: the heroes did not reach the save"
GOOD_END = "EMULATOR CHECK OK: four starts, four passed self-checks, the layout followed the screen"
STARTS = ("1_upright", "2_larger_font", "3_sideways", "4_started_sideways")


def emulator_check(tmp_path, logs: list[str | None], turned: str | None = SIDEWAYS, stuck: bool = False, follows: tuple[int, ...] = (1, 2, 3, 4),
                   packages: str = "package:com.android.chrome\npackage:dev.battledice.battle_dice_android\n"):
    """Runs the script. ``logs`` is the device log of each start in turn (None: the app never reports; starts
    that are not given pass);
    ``turned`` is what the app adds to the log once the screen is sideways (None: it does not notice), in the
    starts named by ``follows``;
    ``stuck`` is a device whose screen does not turn."""
    import os
    from pathlib import Path

    state, tools, out = tmp_path / "state", tmp_path / "tools", tmp_path / "out"
    state.mkdir()
    tools.mkdir()
    (tools / "adb").write_text(FAKE_ADB, encoding="utf-8", newline="\n")
    (tools / "adb").chmod(0o755)
    (state / "starts").write_text("0\n", encoding="utf-8")
    (state / "turned").write_text("0\n", encoding="utf-8")
    (state / "packages").write_text(packages, encoding="utf-8")
    if stuck:
        (state / "stuck").write_text("", encoding="utf-8")
    for number, log in enumerate([*logs, *[PASSED] * (len(STARTS) - len(logs))], start=1):
        if log is not None:
            (state / f"log_{number}").write_text(f"other line\n{log}\n", encoding="utf-8")
        if turned is not None and number in follows:
            (state / f"log_{number}_turned").write_text(f"{turned}\n", encoding="utf-8")
    script = Path(__file__).resolve().parents[2] / "android" / "tools" / "emulator_check.sh"
    env = {**os.environ, "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}", "FAKE_ADB_STATE": str(state),
           "EMULATOR_CHECK_PAUSE": "0", "EMULATOR_CHECK_POLL": "0", "EMULATOR_CHECK_LIMIT": "0", "EMULATOR_CHECK_SETTLE": "0"}
    done = subprocess.run(["bash", str(script), "app.apk", str(out)], env=env, capture_output=True, text=True, check=False, timeout=60)
    return done, out, state


needs_bash = pytest.mark.skipif(sys.platform == "win32", reason="the script runs on the Linux build machine")


@needs_bash
def test_the_emulator_check_passes_when_every_start_passes_and_the_layout_follows_the_screen(tmp_path):
    done, out, state = emulator_check(tmp_path, [PASSED, PASSED, PASSED])
    assert done.returncode == 0 and GOOD_END in done.stdout, done.stdout + done.stderr
    assert "package: dev.battledice.battle_dice_android" in done.stdout
    report = (out / "report.txt").read_text(encoding="utf-8").splitlines()
    assert [line.split(":")[0] for line in report] == [name for start in STARTS for name in (start, start)] + ["EMULATOR CHECK OK"]
    # (The seconds are whatever the machine took: a busy one may need one or two even with nothing to wait for.)
    assert all("BATTLE DICE SELF-CHECK OK" in line and re.search(r" seconds_until_report=\d+$", line) for line in report[0:8:2])
    assert report[1] == "1_upright: BATTLE DICE SCREEN: layout=upright width=411 height=891 (expected upright; the screenshot is 1440x3120)"
    assert report[5] == "3_sideways: BATTLE DICE SCREEN: layout=sideways width=891 height=411 (expected sideways; the screenshot is 3120x1440)"
    assert report[7] == "4_started_sideways: BATTLE DICE SCREEN: layout=sideways width=891 height=411 (expected sideways; the screenshot is 3120x1440)"
    assert all((out / f"{name}.png").stat().st_size == 24 and (out / f"{name}_logcat.txt").is_file() for name in STARTS)
    # The larger font is set for the second start only. The screen is turned in the third start and turned back;
    # for the fourth the device is held sideways with its screen free to turn, and put back upright and locked.
    turn = lambda way: ["shell settings put system accelerometer_rotation 0", f"shell settings put system user_rotation {way}", f"shell cmd window user-rotation lock {way}"]  # noqa: E731
    free = "shell settings put system accelerometer_rotation 1"
    assert (state / "settings").read_text(encoding="utf-8").splitlines() == [
        "shell settings put system font_scale 1.3", "shell settings put system font_scale 1.0", *turn(1), *turn(0),
        free, "emu sensor set acceleration 9.81:0:0", free, "emu sensor set acceleration 0:9.81:0", "shell settings put system accelerometer_rotation 0"]
    assert "auto-rotate" not in done.stdout, "the device's rotation facts are printed only when a layout is wrong"
    assert (state / "turned").read_text(encoding="utf-8").strip() == "0"


@needs_bash
@pytest.mark.parametrize(("logs", "named"), [
    ([PASSED, FAILED, PASSED], "2_larger_font"),       # what the first emulator run did, and the script called it passed
    ([PASSED, PASSED, FAILED], "3_sideways"),
    ([FAILED, PASSED, PASSED], "1_upright"),
    ([PASSED, FAILED, FAILED], "2_larger_font 3_sideways"),
    ([PASSED, PASSED, PASSED, FAILED], "4_started_sideways"),
])
def test_the_emulator_check_fails_when_any_start_does_not_report_a_passed_self_check(tmp_path, logs, named):
    done, out, _ = emulator_check(tmp_path, logs)
    assert done.returncode == 1 and f"EMULATOR CHECK FAILED: no passed self-check at: {named}\n" in done.stdout, done.stdout + done.stderr
    assert "EMULATOR CHECK OK" not in done.stdout and "not the expected layout" not in done.stdout
    assert f"EMULATOR CHECK FAILED: no passed self-check at: {named}\n" in (out / "report.txt").read_text(encoding="utf-8")
    assert (out / "3_sideways.png").is_file(), "the screenshots are kept also when a start fails: they are the evidence"


@needs_bash
def test_the_emulator_check_fails_when_the_app_never_reports(tmp_path):
    done, out, _ = emulator_check(tmp_path, [PASSED, PASSED, None], turned=None)
    assert done.returncode == 1 and "3_sideways: no self-check report within 0 seconds (see 3_sideways_logcat.txt)" in done.stdout
    assert "EMULATOR CHECK FAILED: no passed self-check at: 3_sideways\n" in done.stdout
    assert "3_sideways: the app reported no layout (expected sideways; the screenshot is 3120x1440)" in done.stdout
    assert "EMULATOR CHECK FAILED: not the expected layout at: 3_sideways 4_started_sideways\n" in done.stdout


@needs_bash
def test_the_emulator_check_fails_when_the_app_stays_upright_on_a_turned_screen(tmp_path):
    """The second emulator run: all self-checks passed, the start named sideways was upright, and nothing said so."""
    done, out, _ = emulator_check(tmp_path, [PASSED, PASSED, PASSED], turned=None)
    assert done.returncode == 1 and "EMULATOR CHECK OK" not in done.stdout, done.stdout + done.stderr
    for name in ("3_sideways", "4_started_sideways"):
        assert f"{name}: BATTLE DICE SCREEN: layout=upright width=411 height=891 (expected sideways; the screenshot is 3120x1440)" in done.stdout
    assert done.stdout.rstrip().endswith("EMULATOR CHECK FAILED: not the expected layout at: 3_sideways 4_started_sideways") and "no passed self-check" not in done.stdout


@needs_bash
def test_the_report_shows_when_it_was_the_screen_that_did_not_turn(tmp_path):
    """Then the screenshot is upright too: the fault is the emulator's, and the report lets a reader see it."""
    done, _, _ = emulator_check(tmp_path, [PASSED, PASSED, PASSED], stuck=True)
    assert done.returncode == 1
    assert "3_sideways: BATTLE DICE SCREEN: layout=upright width=411 height=891 (expected sideways; the screenshot is 1440x3120)" in done.stdout
    # What the device says about its rotation follows each wrong layout, in the job's log and in the report.
    facts = "    auto-rotate: 0, user rotation: 0\n    mDisplayRotation=ROTATION_0\n    mLastOrientation=-1\n"
    assert done.stdout.count(facts) == 2 and "size of the display" not in done.stdout


@needs_bash
def test_the_emulator_check_tells_a_turn_while_running_from_a_start_on_a_turned_screen(tmp_path):
    """An app that follows a turn but comes up upright when started sideways fails at the fourth start only."""
    done, _, _ = emulator_check(tmp_path, [PASSED] * 4, follows=(3,))
    assert done.returncode == 1 and done.stdout.rstrip().endswith("EMULATOR CHECK FAILED: not the expected layout at: 4_started_sideways"), done.stdout
    assert "3_sideways: BATTLE DICE SCREEN: layout=sideways width=891 height=411 (expected sideways; the screenshot is 3120x1440)" in done.stdout


@needs_bash
def test_the_emulator_check_fails_when_an_upright_start_is_laid_out_sideways(tmp_path):
    done, _, _ = emulator_check(tmp_path, [PASSED.replace(UPRIGHT, SIDEWAYS), PASSED, PASSED])
    assert done.returncode == 1 and "EMULATOR CHECK FAILED: not the expected layout at: 1_upright\n" in done.stdout


@needs_bash
def test_the_emulator_check_fails_when_the_app_is_not_installed(tmp_path):
    done, _, _ = emulator_check(tmp_path, [PASSED, PASSED, PASSED], packages="package:com.android.chrome\n")
    assert done.returncode == 1 and "EMULATOR CHECK FAILED: the app's package was not found after the install" in done.stdout
