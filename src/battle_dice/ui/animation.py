"""Presentation-only animation driven by the engine's event log.

The animator reads events that were appended since the last frame and turns them into short
overlays: floating numbers, a dice tumble, eased HP bars and a pulse on the acting combatant.
It never calls the engine, never changes rules state and never uses the engine's random streams,
so seeded replays are unaffected. Time comes from the frame delta, which keeps tests deterministic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

FLOAT_MS = 950.0
TUMBLE_MS = 420.0
TUMBLE_STEP_MS = 55.0
HP_EASE_PER_MS = 0.012  # fraction of the remaining gap closed per millisecond (capped at 1)
PULSE_PERIOD_MS = 900.0
FAST_FACTOR = 0.45

GOOD = (112, 207, 127)
BAD = (240, 110, 110)
SHIELD = (150, 190, 235)
MANA = (120, 150, 245)
CORRUPT = (190, 120, 220)
NOTE = (242, 193, 78)
STATUS_SHORT = {"poison": "PSN", "weaken": "WKN", "speed_up": "SPD+"}


@dataclass
class Floater:
    target_id: str
    text: str
    colour: tuple[int, int, int]
    age_ms: float = 0.0
    lane: int = 0

    def progress(self, duration: float) -> float:
        return min(1.0, self.age_ms / duration)


class Animator:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.fast = False
        self.floaters: list[Floater] = []
        self.tumbles: dict[str, float] = {}  # die_id -> elapsed ms
        self.display_hp: dict[str, float] = {}
        self.clock_ms = 0.0
        self._event_index = 0
        self._engine_id: int | None = None

    # -- timing ------------------------------------------------------------------------------

    def _factor(self) -> float:
        return FAST_FACTOR if self.fast else 1.0

    @property
    def float_ms(self) -> float:
        return FLOAT_MS * self._factor()

    @property
    def tumble_ms(self) -> float:
        return TUMBLE_MS * self._factor()

    def reset(self) -> None:
        self.floaters.clear()
        self.tumbles.clear()
        self.display_hp.clear()
        self._event_index = 0

    # -- input: engine events ----------------------------------------------------------------

    def sync(self, engine: Any | None) -> None:
        """Consume events appended since the last call. Read-only on the engine."""
        if engine is None or not engine.started:
            self._engine_id = None
            self.reset()
            return
        if id(engine) != self._engine_id or self._event_index > len(engine.events):
            self._engine_id = id(engine)
            self.reset()
            self._event_index = len(engine.events)  # do not replay history of a run we just met
            return
        new_events = engine.events[self._event_index:]
        self._event_index = len(engine.events)
        if not self.enabled:
            return
        for event in new_events:
            self._on_event(event)

    def _add(self, target_id: str, text: str, colour: tuple[int, int, int]) -> None:
        lane = sum(1 for f in self.floaters if f.target_id == target_id and f.age_ms < 250)
        self.floaters.append(Floater(target_id, text, colour, lane=lane))

    def _on_event(self, event: Any) -> None:
        kind, d = event.type, event.delta
        if kind in ("dice_rolled", "dice_rerolled"):
            self.tumbles[d["die_id"]] = 0.0
        elif kind == "action_resolved":
            for result in d.get("results", []):
                target = result.get("target")
                if not target:
                    continue
                effect = result.get("type")
                if effect == "damage":
                    if result.get("hp_damage"):
                        self._add(target, f"-{result['hp_damage']}", BAD)
                    if result.get("absorbed"):
                        self._add(target, f"blocked {result['absorbed']}", SHIELD)
                    if not result.get("hp_damage") and not result.get("absorbed"):
                        self._add(target, "0", SHIELD)
                elif effect == "shield" and result.get("gained"):
                    self._add(target, f"+{result['gained']} SH", SHIELD)
                elif effect == "heal":
                    self._add(target, "REVIVED" if result.get("revived") else f"+{result.get('healed', 0)}", GOOD)
                elif effect == "apply_status" and result.get("applied"):
                    self._add(target, STATUS_SHORT.get(result["status"], result["status"]), NOTE)
                elif effect == "gain_mana" and result.get("gained"):
                    self._add(target, f"+{result['gained']} MP", MANA)
                elif effect == "gain_corruption" and result.get("gained"):
                    self._add(target, f"+{result['gained']} CR", CORRUPT)
                elif effect == "remove_corruption" and result.get("removed"):
                    self._add(target, f"-{result['removed']} CR", CORRUPT)
        elif kind in ("poison_tick", "corruption_backlash") and event.actor_id and d.get("hp_damage"):
            self._add(event.actor_id, f"-{d['hp_damage']}", BAD)
        elif kind == "combatant_downed":
            self._add(d["id"], "DOWNED", BAD)
        elif kind == "combatant_defeated":
            self._add(d["id"], "DEFEATED", NOTE)
        elif kind == "reaction_used" and event.actor_id:
            self._add(event.actor_id, d.get("name", "Reaction"), NOTE)
        elif kind == "intent_cancelled" and event.actor_id:
            self._add(event.actor_id, "CANCELLED", NOTE)
        elif kind == "action_retargeted" and d.get("to"):
            self._add(d["to"], "RETARGET", NOTE)

    # -- update ------------------------------------------------------------------------------

    def update(self, dt_ms: float, actual_hp: dict[str, int] | None = None) -> None:
        dt_ms = max(0.0, dt_ms)
        self.clock_ms += dt_ms
        for floater in self.floaters:
            floater.age_ms += dt_ms
        self.floaters = [f for f in self.floaters if f.age_ms < self.float_ms]
        for die_id in list(self.tumbles):
            self.tumbles[die_id] += dt_ms
            if self.tumbles[die_id] >= self.tumble_ms:
                del self.tumbles[die_id]
        if actual_hp is not None:
            for cid in list(self.display_hp):
                if cid not in actual_hp:
                    del self.display_hp[cid]
            for cid, hp in actual_hp.items():
                shown = self.display_hp.get(cid)
                if shown is None or not self.enabled:
                    self.display_hp[cid] = float(hp)
                    continue
                gap = hp - shown
                step = gap * min(1.0, HP_EASE_PER_MS * dt_ms / self._factor())
                self.display_hp[cid] = float(hp) if abs(gap - step) < 0.05 else shown + step

    # -- output: what to draw ----------------------------------------------------------------

    def shown_hp(self, combatant_id: str, actual: int) -> float:
        if not self.enabled:
            return float(actual)
        return self.display_hp.get(combatant_id, float(actual))

    def tumbling_face(self, die_id: str, size: int, real_face: int) -> int:
        """Face index to draw for a die: cycles while tumbling, then settles on the real result."""
        elapsed = self.tumbles.get(die_id)
        if not self.enabled or elapsed is None or size <= 0:
            return real_face
        return (real_face + 1 + int(elapsed // TUMBLE_STEP_MS)) % size

    def is_tumbling(self, die_id: str) -> bool:
        return self.enabled and die_id in self.tumbles

    def pulse(self) -> float:
        """0..1 breathing value for the acting combatant's highlight (constant when disabled)."""
        if not self.enabled:
            return 1.0
        return 0.5 + 0.5 * math.sin(2 * math.pi * self.clock_ms / PULSE_PERIOD_MS)

    def active_floaters(self) -> list[tuple[Floater, float]]:
        return [(f, f.progress(self.float_ms)) for f in self.floaters] if self.enabled else []

    def busy(self) -> bool:
        return self.enabled and bool(self.floaters or self.tumbles)
