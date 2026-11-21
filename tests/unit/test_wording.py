"""Messages for a device without keys (Android plan, phase 1, step 2).

A controller made with ``touch=True`` words everything it says for a finger. The desktop's
wording is not changed by any of this.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from battle_dice.app import wording
from battle_dice.app.controller import AppController
from battle_dice.phone import screens as phone
from tests.phone.test_phone_screens import tap_through_a_battle

ROOT = Path(__file__).resolve().parents[2]
#: Where the game's messages to the player are written without a toolkit.
SOURCES = ("src/battle_dice/app/controller.py", "src/battle_dice/app/progression.py", "src/battle_dice/core/view.py",
           "src/battle_dice/core/planning.py", "src/battle_dice/phone/screens.py")


def messages_in(path: Path) -> list[str]:
    """Every text in a source file that is not a docstring; a formatted text with ``{}`` for each value."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) and node.body
                  and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)}
    inside_formatted = {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            found.append("".join(str(part.value) if isinstance(part, ast.Constant) else "{}" for part in node.values))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings and id(node) not in inside_formatted:
            found.append(node.value)
    return found


def test_no_message_the_game_can_say_names_a_key_a_press_or_a_click_once_worded_for_touch():
    """Read from the source, so a message added later is checked without anyone remembering to."""
    desktop_only, left = [], []
    for source in SOURCES:
        for text in messages_in(ROOT / source):
            if wording.LEFT_OVER.search(text):
                desktop_only.append(text)
                worded = wording.touch_wording(text)
                if wording.LEFT_OVER.search(worded):
                    left.append((source, text, worded))
    assert left == [], left
    assert len(desktop_only) >= 14, "the scan finds the messages that name keys: " + repr(desktop_only)
    assert any("Roll the dice (R)" in text for text in desktop_only) and any("Press again to dismiss" in text for text in desktop_only)


@pytest.mark.parametrize(("said", "for_touch"), [
    ("Recruit 1 is up. Roll the dice (R).", "Recruit 1 is up. Roll the dice."),
    ("Rolled. Reroll (R) rerolls every die you have not kept; Keep (Z, X) holds a die. Then choose actions.",
     "Rolled. Reroll rerolls every die you have not kept; Keep holds a die. Then choose actions."),
    ("Choose a target for Strike (Esc cancels).", "Choose a target for Strike."),
    ("Choose which ally receives the reaction: press its number or click it (Esc cancels).", "Choose which ally receives the reaction: tap it."),
    ("Press again to abandon this run. It is not saved and cannot be continued.", "Tap again to abandon this run. It is not saved and cannot be continued."),
    ("A die could still act. Press Pass again to pass anyway.", "A die could still act. Tap Pass again to pass anyway."),
    ("press D to type a seed", "tap to type a seed"),
    ("type digits, Enter to set, Esc to cancel", "type digits, then set or cancel"),
    ("Type a dice seed (digits). Enter sets it, Esc cancels. The same seed, party and choices give the same run.",
     "Type a dice seed (digits). Then set it or cancel. The same seed, party and choices give the same run."),
    ("Click a hero to add it, or click its Career button.", "Tap a hero to add it, or tap its Career button."),
    # What is not a key stays: numbers in brackets, names, and words that only contain "press".
    ("Now deals 2 (Weaken -1).", "Now deals 2 (Weaken -1)."),
    ("Disrupt (2 mana): cancel a basic hostile ability.", "Disrupt (2 mana): cancel a basic hostile ability."),
    ("Squire 2 is at 14/15 HP (Steadfast +1).", "Squire 2 is at 14/15 HP (Steadfast +1)."),
    ("The enemy is suppressed and impressed.", "The enemy is suppressed and impressed."),
])
def test_touch_wording_takes_the_keys_out_and_nothing_else(said, for_touch):
    assert wording.touch_wording(said) == for_touch
    assert wording.touch_wording(for_touch) == for_touch, "wording it twice changes nothing more"
    assert phone.touch_wording is wording.touch_wording


def begun(tmp_path, **options) -> AppController:
    controller = AppController(fixed_seed=11, log_dir=tmp_path / "logs", **options)
    controller.new_run()
    controller.add_hero("squire")
    controller.add_hero("scout")
    controller.begin_run()
    phone.settle(controller)
    return controller


def test_a_touch_controller_says_its_messages_without_keys_and_a_desktop_one_as_before(tmp_path):
    desktop, touch = begun(tmp_path / "desktop"), begun(tmp_path / "touch", touch=True)
    assert desktop.message.endswith("is up. Roll the dice (R).") and touch.message == desktop.message.replace(" (R)", "")
    for controller in (desktop, touch):
        controller.roll()
    assert "Reroll (R) rerolls" in desktop.message and "Keep (Z, X) holds" in desktop.message
    assert touch.message == "Rolled. Reroll rerolls every die you have not kept; Keep holds a die. Then choose actions."
    # A safeguard asks once more in the device's own word, and still works.
    for controller, word in ((desktop, "Press"), (touch, "Tap")):
        controller.open_pause()
        controller.abandon_to_menu()
        assert controller.message == f"{word} again to abandon this run. It is not saved and cannot be continued." and controller.engine is not None
        controller.abandon_to_menu()
        assert controller.engine is None
    # Texts that are not messages are worded too: the seed control's hint.
    hints = [AppController(log_dir=tmp_path / "logs", touch=touch).seed_view()["hint"] for touch in (False, True)]
    assert hints == ["press D to type a seed", "tap to type a seed"]


def test_the_phone_screens_word_a_desktop_controllers_message_for_touch_too(tmp_path):
    """The screen data is for a finger whoever made the controller."""
    desktop = begun(tmp_path)
    assert desktop.message.endswith("Roll the dice (R).") and phone.screen(desktop)["message"].endswith("is up. Roll the dice.")


def test_everything_a_touch_controller_says_in_a_whole_battle_is_free_of_keys(tmp_path):
    controller = begun(tmp_path, touch=True)
    said = {controller.message}
    def listening(say):  # every message, also one that the next replaces at once
        def spy(text):
            say(text)
            said.add(controller.message)
        return spy

    for name in ("info", "warn"):
        setattr(controller, name, listening(getattr(controller, name)))
    taps = tap_through_a_battle(controller)
    assert len(taps) > 20 and len(said) > 10, sorted(said)
    assert [text for text in said if wording.LEFT_OVER.search(text)] == []
    assert any(text.endswith("Roll the dice.") for text in said) and any(text.startswith("Choose a target for") for text in said)


def test_the_phone_app_asks_for_touch_wording():
    """The app is not imported by the tests (it needs the phone toolkit), so its one line is read."""
    source = (ROOT / "android" / "src" / "main.py").read_text(encoding="utf-8")
    assert source.count("AppController(") == 1 and 'AppController(log_dir=folder / "logs", touch=True)' in source
