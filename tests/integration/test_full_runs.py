"""Integration: complete two-battle runs, invariants after every command, both outcomes (AC-17)."""

from __future__ import annotations

import pytest

from battle_dice.core import commands as cmd
from battle_dice.core.engine import Engine
from battle_dice.core.models import CombatPhase, RunPhase
from battle_dice.core.view import combat_log, snapshot
from battle_dice.sim.policies import HeuristicPolicy, RandomPolicy
from battle_dice.sim.runner import compositions, simulate
from tests.conftest import ok, party_spec, start

CLASSES = ["squire", "apprentice", "scout"]


def check_invariants(engine: Engine) -> None:
    balance = engine.content.balance
    combat = engine.combat
    for c in combat.combatants.values():
        assert 0 <= c.hp <= c.max_hp, c
        assert 0 <= c.shields <= balance["shield"]["cap"], c
        assert 0 <= c.mana <= c.max_mana, c
        assert 0 <= c.corruption <= c.max_corruption, c
        assert c.gauge >= 0, c
        assert 0 <= c.reaction_charges <= balance["reactions"]["charges_per_activation"], c
        assert (c.hp == 0) == (c.state != "standing"), c
        for kind in ("poison", "weaken", "speed_up"):
            assert len(c.instances_of(kind)) <= balance["statuses"][kind]["stack_cap"], c
        assert all(s.remaining_target_activations > 0 for s in c.status_instances), c
        if c.is_hero:
            assert len(c.equipped_dice_ids) == engine.content.class_def(c.archetype_id)["dice_capacity"]
    if combat.turn is not None:
        assert 0 <= combat.turn.rerolls_remaining <= 2
    assert len(engine.state.upgrades) <= 1
    hero_ids = {member["id"] for member in engine.state.party}
    assert set(engine.state.swaps_used) <= hero_ids
    assert all(0 < used <= balance["upgrades"]["max_swaps_per_hero"] for used in engine.state.swaps_used.values())


def play_checked(engine: Engine, policy, limit: int = 20000) -> str:
    commands = 0
    while not engine.finished():
        commands += 1
        assert commands < limit, "run did not terminate"
        if engine.needs_input():
            policy.act(engine)
        else:
            ok(engine.do(cmd.ADVANCE_PHASE))
        check_invariants(engine)
    return engine.state.outcome


@pytest.mark.parametrize("seed", range(25))
def test_random_play_never_corrupts_state_or_soft_locks(seed):
    size = seed % 5 + 1
    party = [f"{CLASSES[(seed + i) % 3]}:{'front' if (seed + i) % 2 else 'back'}" for i in range(size)]
    engine = start(*party, seed=seed)
    outcome = play_checked(engine, RandomPolicy(seed))
    assert outcome in ("victory", "defeat")
    assert snapshot(engine)["run_outcome"] == outcome


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5])
def test_informed_play_completes_two_battles_for_every_party_size(content, size):
    class_ids = [CLASSES[i % 3] for i in range(size)]
    engine = Engine(content)
    ok(engine.do(cmd.START_RUN, seed=900 + size, party=party_spec(*class_ids)))
    outcome = play_checked(engine, HeuristicPolicy())
    assert outcome in ("victory", "defeat")
    if outcome == "victory":
        assert engine.state.encounter_index == 1 and len(engine.state.upgrades) == 1
    log = combat_log(engine)
    assert log[0] == "--- Battle 1 begins ---"
    assert any(line.startswith("*** Battle") for line in log)


class PassPolicy:
    """Rolls and always passes; never reacts. A legal but hopeless player."""

    def act(self, engine: Engine) -> None:
        phase = engine.combat.phase
        if phase == CombatPhase.HERO_ROLL:
            ok(engine.do(cmd.ROLL_DICE))
        elif phase == CombatPhase.KEEP_REROLL:
            ok(engine.do(cmd.SET_ACTION_PLAN, actions=[]))
        elif phase == CombatPhase.ACTION_PLAN:
            ok(engine.do(cmd.COMMIT_ACTION_PLAN))
        else:
            ok(engine.do(cmd.SKIP_REACTION_STAGE))


@pytest.mark.parametrize("size", [1, 3, 5])
def test_a_full_run_can_end_in_defeat_without_undefined_states(size):
    engine = start(*[CLASSES[i % 3] for i in range(size)], seed=size)
    assert play_checked(engine, PassPolicy()) == "defeat"
    assert engine.state.phase == RunPhase.DEFEAT and engine.state.encounter_index == 0
    assert all(not h.standing for h in engine.combat.side("hero"))


def test_a_full_run_can_end_in_victory(content):
    result = simulate(content, 3, ["squire", "apprentice", "scout"], HeuristicPolicy())
    assert result["outcome"] == "victory" and result["battle_reached"] == 2
    assert result["stats"]["enemies_defeated"] == 6  # 3 in each battle


def test_every_composition_is_enumerated_for_the_seed_matrix(content):
    assert [len([c for c in compositions(content, [n])]) for n in (1, 2, 3, 4, 5)] == [3, 6, 10, 15, 21]


def test_snapshot_is_available_in_every_phase_of_a_run(content):
    engine = Engine(content)
    assert snapshot(engine) == {"started": False, "permissible_commands": [cmd.START_RUN], "revision": 0}
    ok(engine.do(cmd.START_RUN, seed=2, party=party_spec("squire", "apprentice", "scout")))
    policy = HeuristicPolicy()
    seen = set()
    while not engine.finished():
        view = snapshot(engine)
        seen.add((view["run_phase"], view["combat_phase"]))
        assert view["revision"] == engine.revision
        assert view["needs_input"] == engine.needs_input()
        if engine.needs_input():
            policy.act(engine)
        else:
            ok(engine.do(cmd.ADVANCE_PHASE))
    final = snapshot(engine)
    assert final["run_outcome"] in ("victory", "defeat") and final["permissible_commands"] == []
    phases = {combat_phase for run_phase, combat_phase in seen if run_phase == "battle"}
    assert {CombatPhase.ADVANCE_TIMELINE, CombatPhase.ACTOR_START, CombatPhase.HERO_ROLL, CombatPhase.KEEP_REROLL,
            CombatPhase.ACTION_PLAN, CombatPhase.LOCK_PLAN, CombatPhase.ACTION_RESOLVE, CombatPhase.ENEMY_INTENT,
            CombatPhase.REVEAL_INTENT, CombatPhase.ENEMY_RESOLVE, CombatPhase.ACTOR_END,
            CombatPhase.TERMINAL_CHECK} <= phases


def test_simulator_matrix_is_identical_for_any_job_count_and_accepts_a_content_dir(content, tmp_path):
    import json

    from battle_dice.content.loader import load_documents
    from battle_dice.sim.runner import main, run_matrix

    serial = run_matrix(content, [0, 1], [1], "heuristic")
    parallel = run_matrix(content, [0, 1], [1], "heuristic", jobs=2)
    for key in ("overall", "by_party_size", "by_composition", "content_hash"):
        assert serial[key] == parallel[key]
    assert serial["overall"]["runs"] == 6 and sum(v["runs"] for v in serial["by_composition"].values()) == 6

    # A candidate fixture set in a folder is validated and measured without touching the packaged content.
    documents = load_documents()
    documents["encounters"]["encounters"]["1"][0]["enemies"][0]["overrides"] = {"max_hp": 60}
    for name, document in documents.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(document), encoding="utf-8")
    out = tmp_path / "result.json"
    assert main(["--seeds", "1", "--sizes", "1", "--content-dir", str(tmp_path), "--out", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["content_hash"] != content.content_hash and result["content_dir"] == str(tmp_path)
    assert result["overall"]["runs"] == 3
