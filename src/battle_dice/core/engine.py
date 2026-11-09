"""The authoritative rules engine: one mutation path, transactional and idempotent (section 14).

* Every change to the authoritative state goes through :meth:`Engine.submit`.
* A rejected command leaves state, RNG stream positions and the event sequence unchanged.
* A command whose ``command_id`` was already accepted is acknowledged without a second effect.
* Automatic combat transitions advance one step per ``AdvancePhase`` command so that a UI can pace
  them and a test can run to the next required player input.

This module has no pygame dependency.
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any

from battle_dice import RNG_ALGORITHM, RULES_VERSION, rng
from battle_dice.content.loader import Content, load_content
from battle_dice.core import commands as cmd
from battle_dice.core import effects, enemy_ai, planning, progression, reactions, terminal, timeline
from battle_dice.core.commands import Command, CommandRejected, CommandResult
from battle_dice.core.events import EventType
from battle_dice.core.models import (
    REACTION_STAGES,
    ROWS,
    SIDE_HERO,
    ActionIntent,
    Combatant,
    CombatEvent,
    CombatPhase,
    CombatState,
    DieDefinition,
    FaceDefinition,
    HeroTurn,
    RunPhase,
    RunState,
    to_plain,
)


class Engine:
    def __init__(self, content: Content | None = None):
        self.content: Content = content if content is not None else load_content()
        self._state: RunState | None = None
        self.events: list[CombatEvent] = []
        self.command_log: list[Command] = []
        self._accepted: set[str] = set()
        self._auto_command = 0

    # ----------------------------------------------------------------------------------------
    # Accessors
    # ----------------------------------------------------------------------------------------

    @property
    def started(self) -> bool:
        return self._state is not None

    @property
    def state(self) -> RunState:
        if self._state is None:
            raise RuntimeError("No run has been started.")
        return self._state

    @property
    def combat(self) -> CombatState:
        combat = self.state.combat
        if combat is None:  # pragma: no cover - a started run always has a combat state
            raise RuntimeError("No combat state.")
        return combat

    @property
    def revision(self) -> int:
        return self._state.revision if self._state is not None else 0

    def die_for(self, hero_id: str, die_id: str) -> DieDefinition:
        """The hero's die definition, honouring this run's versioned upgrade override."""
        override = self.state.die_overrides.get(hero_id, {}).get(die_id)
        return override if override is not None else self.content.die(die_id)

    def enemy_action(self, enemy: Combatant, action_id: str) -> FaceDefinition:
        base = self.content.enemy_action(enemy.archetype_id, action_id)
        overrides = enemy.action_overrides.get(action_id)
        if not overrides:
            return base
        return dataclasses.replace(
            base, power=overrides.get("power", base.power), weight=overrides.get("weight", base.weight)
        )

    def intent_face(self, intent: ActionIntent) -> FaceDefinition:
        actor = self.combat.combatants[intent.actor_id]
        if intent.source_die_id is not None:
            assert intent.face_index is not None
            return self.die_for(actor.id, intent.source_die_id).faces[intent.face_index]
        assert intent.ability_id is not None
        return self.enemy_action(actor, intent.ability_id)

    def needs_input(self) -> bool:
        """True when the engine is waiting for a player decision rather than ``AdvancePhase``."""
        if self._state is None:
            return True
        if self.state.phase == RunPhase.BATTLE:
            return self.combat.phase in CombatPhase.INPUT_PHASES
        return True

    def finished(self) -> bool:
        return self._state is not None and self.state.phase in (RunPhase.VICTORY, RunPhase.DEFEAT)

    # ----------------------------------------------------------------------------------------
    # Command handling
    # ----------------------------------------------------------------------------------------

    def do(self, command_type: str, **params: Any) -> CommandResult:
        """Convenience wrapper: submit a command with an auto-generated id at the current revision."""
        self._auto_command += 1
        return self.submit(Command(command_type, f"auto-{self._auto_command:06d}", self.revision, params))

    def submit(self, command: Command) -> CommandResult:
        if command.command_id in self._accepted:
            return CommandResult(True, self.revision, duplicate=True)
        problem = cmd.validate_command(command)
        if problem:
            return CommandResult(False, self.revision, reason=problem)
        if command.state_revision != self.revision:
            return CommandResult(
                False,
                self.revision,
                reason=f"Stale command: expected revision {command.state_revision}, current is {self.revision}.",
            )
        if self._state is None and command.type != cmd.START_RUN:
            return CommandResult(False, self.revision, reason="No run has been started; send StartRun first.")
        backup = copy.deepcopy(self._state)
        event_count = len(self.events)
        handler = getattr(self, _HANDLERS[command.type])
        try:
            handler(**command.params)
        except CommandRejected as rejection:
            self._state = backup
            del self.events[event_count:]
            return CommandResult(False, self.revision, reason=str(rejection))
        except Exception:
            self._state = backup
            del self.events[event_count:]
            raise
        self.state.revision += 1
        self._accepted.add(command.command_id)
        self.command_log.append(command)
        return CommandResult(True, self.revision, events=self.events[event_count:])

    def force_draws(self, stream: str, values: list[int]) -> None:
        """Fixture hook: queue forced bounded results for a stream (e.g. specific die faces).

        Forced values replace PCG draws one for one and do not advance the stream. Production
        code never calls this; it exists so fixtures can force a known roll or catalog order.
        """
        if stream not in rng.STREAM_NAMES:
            raise ValueError(f"unknown RNG stream '{stream}'")
        self.state.forced_draws.setdefault(stream, []).extend(int(v) for v in values)

    # ----------------------------------------------------------------------------------------
    # Services used by the rules modules
    # ----------------------------------------------------------------------------------------

    def draw(self, stream: str, n: int) -> tuple[int, dict[str, Any]]:
        """Draw a uniform integer in ``[0, n)`` from a named stream and describe the draw for the log."""
        state = self.state
        forced = state.forced_draws.get(stream)
        if forced:
            value = forced.pop(0)
            if not 0 <= value < n:
                raise CommandRejected(f"Forced draw {value} is outside [0, {n}) for stream '{stream}'.")
            return value, {"stream": f"{stream}:forced", "index": state.rng[stream].draws}
        value = rng.bounded(state.rng[stream], n)
        return value, {"stream": stream, "index": state.rng[stream].draws}

    def snap(self, ids: list[str] | None) -> dict[str, Any]:
        """Compact before/after view of the given combatants for an event record."""
        result: dict[str, Any] = {}
        for cid in ids or []:
            c = self.combat.combatants.get(cid)
            if c is None:
                continue
            result[cid] = {
                "hp": c.hp,
                "shields": c.shields,
                "mana": c.mana,
                "corruption": c.corruption,
                "gauge": c.gauge,
                "state": c.state,
                "statuses": [[s.kind, s.stacks, s.remaining_target_activations] for s in c.status_instances],
            }
        return result

    def emit(
        self,
        event_type: str,
        actor_id: str | None = None,
        intent_id: str | None = None,
        delta: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        affected: list[str] | None = None,
        rng_stream: str | None = None,
        rng_draw_index: int | None = None,
    ) -> CombatEvent:
        combat = self.combat
        combat.event_seq += 1
        event = CombatEvent(
            seq=combat.event_seq,
            tick=combat.timeline_tick,
            actor_id=actor_id,
            type=event_type,
            intent_id=intent_id,
            before=before or {},
            delta=to_plain(delta or {}),
            after=self.snap(affected),
            rng_stream=rng_stream,
            rng_draw_index=rng_draw_index,
        )
        self.events.append(event)
        return event

    def check_terminal(self) -> bool:
        """Evaluate terminal states after an atomic effect. Returns True when the battle is over."""
        combat = self.combat
        if combat.outcome is not None:
            return True
        outcome = terminal.evaluate(combat)
        if outcome is None:
            return False
        self._finish_battle(outcome)
        return True

    # ----------------------------------------------------------------------------------------
    # Run lifecycle
    # ----------------------------------------------------------------------------------------

    def _start_run(self, seed: int, party: list[dict[str, str]], run_id: str | None = None) -> None:
        if self._state is not None:
            raise CommandRejected("A run is already in progress; start a new run with a new engine.")
        try:
            rng.validate_seed(seed)
        except ValueError as error:
            raise CommandRejected(str(error)) from error
        limits = self.content.balance["party"]
        if not limits["min_size"] <= len(party) <= limits["max_size"]:
            raise CommandRejected(
                f"Party size must be between {limits['min_size']} and {limits['max_size']} (got {len(party)})."
            )
        for member in party:
            if member["class_id"] not in self.content.classes:
                raise CommandRejected(f"Unknown class '{member['class_id']}'.")
            if member["row"] not in ROWS:
                raise CommandRejected(f"Row must be 'front' or 'back' (got '{member['row']}').")

        state = RunState(
            run_id=run_id or f"run-{seed}",
            seed=seed,
            rules_version=RULES_VERSION,
            content_version=self.content.content_version,
            content_hash=self.content.content_hash,
            rng_algorithm=RNG_ALGORITHM,
            rng=rng.derive_streams(seed),
        )
        heroes = []
        for slot, member in enumerate(party, start=1):
            hero_id = f"h{slot:02d}"
            state.party.append({"id": hero_id, "class_id": member["class_id"], "row": member["row"]})
            state.inventory[hero_id] = list(self.content.class_def(member["class_id"])["bench_dice"])
            heroes.append(progression.make_hero(self.content, hero_id, member["class_id"], member["row"]))
        self._state = state
        state.combat = self._build_combat(1, heroes, event_seq=0)
        self.emit(
            EventType.RUN_STARTED,
            delta={
                "run_id": state.run_id,
                "seed": str(seed),
                "rules_version": state.rules_version,
                "content_version": state.content_version,
                "content_hash": state.content_hash,
                "rng_algorithm": state.rng_algorithm,
                "rng_streams": list(rng.STREAM_NAMES),
                "party": state.party,
            },
        )
        self._emit_battle_started()

    def _build_combat(self, battle: int, heroes: list[Combatant], event_seq: int) -> CombatState:
        combat = CombatState(encounter_id=f"p{len(heroes)}_b{battle}", event_seq=event_seq)
        for hero in heroes:
            combat.combatants[hero.id] = hero
        for enemy in progression.make_enemies(self.content, len(heroes), battle):
            combat.combatants[enemy.id] = enemy
        return combat

    def _emit_battle_started(self) -> None:
        combat = self.combat
        self.emit(
            EventType.BATTLE_STARTED,
            delta={
                "battle": self.state.encounter_index + 1,
                "encounter_id": combat.encounter_id,
                "roster": [
                    {"id": c.id, "name": c.name, "side": c.side, "archetype": c.archetype_id, "row": c.row, "hp": c.hp,
                     "max_hp": c.max_hp, "speed": c.speed, "action_overrides": c.action_overrides}
                    for c in combat.sorted_combatants()
                ],
            },
        )

    def _finish_battle(self, outcome: str) -> None:
        state = self.state
        combat = self.combat
        combat.outcome = outcome
        combat.phase = CombatPhase.VICTORY if outcome == terminal.OUTCOME_VICTORY else CombatPhase.DEFEAT
        combat.turn = None
        combat.committed_intent = None
        combat.reaction_stage = None
        combat.active_combatant_id = None
        battle = state.encounter_index + 1
        state.battle_records.append(
            {"battle": battle, "outcome": outcome, "ticks": combat.timeline_tick, "activations": combat.activation_count}
        )
        if outcome == terminal.OUTCOME_DEFEAT:
            self.emit(EventType.BATTLE_LOST, delta={"battle": battle})
            state.phase = RunPhase.DEFEAT
            state.outcome = terminal.OUTCOME_DEFEAT
            self.emit(EventType.RUN_DEFEAT, delta={"battle": battle})
            return
        self.emit(EventType.BATTLE_WON, delta={"battle": battle})
        if battle >= self.content.documents["encounters"]["battle_count"]:
            state.phase = RunPhase.VICTORY
            state.outcome = terminal.OUTCOME_VICTORY
            self.emit(EventType.RUN_VICTORY, delta={"battle": battle})
            return
        state.phase = RunPhase.UPGRADE
        progression.apply_recovery(self)
        progression.generate_offers(self)

    def _start_next_battle(self) -> None:
        state = self.state
        previous = self.combat
        heroes = previous.side(SIDE_HERO)
        state.encounter_index += 1
        state.upgrade_offers = {}
        state.combat = self._build_combat(state.encounter_index + 1, heroes, event_seq=previous.event_seq)
        state.phase = RunPhase.BATTLE
        self._emit_battle_started()

    # ----------------------------------------------------------------------------------------
    # Between-battle commands
    # ----------------------------------------------------------------------------------------

    def _set_formation(self, hero_id: str, row: str) -> None:
        state = self.state
        if state.phase not in (RunPhase.UPGRADE, RunPhase.EQUIPMENT):
            raise CommandRejected("Formation can only be changed between battles, not during combat.")
        if row not in ROWS:
            raise CommandRejected(f"Row must be 'front' or 'back' (got '{row}').")
        hero = self.combat.combatants.get(hero_id)
        if hero is None or not hero.is_hero:
            raise CommandRejected(f"Unknown hero '{hero_id}'.")
        previous = hero.row
        hero.row = row
        for member in state.party:
            if member["id"] == hero_id:
                member["row"] = row
        self.emit(EventType.FORMATION_CHANGED, actor_id=hero_id, delta={"from": previous, "to": row})

    def _choose_upgrade(self, hero_id: str, die_id: str, offer_id: str) -> None:
        state = self.state
        if state.phase != RunPhase.UPGRADE:
            raise CommandRejected("The mandatory upgrade can only be chosen once, after winning Battle 1.")
        problem = progression.apply_upgrade(self, hero_id, die_id, offer_id)
        if problem:
            raise CommandRejected(problem)
        state.phase = RunPhase.EQUIPMENT

    def _swap_die(self, hero_id: str, out_die_id: str, in_die_id: str) -> None:
        if self.state.phase != RunPhase.EQUIPMENT:
            raise CommandRejected("Dice can only be swapped between battles, after the mandatory upgrade.")
        problem = progression.apply_swap(self, hero_id, out_die_id, in_die_id)
        if problem:
            raise CommandRejected(problem)

    # ----------------------------------------------------------------------------------------
    # Hero activation commands
    # ----------------------------------------------------------------------------------------

    def _require_combat_phase(self, *phases: str) -> CombatState:
        if self.state.phase != RunPhase.BATTLE:
            raise CommandRejected("No battle is in progress.")
        combat = self.combat
        if combat.phase not in phases:
            raise CommandRejected(f"Not allowed during the '{combat.phase}' phase.")
        return combat

    def _active_hero(self) -> tuple[Combatant, HeroTurn]:
        combat = self.combat
        assert combat.active_combatant_id is not None and combat.turn is not None
        return combat.combatants[combat.active_combatant_id], combat.turn

    def _roll_die(self, hero: Combatant, turn: HeroTurn, die_id: str, event_type: str, extra: dict[str, Any]) -> None:
        die = self.die_for(hero.id, die_id)
        previous = turn.rolled.get(die_id)
        value, draw = self.draw("dice", die.size)
        turn.rolled[die_id] = value
        face = die.faces[value]
        self.emit(
            event_type,
            actor_id=hero.id,
            delta={"die_id": die_id, "die_size": die.size, "previous_face": None if previous is None else previous + 1,
                   "face": value + 1, "face_name": face.name, "category": face.category, **extra},
            rng_stream=draw["stream"],
            rng_draw_index=draw["index"],
        )

    def _roll_dice(self) -> None:
        self._require_combat_phase(CombatPhase.HERO_ROLL)
        hero, turn = self._active_hero()
        for die_id in sorted(hero.equipped_dice_ids):
            self._roll_die(hero, turn, die_id, EventType.DICE_ROLLED, {})
        self.combat.phase = CombatPhase.KEEP_REROLL

    def _set_kept_dice(self, die_ids: list[str]) -> None:
        self._require_combat_phase(CombatPhase.KEEP_REROLL)
        hero, turn = self._active_hero()
        unknown = [d for d in die_ids if d not in turn.rolled]
        if unknown:
            raise CommandRejected(f"Cannot keep dice that were not rolled: {', '.join(unknown)}.")
        if len(set(die_ids)) != len(die_ids):
            raise CommandRejected("Each die can be kept only once.")
        turn.kept = sorted(die_ids)
        self.emit(EventType.DICE_KEPT, actor_id=hero.id, delta={"kept": turn.kept})

    def _reroll_unkept(self) -> None:
        self._require_combat_phase(CombatPhase.KEEP_REROLL)
        hero, turn = self._active_hero()
        if turn.rerolls_remaining <= 0:
            raise CommandRejected("No rerolls remaining this activation.")
        unkept = [d for d in sorted(turn.rolled) if d not in turn.kept]
        if not unkept:
            raise CommandRejected("Every die is kept, so there is nothing to reroll. No reroll was spent.")
        turn.rerolls_remaining -= 1
        turn.rerolls_used += 1
        for position, die_id in enumerate(unkept):
            self._roll_die(
                hero, turn, die_id, EventType.DICE_REROLLED,
                {"rerolls_remaining": turn.rerolls_remaining, "first_of_reroll": position == 0},
            )

    def _set_action_plan(self, actions: list[dict[str, Any]]) -> None:
        combat = self._require_combat_phase(CombatPhase.KEEP_REROLL, CombatPhase.ACTION_PLAN)
        hero, turn = self._active_hero()
        try:
            turn.plan = planning.build_plan(self, hero, turn, actions)
        except planning.PlanError as error:
            raise CommandRejected(str(error)) from error
        combat.phase = CombatPhase.ACTION_PLAN
        self.emit(
            EventType.PLAN_SET,
            actor_id=hero.id,
            delta={"actions": [{"die_id": a.source_die_id, "name": a.name, "target_ids": a.committed_target_ids} for a in turn.plan]},
        )

    def _commit_action_plan(self) -> None:
        combat = self._require_combat_phase(CombatPhase.ACTION_PLAN)
        hero, turn = self._active_hero()
        # Rebuild from the stored selections so legality is checked against the current state.
        selections = [
            {"die_id": a.source_die_id, "target_ids": list(a.committed_target_ids)}
            for a in sorted(turn.plan, key=lambda a: a.plan_order)
        ]
        try:
            turn.plan = planning.build_plan(self, hero, turn, selections)
        except planning.PlanError as error:
            raise CommandRejected(str(error)) from error
        combat.next_intent_seq += len(turn.plan)
        turn.committed = True
        turn.queue_index = 0
        used = {a.source_die_id for a in turn.plan}
        combat.phase = CombatPhase.LOCK_PLAN
        self.emit(
            EventType.PLAN_COMMITTED,
            actor_id=hero.id,
            delta={
                "actions": [
                    {"intent_id": a.id, "die_id": a.source_die_id, "effect_id": a.effect_id, "name": a.name,
                     "category": a.category, "action_speed": a.action_speed, "costs": a.costs,
                     "committed_target_ids": a.committed_target_ids, "plan_order": a.plan_order}
                    for a in turn.plan
                ],
                "discarded_dice": [d for d in sorted(turn.rolled) if d not in used],
                "rerolls_unused": turn.rerolls_remaining,
            },
        )
        if not turn.plan:
            self.emit(EventType.HERO_PASSED, actor_id=hero.id, delta={"reason": "no action committed"})

    # ----------------------------------------------------------------------------------------
    # Reaction commands
    # ----------------------------------------------------------------------------------------

    _WINDOWS = (CombatPhase.GUARD_WINDOW, CombatPhase.RESOURCE_WINDOW, CombatPhase.INTERRUPT_WINDOW)

    def _use_reaction(self, hero_id: str, target_id: str | None = None) -> None:
        combat = self._require_combat_phase(*self._WINDOWS)
        problem = reactions.use_reaction(self, hero_id, target_id)
        if problem:
            raise CommandRejected(problem)
        intent = combat.committed_intent
        assert intent is not None and combat.reaction_stage is not None
        if intent.cancelled:
            combat.reaction_stage = None
            combat.phase = CombatPhase.ENEMY_RESOLVE
        elif not reactions.eligible_options(self, combat.reaction_stage):
            self._enter_stage(combat.stage_index + 1)

    def _skip_reaction_stage(self) -> None:
        combat = self._require_combat_phase(*self._WINDOWS)
        assert combat.committed_intent is not None
        self.emit(
            EventType.REACTION_STAGE_SKIPPED,
            intent_id=combat.committed_intent.id,
            delta={"stage": combat.reaction_stage, "reason": "skipped by player"},
        )
        self._enter_stage(combat.stage_index + 1)

    def _enter_stage(self, index: int) -> None:
        """Open the next stage that has an eligible reaction; stages never reopen."""
        combat = self.combat
        intent = combat.committed_intent
        assert intent is not None
        while index < len(REACTION_STAGES):
            stage = REACTION_STAGES[index]
            eligible = reactions.eligible_options(self, stage)
            if eligible:
                combat.stage_index = index
                combat.reaction_stage = stage
                combat.phase = CombatPhase.WINDOW_BY_STAGE[stage]
                self.emit(
                    EventType.REACTION_STAGE_OPENED,
                    intent_id=intent.id,
                    delta={"stage": stage, "eligible_hero_ids": [o["hero_id"] for o in eligible]},
                )
                return
            self.emit(
                EventType.REACTION_STAGE_SKIPPED,
                intent_id=intent.id,
                delta={"stage": stage, "reason": "no eligible reaction"},
            )
            index += 1
        combat.stage_index = len(REACTION_STAGES)
        combat.reaction_stage = None
        combat.phase = CombatPhase.ENEMY_RESOLVE

    # ----------------------------------------------------------------------------------------
    # Automatic transitions (AdvancePhase)
    # ----------------------------------------------------------------------------------------

    def _advance_phase(self) -> None:
        state = self.state
        if state.phase == RunPhase.EQUIPMENT:
            self._start_next_battle()
            return
        if state.phase == RunPhase.UPGRADE:
            raise CommandRejected("A dice upgrade must be chosen before Battle 2 can start.")
        if state.phase != RunPhase.BATTLE:
            raise CommandRejected("The run is over.")
        combat = self.combat
        if combat.phase in CombatPhase.INPUT_PHASES:
            raise CommandRejected(f"Waiting for player input in the '{combat.phase}' phase.")
        step = _STEPS.get(combat.phase)
        if step is None:  # pragma: no cover - terminal combat phases imply a non-battle run phase
            raise CommandRejected("The battle is over.")
        getattr(self, step)()

    def _step_advance_timeline(self) -> None:
        combat = self.combat
        balance = self.content.balance
        ticks = timeline.advance_until_ready(combat, balance)
        if ticks:
            self.emit(
                EventType.TIMELINE_ADVANCED,
                delta={"ticks": ticks, "gauges": {c.id: c.gauge for c in combat.sorted_combatants() if c.standing}},
            )
        actor = timeline.begin_activation(combat, balance)
        if actor is None:  # pragma: no cover - guarded by terminal evaluation
            raise CommandRejected("No combatant is able to act.")
        combat.phase = CombatPhase.ACTOR_START
        self.emit(
            EventType.ACTIVATION_STARTED,
            actor_id=actor.id,
            delta={"side": actor.side, "name": actor.name, "activation": combat.activation_count,
                   "speed": timeline.current_speed(actor, balance), "gauge_after": actor.gauge},
            affected=[actor.id],
        )

    def _step_actor_start(self) -> None:
        combat = self.combat
        assert combat.active_combatant_id is not None
        actor = combat.combatants[combat.active_combatant_id]
        if actor.is_hero:
            charges = self.content.balance["reactions"]["charges_per_activation"]
            if actor.reaction_charges != charges:
                actor.reaction_charges = charges
                self.emit(EventType.REACTION_CHARGE_REFRESHED, actor_id=actor.id, delta={"charges": charges})
        effects.activation_start_effects(self, actor)
        if combat.outcome is not None:
            return
        if not actor.standing:
            self.emit(EventType.ACTIVATION_ENDED, actor_id=actor.id, delta={"reason": "removed at activation start"})
            combat.active_combatant_id = None
            combat.phase = CombatPhase.TERMINAL_CHECK
            return
        if actor.is_hero:
            rerolls = self.content.class_def(actor.archetype_id)["rerolls"]
            combat.turn = HeroTurn(hero_id=actor.id, rerolls_remaining=rerolls)
            combat.phase = CombatPhase.HERO_ROLL
        else:
            combat.phase = CombatPhase.ENEMY_INTENT

    def _step_lock_plan(self) -> None:
        self.combat.phase = CombatPhase.ACTION_RESOLVE

    def _step_action_resolve(self) -> None:
        combat = self.combat
        turn = combat.turn
        assert turn is not None
        if turn.queue_index >= len(turn.plan):
            combat.phase = CombatPhase.ACTOR_END
            return
        intent = turn.plan[turn.queue_index]
        turn.queue_index += 1
        if effects.resolve_action(self, intent, self.intent_face(intent)):
            turn.resolved_categories.append(intent.category)
        if self.check_terminal():
            return
        if turn.queue_index >= len(turn.plan):
            combat.phase = CombatPhase.ACTOR_END

    def _step_enemy_intent(self) -> None:
        combat = self.combat
        assert combat.active_combatant_id is not None
        enemy = combat.combatants[combat.active_combatant_id]
        intent, record = enemy_ai.choose_intent(self, enemy)
        if intent is None:
            self.emit(EventType.ENEMY_PASSED, actor_id=enemy.id, delta={"reason": "no legal action"})
            combat.phase = CombatPhase.ACTOR_END
            return
        combat.committed_intent = intent
        combat.reactions_used = []
        draw = record.pop("draw")
        self.emit(
            EventType.INTENT_SELECTED,
            actor_id=enemy.id,
            intent_id=intent.id,
            delta=record,
            rng_stream=draw["stream"],
            rng_draw_index=draw["index"],
        )
        combat.phase = CombatPhase.REVEAL_INTENT

    def _step_reveal_intent(self) -> None:
        combat = self.combat
        intent = combat.committed_intent
        assert intent is not None
        face = self.intent_face(intent)
        reactable = reactions.intent_is_reactable(self, intent, face)
        self.emit(
            EventType.INTENT_REVEALED,
            actor_id=intent.actor_id,
            intent_id=intent.id,
            delta={
                "name": intent.name,
                "category": intent.category,
                "power": intent.power,
                "effects": face.effects,
                "target_ids": intent.committed_target_ids,
                "costs": intent.costs,
                "tags": intent.tags,
                "interruptible": "interruptible" in intent.tags,
                "elite_resistant": "elite_resistant" in intent.tags,
                "reactable": reactable,
            },
        )
        if reactable:
            self._enter_stage(0)
        else:
            self.emit(
                EventType.REACTION_STAGE_SKIPPED,
                intent_id=intent.id,
                delta={"stage": "all", "reason": "enemy action is not reactable"},
            )
            combat.phase = CombatPhase.ENEMY_RESOLVE

    def _step_enemy_resolve(self) -> None:
        combat = self.combat
        intent = combat.committed_intent
        assert intent is not None
        if intent.cancelled:
            self.emit(
                EventType.ACTION_CANCELLED,
                actor_id=intent.actor_id,
                intent_id=intent.id,
                delta={"name": intent.name, "category": intent.category, "reason": intent.cancel_reason,
                       "cost_spent": 0, "committed_target_ids": intent.committed_target_ids},
            )
        else:
            effects.resolve_action(self, intent, self.intent_face(intent))
        if self.check_terminal():
            return
        combat.phase = CombatPhase.ACTOR_END

    def _step_actor_end(self) -> None:
        combat = self.combat
        assert combat.active_combatant_id is not None
        actor = combat.combatants[combat.active_combatant_id]
        effects.activation_end_effects(self, actor)
        if combat.outcome is not None:
            return
        self.emit(EventType.ACTIVATION_ENDED, actor_id=actor.id, delta={"reason": "completed"}, affected=[actor.id])
        combat.active_combatant_id = None
        combat.turn = None
        combat.committed_intent = None
        combat.reaction_stage = None
        combat.reactions_used = []
        combat.phase = CombatPhase.TERMINAL_CHECK

    def _step_terminal_check(self) -> None:
        if not self.check_terminal():
            self.combat.phase = CombatPhase.ADVANCE_TIMELINE

    # ----------------------------------------------------------------------------------------
    # Read-only queries (never mutate state or consume randomness)
    # ----------------------------------------------------------------------------------------

    def preview_plan(self, actions: list[dict[str, Any]]) -> tuple[list[ActionIntent], str | None]:
        """Validate a draft plan without committing it. Returns ``(ordered intents, problem)``."""
        if self._state is None or self.state.phase != RunPhase.BATTLE or self.combat.turn is None:
            return [], "No hero is planning."
        hero, turn = self._active_hero()
        if not turn.rolled:
            return [], "Roll the dice first."
        try:
            return planning.build_plan(self, hero, turn, actions), None
        except planning.PlanError as error:
            return [], str(error)

    def permissible_commands(self) -> list[str]:
        if self._state is None:
            return [cmd.START_RUN]
        state = self.state
        if state.phase == RunPhase.UPGRADE:
            return [cmd.CHOOSE_UPGRADE, cmd.SET_FORMATION]
        if state.phase == RunPhase.EQUIPMENT:
            allowed = [cmd.ADVANCE_PHASE, cmd.SET_FORMATION]
            limit = self.content.balance["upgrades"]["max_swaps_per_hero"]
            if any(state.swaps_used.get(member["id"], 0) < limit for member in state.party):
                allowed.append(cmd.SWAP_DIE)
            return allowed
        if state.phase != RunPhase.BATTLE:
            return []
        phase = self.combat.phase
        if phase == CombatPhase.HERO_ROLL:
            return [cmd.ROLL_DICE]
        if phase == CombatPhase.KEEP_REROLL:
            return [cmd.SET_KEPT_DICE, cmd.REROLL_UNKEPT, cmd.SET_ACTION_PLAN]
        if phase == CombatPhase.ACTION_PLAN:
            return [cmd.SET_ACTION_PLAN, cmd.COMMIT_ACTION_PLAN]
        if phase in self._WINDOWS:
            return [cmd.USE_REACTION, cmd.SKIP_REACTION_STAGE]
        return [cmd.ADVANCE_PHASE]


_HANDLERS = {
    cmd.START_RUN: "_start_run",
    cmd.SET_FORMATION: "_set_formation",
    cmd.ROLL_DICE: "_roll_dice",
    cmd.SET_KEPT_DICE: "_set_kept_dice",
    cmd.REROLL_UNKEPT: "_reroll_unkept",
    cmd.SET_ACTION_PLAN: "_set_action_plan",
    cmd.COMMIT_ACTION_PLAN: "_commit_action_plan",
    cmd.USE_REACTION: "_use_reaction",
    cmd.SKIP_REACTION_STAGE: "_skip_reaction_stage",
    cmd.CHOOSE_UPGRADE: "_choose_upgrade",
    cmd.SWAP_DIE: "_swap_die",
    cmd.ADVANCE_PHASE: "_advance_phase",
}

_STEPS = {
    CombatPhase.ADVANCE_TIMELINE: "_step_advance_timeline",
    CombatPhase.ACTOR_START: "_step_actor_start",
    CombatPhase.LOCK_PLAN: "_step_lock_plan",
    CombatPhase.ACTION_RESOLVE: "_step_action_resolve",
    CombatPhase.ENEMY_INTENT: "_step_enemy_intent",
    CombatPhase.REVEAL_INTENT: "_step_reveal_intent",
    CombatPhase.ENEMY_RESOLVE: "_step_enemy_resolve",
    CombatPhase.ACTOR_END: "_step_actor_end",
    CombatPhase.TERMINAL_CHECK: "_step_terminal_check",
}


def run_until_input(engine: Engine, max_steps: int = 10000) -> int:
    """Send ``AdvancePhase`` until the engine needs a player decision or the run ends."""
    steps = 0
    while engine.started and not engine.needs_input():
        result = engine.do(cmd.ADVANCE_PHASE)
        if not result.accepted:  # pragma: no cover - defensive
            raise RuntimeError(f"AdvancePhase rejected: {result.reason}")
        steps += 1
        if steps > max_steps:
            raise RuntimeError("Combat did not reach a decision point (possible non-terminating state).")
    return steps
