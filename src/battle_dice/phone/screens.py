"""What each phone screen shows, and what a tap does: the walking skeleton (menu, party, one battle).

``screen(controller)`` returns a description of the screen the game is on::

    {"screen": "battle", "title": "...", "message": "...", "is_error": False,
     "groups": [{"title": "Enemies", "tone": "enemy", "cards": [{"title": ..., "lines": [...], "tone": ..., "tap": action or None}]}],
     "actions": [{"id": "roll", "label": "Roll the dice", "enabled": True, "reason": "", "primary": True}]}

``act(controller, action_id)`` does what the action with that id stands for and lets the game run on until
it waits for the player. Both use the same controller the desktop game uses; no rule is decided here.
"""

from __future__ import annotations

import re
from typing import Any

from battle_dice.app.controller import AppController, Screen

Json = dict[str, Any]
#: Hints at keys in the controller's messages, which a phone has not: " (R)", " (Z, X)", " (Esc cancels)", " (Enter)".
_KEY_HINT = re.compile(r"\s*\((?:[A-Z](?:, [A-Z])*|Esc|Enter|Esc cancels)\)")
#: Steps the game may take on its own before it must wait for the player again.
_SETTLE_LIMIT = 5000
CLASS_ORDER = ("squire", "apprentice", "scout")


def touch_wording(text: str) -> str:
    """A message of the controller without its key hints: "Roll the dice (R)." becomes "Roll the dice."."""
    return _KEY_HINT.sub("", text)


def _action(action_id: str, label: str, enabled: bool = True, reason: str | None = "", primary: bool = False) -> Json:
    return {"id": action_id, "label": label, "enabled": enabled, "reason": "" if enabled else (reason or "Not possible right now."), "primary": primary}


def _base(controller: AppController, name: str, title: str) -> Json:
    return {"screen": name, "title": title, "message": touch_wording(controller.message), "is_error": controller.message_is_error,
            "groups": [], "actions": []}


def settle(controller: AppController) -> None:
    """Let the game take every step that needs no decision."""
    for _ in range(_SETTLE_LIMIT):
        if not controller.auto_advance():
            return


# --------------------------------------------------------------------------------------------
# What a screen shows
# --------------------------------------------------------------------------------------------


def screen(controller: AppController) -> Json:
    if controller.screen == Screen.MAIN_MENU:
        return _menu(controller)
    if controller.screen == Screen.PARTY_SETUP:
        return _party(controller)
    if controller.screen == Screen.BATTLE:
        return _battle(controller)
    if controller.screen == Screen.ERROR:
        view = _base(controller, "error", "Something went wrong")
        view["groups"].append({"title": "Details", "tone": "plain", "cards": [{"title": "", "lines": controller.error_text.strip().splitlines()[-8:], "tone": "plain", "tap": None}]})
        view["actions"].append(_action("to_menu", "Back to the menu", primary=True))
        return view
    # The upgrade and the outcome: the skeleton says where the run stands and leads back.
    view = _base(controller, "after_battle", "Battle over")
    engine = controller.engine
    if engine is not None:
        records = [f"Battle {record['battle']}: {record['outcome']}" for record in engine.state.battle_records]
        view["groups"].append({"title": "This run", "tone": "plain", "cards": [{"title": "", "lines": records or ["No battle is finished yet."], "tone": "plain", "tap": None}]})
    view["message"] = "The walking skeleton ends after one battle. The upgrade, the second battle and the result come with the real phone screens."
    view["actions"].append(_action("to_menu", "Back to the menu", primary=True))
    return view


def _menu(controller: AppController) -> Json:
    view = _base(controller, "menu", "Battle Dice")
    view["message"] = view["message"] or "A turn-based tactical dice game. This is the walking skeleton of the phone app: one battle."
    view["actions"].append(_action("menu:new", "New run", primary=True))
    return view


def _party(controller: AppController) -> Json:
    minimum, maximum = controller.party_limits()
    view = _base(controller, "party", f"Party: {len(controller.party)} of {maximum} heroes")
    cards = []
    for index, member in enumerate(controller.party):
        cls = controller.content.class_def(member["class_id"])
        cards.append({"title": f"{index + 1}. {cls['name']}", "lines": [f"{member['row'].capitalize()} row", f"HP {cls['start_hp']}   Speed {cls['speed']}"],
                      "tone": "hero", "tap": _action(f"party:remove:{index}", "Remove")})
    view["groups"].append({"title": "Heroes" if cards else "No hero yet: add one to three below", "tone": "hero", "cards": cards})
    full = len(controller.party) >= maximum
    for class_id in CLASS_ORDER:
        name = controller.content.class_def(class_id)["name"]
        view["actions"].append(_action(f"party:add:{class_id}", f"Add {name}", enabled=not full, reason=f"The party already has {maximum} heroes."))
    problem = controller.begin_problem()
    view["actions"].append(_action("party:begin", "Begin the battle", enabled=problem is None, reason=problem, primary=True))
    view["actions"].append(_action("to_menu", "Back"))
    return view


def _unit(c: Json, active: str | None, tap: Json | None) -> Json:
    lines = [f"HP {c['hp']}/{c['max_hp']}   Shield {c['shields']}"]
    if c["side"] == "hero":
        lines.append(f"Mana {c['mana']}/{c['max_mana']}   Corruption {c['corruption']}/{c['max_corruption']}")
    if c["state"] != "standing":
        lines.append("Down" if c["side"] == "hero" else "Defeated")
    elif c["statuses"]:
        lines.append(", ".join(f"{status['label']} x{status['stacks']} ({status['remaining']})" for status in c["statuses"]))
    return {"title": c["name"] + ("  (acting)" if c["id"] == active else ""), "lines": lines, "tone": c["side"], "tap": tap}


def _battle(controller: AppController) -> Json:
    view = controller.view()
    turn, reaction = view.get("hero_turn"), view.get("reaction")
    out = _base(controller, "battle", f"Battle {view['battle']} of {view['battle_count']}")
    targeting = controller.targeting_die
    option = next((die for die in turn["dice"] if die["die_id"] == targeting), None) if turn and targeting else None
    eligible = set(option["eligible_target_ids"]) if option else set()

    def unit(c: Json) -> Json:
        tap = _action(f"target:{c['id']}", "Choose") if c["id"] in eligible else None
        return _unit(c, view["active_combatant_id"], tap)

    units = view["combatants"]
    out["groups"].append({"title": "Enemies", "tone": "enemy", "cards": [unit(c) for c in units if c["side"] == "enemy"]})
    out["groups"].append({"title": "Heroes", "tone": "hero", "cards": [unit(c) for c in units if c["side"] == "hero"]})
    intent = view.get("intent")
    if intent is not None and not intent["cancelled"]:
        note = f" Now {intent['forecast']['note']}." if intent["forecast"]["note"] else ""
        out["groups"].append({"title": "Enemy action", "tone": "enemy", "cards": [
            {"title": f"{intent['actor_name']}: {intent['name']}", "lines": [f"{intent['text']} on {', '.join(intent['target_names'])}.{note}"], "tone": "enemy", "tap": None}]})
    if reaction is not None:
        names = {c["id"]: c["name"] for c in units}
        for choice in reaction["options"]:
            targets = list(choice["target_ids"]) if choice["needs_target"] and choice["eligible"] else []
            if targets:
                for target_id in targets:
                    out["actions"].append(_action(f"react:{choice['hero_id']}:{target_id}", f"{choice['name']} on {names[target_id]} ({choice['hero_name']}, {choice['mana_cost']} mana)"))
            else:
                out["actions"].append(_action(f"react:{choice['hero_id']}", f"{choice['name']} ({choice['hero_name']}, {choice['mana_cost']} mana)",
                                              enabled=choice["eligible"], reason=choice["reason"]))
        out["actions"].append(_action("skip", "Skip this stage", primary=True))
        out["actions"].append(_action("skip_all", "No reaction to this action"))
    elif turn is not None and not turn["rolled"]:
        out["actions"].append(_action("roll", "Roll the dice", primary=True))
    elif turn is not None:
        preview = controller.plan_preview()
        planned = {entry["die_id"]: entry for entry in preview["ordered"]}
        cards = []
        for die in turn["dice"]:
            face = die["face"]
            forecast = planned[die["die_id"]]["forecast"] if die["die_id"] in planned and not preview["problem"] else die["forecast"]["note"]
            lines = [face["text"]] + ([f"Now {forecast}"] if forecast else [])
            in_plan = die["die_id"] in {entry["die_id"] for entry in controller.draft}
            lines.append("In the plan" if in_plan else "Kept" if die["kept"] else die["reason"] or "")
            tap = _action(f"use:{die['die_id']}", "Remove" if in_plan else "Use", enabled=die["selectable"] or in_plan, reason=die["reason"])
            cards.append({"title": f"{die['die_name']}: {face['name']}", "lines": [line for line in lines if line], "tone": "die", "tap": tap,
                          "extra": _action(f"keep:{die['die_id']}", "Unkeep" if die["kept"] else "Keep")})
        out["groups"].append({"title": f"{turn['hero_name']}: rolled dice", "tone": "die", "cards": cards})
        if targeting:
            out["actions"].append(_action("cancel_target", "Choose another die"))
        else:
            unkept = [die for die in turn["dice"] if not die["kept"]]
            left = turn["rerolls_remaining"]
            out["actions"].append(_action("reroll", f"Reroll ({left} left)", enabled=left > 0 and bool(unkept),
                                          reason="No reroll is left." if left <= 0 else "Every die is kept."))
            problem = controller.confirm_problem()
            out["actions"].append(_action("confirm", "Confirm the plan", enabled=problem is None, reason=problem, primary=True))
            out["actions"].append(_action("pass", "Pass"))
            if preview["backlash"]:
                out["message"] = (out["message"] + " " + preview["backlash"]).strip()
    out["log"] = controller.log_lines(6)
    return out


# --------------------------------------------------------------------------------------------
# What a tap does
# --------------------------------------------------------------------------------------------


def act(controller: AppController, action_id: str) -> None:
    """Do what the action stands for, then let the game run on until it waits for the player.

    An id the current screen does not offer is refused with a message; nothing else happens.
    """
    offered = {action["id"]: action for action in _all_actions(screen(controller))}
    chosen = offered.get(action_id)
    if chosen is None:
        controller.warn("That is not possible on this screen.")
        return
    if not chosen["enabled"]:
        controller.warn(chosen["reason"])
        return
    kind, _, rest = action_id.partition(":")
    if action_id == "menu:new":
        controller.new_run()
    elif action_id == "to_menu":
        controller.to_main_menu()
    elif action_id == "party:begin":
        controller.begin_run()
    elif kind == "party":
        what, _, value = rest.partition(":")
        if what == "add":
            controller.add_hero(value)
        else:
            controller.remove_hero(int(value))
    elif kind == "roll":
        controller.roll()
    elif kind == "reroll":
        controller.reroll()
    elif kind == "keep":
        controller.toggle_keep(rest)
    elif kind == "use":
        controller.use_die(rest)
    elif kind == "target":
        controller.choose_target(rest)
    elif kind == "cancel_target":
        controller.cancel_targeting()
    elif kind == "confirm":
        controller.confirm_plan()
    elif kind == "pass":
        controller.pass_turn()
    elif kind == "react":
        hero_id, _, target_id = rest.partition(":")
        controller.use_reaction(hero_id, target_id or None)
    elif kind == "skip":
        controller.skip_stage()
    elif kind == "skip_all":
        controller.skip_all_stages()
    settle(controller)


def _all_actions(view: Json) -> list[Json]:
    """Every action of a screen: its buttons, and the taps on its cards."""
    found = list(view["actions"])
    for group in view["groups"]:
        for card in group["cards"]:
            found += [card[key] for key in ("tap", "extra") if card.get(key)]
    return found
