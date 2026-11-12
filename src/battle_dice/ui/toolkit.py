"""A small immediate-mode UI toolkit on pygame-ce: scaling, text, panels, buttons, focus and hotkeys.

Every screen is rebuilt each frame from a state snapshot. Widgets registered during a frame are
used to route the next input events, so mouse and keyboard always act on what is visible.
Layout is authored for a 1280x720 logical canvas and scaled uniformly (letterboxed) to the
window, down to the minimum supported 960x540.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pygame

from battle_dice.ui.animation import Animator
from battle_dice.ui.artwork import PLACEHOLDER_COLOUR, AssetStore

LOGICAL_W, LOGICAL_H = 1280, 720
MIN_W, MIN_H = 960, 540
#: At a larger text size, two texts side by side keep this many logical units between them: about the width of a space.
TEXT_CLEARANCE = 5
FONT_CANDIDATES = ("segoeui", "arial", "liberationsans", "dejavusans", "helvetica", "freesans")
KEYPAD_DIGITS = {
    pygame.K_KP1: pygame.K_1, pygame.K_KP2: pygame.K_2, pygame.K_KP3: pygame.K_3, pygame.K_KP4: pygame.K_4,
    pygame.K_KP5: pygame.K_5, pygame.K_KP6: pygame.K_6, pygame.K_KP7: pygame.K_7, pygame.K_KP8: pygame.K_8,
    pygame.K_KP9: pygame.K_9,
}


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
    #: Darker fills: an inset panel, the card of a downed unit, the top and status bars.
    PANEL_DEEP = (24, 27, 35)
    PANEL_DOWN = (26, 26, 30)
    BAR = (12, 13, 18)
    #: The name of the palette in use: "normal" or "high_contrast".
    NAME = "normal"


#: The colours of ``Theme`` as shipped, kept so the normal palette can be put back.
NORMAL_PALETTE = {name: value for name, value in vars(Theme).items() if name.isupper() and isinstance(value, tuple)}
#: High contrast (owner decision D-31; Xbox Accessibility Guideline 102 asks for 7:1): every text colour is at
#: least 7:1 against every surface it is drawn on, surfaces are black or near black, borders are bright.
HIGH_CONTRAST_PALETTE = {
    **NORMAL_PALETTE,
    "BG": (0, 0, 0), "PANEL": (0, 0, 0), "PANEL_ALT": (12, 12, 12), "PANEL_DEEP": (0, 0, 0), "PANEL_DOWN": (0, 0, 0), "BAR": (0, 0, 0),
    "BORDER": (200, 200, 200), "TEXT": (255, 255, 255), "DIM": (225, 225, 225), "FAINT": (195, 195, 195),
    "ACCENT": (255, 215, 90), "HERO": (130, 190, 255), "ENEMY": (255, 150, 130), "GOOD": (130, 230, 145), "BAD": (255, 150, 150),
    "WARN": (255, 180, 110), "SHIELD": (170, 205, 245), "MANA": (160, 180, 255), "CORRUPT": (220, 160, 245), "GAUGE": (225, 215, 130),
    "BUTTON": (0, 0, 48), "BUTTON_HOVER": (0, 0, 84), "BUTTON_SELECTED": (60, 46, 0), "BUTTON_DISABLED": (22, 22, 22),
}
PALETTES = {"normal": NORMAL_PALETTE, "high_contrast": HIGH_CONTRAST_PALETTE}


def apply_theme(name: str) -> None:
    """Switch every colour of ``Theme``. Screens read ``Theme`` when they draw, so the next frame is in the new palette."""
    for colour, value in PALETTES[name].items():
        setattr(Theme, colour, value)
    Theme.NAME = name


def contrast_ratio(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    """The WCAG contrast ratio of two colours, 1 (none) to 21 (black on white)."""
    def luminance(colour: tuple[int, int, int]) -> float:
        parts = []
        for channel in colour:
            c = channel / 255
            parts.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]

    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


@dataclass(frozen=True)
class DrawnText:
    """One text as it reached the screen."""

    text: str            # as asked for
    shown: str           # as drawn: shorter when it had to be cut
    ink: pygame.Rect     # the pixels that carry ink, in window coordinates
    pixels: int          # the font size it was drawn in
    normal_pixels: int   # the font size it has at the normal text size


@dataclass(frozen=True)
class _Measured:
    """A text of the frame being measured: where its ink is at the normal size, and where it would be if it grew."""

    text: str
    normal: pygame.Rect
    large: pygame.Rect
    normal_pixels: int
    wanted: int          # the size it would grow to; the normal one when it cannot grow
    group: int | None    # texts of one group grow together or not at all


@dataclass
class Trace:
    """What one frame drew, for the layout check: ``UI.trace`` is ``None`` in play, so nothing is kept."""

    texts: list[DrawnText] = field(default_factory=list)
    boxes: list[pygame.Rect] = field(default_factory=list)    # panels and buttons: what a text sits in
    sprites: list[pygame.Rect] = field(default_factory=list)  # pictures and bars: what a text must stay clear of


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
        #: How long the pointer has rested on the hovered control, and how long it must before its help shows.
        self.hover_ms = 0.0
        self.tooltip_delay_ms = 0
        self._hover_timed: str | None = None
        self.mouse_pos = (-1, -1)
        self.scale = 1.0
        self.offset = (0, 0)
        self.surface: pygame.Surface | None = None
        #: Text size: 1.0 is the size the layout was drawn for. A larger text is used only where it still fits (plan_sizes).
        self.text_scale = 1.0
        #: The layout check sets this and reads every text, box and picture of a frame from it.
        self.trace: Trace | None = None
        self._measuring = False
        self._measured: list[_Measured] = []
        self._boxes: list[pygame.Rect] = []
        self._sprites: list[pygame.Rect] = []
        self._plan: list[tuple[str, int]] | None = None
        self._cursor = 0
        self._group: int | None = None
        self._group_serial = 0
        self._inks: dict[tuple[str, int, bool], tuple[int, pygame.Rect]] = {}
        self._fonts: dict[tuple[int, bool], pygame.font.Font] = {}
        self._font_paths: dict[bool, str | None] = {}
        self.on_disabled: Callable[[str], None] | None = None
        self.escape_action: Callable[[], Any] | None = None
        self.assets = AssetStore()
        self.anim = Animator()
        self._backdrops: dict[tuple[int, int, int], pygame.Surface] = {}
        # Status bar: a fresh controller message stays visible until the pointer or focus moves on.
        self.message_serial = -1
        self.message_pin: tuple[str | None, str | None] | None = None

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
        if self.hover_key != self._hover_timed:  # the pointer reached another control: its rest starts now
            self._hover_timed, self.hover_ms = self.hover_key, 0.0

    def tick(self, dt_ms: float) -> None:
        """Time passes: the pointer has rested that much longer on the control under it."""
        self.hover_ms += max(0.0, dt_ms)

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
        """The font of a text at the normal text size. Every measurement a screen makes uses this one."""
        return self._font_of(self._pixels(size), bold)

    def _pixels(self, size: float) -> int:
        return max(9, int(round(size * self.scale)))

    def _sizes(self, size: float) -> list[int]:
        """The font sizes a text may be drawn in, largest first; the last one is its normal size."""
        normal = self._pixels(size)
        largest = max(normal, int(round(size * self.scale * self.text_scale)))
        return list(range(largest, normal - 1, -1))

    def _font_of(self, pixels: int, bold: bool) -> pygame.font.Font:
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

    def text_width(self, text: str, size: int = 16, bold: bool = False) -> float:
        """Width of ``text`` in logical units at the current scale."""
        return self.font(size, bold).size(text)[0] / self.scale

    def fit_name(self, text: str, size: int, bold: bool, max_width: float) -> str:
        """Shorten a name but keep a trailing number, so "Goblin Skirmisher 2" never loses its 2."""
        font = self.font(size, bold)
        limit = self.px(max_width)
        if font.size(text)[0] <= limit:
            return text
        head, _, tail = text.rpartition(" ")
        if head and tail.isdigit():
            room = limit - font.size(" " + tail)[0]
            return f"{self.fit(head, font, max(1, room))} {tail}"
        return self.fit(text, font, limit)

    def text(
        self, x: float, y: float, text: str, size: int = 16, color: tuple[int, int, int] | None = None,
        bold: bool = False, max_width: float | None = None, align: str = "left", grow: str = "middle",
    ) -> None:
        """Draw one line. ``max_width`` cuts a text that is too long.

        At a larger text size the line is drawn larger only where the whole of it fits and the frame has room for it
        (see ``plan_sizes``). It grows around its middle, or ``up`` or ``down`` when a neighbour sits right below or
        above; ``none`` keeps the normal size.
        """
        normal = self._pixels(size)
        if self.text_scale <= 1.0:
            self._draw_text(x, y, text, size, normal, color, bold, max_width, align, grow)
            return
        if self._measuring:
            # A larger text must not cost a word: the largest size at which the whole text fits, else the normal one.
            # A text that keeps its size is measured too: its neighbours must stay clear of it.
            sizes = self._sizes(size) if grow != "none" else [normal]
            wanted = sizes[0]
            if max_width is not None:
                limit = self.px(max_width)
                wanted = next((p for p in sizes if self._font_of(p, bold).size(text)[0] <= limit), normal)
            self._measure(x, y, text, text, size, wanted, bold, max_width, align, grow)
            return
        self._draw_text(x, y, text, size, self._planned(text, normal), color, bold, max_width, align, grow)

    def _ink(self, text: str, pixels: int, bold: bool) -> tuple[int, pygame.Rect]:
        """Width of a rendered text and the part of it that carries ink. Remembered: measuring happens every frame."""
        key = (text, pixels, bold)
        found = self._inks.get(key)
        if found is None:
            if len(self._inks) > 4000:
                self._inks.clear()
            image = self._font_of(pixels, bold).render(text, True, (255, 255, 255))
            found = self._inks[key] = (image.get_width(), image.get_bounding_rect())
        return found

    def _origin(self, x: float, y: float, width: int, size: float, pixels: int, bold: bool, align: str, grow: str) -> tuple[int, int]:
        """Where a rendered line is put: by its alignment, and by the side it grows to when it is larger than normal."""
        rect = self.r(x, y, 1, 1)
        # A larger text grows around the middle of its line, half upwards, so stacked lines keep their distance.
        # Where a neighbour sits right below or above, the caller lets it grow to the other side only.
        normal_pixels = self._pixels(size)
        top = rect.y
        if pixels != normal_pixels:
            growth = self._font_of(pixels, bold).get_height() - self._font_of(normal_pixels, bold).get_height()
            top -= {"middle": growth // 2, "up": growth, "down": 0, "none": 0}[grow]
        left = rect.x - width // 2 if align == "center" else rect.x - width if align == "right" else rect.x
        return left, top

    def _draw_text(
        self, x: float, y: float, text: str, size: float, pixels: int, color: tuple[int, int, int] | None,
        bold: bool, max_width: float | None, align: str = "left", grow: str = "middle",
    ) -> None:
        assert self.surface is not None
        color = color or Theme.TEXT  # read when drawn: a default written in the signature would be the palette at start
        font = self._font_of(pixels, bold)
        shown = self.fit(text, font, self.px(max_width)) if max_width is not None else text
        image = font.render(shown, True, color)
        pos = self._origin(x, y, image.get_width(), size, pixels, bold, align, grow)
        self.surface.blit(image, pos)
        if self.trace is not None and shown.strip():
            self.trace.texts.append(DrawnText(text, shown, image.get_bounding_rect().move(pos), pixels, self._pixels(size)))

    # -- a larger text size: every frame is measured first -----------------------------------

    def plan_sizes(self, draw: Callable[[], object]) -> None:
        """Measure a frame before it is drawn, and decide which of its texts may be drawn larger.

        The layout is fixed, so a larger text cannot push its neighbours away. ``draw`` is run once without drawing
        any text; then every text is given the larger size only if, at that size, it stays inside the panel or button
        it sits in, stays clear of the pictures and bars, and keeps its distance from every other text. Texts are asked in the
        order they are drawn, so the first of two neighbours grows. A group (``group``) grows whole or not at all.
        The caller then starts the frame again and draws it; ``text`` and ``paragraph`` follow the plan.
        """
        self._plan = None
        if self.text_scale <= 1.0:
            return
        self._measured, self._boxes, self._sprites, self._measuring = [], [], [], True
        try:
            draw()
        except Exception:  # noqa: BLE001 - a fault while measuring: nothing grows; drawing raises it again where it is handled
            return
        finally:
            self._measuring = False
        self._plan = self._solve()
        self._cursor = 0

    @contextmanager
    def group(self) -> Iterator[None]:
        """Texts drawn inside grow together or not at all: a row of labels never mixes two sizes."""
        outer, self._group_serial = self._group, self._group_serial + 1
        self._group = self._group_serial
        try:
            yield
        finally:
            self._group = outer

    def _measure(
        self, x: float, y: float, text: str, large_text: str, size: float, wanted: int, bold: bool,
        max_width: float | None, align: str, grow: str, group: int | None = None,
    ) -> None:
        """Record where a text's ink is at the normal size and where it would be at the size it wants."""
        normal_pixels = self._pixels(size)
        rects = []
        for words, pixels in ((text, normal_pixels), (large_text, wanted)):
            shown = self.fit(words, self._font_of(pixels, bold), self.px(max_width)) if max_width is not None else words
            width, ink = self._ink(shown, pixels, bold)
            rects.append(ink.move(self._origin(x, y, width, size, pixels, bold, align, grow)))
        self._measured.append(_Measured(text, rects[0], rects[1], normal_pixels, wanted, group if group is not None else self._group))

    def _planned(self, text: str, normal: int) -> int:
        """The size the plan gives the next text. A frame that differs from the measured one is drawn at the normal size."""
        plan, cursor = self._plan, self._cursor
        self._cursor += 1
        if plan is None or cursor >= len(plan) or plan[cursor][0] != text:
            self._plan = None
            return normal
        return plan[cursor][1]

    def _solve(self) -> list[tuple[str, int]]:
        assert self.surface is not None
        items = self._measured
        boxes = [*self._boxes, self.surface.get_rect()]
        near = 2 * self.px(TEXT_CLEARANCE)
        occupied = [item.normal for item in items]  # where each text is, as far as decided: normal until it grows
        grown = [False] * len(items)
        groups: dict[int, list[int]] = {}
        for index, item in enumerate(items):
            if item.group is not None:
                groups.setdefault(item.group, []).append(index)

        def apart(first: pygame.Rect, second: pygame.Rect, first_normal: pygame.Rect, second_normal: pygame.Rect) -> bool:
            """Two texts keep their distance; two that were already close do not start to overlap; an overlap may stay."""
            if not first.inflate(near, 0).colliderect(second):
                return True
            if not first_normal.inflate(near, 0).colliderect(second_normal):
                return False
            return first_normal.colliderect(second_normal) or not first.colliderect(second)

        def fits(index: int, members: list[int]) -> bool:
            item = items[index]
            if item.wanted <= item.normal_pixels:
                return False
            homes = [box for box in boxes if box.contains(item.normal)]
            if homes and not min(homes, key=lambda box: box.w * box.h).contains(item.large):
                return False
            if any(item.large.colliderect(sprite) and not item.normal.colliderect(sprite) for sprite in self._sprites):
                return False
            for other in item.large.inflate(near, 0).collidelistall(occupied):
                if other != index and other not in members and not apart(item.large, occupied[other], item.normal, items[other].normal):
                    return False
            return all(apart(item.large, items[other].large, item.normal, items[other].normal) for other in members if other > index)

        decided: set[int] = set()
        for index, item in enumerate(items):
            if index in decided:
                continue
            members = groups[item.group] if item.group is not None else [index]
            decided.update(members)
            if all(fits(member, members) for member in members):
                for member in members:
                    grown[member], occupied[member] = True, items[member].large
        return [(item.text, item.wanted if grown[index] else item.normal_pixels) for index, item in enumerate(items)]

    def wrap_lines(self, text: str, width: float, size: int = 16, bold: bool = False) -> list[str]:
        """The lines of ``text`` at the normal text size."""
        return self._wrap(text, self.px(width), self.font(size, bold))

    @staticmethod
    def _wrap(text: str, limit: int, font: pygame.font.Font) -> list[str]:
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
        self, x: float, y: float, text: str, width: float, size: int = 16, color: tuple[int, int, int] | None = None,
        line_height: float | None = None, max_lines: int | None = None, bold: bool = False,
    ) -> float:
        """Draw wrapped text. Returns the logical y just below the last line."""
        step = line_height or size * 1.3
        limit = self.px(width)

        def laid_out(pixels: int) -> tuple[list[str], bool]:
            """The lines at one font size, and whether every one of them is whole."""
            font = self._font_of(pixels, bold)
            lines = self._wrap(text, limit, font)
            if max_lines is not None and len(lines) > max_lines:
                lines = lines[:max_lines]
                lines[-1] = lines[-1] + " ..."
            return lines, all(font.size(line)[0] <= limit for line in lines)

        normal = self._pixels(size)
        lines, whole = laid_out(normal)
        pixels = normal
        if self.text_scale > 1.0:
            # The whole paragraph has one size: the largest that needs no more lines than the normal size and cuts no
            # line the normal size leaves whole. What follows a paragraph is placed for its normal height.
            larger, wanted = lines, normal
            for candidate in self._sizes(size)[:-1]:
                tried, tried_whole = laid_out(candidate)
                if len(tried) == len(lines) and (tried_whole or not whole):
                    larger, wanted = tried, candidate
                    break
            if self._measuring:
                self._group_serial += 1
                for row, (line, large_line) in enumerate(zip(lines, larger, strict=True)):
                    self._measure(x, y + row * step, line, large_line, size, wanted, bold, width, "left", "middle", self._group_serial)
                return y + len(lines) * step
            # The plan has one entry for each line, all of one size; a paragraph is larger only if the plan says so.
            sizes = [self._planned(line, normal) for line in lines]
            if sizes and all(planned == wanted for planned in sizes):
                lines, pixels = larger, wanted
        for line in lines:
            self._draw_text(x, y, line, size, pixels, color, bold, width)
            y += step
        return y

    # -- primitives --------------------------------------------------------------------------

    def panel(
        self, x: float, y: float, w: float, h: float, title: str | None = None,
        fill: tuple[int, int, int] | None = None, border: tuple[int, int, int] | None = None, width: int = 1,
    ) -> None:
        assert self.surface is not None
        fill, border = fill or Theme.PANEL, border or Theme.BORDER
        rect = self.r(x, y, w, h)
        if self._measuring:
            self._boxes.append(rect)
        elif self.trace is not None:
            self.trace.boxes.append(rect)
        pygame.draw.rect(self.surface, fill, rect, border_radius=self.px(5))
        pygame.draw.rect(self.surface, border, rect, self.px(width), border_radius=self.px(5))
        if title:
            self.text(x + 8, y + 5, title, 15, Theme.DIM, bold=True, max_width=w - 16)

    def bar(
        self, x: float, y: float, w: float, h: float, value: float, maximum: int,
        color: tuple[int, int, int], back: tuple[int, int, int] = (20, 22, 28),
    ) -> None:
        assert self.surface is not None
        rect = self.r(x, y, w, h)
        if self._measuring:
            self._sprites.append(rect)
        elif self.trace is not None:
            self.trace.sprites.append(rect)
        pygame.draw.rect(self.surface, back, rect)
        if maximum > 0 and value > 0:
            fill = rect.copy()
            fill.width = max(1, int(rect.width * min(1.0, value / maximum)))
            pygame.draw.rect(self.surface, color, fill)
        pygame.draw.rect(self.surface, Theme.BORDER, rect, 1)

    def line(self, x1: float, y1: float, x2: float, y2: float, color: tuple[int, int, int] | None = None) -> None:
        color = color or Theme.BORDER
        assert self.surface is not None
        a, b = self.r(x1, y1, 1, 1), self.r(x2, y2, 1, 1)
        pygame.draw.line(self.surface, color, a.topleft, b.topleft, 1)

    # -- pixel art ---------------------------------------------------------------------------

    def sprite(
        self, key: str | None, x: float, y: float, w: float, h: float, variant: str = "", alpha: int = 255,
    ) -> int:
        """Draw a sprite centred in a logical slot at the largest whole-number scale that fits.

        Returns the scale used (0 when ``key`` is None). A missing sprite draws a visible
        placeholder box and is recorded in ``assets.missing``; it never raises.
        """
        assert self.surface is not None
        if key is None:
            return 0
        slot = self.r(x, y, w, h)
        base = self.assets.base(key)
        if base is None:
            pygame.draw.rect(self.surface, PLACEHOLDER_COLOUR, slot, 1)
            return 0
        scale = self.assets.fit_scale(base.get_size(), slot.size)
        image = self.assets.scaled(key, scale, variant)
        assert image is not None
        if alpha < 255:
            image = image.copy()
            image.set_alpha(alpha)
        placed = image.get_rect(center=slot.center)
        self.surface.blit(image, placed)
        if self._measuring:
            self._sprites.append(placed)
        elif self.trace is not None:
            self.trace.sprites.append(placed)
        return scale

    def backdrop(self, x: float, y: float, w: float, h: float, wall_rows: int = 1, dim: int = 150) -> None:
        """Tiled dungeon floor behind a dark overlay, so text on top keeps its contrast."""
        assert self.surface is not None
        area = self.r(x, y, w, h)
        if Theme.NAME == "high_contrast":  # no picture behind the cards: plain black
            self.surface.fill(Theme.BG, area)
            return
        cache_key = (area.width, area.height, wall_rows)
        cached = self._backdrops.get(cache_key)
        if cached is None:
            cached = pygame.Surface(area.size)
            cached.fill(Theme.BG)
            layout = self.assets.manifest["backdrop"]
            tile = self.assets.tile_size
            scale = max(2, int(round(3 * self.scale)))
            step = tile * scale
            floors = layout["floor"]
            for row in range(area.height // step + 1):
                for col in range(area.width // step + 1):
                    if row < wall_rows:
                        key = layout["wall"]
                    else:
                        key = floors[(((col * 73856093) ^ (row * 19349663)) >> 3) % len(floors)]
                    image = self.assets.scaled(key, scale)
                    if image is not None:
                        cached.blit(image, (col * step, row * step))
            shade = pygame.Surface(area.size, pygame.SRCALPHA)
            shade.fill((14, 15, 20, dim))
            cached.blit(shade, (0, 0))
            if len(self._backdrops) > 12:
                self._backdrops.clear()
            self._backdrops[cache_key] = cached
        self.surface.blit(cached, area.topleft)

    def rect_of(self, key: str) -> pygame.Rect | None:
        """Screen rectangle of a widget registered in the frame being built (or the last frame)."""
        for widget in reversed(self._building):
            if widget.key == key:
                return widget.rect
        found = self.widget(key)
        return found.rect if found is not None else None

    def floating_text(self, rect: pygame.Rect, text: str, colour: tuple[int, int, int], progress: float, lane: int = 0) -> None:
        """A number or word that rises from a card and fades. Drawn in screen pixels."""
        assert self.surface is not None
        font = self.font(18, bold=True)
        rise = self.px(26) * progress + lane * self.px(16)
        alpha = 255 if progress < 0.6 else max(0, int(255 * (1 - (progress - 0.6) / 0.4)))
        image = font.render(text, True, colour)
        shadow = font.render(text, True, (10, 10, 14))
        x = rect.centerx - image.get_width() // 2
        y = rect.y + self.px(6) - int(rise)
        for surface, offset in ((shadow, (1, 1)), (image, (0, 0))):
            surface.set_alpha(alpha)
            self.surface.blit(surface, (x + offset[0], y + offset[1]))

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
        if self._measuring:
            self._boxes.append(rect)
        elif self.trace is not None:
            self.trace.boxes.append(rect)
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
            self.text(x + w / 2, y + h / 2 - size * 0.95, label, size, text_color, bold=True, max_width=w - 10, align="center",
                      grow="up")
            self.text(x + w / 2, y + h / 2 + 2, sublabel, max(13, size - 3), Theme.DIM if enabled else Theme.FAINT,
                      max_width=w - 10, align="center", grow="down")
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
        """Run a widget's action. Focus is never changed here: only Tab and the arrow keys move it,
        so Enter after a hotkey or a click reaches the screen's default control."""
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
            self.focus_key = None  # the pointer takes over; Enter goes back to the default control
            for widget in reversed(self.widgets):
                if widget.rect.collidepoint(event.pos):
                    self.activate(widget)
                    return True
            return False
        if event.type != pygame.KEYDOWN:
            return False
        key = KEYPAD_DIGITS.get(event.key, event.key)
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
        if key == pygame.K_ESCAPE:
            if self.escape_action is not None:
                self.focus_key = None
                self.escape_action()
                return True
            if self.focus_key is not None:
                self.focus_key = None
                return True
            return False
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            focused = self.widget(self.focus_key) if self.focus_key else None
            # A focused control with nothing to do (a unit card outside targeting) does not swallow Enter.
            if focused is not None and (focused.action is not None or not focused.enabled):
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
                self.focus_key = None  # a hotkey is a direct command, not a move of the focus ring
                self.activate(widget)
                return True
        return False

    def status_line(self, message: str, is_error: bool, serial: int) -> tuple[str, bool]:
        """What the status bar shows: a new controller message first, then help for the hot control.

        A message that arrived since the last frame is pinned until the pointer or the focus moves
        to a different control. Without this, the tooltip of the control that was just used would
        hide the answer to using it (for example the reason a click was refused).
        """
        # The pointer may have moved since the last frame ended, so look it up among the widgets
        # of the frame being built (the status bar is drawn after them).
        hover = next((w.key for w in reversed(self._building) if w.rect.collidepoint(self.mouse_pos)), None)
        hot = (hover, self.focus_key)
        if serial != self.message_serial:
            self.message_serial = serial
            self.message_pin = hot if message else None
        if self.message_pin is not None:
            if self.message_pin == hot and message:
                return message, is_error
            self.message_pin = None
        hint = self.status_text()
        return hint if hint is not None else (message, is_error)

    def status_text(self) -> tuple[str, bool] | None:
        """Help or disabled-reason text for the focused/hovered widget."""
        for key in (self.hover_key, self.focus_key):
            widget = self.widget(key) if key else None
            if widget is None:
                continue
            if not widget.enabled and widget.reason:
                return f"Unavailable: {widget.reason}", True  # why a control is off is never delayed
            resting = key != self.hover_key or self.hover_ms >= self.tooltip_delay_ms
            if widget.tooltip and resting:
                return widget.tooltip, False
        return None
