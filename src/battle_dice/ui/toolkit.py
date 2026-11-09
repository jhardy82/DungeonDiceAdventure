"""A small immediate-mode UI toolkit on pygame-ce: scaling, text, panels, buttons, focus and hotkeys.

Every screen is rebuilt each frame from a state snapshot. Widgets registered during a frame are
used to route the next input events, so mouse and keyboard always act on what is visible.
Layout is authored for a 1280x720 logical canvas and scaled uniformly (letterboxed) to the
window, down to the minimum supported 960x540.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pygame

LOGICAL_W, LOGICAL_H = 1280, 720
MIN_W, MIN_H = 960, 540
FONT_CANDIDATES = ("segoeui", "arial", "liberationsans", "dejavusans", "helvetica", "freesans")


class Theme:
    BG = (18, 20, 26)
    PANEL = (30, 34, 44)
    PANEL_ALT = (38, 43, 56)
    BORDER = (70, 78, 98)
    TEXT = (232, 235, 241)
    DIM = (150, 158, 176)
    FAINT = (104, 112, 130)
    ACCENT = (242, 193, 78)
    HERO = (96, 168, 230)
    ENEMY = (232, 116, 97)
    GOOD = (112, 207, 127)
    BAD = (240, 110, 110)
    WARN = (240, 160, 96)
    SHIELD = (150, 190, 235)
    MANA = (120, 150, 245)
    CORRUPT = (190, 120, 220)
    GAUGE = (210, 200, 120)
    BUTTON = (52, 60, 80)
    BUTTON_HOVER = (68, 78, 104)
    BUTTON_SELECTED = (88, 80, 44)
    BUTTON_DISABLED = (36, 39, 48)
    FOCUS = (255, 255, 255)


@dataclass
class Widget:
    key: str
    rect: pygame.Rect
    action: Callable[[], Any] | None
    enabled: bool
    reason: str | None
    tooltip: str | None
    hotkeys: tuple[int, ...]
    default: bool = False


class UI:
    def __init__(self) -> None:
        self.widgets: list[Widget] = []
        self._building: list[Widget] = []
        self.focus_key: str | None = None
        self.hover_key: str | None = None
        self.mouse_pos = (-1, -1)
        self.scale = 1.0
        self.offset = (0, 0)
        self.surface: pygame.Surface | None = None
        self._fonts: dict[tuple[int, bool], pygame.font.Font] = {}
        self._font_paths: dict[bool, str | None] = {}
        self.on_disabled: Callable[[str], None] | None = None
        self.escape_action: Callable[[], Any] | None = None

    # -- frame lifecycle ---------------------------------------------------------------------

    def begin(self, surface: pygame.Surface) -> None:
        self.surface = surface
        width, height = surface.get_size()
        self.scale = min(width / LOGICAL_W, height / LOGICAL_H)
        self.offset = (int((width - LOGICAL_W * self.scale) / 2), int((height - LOGICAL_H * self.scale) / 2))
        self._building = []
        self.escape_action = None
        surface.fill(Theme.BG)

    def end(self) -> None:
        self.widgets = self._building
        keys = {w.key for w in self.widgets}
        if self.focus_key not in keys:
            self.focus_key = None
        self.hover_key = None
        for widget in self.widgets:
            if widget.rect.collidepoint(self.mouse_pos):
                self.hover_key = widget.key

    # -- geometry and text -------------------------------------------------------------------

    def px(self, value: float) -> int:
        return max(1, int(round(value * self.scale)))

    def r(self, x: float, y: float, w: float, h: float) -> pygame.Rect:
        return pygame.Rect(
            self.offset[0] + int(round(x * self.scale)),
            self.offset[1] + int(round(y * self.scale)),
            max(1, int(round(w * self.scale))),
            max(1, int(round(h * self.scale))),
        )

    def _font_path(self, bold: bool) -> str | None:
        """A regular-weight system sans-serif when one exists; pygame's bundled font otherwise."""
        if bold not in self._font_paths:
            path = None
            for name in FONT_CANDIDATES:
                path = pygame.font.match_font(name, bold=bold)
                if path:
                    break
            self._font_paths[bold] = path
        return self._font_paths[bold]

    def font(self, size: int, bold: bool = False) -> pygame.font.Font:
        pixels = max(9, int(round(size * self.scale)))
        key = (pixels, bold)
        if key not in self._fonts:
            path = self._font_path(bold)
            try:
                font = pygame.font.Font(path, pixels) if path else pygame.font.Font(None, int(pixels * 1.3))
            except (OSError, pygame.error):
                font = pygame.font.Font(None, int(pixels * 1.3))
            self._fonts[key] = font
        return self._fonts[key]

    def fit(self, text: str, font: pygame.font.Font, max_pixels: int) -> str:
        if font.size(text)[0] <= max_pixels:
            return text
        ellipsis = "..."
        low, high = 0, len(text)
        while low < high:
            mid = (low + high + 1) // 2
            if font.size(text[:mid] + ellipsis)[0] <= max_pixels:
                low = mid
            else:
                high = mid - 1
        return text[:low] + ellipsis

    def text(
        self, x: float, y: float, text: str, size: int = 16, color: tuple[int, int, int] = Theme.TEXT,
        bold: bool = False, max_width: float | None = None, align: str = "left",
    ) -> None:
        assert self.surface is not None
        font = self.font(size, bold)
        if max_width is not None:
            text = self.fit(text, font, self.px(max_width))
        image = font.render(text, True, color)
        rect = self.r(x, y, 1, 1)
        if align == "center":
            pos = (rect.x - image.get_width() // 2, rect.y)
        elif align == "right":
            pos = (rect.x - image.get_width(), rect.y)
        else:
            pos = (rect.x, rect.y)
        self.surface.blit(image, pos)

    def wrap_lines(self, text: str, width: float, size: int = 16, bold: bool = False) -> list[str]:
        font = self.font(size, bold)
        limit = self.px(width)
        lines: list[str] = []
        for paragraph in text.split("\n"):
            current = ""
            for word in paragraph.split(" "):
                candidate = word if not current else f"{current} {word}"
                if font.size(candidate)[0] <= limit or not current:
                    current = candidate
                else:
                    lines.append(current)
                    current = word
            lines.append(current)
        return lines

    def paragraph(
        self, x: float, y: float, text: str, width: float, size: int = 16, color: tuple[int, int, int] = Theme.TEXT,
        line_height: float | None = None, max_lines: int | None = None, bold: bool = False,
    ) -> float:
        """Draw wrapped text. Returns the logical y just below the last line."""
        step = line_height or size * 1.3
        lines = self.wrap_lines(text, width, size, bold)
        if max_lines is not None and len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1] + " ..."
        for line in lines:
            self.text(x, y, line, size, color, bold, max_width=width)
            y += step
        return y

    # -- primitives --------------------------------------------------------------------------

    def panel(
        self, x: float, y: float, w: float, h: float, title: str | None = None,
        fill: tuple[int, int, int] = Theme.PANEL, border: tuple[int, int, int] = Theme.BORDER, width: int = 1,
    ) -> None:
        assert self.surface is not None
        rect = self.r(x, y, w, h)
        pygame.draw.rect(self.surface, fill, rect, border_radius=self.px(5))
        pygame.draw.rect(self.surface, border, rect, self.px(width), border_radius=self.px(5))
        if title:
            self.text(x + 8, y + 5, title, 15, Theme.DIM, bold=True, max_width=w - 16)

    def bar(
        self, x: float, y: float, w: float, h: float, value: int, maximum: int,
        color: tuple[int, int, int], back: tuple[int, int, int] = (20, 22, 28),
    ) -> None:
        assert self.surface is not None
        rect = self.r(x, y, w, h)
        pygame.draw.rect(self.surface, back, rect)
        if maximum > 0 and value > 0:
            fill = rect.copy()
            fill.width = max(1, int(rect.width * min(1.0, value / maximum)))
            pygame.draw.rect(self.surface, color, fill)
        pygame.draw.rect(self.surface, Theme.BORDER, rect, 1)

    def line(self, x1: float, y1: float, x2: float, y2: float, color: tuple[int, int, int] = Theme.BORDER) -> None:
        assert self.surface is not None
        a, b = self.r(x1, y1, 1, 1), self.r(x2, y2, 1, 1)
        pygame.draw.line(self.surface, color, a.topleft, b.topleft, 1)

    # -- widgets -----------------------------------------------------------------------------

    def register(
        self, key: str, rect: pygame.Rect, action: Callable[[], Any] | None, enabled: bool = True,
        reason: str | None = None, tooltip: str | None = None, hotkeys: tuple[int, ...] = (), default: bool = False,
    ) -> Widget:
        widget = Widget(key, rect, action, enabled, reason, tooltip, hotkeys, default)
        self._building.append(widget)
        return widget

    def is_focused(self, key: str) -> bool:
        return self.focus_key == key

    def is_hot(self, key: str) -> bool:
        return self.focus_key == key or self.hover_key == key

    def decorate(self, key: str, rect: pygame.Rect, enabled: bool) -> None:
        """Focus ring and disabled hatch. Both are shape cues, so state never relies on color alone."""
        assert self.surface is not None
        if not enabled:
            step = self.px(9)
            clip = self.surface.get_clip()
            self.surface.set_clip(rect)
            for offset in range(-rect.height, rect.width, step):
                pygame.draw.line(
                    self.surface, (58, 62, 74), (rect.x + offset, rect.bottom), (rect.x + offset + rect.height, rect.y), 1
                )
            self.surface.set_clip(clip)
        if self.focus_key == key:
            ring = rect.inflate(self.px(6), self.px(6))
            pygame.draw.rect(self.surface, Theme.FOCUS, ring, self.px(2), border_radius=self.px(6))
            tip = ring.midleft
            size = self.px(6)
            pygame.draw.polygon(
                self.surface, Theme.FOCUS, [(tip[0] - size, tip[1] - size), (tip[0], tip[1]), (tip[0] - size, tip[1] + size)]
            )

    def button(
        self, key: str, x: float, y: float, w: float, h: float, label: str, action: Callable[[], Any] | None,
        enabled: bool = True, reason: str | None = None, tooltip: str | None = None,
        hotkeys: tuple[int, ...] = (), selected: bool = False, default: bool = False, size: int = 16,
        sublabel: str | None = None,
    ) -> Widget:
        assert self.surface is not None
        rect = self.r(x, y, w, h)
        widget = self.register(key, rect, action, enabled, reason, tooltip, hotkeys, default)
        if not enabled:
            fill, text_color = Theme.BUTTON_DISABLED, Theme.FAINT
        elif selected:
            fill, text_color = Theme.BUTTON_SELECTED, Theme.ACCENT
        elif self.hover_key == key:
            fill, text_color = Theme.BUTTON_HOVER, Theme.TEXT
        else:
            fill, text_color = Theme.BUTTON, Theme.TEXT
        pygame.draw.rect(self.surface, fill, rect, border_radius=self.px(5))
        border = Theme.ACCENT if selected else Theme.BORDER
        pygame.draw.rect(self.surface, border, rect, self.px(2 if selected else 1), border_radius=self.px(5))
        self.decorate(key, rect, enabled)
        if sublabel:
            self.text(x + w / 2, y + h / 2 - size * 0.95, label, size, text_color, bold=True, max_width=w - 10, align="center")
            self.text(x + w / 2, y + h / 2 + 2, sublabel, max(13, size - 3), Theme.DIM if enabled else Theme.FAINT,
                      max_width=w - 10, align="center")
        else:
            self.text(x + w / 2, y + h / 2 - size * 0.48, label, size, text_color, bold=True, max_width=w - 10, align="center")
        return widget

    def widget(self, key: str) -> Widget | None:
        for widget in self.widgets:
            if widget.key == key:
                return widget
        return None

    def keys(self, prefix: str = "") -> list[str]:
        return [w.key for w in self.widgets if w.key.startswith(prefix)]

    # -- input -------------------------------------------------------------------------------

    def activate(self, widget: Widget) -> None:
        self.focus_key = widget.key
        if not widget.enabled:
            if self.on_disabled is not None:
                self.on_disabled(widget.reason or "That is not available right now.")
            return
        if widget.action is not None:
            widget.action()

    def move_focus(self, step: int) -> None:
        if not self.widgets:
            return
        keys = [w.key for w in self.widgets]
        if self.focus_key in keys:
            index = (keys.index(self.focus_key) + step) % len(keys)
        else:
            index = 0 if step > 0 else len(keys) - 1
        self.focus_key = keys[index]

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Route one event to the widgets from the last drawn frame. Returns True when consumed."""
        if event.type == pygame.MOUSEMOTION:
            self.mouse_pos = event.pos
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.mouse_pos = event.pos
            for widget in reversed(self.widgets):
                if widget.rect.collidepoint(event.pos):
                    self.activate(widget)
                    return True
            return False
        if event.type != pygame.KEYDOWN:
            return False
        key = event.key
        shift = bool(getattr(event, "mod", 0) & pygame.KMOD_SHIFT)
        if key == pygame.K_TAB:
            self.move_focus(-1 if shift else 1)
            return True
        if key in (pygame.K_DOWN, pygame.K_RIGHT):
            self.move_focus(1)
            return True
        if key in (pygame.K_UP, pygame.K_LEFT):
            self.move_focus(-1)
            return True
        if key == pygame.K_ESCAPE and self.escape_action is not None:
            self.escape_action()
            return True
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            focused = self.widget(self.focus_key) if self.focus_key else None
            if focused is not None:
                self.activate(focused)
                return True
            if key != pygame.K_SPACE:
                for widget in self.widgets:
                    if widget.default:
                        self.activate(widget)
                        return True
            return False
        for widget in self.widgets:
            if key in widget.hotkeys:
                self.activate(widget)
                return True
        return False

    def status_text(self) -> tuple[str, bool] | None:
        """Help or disabled-reason text for the focused/hovered widget."""
        for key in (self.hover_key, self.focus_key):
            widget = self.widget(key) if key else None
            if widget is None:
                continue
            if not widget.enabled and widget.reason:
                return f"Unavailable: {widget.reason}", True
            if widget.tooltip:
                return widget.tooltip, False
        return None
