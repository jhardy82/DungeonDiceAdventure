"""Regression tests for the defects and test gaps found in the MVP review.

Each test names the behaviour it protects. Several of them were written against a deliberately
broken copy of the engine that the previous suite did not notice (enemy damage ignoring the
per-party-size override, Speed Up resetting the gauge, no Sharpen cap, replay hash checks removed,
area actions never cancelling, the content hash ignoring balance.json, no rollback on an
unexpected exception).
"""

from __future__ import annotations

import copy
import itertools

import pytest

from battle_dice.content.loader import ContentError, build_content, load_documents
from battle_dice.core import commands as cmd
from battle_dice.core import effects, enemy_ai, progression, replay
from battle_dice.core.commands import Command
from battle_dice.core.engine import Engine, run_until_input
from battle_dice.core.events import EventType, events_hash, state_hash
from battle_dice.core.models import CombatPhase, RunPhase
from battle_dice.core.view import snapshot
from battle_dice.sim.policies import HeuristicPolicy, play_run
from tests.conftest import (
    action,
    add_status,
    begin_enemy,
    begin_hero,
    captain_content,
    commit,
    content_with,
    down,
    enemies,
    enemy_acts,
    events_of,
    finish_activation,
    force_slash,
    heroes,
    last_event,
    make_ready,
    ok,
    packaged_content,
    rejected,
    resolve_hero,
    skip_reactions,
    start,
    step,
    step_to,
    unit,
    win_battle,
)


def roll_for(engine: Engine, enemy_id: str, action_id: str) -> int:
    """The forced weighted roll that makes ``enemy_id`` choose ``action_id`` from its top tier."""
    evaluated = enemy_ai.evaluate_actions(engine, unit(engine, enemy_id))
    top = max(entry["priority"] for entry in evaluated)
    offset = 0
    for entry in (e for e in evaluated if e["priority"] == top):
        if entry["action_id"] == action_id:
            return offset
        offset += entry["face"].weight
    raise AssertionError(f"{action_id} is not in the top tier of {enemy_id}")


def saturate(engine: Engine, kind: str) -> None:
    """Arrange: every hero at the stack cap of ``kind`` with long durations, so re-applying it is illegal."""
    cap = engine.content.status_cap(kind)
    for hero in heroes(engine):
        hero.status_instances = [s for s in hero.status_instances if s.kind != kind]
        for _ in range(cap):
            add_status(engine, hero.id, kind, remaining=9)


# --------------------------------------------------------------------------------------------
# Status stacks at the cap
# --------------------------------------------------------------------------------------------


def test_a_status_at_the_cap_refreshes_the_stack_with_the_least_time_left():
    engine = start("scout")
    foe = enemies(engine)[0]
    long_stack = add_status(engine, foe.id, "weaken", remaining=3)
    short_stack = add_status(engine, foe.id, "weaken", remaining=1)
    begin_hero(engine, "h01", striker_d8=6, tools_d4=4)  # Hamstring: Weaken 1 for 2 activations
    resolve_hero(engine, action("striker_d8", foe.id))
    applied = last_event(engine, EventType.ACTION_RESOLVED).delta["results"][0]["applied"]
    assert applied == [{"status": "weaken", "result": "refreshed", "id": short_stack.id}]
    remaining = {s.id: s.remaining_target_activations for s in unit(engine, foe.id).instances_of("weaken")}
    assert remaining == {long_stack.id: 3, short_stack.id: 2}
    refreshed = last_event(engine, EventType.STATUS_REFRESHED)
    assert refreshed.delta["status"] == "weaken" and refreshed.delta["status_id"] == short_stack.id


@pytest.mark.parametrize("kind", ["poison", "weaken"])
def test_the_ai_legality_test_agrees_with_what_applying_the_status_does(kind):
    """"Applying changes nothing" must mean the same thing to the AI and to the effect itself."""
    base = start("scout")
    foe_id = enemies(base)[0].id
    cap = base.content.status_cap(kind)
    for durations in itertools.product((1, 2, 3), repeat=cap):
        for new_duration in (1, 2, 3):
            engine = copy.deepcopy(base)
            foe = unit(engine, foe_id)
            for remaining in durations:
                add_status(engine, foe_id, kind, remaining=remaining)
            predicted_no_change = effects.status_unrefreshable(engine, foe, kind, new_duration)
            results = effects.apply_status(engine, unit(engine, "h01"), foe, kind, 1, new_duration)
            assert (results[0]["result"] == "no_change") == predicted_no_change, (durations, new_duration, results)


def test_a_first_application_logs_status_applied():
    engine = start("scout")
    foe = enemies(engine)[0]
    begin_hero(engine, "h01", striker_d8=4, tools_d4=4)  # Poison
    resolve_hero(engine, action("striker_d8", foe.id))
    event = last_event(engine, EventType.STATUS_APPLIED)
    assert event.delta["status"] == "poison" and event.delta["id"] == foe.id, "the event names the affected unit"
    assert event.delta["status_id"] == unit(engine, foe.id).instances_of("poison")[0].id
    assert foe.id in event.after, "and records that unit's state after the change"


# --------------------------------------------------------------------------------------------
# Enemy AI
# --------------------------------------------------------------------------------------------


def _wave_with_poison(size: int):
    def mutate(documents):
        documents["encounters"]["encounters"][str(size)][0]["enemies"] = [{"archetype": "captain"}]
        documents["enemies"]["enemies"]["captain"]["actions"]["blight_wave"]["effects"].append(
            {"type": "apply_status", "target": "target", "status": "poison", "duration": 2})

    return content_with(mutate)


def test_an_area_action_with_a_status_still_hits_heroes_whose_status_cannot_change():
    engine = start("squire", "scout", content=_wave_with_poison(2))
    for _ in range(engine.content.status_cap("poison")):
        add_status(engine, "h01", "poison", remaining=9)
    wave = next(e for e in enemy_ai.evaluate_actions(engine, enemies(engine)[0]) if e["action_id"] == "blight_wave")
    assert sorted(t.id for t in wave["targets"]) == ["h01", "h02"], "the capped hero must still take the damage"


def test_a_pure_status_area_action_is_illegal_only_when_nothing_would_change():
    def mutate(documents):
        documents["encounters"]["encounters"]["2"][0]["enemies"] = [{"archetype": "captain"}]
        wave = documents["enemies"]["enemies"]["captain"]["actions"]["blight_wave"]
        wave["category"] = "status"
        wave["effects"] = [{"type": "apply_status", "target": "target", "status": "poison", "duration": 2}]

    engine = start("squire", "scout", content=content_with(mutate))
    captain = enemies(engine)[0]
    assert "blight_wave" in {e["action_id"] for e in enemy_ai.evaluate_actions(engine, captain)}
    saturate(engine, "poison")
    assert "blight_wave" not in {e["action_id"] for e in enemy_ai.evaluate_actions(engine, captain)}


def test_an_enemy_with_no_legal_action_passes_and_the_battle_goes_on():
    def mutate(documents):
        documents["enemies"]["enemies"]["goblin"]["actions"]["slash"]["weight"] = 0  # only Dirty Trick is left

    engine = start("squire", content=content_with(mutate))
    goblin = enemies(engine)[0]
    force_slash(engine)  # Weaken saturated: Dirty Trick would change nothing, so it is illegal too
    before = unit(engine, "h01").hp
    make_ready(engine, goblin.id)
    for _ in range(20):
        if events_of(engine, EventType.ENEMY_PASSED):
            break
        step(engine)
    passed = last_event(engine, EventType.ENEMY_PASSED)
    assert passed.actor_id == goblin.id
    finish_activation(engine)
    assert engine.combat.phase == CombatPhase.ADVANCE_TIMELINE and unit(engine, "h01").hp == before
    assert last_event(engine, EventType.ACTIVATION_ENDED).actor_id == goblin.id


# --------------------------------------------------------------------------------------------
# Shipped per-party-size numbers, checked as behaviour and not only as data
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("party", [("squire",), ("squire", "scout"), ("squire",) * 3, ("squire",) * 4, ("squire",) * 5])
def test_shipped_slash_deals_its_per_size_damage(party):
    shipped = packaged_content()
    engine = start(*party, content=shipped)
    goblin = next(e for e in enemies(engine) if e.archetype_id == "goblin")
    expected = engine.enemy_action(goblin, "slash").power
    assert expected == 3 and shipped.enemy_action("goblin", "slash").power == 2, "the shipped table raises Slash by 1"
    force_slash(engine)
    enemy_acts(engine, goblin.id)
    result = last_event(engine, EventType.ACTION_RESOLVED).delta["results"][0]
    victim = unit(engine, result["target"])
    assert result["base"] == 3 and result["hp_damage"] == 3
    assert victim.hp == victim.max_hp - 3


def test_shipped_shadow_bolt_deals_its_per_size_damage():
    shipped = packaged_content()
    engine = start("squire", "scout", content=shipped)
    adept = next(e for e in enemies(engine) if e.archetype_id == "hex_adept")
    assert engine.enemy_action(adept, "shadow_bolt").power == 4 and shipped.enemy_action("hex_adept", "shadow_bolt").power == 3
    saturate(engine, "poison")  # Poison Dart illegal, so Shadow Bolt and Corrupt Mark share one tier
    make_ready(engine, adept.id)
    engine.force_draws("enemy", [roll_for(engine, adept.id, "shadow_bolt")])
    step_to(engine, CombatPhase.REVEAL_INTENT)
    step(engine)
    skip_reactions(engine)
    finish_activation(engine)
    result = last_event(engine, EventType.ACTION_RESOLVED).delta["results"][0]
    assert result["base"] == 4 and result["hp_damage"] == 4


def test_shipped_captain_strike_deals_its_per_size_damage_in_battle_two():
    shipped = packaged_content()
    engine = start("squire", "scout", content=shipped)
    win_battle(engine)
    offer = engine.state.upgrade_offers["h01"]["iron_d6"][0]["offer_id"]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="iron_d6", offer_id=offer))
    ok(engine.do(cmd.ADVANCE_PHASE))
    assert engine.state.encounter_index == 1
    run_until_input(engine)
    captain = next(e for e in enemies(engine) if e.archetype_id == "captain")
    assert engine.enemy_action(captain, "strike").power == 4 and shipped.enemy_action("captain", "strike").power == 3
    while engine.combat.phase != CombatPhase.ADVANCE_TIMELINE:  # finish whatever was in progress
        if engine.needs_input():
            if engine.combat.phase in CombatPhase.STAGE_BY_WINDOW:
                ok(engine.do(cmd.SKIP_REACTION_STAGE))
            elif engine.combat.phase == CombatPhase.HERO_ROLL:
                ok(engine.do(cmd.ROLL_DICE))
            else:
                commit(engine)
        else:
            step(engine)
    for hero in heroes(engine):
        hero.hp, hero.shields = hero.max_hp, 0
        hero.status_instances.clear()
    add_status(engine, captain.id, "speed_up", stacks=2)  # War Cry already active, so it is not chosen again
    make_ready(engine, captain.id)
    engine.force_draws("enemy", [roll_for(engine, captain.id, "strike")])
    step_to(engine, CombatPhase.REVEAL_INTENT)
    step(engine)
    skip_reactions(engine)
    finish_activation(engine)
    result = last_event(engine, EventType.ACTION_RESOLVED).delta["results"][0]
    assert result["base"] == 4 and result["hp_damage"] == 4


# --------------------------------------------------------------------------------------------
# Timeline: a speed change keeps the gauge (AC-06)
# --------------------------------------------------------------------------------------------


def test_war_cry_changes_speed_but_keeps_the_gauge_it_had():
    engine = start("squire", content=captain_content(1))
    captain = enemies(engine)[0]
    make_ready(engine, captain.id)
    captain.gauge = 137  # 37 over the threshold, so the gauge is not 0 while War Cry resolves
    engine.force_draws("enemy", [roll_for(engine, captain.id, "war_cry")])
    speed_before = captain.speed
    step_to(engine, CombatPhase.REVEAL_INTENT)
    assert engine.combat.committed_intent.ability_id == "war_cry"
    step(engine)
    skip_reactions(engine)
    finish_activation(engine)
    captain = unit(engine, captain.id)
    assert captain.gauge == 37, "applying Speed Up must not reset or change the gauge"
    assert captain.stacks_of("speed_up") == 2
    shown = next(c for c in snapshot(engine)["combatants"] if c["id"] == captain.id)
    assert shown["speed"] == speed_before + 2


def test_applying_speed_up_directly_never_touches_the_gauge():
    engine = start("squire")
    foe = enemies(engine)[0]
    foe.gauge = 63
    effects.apply_status(engine, foe, foe, "speed_up", 2, 2)
    assert foe.gauge == 63
    effects.apply_status(engine, foe, foe, "speed_up", 2, 2)  # refresh: still untouched
    assert foe.gauge == 63 and len(foe.instances_of("speed_up")) == 1


# --------------------------------------------------------------------------------------------
# Upgrades: Sharpen respects the caps (D-11)
# --------------------------------------------------------------------------------------------


def test_sharpen_stops_at_the_face_power_cap(content):
    cap = content.balance["upgrades"]["face_power_cap"]
    face = copy.deepcopy(content.die("iron_d6").faces[0])  # Strike 2
    for expected in range(face.power + 1, cap + 1):
        face = progression.sharpened(face, cap)
        assert face is not None and face.power == expected
    assert face.power == cap and progression.sharpened(face, cap) is None, "a face at the cap cannot be sharpened"


def test_sharpen_stops_at_the_cap_for_status_durations_too(content):
    cap = content.balance["upgrades"]["face_power_cap"]
    face = copy.deepcopy(next(f for f in content.die("striker_d8").faces if f.id == "sc_poison"))
    def duration(of) -> int:
        effect = of.status_effect()
        assert effect is not None
        return effect["duration"]

    seen = [duration(face)]
    while (sharper := progression.sharpened(face, cap)) is not None:
        face = sharper
        seen.append(duration(face))
    assert seen == list(range(2, cap + 1)) and face.power == 1, "duration grows to the cap; stack size never does"


# --------------------------------------------------------------------------------------------
# Targets: an area action with nobody left is cancelled (D-15)
# --------------------------------------------------------------------------------------------


def test_an_area_action_with_no_remaining_target_is_cancelled():
    engine = start("squire", "scout", content=captain_content(2))
    captain = enemies(engine)[0]
    add_status(engine, captain.id, "speed_up", stacks=2)
    make_ready(engine, captain.id)
    engine.force_draws("enemy", [roll_for(engine, captain.id, "blight_wave")])
    step_to(engine, CombatPhase.REVEAL_INTENT)
    step(engine)
    skip_reactions(engine)
    down(engine, "h01")  # arrange: both committed targets fall before the wave resolves
    down(engine, "h02")
    resolved_before = len(events_of(engine, EventType.ACTION_RESOLVED))
    for _ in range(10):
        if events_of(engine, EventType.ACTION_CANCELLED) or engine.state.phase != RunPhase.BATTLE:
            break
        step(engine)
    cancelled = last_event(engine, EventType.ACTION_CANCELLED)
    assert cancelled.delta["reason"] == "no legal target remains"
    assert len(events_of(engine, EventType.ACTION_RESOLVED)) == resolved_before


# --------------------------------------------------------------------------------------------
# Commands, replay and snapshots
# --------------------------------------------------------------------------------------------


def _played(seed: int = 4) -> Engine:
    engine = start("squire", "apprentice", "scout", seed=seed, content=packaged_content())
    play_run(engine, HeuristicPolicy())
    return engine


def test_do_keeps_working_on_an_engine_rebuilt_by_replay():
    original = start("squire", seed=11)
    run_until_input(original)
    ok(original.do(cmd.ROLL_DICE))
    rebuilt = replay.replay(original.content, original.command_log)
    assert state_hash(rebuilt.state) == state_hash(original.state)
    result = rebuilt.do(cmd.SET_KEPT_DICE, die_ids=["iron_d6"])
    assert result.accepted and not result.duplicate, "the first new command after a replay was silently ignored"
    assert rebuilt.combat.turn.kept == ["iron_d6"]
    assert len({c.command_id for c in rebuilt.command_log}) == len(rebuilt.command_log)


def test_a_command_id_reused_for_a_different_command_is_rejected():
    engine = start("squire", seed=11)
    run_until_input(engine)
    first = Command(cmd.ROLL_DICE, "client-1", engine.revision, {})
    ok(engine.submit(first))
    again = engine.submit(first)
    assert again.accepted and again.duplicate, "the same command sent twice is acknowledged once"
    revision = engine.revision
    other = engine.submit(Command(cmd.SET_KEPT_DICE, "client-1", revision, {"die_ids": ["iron_d6"]}))
    rejected(other, "already used by a different command")
    assert engine.revision == revision and engine.combat.turn.kept == []


def test_the_command_log_does_not_share_lists_with_the_caller():
    engine = start("squire", seed=11)
    run_until_input(engine)
    ok(engine.do(cmd.ROLL_DICE))
    kept = ["iron_d6"]
    ok(engine.do(cmd.SET_KEPT_DICE, die_ids=kept))
    kept.append("oath_d4")  # the caller reuses its list afterwards
    assert engine.command_log[-1].params == {"die_ids": ["iron_d6"]}
    assert engine.combat.turn.kept == ["iron_d6"]
    replay.verify(engine.content, replay.export_run(engine))


def test_the_command_log_does_not_share_lists_with_the_state():
    engine = start("squire", "scout", seed=3)
    party = engine.command_log[0].params["party"]
    engine.state.party[0]["row"] = "back"  # white-box change to the state ...
    assert party[0]["row"] == "front", "... must not rewrite the logged StartRun command"


def _scramble(value):
    """Empty every container inside a snapshot, in place."""
    if isinstance(value, dict):
        for child in list(value.values()):
            _scramble(child)
        value.clear()
    elif isinstance(value, list):
        for child in value:
            _scramble(child)
        value.clear()


@pytest.mark.parametrize("stage", ["battle", "upgrade"])
def test_changing_a_snapshot_changes_neither_the_state_nor_the_content(stage):
    engine = start("squire", "apprentice", "scout", seed=2)
    if stage == "upgrade":
        win_battle(engine)
        assert engine.state.phase == RunPhase.UPGRADE
    else:
        begin_hero(engine, "h03", striker_d8=1, tools_d4=1)
    state_before = state_hash(engine.state)
    content_before = copy.deepcopy((engine.content.classes, engine.content.reactions, engine.content.balance))
    dice_before = copy.deepcopy(engine.content.dice)
    _scramble(snapshot(engine))
    assert state_hash(engine.state) == state_before
    assert (engine.content.classes, engine.content.reactions, engine.content.balance) == content_before
    assert engine.content.dice == dice_before
    assert snapshot(engine)["combatants"], "a fresh snapshot is complete again"


def test_replay_verify_checks_both_recorded_hashes():
    engine = _played()
    record = replay.export_run(engine)
    replay.verify(engine.content, record)
    for key, message in (("events_hash", "Event log hash differs"), ("final_state_hash", "Final state hash differs")):
        tampered = dict(record)
        tampered[key] = "0" * 64
        with pytest.raises(replay.ReplayError, match=message):
            replay.verify(engine.content, tampered)
    assert record["events_hash"] == events_hash(engine.events)


def test_an_unexpected_exception_inside_a_command_rolls_the_state_back(monkeypatch):
    engine = start("squire", seed=11)
    run_until_input(engine)
    before = (state_hash(engine.state), len(engine.events), len(engine.command_log), engine.revision)
    original = Engine._roll_die

    def roll_then_fail(self, *args, **kwargs):
        original(self, *args, **kwargs)  # the state and the event log are changed first ...
        raise RuntimeError("simulated fault after a partial change")

    monkeypatch.setattr(Engine, "_roll_die", roll_then_fail)
    with pytest.raises(RuntimeError, match="simulated fault"):
        engine.do(cmd.ROLL_DICE)
    assert (state_hash(engine.state), len(engine.events), len(engine.command_log), engine.revision) == before
    monkeypatch.undo()
    ok(engine.do(cmd.ROLL_DICE))  # and the engine is still usable


def test_a_plan_that_became_illegal_is_rejected_at_commit():
    engine = start("apprentice", seed=11)
    foe = enemies(engine)[0]
    begin_hero(engine, "h01", arcane_d6=1, focus_d4=4)  # Arcane Bolt (1 mana), blank
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("arcane_d6", foe.id)]))
    unit(engine, "h01").mana = 0  # arrange: the mana is gone before the commit
    before = state_hash(engine.state)
    rejected(engine.do(cmd.COMMIT_ACTION_PLAN), "mana")
    assert state_hash(engine.state) == before and not engine.combat.turn.committed


# --------------------------------------------------------------------------------------------
# Events that no test named before
# --------------------------------------------------------------------------------------------


def test_run_keep_plan_and_formation_events_carry_their_data():
    engine = start("squire", "scout", seed=6)
    started = last_event(engine, EventType.RUN_STARTED)
    assert started.seq == 1 and started.delta["rules_version"] == engine.state.rules_version
    begin_hero(engine, "h01", iron_d6=1, oath_d4=4)
    ok(engine.do(cmd.SET_KEPT_DICE, die_ids=["iron_d6"]))
    assert last_event(engine, EventType.DICE_KEPT).delta == {"kept": ["iron_d6"]}
    foe = enemies(engine)[0]
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[action("iron_d6", foe.id)]))
    planned = last_event(engine, EventType.PLAN_SET).delta["actions"]
    assert planned == [{"die_id": "iron_d6", "name": "Strike", "target_ids": [foe.id]}]


def test_upgrade_swap_and_formation_events_carry_their_data():
    engine = start("squire", "scout", seed=6)
    win_battle(engine)
    offers = last_event(engine, EventType.UPGRADE_OFFERS_GENERATED)
    assert offers.rng_stream == "rewards" or offers.delta, "offers are generated from the rewards stream"
    offer = engine.state.upgrade_offers["h01"]["iron_d6"][0]["offer_id"]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="iron_d6", offer_id=offer))
    ok(engine.do(cmd.SWAP_DIE, hero_id="h01", out_die_id="oath_d4", in_die_id="bulwark_d4"))
    swapped = last_event(engine, EventType.DIE_SWAPPED).delta
    assert (swapped["hero_id"], swapped["out_die_id"], swapped["in_die_id"]) == ("h01", "oath_d4", "bulwark_d4")
    ok(engine.do(cmd.SET_FORMATION, hero_id="h02", row="front"))
    moved = last_event(engine, EventType.FORMATION_CHANGED)
    assert moved.actor_id == "h02" and moved.delta["to"] == "front"
    rejected(engine.do(cmd.SET_FORMATION, hero_id="h02", row="middle"))
    rejected(engine.do(cmd.SET_FORMATION, hero_id="h09", row="front"))


# --------------------------------------------------------------------------------------------
# Content hash and content validation
# --------------------------------------------------------------------------------------------


def test_the_content_hash_changes_when_any_one_document_changes():
    shipped = load_documents()
    reference = build_content(copy.deepcopy(shipped)).content_hash
    assert build_content(copy.deepcopy(shipped)).content_hash == reference

    def changed(mutate) -> str:
        documents = copy.deepcopy(shipped)
        mutate(documents)
        return build_content(documents).content_hash

    hashes = {
        "balance": changed(lambda d: d["balance"]["shield"].__setitem__("cap", 11)),
        "classes": changed(lambda d: d["classes"]["classes"]["squire"].__setitem__("max_hp", 15)),
        "dice": changed(lambda d: d["dice"]["face_library"]["sq_strike_2"].__setitem__("name", "Slice")),
        "enemies": changed(lambda d: d["enemies"]["enemies"]["goblin"].__setitem__("max_hp", 7)),
        "encounters": changed(lambda d: d["encounters"]["encounters"]["1"][0]["enemies"][0]["overrides"].__setitem__("max_hp", 10)),
        "upgrades": changed(lambda d: d["upgrades"]["kinds"]["sharpen"].__setitem__("name", "Hone")),
    }
    assert reference not in hashes.values() and len(set(hashes.values())) == len(hashes)


def _face(documents, name="sq_strike_2"):
    return documents["dice"]["face_library"][name]


INVALID_CONTENT = [
    ("a die face with a reaction-only effect",
     lambda d: _face(d).__setitem__("effects", [{"type": "interrupt"}]), "which only a reaction can have"),
    ("an enemy action with a reaction-only effect",
     lambda d: d["enemies"]["enemies"]["goblin"]["actions"]["slash"].__setitem__("effects", [{"type": "interrupt"}]),
     "which only a reaction can have"),
    ("a status stack cap of zero",
     lambda d: d["balance"]["statuses"]["poison"].__setitem__("stack_cap", 0), "stack_cap"),
    ("a removed balance key coming back",
     lambda d: d["balance"]["statuses"]["poison"].__setitem__("default_duration", 2), "default_duration"),
    ("a stacking Speed Up",
     lambda d: d["balance"]["statuses"]["speed_up"].__setitem__("stack_cap", 2), "stack_cap"),
    ("the same die listed twice",
     lambda d: d["classes"]["classes"]["squire"].__setitem__("starting_dice", ["iron_d6", "iron_d6"]), "starting_dice"),
    ("a die both equipped and on the bench",
     lambda d: d["classes"]["classes"]["squire"].__setitem__("bench_dice", ["iron_d6"]), "same die more than once"),
    ("a revival that restores no HP",
     lambda d: _face(d, "sq_rally").__setitem__("power", 0), "would revive at 0 HP"),
    ("a misspelled tag",
     lambda d: d["enemies"]["enemies"]["goblin"]["actions"]["slash"].__setitem__("tags", ["basic", "interruptable", "hostile"]),
     "interruptable"),
    ("an executable face with no target scope",
     lambda d: d["enemies"]["enemies"]["goblin"]["actions"]["slash"].update({"target_scope": "none", "range_type": "none"}),
     "needs a target scope"),
    ("a reaction with an effect reactions do not implement",
     lambda d: d["classes"]["reactions"]["interpose"].__setitem__("effects", [{"type": "heal", "target": "target", "amount": 2}]),
     "which reactions do not implement"),
    ("a reaction shield without an amount",
     lambda d: d["classes"]["reactions"]["interpose"].__setitem__("effects", [{"type": "shield", "target": "target"}]),
     "needs an amount of at least 1"),
    ("an interrupt without its resisted values",
     lambda d: d["classes"]["reactions"]["disrupt"].__setitem__("effects", [{"type": "interrupt"}]),
     "resisted_damage_reduction"),
    ("overrides that leave an enemy with no weighted action",
     lambda d: d["encounters"]["encounters"]["1"][0]["enemies"][0].__setitem__(
         "overrides", {"actions": {"slash": {"weight": 0}, "dirty_trick": {"weight": 0}}}),
     "no action of positive weight"),
    ("a power override the action would ignore",
     lambda d: (d["enemies"]["enemies"]["goblin"]["actions"]["slash"].__setitem__(
         "effects", [{"type": "damage", "target": "target", "amount": 2}]),),
     "has an effect with its own amount"),
    ("a minimum speed above the maximum",
     lambda d: d["balance"]["timeline"].update({"min_speed": 50, "max_speed": 5}), "min_speed is above max_speed"),
    ("a minimum party size above the maximum",
     lambda d: d["balance"]["party"].update({"min_size": 4, "max_size": 2}), "min_size is above max_size"),
]


@pytest.mark.parametrize("label, mutate, fragment", INVALID_CONTENT, ids=[case[0] for case in INVALID_CONTENT])
def test_content_that_would_break_a_battle_is_rejected_before_a_run_can_start(label, mutate, fragment):
    documents = copy.deepcopy(load_documents())
    mutate(documents)
    with pytest.raises(ContentError) as error:
        build_content(documents)
    assert any(fragment in problem for problem in error.value.problems), error.value.problems


def test_no_balance_key_is_left_that_nothing_reads(content):
    assert content.balance["statuses"] == {
        "poison": {"stack_cap": 3, "damage_per_stack": 1},
        "weaken": {"stack_cap": 2, "damage_penalty_per_stack": 1},
        "speed_up": {"stack_cap": 1},
    }


# --------------------------------------------------------------------------------------------
# Reaction eligibility reasons that no test reached
# --------------------------------------------------------------------------------------------


def _reason(engine: Engine, stage: str, hero_id: str) -> str | None:
    from battle_dice.core import reactions

    return next(o["reason"] for o in reactions.stage_options(engine, stage) if o["hero_id"] == hero_id)


def test_a_second_interrupt_is_refused_once_the_action_is_cancelled():
    engine = start("squire", "scout", "scout")
    force_slash(engine)
    begin_enemy(engine, enemies(engine)[0].id)
    while engine.combat.phase != CombatPhase.INTERRUPT_WINDOW:
        ok(engine.do(cmd.SKIP_REACTION_STAGE))
    ok(engine.do(cmd.USE_REACTION, hero_id="h02"))  # Disrupt cancels the basic Slash
    assert last_event(engine, EventType.INTENT_CANCELLED).delta["by"] == "h02"
    if engine.combat.phase == CombatPhase.INTERRUPT_WINDOW:
        assert _reason(engine, "interrupt", "h03") == "The enemy action is already cancelled."
        rejected(engine.do(cmd.USE_REACTION, hero_id="h03"), "already cancelled")
    else:  # the window closed with the cancel: the reason is still what the rules report
        engine.combat.committed_intent.cancelled = True
        assert _reason(engine, "interrupt", "h03") == "The enemy action is already cancelled."


def test_an_unreactable_action_and_a_non_interruptible_one_say_why():
    engine = start("squire", "scout", content=captain_content(2))
    captain = enemies(engine)[0]
    make_ready(engine, captain.id)
    engine.force_draws("enemy", [roll_for(engine, captain.id, "war_cry")])
    step_to(engine, CombatPhase.REVEAL_INTENT)
    assert _reason(engine, "guard", "h01") == "This enemy action cannot be reacted to."
    assert _reason(engine, "interrupt", "h02") == "This enemy action cannot be reacted to."

    def mutate(documents):
        documents["enemies"]["enemies"]["goblin"]["actions"]["slash"]["tags"] = ["basic", "hostile"]

    plain = start("squire", "scout", content=content_with(mutate))
    force_slash(plain)
    begin_enemy(plain, enemies(plain)[0].id)
    assert _reason(plain, "interrupt", "h02") == "The enemy action is not interruptible."
    assert _reason(plain, "guard", "h01") is None, "it still deals damage, so Interpose is allowed"


# --------------------------------------------------------------------------------------------
# Class scheduling is its own rule, not a side effect of action speed (AC-02, AC-07)
# --------------------------------------------------------------------------------------------


def test_class_order_wins_even_when_action_speed_says_the_opposite():
    """In the shipped data the two orders happen to agree, so reverse the speeds to tell them apart."""

    def mutate(documents):
        faces = documents["dice"]["face_library"]
        faces["sc_poison"]["action_speed"] = 1  # the Status is now the "slower" action ...
        faces["sc_shot_1"]["action_speed"] = 3  # ... and the Attack the "faster" one

    engine = start("scout", "squire", content=content_with(mutate))
    foe = enemies(engine)[0]
    begin_hero(engine, "h01", striker_d8=4, tools_d4=1)  # Poison and Quick Shot
    for drafted in ([action("tools_d4", foe.id), action("striker_d8", foe.id)],
                    [action("striker_d8", foe.id), action("tools_d4", foe.id)]):
        intents, problem = engine.preview_plan(drafted)
        assert problem is None
        assert [i.category for i in intents] == ["status", "attack"], "Exploit Combo: Status first, then Attack"
    hp = foe.hp
    resolve_hero(engine, action("tools_d4", foe.id), action("striker_d8", foe.id))
    resolved = [e.delta for e in events_of(engine, EventType.ACTION_RESOLVED)][-2:]
    assert [r["name"] for r in resolved] == ["Poison", "Quick Shot"]
    damage = resolved[1]["results"][0]
    assert damage["bonus"] == 1 and unit(engine, foe.id).hp == hp - 2, "Exploit Opening: +1 because the Status resolved first"
