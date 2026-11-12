"""The player's settings: one small JSON file, read at launch and written when a setting changes.

Everything here is a choice a player or the owner may make without touching code. Nothing in it
changes the rules of a battle, the shipped content or the replay pin.

Order of precedence at launch: a command-line flag, then an environment variable, then this
file, then the default. A file that cannot be read, or a value that is not allowed, never stops
the game: the default is used for it and the problem is reported on the main menu.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

FILE_NAME = "settings.json"
ENV_VAR = "BATTLE_DICE_SETTINGS"
#: How fast mastery is earned: every rank needs its points divided by this number (rounded up).
PACES = {"normal": 1, "fast": 2, "very_fast": 4}
#: What a new or reset profile starts with (Class Evolution).
PRESETS = ("fresh", "squire_near_mastery", "guardian_unlocked", "guardian_mastered")
WINDOW_SIZES = ("960x540", "1280x720", "1600x900", "1920x1080")
ROSTER_LIMITS = (6, 12, 24)
MAX_SEED = 2**64 - 1


@dataclass
class Settings:
    #: Play with saved heroes, mastery and vocations. Off by default: the game is then exactly the shipped game.
    class_evolution: bool = False
    #: Offer the third, harder battle after Battle 2 (only with Class Evolution).
    third_battle: bool = True
    animation: bool = True
    #: A fixed seed for every run, or ``None`` for a new one each run.
    seed: int | None = None
    window_size: str = "1280x720"
    #: Folder of the save file, or ``None`` for the usual place.
    save_dir: str | None = None
    roster_limit: int = 12
    mastery_pace: str = "normal"
    demo_preset: str = "fresh"

    def size(self) -> tuple[int, int]:
        width, height = self.window_size.split("x")
        return int(width), int(height)


def _problem(name: str, value: Any) -> str | None:
    """Why ``value`` is not allowed for the setting ``name``; ``None`` when it is."""
    if name in ("class_evolution", "third_battle", "animation"):
        return None if isinstance(value, bool) else "must be true or false"
    if name == "seed":
        ok = value is None or (isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_SEED)
        return None if ok else "must be null or a whole number from 0 to 2^64 - 1"
    if name == "window_size":
        return None if value in WINDOW_SIZES else f"must be one of {', '.join(WINDOW_SIZES)}"
    if name == "save_dir":
        return None if value is None or (isinstance(value, str) and value.strip()) else "must be null or a folder path"
    if name == "roster_limit":
        ok = isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 50
        return None if ok else "must be a whole number from 1 to 50"
    if name == "mastery_pace":
        return None if value in PACES else f"must be one of {', '.join(PACES)}"
    if name == "demo_preset":
        return None if value in PRESETS else f"must be one of {', '.join(PRESETS)}"
    return "is not a setting"


def validate(name: str, value: Any) -> None:
    problem = _problem(name, value)
    if problem:
        raise ValueError(f"{name} {problem}")


def data_dir() -> Path:
    """Where the game keeps the player's files: the working folder from source, the per-user folder when packaged."""
    if getattr(sys, "frozen", False):
        return Path(os.environ.get("LOCALAPPDATA") or str(Path.home())) / "BattleDice"
    return Path.cwd()


def default_path() -> Path:
    override = os.environ.get(ENV_VAR)
    return Path(override) if override else data_dir() / FILE_NAME


def load(path: Path | str | None = None) -> tuple[Settings, list[str]]:
    """Read the settings file. Returns the settings and every problem found (an absent file is not one)."""
    file = Path(path) if path is not None else default_path()
    settings = Settings()
    problems: list[str] = []
    if not file.is_file():
        return settings, problems
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return settings, [f"{file.name} could not be read ({error}); the defaults are used."]
    if not isinstance(raw, dict):
        return settings, [f"{file.name} is not a settings object; the defaults are used."]
    known = {field.name for field in fields(Settings)}
    for name, value in raw.items():
        if name == "version":
            continue
        problem = _problem(name, value) if name in known else "is not a setting"
        if problem:
            problems.append(f"{file.name}: {name} {problem}; the default is used.")
        else:
            setattr(settings, name, value)
    return settings, problems


def save(settings: Settings, path: Path | str | None = None) -> Path:
    """Write the settings file (it is made, with its folder, when it does not exist)."""
    file = Path(path) if path is not None else default_path()
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps({"version": 1, **asdict(settings)}, indent=2) + "\n", encoding="utf-8")
    return file
