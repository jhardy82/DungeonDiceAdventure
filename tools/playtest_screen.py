"""Play Battle Dice step by step without a window, and see what a player would see.

Made for playtesting by an AI agent (or a script): each call applies some actions and prints the
screen as text, with every control that can be clicked, and saves a screenshot.

A session is a folder with a list of actions. Every call plays the whole list again from a fresh
start (fresh settings, fresh save), so a session is repeatable and needs no running process:

    python tools/playtest_screen.py --session DIR start [--size 1280x720] [--seed 500] [--feature NAME]
    python tools/playtest_screen.py --session DIR do click:menu:new key:1 key:b     (prints what changed)
    python tools/playtest_screen.py --session DIR do --full key:r                    (prints the whole screen)
    python tools/playtest_screen.py --session DIR look                               (prints the whole screen)
    python tools/playtest_screen.py --session DIR undo [N]
    python tools/playtest_screen.py --session DIR log

Actions:
    click:KEY      click the control with this key (as listed under CONTROLS), enabled or not
    clickxy:X,Y    click at a point of the 1280x720 layout
    hover:KEY      rest the pointer on a control, to read its help text (with the setting "Help text
                   delay" on, the help shows only after a following wait:MS)
    key:NAME       press a key: a letter or digit, or escape, enter, space, tab, shift+tab, backspace,
                   up, down, left, right
    type:DIGITS    press these digit keys one after another
    wait:MS        let this many milliseconds pass

After every action the game runs on until it waits for the player, as it does for a person.
Animation is off, so what is printed is the settled screen.

The first run of a session uses the session's seed (500 unless --seed is given) and each further
run the next number, also while the game's New Run screen says "Dice seed: random". That keeps a
session repeatable; it is the driver's doing, not the game's.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import shutil
import sys
import traceback
from pathlib import Path
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402 - the video driver must be chosen first

from battle_dice.app.controller import AppController, Screen  # noqa: E402
from battle_dice.ui.app import GameApp  # noqa: E402
from battle_dice.ui.toolkit import Trace  # noqa: E402

KEYS = {
    "escape": pygame.K_ESCAPE, "esc": pygame.K_ESCAPE, "enter": pygame.K_RETURN, "return": pygame.K_RETURN,
    "space": pygame.K_SPACE, "tab": pygame.K_TAB, "backspace": pygame.K_BACKSPACE, "up": pygame.K_UP,
    "down": pygame.K_DOWN, "left": pygame.K_LEFT, "right": pygame.K_RIGHT,
}
ROW_UNITS = 7  # texts whose middles are closer than this (in layout units) are printed as one line


class ActionError(Exception):
    """An action that cannot be carried out as written."""


def _session_file(folder: Path) -> Path:
    return folder / "session.json"


def load(folder: Path) -> dict[str, Any]:
    file = _session_file(folder)
    if not file.exists():
        raise SystemExit(f"No session in {folder}. Begin one with: --session {folder} start")
    session: dict[str, Any] = json.loads(file.read_text(encoding="utf-8"))
    return session


def save(folder: Path, session: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    _session_file(folder).write_text(json.dumps(session, indent=2), encoding="utf-8")


class Game:
    """One fresh game, driven by the events a player produces."""

    def __init__(self, folder: Path, session: dict[str, Any]):
        state = folder / "state"
        shutil.rmtree(state, ignore_errors=True)  # every replay starts from nothing: no settings, no save
        state.mkdir(parents=True)
        runs = iter(range(int(session["seed"]), int(session["seed"]) + 10_000))
        self.ctrl = AppController(
            seed_source=lambda: next(runs) & 0xFFFFFFFF,  # each new run gets the next seed: repeatable, and the game's own seed controls stay usable
            log_dir=state / "logs", settings_path=state / "settings.json", features=session.get("features", []),
            fixed_seed=session.get("fixed_seed"),
        )
        width, height = (int(part) for part in session["size"].split("x"))
        # Motion starts switched off, and the setting says so: a playtester reads one fact, not two (the playtest
        # of 2026-11-21 saw "Motion off (M)" in a battle while Settings said "On").
        self.ctrl.settings.animation = False
        self.app = GameApp(self.ctrl, size=(width, height), headless=True, animations=False)
        self.settle()

    # -- time ------------------------------------------------------------------------------------

    def settle(self) -> None:
        """Let the game run until it waits for the player, as it does for a person who watches."""
        for _ in range(5000):
            if self.ctrl.screen != Screen.BATTLE or self.ctrl.paused or self.ctrl.waiting_for_player():
                break
            self.app.frame(100)
        # With motion switched on, dice tumble for a moment. A person sees them settle before reading the
        # screen; so does the driver, instead of printing "Rolling ..." beside controls that are already on.
        for _ in range(100):
            if not (self.app.ui.anim.enabled and self.app.ui.anim.tumbles):
                break
            self.app.frame(50)
        self.app.frame(0)

    # -- actions ---------------------------------------------------------------------------------

    def _point_of(self, key: str) -> tuple[int, int]:
        widget = self.app.ui.widget(key)
        if widget is None:
            raise ActionError(f"no control {key!r} on this screen; the controls are: {', '.join(self.app.ui.keys())}")
        center: tuple[int, int] = widget.rect.center
        return center

    def _click(self, position: tuple[int, int]) -> None:
        self.app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=position, rel=(0, 0), buttons=(0, 0, 0)))
        self.app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=position, button=1))
        self.app.frame(0)

    def _press(self, name: str) -> None:
        shift = name.startswith("shift+")
        name = name.removeprefix("shift+")
        if name in KEYS:
            key = KEYS[name]
        elif len(name) == 1 and name.isascii() and name.isprintable():
            key = ord(name.lower())
        else:
            raise ActionError(f"unknown key {name!r}; use a letter, a digit, or one of: {', '.join(sorted(KEYS))}")
        text = name if len(name) == 1 else ""
        self.app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=pygame.KMOD_SHIFT if shift else 0, unicode=text))
        self.app.frame(0)

    def apply(self, action: str) -> None:
        kind, _, value = action.partition(":")
        if kind == "click":
            self._click(self._point_of(value))
        elif kind == "clickxy":
            try:
                x, y = (float(part) for part in value.split(","))
            except ValueError:
                raise ActionError(f"clickxy needs X,Y in layout units, not {value!r}") from None
            point = self.app.ui.r(x, y, 1, 1)
            self._click((point.x, point.y))
        elif kind == "hover":
            self.app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=self._point_of(value), rel=(0, 0), buttons=(0, 0, 0)))
            self.app.frame(0)  # the pointer is looked up at the end of a frame ...
            self.app.frame(0)  # ... and its help shows in the next one; with a help text delay set, only after `wait:MS`
        elif kind == "key":
            self._press(value)
        elif kind == "type":
            for digit in value:
                self._press(digit)
        elif kind == "wait":
            try:
                remaining = int(value)
            except ValueError:
                raise ActionError(f"wait needs milliseconds, not {value!r}") from None
            while remaining > 0:
                self.app.frame(min(100, remaining))
                remaining -= 100
        else:
            raise ActionError(f"unknown action {action!r}; see --help")
        self.settle()

    # -- what the player sees --------------------------------------------------------------------

    def describe(self, screenshot: Path | None) -> str:
        ui, app = self.app.ui, self.app
        ui.trace = Trace()
        app.frame(0)
        trace, ui.trace = ui.trace, None
        scale, (left, top) = ui.scale, ui.offset

        def units(rect: pygame.Rect) -> tuple[float, float]:
            return (rect.x - left) / scale, (rect.centery - top) / scale

        # Texts are printed panel by panel, as the eye reads them. A button's label is listed with the button below.
        buttons = {tuple(widget.rect) for widget in ui.widgets if widget.action is not None}
        sections: dict[tuple[int, int, int, int] | None, list[Any]] = {}
        for text in trace.texts:
            homes = [box for box in trace.boxes if box.contains(text.ink)]
            home = min(homes, key=lambda box: box.w * box.h) if homes else None
            if home is not None and tuple(home) in buttons:
                continue
            sections.setdefault((home.x, home.y, home.w, home.h) if home is not None else None, []).append(text)
        size = app.surface.get_size()
        lines = [f"SCREEN: {self.ctrl.screen}{'  (paused: the in-run menu is open)' if self.ctrl.paused else ''}    window {size[0]}x{size[1]}"]
        if app.render_faults:
            lines.append(f"DRAWING FAULTS: {app.render_faults}  (the game hit an error while drawing; this is a defect)")
        if self.ctrl.screen == Screen.ERROR:
            lines.append(f"ERROR SCREEN. The game's error text:\n{self.ctrl.error_text}")
        lines.append("")
        lines.append("TEXT ON SCREEN (panel by panel, top to bottom; texts on one line are separated by ' | '):")
        for place in sorted(sections, key=lambda key: (-1, -1) if key is None else (key[1], key[0])):
            if place is None:
                lines.append("  (not inside a panel)")
            else:
                x, y = units(pygame.Rect(place[0], place[1], 1, 1))
                lines.append(f"  [panel at x={x:.0f}, y={y:.0f}, {place[2] / scale:.0f} wide, {place[3] / scale:.0f} high]")
            row_y: list[float] = []
            rows: list[list[tuple[float, str]]] = []
            for text in sorted(sections[place], key=lambda item: (item.ink.centery, item.ink.x)):
                x, y = units(text.ink)
                words = text.shown + ("  [CUT OFF: the full text is " + repr(text.text) + "]" if text.shown != text.text else "")
                if row_y and y - row_y[-1] <= ROW_UNITS:
                    rows[-1].append((x, words))
                else:
                    rows.append([(x, words)])
                    row_y.append(y)
            lines += ["      " + " | ".join(words for _, words in sorted(row)) for row in rows]
        lines.append("")
        lines.append("CONTROLS (use the key after 'click:' or 'hover:'):")
        for widget in ui.widgets:
            label = " ".join(text.shown for text in sorted(trace.texts, key=lambda item: (item.ink.centery, item.ink.x))
                             if widget.rect.collidepoint(text.ink.center))
            keys = ", ".join(pygame.key.name(key) for key in widget.hotkeys)
            if widget.enabled:
                state = "enabled" if widget.action is not None else "shows information only"
            else:
                state = f"DISABLED ({widget.reason or 'no reason given'})"
            marks = "".join(mark for mark, on in ((" [focus]", ui.focus_key == widget.key), (" [pointer]", ui.hover_key == widget.key)) if on)
            lines.append(f"  {widget.key:28} {state}{'   keys: ' + keys if keys else ''}{marks}   label: {label[:70]!r}")
        if screenshot is not None:
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(app.surface, str(screenshot))
            lines += ["", f"SCREENSHOT: {screenshot}"]
        return "\n".join(lines)


def replay(folder: Path, session: dict[str, Any]) -> tuple[Game, str | None]:
    """Play the session's actions on a fresh game. Returns the game and what went wrong, if anything did."""
    game = Game(folder, session)
    for number, action in enumerate(session["actions"], start=1):
        try:
            game.apply(action)
        except ActionError as problem:
            return game, f"action {number} ({action}): {problem}"
    return game, None


def show(folder: Path, session: dict[str, Any], full: bool = True) -> int:
    """Print the screen. With ``full`` off, print only the lines that differ from the screen printed last."""
    count = len(session["actions"])
    game, problem = replay(folder, session)
    print(f"SESSION: {folder}    actions so far: {count}    last action: {session['actions'][-1] if count else '(none)'}")
    view = game.describe(folder / "shots" / f"{count:04d}.png")
    game.ctrl.close()
    last = folder / "last_view.txt"
    before = last.read_text(encoding="utf-8").splitlines() if last.exists() else []
    last.write_text(view, encoding="utf-8")
    now = view.splitlines()
    if full or not before:
        print(view)
    else:
        changes = [line for line in difflib.ndiff(before, now) if line[:2] in ("- ", "+ ") and "SCREENSHOT:" not in line]
        print(now[0])
        if changes:
            print("\nWHAT CHANGED ON THE SCREEN ('-' is gone, '+' is new; `look` prints the whole screen):")
            print("\n".join(changes))
        else:
            print("\nNOTHING CHANGED ON THE SCREEN.")
        print("\n" + now[-1])
    if problem:
        print(f"\nPROBLEM WITH AN ACTION: {problem}")
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play Battle Dice step by step without a window (for playtesting).",
                                     epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", required=True, type=Path, help="folder that holds this playtest session")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="begin a session at the main menu")
    start.add_argument("--size", default="1280x720", help="window size, for example 960x540")
    start.add_argument("--seed", type=int, default=500, help="seed of the first run; each further run takes the next number")
    start.add_argument("--fixed-seed", type=int, default=None, help="like the game's --seed flag: every run uses this seed")
    start.add_argument("--feature", action="append", default=[], help="a launch flag feature, for example class_evolution_v1")
    do = commands.add_parser("do", help="apply actions, then show what changed on the screen")
    do.add_argument("actions", nargs="+")
    do.add_argument("--full", action="store_true", help="print the whole screen, not only what changed")
    commands.add_parser("look", help="show the screen")
    undo = commands.add_parser("undo", help="take back the last action(s)")
    undo.add_argument("count", nargs="?", type=int, default=1)
    commands.add_parser("log", help="list the actions of the session")
    args = parser.parse_args(argv)
    folder: Path = args.session.resolve()

    try:
        if args.command == "start":
            session = {"size": args.size, "seed": args.seed, "fixed_seed": args.fixed_seed, "features": args.feature, "actions": []}
            shutil.rmtree(folder / "shots", ignore_errors=True)
            save(folder, session)
            return show(folder, session)
        session = load(folder)
        if args.command == "log":
            for number, action in enumerate(session["actions"], start=1):
                print(f"{number:4}  {action}")
            return 0
        if args.command == "do":
            before = len(session["actions"])
            session["actions"] += args.actions
            game, problem = replay(folder, session)
            game.ctrl.close()
            if problem:  # an action that cannot be carried out is not kept, so the session stays usable
                session["actions"] = session["actions"][:before]
                print(f"NOT DONE, the session is unchanged. {problem}\n")
                show(folder, session)
                return 2
            save(folder, session)
        elif args.command == "undo":
            session["actions"] = session["actions"][: max(0, len(session["actions"]) - args.count)]
            save(folder, session)
        return show(folder, session, full=args.command != "do" or args.full)
    except BrokenPipeError:  # the reader (for example `| head`) stopped listening: not the game's fault
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115 - keeps the interpreter from complaining again while it exits
        return 0
    except Exception:  # noqa: BLE001 - a crash of the game is a finding; it must be shown, not lost
        print("THE GAME RAISED AN ERROR OUTSIDE ITS OWN ERROR HANDLING. This is a defect; report it with the action list.\n")
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(main())
