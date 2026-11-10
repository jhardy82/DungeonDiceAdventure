"""Command envelope, transactional rejection and idempotency (section 14.4; AC-01, AC-04)."""

from __future__ import annotations

import pytest

from battle_dice.core import commands as cmd
from battle_dice.core.commands import Command
from battle_dice.core.engine import Engine, run_until_input
from battle_dice.core.events import state_hash
from battle_dice.core.models import CombatPhase, RunPhase
from tests.conftest import begin_hero, ok, party_spec, rejected, start


def fingerprint(engine: Engine) -> tuple:
    state = engine.state
    return (state_hash(state), len(engine.events), state.revision, {k: v.draws for k, v in state.rng.items()})


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5])
def test_any_legal_party_size_with_duplicates_and_rows(content, size):
    engine = Engine(content)
    party = [{"class_id": "scout", "row": "front" if i % 2 else "back"} for i in range(size)]
    ok(engine.do(cmd.START_RUN, seed=5, party=party))
    heroes = engine.combat.side("hero")
    assert [h.id for h in heroes] == [f"h{i:02d}" for i in range(1, size + 1)]
    assert [h.row for h in heroes] == [m["row"] for m in party]
    assert all(h.archetype_id == "scout" for h in heroes)


@pytest.mark.parametrize("size", [0, 6, 9])
def test_illegal_party_size_is_rejected(content, size):
    engine = Engine(content)
    rejected(engine.do(cmd.START_RUN, seed=5, party=party_spec(*["squire"] * size)), "party size")
    assert not engine.started and engine.events == []


def test_unknown_class_bad_row_and_bad_seed_are_rejected(content):
    engine = Engine(content)
    rejected(engine.do(cmd.START_RUN, seed=1, party=[{"class_id": "wizard", "row": "front"}]), "unknown class")
    rejected(engine.do(cmd.START_RUN, seed=1, party=[{"class_id": "squire", "row": "middle"}]), "row")
    rejected(engine.do(cmd.START_RUN, seed=-1, party=party_spec("squire")), "64-bit")
    rejected(engine.do(cmd.START_RUN, seed=2**64, party=party_spec("squire")), "64-bit")
    assert not engine.started


def test_second_start_run_is_rejected():
    engine = start("squire")
    rejected(engine.do(cmd.START_RUN, seed=2, party=party_spec("scout")), "already in progress")


@pytest.mark.parametrize(
    "command, fragment",
    [
        (Command("Explode", "x1", 0), "unknown command"),
        (Command(cmd.START_RUN, "", 0, {"seed": 1, "party": []}), "command_id"),
        (Command(cmd.START_RUN, "x1", -1, {"seed": 1, "party": []}), "state_revision"),
        (Command(cmd.START_RUN, "x1", 0, {"party": []}), "requires parameter 'seed'"),
        (Command(cmd.START_RUN, "x1", 0, {"seed": "1", "party": []}), "must be an integer"),
        (Command(cmd.START_RUN, "x1", 0, {"seed": True, "party": []}), "must be an integer"),
        (Command(cmd.START_RUN, "x1", 0, {"seed": 1, "party": [{"class_id": "squire"}]}), "party must be"),
        (Command(cmd.START_RUN, "x1", 0, {"seed": 1, "party": [], "cheat": 1}), "does not accept"),
        (Command(cmd.SET_KEPT_DICE, "x1", 0, {"die_ids": "iron_d6"}), "list of strings"),
        (Command(cmd.SET_ACTION_PLAN, "x1", 0, {"actions": [{"die": "iron_d6"}]}), "actions must be"),
        (Command(cmd.USE_REACTION, "x1", 0, {"hero_id": 3}), "must be a string"),
    ],
)
def test_malformed_commands_are_rejected_before_any_handler_runs(content, command, fragment):
    engine = Engine(content)
    rejected(engine.submit(command), fragment)
    assert not engine.started


def test_stale_revision_is_rejected_without_side_effects():
    engine = start("squire")
    before = fingerprint(engine)
    rejected(engine.submit(Command(cmd.ADVANCE_PHASE, "stale-1", engine.revision + 3)), "stale")
    rejected(engine.submit(Command(cmd.ADVANCE_PHASE, "stale-2", engine.revision - 1)), "stale")
    assert fingerprint(engine) == before


def test_duplicate_command_id_has_no_second_effect():
    engine = start("squire")
    command = Command(cmd.ADVANCE_PHASE, "advance-once", engine.revision)
    first = ok(engine.submit(command))
    after = fingerprint(engine)
    replayed = engine.submit(command)
    assert replayed.accepted and replayed.duplicate and not first.duplicate
    assert fingerprint(engine) == after
    assert len(engine.command_log) == 2  # StartRun + one AdvancePhase


def test_rejected_command_leaves_state_rng_and_event_sequence_unchanged():
    engine = start("squire", seed=3)
    run_until_input(engine)
    while engine.combat.phase != CombatPhase.HERO_ROLL:
        engine.do(cmd.SET_ACTION_PLAN, actions=[])
        engine.do(cmd.COMMIT_ACTION_PLAN)
        run_until_input(engine)
    # The second forced draw is out of range for a d4, so the roll fails after the first die was rolled.
    engine.force_draws("dice", [0, 7])
    before = fingerprint(engine)
    forced_before = list(engine.state.forced_draws["dice"])
    rejected(engine.do(cmd.ROLL_DICE), "forced draw")
    assert fingerprint(engine) == before
    assert engine.state.forced_draws["dice"] == forced_before
    assert engine.combat.turn is not None and engine.combat.turn.rolled == {}
    assert engine.combat.phase == CombatPhase.HERO_ROLL


def test_wrong_phase_commands_are_rejected():
    engine = start("squire")
    before = fingerprint(engine)
    rejected(engine.do(cmd.ROLL_DICE), "not allowed during")
    rejected(engine.do(cmd.REROLL_UNKEPT), "not allowed during")
    rejected(engine.do(cmd.COMMIT_ACTION_PLAN), "not allowed during")
    rejected(engine.do(cmd.USE_REACTION, hero_id="h01"), "not allowed during")
    rejected(engine.do(cmd.SKIP_REACTION_STAGE), "not allowed during")
    rejected(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="iron_d6", offer_id="x"), "after winning battle 1")
    rejected(engine.do(cmd.SWAP_DIE, hero_id="h01", out_die_id="oath_d4", in_die_id="bulwark_d4"), "between battles")
    rejected(engine.do(cmd.SET_FORMATION, hero_id="h01", row="back"), "not during combat")
    assert fingerprint(engine) == before


def test_advance_phase_is_rejected_while_waiting_for_input():
    engine = start("squire")
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    assert engine.needs_input()
    rejected(engine.do(cmd.ADVANCE_PHASE), "waiting for player input")


def test_permissible_commands_follow_the_phase(content):
    engine = Engine(content)
    assert engine.permissible_commands() == [cmd.START_RUN]
    ok(engine.do(cmd.START_RUN, seed=1, party=party_spec("squire")))
    assert engine.permissible_commands() == [cmd.ADVANCE_PHASE]
    begin_hero(engine, "h01", iron_d6=1, oath_d4=1)
    assert engine.permissible_commands() == [cmd.SET_KEPT_DICE, cmd.REROLL_UNKEPT, cmd.SET_ACTION_PLAN]
    ok(engine.do(cmd.SET_ACTION_PLAN, actions=[]))
    assert engine.permissible_commands() == [cmd.SET_ACTION_PLAN, cmd.COMMIT_ACTION_PLAN]
    assert engine.state.phase == RunPhase.BATTLE


def test_command_round_trips_through_its_dict_form():
    command = Command(cmd.SET_KEPT_DICE, "k1", 4, {"die_ids": ["iron_d6"]})
    assert Command.from_dict(command.to_dict()) == command


def test_commands_before_start_run_are_rejected_not_raised(content):
    engine = Engine(content)
    for command_type in (cmd.ROLL_DICE, cmd.ADVANCE_PHASE, cmd.COMMIT_ACTION_PLAN, cmd.SKIP_REACTION_STAGE):
        rejected(engine.do(command_type), "no run has been started")
    assert not engine.started and engine.events == [] and engine.command_log == []
