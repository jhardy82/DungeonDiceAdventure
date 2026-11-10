"""Shared scenario helpers for the Battle Dice test suite.

Tests *arrange* state with the small white-box helpers below (set a gauge, set HP, down a hero)
and then *act* exclusively through engine commands, exactly like the UI does. Specific die faces
and enemy choices are forced through ``Engine.force_draws`` so each rule can be exercised
directly; determinism tests use the real BD-PCG32-v1 streams.

Two content sets are used on purpose:

* **Mechanics content** (``mechanics_content()``, the default for ``start()``): the shipped
  classes, dice, enemies, upgrades and balance, with the encounter table frozen at the
  rules-1.1.0 values in ``tests/golden/encounters_mechanics.json``. Rule fixtures assert exact
  arithmetic (a Slash for 2 against 6 HP, and so on); freezing the encounter numbers keeps them
  about the *rules*, so a balance retune of enemy HP, damage or speed does not rewrite them.
* **Shipped content** (the ``content`` fixture / ``packaged_content()``): exactly what players
  get. The content tables, party-scaling, full-run, replay, simulator and UI tests use it.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from battle_dice.content.loader import Content, build_content, load_content, load_documents
from battle_dice.core import commands as cmd
from battle_dice.core.engine import Engine, run_until_input
from battle_dice.core.models import STATE_DOWNED, Combatant, CombatPhase, StatusInstance

_CONTENT: Content | None = None
_MECHANICS: Content | None = None
_MECHANICS_ENCOUNTERS = Path(__file__).parent / "golden" / "encounters_mechanics.json"


def packaged_content() -> Content:
    """The shipped content, exactly as players get it."""
    global _CONTENT
    if _CONTENT is None:
        _CONTENT = load_content()
    return _CONTENT


def mechanics_documents() -> dict[str, Any]:
    """Shipped documents with the encounter table frozen at the rules-1.1.0 fixture values."""
    documents = copy.deepcopy(load_documents())
    encounters = json.loads(_MECHANICS_ENCOUNTERS.read_text(encoding="utf-8"))
    encounters["content_version"] = documents["balance"]["content_version"]
    documents["encounters"] = encounters
    return documents


def mechanics_content() -> Content:
    """Content for rule fixtures: shipped rules data, frozen encounter numbers."""
    global _MECHANICS
    if _MECHANICS is None:
        _MECHANICS = build_content(mechanics_documents())
    return _MECHANICS


@pytest.fixture(scope="session")
def content() -> Content:
    return packaged_content()


@pytest.fixture()
def documents() -> dict[str, Any]:
    """A private, mutable copy of the raw content documents."""
    return copy.deepcopy(load_documents())


def content_with(mutate: Any) -> Content:
    """Build validated content from the mechanics documents after applying ``mutate(documents)``."""
    documents = mechanics_documents()
    mutate(documents)
    return build_content(documents)


def party_spec(*members: str) -> list[dict[str, str]]:
    """``"squire"`` uses the suggested row; ``"squire:back"`` overrides it."""
    result = []
    for member in members:
        class_id, _, row = member.partition(":")
        result.append({"class_id": class_id, "row": row or packaged_content().class_def(class_id)["suggested_row"]})
    return result


def start(*members: str, seed: int = 1, content: Content | None = None) -> Engine:
    """Start a run. Uses the mechanics content unless ``content`` is given (pass the shipped set explicitly)."""
    engine = Engine(content or mechanics_content())
    result = engine.do(cmd.START_RUN, seed=seed, party=party_spec(*members))
    assert result.accepted, result.reason
    return engine


def ok(result: Any) -> Any:
    assert result.accepted, result.reason
    return result


def rejected(result: Any, fragment: str = "") -> str:
    assert not result.accepted, "command was unexpectedly accepted"
    assert fragment.lower() in (result.reason or "").lower(), result.reason
    return result.reason


def unit(engine: Engine, cid: str) -> Combatant:
    """Current combatant object. Re-read it after a *rejected* command: rejection restores a state copy."""
    return engine.combat.combatants[cid]


def heroes(engine: Engine) -> list[Combatant]:
    return engine.combat.side("hero")


def enemies(engine: Engine) -> list[Combatant]:
    return engine.combat.side("enemy")


def make_ready(engine: Engine, cid: str) -> None:
    """Arrange: make ``cid`` the next actor (everyone else back to gauge 0)."""
    combat = engine.combat
    assert combat.phase == CombatPhase.ADVANCE_TIMELINE, combat.phase
    for combatant in combat.combatants.values():
        combatant.gauge = 0
    combat.combatants[cid].gauge = engine.content.balance["timeline"]["ready_threshold"]


def step(engine: Engine, count: int = 1) -> None:
    for _ in range(count):
        ok(engine.do(cmd.ADVANCE_PHASE))


def step_to(engine: Engine, phase: str, limit: int = 50) -> None:
    """Send AdvancePhase until the combat phase equals ``phase``."""
    for _ in range(limit):
        if engine.combat.phase == phase:
            return
        ok(engine.do(cmd.ADVANCE_PHASE))
    raise AssertionError(f"never reached phase {phase}; stuck at {engine.combat.phase}")


def begin_hero(engine: Engine, hero_id: str, **faces: int) -> None:
    """Arrange + act: activate ``hero_id`` and roll the given 1-based faces (``iron_d6=3``)."""
    make_ready(engine, hero_id)
    run_until_input(engine)
    assert engine.combat.phase == CombatPhase.HERO_ROLL, engine.combat.phase
    assert engine.combat.active_combatant_id == hero_id
    roll(engine, **faces)


def roll(engine: Engine, **faces: int) -> None:
    hero = unit(engine, engine.combat.active_combatant_id)  # type: ignore[arg-type]
    dice = sorted(hero.equipped_dice_ids)
    assert set(faces) == set(dice), f"give a face for each of {dice}"
    engine.force_draws("dice", [faces[d] - 1 for d in dice])
    ok(engine.do(cmd.ROLL_DICE))


def reroll(engine: Engine, **faces: int) -> Any:
    """Force the faces of the dice that will be rerolled (unkept dice, in die-ID order)."""
    turn = engine.combat.turn
    assert turn is not None
    unkept = [d for d in sorted(turn.rolled) if d not in turn.kept]
    assert set(faces) == set(unkept), f"give a face for each unkept die {unkept}"
    engine.force_draws("dice", [faces[d] - 1 for d in unkept])
    return engine.do(cmd.REROLL_UNKEPT)


def action(die_id: str, *target_ids: str) -> dict[str, Any]:
    return {"die_id": die_id, "target_ids": list(target_ids)}


def commit(engine: Engine, *actions: dict[str, Any]) -> None:
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=list(actions)))
    ok(engine.do(cmd.COMMIT_ACTION_PLAN))


def resolve_hero(engine: Engine, *actions: dict[str, Any]) -> None:
    """Commit a plan and resolve the whole activation through ACTOR_END and the terminal check."""
    commit(engine, *actions)
    finish_activation(engine)


def finish_activation(engine: Engine) -> None:
    for _ in range(50):
        if engine.finished() or engine.state.phase != "battle":
            return
        if engine.combat.phase == CombatPhase.ADVANCE_TIMELINE:
            return
        if engine.needs_input():
            raise AssertionError(f"unexpected input phase {engine.combat.phase}")
        ok(engine.do(cmd.ADVANCE_PHASE))
    raise AssertionError("activation did not finish")


def begin_enemy(engine: Engine, enemy_id: str, action_roll: int | None = None) -> None:
    """Arrange + act: activate an enemy and stop once its intent is revealed.

    ``action_roll`` forces the weighted roll inside the highest priority tier (stable action-ID order).
    Stops in the first open reaction window, or at ENEMY_RESOLVE when no window opens.
    """
    make_ready(engine, enemy_id)
    if action_roll is not None:
        engine.force_draws("enemy", [action_roll])
    step_to(engine, CombatPhase.REVEAL_INTENT)
    step(engine)


def down(engine: Engine, hero_id: str) -> None:
    hero = unit(engine, hero_id)
    hero.hp = 0
    hero.state = STATE_DOWNED


def add_status(engine: Engine, cid: str, kind: str, remaining: int = 2, stacks: int = 1) -> StatusInstance:
    combat = engine.combat
    instance = StatusInstance(
        id=f"st{combat.next_status_seq:04d}", kind=kind, source_id="test", target_id=cid, stacks=stacks,
        remaining_target_activations=remaining, created_event_seq=combat.event_seq,
    )
    combat.next_status_seq += 1
    unit(engine, cid).status_instances.append(instance)
    return instance


def events_of(engine: Engine, event_type: str) -> list[Any]:
    return [e for e in engine.events if e.type == event_type]


def last_event(engine: Engine, event_type: str) -> Any:
    found = events_of(engine, event_type)
    assert found, f"no {event_type} event was logged"
    return found[-1]


def skip_reactions(engine: Engine) -> None:
    """Skip every open reaction window for the current enemy intent."""
    while engine.state.phase == "battle" and engine.combat.phase in CombatPhase.STAGE_BY_WINDOW:
        ok(engine.do(cmd.SKIP_REACTION_STAGE))


def enemy_acts(engine: Engine, enemy_id: str, action_roll: int | None = None) -> None:
    """Run one full enemy activation with every reaction window skipped."""
    begin_enemy(engine, enemy_id, action_roll)
    skip_reactions(engine)
    finish_activation(engine)


def force_slash(engine: Engine, *_hero_ids: str) -> None:
    """Arrange: make Dirty Trick illegal so a Goblin's only legal action is Slash.

    Dirty Trick is ranged (rules 1.1.0), so it can reach any standing hero. Two full-duration
    Weaken stacks on *every* hero leave it nothing to change, which makes it illegal for the AI.
    Hero ids are accepted for readability at the call site; all heroes are always saturated.
    """
    for hero in heroes(engine):
        hero.status_instances = [s for s in hero.status_instances if s.kind != "weaken"]
        add_status(engine, hero.id, "weaken", remaining=2)
        add_status(engine, hero.id, "weaken", remaining=2)


def captain_content(size: int) -> Content:
    """Content whose Battle 1 for ``size`` heroes is a lone base-stat Blight Captain (elite fixture)."""

    def mutate(documents: dict[str, Any]) -> None:
        documents["encounters"]["encounters"][str(size)][0]["enemies"] = [{"archetype": "captain"}]

    return content_with(mutate)


def win_battle(engine: Engine) -> None:
    """Arrange + act: leave one enemy at 1 HP and let hero h01 finish it with a real attack."""
    foes = enemies(engine)
    for foe in foes[1:]:
        foe.hp = 0
        foe.state = "defeated"
    foes[0].hp = 1
    foes[0].shields = 0
    hero = unit(engine, "h01")
    hero.status_instances = [s for s in hero.status_instances if s.kind != "weaken"]
    attack_faces = {"squire": {"iron_d6": 1, "oath_d4": 1}, "apprentice": {"arcane_d6": 1, "focus_d4": 1},
                    "scout": {"striker_d8": 1, "tools_d4": 1}}[hero.archetype_id]
    first_die = sorted(attack_faces)[0]
    if hero.archetype_id == "apprentice":
        hero.mana = max(hero.mana, 1)
    begin_hero(engine, "h01", **attack_faces)
    commit(engine, action(first_die, foes[0].id))
    while engine.state.phase == "battle" and not engine.needs_input():
        ok(engine.do(cmd.ADVANCE_PHASE))
