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
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from battle_dice import settings as settings_module
from battle_dice.content.loader import Content, load_content
from battle_dice.core import commands as cmd
from battle_dice.core import planning
from battle_dice.core.build import BuildSource
from battle_dice.core.engine import Engine
from battle_dice.core.events import EventType, summarize, write_jsonl
from battle_dice.core.models import ROW_BACK, ROW_FRONT, CombatPhase, RunPhase
from battle_dice.core.progression import face_from_plain
from battle_dice.core.replay import export_run
from battle_dice.core.view import action_forecast, combat_log, die_view, face_view, hero_turn_view, snapshot
from battle_dice.features import CLASS_EVOLUTION
from battle_dice.settings import Settings


class Screen:
    MAIN_MENU = "main_menu"
    CONTROLS = "controls"
    PARTY_SETUP = "party_setup"
    BATTLE = "battle"
    UPGRADE = "upgrade"  # RECOVERY_AND_UPGRADE
    OUTCOME = "outcome"  # VICTORY_SUMMARY / DEFEAT_SUMMARY
    #: Class Evolution only: a hero's career, and the stop-or-fight-on decision after battle 2.
    CAREER = "career"
    CONTINUE = "continue"
    SETTINGS = "settings"
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


def default_save_dir(log_dir: str | Path | None = None) -> Path:
    """Where the save file goes (Class Evolution only) when no folder is given.

    * ``BATTLE_DICE_SAVE_DIR``, when it is set.
    * With the default log folder: ``saves`` beside it (``./saves`` from source; the per-user
      application data folder for a packaged build).
    * With a log folder the caller chose: ``saves`` **inside** it. Whoever redirects the logs, a
      test for one, gets the save in the same place and never outside it.
    """
    override = os.environ.get("BATTLE_DICE_SAVE_DIR")
    if override:
        return Path(override)
    if log_dir is not None:
        return Path(log_dir) / "saves"
    return default_log_dir().parent / "saves"


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
        features: Iterable[str] = (),
        save_dir: str | Path | None = None,
        settings: Settings | None = None,
        settings_path: str | Path | None = None,
    ):
        self.content = content if content is not None else load_content()
        #: The player's settings. Without a path a change lasts for this session only.
        self.settings: Settings = settings if settings is not None else Settings()
        self.settings_path: Path | None = Path(settings_path) if settings_path is not None else None
        self.settings_problems: list[str] = []
        self.settings_serial = 0  # bumped on every change, so the window can follow (animation, size)
        self.reset_confirm = False
        #: Gates switched on by a launch flag or the environment: the Settings screen cannot switch these off.
        self.forced_features: frozenset[str] = frozenset(features)
        #: Feature gates that are on (``battle_dice.features``). None by default.
        self.features: frozenset[str] = self.forced_features | ({CLASS_EVOLUTION} if self.settings.class_evolution else frozenset())
        self.vocations: BuildSource | None = None
        self._log_dir_given = log_dir
        self._save_dir_given = save_dir
        if CLASS_EVOLUTION in self.features:
            from battle_dice.content.vocations import (
                load_vocation_catalog,  # never imported while the gate is off
            )

            self.vocations = load_vocation_catalog(self.content)
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
        self.fixed_seed = fixed_seed if fixed_seed is not None else self.settings.seed
        self._seed_from_flag = fixed_seed is not None
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
        # Class Evolution: the save and the careers of its heroes. ``None`` unless the gate is on.
        self.progression: Any = None
        self.progression_error: str | None = None
        self.career_hero: str | None = None
        self.career_vocation: str | None = None
        self.career_return = Screen.PARTY_SETUP
        #: Offer the optional third battle after battle 2 (owner decision D-27). A setting of the demo.
        self.third_battle = self.settings.third_battle
        self._open_progression()

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
        self._sync_progression()
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
        elif phase == RunPhase.CONTINUE:
            if self.screen != Screen.CONTINUE:
                self.info("Battle 2 won. Stop here with a victory, or fight a third, harder battle.")
            self.screen = Screen.CONTINUE
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
        self._leave_run()
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
        if self.progression is not None:  # with saved heroes, adding a class recruits a hero of it
            self.recruit(class_id)
            return
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
            self.info(f"Removed {self.member_name(removed)}.")

    def toggle_party_row(self, index: int) -> None:
        if 0 <= index < len(self.party):
            member = self.party[index]
            member["row"] = ROW_BACK if member["row"] == ROW_FRONT else ROW_FRONT
            self.selected_slot = index
            self.info(f"{self.member_name(member)} moves to the {member['row']} row.")

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
        engine = Engine(self.content, self.vocations)
        self.runs_started += 1
        params: dict[str, Any] = {"seed": seed, "party": [dict(m) for m in self.party], "run_id": f"run-{seed}-{self.runs_started}"}
        link = self.progression
        if link is not None:  # saved heroes: their build snapshots, a run id from the save, and the optional third battle
            self._leave_run()
            params["party"] = [link.party_entry(m["hero_id"], m["row"]) for m in self.party]
            params["run_id"] = link.next_run_id(seed)
            if self.third_battle and link.extra_encounters():
                params["encounters"] = link.extra_encounters()
        result = engine.do(cmd.START_RUN, **params)
        if not result.accepted:
            self.warn(result.reason or "The run could not be started.")
            return
        if link is not None:
            link.run_started(engine)
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
        self._leave_run()
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
        result: dict[str, Any] = {"problem": None, "problem_code": None, "ordered": [], "mana_before": 0, "mana_after": 0}
        if engine is None or engine.combat.turn is None:
            return result
        hero = engine.combat.combatants[engine.combat.turn.hero_id]
        result["mana_before"] = result["mana_after"] = hero.mana
        if not self.draft:
            return result
        intents, problem, code = engine.check_plan(self.draft)
        result["problem"], result["problem_code"] = problem, code
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
        if class_id not in self.content.classes:
            return self._vocation_view(class_id)
        cls = copy.deepcopy(self.content.class_def(class_id))
        return {
            "id": class_id,
            **cls,
            "reaction_def": copy.deepcopy(self.content.reactions[cls["reaction"]]),
            "dice": [die_view(self.content.die(d)) for d in cls["starting_dice"]],
            "bench": [die_view(self.content.die(d)) for d in cls["bench_dice"]],
        }

    # ----------------------------------------------------------------------------------------
    # Class Evolution: saved heroes, their careers, and the third battle (only while the gate is on)
    # ----------------------------------------------------------------------------------------

    def close(self) -> None:
        """Release what the controller holds open: the save file, when Class Evolution is on."""
        if self.progression is not None:
            self.progression.close()
            self.progression = None

    def playable(self, vocation_id: str) -> bool:
        """True when the rules can run this vocation today (a starting class, or one whose engine work is done)."""
        if vocation_id in self.content.classes:
            return True
        return self.vocations is not None and vocation_id in getattr(self.vocations, "builds", {})

    def _vocation_view(self, vocation_id: str) -> dict[str, Any]:
        """``class_view`` for a vocation that is not a shipped class: from its build in the catalog."""
        assert self.vocations is not None
        raw = self.progression.catalog.vocations[vocation_id] if self.progression is not None else {}
        if not self.playable(vocation_id):  # listed in the catalog, but the rules cannot run it yet: only what the catalog says
            return {"id": vocation_id, "name": raw.get("name", vocation_id), "playable": False,
                    **{key: raw[key] for key in ("max_hp", "start_hp", "speed", "max_mana", "start_mana", "rerolls") if key in raw}}
        build = self.vocations.build(vocation_id)
        return {
            "id": vocation_id, "name": build.name, "playable": True, "max_hp": build.max_hp, "start_hp": build.start_hp, "speed": build.speed,
            "base_initiative": build.base_initiative, "max_mana": build.max_mana, "start_mana": build.start_mana,
            "max_corruption": build.max_corruption, "start_corruption": build.start_corruption, "rerolls": build.rerolls,
            "suggested_row": raw.get("suggested_row", ROW_FRONT), "scheduling": copy.deepcopy(build.scheduling),
            "passive": copy.deepcopy(build.passive), "reaction_def": copy.deepcopy(build.reaction),
            "dice": [die_view(build.dice.get(d) or self.content.die(d)) for d in build.starting_dice],
            "bench": [die_view(build.dice.get(d) or self.content.die(d)) for d in build.bench_dice],
        }

    def sprite_class(self, class_id: str) -> str:
        """The class whose picture stands for a vocation: itself, or the starting class it grew from."""
        if class_id in self.content.classes or self.vocations is None:
            return class_id
        try:
            return self.vocations.build(class_id).upgrade_family
        except Exception:  # noqa: BLE001 - a picture is never worth an error
            return class_id

    def member_name(self, member: dict[str, str]) -> str:
        if self.progression is not None and "hero_id" in member:
            hero = self.progression.state.heroes.get(member["hero_id"])
            if hero is not None:
                return str(hero.display_name or hero.hero_id)
        return str(self.class_view(member["class_id"])["name"])

    def _leave_run(self) -> None:
        """The player drops an unfinished run: the save records it as a defeat, so the roster is free again."""
        link = self.progression
        if link is not None:
            link.abandon_run()

    def _sync_progression(self) -> None:
        link, engine = self.progression, self.engine
        if link is None or engine is None:
            return
        awards = link.sync(engine)
        if awards:
            self.info("Mastery: " + "  ".join(self.award_line(a) for a in awards))

    @staticmethod
    def award_line(award: dict[str, Any]) -> str:
        """One hero's award for one battle, in words."""
        points = award["base_points"] + award["challenge_points"]
        if points:
            bonus = " with the bonus" if award["challenge_points"] else ""
            rank = f", now rank {award['rank_after']}" if award["rank_after"] != award["rank_before"] else ""
            learned = f", learned {', '.join(award['skills_learned'])}" if award["skills_learned"] else ""
            return f"{award['name']} +{points}{bonus}{rank}{learned}."
        reasons = {"UNDER_THREAT_CAP": "this battle is too easy for its rank", "ENCOUNTER_NOT_WON": "the battle was lost",
                   "ALREADY_MASTERED": "its vocation is mastered"}
        return f"{award['name']} +0 ({reasons.get(award['denial_reason'], 'nothing to earn')})."

    def awards_view(self, battle: int | None = None) -> list[str]:
        """The award lines of one battle of this run (the latest by default), for the screens."""
        link = self.progression
        if link is None or not link.last_awards:
            return []
        wanted = battle if battle is not None else link.last_awards[-1]["battle"]
        return [self.award_line(a) for a in link.last_awards if a["battle"] == wanted]

    # -- roster ----------------------------------------------------------------------------------

    def roster_view(self) -> list[dict[str, Any]]:
        if self.progression is None:
            return []
        in_party = {member.get("hero_id") for member in self.party}
        return [{**row, "in_party": row["hero_id"] in in_party} for row in self.progression.roster()]

    def recruit(self, starting_class: str) -> None:
        self._guard(self._recruit, starting_class)

    def _recruit(self, starting_class: str) -> None:
        link = self.progression
        assert link is not None
        before = set(link.state.heroes)
        result = link.recruit(starting_class)
        if not result.accepted:
            limit = (result.error_details or {}).get("roster_limit", "")
            self.warn({"ROSTER_FULL": f"The roster is full ({limit} heroes). Nobody can be recruited.",
                       "PHASE_LOCKED": "Heroes are recruited between runs, not during one."}.get(str(result.error_code), "That hero cannot be recruited."))
            return
        (hero_id,) = set(link.state.heroes) - before
        name = link.state.heroes[hero_id].display_name
        _, maximum = self.party_limits()
        if len(self.party) < maximum:
            self._add_to_party(hero_id)
            self.info(f"Recruited {name} and added it to the party.")
        else:
            self.info(f"Recruited {name}. The party is full, so it waits in the roster.")

    def _add_to_party(self, hero_id: str) -> None:
        hero = self.progression.state.heroes[hero_id]
        row = self.class_view(hero.active_vocation_id)["suggested_row"]
        self.party.append({"class_id": hero.active_vocation_id, "row": row, "hero_id": hero_id})
        self.selected_slot = len(self.party) - 1

    def add_saved_hero(self, hero_id: str) -> None:
        _, maximum = self.party_limits()
        if any(member.get("hero_id") == hero_id for member in self.party):
            self.warn("That hero is already in the party.")
        elif len(self.party) >= maximum:
            self.warn(f"A party can have at most {maximum} heroes.")
        else:
            self._add_to_party(hero_id)
            self.info(f"{self.member_name(self.party[-1])} joins the party in the {self.party[-1]['row']} row.")

    def _refresh_party(self) -> None:
        """Party entries follow their heroes: a hero that changed vocation fights as its new one."""
        if self.progression is None:
            return
        heroes = self.progression.state.heroes
        self.party = [{**m, "class_id": heroes[m["hero_id"]].active_vocation_id} for m in self.party if m.get("hero_id") in heroes]

    # -- career ----------------------------------------------------------------------------------

    def open_career(self, hero_id: str) -> None:
        self.career_hero, self.career_vocation = hero_id, None
        self.career_return = self.screen
        self.screen = Screen.CAREER
        self.info("A hero's career: what it has mastered, what it can become, and what is still hidden.")

    def close_career(self) -> None:
        self._refresh_party()
        self.screen = self.career_return
        self.career_hero = None

    def select_career_vocation(self, vocation_id: str) -> None:
        self.career_vocation = vocation_id

    def career_view(self) -> dict[str, Any]:
        """One hero's career tree with, for each listed vocation, what the hero may do with it and why not."""
        link, hero_id = self.progression, self.career_hero
        assert link is not None and hero_id is not None
        hero = link.state.heroes[hero_id]
        in_run = link.state.run is not None and link.state.run.phase not in ("victory", "defeat")
        rows = []
        for entry in link.tree(hero_id)["career_tree"]["entries"]:
            if entry["kind"] != "vocation":
                rows.append({**entry, "status": entry.get("clue") or "Not discovered yet.", "can_claim": False, "can_activate": False, "needs": ""})
                continue
            vocation_id = entry["vocation_id"]
            playable = self.playable(vocation_id)
            needs = "" if entry["unlocked"] else self._requirement_text(hero_id, vocation_id)
            if not playable:  # the catalog lists it, the rules cannot run it yet: it can be read about, not taken
                needs = f"Not in this version yet. {needs}".strip()
            if entry["active"]:
                status = "Active"
            elif entry["unlocked"]:
                status = "Unlocked"
            elif not playable:
                status = "Coming later"
            else:
                status = "Ready to claim" if not needs else "Locked"
            if entry["unlocked"]:
                mastery = hero.mastery[vocation_id]
                top = link.catalog.thresholds(vocation_id)
                progress = "mastered" if entry["mastered"] else f"rank {mastery.rank}, {mastery.points}/{top[mastery.rank]} to the next"
                status = f"{status}: {progress}"
            rows.append({**entry, "status": status, "needs": needs, "playable": playable,
                         "can_claim": playable and not entry["unlocked"] and not needs and not in_run,
                         "can_activate": playable and entry["unlocked"] and not entry["active"] and not in_run})
        selected = self.career_vocation or hero.active_vocation_id
        chosen = next(row for row in rows if row.get("vocation_id") == selected)
        return {"hero_id": hero_id, "name": hero.display_name or hero_id, "active_vocation_id": hero.active_vocation_id,
                "rows": rows, "selected": selected, "selected_needs": chosen["needs"], "in_run": in_run}

    def _requirement_text(self, hero_id: str, vocation_id: str) -> str:
        """What the hero still lacks for the cheapest route to a vocation; empty when it can be claimed."""
        link = self.progression
        hero = link.state.heroes[hero_id]
        best: list[str] | None = None
        for route in link.career.service.routes(hero, vocation_id):
            lacking = []
            for unmet in route.unmet:
                if unmet["op"] == "MASTERY_AT_LEAST":
                    lacking.append(f"master {link.catalog.name(unmet['vocation_id'])} (now rank {unmet['current_rank']})")
                elif unmet["op"] == "MASTERED_COUNT_AT_LEAST":
                    lacking.append(f"master {unmet['minimum']} {unmet['group']} vocations (now {unmet['current_count']})")
                else:
                    lacking.append("finish a quest")
            for item_id, quantity, _consume in route.items:
                held = link.state.profile.items.get(item_id, 0)
                if held < quantity:
                    lacking.append(f"hold {quantity} {item_id.replace('_', ' ')} (now {held})")
            if best is None or len(lacking) < len(best):
                best = lacking
        return "Needs: " + "; ".join(best) + "." if best else ""

    def claim_vocation(self, vocation_id: str) -> None:
        self._guard(self._career_command, "claim", vocation_id)

    def change_vocation(self, vocation_id: str) -> None:
        self._guard(self._career_command, "change", vocation_id)

    def _career_command(self, what: str, vocation_id: str) -> None:
        link, hero_id = self.progression, self.career_hero
        assert link is not None and hero_id is not None
        result = link.claim(hero_id, vocation_id) if what == "claim" else link.change(hero_id, vocation_id)
        name = link.catalog.name(vocation_id)
        hero_name = link.state.heroes[hero_id].display_name
        if not result.accepted:
            reasons = {"PHASE_LOCKED": "That cannot be done during a run.", "PREREQUISITE_UNMET": f"{hero_name} does not meet what {name} needs yet.",
                       "NOT_DISCOVERED": "That vocation has not been discovered.", "ITEM_INSUFFICIENT": "An item it needs is missing."}
            self.warn(reasons.get(str(result.error_code), "That is not allowed right now."))
            return
        self._refresh_party()
        self.career_vocation = vocation_id
        self.info(f"{hero_name} has unlocked {name}." if what == "claim" else f"{hero_name} is now a {name}.")

    # -- the third battle ------------------------------------------------------------------------

    def continue_view(self) -> dict[str, Any]:
        engine = self.engine
        assert engine is not None
        encounter_id = engine.offered_encounter()
        threat = None
        if self.progression is not None and encounter_id is not None:
            threat = next((e["threat_rating"] for e in self.progression.catalog.raw["encounters"] if e["id"] == encounter_id), None)
        heroes = [{"id": h.id, "name": h.name, "hp": h.hp, "max_hp": h.max_hp, "mana": h.mana, "max_mana": h.max_mana, "row": h.row}
                  for h in engine.combat.side("hero")]
        return {"encounter_id": encounter_id, "threat_rating": threat, "heroes": heroes, "awards": self.awards_view(),
                "battle": engine.state.encounter_index + 1}

    def fight_on(self) -> None:
        if self.engine is not None and self._guard(self._send, cmd.CONTINUE_RUN):
            self.info("Battle 3 begins. Losing it loses the run.")

    def end_run_with_victory(self) -> None:
        if self.engine is not None:
            self._guard(self._send, cmd.END_RUN)

    # ----------------------------------------------------------------------------------------
    # Settings (the demo's configuration)
    # ----------------------------------------------------------------------------------------

    def save_folder(self) -> Path:
        """Where the save file is, or would be: a launch flag, then the settings file, then the usual place."""
        if self._save_dir_given is not None:
            return Path(self._save_dir_given)
        if self.settings.save_dir:
            return Path(self.settings.save_dir)
        return default_save_dir(self._log_dir_given)

    def _open_progression(self) -> None:
        """Open the save when Class Evolution is on. A save that cannot be opened must not stop the game."""
        self.progression, self.progression_error = None, None
        if CLASS_EVOLUTION not in self.features:
            return
        from battle_dice.app.progression import (
            Progression,  # never imported while the gate is off
        )

        try:
            self.progression = Progression(self.save_folder(), self.content, mastery_pace=self.settings.mastery_pace,
                                           roster_limit=self.settings.roster_limit, preset=self.settings.demo_preset)
        except Exception as error:  # noqa: BLE001
            self.progression_error = f"The save could not be opened, so heroes are not saved this session: {error}"

    def open_settings(self) -> None:
        self.screen = Screen.SETTINGS
        self.reset_confirm = False
        self.info("Settings are saved as you change them." if self.settings_path else "Settings last for this session (no settings file is in use).")

    def close_settings(self) -> None:
        self.reset_confirm = False
        self.screen = Screen.MAIN_MENU

    def settings_view(self) -> list[dict[str, Any]]:
        """Every setting as the Settings screen shows it: its value in words, what it does, and whether it can be changed here."""
        current = self.settings
        evolution = CLASS_EVOLUTION in self.features
        forced = CLASS_EVOLUTION in self.forced_features
        needs = None if evolution else "Switch Class Evolution on first."
        paces = {"normal": "Normal", "fast": "Fast (about half the points)", "very_fast": "Very fast (a rank per win at most)"}
        presets = {"fresh": "Fresh: no heroes", "squire_near_mastery": "A Squire one win from mastery",
                   "guardian_unlocked": "A Guardian at rank 1", "guardian_mastered": "A mastered Guardian"}
        rows = [
            {"key": "class_evolution", "label": "Class Evolution", "value": ("On (launch flag)" if forced else "On") if evolution else "Off",
             "help": "Saved heroes, mastery, vocations and the third battle. Off: the game as shipped, and no save file.",
             "reason": "Switched on by a launch flag for this session." if forced else None},
            {"key": "third_battle", "label": "Third battle", "value": "Offered" if current.third_battle else "Not offered",
             "help": "After Battle 2, offer a third, harder battle. A Guardian needs it for its last rank.", "reason": needs},
            {"key": "mastery_pace", "label": "Mastery pace", "value": paces[current.mastery_pace],
             "help": "How many points a rank needs. A faster pace re-ranks your heroes from the points they have.", "reason": needs},
            {"key": "roster_limit", "label": "Roster size", "value": f"{current.roster_limit} heroes",
             "help": "How many heroes a profile may hold.", "reason": needs},
            {"key": "demo_preset", "label": "New profile starts as", "value": presets[current.demo_preset],
             "help": "Used when a profile is made or reset. Every start but the first comes with a Scout and an Apprentice.", "reason": needs},
            {"key": "seed", "label": "Dice seed", "value": "A new one each run" if self.fixed_seed is None else f"Fixed: {self.fixed_seed}",
             "help": "A fixed seed gives the same dice every run with the same party and choices.",
             "reason": "Set by a launch flag for this session." if self._seed_from_flag else None},
            {"key": "animation", "label": "Animation", "value": "On" if current.animation else "Off (reduced motion)",
             "help": "Movement and flashes in battle. M also toggles it during a battle.", "reason": None},
            {"key": "window_size", "label": "Window size", "value": current.window_size.replace("x", " x "),
             "help": "The window can also be resized by dragging its edge.", "reason": None},
        ]
        return rows

    def change_setting(self, key: str) -> None:
        self._guard(self._change_setting, key)

    def _change_setting(self, key: str) -> None:
        """Move one setting to its next value, save the file, and make the change take effect now."""
        current = self.settings
        self.reset_confirm = False

        def following(options: tuple[Any, ...], value: Any) -> Any:
            return options[(options.index(value) + 1) % len(options)] if value in options else options[0]

        if key in ("class_evolution", "third_battle", "animation"):
            setattr(current, key, not getattr(current, key))
        elif key == "mastery_pace":
            current.mastery_pace = following(tuple(settings_module.PACES), current.mastery_pace)
        elif key == "roster_limit":
            current.roster_limit = following(settings_module.ROSTER_LIMITS, current.roster_limit)
        elif key == "demo_preset":
            current.demo_preset = following(settings_module.PRESETS, current.demo_preset)
        elif key == "window_size":
            current.window_size = following(settings_module.WINDOW_SIZES, current.window_size)
        elif key == "seed":
            current.seed = None if current.seed is not None else int(self._seed_source())
            self.fixed_seed = current.seed
        else:
            raise ValueError(f"Unknown setting '{key}'.")
        self.settings_serial += 1
        if self.settings_path is not None:
            settings_module.save(current, self.settings_path)
        self.third_battle = current.third_battle
        if key in ("class_evolution", "mastery_pace", "roster_limit"):
            self._reopen_progression()
        row = next(r for r in self.settings_view() if r["key"] == key)
        self.info(f"{row['label']}: {row['value']}.")
        if self.progression_error:
            self.warn(self.progression_error)

    def _reopen_progression(self) -> None:
        """Class Evolution was switched, or a setting the save depends on changed: close the save and open it again."""
        self.close()
        self.party, self.engine = [], None
        self.features = self.forced_features | ({CLASS_EVOLUTION} if self.settings.class_evolution else frozenset())
        if CLASS_EVOLUTION in self.features and self.vocations is None:
            from battle_dice.content.vocations import load_vocation_catalog

            self.vocations = load_vocation_catalog(self.content)
        elif CLASS_EVOLUTION not in self.features:
            self.vocations = None
        self._open_progression()

    def reset_profile(self) -> None:
        self._guard(self._reset_profile)

    def _reset_profile(self) -> None:
        """Delete the save and start a new profile from the chosen start. Asked twice: it cannot be undone."""
        if CLASS_EVOLUTION not in self.features:
            self.warn("There is no profile to reset while Class Evolution is off.")
            return
        if not self.reset_confirm:
            self.reset_confirm = True
            self.warn("This deletes every saved hero. Press Reset again to do it, or change anything else to cancel.")
            return
        self.reset_confirm = False
        self.close()
        save_file = self.save_folder() / "profile.sqlite"
        for leftover in (save_file, *save_file.parent.glob(save_file.name + "-*")):
            if leftover.is_file():
                leftover.unlink()
        self.party, self.engine = [], None
        self._open_progression()
        if self.progression is not None:
            self.info(f"A new profile was made ({len(self.progression.state.heroes)} heroes).")
        else:
            self.warn(self.progression_error or "The new profile could not be made.")
