"""The required screens (section 13), drawn from controller snapshots with the immediate-mode toolkit.

Screens never mutate rules state. Buttons call controller methods, which submit commands.
Status is always shown as text or shape as well as color (HP numbers, "DOWNED", "KEPT",
"TARGET 1", hatched disabled buttons), and every disabled control carries its reason.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any

import pygame

from battle_dice import RULES_VERSION
from battle_dice.app.controller import AppController
from battle_dice.core.models import CombatPhase
from battle_dice.features import describe as describe_features
from battle_dice.ui.toolkit import UI, Theme

NUMBER_KEYS = (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9)
CATEGORY_COLORS = {
    "attack": Theme.ENEMY,
    "defense": Theme.SHIELD,
    "healing": Theme.GOOD,
    "status": Theme.CORRUPT,
    "resource": Theme.MANA,
    "blank": Theme.FAINT,
}
PHASE_LABELS = {
    CombatPhase.ADVANCE_TIMELINE: "Timeline advancing",
    CombatPhase.ACTOR_START: "Activation start",
    CombatPhase.HERO_ROLL: "Roll dice",
    CombatPhase.KEEP_REROLL: "Keep, reroll and plan",
    CombatPhase.ACTION_PLAN: "Plan review",
    CombatPhase.LOCK_PLAN: "Plan locked",
    CombatPhase.ACTION_RESOLVE: "Resolving actions",
    CombatPhase.ENEMY_INTENT: "Enemy choosing",
    CombatPhase.REVEAL_INTENT: "Enemy intent revealed",
    CombatPhase.GUARD_WINDOW: "Reaction: Guard stage",
    CombatPhase.RESOURCE_WINDOW: "Reaction: Resource stage",
    CombatPhase.INTERRUPT_WINDOW: "Reaction: Interrupt stage",
    CombatPhase.ENEMY_RESOLVE: "Enemy action resolving",
    CombatPhase.ACTOR_END: "Activation end",
    CombatPhase.TERMINAL_CHECK: "Checking outcome",
    CombatPhase.VICTORY: "Victory",
    CombatPhase.DEFEAT: "Defeat",
}


def status_bar(ui: UI, ctrl: AppController, extra: str = "") -> None:
    ui.panel(0, 694, 1280, 26, fill=(12, 13, 18), border=(12, 13, 18))
    text, is_error = ui.status_line(ctrl.message, ctrl.message_is_error, ctrl.message_serial)
    # The right-hand text keeps its usual 250 units; it only grows when a feature gate adds to it.
    extra_width = max(250, ui.text_width(extra, 14) + 4) if extra else 0
    ui.text(10, 699, text, 15, Theme.WARN if is_error else Theme.TEXT, max_width=1250 - extra_width if extra else 1260)
    if extra:
        ui.text(1270, 699, extra, 14, Theme.FAINT, align="right", max_width=extra_width)


def draw_die_faces(ui: UI, x: float, y: float, w: float, die: dict[str, Any], highlight_face: int | None = None,
                   max_rows: int = 8) -> float:
    """List every distinct face with its frequency and exact probability. Returns the next y."""
    ui.sprite(ui.assets.die_key(die["size"]), x, y - 2, 20, 20)
    ui.text(x + 24, y, f"{die['name']}  (d{die['size']}, {die['size']} faces, v{die['definition_version']})", 15, Theme.ACCENT, bold=True, max_width=w - 24)
    y += 20
    for group in die["groups"][:max_rows]:
        face = group["face"]
        rolled = highlight_face is not None and (highlight_face + 1) in group["face_numbers"]
        color = CATEGORY_COLORS[face["category"]]
        text_color = Theme.TEXT if rolled else Theme.DIM
        marker = ">" if rolled else " "
        odds = f"x{group['count']}  {group['probability']}"
        room = w - 54 - ui.text_width(odds, 14) - 10
        line = f"{face['name']}: {face['text']}"
        ui.text(x, y, f"{marker}{face['glyph']}", 14, color, bold=True)
        ui.text(x + w, y, odds, 14, text_color, align="right")
        if ui.text_width(line, 14, rolled) <= room:
            ui.text(x + 54, y, line, 14, text_color, bold=rolled)
            y += 17
        else:  # narrow panel: name beside the odds, the rules text in full underneath
            ui.text(x + 54, y, face["name"], 14, text_color, bold=rolled, max_width=room)
            y = ui.paragraph(x + 54, y + 16, face["text"], w - 54, 13, text_color, line_height=15, max_lines=2) + 2
    return y


# --------------------------------------------------------------------------------------------
# Main menu and controls
# --------------------------------------------------------------------------------------------


def draw_main_menu(ui: UI, ctrl: AppController, quit_action: Callable[[], Any]) -> None:
    ui.backdrop(0, 0, 1280, 694, wall_rows=2, dim=175)
    for position, class_id in enumerate(("squire", "apprentice", "scout")):
        ui.sprite(ui.assets.combatant_key(class_id), 150 + position * 104, 330, 96, 96)
    for position, archetype in enumerate(("goblin", "hex_adept", "captain")):
        ui.sprite(ui.assets.combatant_key(archetype), 826 + position * 104, 330, 96, 96)
    for position, size in enumerate((4, 6, 8)):
        ui.sprite(ui.assets.die_key(size), 574 + position * 46, 254, 40, 40)
    ui.text(640, 150, "BATTLE DICE", 64, Theme.ACCENT, bold=True, align="center")
    ui.text(640, 232, "A turn-based tactical dice RPG. Two battles, one upgrade, every die face visible.", 18, Theme.DIM, align="center")
    ui.button("menu:new", 490, 300, 300, 52, "New Run  (N)", ctrl.new_run, hotkeys=(pygame.K_n,), default=True, size=22,
              tooltip="Configure a party of 1 to 5 heroes and start Battle 1.")
    ui.button("menu:controls", 490, 362, 300, 52, "Controls  (C)", ctrl.show_controls, hotkeys=(pygame.K_c,), size=22,
              tooltip="Mouse and keyboard controls, and how a turn works.")
    ui.button("menu:settings", 490, 424, 300, 52, "Settings  (S)", ctrl.open_settings, hotkeys=(pygame.K_s,), size=22,
              tooltip="Class Evolution, the dice seed, animation, window size and the saved profile.")
    ui.button("menu:quit", 490, 486, 300, 52, "Quit  (Q)", quit_action, hotkeys=(pygame.K_q,), size=22, tooltip="Close the game.")
    ui.escape_action = quit_action
    ui.text(640, 566, "Tab / arrow keys move focus.  Enter or Space activates.  Every screen works with mouse or keyboard.", 15, Theme.FAINT, align="center")
    for line, problem in enumerate(ctrl.settings_problems[:2]):
        ui.text(640, 596 + line * 20, problem, 14, Theme.WARN, align="center", max_width=1200)
    if ctrl.progression_error:
        ui.text(640, 640, ctrl.progression_error, 14, Theme.WARN, align="center", max_width=1200)
    versions = f"rules {RULES_VERSION}   content {ctrl.content.content_version}"
    status_bar(ui, ctrl, f"{versions}   {describe_features(ctrl.features)}".rstrip())


CONTROLS_TEXT = [
    ("Everywhere", "Tab / Shift+Tab or the arrow keys move a focus ring; Enter or Space then activates the ringed control. With no ring, Enter activates the screen's main button. Hotkeys and clicks never move the ring; Esc clears it. Point at or focus a control to read what it does; disabled controls explain why."),
    ("Party setup", "1 / 2 / 3 add a Squire / Apprentice / Scout.  Each hero has a Row and a Remove button.  B or Enter begins the encounter."),
    ("Your activation", "R rolls, then R rerolls every die you did not Keep.  Z / X toggle Keep on die 1 / 2.  1 / 2 plan the rolled face of die 1 / 2; when a target is needed, press the number shown on a legal target (or click it).  O swaps the order of equal-speed actions.  C clears the plan.  Enter confirms the whole plan.  P passes."),
    ("Enemy activation", "The enemy's action and targets are revealed first.  Each reacting hero has a numbered row: press its number, then, if it asks for an ally, the ally's number (or click the ally's button directly).  S skips the current stage (Guard, then Resource, then Interrupt); A skips every remaining stage for this enemy action."),
    ("Pacing", "Automatic steps play on a short timer.  F toggles fast mode.  Space steps immediately while the game is resolving.  M turns animation off or on (reduced motion)."),
    ("During a run", "Esc opens the menu: resume, read these controls, or abandon the run.  While a target is being chosen, Esc cancels that choice first."),
    ("Upgrade", "After Battle 1, pick a hero and a die, select one of three cards, then A applies it.  Optionally swap one die per hero or change rows, then Enter starts Battle 2."),
    ("Reading the board", "A yellow 'Now ...' line under a face or a planned action is the amount that will really happen when it differs from the printed one (Weaken, class bonuses).  HP, SH (shield), MP (mana), CR (corruption).  PSN (Poison) / WKN (Weaken) / SPD+ (Speed Up) show total stacks and, in brackets, activations left.  Point at or focus a unit card to list its abilities, dice and every status in the centre panel.  The gauge bar fills to 100 by speed each tick; the Next row forecasts who acts."),
]


def draw_controls(ui: UI, ctrl: AppController, back: Callable[[], Any] | None = None) -> None:
    back = back or ctrl.to_main_menu
    ui.text(40, 28, "Controls", 34, Theme.ACCENT, bold=True)
    y = 80.0
    for heading, body in CONTROLS_TEXT:
        ui.text(40, y, heading, 17, Theme.TEXT, bold=True)
        y = ui.paragraph(240, y, body, 1000, 15, Theme.DIM, line_height=19) + 9
    ui.button("controls:back", 40, 636, 220, 44, "Back  (Esc)", back, hotkeys=(pygame.K_b,), default=True)
    ui.escape_action = back
    status_bar(ui, ctrl)


# --------------------------------------------------------------------------------------------
# Party setup
# --------------------------------------------------------------------------------------------


def draw_party_setup(ui: UI, ctrl: AppController) -> None:
    if ctrl.progression is not None:  # Class Evolution: the party is made of saved heroes
        draw_roster_setup(ui, ctrl)
        return
    minimum, maximum = ctrl.party_limits()
    ui.text(24, 14, "Party Setup", 30, Theme.ACCENT, bold=True)
    ui.text(250, 26, f"{len(ctrl.party)} / {maximum} heroes.  Any mix of classes, duplicates allowed.  Starting dice are fixed by class.", 16, Theme.DIM)

    ui.panel(16, 60, 430, 470, "Party (click a hero to inspect)")
    for index in range(maximum):
        y: float = 90 + index * 86
        if index < len(ctrl.party):
            member = ctrl.party[index]
            cls = ctrl.content.class_def(member["class_id"])
            selected = index == ctrl.selected_slot
            ui.panel(26, y, 410, 78, fill=Theme.PANEL_ALT, border=Theme.ACCENT if selected else Theme.BORDER, width=2 if selected else 1)
            ui.sprite(ui.assets.combatant_key(member["class_id"]), 30, y + 11, 56, 56)
            ui.button(f"slot:{index}:select", 90, y + 8, 124, 62, f"{index + 1}. {cls['name']}",
                      partial(setattr, ctrl, "selected_slot", index), selected=selected,
                      sublabel=f"HP {cls['max_hp']}  SPD {cls['speed']}",
                      tooltip=f"Inspect {cls['name']}: stats, abilities and dice.")
            ui.button(f"slot:{index}:row", 222, y + 8, 110, 62, f"Row: {member['row'].capitalize()}",
                      partial(ctrl.toggle_party_row, index), sublabel="toggle",
                      tooltip="Front-row heroes shield the back row from melee. Click to switch rows.")
            ui.button(f"slot:{index}:remove", 340, y + 8, 88, 62, "Remove", partial(ctrl.remove_hero, index),
                      tooltip="Remove this hero from the party.")
        else:
            ui.panel(26, y, 410, 78, fill=(24, 27, 35))
            ui.text(231, y + 30, "empty slot", 15, Theme.FAINT, align="center")

    full = len(ctrl.party) >= maximum
    class_ids = sorted(ctrl.content.classes, key=lambda c: ["squire", "apprentice", "scout"].index(c) if c in ("squire", "apprentice", "scout") else 9)
    for position, class_id in enumerate(class_ids):
        cls = ctrl.content.class_def(class_id)
        ui.button(f"add:{class_id}", 16 + position * 146, 540, 138, 50, f"+ {cls['name']} ({position + 1})",
                  partial(ctrl.add_hero, class_id), enabled=not full,
                  reason=f"The party already has {maximum} heroes.", hotkeys=(NUMBER_KEYS[position],),
                  tooltip=f"Add a {cls['name']} ({cls['scheduling']['label']}). Suggested row: {cls['suggested_row']}.")

    problem = ctrl.begin_problem()
    ui.button("party:begin", 16, 606, 284, 60, "Begin Encounter  (B)", ctrl.begin_run, enabled=problem is None,
              reason=problem, hotkeys=(pygame.K_b,), default=True, size=20,
              tooltip="Start Battle 1 with this party.")
    ui.button("party:back", 308, 606, 138, 60, "Back  (Esc)", ctrl.to_main_menu, tooltip="Return to the main menu.")
    ui.escape_action = ctrl.to_main_menu

    # Inspector: the selected hero's class, or the first class when the party is empty.
    if ctrl.party:
        class_id = ctrl.party[min(ctrl.selected_slot, len(ctrl.party) - 1)]["class_id"]
    else:
        class_id = class_ids[0]
    info = ctrl.class_view(class_id)
    ui.panel(458, 60, 806, 606, f"Class: {info['name']}")
    ui.sprite(ui.assets.combatant_key(class_id), 1206, 64, 50, 50)
    x, y = 472.0, 88.0
    ui.text(x, y, f"HP {info['start_hp']}/{info['max_hp']}    Speed {info['speed']}    Initiative {info['base_initiative']}    "
            f"Mana {info['start_mana']}/{info['max_mana']}    Corruption {info['start_corruption']}/{info['max_corruption']}    "
            f"Rerolls {info['rerolls']}    Suggested row: {info['suggested_row']}", 15, Theme.TEXT, max_width=724)
    y += 26
    for label, body in (
        ("Scheduling", f"{info['scheduling']['label']}: {info['scheduling']['summary']}"),
        ("Passive", f"{info['passive']['name']}: {info['passive']['summary']}"),
        ("Reaction", f"{info['reaction_def']['name']} ({info['reaction_def']['stage'].capitalize()} stage, {info['reaction_def']['mana_cost']} mana, "
                     f"1 use until this hero's next activation): {info['reaction_def']['summary']}"),
    ):
        ui.text(x, y, label, 15, Theme.ACCENT, bold=True)
        y = ui.paragraph(x + 96, y, body, 684, 15, Theme.DIM, line_height=19, max_lines=3) + 5
    y += 4
    ui.text(x, y, "Starting dice (every face, its frequency and probability)", 15, Theme.TEXT, bold=True)
    y += 22
    for die in info["dice"]:
        y = draw_die_faces(ui, x, y, 770, die) + 8
    ui.text(x, y, "Bench die (can be swapped in after Battle 1)", 15, Theme.TEXT, bold=True)
    y += 22
    for die in info["bench"]:
        y = draw_die_faces(ui, x, y, 770, die) + 6
    status_bar(ui, ctrl)


# --------------------------------------------------------------------------------------------
# Combat HUD
# --------------------------------------------------------------------------------------------


STATUS_ORDER = ("poison", "weaken", "speed_up")


def _status_forms(c: dict[str, Any]) -> list[str]:
    """One status summary per kind, from most to least verbose. The card uses the first that fits.

    Stacks are summed per kind; the bracket is the remaining activations (a range when the
    stacks expire at different times). The inspect panel lists every stack in full.
    """
    groups: dict[str, dict[str, Any]] = {}
    for status in sorted(c["statuses"], key=lambda s: STATUS_ORDER.index(s["kind"]) if s["kind"] in STATUS_ORDER else len(STATUS_ORDER)):
        group = groups.setdefault(status["kind"], {"glyph": status["glyph"], "stacks": 0, "low": status["remaining"], "high": status["remaining"]})
        group["stacks"] += status["stacks"]
        group["low"] = min(group["low"], status["remaining"])
        group["high"] = max(group["high"], status["remaining"])

    def left(group: dict[str, Any]) -> str:
        return str(group["low"]) if group["low"] == group["high"] else f"{group['low']}-{group['high']}"

    return [
        "  ".join(f"{g['glyph']} x{g['stacks']} ({left(g)})" for g in groups.values()),
        " ".join(f"{g['glyph']} {g['stacks']}({left(g)})" for g in groups.values()),
        " ".join(f"{g['glyph'][0]}{g['stacks']}({left(g)})" for g in groups.values()),
    ]


def _combatant_tooltip(c: dict[str, Any]) -> str:
    if c["side"] == "hero":
        return f"{c['name']}: {c['scheduling']['label']}, speed {c['speed']}, gauge {c['gauge']}. Details are in the centre panel."
    return f"{c['name']}: speed {c['speed']}, gauge {c['gauge']}, {len(c['actions'])} abilities. Details are in the centre panel."


def draw_combatant_card(ui: UI, ctrl: AppController, c: dict[str, Any], x: float, y: float, view: dict[str, Any],
                        target_numbers: dict[str, int], targeting: dict[str, Any] | None) -> None:
    w, h = 222, 70
    active = view["active_combatant_id"] == c["id"]
    standing = c["state"] == "standing"
    side_color = Theme.HERO if c["side"] == "hero" else Theme.ENEMY
    key = f"unit:{c['id']}"
    intent = view.get("intent")
    intended = bool(intent and c["id"] in intent["target_ids"] and not intent["cancelled"])

    enabled, reason = True, None
    action: Callable[[], Any] | None = None
    hotkeys: tuple[int, ...] = ()
    if targeting is not None:
        if c["id"] in targeting["eligible_target_ids"]:
            action = partial(ctrl.choose_target, c["id"])
            number = target_numbers.get(c["id"])
            if number is not None and number <= len(NUMBER_KEYS):
                hotkeys = (NUMBER_KEYS[number - 1],)
        else:
            enabled = False
            if c["id"] in targeting["protected_target_ids"]:
                reason = f"{c['name']} is protected: melee must target the standing front row first."
            elif not standing:
                reason = f"{c['name']} is not standing."
            else:
                reason = f"{c['name']} is not a legal target for {targeting['face']['name']}."
    rect = ui.r(x, y, w, h)
    ui.register(key, rect, action, enabled, reason, _combatant_tooltip(c), hotkeys)

    fill = Theme.PANEL_ALT if standing else (26, 26, 30)
    if active:
        glow = ui.anim.pulse()  # the acting card's border breathes between accent and white
        red, green, blue = (int(a + (255 - a) * 0.55 * glow) for a in Theme.ACCENT)
        border = (red, green, blue)
    else:
        border = side_color if standing else Theme.FAINT
    ui.panel(x, y, w, h, fill=fill, border=border, width=3 if active else 1)
    ui.decorate(key, rect, enabled)
    sprite_key = ui.assets.combatant_key(ctrl.sprite_class(c["archetype_id"]))
    if standing or c["side"] == "hero":
        ui.sprite(sprite_key, x + 3, y + 21, 44, 44, variant="" if standing else "grey")
    else:
        ui.sprite("marker_downed", x + 3, y + 21, 44, 44)

    tag = ""
    if not standing:
        tag = "DOWNED" if c["side"] == "hero" else "DEFEATED"
    elif active:
        tag = "ACTING"
    if targeting is not None and c["id"] in target_numbers:
        tag = f"TARGET {target_numbers[c['id']]}"
    elif intended:
        tag = "TARGETED"
    name_room = w - 12 - (ui.text_width(tag, 14, True) + 8 if tag else 0)
    ui.text(x + 6, y + 3, ui.fit_name(c["name"], 15, True, name_room), 15, Theme.TEXT if standing else Theme.FAINT, bold=True)
    if tag:
        ui.text(x + w - 6, y + 3, tag, 14, Theme.ACCENT if tag.startswith(("TARGET", "ACTING")) else Theme.BAD, bold=True, align="right")

    shown_hp = ui.anim.shown_hp(c["id"], c["hp"])
    ui.bar(x + 50, y + 22, 60, 11, shown_hp, c["max_hp"], Theme.GOOD if standing else Theme.FAINT)
    ui.text(x + 114, y + 19, f"HP {c['hp']}/{c['max_hp']}", 14, Theme.TEXT)
    ui.text(x + w - 6, y + 19, f"SH {c['shields']}", 14, Theme.SHIELD if c["shields"] else Theme.FAINT, bold=bool(c["shields"]), align="right")
    if c["side"] == "hero":
        backlash = "!" if c.get("corruption_backlash") else ""
        ui.text(x + 50, y + 36, f"MP {c['mana']}/{c['max_mana']}", 14, Theme.MANA)
        ui.text(x + 106, y + 36, f"CR {c['corruption']}/{c['max_corruption']}{backlash}", 14, Theme.BAD if backlash else Theme.CORRUPT, bold=bool(backlash))
        ui.text(x + w - 6, y + 36, f"React {c['reaction_charges']}", 14, Theme.TEXT if c["reaction_charges"] else Theme.FAINT, align="right")
    else:
        ui.text(x + 50, y + 36, f"SPD {c['speed']}   {c['row'].capitalize()} row", 14, Theme.DIM)

    # Bottom line: gauge bar, gauge number, status summary. Fonts differ a lot in width between
    # machines, so the layout is chosen by measuring: the status text shortens first, then the
    # gauge number gives way, then the gauge bar narrows and the text shrinks. The bar never goes.
    gauge_number, bar_width, status_text, status_size, status_room = True, 36.0, "", 13, 0.0
    if c["statuses"]:
        forms = _status_forms(c)
        layouts = (
            [(True, 36.0, 96.0, form, 13) for form in forms[:2]]
            + [(False, 36.0, 124.0, form, 13) for form in forms]
            + [(False, 16.0, 146.0, forms[2], size) for size in (13, 12, 11, 10)]
        )
        chosen = next((layout for layout in layouts if ui.text_width(layout[3], layout[4], True) <= layout[2]), layouts[-1])
        gauge_number, bar_width, status_room, status_text, status_size = chosen
    ui.bar(x + 50, y + 56, bar_width, 8, min(c["gauge"], view["ready_threshold"]), view["ready_threshold"], Theme.GAUGE)
    if gauge_number:
        ui.text(x + 90, y + 51, f"G{c['gauge']}", 13, Theme.FAINT)
    kinds = list(dict.fromkeys(status["kind"] for status in c["statuses"]))
    for position, kind in enumerate(kinds[:3]):  # badges at the character's feet; the text stays as well
        ui.sprite(ui.assets.status_key(kind), x + 2 + position * 15, y + 52, 16, 16)
    if status_text:
        ui.text(x + w - 6, y + 51, status_text, status_size, Theme.WARN, bold=True, align="right", max_width=status_room)


def draw_formation(ui: UI, ctrl: AppController, view: dict[str, Any], targeting: dict[str, Any] | None) -> None:
    target_numbers: dict[str, int] = {}
    if targeting is not None:
        for number, cid in enumerate(targeting["eligible_target_ids"], start=1):
            target_numbers[cid] = number
    columns = {
        ("hero", "back"): (12, "Heroes: back row"),
        ("hero", "front"): (244, "Heroes: front row"),
        ("enemy", "front"): (814, "Enemies: front row"),
        ("enemy", "back"): (1046, "Enemies: back row"),
    }
    for (side, row), (x, title) in columns.items():
        ui.text(x + 111, 90, title, 14, Theme.HERO if side == "hero" else Theme.ENEMY, bold=True, align="center")
        members = [c for c in view["combatants"] if c["side"] == side and c["row"] == row]
        for index, c in enumerate(members[:5]):
            draw_combatant_card(ui, ctrl, c, x, 108 + index * 73, view, target_numbers, targeting)


def inspected_combatant(ui: UI, view: dict[str, Any]) -> dict[str, Any] | None:
    """The unit whose card is pointed at, or failing that focused (from the previous frame)."""
    for key in (ui.hover_key, ui.focus_key):
        if key and key.startswith("unit:"):
            return next((c for c in view["combatants"] if c["id"] == key[5:]), None)
    return None


def draw_inspect(ui: UI, c: dict[str, Any], view: dict[str, Any], top: float, height: float) -> None:
    """Everything about one unit in full sentences: stats, every status stack, abilities or dice."""
    x, width = 486.0, 306.0
    ui.panel(478, top, 324, height, f"Inspect: {c['name']}", border=Theme.HERO if c["side"] == "hero" else Theme.ENEMY, width=2)
    bottom = top + height - 6
    y = top + 26

    def para(text: str, color: tuple[int, int, int] = Theme.DIM, bold: bool = False) -> None:
        nonlocal y
        budget = int((bottom - y) // 15)
        if budget >= 1:
            y = ui.paragraph(x, y, text, width, 13, color, line_height=15, max_lines=budget, bold=bold)

    state = "" if c["state"] == "standing" else ("   DOWNED" if c["side"] == "hero" else "   DEFEATED")
    para(f"HP {c['hp']}/{c['max_hp']}   SH {c['shields']}   SPD {c['speed']}   Gauge {c['gauge']}/{view['ready_threshold']}   "
         f"{c['row'].capitalize()} row{state}", Theme.TEXT)
    if c["side"] == "hero":
        para(f"MP {c['mana']}/{c['max_mana']}   CR {c['corruption']}/{c['max_corruption']}   Reaction charges {c['reaction_charges']}", Theme.TEXT)
    if c["statuses"]:
        for status in c["statuses"]:
            plural = "" if status["remaining"] == 1 else "s"
            para(f"{status['label']} x{status['stacks']}, {status['remaining']} activation{plural} left: {status['effect']}.", Theme.WARN)
    else:
        para("No status effects.", Theme.FAINT)
    y += 4
    if c["side"] == "enemy":
        para("Abilities (a higher weight is chosen more often)", Theme.TEXT, bold=True)
        for ability in c["actions"]:
            para(f"{ability['name']} [{ability['glyph']}, weight {ability['weight']}]: {ability['text']}.")
        return
    para("Dice", Theme.TEXT, bold=True)
    for die in c["dice"]:
        faces = ", ".join(g["face"]["name"] + (f" x{g['count']}" if g["count"] > 1 else "") for g in die["groups"])
        para(f"{die['name']}: {faces}.")
    reaction = c["reaction"]
    para(f"Reaction, {reaction['name']} ({reaction['stage'].capitalize()} stage, {reaction['mana_cost']} mana): {reaction['summary']}")
    para(f"Passive, {c['passive']['name']}: {c['passive']['summary']}")
    para(f"{c['scheduling']['label']}: {c['scheduling']['summary']}")


def draw_center(ui: UI, ctrl: AppController, view: dict[str, Any], inspect: dict[str, Any] | None = None) -> None:
    intent = view.get("intent")
    log_top = 92.0
    if intent is not None:
        ui.panel(478, 88, 324, 144, "Enemy intent (committed)", border=Theme.ENEMY, width=2)
        state = "CANCELLED" if intent["cancelled"] else "elite-resistant" if intent["elite_resistant"] else "interruptible" if intent["interruptible"] else "not interruptible"
        actor_archetype = next((c["archetype_id"] for c in view["combatants"] if c["id"] == intent["actor_id"]), "")
        ui.sprite(ui.assets.combatant_key(ctrl.sprite_class(actor_archetype)), 760, 106, 36, 36)
        ui.sprite(ui.assets.category_key(intent["category"]), 722, 106, 36, 36)
        # The lines flow, so a long name or rule wraps instead of being cut on a wide font.
        y = ui.paragraph(488, 108, f"{intent['actor_name']}: {intent['name']}", 230, 16, Theme.TEXT, line_height=18, max_lines=2, bold=True)
        y = ui.paragraph(488, y + 1, f"{intent['glyph']} {intent['power']}: {intent['text']}", 230, 14, Theme.DIM, line_height=16, max_lines=2)
        y = max(y + 2, 146.0)  # below the two sprites, where the full width is free
        y = ui.paragraph(488, y, "Targets: " + ", ".join(intent["target_names"]), 304, 14, Theme.ACCENT, line_height=16, max_lines=2)
        mods = []
        if intent["forecast"]["weaken"]:
            mods.append(f"-{intent['forecast']['weaken']} damage (Weaken)")
        if intent["damage_reduction"]:
            mods.append(f"-{intent['damage_reduction']} damage")
        if intent["magnitude_reduction"]:
            mods.append(f"-{intent['magnitude_reduction']} magnitude")
        extra = f"  ({', '.join(mods)})" if mods else ""
        ui.text(488, y + 2, f"[{state}]{'' if intent['reactable'] else ' [no reactions]'}{extra}", 14,
                Theme.BAD if intent["cancelled"] else Theme.WARN, bold=True, max_width=304)
        log_top = 238.0
    height = 470 - log_top
    if inspect is not None:
        draw_inspect(ui, inspect, view, log_top, height)
        return
    ui.panel(478, log_top, 324, height, "Combat log")
    rows = int((height - 30) // 16)
    lines: list[str] = []
    for entry in ctrl.log_lines(60):
        lines.extend(ui.wrap_lines(entry, 306, 13))
    y = log_top + 24
    for line in lines[-rows:]:
        ui.text(486, y, line, 13, Theme.TEXT if line.startswith((">", "-", "*")) else Theme.DIM, max_width=310)
        y += 16


def draw_header(ui: UI, ctrl: AppController, view: dict[str, Any], fast: bool) -> None:
    names = {c["id"]: c["name"] for c in view["combatants"]}
    archetypes = {c["id"]: c["archetype_id"] for c in view["combatants"]}
    ui.panel(0, 0, 1280, 40, fill=(12, 13, 18), border=(12, 13, 18))
    ui.text(12, 9, f"Battle {view['battle']} of {view['battle_count']}", 20, Theme.ACCENT, bold=True)
    actor = names.get(view["active_combatant_id"] or "", "nobody")
    ui.text(200, 12, f"Tick {view['timeline_tick']}    Phase: {PHASE_LABELS.get(view['combat_phase'], view['combat_phase'])}    Acting: {actor}",
            16, Theme.TEXT, max_width=760)
    ui.text(1166, 12, f"Seed {view['seed']}   {'FAST' if fast else 'normal'} (F)", 14, Theme.FAINT, align="right")
    ui.text(12, 52, "Next:", 15, Theme.DIM, bold=True)
    x = 62.0
    for position, cid in enumerate(view["forecast"][:8]):
        name = names.get(cid, cid)
        hero = cid.startswith("h")
        ui.panel(x, 46, 146, 28, fill=Theme.PANEL, border=Theme.ACCENT if position == 0 else Theme.HERO if hero else Theme.ENEMY,
                 width=2 if position == 0 else 1)
        ui.sprite(ui.assets.combatant_key(ctrl.sprite_class(archetypes.get(cid, ""))), x + 3, 49, 22, 22)
        ui.text(x + 28, 53, ui.fit_name(name, 13, False, 114), 13, Theme.TEXT)
        x += 151


def draw_planner(ui: UI, ctrl: AppController, view: dict[str, Any]) -> dict[str, Any] | None:
    """Hero action planner. Returns the die option awaiting a target, if any."""
    turn = view["hero_turn"]
    ui.panel(8, 476, 1264, 214, f"{turn['hero_name']}: {turn['policy_text']}", border=Theme.HERO, width=2)
    if not turn["rolled"]:
        ui.button("plan:roll", 490, 550, 300, 70, "Roll Dice  (R)", ctrl.roll, hotkeys=(pygame.K_r,), default=True, size=24,
                  tooltip="Roll every equipped die once. You then get rerolls for the dice you do not keep.")
        ui.text(640, 632, f"{turn['rerolls_total']} rerolls this activation.", 15, Theme.DIM, align="center")
        return None

    targeting = None
    drafted = {a["die_id"]: a for a in ctrl.draft}
    inspect = ctrl.inspect_die
    for index, die in enumerate(turn["dice"][:2]):
        x = 16 + index * 256
        face = die["face"]  # always the real result; the tumble only animates the artwork
        tumbling = ui.anim.is_tumbling(die["die_id"])
        in_plan = die["die_id"] in drafted
        awaiting = ctrl.targeting_die == die["die_id"]
        if awaiting:
            targeting = die
        if ui.is_hot(f"die:{die['die_id']}:use") or ui.is_hot(f"die:{die['die_id']}:keep"):
            inspect = die["die_id"]
        border = Theme.ACCENT if in_plan or awaiting else Theme.BORDER if tumbling else CATEGORY_COLORS[face["category"]]
        ui.panel(x, 500, 248, 184, fill=Theme.PANEL_ALT, border=border, width=2)
        ui.text(x + 8, 505, f"Die {index + 1}: {die['die_name']}", 14, Theme.DIM, bold=True, max_width=150)
        # A die in the plan or being aimed is not marked "will reroll": the player has just chosen to use it.
        state = "KEPT" if die["kept"] else "" if in_plan or awaiting else "will reroll"
        ui.text(x + 240, 505, state, 14, Theme.ACCENT if die["kept"] else Theme.FAINT, bold=die["kept"], align="right")
        ui.sprite(ui.assets.die_key(die["die_size"]), x + 200, 521, 44, 44)
        if tumbling:
            # No face name or rules text until the die settles: the panel never states a face
            # that was not rolled. The combat log and the die list already show the result.
            art = die["die"]["faces"][ui.anim.tumbling_face(die["die_id"], die["die_size"], die["face_index"])]
            ui.sprite(ui.assets.category_key(art["category"]), x + 4, 521, 44, 44)
            ui.text(x + 52, 533, "Rolling ...", 17, Theme.ACCENT, bold=True, max_width=146)
            ui.text(x + 8, 598, f"d{die['die_size']}", 13, Theme.FAINT)
        else:
            ui.sprite(ui.assets.category_key(face["category"]), x + 4, 521, 44, 44)
            heading = f"{face['glyph']}  {face['name']}"
            heading_size = next((size for size in (17, 15, 13, 12) if ui.text_width(heading, size, True) <= 146), 12)
            ui.text(x + 52, 533 + (17 - heading_size) * 0.6, heading, heading_size, CATEGORY_COLORS[face["category"]], bold=True, max_width=146)
            # The amount that will really happen, when it differs from the printed one (Weaken, class bonuses).
            note = f"Now {die['forecast']['note']}" if die["forecast"]["note"] else ""
            styles = ((13, True), (12, True), (11, True), (11, False), (10, False))
            note_size, note_bold = next((style for style in styles if ui.text_width(note, *style) <= 232), styles[-1])
            one_line = ui.text_width(face["text"], 14, False) <= 232
            if note and one_line:
                ui.text(x + 8, 567, face["text"], 14, Theme.TEXT, max_width=232)
                ui.text(x + 8, 582, note, note_size, Theme.WARN, bold=note_bold, max_width=232)
            else:
                ui.paragraph(x + 8, 567, face["text"], 232, 14, Theme.TEXT, line_height=15, max_lines=2)
            if note and not one_line:
                # Two lines of rules text leave no free line: the forecast takes the place of the face details.
                ui.text(x + 8, 598, note, note_size, Theme.WARN, bold=note_bold, max_width=232)
            else:
                detail = f"Face {die['face_index'] + 1}/{die['die_size']}"
                if face["action_speed"] is not None:
                    detail += f"   speed {face['action_speed']}   target: {face['target_label']}"
                ui.text(x + 8, 598, detail, 13, Theme.FAINT, max_width=232)
            if die["reason"]:
                ui.text(x + 8, 612, die["reason"], 13, Theme.WARN, bold=True, max_width=232)
            elif in_plan:
                ui.text(x + 8, 612, "IN PLAN", 13, Theme.ACCENT, bold=True)
            elif awaiting:
                ui.text(x + 8, 612, "CHOOSE A TARGET", 13, Theme.ACCENT, bold=True)
            elif die.get("skill_note"):
                # An equipped skill widens what this face may do right now (Field Medic: a downed ally is a target).
                ui.text(x + 8, 612, die["skill_note"], 13, Theme.GOOD, bold=True, max_width=232)
        keep_key = (pygame.K_z, pygame.K_x)[index]
        ui.button(f"die:{die['die_id']}:keep", x + 8, 628, 112, 48, "Unkeep" if die["kept"] else "Keep",
                  partial(ctrl.toggle_keep, die["die_id"]), selected=die["kept"], hotkeys=(keep_key,),
                  sublabel=f"({'ZX'[index]})", tooltip="Kept dice are not rerolled. You can unkeep before a later reroll.")
        use_hotkeys = () if ctrl.targeting_die is not None else (NUMBER_KEYS[index],)
        ui.button(f"die:{die['die_id']}:use", x + 128, 628, 112, 48, "Remove" if in_plan else "Cancel" if awaiting else "Use",
                  partial(ctrl.use_die, die["die_id"]) if not awaiting else ctrl.cancel_targeting,
                  enabled=die["selectable"] or in_plan, reason=die["reason"], selected=in_plan or awaiting,
                  hotkeys=use_hotkeys, sublabel=f"({index + 1})",
                  tooltip=f"Plan {face['name']}: {face['text']}." if die["selectable"] else None)

    # Plan column
    px0 = 530
    preview = ctrl.plan_preview()
    ui.text(px0, 500, "Plan (resolves top to bottom)" if not preview["problem"] else "Plan (not legal yet)", 15, Theme.TEXT, bold=True)
    y = 520.0
    if not preview["ordered"] and not ctrl.draft:
        ui.text(px0, y, "No action selected yet.", 14, Theme.FAINT)
        y += 18
    for number, entry in enumerate(preview["ordered"], start=1):
        targets = ", ".join(entry["target_names"]) or "-"
        cost = f", {entry['mana_cost']} mana" if entry["mana_cost"] else ""
        line = f"{number}. {entry['name']} -> {targets}  (speed {entry['action_speed']}{cost})"
        # A long action name (a skill's, for one) is set smaller before it is ever cut off.
        line_size = next((size for size in (14, 13, 12, 11) if ui.text_width(line, size, True) <= 372), 11)
        ui.text(px0, y, line, line_size, Theme.TEXT, bold=True, max_width=372)
        if entry["forecast"]:
            ui.text(px0 + 14, y + 16, f"Now {entry['forecast']}", 12, Theme.WARN, bold=True, max_width=358)
            y += 34
        elif entry["fallback"]:
            ui.text(px0 + 14, y + 16, entry["fallback"], 12, Theme.FAINT, max_width=358)
            y += 34
        else:
            y += 18
    if preview["problem"]:
        y = ui.paragraph(px0, y, f"Not legal: {preview['problem']}", 372, 14, Theme.WARN, line_height=17, max_lines=3, bold=True)
    elif preview["ordered"]:
        ui.text(px0, y, f"Mana {preview['mana_before']} -> {preview['mana_after']}.  Unused dice are discarded.", 13, Theme.DIM, max_width=372)

    rerolls = turn["rerolls_remaining"]
    unkept = [d for d in turn["dice"] if not d["kept"]]
    reroll_reason = "No rerolls remaining this activation." if rerolls <= 0 else "Every die is kept; unkeep one to reroll." if not unkept else None
    ui.button("plan:reroll", px0, 628, 112, 48, "Reroll", ctrl.reroll, enabled=reroll_reason is None, reason=reroll_reason,
              hotkeys=(pygame.K_r,), sublabel=f"(R)  {rerolls} left",
              tooltip="Reroll every die that is not kept. Costs one reroll.")
    confirm_reason = ctrl.confirm_problem()
    ui.button("plan:confirm", px0 + 118, 628, 112, 48, "Confirm", ctrl.confirm_plan, enabled=confirm_reason is None,
              reason=confirm_reason, default=True, sublabel="(Enter)",
              tooltip="Lock the whole plan and its targets. It cannot be changed afterwards.")
    ui.button("plan:pass", px0 + 236, 628, 52, 48, "Pass", ctrl.pass_turn, hotkeys=(pygame.K_p,), sublabel="(P)",
              tooltip="End this activation without acting." if turn["has_legal_action"] else "No legal action is available: pass.")
    ui.button("plan:order", px0 + 294, 628, 86, 22, "Order (O)", ctrl.swap_plan_order, enabled=len(ctrl.draft) >= 2,
              reason="Needs two planned actions.", hotkeys=(pygame.K_o,), size=13,
              tooltip="Swap the order of the two actions. Class rules and action speed still decide first; this breaks ties.")
    ui.button("plan:clear", px0 + 294, 654, 86, 22, "Clear (C)", ctrl.clear_plan, enabled=bool(ctrl.draft) or ctrl.targeting_die is not None,
              reason="The plan is already empty.", hotkeys=(pygame.K_c,), size=13, tooltip="Remove every planned action.")
    if ctrl.targeting_die is not None:
        ui.escape_action = ctrl.cancel_targeting

    # Die inspector
    by_id = {d["die_id"]: d for d in turn["dice"]}
    shown = by_id.get(inspect or "") or (turn["dice"][0] if turn["dice"] else None)
    if shown is not None:
        ui.panel(918, 496, 346, 190, fill=(24, 27, 35))
        draw_die_faces(ui, 926, 502, 330, shown["die"], highlight_face=shown["face_index"])
        ctrl.inspect_die = shown["die_id"]
    return targeting


def draw_reactions(ui: UI, ctrl: AppController, view: dict[str, Any]) -> None:
    """One row per reacting hero (at most five), with that reaction's allies as buttons on the row.

    Mouse: click an ally button. Keyboard: the row's number, then the ally's number.
    """
    reaction = view["reaction"]
    intent = view["intent"]
    names = {c["id"]: c["name"] for c in view["combatants"]}
    stage = reaction["stage"]
    options = reaction["options"]
    ui.panel(8, 476, 1264, 214, f"Reaction window: stage {reaction['stage_number']} of 3: {stage.capitalize()}   (Guard -> Resource -> Interrupt -> enemy action)",
             border=Theme.ACCENT, width=2)
    ui.text(20, 500, f"{intent['actor_name']} will use {intent['name']} ({intent['text']}) on {', '.join(intent['target_names'])}.", 15, Theme.TEXT, bold=True, max_width=1010)

    picking = ctrl.reaction_hero
    if not any(o["hero_id"] == picking and o["eligible"] and o["needs_target"] for o in options):
        picking = ctrl.reaction_hero = None
    described = None
    y = 524.0
    for number, option in enumerate(options, start=1):
        hero_id = option["hero_id"]
        row_key = f"react:{hero_id}"
        targets = list(option["target_ids"]) if option["needs_target"] and option["eligible"] else []
        selected = picking == hero_id
        row_hotkeys = (NUMBER_KEYS[number - 1],) if picking is None and number <= len(NUMBER_KEYS) else ()
        follow_up = " Then choose the ally." if len(targets) > 1 else ""
        ui.button(row_key, 20, y, 228, 28, f"{number}. {option['name']} ({option['hero_name']})",
                  partial(ctrl.pick_reaction, hero_id, option["needs_target"], targets),
                  enabled=option["eligible"], reason=option["reason"], hotkeys=row_hotkeys, selected=selected, size=14,
                  tooltip=f"{option['expected']} Cost: {option['mana_cost']} mana, 1 charge.{follow_up}")
        # Cost only: the reaction charge is on the hero's card ("React 1") and in the tooltip.
        ui.text(254, y + 7, f"costs {option['mana_cost']} mana", 12, Theme.DIM, max_width=108)
        hot = ui.is_hot(row_key) or selected
        if not option["eligible"]:
            ui.text(366, y + 6, f"Unavailable: {option['reason']}", 13, Theme.WARN, max_width=664)
        elif targets:
            for position, target_id in enumerate(targets, start=1):
                target_key = f"react:{hero_id}:{target_id}"
                target_hotkeys = (NUMBER_KEYS[position - 1],) if selected and position <= len(NUMBER_KEYS) else ()
                label = f"{position}. {names[target_id]}" if selected else names[target_id]
                ui.button(target_key, 366 + (position - 1) * 134, y, 130, 28, label,
                          partial(ctrl.use_reaction, hero_id, target_id), hotkeys=target_hotkeys, size=13,
                          tooltip=f"{option['name']} on {names[target_id]}. {option['expected']} Cost: {option['mana_cost']} mana, 1 charge.")
                hot = hot or ui.is_hot(target_key)
        else:
            ui.text(366, y + 6, option["expected"], 13, Theme.TEXT, max_width=664)
        if hot and described is None:
            described = option
        y += 31
    if picking is not None:
        ui.escape_action = ctrl.cancel_reaction_pick

    described = described or next((o for o in options if o["eligible"]), None)
    if described is not None:
        ui.paragraph(1050, 524, f"{described['name']}: {described['expected']}", 214, 13, Theme.DIM, line_height=15, max_lines=5)
    used = ", ".join(f"{names[u['hero_id']]}: {u['reaction']}" for u in reaction["used"]) or "none"
    ui.text(1050, 606, f"Used this intent: {used}", 13, Theme.DIM, max_width=214)
    ui.button("react:skip", 1050, 628, 102, 48, "Skip", ctrl.skip_stage, hotkeys=(pygame.K_s,), default=True,
              sublabel="(S) this stage", tooltip="Close this stage without reacting. Stages never reopen.")
    ui.button("react:skip_all", 1158, 628, 102, 48, "Skip All", ctrl.skip_all_stages, hotkeys=(pygame.K_a,),
              sublabel="(A) all stages",
              tooltip="Do not react to this enemy action at all: every remaining stage is skipped without asking.")


def draw_battle(ui: UI, ctrl: AppController, fast: bool) -> None:
    view = ctrl.view()
    inspect = inspected_combatant(ui, view)
    ui.backdrop(0, 80, 1280, 394)
    draw_header(ui, ctrl, view, fast)
    ui.escape_action = ctrl.open_pause  # the planner and the reaction panel replace this while choosing a target
    targeting = None
    waiting = view["needs_input"]
    if view["reaction"] is not None:
        draw_reactions(ui, ctrl, view)
    elif view["hero_turn"] is not None and view["combat_phase"] in (
        CombatPhase.HERO_ROLL, CombatPhase.KEEP_REROLL, CombatPhase.ACTION_PLAN
    ):
        targeting = draw_planner(ui, ctrl, view)
    else:
        ui.panel(8, 476, 1264, 214, "Resolving")
        ui.text(640, 560, PHASE_LABELS.get(view["combat_phase"], view["combat_phase"]) + " ...", 24, Theme.DIM, bold=True, align="center")
        ui.text(640, 600, "Space steps immediately.  F toggles fast mode.  M toggles animation.  Esc opens the menu.", 15, Theme.FAINT, align="center")
    draw_formation(ui, ctrl, view, targeting)
    draw_center(ui, ctrl, view, inspect)
    for floater, progress in ui.anim.active_floaters():
        rect = ui.rect_of(f"unit:{floater.target_id}")
        if rect is not None:
            ui.floating_text(rect, floater.text, floater.colour, progress, floater.lane)
    # Registered last so it is the final Tab stop, after every decision control.
    ui.button("battle:menu", 1176, 6, 96, 28, "Menu (Esc)", ctrl.open_pause, size=13,
              tooltip="Pause. From the menu you can read the controls or abandon the run.")
    status_bar(ui, ctrl, "your decision" if waiting else "resolving")


def draw_pause(ui: UI, ctrl: AppController) -> None:
    """In-run menu. Nothing advances while it is open; the run continues exactly where it was."""
    if ctrl.pause_help:
        draw_controls(ui, ctrl, back=ctrl.toggle_pause_help)
        return
    ui.backdrop(0, 0, 1280, 694, wall_rows=2, dim=190)
    ui.text(640, 130, "PAUSED", 52, Theme.ACCENT, bold=True, align="center")
    ui.text(640, 204, "The run is waiting exactly where you left it. Nothing advances while this menu is open.", 17, Theme.DIM, align="center")
    ui.button("pause:resume", 470, 260, 340, 56, "Resume  (Esc)", ctrl.resume, default=True, size=20,
              tooltip="Return to the run.")
    ui.button("pause:controls", 470, 330, 340, 56, "Controls", ctrl.toggle_pause_help, size=20,
              tooltip="Mouse and keyboard controls, and how a turn works.")
    ui.button("pause:party", 470, 400, 340, 56, "Abandon Run: Change Party", ctrl.abandon_to_party, size=18,
              tooltip="Give up this run and return to party setup. The run is not saved and writes no event log.")
    ui.button("pause:menu", 470, 470, 340, 56, "Abandon Run: Main Menu", ctrl.abandon_to_menu, size=18,
              tooltip="Give up this run and return to the main menu. The run is not saved and writes no event log.")
    ui.escape_action = ctrl.resume
    status_bar(ui, ctrl)


# --------------------------------------------------------------------------------------------
# Recovery, upgrade and equipment
# --------------------------------------------------------------------------------------------


def draw_upgrade(ui: UI, ctrl: AppController) -> None:
    view = ctrl.view()
    upgrade = view["upgrade"]
    chosen = upgrade["upgrade_chosen"]
    ui.text(20, 12, "Recovery and Upgrade", 28, Theme.ACCENT, bold=True)
    ui.sprite("chest", 372, 8, 40, 40)
    step = "Step 2 of 2: optional swap and rows, then start Battle 2." if chosen else "Step 1 of 2: choose one dice upgrade (required)."
    ui.text(420, 22, step, 17, Theme.TEXT, bold=True)

    by_id = {c["id"]: c for c in view["combatants"]}
    ui.panel(12, 56, 300, 420, "Heroes after recovery")
    for index, hero in enumerate(upgrade["heroes"]):
        c = by_id[hero["hero_id"]]
        y: float = 84 + index * 76
        selected = hero["hero_id"] == ctrl.upgrade_hero
        ui.button(f"up:hero:{hero['hero_id']}", 20, y, 196, 68, hero["hero_name"],
                  partial(ctrl.select_upgrade_hero, hero["hero_id"]), selected=selected,
                  sublabel=f"HP {c['hp']}/{c['max_hp']}  MP {c['mana']}  CR {c['corruption']}",
                  tooltip="Show this hero's dice. HP partly recovered, mana refilled, shields and statuses cleared, corruption kept.")
        ui.button(f"up:row:{hero['hero_id']}", 222, y, 82, 68, c["row"].capitalize(),
                  partial(ctrl.toggle_formation, hero["hero_id"]), sublabel="row",
                  tooltip="Move this hero to the other row for Battle 2.")

    hero_view = next((h for h in upgrade["heroes"] if h["hero_id"] == ctrl.upgrade_hero), upgrade["heroes"][0])
    ui.panel(12, 484, 300, 200, f"{hero_view['hero_name']}: equipped dice")
    for index, entry in enumerate(hero_view["equipped"]):
        die = entry["die"]
        label = die["name"] + ("  [UPGRADED]" if entry["locked"] else "")
        ui.button(f"up:die:{die['id']}", 20, 512 + index * 56, 284, 48, label,
                  partial(ctrl.select_upgrade_die, die["id"]), selected=die["id"] == ctrl.upgrade_die,
                  sublabel=f"d{die['size']}  v{die['definition_version']}" + ("  locked against swapping" if entry["locked"] else ""),
                  tooltip="Show the three upgrade cards for this die.")

    # Offer cards
    ui.panel(322, 56, 610, 628, "Upgrade cards" if not chosen else "Upgrade applied")
    offers = ctrl.current_offers() if not chosen else []
    if chosen:
        record = upgrade["upgrades"][0]
        ui.paragraph(336, 90, f"{record['kind'].capitalize()} was applied to {by_id[record['hero_id']]['name']}'s {ctrl.content.die(record['die_id']).name} "
                     f"(face {record['face_index'] + 1}, version {record['from_version']} -> {record['to_version']}). "
                     "It lasts through Battle 2 and is removed when the run ends.", 580, 16, Theme.TEXT, line_height=21)
        die_entry = next((e for e in hero_view["equipped"] if e["die"]["id"] == ctrl.upgrade_die), hero_view["equipped"][0])
        draw_die_faces(ui, 336, 180, 580, die_entry["die"])
    for index, offer in enumerate(offers[:3]):
        x = 334 + index * 198
        selected = offer["offer_id"] == ctrl.upgrade_offer
        preview = ctrl.offer_preview(offer)
        ui.button(f"up:offer:{index}", x, 84, 190, 44, f"{index + 1}. {offer['kind_name']}", partial(ctrl.select_offer, offer["offer_id"]),
                  selected=selected, hotkeys=(NUMBER_KEYS[index],), tooltip=offer["summary"])
        ui.panel(x, 132, 190, 172, fill=Theme.PANEL_ALT, border=Theme.ACCENT if selected else Theme.BORDER, width=2 if selected else 1)
        ui.text(x + 8, 138, f"Face {offer['face_index'] + 1} of {preview['before']['size']}", 13, Theme.DIM, bold=True)
        ui.text(x + 8, 156, "Before:", 13, Theme.FAINT, bold=True)
        ui.paragraph(x + 8, 172, f"{preview['before_face']['name']}: {preview['before_face']['text']}", 174, 13, Theme.DIM, line_height=15, max_lines=3)
        ui.text(x + 8, 222, "After:", 13, Theme.ACCENT, bold=True)
        ui.paragraph(x + 8, 238, f"{preview['after_face']['name']}: {preview['after_face']['text']}", 174, 13, Theme.TEXT, line_height=15, max_lines=4)
    selected_offer = next((o for o in offers if o["offer_id"] == ctrl.upgrade_offer), None)
    if not chosen:
        if selected_offer is not None:
            preview = ctrl.offer_preview(selected_offer)
            ui.text(336, 310, "Die before", 14, Theme.DIM, bold=True)
            draw_die_faces(ui, 336, 328, 580, preview["before"], max_rows=6)
            ui.text(336, 456, "Die after (faces and probabilities)", 14, Theme.ACCENT, bold=True)
            draw_die_faces(ui, 336, 474, 580, preview["after"], highlight_face=selected_offer["face_index"], max_rows=6)
        elif offers:
            ui.text(336, 318, "Select a card to compare the die before and after.", 15, Theme.FAINT)
        problem = ctrl.apply_problem()
        ui.button("up:apply", 336, 624, 300, 50, "Apply Upgrade  (A)", ctrl.apply_upgrade, enabled=problem is None, reason=problem,
                  hotkeys=(pygame.K_a,), default=problem is None, size=18,
                  tooltip="Apply the selected card. Exactly one upgrade per run; it cannot be undone.")

    # Equipment column
    ui.panel(942, 56, 326, 510, "Optional bench swap")
    ui.text(952, 80, f"{hero_view['hero_name']}: {hero_view['swaps_remaining']} swap left (one per hero)", 14, Theme.DIM)
    y = 102.0
    die_names = {e["die"]["id"]: e["die"]["name"] for e in hero_view["equipped"]}
    for bench in hero_view["bench"]:
        y = draw_die_faces(ui, 952, y, 306, bench["die"], max_rows=5) + 6
        for swap in bench["swaps"]:
            request = (hero_view["hero_id"], swap["out_die_id"], bench["die"]["id"])
            ui.button(f"up:swap:{hero_view['hero_id']}:{swap['out_die_id']}", 952, y, 306, 38,
                      ("Confirm: give up " if ctrl.swap_confirm == request else "Swap out ")
                      + die_names.get(swap["out_die_id"], swap["out_die_id"]),
                      partial(ctrl.swap_die, hero_view["hero_id"], swap["out_die_id"], bench["die"]["id"]),
                      enabled=swap["allowed"], reason=swap["reason"], selected=ctrl.swap_confirm == request,
                      tooltip=f"Equip {bench['die']['name']} in place of {die_names.get(swap['out_die_id'], swap['out_die_id'])} for Battle 2.")
            y += 44
    if not hero_view["bench"]:
        ui.text(952, y, "No bench die.", 14, Theme.FAINT)
    proceed_problem = ctrl.proceed_problem()
    ui.button("up:start", 942, 576, 326, 108, "Start Battle 2  (Enter)", ctrl.start_next_battle, enabled=proceed_problem is None,
              reason=proceed_problem, default=proceed_problem is None, size=20, hotkeys=(pygame.K_b,),
              tooltip="Begin the second, harder battle with this party and equipment.")
    ui.button("up:menu", 1150, 12, 118, 34, "Menu (Esc)", ctrl.open_pause, size=14,
              tooltip="Pause. From the menu you can read the controls or abandon the run.")
    ui.escape_action = ctrl.open_pause
    status_bar(ui, ctrl)


# --------------------------------------------------------------------------------------------
# Outcome and error
# --------------------------------------------------------------------------------------------

STAT_LABELS = [
    ("activations", "Activations"),
    ("timeline_ticks", "Timeline ticks"),
    ("damage_dealt", "Damage dealt to enemies"),
    ("damage_taken", "HP damage taken"),
    ("shield_absorbed", "Damage absorbed by shields"),
    ("healing_done", "Healing done"),
    ("rerolls_used", "Rerolls used"),
    ("reactions_used", "Reactions used"),
    ("enemies_defeated", "Enemies defeated"),
    ("heroes_downed", "Heroes downed"),
    ("revivals", "Revivals"),
]


def draw_outcome(ui: UI, ctrl: AppController) -> None:
    outcome = ctrl.outcome_view()
    victory = outcome["outcome"] == "victory"
    ui.text(640, 40, "VICTORY" if victory else "DEFEAT", 60, Theme.GOOD if victory else Theme.BAD, bold=True, align="center")
    if victory:
        summary = "Both battles won. The run is complete."
    else:
        lost = " The upgrade is lost." if outcome["upgrades"] else ""
        summary = f"No hero was left standing in Battle {outcome['battle_reached']}. The run is over.{lost}"
    ui.text(640, 116, summary, 18, Theme.TEXT, align="center")
    records = "   ".join(f"Battle {r['battle']}: {r['outcome']} ({r['activations']} activations, {r['ticks']} ticks)" for r in outcome["battle_records"])
    ui.text(640, 146, records, 15, Theme.DIM, align="center", max_width=1200)

    party = [c for c in ctrl.view()["combatants"] if c["side"] == "hero"]
    for position, hero in enumerate(party[:5]):
        ui.sprite(ui.assets.combatant_key(ctrl.sprite_class(hero["archetype_id"])), 130, 190 + position * 64, 60, 60,
                  variant="" if hero["state"] == "standing" else "grey")
        ui.text(198, 202 + position * 64, ui.fit_name(hero["name"], 15, True, 134), 15, Theme.TEXT, bold=True)
        ui.text(198, 222 + position * 64, "standing" if hero["state"] == "standing" else "DOWNED", 13,
                Theme.DIM if hero["state"] == "standing" else Theme.BAD)
    ui.panel(340, 180, 600, 330, "Combat metrics")
    y = 210.0
    for key, label in STAT_LABELS:
        ui.text(360, y, label, 16, Theme.DIM)
        ui.text(920, y, str(outcome["stats"][key]), 16, Theme.TEXT, bold=True, align="right")
        y += 26
    awards = ctrl.awards_view()
    if awards:  # Class Evolution: what each saved hero earned in the last battle of the run
        ui.panel(952, 180, 312, 330, "Mastery from the last battle")
        award_y = 208.0
        for award in awards[:5]:
            award_y = ui.paragraph(966, award_y, award, 286, 14, Theme.TEXT, line_height=17, max_lines=3) + 8
    log_text = f"Event log: {outcome['log_path']}" if outcome["log_path"] else f"Event log not written: {outcome['log_error'] or 'unknown reason'}"
    ui.text(640, 522, log_text, 13, Theme.FAINT, align="center", max_width=1200)
    ui.text(640, 542, f"Seed {outcome['seed']} (use --seed to replay the same dice).", 13, Theme.FAINT, align="center")
    ui.button("out:retry", 250, 580, 250, 60, "Retry Same Party  (R)", ctrl.retry_same_party, hotkeys=(pygame.K_r,), default=True, size=18,
              tooltip="Start a new run at Battle 1 with the same heroes and rows. No upgrade carries over.")
    ui.button("out:modify", 515, 580, 250, 60, "Modify Party  (M)", ctrl.modify_party, hotkeys=(pygame.K_m,), size=18,
              tooltip="Return to party setup, then start a new run at Battle 1.")
    ui.button("out:menu", 780, 580, 250, 60, "Main Menu  (Esc)", ctrl.to_main_menu, size=18, tooltip="Return to the main menu.")
    for line, tip in enumerate(outcome["tips"][:2]):
        ui.text(640, 650 + line * 18, tip, 14, Theme.ACCENT, align="center", max_width=1200)
    ui.escape_action = ctrl.to_main_menu
    status_bar(ui, ctrl)


# --------------------------------------------------------------------------------------------
# Class Evolution: party setup with saved heroes, the career screen, stop or fight on
# --------------------------------------------------------------------------------------------

GROUP_LABELS = {"novice": "Starting class", "advanced": "Advanced", "capstone": "Capstone",
                "secret_sidegrade": "Secret", "secret_prestige": "Secret"}


def draw_roster_setup(ui: UI, ctrl: AppController) -> None:
    """Party setup while Class Evolution is on: pick saved heroes, recruit new ones, open a hero's career."""
    _, maximum = ctrl.party_limits()
    roster = ctrl.roster_view()
    by_id = {row["hero_id"]: row for row in roster}
    ui.text(24, 14, "Party Setup", 30, Theme.ACCENT, bold=True)
    ui.text(250, 26, f"{len(ctrl.party)} / {maximum} heroes in the party.  Your heroes are saved and keep what they master.", 16, Theme.DIM, max_width=1010)

    ui.panel(16, 60, 560, 470, "Party")
    for index in range(maximum):
        y: float = 90 + index * 86
        if index >= len(ctrl.party):
            ui.panel(26, y, 540, 78, fill=(24, 27, 35))
            ui.text(296, y + 30, "empty slot", 15, Theme.FAINT, align="center")
            continue
        member = ctrl.party[index]
        hero = by_id[member["hero_id"]]
        selected = index == ctrl.selected_slot
        ui.panel(26, y, 540, 78, fill=Theme.PANEL_ALT, border=Theme.ACCENT if selected else Theme.BORDER, width=2 if selected else 1)
        ui.sprite(ui.assets.combatant_key(ctrl.sprite_class(member["class_id"])), 30, y + 11, 56, 56)
        ui.button(f"slot:{index}:select", 90, y + 8, 170, 62, f"{index + 1}. {ui.fit_name(hero['name'], 16, False, 150)}",
                  partial(setattr, ctrl, "selected_slot", index), selected=selected,
                  sublabel=f"{hero['vocation_name']}, rank {hero['rank']}",
                  tooltip=f"{hero['name']}: {hero['vocation_name']}, mastery rank {hero['rank']} of 8.")
        ui.button(f"slot:{index}:row", 266, y + 8, 100, 62, member["row"].capitalize(),
                  partial(ctrl.toggle_party_row, index), sublabel="row: toggle",
                  tooltip="Front-row heroes shield the back row from melee. Click to switch rows.")
        ui.button(f"slot:{index}:career", 372, y + 8, 92, 62, "Career", partial(ctrl.open_career, member["hero_id"]),
                  sublabel="press C" if selected else "vocations", hotkeys=(pygame.K_c,) if selected else (),
                  tooltip="What this hero has mastered and what it can become.")
        ui.button(f"slot:{index}:remove", 470, y + 8, 88, 62, "Remove", partial(ctrl.remove_hero, index),
                  tooltip="Take this hero out of the party. It stays in the roster.")

    problem = ctrl.begin_problem()
    ui.button("party:begin", 16, 606, 284, 60, "Begin Encounter  (B)", ctrl.begin_run, enabled=problem is None,
              reason=problem, hotkeys=(pygame.K_b,), default=True, size=20,
              tooltip="Start Battle 1 with this party.")
    ui.button("party:back", 308, 606, 138, 60, "Back  (Esc)", ctrl.to_main_menu, tooltip="Return to the main menu.")
    ui.escape_action = ctrl.to_main_menu
    third = "After Battle 2 you may stop with a victory or fight a third, harder battle." if ctrl.third_battle else "The third battle is switched off."
    ui.text(16, 548, third, 14, Theme.DIM, max_width=560)
    ui.text(16, 570, "Mastery is earned by winning battles. A mastered class opens new vocations.", 14, Theme.DIM, max_width=560)

    limit = ctrl.progression.career.service.roster_limit
    ui.panel(588, 60, 676, 606, f"Roster ({len(roster)} of {limit} heroes)")
    full = len(ctrl.party) >= maximum
    y = 88.0
    if not roster:
        ui.text(604, y, "No heroes yet. Recruit one below: a Squire, an Apprentice or a Scout.", 15, Theme.DIM, max_width=640)
    for row in roster:
        reason = "Already in the party." if row["in_party"] else f"The party already has {maximum} heroes." if full else None
        progress = "mastered" if row["mastered"] else f"{row['points']}/{row['points_for_next_rank']} to rank {row['rank'] + 1}"
        ui.button(f"roster:{row['hero_id']}:add", 600, y, 520, 34,
                  f"{ui.fit_name(row['name'], 15, False, 170)}   {row['vocation_name']}, rank {row['rank']}   ({progress})",
                  partial(ctrl.add_saved_hero, row["hero_id"]), enabled=reason is None, reason=reason, size=15,
                  tooltip="Add this hero to the party.")
        ui.button(f"roster:{row['hero_id']}:career", 1126, y, 126, 34, "Career", partial(ctrl.open_career, row["hero_id"]), size=15,
                  tooltip="What this hero has mastered and what it can become.")
        y += 38
    roster_full = len(roster) >= limit
    for position, class_id in enumerate(ctrl.progression.catalog.starting_classes()):
        name = ctrl.class_view(class_id)["name"]
        ui.button(f"add:{class_id}", 600 + position * 220, 606, 212, 50, f"Recruit {name} ({position + 1})",
                  partial(ctrl.add_hero, class_id), enabled=not roster_full,
                  reason=f"The roster is full ({limit} heroes).", hotkeys=(NUMBER_KEYS[position],),
                  tooltip=f"Recruit a new {name}. It joins the party if there is room. Recruiting is free.")
    status_bar(ui, ctrl)


def draw_career(ui: UI, ctrl: AppController) -> None:
    """One hero's career: every vocation it knows of, what it may claim or become, and what is still hidden."""
    view = ctrl.career_view()
    ui.text(24, 14, f"Career: {ui.fit_name(view['name'], 30, True, 520)}", 30, Theme.ACCENT, bold=True)
    note = "During a run a hero cannot change. Come back between runs." if view["in_run"] else \
        "Master a vocation (rank 8) to open the ones that build on it. A hero fights as its active vocation."
    ui.text(24, 52, note, 15, Theme.DIM, max_width=1230)

    ui.panel(16, 78, 760, 540, "Vocations")
    y = 104.0
    for index, row in enumerate(view["rows"]):
        if row["kind"] != "vocation":
            ui.panel(26, y, 740, 32, fill=(24, 27, 35))
            ui.text(36, y + 7, row["label"], 16, Theme.FAINT, bold=True)
            ui.text(110, y + 8, row["status"], 14, Theme.FAINT, max_width=640)
            y += 36
            continue
        vocation_id = row["vocation_id"]
        selected = vocation_id == view["selected"]
        ui.button(f"career:{vocation_id}:select", 26, y, 176, 32, row["name"], partial(ctrl.select_career_vocation, vocation_id),
                  selected=selected, size=15, tooltip=f"Show what a {row['name']} is.")
        ui.text(210, y + 8, GROUP_LABELS.get(row["group"], row["group"]), 13, Theme.FAINT, max_width=96)
        # The row says where the hero stands; what a locked vocation still needs is spelled out on the right.
        ui.text(310, y + 8, row["status"], 14, Theme.TEXT if row["unlocked"] else Theme.DIM, max_width=320)
        if row["unlocked"]:
            ui.button(f"career:{vocation_id}:activate", 640, y, 126, 32, "Active" if row["active"] else "Make active",
                      partial(ctrl.change_vocation, vocation_id), enabled=row["can_activate"], size=14,
                      reason="This is the active vocation." if row["active"] else "A hero cannot change during a run.",
                      tooltip="The hero fights as this vocation from the next run on.")
        else:
            ui.button(f"career:{vocation_id}:claim", 640, y, 126, 32, "Claim", partial(ctrl.claim_vocation, vocation_id),
                      enabled=row["can_claim"], size=14,
                      reason=row["needs"] or "A hero cannot claim a vocation during a run.",
                      tooltip="Unlock this vocation for the hero. It costs nothing.")
        y += 36 if index < len(view["rows"]) - 1 else 0

    skills_tab = ctrl.career_tab == "skills"
    ui.button("career:tab", 248, 630, 220, 44, "Vocation  (K)" if skills_tab else "Skills  (K)", ctrl.toggle_career_skills,
              hotkeys=(pygame.K_k,), tooltip="Show the vocation's details." if skills_tab else "Show the skills this hero has learned and equip them.")
    if skills_tab:
        draw_career_skills(ui, ctrl)
        ui.button("career:back", 16, 630, 220, 44, "Back  (Esc)", ctrl.close_career, hotkeys=(pygame.K_b,), default=True)
        ui.escape_action = ctrl.close_career
        status_bar(ui, ctrl)
        return
    info = ctrl.class_view(view["selected"])
    ui.panel(788, 78, 476, 540, info["name"])
    ui.sprite(ui.assets.combatant_key(ctrl.sprite_class(view["selected"])), 1206, 82, 50, 50)
    x, y = 802.0, 106.0
    ui.text(x, y, f"HP {info['max_hp']}   Speed {info['speed']}   Mana {info['start_mana']}/{info['max_mana']}   Rerolls {info['rerolls']}", 15,
            Theme.TEXT, max_width=390)
    y += 24
    if view["selected_needs"]:
        ui.text(x, y, "To claim", 14, Theme.WARN, bold=True)
        y = ui.paragraph(x + 76, y, view["selected_needs"], 372, 14, Theme.TEXT, line_height=17, max_lines=5) + 5
    if not info.get("playable", True):
        ui.paragraph(x, y + 6, "This vocation is part of the design but cannot be played in this version: the rules it needs are "
                               "not built yet. Its dice and abilities will be shown here when they are.", 448, 14, Theme.DIM, line_height=18)
        ui.button("career:back", 16, 630, 220, 44, "Back  (Esc)", ctrl.close_career, hotkeys=(pygame.K_b,), default=True)
        ui.escape_action = ctrl.close_career
        status_bar(ui, ctrl)
        return
    for label, body in (
        ("Schedule", f"{info['scheduling']['label']}: {info['scheduling']['summary']}"),
        ("Passive", f"{info['passive']['name']}: {info['passive']['summary']}"),
        ("Reaction", f"{info['reaction_def']['name']} ({info['reaction_def']['mana_cost']} mana): {info['reaction_def']['summary']}"),
    ):
        ui.text(x, y, label, 14, Theme.ACCENT, bold=True)
        y = ui.paragraph(x + 76, y, body, 372, 14, Theme.DIM, line_height=17, max_lines=4) + 5
    for die in info["dice"]:
        y = draw_die_faces(ui, x, y + 2, 448, die, max_rows=6) + 4
    ui.button("career:back", 16, 630, 220, 44, "Back  (Esc)", ctrl.close_career, hotkeys=(pygame.K_b,), default=True)
    ui.escape_action = ctrl.close_career
    status_bar(ui, ctrl)


def draw_career_skills(ui: UI, ctrl: AppController) -> None:
    """The right half of the career screen as the hero's skills: what it has learned, what is equipped, and why not."""
    view = ctrl.skills_view()
    ui.panel(788, 78, 476, 540, "Skills")
    x, y = 802.0, 106.0
    ui.text(x, y, f"Capacity used: {view['used']} of {view['capacity']} as a {view['vocation_name']}", 15, Theme.TEXT, bold=True, max_width=448)
    y = ui.paragraph(x, y + 22, "A mastered vocation teaches a skill. It is free while that vocation is active; "
                                "with another vocation it takes capacity.", 448, 13, Theme.DIM, line_height=16, max_lines=3) + 8
    if not view["rows"]:
        ui.paragraph(x, y, "This hero has learned no skill yet. Skills come with mastery ranks; the vocation's rows on the left "
                           "show how far it is.", 448, 14, Theme.DIM, line_height=18, max_lines=4)
        return
    for row in view["rows"][:3]:
        ui.panel(798, y, 456, 128, fill=(24, 27, 35))
        ui.text(808, y + 8, row["name"], 16, Theme.ACCENT, bold=True, max_width=300)
        state = "EQUIPPED" if row["equipped"] else "not equipped"
        ui.text(1244, y + 10, state, 13, Theme.GOOD if row["equipped"] else Theme.FAINT, bold=row["equipped"], align="right", max_width=130)
        cost = "free here" if row["cost"] == 0 else f"capacity {row['cost']}"
        ui.text(808, y + 30, f"Taught by the {row['taught_by']}; {cost}", 13, Theme.FAINT, max_width=300)
        ui.paragraph(808, y + 48, row["summary"], 300, 12, Theme.TEXT if row["in_battle"] else Theme.DIM, line_height=14, max_lines=4)
        if row["reason"] and not row["equipped"]:
            ui.text(808, y + 108, row["reason"], 12, Theme.WARN, max_width=436)
        if row["equipped"]:
            ui.button(f"skill:{row['skill_id']}:unequip", 1118, y + 44, 126, 44, "Take off", partial(ctrl.unequip_skill, row["skill_id"]),
                      enabled=row["can_unequip"], reason=row["reason"], size=14, tooltip="The skill stays learned and can be equipped again.")
        else:
            ui.button(f"skill:{row['skill_id']}:equip", 1118, y + 44, 126, 44, "Equip", partial(ctrl.equip_skill, row["skill_id"]),
                      enabled=row["can_equip"], reason=row["reason"], size=14, tooltip="The hero brings this skill into its next run.")
        y += 134


def draw_continue(ui: UI, ctrl: AppController) -> None:
    """After Battle 2 of a run that offers a third battle: stop with the victory, or fight on."""
    view = ctrl.continue_view()
    ui.text(640, 36, f"BATTLE {view['battle']} WON", 52, Theme.GOOD, bold=True, align="center")
    ui.text(640, 104, "Your party has recovered. Stop here with a victory, or fight a third, harder battle.", 18, Theme.TEXT, align="center",
            max_width=1200)
    threat = f" (threat {view['threat_rating']} of 5)" if view["threat_rating"] is not None else ""
    ui.text(640, 132, f"The third battle is harder than the first two{threat}. Losing it loses the run; mastery already earned is kept.", 15,
            Theme.DIM, align="center", max_width=1200)

    ui.panel(240, 170, 380, 300, "Party after recovery")
    for position, hero in enumerate(view["heroes"][:5]):
        line_y = 200 + position * 52
        ui.text(256, line_y, ui.fit_name(hero["name"], 16, True, 170), 16, Theme.TEXT, bold=True)
        ui.text(604, line_y, f"HP {hero['hp']}/{hero['max_hp']}   MP {hero['mana']}/{hero['max_mana']}   {hero['row']}", 14, Theme.DIM, align="right")
    ui.panel(640, 170, 400, 300, f"Mastery from Battle {view['battle']}")
    y = 200.0
    if not view["awards"]:
        ui.text(656, y, "No saved hero fought this battle.", 14, Theme.DIM, max_width=370)
    for line in view["awards"][:5]:
        y = ui.paragraph(656, y, line, 370, 14, Theme.TEXT, line_height=17, max_lines=3) + 8

    ui.button("continue:fight", 300, 500, 320, 64, "Fight On  (F)", ctrl.fight_on, hotkeys=(pygame.K_f,), size=20,
              tooltip="Start the third battle. Winning it wins the run; losing it loses the run.")
    ui.button("continue:stop", 660, 500, 320, 64, "End Run: Victory  (V)", ctrl.end_run_with_victory, hotkeys=(pygame.K_v,), default=True, size=20,
              tooltip="End the run now as a victory, with two battles won.")
    ui.text(640, 584, "Mastery is awarded for every won battle, so the points from Battles 1 and 2 are yours either way.", 14, Theme.FAINT,
            align="center", max_width=1200)
    ui.escape_action = None
    status_bar(ui, ctrl)


def draw_settings(ui: UI, ctrl: AppController) -> None:
    """The demo's configuration: every setting, what it does, and a button that moves it to its next value."""
    ui.text(24, 14, "Settings", 30, Theme.ACCENT, bold=True)
    where = f"Saved in {ctrl.settings_path}" if ctrl.settings_path else "No settings file is in use: changes last for this session."
    ui.text(170, 26, where, 14, Theme.DIM, max_width=1090)
    y = 70.0
    for row in ctrl.settings_view():
        ui.panel(16, y, 1248, 54, fill=Theme.PANEL_ALT)
        ui.text(30, y + 17, row["label"], 17, Theme.TEXT, bold=True, max_width=210)
        ui.button(f"settings:{row['key']}", 250, y + 6, 330, 42, row["value"], partial(ctrl.change_setting, row["key"]),
                  enabled=row["reason"] is None, reason=row["reason"], size=15, tooltip="Click to change.")
        ui.paragraph(596, y + 9, row["help"], 656, 14, Theme.DIM, line_height=17, max_lines=2)
        y += 60
    evolution = ctrl.progression is not None
    label = "Press again to delete every hero" if ctrl.reset_confirm else "Reset the saved profile"
    ui.button("settings:reset", 250, 566, 330, 46, label, ctrl.reset_profile, enabled=evolution,
              reason="There is no profile while Class Evolution is off.", size=15,
              tooltip="Delete the save and start a new profile from the start chosen above. Asked twice.")
    if evolution:
        ui.text(596, 580, f"Save file: {ctrl.progression.path}", 13, Theme.FAINT, max_width=656)
    ui.button("settings:back", 16, 630, 220, 44, "Back  (Esc)", ctrl.close_settings, hotkeys=(pygame.K_b,), default=True)
    ui.escape_action = ctrl.close_settings
    status_bar(ui, ctrl)


def draw_error(ui: UI, ctrl: AppController) -> None:
    ui.text(40, 30, "Something went wrong", 34, Theme.BAD, bold=True)
    ui.text(40, 80, "The game hit an unexpected error. Your window is still responsive; return to the menu to start again.", 17, Theme.TEXT)
    ui.panel(40, 120, 1200, 470, "Details")
    y = 148.0
    for line in ctrl.error_text.strip().splitlines()[-24:]:
        ui.text(52, y, line, 13, Theme.DIM, max_width=1176)
        y += 17
    ui.button("error:menu", 40, 610, 300, 56, "Return to Main Menu", ctrl.to_main_menu, default=True, size=18)
    ui.escape_action = ctrl.to_main_menu
    status_bar(ui, ctrl)
