"""Application controller: menus, party setup, battle flow, upgrade and outcome states (section 14.3).

The controller is presentation-agnostic (no pygame). It owns the *draft* the player is editing
(party list, plan under construction, upgrade selection) and talks to the authoritative rules
engine only through commands. Rejections become user-visible feedback; unexpected exceptions
become a recoverable error screen instead of a crash.
"""

from __future__ import annotations

import copy
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from battle_dice.content.loader import Content, load_content
from battle_dice.core import commands as cmd
from battle_dice.core import planning
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType, summarize, write_jsonl
from battle_dice.core.models import ROW_BACK, ROW_FRONT, CombatPhase, RunPhase
from battle_dice.core.progression import face_from_plain
from battle_dice.core.replay import export_run
from battle_dice.core.view import action_forecast, combat_log, die_view, face_view, hero_turn_view, snapshot


class Screen:
    MAIN_MENU = "main_menu"
    CONTROLS = "controls"
    PARTY_SETUP = "party_setup"
    BATTLE = "battle"
    UPGRADE = "upgrade"  # RECOVERY_AND_UPGRADE
    OUTCOME = "outcome"  # VICTORY_SUMMARY / DEFEAT_SUMMARY
    ERROR = "error"


FALLBACK_TEXT = {
    "single_enemy": "If the target is gone: retargets (same row, then lowest HP%, then ID); cancels if none.",
    "all_enemies": "Hits every enemy still standing; cancels if none.",
    "single_ally": "If the target becomes invalid: cancelled, no cost spent.",
    "all_allies": "Affects every ally still standing.",
    "self": "Always valid while the hero can act.",
    "none": "",
}


def default_log_dir() -> Path:
    """Where JSONL event logs go when no folder is given.

    From source this is ``./logs``. A packaged build may live in a read-only folder, so it uses
    the per-user application data folder instead.
    """
    override = os.environ.get("BATTLE_DICE_LOG_DIR")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "BattleDice" / "logs"
    return Path.cwd() / "logs"


def default_seed() -> int:
    """A fresh run seed. Chosen by the application layer, never by the rules engine."""
    return time.time_ns() & 0xFFFFFFFF


class AppController:
    def __init__(
        self,
        content: Content | None = None,
        seed_source: Any = None,
        log_dir: str | Path | None = None,
        fixed_seed: int | None = None,
    ):
        self.content = content if content is not None else load_content()
        self.screen = Screen.MAIN_MENU
        self.engine: Engine | None = None
        self.party: list[dict[str, str]] = []
        self.message = ""
        self.message_is_error = False
        self.message_serial = 0  # bumped on every new message, so the status bar can tell it is new
        self.error_text = ""
        # In-run menu (Esc). While it is open nothing in the run advances.
        self.paused = False
        self.pause_help = False
        self.fixed_seed = fixed_seed
        self._seed_source = seed_source or default_seed
        self.log_dir = Path(log_dir) if log_dir is not None else default_log_dir()
        self.log_path: Path | None = None
        self.log_error: str | None = None
        self.runs_started = 0
        # Hero planning draft (kept locally until Confirm; section 5.6).
        self.draft: list[dict[str, Any]] = []
        self.targeting_die: str | None = None
        self.inspect_die: str | None = None
        self.reaction_hero: str | None = None  # reacting hero whose target is being chosen by number key
        self.hints_shown: set[str] = set()  # one-time guidance already given in this run
        self.skip_reactions_for: str | None = None  # enemy intent whose remaining stages are all skipped
        self.swap_confirm: tuple[str, str, str] | None = None  # a swap that gives up a larger die, awaiting a second press
        self._draft_owner: tuple[str | None, int] = (None, -1)
        # Upgrade screen selection.
        self.upgrade_hero: str | None = None
        self.upgrade_die: str | None = None
        self.upgrade_offer: str | None = None
        self.selected_slot = 0

    # ----------------------------------------------------------------------------------------
    # Feedback helpers
    # ----------------------------------------------------------------------------------------

    def info(self, text: str) -> None:
        self.message, self.message_is_error = text, False
        self.message_serial += 1

    def warn(self, text: str) -> None:
        self.message, self.message_is_error = text, True
        self.message_serial += 1

    def fail(self) -> None:
        """Record the exception being handled and switch to the recoverable error screen."""
        self.error_text = traceback.format_exc()
        self.screen = Screen.ERROR
        self.paused = self.pause_help = False

    def _guard(self, action: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a controller action; turn an unexpected exception into the recoverable error screen."""
        try:
            return action(*args, **kwargs)
        except Exception:  # noqa: BLE001 - the UI must never crash on an engine fault
            self.fail()
            return None

    def _send(self, command_type: str, **params: Any) -> bool:
        assert self.engine is not None
        result = self.engine.do(command_type, **params)
        if not result.accepted:
            self.warn(result.reason or "That is not allowed right now.")
            return False
        self._sync_screen()
        return True

    def refresh(self) -> None:
        """Re-derive the current screen from engine state (for callers that drove the engine directly)."""
        self._guard(self._sync_screen)

    def _sync_screen(self) -> None:
        engine = self.engine
        if engine is None or not engine.started:
            return
        phase = engine.state.phase
        if phase in (RunPhase.VICTORY, RunPhase.DEFEAT):
            if self.screen != Screen.OUTCOME:
                self._write_log()
                self.info("The run is over. Retry with the same party, change the party, or return to the menu.")
            self.screen = Screen.OUTCOME
        elif phase in (RunPhase.UPGRADE, RunPhase.EQUIPMENT):
            if self.screen != Screen.UPGRADE:
                self._enter_upgrade()
            self.screen = Screen.UPGRADE
        else:
            self.screen = Screen.BATTLE
        self._sync_draft()

    def _sync_draft(self) -> None:
        """Drop the local draft whenever a different activation begins or planning is over."""
        engine = self.engine
        owner: tuple[str | None, int] = (None, -1)
        if engine is not None and engine.started and engine.state.phase == RunPhase.BATTLE:
            combat = engine.combat
            planning_phases = (CombatPhase.HERO_ROLL, CombatPhase.KEEP_REROLL, CombatPhase.ACTION_PLAN)
            if combat.turn is not None and combat.phase in planning_phases:
                owner = (combat.turn.hero_id, combat.activation_count)
        if owner != self._draft_owner:
            self._draft_owner = owner
            self.draft = []
            self.targeting_die = None
            self.inspect_die = None
        if engine is None or not engine.started or engine.state.phase != RunPhase.BATTLE \
                or engine.combat.phase not in CombatPhase.STAGE_BY_WINDOW:
            self.reaction_hero = None

    # ----------------------------------------------------------------------------------------
    # Menus and party setup
    # ----------------------------------------------------------------------------------------

    def new_run(self) -> None:
        self.screen = Screen.PARTY_SETUP
        self.info("Add 1 to 5 heroes, set their rows, then begin.")

    def show_controls(self) -> None:
        self.screen = Screen.CONTROLS

    def to_main_menu(self) -> None:
        self.screen = Screen.MAIN_MENU
        self.engine = None
        self.paused = self.pause_help = False
        self.reaction_hero = None
        self.message = ""
        self.message_serial += 1
        self.error_text = ""

    # ----------------------------------------------------------------------------------------
    # In-run menu
    # ----------------------------------------------------------------------------------------

    def run_in_progress(self) -> bool:
        return self.engine is not None and self.screen in (Screen.BATTLE, Screen.UPGRADE)

    def open_pause(self) -> None:
        if self.run_in_progress():
            self.paused, self.pause_help = True, False
            self.info("Paused. Nothing advances while this menu is open.")

    def resume(self) -> None:
        self.paused = self.pause_help = False
        self.info("Resumed.")

    def toggle_pause_help(self) -> None:
        self.pause_help = not self.pause_help

    def abandon_to_menu(self) -> None:
        """Give up the current run. Nothing is saved; an unfinished run writes no event log."""
        self.to_main_menu()
        self.info("Run abandoned.")

    def abandon_to_party(self) -> None:
        self.modify_party()
        self.info("Run abandoned. Change the party, then begin a new run.")

    def party_limits(self) -> tuple[int, int]:
        limits = self.content.balance["party"]
        return limits["min_size"], limits["max_size"]

    def add_hero(self, class_id: str) -> None:
        _, maximum = self.party_limits()
        if len(self.party) >= maximum:
            self.warn(f"A party can have at most {maximum} heroes.")
            return
        row = self.content.class_def(class_id)["suggested_row"]
        self.party.append({"class_id": class_id, "row": row})
        self.selected_slot = len(self.party) - 1
        self.info(f"Added {self.content.class_def(class_id)['name']} to the {row} row.")

    def remove_hero(self, index: int) -> None:
        if 0 <= index < len(self.party):
            removed = self.party.pop(index)
            self.selected_slot = max(0, min(self.selected_slot, len(self.party) - 1))
            self.info(f"Removed {self.content.class_def(removed['class_id'])['name']}.")

    def toggle_party_row(self, index: int) -> None:
        if 0 <= index < len(self.party):
            member = self.party[index]
            member["row"] = ROW_BACK if member["row"] == ROW_FRONT else ROW_FRONT
            self.selected_slot = index
            self.info(f"{self.content.class_def(member['class_id'])['name']} moves to the {member['row']} row.")

    def begin_problem(self) -> str | None:
        minimum, maximum = self.party_limits()
        if len(self.party) < minimum:
            return f"Add at least {minimum} hero to begin."
        if len(self.party) > maximum:
            return f"A party can have at most {maximum} heroes."
        return None

    def begin_run(self) -> None:
        self._guard(self._begin_run)

    def _begin_run(self) -> None:
        problem = self.begin_problem()
        if problem:
            self.warn(problem)
            return
        seed = self.fixed_seed if self.fixed_seed is not None else int(self._seed_source())
        engine = Engine(self.content)
        self.runs_started += 1
        result = engine.do(cmd.START_RUN, seed=seed, party=[dict(m) for m in self.party],
                           run_id=f"run-{seed}-{self.runs_started}")
        if not result.accepted:
            self.warn(result.reason or "The run could not be started.")
            return
        self.engine = engine
        self.paused = self.pause_help = False
        self.reaction_hero = None
        self.hints_shown = set()
        self.skip_reactions_for = None
        self.swap_confirm = None
        self.log_path = None
        self.log_error = None
        self._draft_owner = (None, -1)
        self.draft = []
        self.upgrade_hero = self.upgrade_die = self.upgrade_offer = None
        self.info(f"Battle 1 begins. Seed {seed}.")
        self._sync_screen()

    def retry_same_party(self) -> None:
        """Defeat or victory summary -> a brand-new run at Battle 1 with the same party."""
        self.begin_run()

    def modify_party(self) -> None:
        self.engine = None
        self.paused = self.pause_help = False
        self.reaction_hero = None
        self.screen = Screen.PARTY_SETUP
        self.info("Change the party, then begin a new run.")

    # ----------------------------------------------------------------------------------------
    # Battle: automatic phases
    # ----------------------------------------------------------------------------------------

    def waiting_for_player(self) -> bool:
        return self.paused or self.engine is None or not self.engine.started or self.engine.needs_input()

    def auto_advance(self) -> bool:
        """Advance one automatic combat step. Returns True when a step was taken."""
        if self.paused or self.screen != Screen.BATTLE or self.engine is None or self.engine.needs_input():
            return False
        stepped = bool(self._guard(self._send, cmd.ADVANCE_PHASE))
        if stepped:
            self._reaction_opened()
        return stepped

    def _in_reaction_window(self) -> bool:
        engine = self.engine
        return (engine is not None and self.screen == Screen.BATTLE and engine.started and not engine.finished()
                and engine.state.phase == RunPhase.BATTLE and engine.needs_input()
                and engine.combat.phase in CombatPhase.STAGE_BY_WINDOW)

    def _reaction_opened(self) -> None:
        """A reaction decision has just opened: skip it if the player declined every stage, else say so."""
        while self._in_reaction_window():
            assert self.engine is not None
            intent = self.engine.combat.committed_intent
            if intent is None or intent.id != self.skip_reactions_for:
                break
            if not self._guard(self._send, cmd.SKIP_REACTION_STAGE):
                return
        if not self._in_reaction_window():
            return
        if "reaction" not in self.hints_shown:
            self.hints_shown.add("reaction")
            self.info("An enemy action is revealed. A hero may react before it lands: pick a reaction, or Skip Stage (S).")
        else:
            self.info("Reaction decision: pick a reaction, Skip Stage (S), or Skip All (A).")

    # ----------------------------------------------------------------------------------------
    # Battle: hero activation
    # ----------------------------------------------------------------------------------------

    def _turn_view(self) -> dict[str, Any] | None:
        if self.engine is None or not self.engine.started or self.engine.state.phase != RunPhase.BATTLE:
            return None
        return hero_turn_view(self.engine)

    def roll(self) -> None:
        if self._guard(self._send, cmd.ROLL_DICE):
            if "reroll" not in self.hints_shown:
                self.hints_shown.add("reroll")
                self.info("Rolled. Reroll (R) rerolls every die you have not kept; Keep (Z, X) holds a die. Then choose actions.")
            else:
                self.info("Keep dice, reroll the rest, then choose actions.")

    def toggle_keep(self, die_id: str) -> None:
        engine = self.engine
        if engine is None or engine.combat.turn is None:
            return
        kept = set(engine.combat.turn.kept)
        kept.symmetric_difference_update({die_id})
        self._guard(self._send, cmd.SET_KEPT_DICE, die_ids=sorted(kept))

    def reroll(self) -> None:
        engine = self.engine
        if engine is None or engine.combat.turn is None:
            return
        kept = set(engine.combat.turn.kept)
        if self._guard(self._send, cmd.REROLL_UNKEPT):
            dropped = [a for a in self.draft if a["die_id"] not in kept]
            self.draft = [a for a in self.draft if a["die_id"] in kept]
            if self.targeting_die is not None and self.targeting_die not in kept:
                self.targeting_die = None
            turn = engine.combat.turn
            left = turn.rerolls_remaining if turn is not None else 0
            note = " Planned actions on rerolled dice were removed." if dropped else ""
            self.info(f"Rerolled the unkept dice. {left} reroll(s) left.{note}")

    def use_die(self, die_id: str) -> None:
        """Add the rolled face of ``die_id`` to the draft plan (or remove it if already planned)."""
        self._guard(self._use_die, die_id)

    def _use_die(self, die_id: str) -> None:
        view = self._turn_view()
        if view is None or not view["rolled"]:
            return
        if any(a["die_id"] == die_id for a in self.draft):
            self.draft = [a for a in self.draft if a["die_id"] != die_id]
            self.targeting_die = None
            self.info("Action removed from the plan.")
            return
        option = next((d for d in view["dice"] if d["die_id"] == die_id), None)
        if option is None:
            return
        if not option["selectable"]:
            self.warn(option["reason"] or "That face cannot be used.")
            return
        if len(self.draft) >= view["scheduling"]["max_actions"]:
            self.warn(f"{view['policy_text']} Remove an action first.")
            return
        scope = option["face"]["target_scope"]
        if scope in ("single_enemy", "single_ally"):
            if len(option["eligible_target_ids"]) == 1 and scope == "single_enemy":
                self.draft.append({"die_id": die_id, "target_ids": list(option["eligible_target_ids"])})
                self.targeting_die = None
                self._report_draft()
            else:
                self.targeting_die = die_id
                self.info(f"Choose a target for {option['face']['name']} (Esc cancels).")
            return
        self.draft.append({"die_id": die_id, "target_ids": []})
        self._report_draft()

    def choose_target(self, target_id: str) -> None:
        self._guard(self._choose_target, target_id)

    def _choose_target(self, target_id: str) -> None:
        engine = self.engine
        view = self._turn_view()
        if engine is None or view is None or self.targeting_die is None:
            return
        option = next((d for d in view["dice"] if d["die_id"] == self.targeting_die), None)
        if option is None:
            self.targeting_die = None
            return
        if target_id not in option["eligible_target_ids"]:
            hero = engine.combat.combatants[view["hero_id"]]
            face = engine.die_for(hero.id, option["die_id"]).faces[option["face_index"]]
            self.warn(planning.target_problem(engine, hero, face, target_id))
            return
        self.draft.append({"die_id": self.targeting_die, "target_ids": [target_id]})
        self.targeting_die = None
        self._report_draft()

    def cancel_targeting(self) -> None:
        if self.targeting_die is not None:
            self.targeting_die = None
            self.info("Target selection cancelled.")

    def swap_plan_order(self) -> None:
        if len(self.draft) >= 2:
            self.draft.reverse()
            self._guard(self._report_draft)

    def clear_plan(self) -> None:
        self.draft = []
        self.targeting_die = None
        self.info("Plan cleared.")

    def _report_draft(self) -> None:
        preview = self.plan_preview()
        if preview["problem"]:
            self.warn(preview["problem"])
        else:
            self.info("Plan is legal. Confirm to lock it in, or keep editing.")

    def plan_preview(self) -> dict[str, Any]:
        """Validated view of the draft: resolution order, costs, target fallback, or the problem."""
        engine = self.engine
        result: dict[str, Any] = {"problem": None, "ordered": [], "mana_before": 0, "mana_after": 0}
        if engine is None or engine.combat.turn is None:
            return result
        hero = engine.combat.combatants[engine.combat.turn.hero_id]
        result["mana_before"] = result["mana_after"] = hero.mana
        if not self.draft:
            return result
        intents, problem = engine.preview_plan(self.draft)
        result["problem"] = problem
        if problem is not None:
            # Still list what is drafted, so the player can see which action to change.
            turn = engine.combat.turn
            for entry in self.draft:
                if entry["die_id"] not in turn.rolled:
                    continue
                face = engine.die_for(hero.id, entry["die_id"]).faces[turn.rolled[entry["die_id"]]]
                result["ordered"].append(
                    {
                        "die_id": entry["die_id"],
                        "name": face.name,
                        "category": face.category,
                        "action_speed": face.action_speed,
                        "mana_cost": face.mana_cost,
                        "text": face_view(face)["text"],
                        "target_names": [engine.combat.combatants[t].name for t in entry["target_ids"]
                                         if t in engine.combat.combatants],
                        "fallback": "",
                        "forecast": action_forecast(engine, hero, face)["note"],
                    }
                )
            return result
        mana = hero.mana
        opening = engine.build(hero.id).schedule.opening_categories
        for position, intent in enumerate(intents):
            face = engine.intent_face(intent)
            target = engine.combat.combatants[intent.committed_target_ids[0]] if intent.committed_target_ids else hero
            combo = len(intents) == 2 and position == 1 and intents[0].category in opening
            mana -= face.mana_cost
            for effect in face.effects:
                if effect["type"] == "gain_mana" and effect.get("target", "target") == "self":
                    mana = min(hero.max_mana, mana + face.effect_amount(effect))
            result["ordered"].append(
                {
                    "die_id": intent.source_die_id,
                    "name": intent.name,
                    "category": intent.category,
                    "action_speed": intent.action_speed,
                    "mana_cost": face.mana_cost,
                    "text": face_view(face)["text"],
                    "target_names": [engine.combat.combatants[t].name for t in intent.committed_target_ids],
                    "fallback": FALLBACK_TEXT[face.target_scope],
                    "forecast": action_forecast(engine, hero, face, intent, target, combo)["note"],
                }
            )
        result["mana_after"] = mana
        return result

    def confirm_problem(self) -> str | None:
        if self.targeting_die is not None:
            return "Finish choosing a target first."
        if not self.draft:
            return "No action selected. Choose a die, or Pass."
        return self.plan_preview()["problem"]

    def confirm_plan(self) -> None:
        self._guard(self._confirm_plan)

    def _confirm_plan(self) -> None:
        problem = self.confirm_problem()
        if problem:
            self.warn(problem)
            return
        self._commit(list(self.draft))

    def pass_turn(self) -> None:
        self._guard(self._commit, [])

    def _commit(self, actions: list[dict[str, Any]]) -> None:
        if not self._send(cmd.SET_ACTION_PLAN, actions=actions):
            return
        if self._send(cmd.COMMIT_ACTION_PLAN):
            self.info("Plan locked. Resolving." if actions else "Passed.")

    # ----------------------------------------------------------------------------------------
    # Battle: reactions
    # ----------------------------------------------------------------------------------------

    def use_reaction(self, hero_id: str, target_id: str | None = None) -> None:
        self.reaction_hero = None
        if self._guard(self._send, cmd.USE_REACTION, hero_id=hero_id, target_id=target_id):
            self.info("Reaction used.")
            self._reaction_opened()

    def pick_reaction(self, hero_id: str, needs_target: bool, target_ids: list[str]) -> None:
        """Keyboard path: choose the reacting hero first, then the ally by number."""
        if not needs_target:
            self.use_reaction(hero_id)
        elif len(target_ids) == 1:
            self.use_reaction(hero_id, target_ids[0])
        elif self.reaction_hero == hero_id:
            self.cancel_reaction_pick()
        else:
            self.reaction_hero = hero_id
            self.info("Choose which ally receives the reaction: press its number or click it (Esc cancels).")

    def cancel_reaction_pick(self) -> None:
        if self.reaction_hero is not None:
            self.reaction_hero = None
            self.info("Reaction target selection cancelled.")

    def skip_stage(self) -> None:
        self.reaction_hero = None
        if self._guard(self._send, cmd.SKIP_REACTION_STAGE):
            self.info("Stage skipped.")
            self._reaction_opened()

    def skip_all_stages(self) -> None:
        """Decline every remaining reaction stage for the enemy action now revealed."""
        engine = self.engine
        if engine is None or not self._in_reaction_window() or engine.combat.committed_intent is None:
            return
        self.reaction_hero = None
        self.skip_reactions_for = engine.combat.committed_intent.id
        name = engine.combat.committed_intent.name
        if self._guard(self._send, cmd.SKIP_REACTION_STAGE):
            self._reaction_opened()
            self.info(f"No reaction to {name}: every stage skipped.")

    # ----------------------------------------------------------------------------------------
    # Recovery, upgrade and equipment
    # ----------------------------------------------------------------------------------------

    def _enter_upgrade(self) -> None:
        engine = self.engine
        assert engine is not None
        heroes = engine.combat.side("hero")
        self.upgrade_hero = heroes[0].id
        self.upgrade_die = heroes[0].equipped_dice_ids[0]
        self.upgrade_offer = None
        self.info("Battle 1 won. Choose one dice upgrade (required).")

    def select_upgrade_hero(self, hero_id: str) -> None:
        engine = self.engine
        if engine is None:
            return
        self.upgrade_hero = hero_id
        self.upgrade_die = engine.combat.combatants[hero_id].equipped_dice_ids[0]
        self.upgrade_offer = None

    def select_upgrade_die(self, die_id: str) -> None:
        self.upgrade_die = die_id
        self.upgrade_offer = None

    def select_offer(self, offer_id: str) -> None:
        self.upgrade_offer = offer_id
        self.info("Review the before/after faces, then apply the upgrade.")

    def current_offers(self) -> list[dict[str, Any]]:
        engine = self.engine
        if engine is None or self.upgrade_hero is None or self.upgrade_die is None:
            return []
        return copy.deepcopy(engine.state.upgrade_offers.get(self.upgrade_hero, {}).get(self.upgrade_die, []))

    def offer_preview(self, offer: dict[str, Any]) -> dict[str, Any]:
        """Before/after die views (faces and probabilities) for an upgrade card."""
        engine = self.engine
        assert engine is not None
        before = engine.die_for(offer["hero_id"], offer["die_id"])
        after = copy.deepcopy(before)
        after.faces[offer["face_index"]] = face_from_plain(offer["after"])
        after.definition_version = before.definition_version + 1
        return {
            "before": die_view(before),
            "after": die_view(after),
            "before_face": face_view(face_from_plain(offer["before"])),
            "after_face": face_view(face_from_plain(offer["after"])),
        }

    def apply_problem(self) -> str | None:
        engine = self.engine
        if engine is None:
            return "No run."
        if engine.state.phase != RunPhase.UPGRADE:
            return "The upgrade has already been applied."
        if self.upgrade_offer is None:
            return "Select one of the three upgrade cards first."
        return None

    def apply_upgrade(self) -> None:
        problem = self.apply_problem()
        if problem:
            self.warn(problem)
            return
        assert self.upgrade_hero and self.upgrade_die and self.upgrade_offer
        if self._guard(self._send, cmd.CHOOSE_UPGRADE, hero_id=self.upgrade_hero, die_id=self.upgrade_die,
                       offer_id=self.upgrade_offer):
            self.upgrade_offer = None
            self.info("Upgrade applied. Optional: swap one die per hero or change rows, then start Battle 2.")

    def swap_gives_up_a_larger_die(self, hero_id: str, out_die_id: str, in_die_id: str) -> bool:
        engine = self.engine
        arriving = engine.base_die(hero_id, in_die_id) if engine is not None else None
        if engine is None or arriving is None:
            return False
        return engine.die_for(hero_id, out_die_id).size > arriving.size

    def swap_die(self, hero_id: str, out_die_id: str, in_die_id: str) -> None:
        engine = self.engine
        request = (hero_id, out_die_id, in_die_id)
        if engine is not None and self.swap_gives_up_a_larger_die(*request) and self.swap_confirm != request:
            self.swap_confirm = request
            leaving, arriving = engine.die_for(hero_id, out_die_id), engine.die_for(hero_id, in_die_id)
            self.warn(f"{leaving.name} has {leaving.size} faces and {arriving.name} only {arriving.size}: "
                      "this swap gives up the larger die. Press the same swap again to confirm.")
            return
        self.swap_confirm = None
        if self._guard(self._send, cmd.SWAP_DIE, hero_id=hero_id, out_die_id=out_die_id, in_die_id=in_die_id):
            self.upgrade_die = in_die_id if self.upgrade_hero == hero_id else self.upgrade_die
            self.info("Die swapped.")

    def toggle_formation(self, hero_id: str) -> None:
        engine = self.engine
        if engine is None:
            return
        hero = engine.combat.combatants[hero_id]
        row = ROW_BACK if hero.row == ROW_FRONT else ROW_FRONT
        if self._guard(self._send, cmd.SET_FORMATION, hero_id=hero_id, row=row):
            for index, member in enumerate(engine.state.party):
                if index < len(self.party):
                    self.party[index]["row"] = member["row"]
            self.info(f"{hero.name} moves to the {row} row.")

    def proceed_problem(self) -> str | None:
        engine = self.engine
        if engine is None:
            return "No run."
        if engine.state.phase == RunPhase.UPGRADE:
            return "A dice upgrade must be applied before Battle 2."
        return None

    def start_next_battle(self) -> None:
        problem = self.proceed_problem()
        if problem:
            self.warn(problem)
            return
        if self._guard(self._send, cmd.ADVANCE_PHASE):
            self.info("Battle 2 begins.")

    # ----------------------------------------------------------------------------------------
    # Outcome and logs
    # ----------------------------------------------------------------------------------------

    def _write_log(self) -> None:
        engine = self.engine
        if engine is None:
            return
        # The header carries the ordered commands, so the file alone is enough to replay the run
        # (battle-dice-replay verifies it).
        header = export_run(engine)
        header["command_count"] = len(engine.command_log)
        try:
            path = self._free_log_path(engine.state.run_id)
            write_jsonl(path, header, engine.events)
            self.log_path = path
        except OSError as error:  # a read-only folder must not break the outcome screen
            self.log_path = None
            self.log_error = str(error)

    def _free_log_path(self, run_id: str) -> Path:
        """A log file name that does not exist yet, so an earlier session's log is never overwritten."""
        path = self.log_dir / f"{run_id}.jsonl"
        suffix = 2
        while path.exists():
            path = self.log_dir / f"{run_id}-{suffix}.jsonl"
            suffix += 1
        return path

    def outcome_view(self) -> dict[str, Any]:
        engine = self.engine
        assert engine is not None
        return {
            "outcome": engine.state.outcome,
            "battle_reached": engine.state.encounter_index + 1,
            "battle_records": copy.deepcopy(engine.state.battle_records),
            "stats": summarize(engine.events),
            "seed": str(engine.state.seed),
            "log_path": str(self.log_path) if self.log_path else None,
            "log_error": self.log_error,
            "upgrades": copy.deepcopy(engine.state.upgrades),
            "tips": self.outcome_tips(),
        }

    def outcome_tips(self) -> list[str]:
        """Advice for the outcome screen when a whole mechanic went unused (playtest finding 2)."""
        engine = self.engine
        assert engine is not None
        stats = summarize(engine.events)
        tips = []
        if stats["rerolls_used"] == 0 and stats["hero_activations"] > 0:
            tips.append("Tip: no reroll was used. Reroll (R) rerolls every die you have not kept, twice per activation, for free.")
        offered = any(e.type == EventType.REACTION_STAGE_OPENED for e in engine.events)
        if stats["reactions_used"] == 0 and offered:
            tips.append("Tip: no reaction was used. Interpose, Grounding and Disrupt answer enemy actions before they land.")
        return tips

    # ----------------------------------------------------------------------------------------
    # Views
    # ----------------------------------------------------------------------------------------

    def view(self) -> dict[str, Any]:
        if self.engine is None:
            return {"started": False}
        return snapshot(self.engine)

    def log_lines(self, limit: int = 200) -> list[str]:
        if self.engine is None:
            return []
        return combat_log(self.engine, limit)

    def class_view(self, class_id: str) -> dict[str, Any]:
        cls = copy.deepcopy(self.content.class_def(class_id))
        return {
            "id": class_id,
            **cls,
            "reaction_def": copy.deepcopy(self.content.reactions[cls["reaction"]]),
            "dice": [die_view(self.content.die(d)) for d in cls["starting_dice"]],
            "bench": [die_view(self.content.die(d)) for d in cls["bench_dice"]],
        }
