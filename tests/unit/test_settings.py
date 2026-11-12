"""The player's settings file (the demo's configuration).

A setting is a choice a player may make without touching code. A file that cannot be read or a
value that is not allowed never stops the game: the default is used and the problem is reported.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from battle_dice import settings as module
from battle_dice.settings import PACES, PRESETS, ROSTER_LIMITS, WINDOW_SIZES, Settings


def test_the_defaults_are_the_shipped_game():
    defaults = Settings()
    assert defaults.class_evolution is False, "Class Evolution is off until the player switches it on"
    assert (defaults.third_battle, defaults.animation, defaults.seed, defaults.save_dir) == (True, True, None, None)
    assert (defaults.window_size, defaults.size()) == ("1280x720", (1280, 720))
    assert (defaults.roster_limit, defaults.mastery_pace, defaults.demo_preset) == (12, "normal", "fresh")
    assert defaults.mastery_pace in PACES and defaults.demo_preset in PRESETS and defaults.window_size in WINDOW_SIZES
    assert defaults.roster_limit in ROSTER_LIMITS


def test_no_file_means_the_defaults_and_no_problem(tmp_path: Path):
    assert module.load(tmp_path / "settings.json") == (Settings(), [])
    assert not (tmp_path / "settings.json").exists(), "reading never creates the file"


def test_what_is_saved_is_what_is_loaded(tmp_path: Path):
    chosen = Settings(class_evolution=True, third_battle=False, animation=False, seed=12345, window_size="1600x900",
                      save_dir=str(tmp_path / "my saves"), roster_limit=24, mastery_pace="very_fast", demo_preset="guardian_mastered")
    file = module.save(chosen, tmp_path / "deep" / "folder" / "settings.json")
    assert file.is_file() and json.loads(file.read_text(encoding="utf-8"))["version"] == 1
    assert module.load(file) == (chosen, [])


@pytest.mark.parametrize(("text", "said"), [
    ("{not json", "could not be read"),
    ("[1, 2, 3]", "is not a settings object"),
    ('"class_evolution"', "is not a settings object"),
])
def test_a_file_that_is_not_a_settings_file_gives_the_defaults_and_says_so(tmp_path: Path, text, said):
    file = tmp_path / "settings.json"
    file.write_text(text, encoding="utf-8")
    loaded, problems = module.load(file)
    assert loaded == Settings() and len(problems) == 1 and said in problems[0] and "settings.json" in problems[0]


@pytest.mark.parametrize(("name", "value", "said"), [
    ("class_evolution", "yes", "must be true or false"),
    ("animation", 1, "must be true or false"),
    ("seed", -1, "must be null or a whole number"),
    ("seed", 2**64, "must be null or a whole number"),
    ("seed", True, "must be null or a whole number"),
    ("seed", "12", "must be null or a whole number"),
    ("window_size", "800x600", "must be one of 960x540"),
    ("save_dir", "   ", "must be null or a folder path"),
    ("save_dir", 7, "must be null or a folder path"),
    ("roster_limit", 0, "must be a whole number from 1 to 50"),
    ("roster_limit", 51, "must be a whole number from 1 to 50"),
    ("roster_limit", 12.5, "must be a whole number from 1 to 50"),
    ("mastery_pace", "instant", "must be one of normal, fast, very_fast"),
    ("demo_preset", "everything", "must be one of fresh"),
    ("difficulty", "hard", "is not a setting"),
])
def test_a_value_that_is_not_allowed_keeps_its_default_and_every_other_value_is_used(tmp_path: Path, name, value, said):
    file = tmp_path / "settings.json"
    file.write_text(json.dumps({"version": 1, "third_battle": False, name: value}), encoding="utf-8")
    loaded, problems = module.load(file)
    assert loaded == Settings(third_battle=False), "the good value is used, the bad one is not"
    assert problems == [f"settings.json: {name} {said}; the default is used."] or (len(problems) == 1 and said in problems[0])
    with pytest.raises(ValueError, match=name):
        module.validate(name, value)


def test_allowed_values_pass_validation():
    for name, value in (("seed", 0), ("seed", 2**64 - 1), ("seed", None), ("roster_limit", 1), ("roster_limit", 50),
                        ("save_dir", "D:/games/saves"), ("save_dir", None), ("mastery_pace", "fast"), ("window_size", "960x540")):
        module.validate(name, value)


def test_the_file_is_in_the_working_folder_from_source_and_the_user_folder_when_packaged(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(module.ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    assert module.data_dir() == tmp_path and module.default_path() == tmp_path / "settings.json"
    monkeypatch.setattr(module.sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData"))
    assert module.default_path() == tmp_path / "AppData" / "BattleDice" / "settings.json"
    monkeypatch.setenv(module.ENV_VAR, str(tmp_path / "elsewhere.json"))
    assert module.default_path() == tmp_path / "elsewhere.json"


def test_the_shipped_game_is_untouched_by_a_missing_or_default_settings_file(tmp_path: Path):
    """The controller made with default settings is the controller the game always had."""
    from battle_dice.app.controller import AppController

    plain = AppController(fixed_seed=1, log_dir=tmp_path / "a")
    with_defaults = AppController(fixed_seed=1, log_dir=tmp_path / "b", settings=Settings(), settings_path=tmp_path / "settings.json")
    for ctrl in (plain, with_defaults):
        assert ctrl.features == frozenset() and ctrl.vocations is None and ctrl.progression is None and ctrl.fixed_seed == 1
        ctrl.new_run()
        ctrl.add_hero("squire")
        ctrl.begin_run()
        assert ctrl.engine is not None and ctrl.engine.state.run_id == "run-1-1" and ctrl.engine.battle_count == 2
    assert not list(tmp_path.rglob("*.sqlite")) and not (tmp_path / "settings.json").exists()
