"""The required screens (section 13), drawn from controller snapshots with the immediate-mode toolkit.

Screens never mutate rules state. Buttons call controller methods, which submit commands.
Status is always shown as text or shape as well as color (HP numbers, "DOWNED", "KEPT",
"TARGET 1", hatched disabled buttons), and every disabled control carries its reason.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pygame

from battle_dice.app.controller import AppController
from battle_dice.core.models import CombatPhase
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
    hint = ui.status_text()
    if hint is not None:
        text, is_error = hint
    else:
        text, is_error = ctrl.message, ctrl.message_is_error
    ui.text(10, 699, text, 15, Theme.WARN if is_error else Theme.TEXT, max_width=1000 if extra else 1260)
    if extra:
        ui.text(1270, 699, extra, 14, Theme.FAINT, align="right", max_width=250)


def draw_die_faces(ui: UI, x: float, y: float, w: float, die: dict[str, Any], highlight_face: int | None = None,
                   max_rows: int = 8) -> float:
    """List every distinct face with its frequency and exact probability. Returns the next y."""
    ui.text(x, y, f"{die['name']}  (d{die['size']}, {die['size']} faces, v{die['definition_version']})", 15, Theme.ACCENT, bold=True, max_width=w)
    y += 20
    for group in die["groups"][:max_rows]:
        face = group["face"]
        rolled = highlight_face is not None and (highlight_face + 1) in group["face_numbers"]
        color = CATEGORY_COLORS[face["category"]]
        marker = ">" if rolled else " "
        ui.text(x, y, f"{marker}{face['glyph']}", 14, color, bold=True)
        ui.text(x + 54, y, f"{face['name']}: {face['text']}", 14, Theme.TEXT if rolled else Theme.DIM, bold=rolled, max_width=w - 54 - 124)
        ui.text(x + w, y, f"x{group['count']}  {group['probability']}", 14, Theme.TEXT if rolled else Theme.DIM, align="right")
        y += 17
    return y


# --------------------------------------------------------------------------------------------
# Main menu and controls
# --------------------------------------------------------------------------------------------


def draw_main_menu(ui: UI, ctrl: AppController, quit_action: Callable[[], Any]) -> None:
    ui.text(640, 150, "BATTLE DICE", 64, Theme.ACCENT, bold=True, align="center")
    ui.text(640, 232, "A turn-based tactical dice RPG. Two battles, one upgrade, every die face visible.", 18, Theme.DIM, align="center")
    ui.button("menu:new", 490, 310, 300, 56, "New Run  (N)", ctrl.new_run, hotkeys=(pygame.K_n,), default=True, size=22,
              tooltip="Configure a party of 1 to 5 heroes and start Battle 1.")
    ui.button("menu:controls", 490, 380, 300, 56, "Controls  (C)", ctrl.show_controls, hotkeys=(pygame.K_c,), size=22,
              tooltip="Mouse and keyboard controls, and how a turn works.")
    ui.button("menu:quit", 490, 450, 300, 56, "Quit  (Q)", quit_action, hotkeys=(pygame.K_q,), size=22, tooltip="Close the game.")
    ui.escape_action = quit_action
    ui.text(640, 560, "Tab / arrow keys move focus.  Enter or Space activates.  Every screen works with mouse or keyboard.", 15, Theme.FAINT, align="center")
    status_bar(ui, ctrl, f"rules {ctrl.content.content_version}")


CONTROLS_TEXT = [
    ("Everywhere", "Tab / Shift+Tab or arrow keys move focus.  Enter or Space activates the focused control.  Esc goes back or cancels.  Hover or focus a control to read what it does; disabled controls explain why."),
    ("Party setup", "1 / 2 / 3 add a Squire / Apprentice / Scout.  Each hero has a Row and a Remove button.  B begins the encounter."),
    ("Your activation", "R rolls, then R rerolls every die you did not Keep.  Z / X toggle Keep on die 1 / 2.  1 / 2 plan the rolled face of die 1 / 2; when a target is needed, press the number shown on a legal target (or click it).  O swaps the order of equal-speed actions.  C clears the plan.  Enter confirms the whole plan.  P passes."),
    ("Enemy activation", "The enemy's action and targets are revealed first.  Number keys use a listed reaction.  S skips the current stage (Guard, then Resource, then Interrupt)."),
    ("Pacing", "Automatic steps play on a short timer.  F toggles fast mode.  Space with nothing focused steps immediately."),
    ("Upgrade", "After Battle 1, pick a hero and a die, select one of three cards, then A applies it.  Optionally swap one die or change rows, then Enter starts Battle 2."),
    ("Reading the board", "HP, SH (shield), MP (mana), CR (corruption).  PSN / WKN / SPD+ show stacks and remaining activations.  The gauge bar fills to 100 by speed each tick; the Next row forecasts who acts."),
]


def draw_controls(ui: UI, ctrl: AppController) -> None:
    ui.text(40, 28, "Controls", 34, Theme.ACCENT, bold=True)
    y = 90.0
    for heading, body in CONTROLS_TEXT:
        ui.text(40, y, heading, 18, Theme.TEXT, bold=True)
        y = ui.paragraph(240, y, body, 990, 16, Theme.DIM, line_height=21) + 12
    ui.button("controls:back", 40, 630, 220, 46, "Back  (Esc)", ctrl.to_main_menu, hotkeys=(pygame.K_b,), default=True)
    ui.escape_action = ctrl.to_main_menu
    status_bar(ui, ctrl)


# --------------------------------------------------------------------------------------------
# Party setup
# --------------------------------------------------------------------------------------------


def draw_party_setup(ui: UI, ctrl: AppController) -> None:
    minimum, maximum = ctrl.party_limits()
    ui.text(24, 14, "Party Setup", 30, Theme.ACCENT, bold=True)
    ui.text(250, 26, f"{len(ctrl.party)} / {maximum} heroes.  Any mix of classes, duplicates allowed.  Starting dice are fixed by class.", 16, Theme.DIM)

    ui.panel(16, 60, 430, 470, "Party (click a hero to inspect)")
    for index in range(maximum):
        y = 90 + index * 86
        if index < len(ctrl.party):
            member = ctrl.party[index]
            cls = ctrl.content.class_def(member["class_id"])
            selected = index == ctrl.selected_slot
            ui.panel(26, y, 410, 78, fill=Theme.PANEL_ALT, border=Theme.ACCENT if selected else Theme.BORDER, width=2 if selected else 1)
            ui.button(f"slot:{index}:select", 34, y + 8, 180, 62, f"{index + 1}. {cls['name']}",
                      lambda i=index: setattr(ctrl, "selected_slot", i), selected=selected,
                      sublabel=f"HP {cls['max_hp']}  SPD {cls['speed']}  MP {cls['start_mana']}/{cls['max_mana']}",
                      tooltip=f"Inspect {cls['name']}: stats, abilities and dice.")
            ui.button(f"slot:{index}:row", 222, y + 8, 110, 62, f"Row: {member['row'].capitalize()}",
                      lambda i=index: ctrl.toggle_party_row(i), sublabel="toggle",
                      tooltip="Front-row heroes shield the back row from melee. Click to switch rows.")
            ui.button(f"slot:{index}:remove", 340, y + 8, 88, 62, "Remove", lambda i=index: ctrl.remove_hero(i),
                      tooltip="Remove this hero from the party.")
        else:
            ui.panel(26, y, 410, 78, fill=(24, 27, 35))
            ui.text(231, y + 30, "empty slot", 15, Theme.FAINT, align="center")

    full = len(ctrl.party) >= maximum
    class_ids = sorted(ctrl.content.classes, key=lambda c: ["squire", "apprentice", "scout"].index(c) if c in ("squire", "apprentice", "scout") else 9)
    for position, class_id in enumerate(class_ids):
        cls = ctrl.content.class_def(class_id)
        ui.button(f"add:{class_id}", 16 + position * 146, 540, 138, 50, f"+ {cls['name']} ({position + 1})",
                  lambda c=class_id: ctrl.add_hero(c), enabled=not full,
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
    x, y = 472.0, 88.0
    ui.text(x, y, f"HP {info['start_hp']}/{info['max_hp']}    Speed {info['speed']}    Initiative {info['base_initiative']}    "
            f"Mana {info['start_mana']}/{info['max_mana']}    Corruption {info['start_corruption']}/{info['max_corruption']}    "
            f"Rerolls {info['rerolls']}    Suggested row: {info['suggested_row']}", 15, Theme.TEXT, max_width=780)
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


def _status_text(c: dict[str, Any]) -> str:
    return "  ".join(f"{s['glyph']} x{s['stacks']} ({s['remaining']})" for s in c["statuses"])


def _combatant_tooltip(c: dict[str, Any]) -> str:
    if c["side"] == "hero":
        return (f"{c['name']}: {c['scheduling']['label']}. Passive {c['passive']['name']}. Reaction {c['reaction']['name']} "
                f"({c['reaction_charges']} charge). Speed {c['speed']}, gauge {c['gauge']}.")
    actions = "; ".join(f"{a['name']}: {a['text']} (weight {a['weight']})" for a in c["actions"])
    return f"{c['name']} (speed {c['speed']}, gauge {c['gauge']}). Abilities: {actions}"


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
            action = lambda cid=c["id"]: ctrl.choose_target(cid)  # noqa: E731
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
    border = Theme.ACCENT if active else side_color if standing else Theme.FAINT
    ui.panel(x, y, w, h, fill=fill, border=border, width=3 if active else 1)
    ui.decorate(key, rect, enabled)

    tag = ""
    if not standing:
        tag = "DOWNED" if c["side"] == "hero" else "DEFEATED"
    elif active:
        tag = "ACTING"
    if targeting is not None and c["id"] in target_numbers:
        tag = f"TARGET {target_numbers[c['id']]}"
    elif intended:
        tag = "TARGETED"
    ui.text(x + 6, y + 3, c["name"], 15, Theme.TEXT if standing else Theme.FAINT, bold=True, max_width=w - (90 if tag else 12))
    if tag:
        ui.text(x + w - 6, y + 3, tag, 14, Theme.ACCENT if tag.startswith(("TARGET", "ACTING")) else Theme.BAD, bold=True, align="right")

    ui.bar(x + 6, y + 22, 100, 11, c["hp"], c["max_hp"], Theme.GOOD if standing else Theme.FAINT)
    ui.text(x + 112, y + 19, f"HP {c['hp']}/{c['max_hp']}", 14, Theme.TEXT)
    ui.text(x + w - 6, y + 19, f"SH {c['shields']}", 14, Theme.SHIELD if c["shields"] else Theme.FAINT, bold=bool(c["shields"]), align="right")
    if c["side"] == "hero":
        backlash = "!" if c.get("corruption_backlash") else ""
        ui.text(x + 6, y + 36, f"MP {c['mana']}/{c['max_mana']}", 14, Theme.MANA)
        ui.text(x + 78, y + 36, f"CR {c['corruption']}/{c['max_corruption']}{backlash}", 14, Theme.BAD if backlash else Theme.CORRUPT, bold=bool(backlash))
        ui.text(x + w - 6, y + 36, f"React {c['reaction_charges']}", 14, Theme.TEXT if c["reaction_charges"] else Theme.FAINT, align="right")
    else:
        ui.text(x + 6, y + 36, f"SPD {c['speed']}   {c['row'].capitalize()} row", 14, Theme.DIM)
    ui.bar(x + 6, y + 56, 70, 8, min(c["gauge"], view["ready_threshold"]), view["ready_threshold"], Theme.GAUGE)
    ui.text(x + 80, y + 51, f"G{c['gauge']}", 13, Theme.FAINT)
    statuses = _status_text(c)
    if statuses:
        ui.text(x + w - 6, y + 51, statuses, 13, Theme.WARN, bold=True, align="right", max_width=110)


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


def draw_center(ui: UI, ctrl: AppController, view: dict[str, Any]) -> None:
    intent = view.get("intent")
    log_top = 92.0
    if intent is not None:
        ui.panel(478, 88, 324, 104, "Enemy intent (committed)", border=Theme.ENEMY, width=2)
        state = "CANCELLED" if intent["cancelled"] else "elite-resistant" if intent["elite_resistant"] else "interruptible" if intent["interruptible"] else "not interruptible"
        ui.text(488, 110, f"{intent['actor_name']}: {intent['name']}", 16, Theme.TEXT, bold=True, max_width=304)
        ui.text(488, 130, f"{intent['glyph']} {intent['power']}: {intent['text']}", 14, Theme.DIM, max_width=304)
        ui.text(488, 148, "Targets: " + ", ".join(intent["target_names"]), 14, Theme.ACCENT, max_width=304)
        mods = []
        if intent["damage_reduction"]:
            mods.append(f"-{intent['damage_reduction']} damage")
        if intent["magnitude_reduction"]:
            mods.append(f"-{intent['magnitude_reduction']} magnitude")
        extra = f"  ({', '.join(mods)})" if mods else ""
        ui.text(488, 166, f"[{state}]{'' if intent['reactable'] else ' [no reactions]'}{extra}", 14,
                Theme.BAD if intent["cancelled"] else Theme.WARN, bold=True, max_width=304)
        log_top = 198.0
    height = 470 - log_top
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
    ui.panel(0, 0, 1280, 40, fill=(12, 13, 18), border=(12, 13, 18))
    ui.text(12, 9, f"Battle {view['battle']} of {view['battle_count']}", 20, Theme.ACCENT, bold=True)
    actor = names.get(view["active_combatant_id"] or "", "nobody")
    ui.text(200, 12, f"Tick {view['timeline_tick']}    Phase: {PHASE_LABELS.get(view['combat_phase'], view['combat_phase'])}    Acting: {actor}",
            16, Theme.TEXT, max_width=780)
    ui.text(1268, 12, f"Seed {view['seed']}   {'FAST' if fast else 'normal'} (F)", 14, Theme.FAINT, align="right")
    ui.text(12, 52, "Next:", 15, Theme.DIM, bold=True)
    x = 62.0
    for position, cid in enumerate(view["forecast"][:8]):
        name = names.get(cid, cid)
        hero = cid.startswith("h")
        ui.panel(x, 46, 146, 28, fill=Theme.PANEL, border=Theme.HERO if hero else Theme.ENEMY)
        ui.text(x + 5, 53, f"{position + 1}. {name}", 13, Theme.TEXT, max_width=138)
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
        face = die["face"]
        in_plan = die["die_id"] in drafted
        awaiting = ctrl.targeting_die == die["die_id"]
        if awaiting:
            targeting = die
        if ui.is_hot(f"die:{die['die_id']}:use") or ui.is_hot(f"die:{die['die_id']}:keep"):
            inspect = die["die_id"]
        border = Theme.ACCENT if in_plan or awaiting else CATEGORY_COLORS[face["category"]]
        ui.panel(x, 500, 248, 184, fill=Theme.PANEL_ALT, border=border, width=2)
        ui.text(x + 8, 505, f"Die {index + 1}: {die['die_name']}", 14, Theme.DIM, bold=True, max_width=150)
        state = "KEPT" if die["kept"] else "will reroll"
        ui.text(x + 240, 505, state, 14, Theme.ACCENT if die["kept"] else Theme.FAINT, bold=die["kept"], align="right")
        ui.text(x + 8, 524, f"{face['glyph']}  {face['name']}", 20, CATEGORY_COLORS[face["category"]], bold=True, max_width=232)
        ui.paragraph(x + 8, 550, face["text"], 232, 14, Theme.TEXT, line_height=17, max_lines=2)
        detail = f"Face {die['face_index'] + 1}/{die['die_size']}"
        if face["action_speed"] is not None:
            detail += f"   speed {face['action_speed']}   target: {face['target_label']}"
        ui.text(x + 8, 588, detail, 13, Theme.FAINT, max_width=232)
        if die["reason"]:
            ui.text(x + 8, 606, die["reason"], 13, Theme.WARN, bold=True, max_width=232)
        elif in_plan:
            ui.text(x + 8, 606, "IN PLAN", 13, Theme.ACCENT, bold=True)
        elif awaiting:
            ui.text(x + 8, 606, "CHOOSE A TARGET", 13, Theme.ACCENT, bold=True)
        keep_key = (pygame.K_z, pygame.K_x)[index]
        ui.button(f"die:{die['die_id']}:keep", x + 8, 628, 112, 48, "Unkeep" if die["kept"] else "Keep",
                  lambda d=die["die_id"]: ctrl.toggle_keep(d), selected=die["kept"], hotkeys=(keep_key,),
                  sublabel=f"({'ZX'[index]})", tooltip="Kept dice are not rerolled. You can unkeep before a later reroll.")
        use_hotkeys = () if ctrl.targeting_die is not None else (NUMBER_KEYS[index],)
        ui.button(f"die:{die['die_id']}:use", x + 128, 628, 112, 48, "Remove" if in_plan else "Cancel" if awaiting else "Use",
                  (lambda d=die["die_id"]: ctrl.use_die(d)) if not awaiting else ctrl.cancel_targeting,
                  enabled=die["selectable"] or in_plan, reason=die["reason"], selected=in_plan or awaiting,
                  hotkeys=use_hotkeys, sublabel=f"({index + 1})",
                  tooltip=f"Plan {face['name']}: {face['text']}." if die["selectable"] else None)

    # Plan column
    px0 = 530
    preview = ctrl.plan_preview()
    ui.text(px0, 500, "Plan (resolves top to bottom)", 15, Theme.TEXT, bold=True)
    y = 520.0
    if not preview["ordered"] and not ctrl.draft:
        ui.text(px0, y, "No action selected yet.", 14, Theme.FAINT)
        y += 18
    for number, entry in enumerate(preview["ordered"], start=1):
        targets = ", ".join(entry["target_names"]) or "-"
        cost = f", {entry['mana_cost']} mana" if entry["mana_cost"] else ""
        ui.text(px0, y, f"{number}. {entry['name']} -> {targets}  (speed {entry['action_speed']}{cost})", 14, Theme.TEXT, bold=True, max_width=372)
        ui.text(px0 + 14, y + 16, entry["fallback"], 12, Theme.FAINT, max_width=358)
        y += 34
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
        ui.panel(918, 498, 346, 186, fill=(24, 27, 35))
        draw_die_faces(ui, 926, 504, 330, shown["die"], highlight_face=shown["face_index"])
        ctrl.inspect_die = shown["die_id"]
    return targeting


def draw_reactions(ui: UI, ctrl: AppController, view: dict[str, Any]) -> None:
    reaction = view["reaction"]
    intent = view["intent"]
    names = {c["id"]: c["name"] for c in view["combatants"]}
    stage = reaction["stage"]
    ui.panel(8, 476, 1264, 214, f"Reaction window: stage {reaction['stage_number']} of 3: {stage.capitalize()}   (Guard -> Resource -> Interrupt -> enemy action)",
             border=Theme.ACCENT, width=2)
    ui.text(20, 502, f"{intent['actor_name']} will use {intent['name']} ({intent['text']}) on {', '.join(intent['target_names'])}.", 16, Theme.TEXT, bold=True, max_width=1040)
    y = 530.0
    number = 0
    for option in reaction["options"]:
        targets = option["target_ids"] if option["needs_target"] and option["eligible"] else [None]
        for target_id in targets[:4]:
            number += 1
            label = f"{option['name']} ({option['hero_name']})"
            if target_id is not None:
                label += f" -> {names[target_id]}"
            hotkey = (NUMBER_KEYS[number - 1],) if number <= len(NUMBER_KEYS) else ()
            ui.button(f"react:{option['hero_id']}:{target_id or 'intent'}", 20, y, 430, 36, f"{number}. {label}",
                      lambda h=option["hero_id"], t=target_id: ctrl.use_reaction(h, t),
                      enabled=option["eligible"], reason=option["reason"], hotkeys=hotkey,
                      tooltip=f"{option['expected']} Cost: {option['mana_cost']} mana, 1 charge.")
            detail = option["expected"] if option["eligible"] else f"Unavailable: {option['reason']}"
            ui.text(462, y + 2, f"Cost {option['mana_cost']} mana, charges {option['charges']}", 13, Theme.DIM)
            ui.text(462, y + 18, detail, 13, Theme.TEXT if option["eligible"] else Theme.WARN, max_width=560)
            y += 40
    ui.button("react:skip", 1050, 628, 210, 48, "Skip Stage  (S)", ctrl.skip_stage, hotkeys=(pygame.K_s,), default=True,
              tooltip="Close this stage without reacting. Stages never reopen.")
    used = ", ".join(f"{names[u['hero_id']]}: {u['reaction']}" for u in reaction["used"]) or "none"
    ui.text(1050, 606, f"Used this intent: {used}", 13, Theme.DIM, max_width=214)


def draw_battle(ui: UI, ctrl: AppController, fast: bool) -> None:
    view = ctrl.view()
    draw_header(ui, ctrl, view, fast)
    targeting = None
    waiting = view["needs_input"]
    if view["reaction"] is not None:
        draw_reactions(ui, ctrl, view)
    elif view["hero_turn"] is not None and view["combat_phase"] in (CombatPhase.HERO_ROLL, CombatPhase.KEEP_REROLL):
        targeting = draw_planner(ui, ctrl, view)
    else:
        ui.panel(8, 476, 1264, 214, "Resolving")
        ui.text(640, 560, PHASE_LABELS.get(view["combat_phase"], view["combat_phase"]) + " ...", 24, Theme.DIM, bold=True, align="center")
        ui.text(640, 600, "Space steps immediately.  F toggles fast mode.", 15, Theme.FAINT, align="center")
    draw_formation(ui, ctrl, view, targeting)
    draw_center(ui, ctrl, view)
    status_bar(ui, ctrl, "your decision" if waiting else "resolving")


# --------------------------------------------------------------------------------------------
# Recovery, upgrade and equipment
# --------------------------------------------------------------------------------------------


def draw_upgrade(ui: UI, ctrl: AppController) -> None:
    view = ctrl.view()
    upgrade = view["upgrade"]
    chosen = upgrade["upgrade_chosen"]
    ui.text(20, 12, "Recovery and Upgrade", 28, Theme.ACCENT, bold=True)
    step = "Step 2 of 2: optional swap and rows, then start Battle 2." if chosen else "Step 1 of 2: choose one dice upgrade (required)."
    ui.text(420, 22, step, 17, Theme.TEXT, bold=True)

    by_id = {c["id"]: c for c in view["combatants"]}
    ui.panel(12, 56, 300, 420, "Heroes after recovery")
    for index, hero in enumerate(upgrade["heroes"]):
        c = by_id[hero["hero_id"]]
        y = 84 + index * 76
        selected = hero["hero_id"] == ctrl.upgrade_hero
        ui.button(f"up:hero:{hero['hero_id']}", 20, y, 196, 68, hero["hero_name"],
                  lambda h=hero["hero_id"]: ctrl.select_upgrade_hero(h), selected=selected,
                  sublabel=f"HP {c['hp']}/{c['max_hp']}  MP {c['mana']}  CR {c['corruption']}",
                  tooltip="Show this hero's dice. HP partly recovered, mana refilled, shields and statuses cleared, corruption kept.")
        ui.button(f"up:row:{hero['hero_id']}", 222, y, 82, 68, c["row"].capitalize(),
                  lambda h=hero["hero_id"]: ctrl.toggle_formation(h), sublabel="row",
                  tooltip="Move this hero to the other row for Battle 2.")

    hero_view = next((h for h in upgrade["heroes"] if h["hero_id"] == ctrl.upgrade_hero), upgrade["heroes"][0])
    ui.panel(12, 484, 300, 200, f"{hero_view['hero_name']}: equipped dice")
    for index, entry in enumerate(hero_view["equipped"]):
        die = entry["die"]
        label = die["name"] + ("  [UPGRADED]" if entry["locked"] else "")
        ui.button(f"up:die:{die['id']}", 20, 512 + index * 56, 284, 48, label,
                  lambda d=die["id"]: ctrl.select_upgrade_die(d), selected=die["id"] == ctrl.upgrade_die,
                  sublabel=f"d{die['size']}  v{die['definition_version']}" + ("  locked against swapping" if entry["locked"] else ""),
                  tooltip="Show the three upgrade cards for this die.")

    # Offer cards
    ui.panel(322, 56, 610, 628, "Upgrade cards" if not chosen else "Upgrade applied")
    offers = ctrl.current_offers() if not chosen else []
    if chosen:
        record = upgrade["upgrades"][0]
        ui.paragraph(336, 90, f"{record['kind'].capitalize()} was applied to {by_id[record['hero_id']]['name']}'s {record['die_id']} "
                     f"(face {record['face_index'] + 1}, version {record['from_version']} -> {record['to_version']}). "
                     "It lasts through Battle 2 and is removed when the run ends.", 580, 16, Theme.TEXT, line_height=21)
        die_entry = next((e for e in hero_view["equipped"] if e["die"]["id"] == ctrl.upgrade_die), hero_view["equipped"][0])
        draw_die_faces(ui, 336, 180, 580, die_entry["die"])
    for index, offer in enumerate(offers[:3]):
        x = 334 + index * 198
        selected = offer["offer_id"] == ctrl.upgrade_offer
        preview = ctrl.offer_preview(offer)
        ui.button(f"up:offer:{index}", x, 84, 190, 44, f"{index + 1}. {offer['kind_name']}", lambda o=offer["offer_id"]: ctrl.select_offer(o),
                  selected=selected, hotkeys=(NUMBER_KEYS[index],), tooltip=offer["summary"])
        ui.panel(x, 132, 190, 150, fill=Theme.PANEL_ALT, border=Theme.ACCENT if selected else Theme.BORDER, width=2 if selected else 1)
        ui.text(x + 8, 138, f"Face {offer['face_index'] + 1} of {preview['before']['size']}", 13, Theme.DIM, bold=True)
        ui.text(x + 8, 156, "Before:", 13, Theme.FAINT, bold=True)
        ui.paragraph(x + 8, 172, f"{preview['before_face']['name']}: {preview['before_face']['text']}", 174, 13, Theme.DIM, line_height=15, max_lines=2)
        ui.text(x + 8, 208, "After:", 13, Theme.ACCENT, bold=True)
        ui.paragraph(x + 8, 224, f"{preview['after_face']['name']}: {preview['after_face']['text']}", 174, 13, Theme.TEXT, line_height=15, max_lines=3)
    selected_offer = next((o for o in offers if o["offer_id"] == ctrl.upgrade_offer), None)
    if not chosen:
        if selected_offer is not None:
            preview = ctrl.offer_preview(selected_offer)
            ui.text(336, 292, "Die before", 14, Theme.DIM, bold=True)
            draw_die_faces(ui, 336, 310, 580, preview["before"], max_rows=6)
            ui.text(336, 444, "Die after (faces and probabilities)", 14, Theme.ACCENT, bold=True)
            draw_die_faces(ui, 336, 462, 580, preview["after"], highlight_face=selected_offer["face_index"], max_rows=6)
        elif offers:
            ui.text(336, 300, "Select a card to compare the die before and after.", 15, Theme.FAINT)
        problem = ctrl.apply_problem()
        ui.button("up:apply", 336, 624, 300, 50, "Apply Upgrade  (A)", ctrl.apply_upgrade, enabled=problem is None, reason=problem,
                  hotkeys=(pygame.K_a,), default=problem is None, size=18,
                  tooltip="Apply the selected card. Exactly one upgrade per run; it cannot be undone.")

    # Equipment column
    ui.panel(942, 56, 326, 510, "Optional bench swap")
    ui.text(952, 80, f"Swaps remaining this run: {upgrade['swaps_remaining']}", 14, Theme.DIM)
    y = 102.0
    die_names = {e["die"]["id"]: e["die"]["name"] for e in hero_view["equipped"]}
    for bench in hero_view["bench"]:
        y = draw_die_faces(ui, 952, y, 306, bench["die"], max_rows=5) + 6
        for swap in bench["swaps"]:
            ui.button(f"up:swap:{hero_view['hero_id']}:{swap['out_die_id']}", 952, y, 306, 38,
                      f"Swap out {die_names.get(swap['out_die_id'], swap['out_die_id'])}",
                      lambda h=hero_view["hero_id"], o=swap["out_die_id"], i=bench["die"]["id"]: ctrl.swap_die(h, o, i),
                      enabled=swap["allowed"], reason=swap["reason"],
                      tooltip=f"Equip {bench['die']['name']} in place of {die_names.get(swap['out_die_id'], swap['out_die_id'])} for Battle 2.")
            y += 44
    if not hero_view["bench"]:
        ui.text(952, y, "No bench die.", 14, Theme.FAINT)
    proceed_problem = ctrl.proceed_problem()
    ui.button("up:start", 942, 576, 326, 108, "Start Battle 2  (Enter)", ctrl.start_next_battle, enabled=proceed_problem is None,
              reason=proceed_problem, default=proceed_problem is None, size=20, hotkeys=(pygame.K_b,),
              tooltip="Begin the second, harder battle with this party and equipment.")
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
        summary = f"No hero was left standing in Battle {outcome['battle_reached']}. The run is over; the upgrade is lost."
    ui.text(640, 116, summary, 18, Theme.TEXT, align="center")
    records = "   ".join(f"Battle {r['battle']}: {r['outcome']} ({r['activations']} activations, {r['ticks']} ticks)" for r in outcome["battle_records"])
    ui.text(640, 146, records, 15, Theme.DIM, align="center", max_width=1200)

    ui.panel(340, 180, 600, 330, "Combat metrics")
    y = 210.0
    for key, label in STAT_LABELS:
        ui.text(360, y, label, 16, Theme.DIM)
        ui.text(920, y, str(outcome["stats"][key]), 16, Theme.TEXT, bold=True, align="right")
        y += 26
    log_text = f"Event log: {outcome['log_path']}" if outcome["log_path"] else f"Event log not written: {outcome['log_error'] or 'unknown reason'}"
    ui.text(640, 522, log_text, 13, Theme.FAINT, align="center", max_width=1200)
    ui.text(640, 542, f"Seed {outcome['seed']} (use --seed to replay the same dice).", 13, Theme.FAINT, align="center")
    ui.button("out:retry", 250, 580, 250, 60, "Retry Same Party  (R)", ctrl.retry_same_party, hotkeys=(pygame.K_r,), default=True, size=18,
              tooltip="Start a new run at Battle 1 with the same heroes and rows. No upgrade carries over.")
    ui.button("out:modify", 515, 580, 250, 60, "Modify Party  (M)", ctrl.modify_party, hotkeys=(pygame.K_m,), size=18,
              tooltip="Return to party setup, then start a new run at Battle 1.")
    ui.button("out:menu", 780, 580, 250, 60, "Main Menu  (Esc)", ctrl.to_main_menu, size=18, tooltip="Return to the main menu.")
    ui.escape_action = ctrl.to_main_menu
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
