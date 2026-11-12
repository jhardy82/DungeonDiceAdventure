"""Text size (owner decision D-31): Large draws text larger wherever it still fits, and breaks no screen.

The layout is drawn for 1280x720 and fixed, so a larger text cannot push its neighbours away. The
rule is therefore: a text grows only where the whole of it still fits. The toolkit decides that for
every frame (``UI.plan_sizes``). The layout check below does not trust it: it draws every state at
the normal and at the large size and compares the two finished frames text by text.
"""

from __future__ import annotations

import itertools
import json

import pygame
import pytest

from battle_dice import settings as module
from battle_dice.app.controller import Screen
from battle_dice.settings import TEXT_SIZES, Settings
from battle_dice.ui import screens
from battle_dice.ui.toolkit import UI, DrawnText, Theme, Trace
from tests.conftest import begin_hero, down, unit
from tests.ui.test_evolution_ui import Configured, close_every_save, medic_game  # noqa: F401 - the fixture closes the saves
from tests.ui.test_ui_flow import SIZES, Play, font  # noqa: F401 - the fixture runs a test under three fonts

LARGE = TEXT_SIZES["large"]


# --------------------------------------------------------------------------------------------
# The layout check
# --------------------------------------------------------------------------------------------


def traced(app, scale: float) -> Trace:
    """One frame of the current state at a text size, with everything it drew."""
    app.ui.text_scale = scale
    app.ui.trace = Trace()
    try:
        app.frame(0)
        return app.ui.trace
    finally:
        app.ui.trace = None
        app.ui.text_scale = 1.0


def problems(app, name: str) -> tuple[list[str], int, int]:
    """What the large text size breaks in the state on screen; and how many texts there are and how many grew.

    Four rules, each against the same frame at the normal size:
    a text that is whole stays whole; a text stays inside the panel or button it sits in; a text does not
    reach a picture it was clear of; two texts that were apart stay apart, by five units side by side
    (and two that were closer than that do not start to overlap).
    """
    normal, large, again = traced(app, 1.0), traced(app, LARGE), traced(app, 1.0)
    assert [text.text for text in normal.texts] == [text.text for text in again.texts], f"{name}: the state moves from frame to frame"
    if len(normal.texts) != len(large.texts):
        return [f"{name}: {len(normal.texts)} texts at the normal size but {len(large.texts)} at the large one"], len(large.texts), 0
    found: list[str] = []
    boxes = [*normal.boxes, app.surface.get_rect()]
    for before, after in zip(normal.texts, large.texts, strict=True):
        if after.shown != after.text and before.shown == before.text:
            found.append(f"{name}: cut off: {after.text!r} -> {after.shown!r}")
        home = min((box for box in boxes if box.contains(before.ink)), key=lambda box: box.w * box.h)
        if not home.contains(after.ink):
            found.append(f"{name}: leaves its box: {after.text!r} {after.ink} is not in {home}")
        if any(after.ink.colliderect(sprite) and not before.ink.colliderect(sprite) for sprite in large.sprites):
            found.append(f"{name}: reaches a picture: {after.text!r}")
    clearance = 2 * app.ui.px(5)
    for first, second in itertools.combinations(range(len(large.texts)), 2):
        one, other, one_before, other_before = large.texts[first].ink, large.texts[second].ink, normal.texts[first].ink, normal.texts[second].ink
        if not one.inflate(clearance, 0).colliderect(other) or one_before.colliderect(other_before):
            continue  # apart; or they overlapped before, which is the layout's own business
        if not one_before.inflate(clearance, 0).colliderect(other_before) or one.colliderect(other):
            found.append(f"{name}: touch: {large.texts[first].text!r} and {large.texts[second].text!r}")
    return found, len(large.texts), sum(1 for text in large.texts if text.pixels > text.normal_pixels)


def end_the_battle(play) -> None:
    """Arrange: every enemy is down. Act: the hero whose dice are rolled passes, and the battle is won."""
    engine = play.ctrl.engine
    for foe in engine.combat.side("enemy"):
        foe.hp, foe.state = 0, "defeated"
    play.ctrl.draft = []
    assert engine.do("SetActionPlan", actions=[]).accepted and engine.do("CommitActionPlan").accepted
    while engine.state.phase == "battle" and not engine.needs_input():
        assert engine.do("AdvancePhase").accepted
    play.ctrl.refresh()
    play.app.frame(0)


class Walk:
    """Collects the check's result over the states of a tour."""

    def __init__(self, app):
        self.app = app
        self.found: list[str] = []
        self.states: dict[str, tuple[int, int]] = {}

    def look(self, name: str) -> None:
        assert name not in self.states, name
        found, texts, grew = problems(self.app, name)
        self.found += found
        self.states[name] = (texts, grew)

    def share_that_grew(self) -> float:
        return sum(grew for _, grew in self.states.values()) / sum(texts for texts, _ in self.states.values())


def tour_with_saved_heroes(tmp_path, size) -> Walk:
    """Class Evolution on: menus, Settings, party, career, a battle with Field Medic, the upgrade, the decision, the end."""
    play = medic_game(tmp_path, size=size)
    ctrl, walk = play.ctrl, Walk(play.app)
    ctrl.to_main_menu()
    walk.look("main menu")
    ctrl.show_controls()
    walk.look("controls")
    ctrl.close_controls()
    ctrl.open_settings()
    for group, _ in ctrl.SETTINGS_GROUPS:
        ctrl.select_settings_tab(group)
        walk.look(f"settings: {group}")
    ctrl.reset_settings()
    walk.look("settings: asked whether to reset")
    ctrl.select_settings_tab("evolution")
    ctrl.reset_profile()
    walk.look("settings: asked whether to reset the profile")
    ctrl.close_settings()
    ctrl.new_run()
    walk.look("party: empty")
    for hero_id in ("hero_001", "hero_002", "hero_003"):
        ctrl.add_saved_hero(hero_id)
    walk.look("party: three saved heroes")
    ctrl.toggle_seed()
    for digit in "20261112":
        ctrl.seed_key(digit)
    walk.look("party: typing a seed")
    ctrl.toggle_seed()
    ctrl.open_career("hero_001")
    for vocation_id in ("squire", "guardian", "champion", "ranger"):
        ctrl.select_career_vocation(vocation_id)
        walk.look(f"career: {vocation_id}")
    ctrl.toggle_career_skills()
    walk.look("career: skills")
    ctrl.close_career()
    ctrl.begin_run()
    engine = ctrl.engine
    assert engine is not None
    down(engine, "h02")
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=5)
    unit(engine, "h01").mana = 2
    ctrl.refresh()
    walk.look("battle: dice rolled")
    ctrl.use_die("guardian_d6")
    walk.look("battle: choosing a target")
    ctrl.choose_target("h02")
    walk.look("battle: a plan with Field Medic")
    play.hover("unit:b1_e01")
    walk.look("battle: an enemy inspected")
    play.hover("unit:h01")
    walk.look("battle: a hero inspected")
    play.app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=(2, 2), rel=(0, 0), buttons=(0, 0, 0)))
    play.app.frame(0)
    ctrl.open_pause()
    walk.look("pause")
    ctrl.open_settings()
    walk.look("settings: during a run")
    ctrl.close_settings()
    ctrl.resume()
    end_the_battle(play)
    assert ctrl.screen == Screen.UPGRADE
    walk.look("upgrade: awards and offers")
    ctrl.select_offer(ctrl.current_offers()[0]["offer_id"])
    walk.look("upgrade: a card chosen")
    ctrl.apply_upgrade()
    walk.look("upgrade: applied")
    ctrl.start_next_battle()
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=1)
    ctrl.refresh()
    walk.look("battle 2: the boss")
    end_the_battle(play)
    assert ctrl.screen == Screen.CONTINUE
    walk.look("decision: stop or fight on")
    ctrl.end_run_with_victory()
    assert ctrl.screen == Screen.OUTCOME
    walk.look("outcome: victory with awards")
    return walk


def tour_of_the_shipped_game(tmp_path, size) -> Walk:
    """Class Evolution off: a party of five, the roll prompt, both battles, a lost run."""
    play = Play(tmp_path, ("squire", "apprentice", "scout", "squire", "scout"), size=size)
    ctrl, walk = play.ctrl, Walk(play.app)
    walk.look("party: five heroes")
    play.hover("slot:1:select")
    walk.look("party: a hero pointed at")
    play.begin()
    play.to_roll_prompt()
    walk.look("battle: roll prompt")
    play.key(pygame.K_r)
    walk.look("battle: after the roll")
    engine = ctrl.engine
    end_the_battle(play)
    assert ctrl.screen == Screen.UPGRADE
    walk.look("upgrade")
    for offer in ctrl.current_offers()[:3]:
        ctrl.select_offer(offer["offer_id"])
        walk.look(f"upgrade: {offer['offer_id']}")
    ctrl.apply_upgrade()
    ctrl.start_next_battle()
    play.to_roll_prompt()
    walk.look("battle 2: roll prompt")
    for hero in engine.combat.side("hero"):
        hero.hp, hero.mana, hero.shields = 1, 0, 0
    play.until(lambda: False)
    assert ctrl.screen == Screen.OUTCOME and engine.state.outcome == "defeat"
    walk.look("outcome: defeat")
    return walk


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("tour", [tour_with_saved_heroes, tour_of_the_shipped_game])
def test_large_text_breaks_no_screen_and_most_text_grows(tmp_path, font, size, tour):  # noqa: F811
    walk = tour(tmp_path, size)
    assert walk.found == [], "\n".join(walk.found)
    assert len(walk.states) >= 10
    assert all(grew > 0 for _, grew in walk.states.values()), {name: v for name, v in walk.states.items() if v[1] == 0}
    assert walk.share_that_grew() >= 0.75, walk.share_that_grew()  # the widest font leaves the least room: 79% at 960x540


FAULTS = [
    ("a text beside another", lambda ui: (ui.text(100, 100, "Squire of the Guard", 16), ui.text(100 + ui.text_width("Squire of the Guard", 16) + 4, 100, "HP 14", 16)),
     "touch: 'Squire of the Guard' and 'HP 14'"),
    ("a line right below another", lambda ui: (ui.text(100, 100, "Guard gypsy", 14, grow="down"), ui.text(100, 114, "HEAVY GUARD", 14, grow="up")),
     "touch: 'Guard gypsy' and 'HEAVY GUARD'"),
    ("a text that fills its panel", lambda ui: (ui.panel(100, 100, ui.text_width("Blight Captain", 15) + 6, 30), ui.text(103, 106, "Blight Captain", 15)),
     "leaves its box: 'Blight Captain'"),
    ("a text beside a picture", lambda ui: (ui.sprite(ui.assets.die_key(6), 300, 100, 20, 20), ui.text(300 - ui.text_width("Heal 2", 14) - 1, 102, "Heal 2", 14)),
     "reaches a picture: 'Heal 2'"),
]


@pytest.mark.parametrize(("what", "draw", "said"), FAULTS)
def test_a_text_with_no_room_to_grow_keeps_its_size_and_the_check_would_have_found_it(tmp_path, monkeypatch, what, draw, said):
    """Four small cases, each drawn on the main menu.

    With the toolkit's rule, the text keeps its normal size and the check has nothing to report. With the rule
    switched off (every text grows), the check reports exactly that case: so the check is not blind, and the tours
    above pass because of the rule.
    """
    play = Configured(tmp_path)
    original = screens.draw_main_menu

    def with_the_case(ui, *arguments):
        original(ui, *arguments)
        draw(ui)

    monkeypatch.setattr(screens, "draw_main_menu", with_the_case)
    found, texts, grew = problems(play.app, "menu")
    assert play.app.render_faults == 0 and found == [] and 0 < grew < texts, (what, found)
    monkeypatch.setattr(UI, "_solve", lambda self: [(item.text, item.wanted) for item in self._measured])
    found, texts, grew = problems(play.app, "menu")
    assert len(found) == 1 and said in found[0] and grew == texts, (what, found)


def test_a_fault_while_measuring_reaches_the_error_screen_once(tmp_path, monkeypatch):
    play = Configured(tmp_path, settings=Settings(text_size="large"))

    def boom(*arguments):
        raise RuntimeError("simulated drawing fault")

    monkeypatch.setattr(screens, "draw_main_menu", boom)
    play.app.ui.trace = Trace()
    play.app.frame(0)
    in_the_same_frame, play.app.ui.trace = play.app.ui.trace.texts, None
    assert play.ctrl.screen == Screen.ERROR and play.app.render_faults == 1
    assert len(in_the_same_frame) > 3, "the error screen is drawn, with its text, in the frame of the fault"
    shown = traced(play.app, LARGE)
    assert play.app.render_faults == 1, "the error screen itself draws at the large size"
    assert len(shown.texts) > 3 and any(text.pixels > text.normal_pixels for text in shown.texts), "... with its text"


# --------------------------------------------------------------------------------------------
# The toolkit's rule, text by text
# --------------------------------------------------------------------------------------------


def drawn(scale: float, draw) -> list[DrawnText]:
    """What ``draw`` puts on an empty frame: measured first, then drawn, as the game does it."""
    ui = UI()
    ui.text_scale = scale
    surface = pygame.Surface((1280, 720))
    ui.begin(surface)
    ui.plan_sizes(lambda: draw(ui))
    ui.begin(surface)
    ui.trace = Trace()
    draw(ui)
    return ui.trace.texts


def measuring() -> UI:
    ui = UI()
    ui.begin(pygame.Surface((1280, 720)))
    return ui


def test_at_the_normal_size_every_text_has_its_normal_size():
    texts = drawn(1.0, lambda ui: (ui.text(10, 10, "Guard", 16), ui.text(10, 40, "Guard", 16, max_width=20), ui.paragraph(10, 80, "one two three four", 60, 14)))
    assert len(texts) >= 4 and all(text.pixels == text.normal_pixels for text in texts)


def test_a_text_with_room_grows_and_one_that_would_not_fit_its_width_keeps_its_size_and_its_words():
    width = measuring().text_width("Goblin Skirmisher 2", 16)
    free, roomy, tight, too_long = drawn(LARGE, lambda ui: (
        ui.text(10, 10, "Goblin Skirmisher 2", 16),
        ui.text(10, 40, "Goblin Skirmisher 2", 16, max_width=width * 1.3),
        ui.text(10, 70, "Goblin Skirmisher 2", 16, max_width=width + 2),
        ui.text(10, 100, "Goblin Skirmisher 2", 16, max_width=width - 20),
    ))
    assert free.pixels == roomy.pixels == 18 and free.normal_pixels == 16
    assert tight.pixels == 16 and tight.shown == "Goblin Skirmisher 2"
    assert too_long.pixels == 16 and too_long.shown.endswith("...")
    # ... and the cut is the one the normal size makes: a larger text never costs a letter.
    assert too_long.shown == drawn(1.0, lambda ui: ui.text(10, 100, "Goblin Skirmisher 2", 16, max_width=width - 20))[0].shown


def test_a_text_may_take_a_size_between_normal_and_large():
    seventeen = measuring()._font_of(17, False).size("Goblin Skirmisher 2")[0]
    (text,) = drawn(LARGE, lambda ui: ui.text(10, 10, "Goblin Skirmisher 2", 16, max_width=seventeen))
    assert text.pixels == 17 and text.shown == "Goblin Skirmisher 2"


def test_of_two_neighbours_on_a_line_the_first_drawn_grows_and_the_second_only_if_there_is_still_room():
    """Like the HP and the shield on a unit's card: one starts at the left, the other ends at the right."""
    ui = measuring()
    width = ui.text_width("HP 29/29", 14)
    growth = ui._font_of(16, False).size("HP 29/29")[0] - ui._font_of(14, False).size("HP 29/29")[0]

    def pair(gap):
        right_edge = 100 + width + gap + ui.text_width("SH 3", 14)
        return drawn(LARGE, lambda ui: (ui.text(100, 10, "HP 29/29", 14), ui.text(right_edge, 10, "SH 3", 14, align="right")))

    first, second = pair(60)
    assert first.pixels == second.pixels == 16
    first, second = pair(growth + 7)  # room for one of them: the first one asked
    assert first.pixels == 16 and second.pixels == 14 and not first.ink.inflate(10, 0).colliderect(second.ink)
    first, second = pair(6)  # room for neither: five units stay between them
    assert first.pixels == second.pixels == 14


def test_texts_that_were_already_closer_than_five_units_may_grow_until_they_would_overlap():
    width = measuring().text_width(">DEF", 14)
    first, second = drawn(LARGE, lambda ui: (ui.text(100, 10, ">DEF", 14), ui.text(100 + width + 2, 10, "Guard", 14)))
    assert not first.ink.colliderect(second.ink) and second.pixels == 16
    first, second = drawn(LARGE, lambda ui: (ui.text(100, 10, ">DEF", 14), ui.text(100 + width + 20, 10, "Guard", 14)))
    assert first.pixels == second.pixels == 16


def test_a_text_stays_in_the_box_it_sits_in_and_clear_of_a_picture():
    ui = measuring()
    width = ui.text_width("Blight Captain", 15)
    (snug,) = drawn(LARGE, lambda ui: (ui.panel(100, 100, width + 6, 30), ui.text(103, 106, "Blight Captain", 15)))
    (roomy,) = drawn(LARGE, lambda ui: (ui.panel(100, 100, width + 60, 34), ui.text(103, 108, "Blight Captain", 15)))
    assert snug.pixels == 15 and roomy.pixels == 17
    by_a_picture = lambda gap: drawn(LARGE, lambda ui: (  # noqa: E731
        ui.sprite(ui.assets.die_key(6), 300, 100, 20, 20), ui.text(300 - ui.text_width("Heal 2", 14) - gap, 102, "Heal 2", 14)))[0]
    assert by_a_picture(1).pixels == 14 and by_a_picture(30).pixels == 16


def test_a_text_grows_around_its_middle_or_only_up_or_only_down():
    normal = drawn(1.0, lambda ui: ui.text(10, 100, "Hxg", 16))[0].ink
    middle, up, down_, none = (drawn(LARGE, lambda ui, g=grow: ui.text(10, 100, "Hxg", 16, grow=g))[0].ink for grow in ("middle", "up", "down", "none"))
    assert none == normal and middle.height == up.height == down_.height > normal.height
    assert up.top < middle.top < down_.top and up.bottom < middle.bottom < down_.bottom
    assert up.top < normal.top and down_.top >= normal.top and down_.bottom > normal.bottom


def test_a_paragraph_grows_only_while_it_needs_no_more_lines_and_has_one_size():
    words = "A mastered vocation teaches a skill. It is free while that vocation is active."
    ui = measuring()

    def lines_at(width, pixels):
        return len(ui._wrap(words, ui.px(width), ui._font_of(pixels, False)))

    below = {}

    def draw(ui, width):
        below[width] = ui.paragraph(10, 10, words, width, 14)

    wide = drawn(LARGE, lambda ui: draw(ui, 420))
    assert {text.pixels for text in wide} == {16} and len(wide) == lines_at(420, 14) == lines_at(420, 16)
    # A width at which the normal size needs two lines and anything larger needs three: the paragraph keeps its size.
    narrow_width = next(width for width in range(200, 420) if lines_at(width, 14) == 2 and lines_at(width, 15) == 3)
    narrow = drawn(LARGE, lambda ui: draw(ui, narrow_width))
    assert [text.text for text in narrow] == ui.wrap_lines(words, narrow_width, 14) and {text.pixels for text in narrow} == {14}
    # In between, the paragraph takes the size that still needs two lines.
    between_width = next(width for width in range(200, 420) if lines_at(width, 15) == 2 and lines_at(width, 16) == 3)
    assert {text.pixels for text in drawn(LARGE, lambda ui: draw(ui, between_width))} == {15}
    # What follows a paragraph is placed for its normal height, at either size.
    assert drawn(1.0, lambda ui: draw(ui, 420)) and below[420] == 10 + len(wide) * 14 * 1.3


def test_a_paragraph_keeps_its_size_when_one_of_its_lines_has_no_room():
    words = "A mastered vocation teaches a skill. It is free while that vocation is active."
    ui = measuring()
    second_line = ui.wrap_lines(words, 420, 14)[1]

    def draw(ui, x):
        ui.paragraph(10, 10, words, 420, 14)
        ui.text(x, 10 + 14 * 1.3, "rank 8", 14, grow="none")  # beside the second line

    assert {text.pixels for text in drawn(LARGE, lambda ui: draw(ui, 10 + 420 + 10))[:2]} == {16}
    close = 10 + ui.text_width(second_line, 14) + 6
    assert {text.pixels for text in drawn(LARGE, lambda ui: draw(ui, close))[:2]} == {14}, "the first line had room, but a paragraph has one size"
    # Larger words wrap differently: the second line of the larger paragraph is longer than the normal one made larger.
    # The neighbour is clear of the latter and in the way of the former, and it is the former that counts.
    large_font = ui._font_of(16, False)
    larger_second_line = ui._wrap(words, ui.px(420), large_font)[1]
    between = 10 + large_font.size(second_line)[0] + 12
    assert large_font.size(larger_second_line)[0] > between - 10 and larger_second_line != second_line
    assert {text.pixels for text in drawn(LARGE, lambda ui: draw(ui, between))[:2]} == {14}


def test_a_paragraph_that_is_cut_at_the_normal_size_is_cut_the_same_way_at_the_large_one():
    words = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen"
    normal = drawn(1.0, lambda ui: ui.paragraph(10, 10, words, 120, 14, max_lines=2))
    large = drawn(LARGE, lambda ui: ui.paragraph(10, 10, words, 120, 14, max_lines=2))
    assert len(normal) == len(large) == 2 and normal[-1].text.endswith(" ...") and large[-1].text.endswith(" ...")
    assert all(text.shown == text.text for text in large)


def test_a_group_grows_together_or_not_at_all():
    ui = measuring()
    labels = ("Schedule", "Passive", "Reaction")
    widest = max(ui.text_width(label, 14, True) for label in labels)

    def column(ui, room, grouped):
        ui.panel(100, 100, room, 80)
        if grouped:
            with ui.group():
                for row, label in enumerate(labels):
                    ui.text(102, 104 + row * 24, label, 14, bold=True)
        else:
            for row, label in enumerate(labels):
                ui.text(102, 104 + row * 24, label, 14, bold=True)

    assert [text.pixels for text in drawn(LARGE, lambda ui: column(ui, widest * 1.5, True))] == [16, 16, 16]
    alone = [text.pixels for text in drawn(LARGE, lambda ui: column(ui, widest + 6, False))]
    assert sorted(set(alone)) == [14, 16], "without a group the short labels grow and the long one cannot"
    assert [text.pixels for text in drawn(LARGE, lambda ui: column(ui, widest + 6, True))] == [14, 14, 14]

    def row(ui, limit):
        with ui.group():
            ui.text(100, 300, "Squire 1", 14, max_width=limit)
            ui.text(400, 300, "Hex Adept", 14)

    width = ui.text_width("Squire 1", 14)
    assert [text.pixels for text in drawn(LARGE, lambda ui: row(ui, width * 1.5))] == [16, 16]
    assert [text.pixels for text in drawn(LARGE, lambda ui: row(ui, width + 1))] == [14, 14], "one member is too wide to grow: none does"


def test_two_paragraphs_decide_each_for_itself():
    words = "A mastered vocation teaches a skill. It is free while that vocation is active."
    ui = measuring()
    narrow = next(width for width in range(200, 420) if len(ui.wrap_lines(words, width, 14)) == 2
                  and len(ui._wrap(words, ui.px(width), ui._font_of(15, False))) == 3)
    first, *second = drawn(LARGE, lambda ui: (ui.paragraph(10, 10, "Guard: +3 shield", 420, 14), ui.paragraph(10, 60, words, narrow, 14)))
    assert first.pixels == 16 and {text.pixels for text in second} == {14}
    *first_lines, last = drawn(LARGE, lambda ui: (ui.paragraph(10, 60, words, narrow, 14), ui.paragraph(10, 140, "Guard: +3 shield", 420, 14)))
    assert {text.pixels for text in first_lines} == {14} and last.pixels == 16


def test_a_text_stays_clear_of_a_bar():
    """Like a number right in front of the health bar on a unit's card."""
    width = measuring().text_width("HP 12", 13)

    def beside(ui, gap):
        ui.bar(200, 100, 36, 8, 5, 10, Theme.GAUGE)
        ui.text(200 - width - gap, 96, "HP 12", 13)

    assert drawn(LARGE, lambda ui: beside(ui, 30))[0].pixels == 15
    assert drawn(LARGE, lambda ui: beside(ui, 1))[0].pixels == 13


def test_the_turn_order_and_the_ability_labels_have_one_size_each(tmp_path):
    """Two groups on the real screens: names of very different length, and three labels in a narrow column."""
    play = medic_game(tmp_path)
    for hero_id in ("hero_001", "hero_002", "hero_003"):
        play.ctrl.add_saved_hero(hero_id)
    play.ctrl.open_career("hero_001")
    play.ctrl.select_career_vocation("guardian")
    labels = {text.text: text.pixels for text in traced(play.app, LARGE).texts if text.text in ("Schedule", "Passive", "Reaction")}
    assert len(labels) == 3 and len(set(labels.values())) == 1, labels
    play.ctrl.close_career()
    play.ctrl.begin_run()
    engine = play.ctrl.engine
    assert engine is not None
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=5)
    play.ctrl.refresh()
    frame = traced(play.app, LARGE)
    strip = pygame.Rect(play.ui.r(62, 46, 1218, 28))
    names = [text for text in frame.texts if strip.contains(text.ink)]
    assert {"Hex Adept", "Goblin Skirmisher 1"} <= {text.text for text in names} and len(names) == 8
    assert len({text.pixels for text in names}) == 1, [(text.text, text.pixels) for text in names]
    # ... and it is the group that does it: the short name alone would have grown.
    hex_adept = next(text for text in names if text.text == "Hex Adept")
    font_now, font_large = play.ui._font_of(hex_adept.normal_pixels, False), play.ui._font_of(15, False)
    assert hex_adept.pixels == hex_adept.normal_pixels and font_large.size("Hex Adept")[0] < font_now.size("Goblin Skirmisher 1")[0]


def test_a_two_line_button_grows_away_from_its_middle():
    def button(ui):
        ui.button("b", 100, 100, 170, 62, "1. Squire 1", None, sublabel="Guardian, rank 8")

    (label, sublabel), (large_label, large_sublabel) = drawn(1.0, button), drawn(LARGE, button)
    assert large_label.pixels > label.pixels and large_sublabel.pixels > sublabel.pixels
    assert large_label.ink.bottom <= label.ink.bottom and large_sublabel.ink.top >= sublabel.ink.top
    assert not large_label.ink.colliderect(large_sublabel.ink)
    assert pygame.Rect(100, 100, 170, 62).contains(large_label.ink.union(large_sublabel.ink))


def test_a_frame_that_was_not_measured_or_differs_from_the_measured_one_is_drawn_at_the_normal_size():
    ui = UI()
    ui.text_scale = LARGE
    surface = pygame.Surface((1280, 720))
    ui.begin(surface)
    ui.trace = Trace()
    ui.text(10, 10, "Guard", 16)
    ui.paragraph(10, 40, "one two three", 300, 14)
    assert [text.pixels for text in ui.trace.texts] == [16, 14], "no plan: nothing grows"
    ui.plan_sizes(lambda: [ui.text(10, y, face, 16) for y, face in ((10, "Guard"), (40, "Brace"), (70, "Jab"))])  # type: ignore[func-returns-value]
    ui.begin(surface)
    ui.trace = Trace()
    ui.text(10, 10, "Guard", 16)
    ui.text(10, 40, "Strike", 16)  # not what was measured: from here on the plan is not trusted
    ui.text(10, 70, "Jab", 16)
    assert [text.pixels for text in ui.trace.texts] == [18, 16, 16]


def test_nothing_is_traced_in_play_and_measuring_draws_nothing():
    ui = UI()
    ui.text_scale = LARGE
    surface = pygame.Surface((1280, 720))
    ui.begin(surface)
    before = surface.copy()
    ui.plan_sizes(lambda: [ui.paragraph(10, y, words, 300, 14) for y, words in ((10, "Guard"), (40, "one two three"))])
    assert ui.trace is None and pygame.image.tobytes(surface, "RGB") == pygame.image.tobytes(before, "RGB")
    ui.text(10, 10, "Guard", 16)
    assert ui.trace is None and pygame.image.tobytes(surface, "RGB") != pygame.image.tobytes(before, "RGB")


# --------------------------------------------------------------------------------------------
# The setting
# --------------------------------------------------------------------------------------------


def test_the_text_size_is_normal_unless_chosen_and_a_wrong_value_is_named(tmp_path):
    assert Settings().text_size == "normal" and TEXT_SIZES == {"normal": 1.0, "large": 1.15}
    file = tmp_path / "settings.json"
    file.write_text(json.dumps({"text_size": "huge"}), encoding="utf-8")
    loaded, said = module.load(file)
    assert loaded.text_size == "normal" and said == ["settings.json: text_size must be one of normal, large; the default is used."]


def test_the_settings_row_switches_the_size_at_once_saves_it_and_a_restart_keeps_it(tmp_path):
    play = Configured(tmp_path)
    play.ctrl.open_settings()
    play.app.frame(0)
    row = next(r for r in play.ctrl.settings_view() if r["key"] == "text_size")
    assert (row["group"], row["label"], row["value"], row["reason"]) == ("comfort", "Text size", "Normal", None)
    assert play.ui.text_scale == 1.0
    controls = sorted(play.ui.keys())
    play.click("settings:text_size")
    assert play.ui.text_scale == LARGE and play.saved()["text_size"] == "large"
    assert sorted(play.ui.keys()) == controls and len(set(controls)) == len(controls), "measuring a frame leaves no second set of controls"
    assert next(r for r in play.ctrl.settings_view() if r["key"] == "text_size")["value"] == "Large"
    again = Configured(tmp_path, settings=module.load(play.file)[0])
    assert again.ui.text_scale == LARGE
    play.click("settings:text_size")
    assert play.ui.text_scale == 1.0 and play.saved()["text_size"] == "normal"


def test_the_large_size_shows_in_the_picture_and_resetting_the_settings_ends_it(tmp_path):
    play = Configured(tmp_path, settings=Settings(text_size="large"))
    play.app.ui.trace = Trace()
    play.app.frame(0)
    title = next(text for text in play.app.ui.trace.texts if text.text == "BATTLE DICE")
    play.app.ui.trace = None
    assert title.pixels > title.normal_pixels
    play.ctrl.open_settings()
    play.ctrl.reset_settings()
    play.ctrl.reset_settings()
    play.app.frame(0)
    assert play.ctrl.settings.text_size == "normal" and play.ui.text_scale == 1.0


def test_the_large_size_is_legible_in_high_contrast_too(tmp_path):
    """The two comfort settings are independent: together they still pass the layout check."""
    from battle_dice.ui import toolkit

    play = Configured(tmp_path, settings=Settings(high_contrast=True))
    try:
        play.ctrl.open_settings()
        found, texts, grew = problems(play.app, "settings in high contrast")
        assert found == [] and grew == texts > 10 and Theme.BG == toolkit.HIGH_CONTRAST_PALETTE["BG"]
    finally:
        toolkit.apply_theme("normal")
