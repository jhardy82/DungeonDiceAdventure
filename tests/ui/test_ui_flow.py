"""Keyboard flow, focus, pause menu, reaction panel and readable-text checks for the battle UI.

These cover defects found in review: Enter repeating the last control instead of confirming,
reaction rows drawn off the panel, no way to leave a run, refusals hidden behind tooltips, and
rules text cut off. Events go through ``GameApp.handle_event`` exactly as a player's would.
"""

from __future__ import annotations

import os

for _variable in ("SDL_VIDEODRIVER", "SDL_AUDIODRIVER"):
    if not os.environ.get(_variable):
        os.environ[_variable] = "dummy"

import pygame  # noqa: E402
import pytest  # noqa: E402

from battle_dice.app.controller import AppController, Screen  # noqa: E402
from battle_dice.core.models import CombatPhase, StatusInstance  # noqa: E402
from battle_dice.ui import screens  # noqa: E402
from battle_dice.ui.app import GameApp  # noqa: E402
from battle_dice.ui.toolkit import UI  # noqa: E402

SIZES = [(1280, 720), (960, 540)]


@pytest.fixture(params=["system", "dejavusans", "bundled"])
def font(request, monkeypatch):
    """Run a text-fit test under several fonts: widths differ a lot between machines.

    "system" is whatever this machine resolves first; DejaVu Sans is the widest common fallback
    (skipped where it is not installed); "bundled" is pygame's own font, used when no listed
    system font exists.
    """
    from battle_dice.ui import toolkit

    pygame.font.init()
    if request.param == "dejavusans":
        if pygame.font.match_font("dejavusans") is None:
            pytest.skip("DejaVu Sans is not installed on this machine")
        monkeypatch.setattr(toolkit, "FONT_CANDIDATES", ("dejavusans",))
    elif request.param == "bundled":
        monkeypatch.setattr(toolkit, "FONT_CANDIDATES", ())
    return request.param


class Play:
    """A headless game with direct access to the same events a player produces."""

    def __init__(self, tmp_path, party, seed=11, size=(1280, 720), animations=False):
        self.ctrl = AppController(fixed_seed=seed, log_dir=tmp_path / "logs")
        self.app = GameApp(self.ctrl, size=size, headless=True, animations=animations)
        self.app.fast = True
        self.ctrl.new_run()
        for class_id in party:
            self.ctrl.add_hero(class_id)
        self.app.frame(0)

    @property
    def ui(self) -> UI:
        return self.app.ui

    @property
    def combat(self):
        return self.ctrl.engine.combat

    def key(self, key, mod=0):
        self.app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode=""))
        self.app.frame(0)

    def click(self, widget_key):
        widget = self.ui.widget(widget_key)
        assert widget is not None, f"{widget_key} not on screen; have {self.ui.keys()}"
        self.app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=widget.rect.center, rel=(0, 0), buttons=(0, 0, 0)))
        self.app.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=widget.rect.center, button=1))
        self.app.frame(0)

    def hover(self, widget_key):
        widget = self.ui.widget(widget_key)
        assert widget is not None, f"{widget_key} not on screen; have {self.ui.keys()}"
        self.app.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=widget.rect.center, rel=(0, 0), buttons=(0, 0, 0)))
        self.app.frame(0)  # hover is computed at the end of a frame ...
        self.app.frame(0)  # ... and drawn in the next one

    def begin(self):
        self.ctrl.begin_run()
        self.app.frame(0)
        assert self.ctrl.screen == Screen.BATTLE

    def to_input(self):
        for _ in range(5000):
            if self.ctrl.screen != Screen.BATTLE or self.ctrl.waiting_for_player():
                break
            self.app.frame(100)
        self.app.frame(0)

    def until(self, condition, limit=600):
        """Pass and skip (through the controller) until ``condition()`` holds at an input point."""
        for _ in range(limit):
            self.to_input()
            if self.ctrl.screen != Screen.BATTLE or condition():
                return
            keys = self.ui.keys()
            if "plan:roll" in keys:
                self.ctrl.roll()
            elif "react:skip" in keys:
                self.ctrl.skip_stage()
            else:
                self.ctrl.pass_turn()
            self.app.frame(0)
        raise AssertionError("the wanted situation never came up")

    def to_roll_prompt(self):
        self.until(lambda: "plan:roll" in self.ui.keys())
        assert "plan:roll" in self.ui.keys()

    def roll_faces(self, **faces):
        """Roll through the UI, then arrange the given 1-based faces so the test is seed-independent."""
        self.key(pygame.K_r)
        turn = self.combat.turn
        assert turn is not None and turn.rolled
        for die_id, face in faces.items():
            turn.rolled[die_id] = face - 1
        self.app.frame(0)


def record_text(monkeypatch):
    """Capture every string the toolkit draws and every string it had to shorten."""
    drawn: list[str] = []
    shortened: list[str] = []
    original_text, original_fit, original_paragraph = UI.text, UI.fit, UI.paragraph

    def text(self, x, y, text, *args, **kwargs):
        drawn.append(text)
        return original_text(self, x, y, text, *args, **kwargs)

    def fit(self, text, font, max_pixels):
        result = original_fit(self, text, font, max_pixels)
        if result != text:
            shortened.append(text)
        return result

    def paragraph(self, x, y, text, width, size=16, *args, **kwargs):
        max_lines = kwargs.get("max_lines")
        if max_lines is not None and len(self.wrap_lines(text, width, size, kwargs.get("bold", False))) > max_lines:
            shortened.append(text)
        drawn.append(text)
        return original_paragraph(self, x, y, text, width, size, *args, **kwargs)

    monkeypatch.setattr(UI, "text", text)
    monkeypatch.setattr(UI, "fit", fit)
    monkeypatch.setattr(UI, "paragraph", paragraph)
    return drawn, shortened


# --------------------------------------------------------------------------------------------
# Enter, focus and hotkeys
# --------------------------------------------------------------------------------------------


def test_enter_confirms_the_plan_after_planning_with_a_hotkey(tmp_path):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    play.roll_faces(iron_d6=1, oath_d4=4)  # Strike and Resolve
    play.key(pygame.K_1)
    assert [a["die_id"] for a in play.ctrl.draft] == ["iron_d6"] and play.ctrl.confirm_problem() is None
    assert play.ui.focus_key is None, "a hotkey must not move the focus ring"
    hero_id = play.combat.turn.hero_id
    play.key(pygame.K_RETURN)
    turn = play.combat.turn
    assert turn is None or turn.hero_id != hero_id or turn.committed, play.ctrl.message
    assert play.ctrl.draft == []


def test_enter_confirms_after_clicking_use_and_a_target(tmp_path):
    play = Play(tmp_path, ["scout"])
    play.begin()
    play.to_roll_prompt()
    play.roll_faces(striker_d8=8, tools_d4=3)  # Blank and Cover (an ally face always asks for its target)
    play.click("die:tools_d4:use")
    assert play.ctrl.targeting_die == "tools_d4"
    target = next(k for k in play.ui.keys("unit:") if play.ui.widget(k).action is not None)
    play.click(target)
    assert play.ctrl.confirm_problem() is None
    hero_id = play.combat.turn.hero_id
    play.key(pygame.K_KP_ENTER)
    turn = play.combat.turn
    assert turn is None or turn.hero_id != hero_id or turn.committed, play.ctrl.message


def test_enter_after_the_reroll_hotkey_does_not_spend_another_reroll(tmp_path):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    play.key(pygame.K_r)  # roll
    play.key(pygame.K_r)  # reroll
    assert play.combat.turn.rerolls_remaining == 1
    play.key(pygame.K_RETURN)  # the default is Confirm, which has nothing to confirm
    assert play.combat.turn.rerolls_remaining == 1
    assert play.ctrl.message_is_error and "No action selected" in play.ctrl.message


def test_enter_after_the_keep_hotkey_does_not_unkeep(tmp_path):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    play.key(pygame.K_r)
    play.key(pygame.K_z)
    assert play.combat.turn.kept == ["iron_d6"]
    play.key(pygame.K_RETURN)
    assert play.combat.turn.kept == ["iron_d6"]


def test_party_setup_enter_begins_instead_of_adding_another_hero(tmp_path):
    play = Play(tmp_path, [])
    play.key(pygame.K_1)
    assert len(play.ctrl.party) == 1
    play.key(pygame.K_RETURN)
    assert len(play.ctrl.party) == 1 and play.ctrl.screen == Screen.BATTLE


def test_keypad_digits_work_like_the_number_row(tmp_path):
    play = Play(tmp_path, [])
    play.key(pygame.K_KP1)
    play.key(pygame.K_KP3)
    assert [m["class_id"] for m in play.ctrl.party] == ["squire", "scout"]


def test_tab_focus_still_drives_enter_and_escape_clears_it(tmp_path):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    play.roll_faces(iron_d6=1, oath_d4=4)
    for _ in range(len(play.ui.widgets) + 1):
        if play.ui.focus_key == "die:iron_d6:keep":
            break
        play.key(pygame.K_TAB)
    assert play.ui.focus_key == "die:iron_d6:keep"
    play.key(pygame.K_RETURN)
    assert play.combat.turn.kept == ["iron_d6"], "Enter activates the focused control"
    assert play.ui.focus_key == "die:iron_d6:keep", "Tab focus stays where the player put it"
    play.key(pygame.K_SPACE)
    assert play.combat.turn.kept == []
    # Focus on a control with nothing to do (a unit card) does not swallow Enter.
    play.ui.focus_key = "unit:h01"
    play.key(pygame.K_1)  # hotkey: plans Strike and clears the ring
    assert play.ui.focus_key is None and len(play.ctrl.draft) == 1
    play.ui.focus_key = "unit:h01"
    play.key(pygame.K_RETURN)
    assert play.ctrl.draft == [], "Enter reached Confirm even though a unit card held the focus"


def test_a_click_on_a_unit_card_does_not_disable_space_or_enter(tmp_path):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    play.click("unit:h01")
    assert play.ui.focus_key is None
    play.key(pygame.K_RETURN)  # default: Roll
    assert play.combat.turn.rolled
    play.key(pygame.K_p)  # pass; the game now resolves on its own
    assert not play.ctrl.waiting_for_player()
    play.app.fast = False
    play.ui.focus_key = "unit:h01"  # even with a focus ring, Space steps while resolving
    before = play.ctrl.engine.revision
    play.app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0, unicode=""))
    play.app.frame(1)  # far less than the normal step delay
    assert play.ctrl.engine.revision == before + 1


# --------------------------------------------------------------------------------------------
# Reaction panel
# --------------------------------------------------------------------------------------------


def _guard_window(play):
    return "react:skip" in play.ui.keys() and play.combat.phase == CombatPhase.GUARD_WINDOW


@pytest.mark.parametrize("size", SIZES)
def test_every_reaction_control_is_inside_the_panel_with_five_reactors(tmp_path, monkeypatch, size, font):
    play = Play(tmp_path, ["squire"] * 5, seed=7, size=size)
    play.begin()
    play.until(lambda: _guard_window(play))
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    intent = play.ctrl.view()["intent"]
    title = f"{intent['actor_name']}: {intent['name']}"
    assert title in drawn and title not in shortened, "the enemy's action name is cut off in the intent panel"
    assert "costs 1 mana" in drawn and "costs 1 mana" not in shortened
    panel = play.ui.r(8, 476, 1264, 214)
    rows = [k for k in play.ui.keys("react:") if k.count(":") == 1 and k not in ("react:skip", "react:skip_all")]
    assert len(rows) == 5
    for key in play.ui.keys("react:"):
        assert panel.contains(play.ui.widget(key).rect), f"{key} is drawn outside the reaction panel"
    rects = [play.ui.widget(k).rect for k in play.ui.keys("react:")]
    assert not any(a.colliderect(b) for i, a in enumerate(rects) for b in rects[i + 1:]), "reaction controls overlap"


def test_every_legal_reaction_target_has_a_button(tmp_path):
    """Five targets on one intent: the fifth ally used to be impossible to choose."""
    play = Play(tmp_path, ["squire", "squire", "apprentice", "scout", "scout"], seed=7)
    play.begin()
    play.to_input()
    combat = play.combat
    play.until(lambda: _guard_window(play))
    intent = combat.committed_intent
    intent.committed_target_ids = sorted(h.id for h in combat.side("hero"))  # arrange: everyone is targeted
    play.app.frame(0)
    view = play.ctrl.view()
    for option in view["reaction"]["options"]:
        if option["eligible"] and option["needs_target"]:
            assert len(option["target_ids"]) == 5
            for target_id in option["target_ids"]:
                assert play.ui.widget(f"react:{option['hero_id']}:{target_id}") is not None
    panel = play.ui.r(8, 476, 1264, 214)
    assert all(panel.contains(play.ui.widget(k).rect) for k in play.ui.keys("react:"))


def test_reaction_by_keyboard_row_number_then_ally_number(tmp_path):
    play = Play(tmp_path, ["squire", "squire", "scout"], seed=7)
    play.begin()
    play.until(lambda: _guard_window(play))
    combat = play.combat
    combat.committed_intent.committed_target_ids = ["h01", "h02", "h03"]  # arrange: three allies to choose from
    play.app.frame(0)
    play.key(pygame.K_1)  # row 1: Interpose (Squire 1) needs an ally
    assert play.ctrl.reaction_hero == "h01" and combat.reactions_used == []
    play.key(pygame.K_ESCAPE)  # Esc cancels the choice, it does not open the menu
    assert play.ctrl.reaction_hero is None and not play.ctrl.paused
    play.key(pygame.K_2)  # row 2: Squire 2
    assert play.ctrl.reaction_hero == "h02"
    shields = combat.combatants["h03"].shields
    play.key(pygame.K_3)  # ally 3: the Scout
    assert play.ctrl.reaction_hero is None
    assert [r.reacting_hero_id for r in combat.reactions_used] == ["h02"]
    assert combat.combatants["h03"].shields > shields


def test_reaction_by_mouse_is_one_click_on_the_ally_button(tmp_path):
    play = Play(tmp_path, ["squire", "scout"], seed=7)
    play.begin()
    play.until(lambda: _guard_window(play))
    combat = play.combat
    combat.committed_intent.committed_target_ids = ["h01", "h02"]
    play.app.frame(0)
    play.click("react:h01:h02")
    assert [r.reacting_hero_id for r in combat.reactions_used] == ["h01"]


# --------------------------------------------------------------------------------------------
# Pause menu
# --------------------------------------------------------------------------------------------


def test_escape_pauses_a_battle_and_nothing_advances_until_resume(tmp_path):
    play = Play(tmp_path, ["squire", "scout"])
    play.begin()
    assert "battle:menu" in play.ui.keys()
    play.to_roll_prompt()
    play.key(pygame.K_r)
    play.key(pygame.K_p)  # passed: the game is now resolving on its own
    assert not play.ctrl.waiting_for_player()
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.paused and {"pause:resume", "pause:controls", "pause:party", "pause:menu"} <= set(play.ui.keys())
    revision = play.ctrl.engine.revision
    for _ in range(20):
        play.app.frame(500)
    play.key(pygame.K_f)
    play.key(pygame.K_SPACE)
    assert play.ctrl.engine.revision == revision, "the run advanced while paused"
    play.click("pause:controls")
    assert "controls:back" in play.ui.keys() and play.ctrl.engine is not None
    play.key(pygame.K_ESCAPE)  # back to the pause menu, not to the main menu
    assert "pause:resume" in play.ui.keys()
    play.key(pygame.K_ESCAPE)
    assert not play.ctrl.paused and play.ctrl.screen == Screen.BATTLE
    play.app.frame(500)
    assert play.ctrl.engine.revision > revision


def test_escape_cancels_targeting_before_it_opens_the_menu(tmp_path):
    play = Play(tmp_path, ["scout"])
    play.begin()
    play.to_roll_prompt()
    play.roll_faces(striker_d8=8, tools_d4=3)  # Blank and Cover
    play.key(pygame.K_2)
    assert play.ctrl.targeting_die == "tools_d4"
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.targeting_die is None and not play.ctrl.paused
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.paused


@pytest.mark.parametrize("button, screen", [("pause:menu", Screen.MAIN_MENU), ("pause:party", Screen.PARTY_SETUP)])
def test_a_run_can_be_abandoned_from_the_pause_menu(tmp_path, button, screen):
    play = Play(tmp_path, ["squire", "scout"])
    play.begin()
    play.click("battle:menu")
    assert play.ctrl.paused
    play.click(button)
    assert play.ctrl.screen == screen and play.ctrl.engine is None and not play.ctrl.paused
    assert len(play.ctrl.party) == 2
    assert not (tmp_path / "logs").exists(), "an abandoned run writes no event log"


def test_the_upgrade_screen_has_the_menu_too(tmp_path):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_input()
    for enemy in play.combat.side("enemy"):
        enemy.hp = 1
    for _ in range(200):
        play.to_input()
        if play.ctrl.screen != Screen.BATTLE:
            break
        if "plan:roll" in play.ui.keys():
            play.roll_faces(iron_d6=1, oath_d4=1)
            play.key(pygame.K_1)
            play.key(pygame.K_RETURN)
        else:
            play.ctrl.skip_stage()
            play.app.frame(0)
    assert play.ctrl.screen == Screen.UPGRADE
    assert "up:menu" in play.ui.keys()
    play.key(pygame.K_ESCAPE)
    assert play.ctrl.paused and "pause:resume" in play.ui.keys()
    play.key(pygame.K_RETURN)  # default: Resume
    assert not play.ctrl.paused and play.ctrl.screen == Screen.UPGRADE and "up:apply" in play.ui.keys()


# --------------------------------------------------------------------------------------------
# Status bar, readable text
# --------------------------------------------------------------------------------------------


def test_a_refused_action_is_shown_instead_of_the_buttons_own_tooltip(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    play.roll_faces(iron_d6=1, oath_d4=1)  # Strike and Jab: both usable, but a Squire takes one action
    play.click("die:iron_d6:use")
    play.click("die:oath_d4:use")
    assert play.ctrl.message_is_error and "Remove an action first" in play.ctrl.message
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert any("Remove an action first" in text for text in drawn), "the refusal is hidden behind the tooltip"
    # Once the pointer moves to another control, help text for that control returns.
    play.hover("plan:pass")
    drawn.clear()
    play.app.frame(0)
    assert any(text.startswith("End this activation") for text in drawn)


def test_enemy_abilities_and_statuses_are_readable_in_full(tmp_path, monkeypatch, font):
    play = Play(tmp_path, ["squire", "scout"], seed=7)
    play.begin()
    play.to_input()
    combat = play.combat
    enemy = combat.side("enemy")[0]
    for index, kind in enumerate(("poison", "poison", "weaken")):
        enemy.status_instances.append(StatusInstance(f"st90{index}", kind, "test", enemy.id, 1, index + 1, 0))
    play.hover(f"unit:{enemy.id}")
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    view = next(c for c in play.ctrl.view()["combatants"] if c["id"] == enemy.id)
    for ability in view["actions"]:
        line = f"{ability['name']} [{ability['glyph']}, weight {ability['weight']}]: {ability['text']}."
        assert line in drawn and line not in shortened
    for status in view["statuses"]:
        assert any(text.startswith(f"{status['label']} x{status['stacks']}, {status['remaining']} activation") for text in drawn)
    assert any("ignores shields" in text for text in drawn) and any("to the damage it deals" in text for text in drawn)


@pytest.mark.parametrize("size", SIZES)
def test_the_boss_move_list_is_never_cut_off(tmp_path, monkeypatch, size, font):
    from tests.conftest import packaged_content

    content = packaged_content()
    documents = __import__("copy").deepcopy(content.documents)
    documents["encounters"]["encounters"]["1"][0]["enemies"] = [{"archetype": "captain"}]
    from battle_dice.content.loader import build_content

    play = Play(tmp_path, [], size=size)
    play.ctrl.content = build_content(documents)
    play.ctrl.add_hero("squire")
    play.begin()
    play.to_input()
    captain = play.combat.side("enemy")[0]
    play.hover(f"unit:{captain.id}")
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    view = next(c for c in play.ctrl.view()["combatants"] if c["id"] == captain.id)
    wanted = [f"{a['name']} [{a['glyph']}, weight {a['weight']}]: {a['text']}." for a in view["actions"]]
    assert len(wanted) == 4
    for line in wanted:
        assert line in drawn and line not in shortened, f"cut off: {line}"


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("class_id", ["squire", "apprentice", "scout"])
def test_die_face_rules_are_never_cut_off_in_battle_or_on_the_upgrade_screen(tmp_path, monkeypatch, size, class_id, font):
    play = Play(tmp_path, [class_id], size=size)
    play.begin()
    play.to_roll_prompt()
    play.key(pygame.K_r)
    hero = play.combat.combatants["h01"]
    face_texts = set()
    for die in next(c for c in play.ctrl.view()["combatants"] if c["id"] == "h01")["dice"]:
        face_texts |= {g["face"]["text"] for g in die["groups"]}
    drawn, shortened = record_text(monkeypatch)
    for die_id in hero.equipped_dice_ids:  # the inspector follows the hot die button
        play.hover(f"die:{die_id}:keep")
        play.app.frame(0)
    cut = [text for text in shortened if any(face in text for face in face_texts)]
    assert not cut, f"face rules were shortened: {cut}"
    rolled = [f"{d['face']['glyph']}  {d['face']['name']}" for d in play.ctrl.view()["hero_turn"]["dice"]]
    assert all(heading in drawn and heading not in shortened for heading in rolled), "a rolled face's name was cut off"

    # Upgrade screen: equipped dice comparison and the bench die.
    for enemy in play.combat.side("enemy"):
        enemy.hp = 0
        enemy.state = "defeated"
    play.combat.phase = CombatPhase.TERMINAL_CHECK
    play.ctrl.engine.do("AdvancePhase")
    play.ctrl.refresh()
    play.app.frame(0)
    assert play.ctrl.screen == Screen.UPGRADE
    bench = play.ctrl.view()["upgrade"]["heroes"][0]["bench"]
    bench_texts = {g["face"]["text"] for b in bench for g in b["die"]["groups"]}
    drawn.clear()
    shortened.clear()
    for index in range(3):
        play.click(f"up:offer:{index}")
        play.app.frame(0)
    cut = [text for text in shortened if any(face in text for face in face_texts | bench_texts)]
    assert not cut, f"face rules were shortened on the upgrade screen: {cut}"


@pytest.mark.parametrize("size", SIZES)
def test_status_summary_on_a_card_groups_stacks_and_never_overlaps_the_gauge(tmp_path, monkeypatch, size, font):
    play = Play(tmp_path, ["squire"], seed=7, size=size)
    play.begin()
    play.to_input()
    hero = play.combat.combatants["h01"]
    hero.status_instances.clear()
    for index, (kind, stacks, remaining) in enumerate((("weaken", 1, 1), ("poison", 1, 2), ("poison", 1, 1), ("poison", 1, 2),
                                                       ("weaken", 1, 2), ("speed_up", 2, 2))):
        hero.status_instances.append(StatusInstance(f"st90{index}", kind, "test", "h01", stacks, remaining, 0))
    view = next(c for c in play.ctrl.view()["combatants"] if c["id"] == "h01")
    forms = screens._status_forms(view)
    assert forms[0] == "PSN x3 (1-2)  WKN x2 (1-2)  SPD+ x2 (2)"  # fixed order, whatever order they were applied in
    assert forms[2] == "P3(1-2) W2(1-2) S2(2)"  # the widest summary the rules allow
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    shown = [text for text in drawn if text in forms]
    assert len(shown) == 1 and shown[0] not in shortened, "the status summary on the card was cut off"
    assert f"G{hero.gauge}" not in drawn, "with three statuses the gauge number gives way (the bar stays)"

    # Two statuses, as heroes commonly have: one of the forms fits whole in every font.
    hero.status_instances = [s for s in hero.status_instances if s.kind != "speed_up"]
    forms = screens._status_forms(next(c for c in play.ctrl.view()["combatants"] if c["id"] == "h01"))
    drawn.clear()
    shortened.clear()
    play.app.frame(0)
    shown = [text for text in drawn if text in forms]
    assert len(shown) == 1 and shown[0] not in shortened

    hero.status_instances = hero.status_instances[:1]
    drawn.clear()
    play.app.frame(0)
    assert "WKN x1 (1)" in drawn and f"G{hero.gauge}" in drawn, "one status: full form and the gauge number together"


def test_unit_names_keep_their_number_when_shortened(tmp_path):
    play = Play(tmp_path, ["squire"])
    name = play.ui.fit_name("Goblin Skirmisher 2", 15, True, 110)
    assert name.endswith(" 2") and "..." in name
    assert play.ui.fit_name("Squire 1", 15, True, 200) == "Squire 1"


def test_an_illegal_draft_still_lists_what_is_drafted(tmp_path):
    play = Play(tmp_path, ["apprentice"])
    play.begin()
    play.to_roll_prompt()
    play.roll_faces(arcane_d6=1, focus_d4=1)  # Arcane Bolt (1 mana) and Channel
    play.combat.combatants["h01"].mana = 0
    play.ctrl.draft = [{"die_id": "arcane_d6", "target_ids": [play.combat.side("enemy")[0].id]}]
    preview = play.ctrl.plan_preview()
    assert preview["problem"] and [entry["name"] for entry in preview["ordered"]] == ["Arcane Bolt"]
    assert preview["problem_code"] == "INSUFFICIENT_MANA"  # the code beside the text (decision of 2026-11-11)
    play.app.frame(0)  # and the planner draws it without error
    assert play.ctrl.screen == Screen.BATTLE


def test_no_face_is_named_while_a_die_is_still_tumbling(tmp_path, monkeypatch):
    play = Play(tmp_path, ["scout"], animations=True)
    play.begin()
    play.to_roll_prompt()
    play.key(pygame.K_r)
    drawn, _ = record_text(monkeypatch)
    play.app.frame(16)
    assert play.ui.anim.is_tumbling("striker_d8")
    assert drawn.count("Rolling ...") == 2
    assert not any(text.startswith("Face ") for text in drawn), "a face number was shown before the die settled"
    for _ in range(60):
        play.app.frame(16)
    drawn.clear()
    play.app.frame(16)
    assert "Rolling ..." not in drawn and sum(text.startswith("Face ") for text in drawn) == 2


def test_the_log_names_dice_not_their_ids(tmp_path):
    play = Play(tmp_path, ["scout"])
    play.begin()
    play.to_roll_prompt()
    play.key(pygame.K_r)
    lines = play.ctrl.log_lines()
    assert any("rolls Striker d8:" in line for line in lines)
    assert not any("striker_d8" in line or "tools_d4" in line for line in lines)


def test_a_first_battle_defeat_does_not_mention_a_lost_upgrade(tmp_path, monkeypatch):
    play = Play(tmp_path, ["scout"], seed=3)
    play.begin()
    play.to_input()
    for hero in play.combat.side("hero"):
        hero.hp, hero.mana, hero.shields = 1, 0, 0
    play.until(lambda: False)
    assert play.ctrl.screen == Screen.OUTCOME and play.ctrl.engine.state.outcome == "defeat"
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert not any("upgrade is lost" in text for text in drawn)
    assert "Scout 1" in drawn, "the outcome screen names each hero"
    assert any(text.startswith("The run is over.") for text in drawn), "the status bar no longer shows a stale battle message"


# --------------------------------------------------------------------------------------------
# Logs and fault handling
# --------------------------------------------------------------------------------------------


def test_a_second_session_with_the_same_seed_does_not_overwrite_the_first_log(tmp_path):
    paths = []
    for party in (["scout"], ["apprentice", "scout"]):
        play = Play(tmp_path, party, seed=9)  # a new controller: the run counter starts again at 1
        play.begin()
        play.to_input()
        for hero in play.combat.side("hero"):
            hero.hp, hero.mana, hero.shields = 1, 0, 0
        play.until(lambda: False)
        assert play.ctrl.screen == Screen.OUTCOME and play.ctrl.log_path is not None
        paths.append(play.ctrl.log_path)
    assert paths[0] != paths[1] and all(path.exists() for path in paths)
    assert paths[0].name == "run-9-1.jsonl" and paths[1].name == "run-9-1-2.jsonl"


def test_a_fault_while_editing_the_plan_reaches_the_error_screen(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    play.roll_faces(iron_d6=1, oath_d4=1)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated preview fault")

    monkeypatch.setattr(play.ctrl.engine, "check_plan", boom)  # what the plan preview of the app calls
    play.click("die:iron_d6:use")  # must not raise out of the event handler
    assert play.ctrl.screen == Screen.ERROR and "simulated preview fault" in play.ctrl.error_text
    play.click("error:menu")
    assert play.ctrl.screen == Screen.MAIN_MENU


def test_an_animation_fault_reaches_the_error_screen(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"], animations=True)
    play.begin()

    def boom(*args, **kwargs):
        raise RuntimeError("simulated animation fault")

    monkeypatch.setattr(play.ui.anim, "sync", boom)
    play.app.frame(16)  # must not raise out of the frame
    assert play.ctrl.screen == Screen.ERROR and "simulated animation fault" in play.ctrl.error_text


def test_a_drawing_fault_is_counted_so_the_smoke_test_can_fail_on_it(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"])
    play.begin()
    assert play.app.render_faults == 0

    def boom(*args, **kwargs):
        raise RuntimeError("simulated drawing fault")

    monkeypatch.setattr(screens, "draw_battle", boom)
    play.app.frame(0)
    assert play.app.render_faults == 1 and play.ctrl.screen == Screen.ERROR


# --------------------------------------------------------------------------------------------
# Self-check and entry point
# --------------------------------------------------------------------------------------------


def _raise(message):
    def boom(*args, **kwargs):
        raise RuntimeError(message)

    return boom


@pytest.mark.parametrize("screen_function", ["draw_battle", "draw_upgrade", "draw_outcome"])
def test_the_smoke_test_fails_when_a_screen_cannot_be_drawn(tmp_path, monkeypatch, screen_function):
    from battle_dice.__main__ import main

    monkeypatch.setattr(screens, screen_function, _raise("simulated drawing fault"))
    report = tmp_path / "smoke.txt"
    assert main(["--smoke-test", "--smoke-out", str(report)]) == 1
    text = report.read_text(encoding="utf-8")
    assert text.startswith("SMOKE TEST FAILED") and "simulated drawing fault" in text


def test_the_smoke_test_fails_when_a_sprite_is_missing(tmp_path, monkeypatch):
    from battle_dice.__main__ import main
    from battle_dice.ui.artwork import AssetStore

    original = AssetStore.load_all

    def load_all(self):
        count = original(self)
        self.missing.add("die_d4")
        return count

    monkeypatch.setattr(AssetStore, "load_all", load_all)
    report = tmp_path / "smoke.txt"
    assert main(["--smoke-test", "--smoke-out", str(report)]) == 1
    assert "sprites failed to load: ['die_d4']" in report.read_text(encoding="utf-8")


def test_version_flag_prints_rules_and_content_versions(capsys):
    from battle_dice import RULES_VERSION
    from battle_dice.__main__ import main

    assert main(["--version"]) == 0
    assert f"rules {RULES_VERSION}, content " in capsys.readouterr().out


def test_an_unexpected_crash_leaves_a_report_file_and_a_nonzero_exit(tmp_path, monkeypatch, capsys):
    from battle_dice.__main__ import main

    monkeypatch.setattr(GameApp, "run", _raise("simulated crash in the main loop"))
    assert main(["--log-dir", str(tmp_path / "logs"), "--seed", "5"]) == 1
    reports = list((tmp_path / "logs").glob("crash-*.txt"))
    assert len(reports) == 1 and "simulated crash in the main loop" in reports[0].read_text(encoding="utf-8")
    assert "Details were saved to" in capsys.readouterr().err


# --------------------------------------------------------------------------------------------
# The remaining documented keys (AC-19)
# --------------------------------------------------------------------------------------------


def test_combo_planning_by_keyboard_alone_with_numbered_targets_order_and_clear(tmp_path):
    play = Play(tmp_path, ["scout", "squire"], seed=7)
    play.begin()
    play.until(lambda: "plan:roll" in play.ui.keys() and play.combat.turn.hero_id == "h01")
    play.roll_faces(striker_d8=4, tools_d4=1)  # Poison (status) and Quick Shot (attack): the Scout's combo
    play.key(pygame.K_x)  # keep die 2
    assert play.combat.turn.kept == ["tools_d4"]
    play.key(pygame.K_x)
    assert play.combat.turn.kept == []

    play.key(pygame.K_1)  # plan Poison: two enemies, so a target is asked for
    assert play.ctrl.targeting_die == "striker_d8"
    numbered = {w.hotkeys[0]: w.key for w in play.ui.widgets if w.key.startswith("unit:") and w.hotkeys}
    assert set(numbered) == {pygame.K_1, pygame.K_2}, "each legal target shows a number key"
    play.key(pygame.K_2)
    assert play.ctrl.draft == [{"die_id": "striker_d8", "target_ids": [numbered[pygame.K_2][5:]]}]
    play.key(pygame.K_2)  # plan Quick Shot
    play.key(pygame.K_1)
    assert [a["die_id"] for a in play.ctrl.draft] == ["striker_d8", "tools_d4"] and play.ctrl.confirm_problem() is None

    play.key(pygame.K_o)  # swap the drafted order; class rules still put the Status first when it resolves
    assert [a["die_id"] for a in play.ctrl.draft] == ["tools_d4", "striker_d8"]
    assert [entry["die_id"] for entry in play.ctrl.plan_preview()["ordered"]] == ["striker_d8", "tools_d4"]
    play.key(pygame.K_c)
    assert play.ctrl.draft == [] and "cleared" in play.ctrl.message.lower()

    play.key(pygame.K_1)
    play.key(pygame.K_1)
    play.key(pygame.K_2)
    play.key(pygame.K_1)
    play.key(pygame.K_RETURN)
    turn = play.combat.turn
    assert turn is None or turn.hero_id != "h01" or turn.committed, play.ctrl.message


def test_arrow_keys_move_the_focus_ring_and_f_and_m_toggle_pacing(tmp_path):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    order = [w.key for w in play.ui.widgets]
    play.key(pygame.K_DOWN)
    assert play.ui.focus_key == order[0]
    play.key(pygame.K_RIGHT)
    assert play.ui.focus_key == order[1]
    play.key(pygame.K_UP)
    play.key(pygame.K_LEFT)
    assert play.ui.focus_key == order[-1], "the ring wraps around"
    play.key(pygame.K_TAB, mod=pygame.KMOD_SHIFT)
    assert play.ui.focus_key == order[-2]
    play.key(pygame.K_ESCAPE)  # first Esc opens the menu (its action wins) and drops the ring
    assert play.ui.focus_key is None and play.ctrl.paused
    play.key(pygame.K_ESCAPE)

    fast = play.app.fast
    play.key(pygame.K_f)
    assert play.app.fast is (not fast) and "Fast mode" in play.ctrl.message
    animated = play.ui.anim.enabled
    play.key(pygame.K_m)
    assert play.ui.anim.enabled is (not animated) and "Animation" in play.ctrl.message


# --------------------------------------------------------------------------------------------
# Fixes from the scenario playtest (docs/PLAYTEST.md)
# --------------------------------------------------------------------------------------------


def _win_battle_1(play):
    for enemy in play.combat.side("enemy"):
        enemy.hp = 1
    for _ in range(200):
        play.to_input()
        if play.ctrl.screen != Screen.BATTLE:
            break
        if "plan:roll" in play.ui.keys():
            play.roll_faces(iron_d6=1, oath_d4=1)
            play.key(pygame.K_1)
            play.key(pygame.K_RETURN)
        else:
            play.ctrl.skip_stage()
            play.app.frame(0)
    assert play.ctrl.screen == Screen.UPGRADE


@pytest.mark.parametrize("size", SIZES)
def test_a_weakened_attack_shows_what_it_will_really_deal_on_the_die_and_in_the_plan(tmp_path, monkeypatch, size, font):
    play = Play(tmp_path, ["squire"], size=size)
    play.begin()
    play.to_roll_prompt()
    play.combat.combatants["h01"].status_instances = [StatusInstance("st900", "weaken", "x", "h01", 1, 2, 0)]
    play.roll_faces(iron_d6=6, oath_d4=1)  # Blank and Jab, with exactly one Weaken stack
    jab = play.ctrl.engine.die_for("h01", "oath_d4").faces[0].power
    note = f"Now deals {jab - 1} (Weaken -1)"
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    assert note in drawn and note not in shortened
    play.key(pygame.K_2)
    drawn.clear()
    play.app.frame(0)
    assert drawn.count(note) == 2, "the die card and the plan line both say it"
    assert not [t for t in shortened if t.startswith("Now ")]


@pytest.mark.parametrize("size", SIZES)
def test_class_bonuses_are_shown_where_the_player_plans(tmp_path, monkeypatch, size, font):
    squire = Play(tmp_path, ["squire"], size=size)
    squire.begin()
    squire.to_roll_prompt()
    squire.roll_faces(iron_d6=3, oath_d4=4)  # Guard
    drawn, shortened = record_text(monkeypatch)
    squire.app.frame(0)
    note = next(t for t in drawn if t.startswith("Now +"))
    assert note.endswith("shield (Steadfast +1)") and note not in shortened

    apprentice = Play(tmp_path, ["apprentice"], size=size)
    apprentice.begin()
    apprentice.to_roll_prompt()
    apprentice.combat.combatants["h01"].corruption = 3
    apprentice.combat.combatants["h01"].status_instances = []
    apprentice.roll_faces(arcane_d6=1, focus_d4=4)  # Arcane Bolt at the Arcane Resonance threshold
    drawn.clear()
    apprentice.app.frame(0)
    note = next(t for t in drawn if t.startswith("Now deals "))
    assert note.endswith("(Arcane Resonance +1)") and note not in shortened

    scout = Play(tmp_path, ["scout"], size=size)
    scout.begin()
    scout.to_roll_prompt()
    scout.combat.combatants["h01"].status_instances = []
    scout.roll_faces(striker_d8=4, tools_d4=1)  # Poison, then Quick Shot
    scout.key(pygame.K_1)
    scout.key(pygame.K_2)
    assert scout.ctrl.confirm_problem() is None
    drawn.clear()
    scout.app.frame(0)
    assert "Now deals 2 (Exploit Opening +1)" in drawn, "the combo bonus appears on the plan line"
    assert not [t for t in shortened if t.startswith("Now ")]


def test_a_die_in_the_plan_is_not_labelled_will_reroll(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    play.roll_faces(iron_d6=1, oath_d4=4)
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert drawn.count("will reroll") == 2
    play.key(pygame.K_1)
    drawn.clear()
    play.app.frame(0)
    assert drawn.count("will reroll") == 1 and "IN PLAN" in drawn


def test_the_reroll_hint_is_given_on_the_first_roll_of_a_run_only(tmp_path):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_roll_prompt()
    play.key(pygame.K_r)
    assert play.ctrl.message.startswith("Rolled. Reroll (R) rerolls every die you have not kept")
    play.key(pygame.K_p)
    play.to_roll_prompt()
    play.key(pygame.K_r)
    assert play.ctrl.message == "Keep dice, reroll the rest, then choose actions."


@pytest.mark.parametrize("size", SIZES)
def test_a_reaction_decision_is_announced_and_skip_all_ends_it(tmp_path, monkeypatch, size, font):
    play = Play(tmp_path, ["squire", "apprentice", "scout"], seed=21, size=size)
    play.begin()
    play.until(lambda: "react:skip" in play.ui.keys())
    assert play.ctrl.message.startswith("An enemy action is revealed."), "the first prompt explains what a reaction is"
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    for label in ("Skip", "Skip All", "(S) this stage", "(A) all stages"):
        assert label in drawn and label not in shortened
    panel = play.ui.r(8, 476, 1264, 214)
    assert panel.contains(play.ui.widget("react:skip").rect) and panel.contains(play.ui.widget("react:skip_all").rect)
    intent_id = play.combat.committed_intent.id
    windows = len([e for e in play.ctrl.engine.events if e.type == "reaction_stage_opened"])
    play.key(pygame.K_a)
    assert "every stage skipped" in play.ctrl.message
    play.to_input()
    assert "react:skip" not in play.ui.keys() or play.combat.committed_intent.id != intent_id, \
        "no further stage of the same enemy action asks again"
    used = [e for e in play.ctrl.engine.events if e.type == "reaction_used" and e.intent_id == intent_id]
    assert not used and len([e for e in play.ctrl.engine.events if e.type == "reaction_stage_opened"]) >= windows
    # The next enemy action asks again, with the shorter reminder.
    play.until(lambda: "react:skip" in play.ui.keys())
    assert play.combat.committed_intent.id != intent_id
    assert play.ctrl.message == "Reaction decision: pick a reaction, Skip Stage (S), or Skip All (A)."


def test_swapping_out_the_larger_die_needs_a_second_press(tmp_path, monkeypatch):
    play = Play(tmp_path, ["squire"])
    play.begin()
    play.to_input()
    _win_battle_1(play)
    play.click("up:offer:0")
    play.click("up:apply")
    assert "up:swap:h01:iron_d6" in play.ui.keys()
    play.click("up:swap:h01:oath_d4") if "iron_d6" in play.ctrl.engine.state.upgrades[0]["die_id"] else None
    engine = play.ctrl.engine
    upgraded = engine.state.upgrades[0]["die_id"]
    if upgraded == "iron_d6":  # the upgraded die is locked; nothing larger can be given up in this run
        assert engine.combat.combatants["h01"].equipped_dice_ids.count("vanguard_d4") == 1
        return
    play.click("up:swap:h01:iron_d6")
    assert "iron_d6" in engine.combat.combatants["h01"].equipped_dice_ids, "the first press only warns"
    assert play.ctrl.message_is_error and "gives up the larger die" in play.ctrl.message
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    assert "Confirm: give up Iron d6" in drawn and "Confirm: give up Iron d6" not in shortened
    play.click("up:swap:h01:iron_d6")
    assert "vanguard_d4" in engine.combat.combatants["h01"].equipped_dice_ids
    assert "iron_d6" not in engine.combat.combatants["h01"].equipped_dice_ids


@pytest.mark.parametrize("size", SIZES)
def test_the_outcome_screen_gives_a_tip_only_for_a_mechanic_that_went_unused(tmp_path, monkeypatch, size, font):
    play = Play(tmp_path, ["scout"], seed=3, size=size)
    play.begin()
    play.to_input()
    for hero in play.combat.side("hero"):
        hero.hp, hero.mana, hero.shields = 1, 0, 0
    play.until(lambda: False)  # passes every turn and skips every stage
    assert play.ctrl.screen == Screen.OUTCOME
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    tips = [t for t in drawn if t.startswith("Tip: ")]
    assert any("no reroll was used" in t for t in tips)
    assert not [t for t in shortened if t.startswith("Tip: ")]
    assert play.ctrl.outcome_tips() == tips

    used = Play(tmp_path, ["scout"], seed=3, size=size)
    used.begin()
    used.to_roll_prompt()
    used.key(pygame.K_r)
    used.key(pygame.K_r)  # one reroll
    for hero in used.combat.side("hero"):
        hero.hp, hero.mana, hero.shields = 1, 0, 0
    used.until(lambda: False)
    assert used.ctrl.screen == Screen.OUTCOME
    assert not any("no reroll was used" in t for t in used.ctrl.outcome_tips())


def test_the_status_bar_names_the_rules_and_the_content_version_separately(tmp_path, monkeypatch):
    from battle_dice import RULES_VERSION

    ctrl = AppController(fixed_seed=1, log_dir=tmp_path / "logs")
    app = GameApp(ctrl, size=(1280, 720), headless=True, animations=False)
    drawn, shortened = record_text(monkeypatch)
    app.frame(0)
    label = f"rules {RULES_VERSION}   content {ctrl.content.content_version}"
    assert label in drawn and label not in shortened
    assert not any("features" in text for text in drawn), "with every gate off the status bar is as it always was"


@pytest.mark.parametrize("size", SIZES)
def test_the_status_bar_names_an_enabled_feature_gate(tmp_path, monkeypatch, size):
    """A screenshot or a bug report must show that the game was launched with a gate on."""
    from battle_dice import RULES_VERSION

    ctrl = AppController(fixed_seed=1, log_dir=tmp_path / "logs", features=["class_evolution_v1"])
    app = GameApp(ctrl, size=size, headless=True, animations=False)
    drawn, shortened = record_text(monkeypatch)
    app.frame(0)
    label = f"rules {RULES_VERSION}   content {ctrl.content.content_version}   features: class_evolution_v1"
    assert label in drawn and label not in shortened
