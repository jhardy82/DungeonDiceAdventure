"""Battle Dice on Android: the walking skeleton (owner decision D-33, phase 0 of docs/android/PLAN.md).

Flet draws what ``battle_dice.phone.screens`` describes and sends taps back to it. No rule and no text
of the game is decided here. On start the app runs the screen-free self-check once and prints its
report, which the build workflow reads from the device log.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

import flet as ft

from battle_dice.app import selfcheck
from battle_dice.app.controller import AppController
from battle_dice.phone import screens as phone

TONES = {"hero": "#5b8def", "enemy": "#e0705a", "die": "#f2c14e", "plain": "#3b4460"}
#: Android's guideline for a control a finger can hit: 48 dp.
TOUCH = 48


def storage() -> Path:
    """Where the app may keep files: its own data folder on a phone, a temporary one elsewhere."""
    given = os.environ.get("FLET_APP_STORAGE_DATA")
    return Path(given) if given else Path(tempfile.mkdtemp(prefix="battle_dice_"))


def self_check_report(folder: Path) -> str:
    """One line for the device log and the menu: what the self-check found, or why it failed."""
    started = time.monotonic()
    try:
        result = selfcheck.run(folder / "selfcheck")
        line = selfcheck.report_line(result) + f" seconds={time.monotonic() - started:.1f} platform={sys.platform}"
    except Exception:  # noqa: BLE001 - whatever went wrong belongs in the report, not in a crash
        line = "BATTLE DICE SELF-CHECK FAILED: " + traceback.format_exc().strip().splitlines()[-1]
        print(traceback.format_exc(), flush=True)
    print(line, flush=True)
    return line


def main(page: ft.Page) -> None:
    page.title = "Battle Dice"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    folder = storage()
    controller = AppController(log_dir=folder / "logs")
    report = {"line": "Self-check running ..."}

    def tap(action_id: str):
        def handler(_event) -> None:
            phone.act(controller, action_id)
            draw()
        return handler

    def button(action: dict, expand: bool = False) -> ft.Control:
        label = action["label"] if action["enabled"] else f"{action['label']} ({action['reason']})"
        kind = ft.FilledButton if action["primary"] else ft.OutlinedButton
        return kind(content=ft.Text(label, size=16, text_align=ft.TextAlign.CENTER), height=None, expand=expand, disabled=not action["enabled"],
                    on_click=tap(action["id"]), style=ft.ButtonStyle(padding=ft.Padding.symmetric(horizontal=12, vertical=14)))

    def card(entry: dict) -> ft.Control:
        rows: list[ft.Control] = []
        if entry["title"]:
            rows.append(ft.Text(entry["title"], size=16, weight=ft.FontWeight.BOLD))
        rows += [ft.Text(line, size=14) for line in entry["lines"]]
        taps = [entry[key] for key in ("tap", "extra") if entry.get(key)]
        if taps:
            rows.append(ft.Row(spacing=8, controls=[button({**action, "primary": action is taps[0]}, expand=True) for action in taps]))
        return ft.Container(padding=10, border_radius=8, bgcolor="#1c2030", border=ft.Border.all(1, TONES.get(entry["tone"], TONES["plain"])),
                            content=ft.Column(spacing=4, tight=True, controls=rows), col={"xs": 12, "sm": 6, "md": 4})

    def draw() -> None:
        view = phone.screen(controller)
        wide = (page.width or 0) > (page.height or 0)  # sideways: what is shown left, what can be done right
        shown: list[ft.Control] = [ft.Text(view["title"], size=22, weight=ft.FontWeight.BOLD, color="#f2c14e")]
        if view["message"]:
            shown.append(ft.Text(view["message"], size=15, color="#f08a70" if view["is_error"] else "#d7dbe6"))
        for group in view["groups"]:
            shown.append(ft.Text(group["title"], size=14, weight=ft.FontWeight.BOLD, color=TONES.get(group["tone"], "#aab1c5")))
            shown.append(ft.ResponsiveRow(spacing=8, run_spacing=8, controls=[card(entry) for entry in group["cards"]]))
        doing: list[ft.Control] = [button(action) for action in view["actions"]]
        if view["screen"] == "menu":
            doing.append(ft.Text(report["line"], size=12, color="#8a8f9c", selectable=True))
        log: list[ft.Control] = [ft.Text(line, size=12, color="#8a8f9c") for line in view.get("log", [])]
        # Upright: what is shown, what can be done, then the log. Sideways: the buttons have the right-hand side.
        left = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=3, controls=[*shown, *log])
        right = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=2, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=doing)
        body = ft.Row(spacing=12, expand=True, vertical_alignment=ft.CrossAxisAlignment.START, controls=[left, right]) if wide else \
            ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, controls=[*shown, *doing, *log])
        page.controls.clear()
        page.add(ft.SafeArea(expand=True, content=ft.Container(padding=12, expand=True, content=body)))
        page.update()

    def resized(_event) -> None:
        draw()

    async def check() -> None:
        report["line"] = await asyncio.to_thread(self_check_report, folder)
        draw()

    page.on_resize = resized
    draw()
    page.run_task(check)


if __name__ == "__main__":
    ft.run(main)
