"""The link between a run and the saved careers of its heroes (Class Evolution Phase 4, step C).

Until now a test had to hand a run's results to the career rules itself. ``app.progression`` does
it: the party from saved heroes with build snapshots, a mastery award per hero and battle, the
run's phase, and its end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from battle_dice.app.progression import PROFILE_ID, SAVE_FILE, Progression
from battle_dice.content.vocations import VocationCatalog, load_vocation_catalog
from battle_dice.core import commands as cmd
from battle_dice.core.engine import Engine
from battle_dice.core.models import RunPhase
from battle_dice.sim.career import play_saved_run, runs_to_master
from battle_dice.sim.policies import HeuristicPolicy
from tests.conftest import ok, packaged_content, win_battle

PARTY = [("hero_001", "front"), ("hero_002", "back")]


@pytest.fixture(scope="module")
def vocations() -> VocationCatalog:
    return load_vocation_catalog(packaged_content())


def opened(folder: Path) -> Progression:
    ticks = iter(range(100000))
    return Progression(folder, packaged_content(), clock=lambda: f"2026-11-12T10:{next(ticks) // 60 % 60:02d}:00Z")


@pytest.fixture()
def progression(tmp_path: Path):
    link = opened(tmp_path)
    assert link.recruit("squire").accepted and link.recruit("scout").accepted
    yield link
    link.close()


def start(link: Progression, vocations: VocationCatalog, seed: int = 11, third: bool = True) -> Engine:
    engine = Engine(packaged_content(), vocations)
    params = {"seed": seed, "run_id": link.next_run_id(seed), "party": [link.party_entry(h, row) for h, row in PARTY]}
    if third:
        params["encounters"] = link.extra_encounters()
    ok(engine.do(cmd.START_RUN, **params))
    link.run_started(engine)
    return engine


def test_the_save_is_made_on_first_use_and_found_again(tmp_path: Path):
    first = opened(tmp_path)
    assert first.path == tmp_path / SAVE_FILE and first.path.is_file() and first.roster() == []
    assert first.recruit("apprentice").accepted
    first.close()
    again = opened(tmp_path)
    assert [(row["hero_id"], row["name"], row["vocation_name"], row["rank"], row["points_for_next_rank"]) for row in again.roster()] == [
        ("hero_001", "Apprentice 1", "Apprentice", 1, 1)]
    assert again.store.profile_ids() == [PROFILE_ID] and again.extra_encounters() == ["training_04"]
    again.close()


def test_a_party_entry_is_the_heros_vocation_with_its_build_snapshot(progression: Progression):
    assert progression.party_entry("hero_001", "front") == {
        "class_id": "squire", "row": "front",
        "hero": {"hero_id": "hero_001", "name": "Squire 1", "stats": {"max_hp": 14, "max_mana": 3, "speed": 7}, "skills": []}}


def test_each_battle_awards_mastery_to_each_saved_hero_by_the_rules(progression: Progression, vocations):
    engine = start(progression, vocations)
    run_id = engine.state.run_id
    assert run_id == "run-0001-11" and progression.state.run is not None and progression.state.run.phase == "battle"
    win_battle(engine)
    awards = progression.sync(engine)
    # Battle 1 is threat 1: enough for a rank 1 starting class. One point each, no bonus without evidence.
    assert [(a["hero_id"], a["encounter_id"], a["threat_rating"], a["base_points"], a["denial_reason"], a["rank_before"], a["rank_after"])
            for a in awards] == [("hero_001", "training_01", 1, 1, None, 1, 2), ("hero_002", "training_01", 1, 1, None, 1, 2)]
    assert progression.sync(engine) == [] and len(progression.last_awards) == 2  # nothing is awarded twice
    assert progression.state.run.phase == "upgrade"
    offer = next(o for dice in engine.state.upgrade_offers.values() for die in dice.values() for o in die)
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id=offer["hero_id"], die_id=offer["die_id"], offer_id=offer["offer_id"]))
    progression.sync(engine)
    assert progression.state.run.phase == "equipment"
    ok(engine.do(cmd.ADVANCE_PHASE))
    win_battle(engine)
    second = progression.sync(engine)
    assert [(a["encounter_id"], a["threat_rating"], a["base_points"], a["rank_after"]) for a in second] == [("training_03", 3, 1, 3)] * 2
    # The run waits for "stop or fight on": the save calls that phase equipment (every build is fixed).
    assert engine.state.phase == RunPhase.CONTINUE and progression.state.run.phase == "equipment"
    ok(engine.do(cmd.END_RUN))
    assert progression.sync(engine) == []
    run = progression.state.run
    assert (run.run_id, run.phase) == (run_id, "victory")
    saved = progression.store.conn.execute("SELECT run_id, phase, completed_at IS NOT NULL FROM run").fetchall()
    assert saved == [(run_id, "victory", 1)]
    rows = progression.store.conn.execute("SELECT encounter_id, hero_id, base_points FROM mastery_award_event ORDER BY rowid").fetchall()
    assert rows == [("training_01", "hero_001", 1), ("training_01", "hero_002", 1), ("training_03", "hero_001", 1), ("training_03", "hero_002", 1)]
    assert progression.store.verify_event_chain(PROFILE_ID) == 8 + 4  # two recruits, four awards


def test_a_lost_battle_is_recorded_with_its_reason_and_ends_the_run_in_the_save(progression: Progression, vocations):
    engine = start(progression, vocations, third=False)
    for hero in engine.combat.side("hero"):  # arranged: a party that cannot survive
        hero.hp, hero.shields, hero.mana = 1, 0, 0
    policy = HeuristicPolicy()
    while not engine.finished():
        policy.act(engine) if engine.needs_input() else engine.do(cmd.ADVANCE_PHASE)
    awards = progression.sync(engine)
    assert engine.state.outcome == "defeat"
    assert [(a["outcome"], a["base_points"], a["denial_reason"], a["rank_after"]) for a in awards] == [("defeat", 0, "ENCOUNTER_NOT_WON", 1)] * 2
    assert progression.state.run.phase == "defeat" and progression.roster()[0]["points"] == 0


def test_every_run_gets_an_id_the_save_has_not_seen_and_an_abandoned_run_is_closed(progression: Progression, vocations):
    first = start(progression, vocations, seed=5)
    assert first.state.run_id == "run-0001-5"
    # The player leaves the run and starts another with the same seed.
    second = start(progression, vocations, seed=5)
    assert second.state.run_id == "run-0002-5"
    saved = progression.store.conn.execute("SELECT run_id, phase FROM run ORDER BY rowid").fetchall()
    assert saved == [("run-0001-5", "defeat"), ("run-0002-5", "battle")]
    assert progression.sync(first) == []  # the abandoned run has nothing more to say


def test_the_run_phase_reaches_the_career_rules_so_their_locks_hold(progression: Progression, vocations):
    engine = start(progression, vocations)
    assert progression.change("hero_001", "scout").error_code == "PHASE_LOCKED"  # in a battle
    assert progression.recruit("scout").error_code == "PHASE_LOCKED"
    win_battle(engine)
    progression.sync(engine)
    # After recovery and before the upgrade a hero may change vocation (decision CE-19): the career rules allow it.
    hero = progression.state.heroes["hero_001"]
    assert progression.state.run.phase == "upgrade" and hero.revision == 1  # the award raised the revision
    assert progression.preview("hero_001", "scout").accepted


def test_the_run_report_is_refused_when_there_is_no_run_or_it_is_over(progression: Progression, vocations):
    with pytest.raises(ValueError, match="no run in progress"):
        progression.career.report_run("battle", 1)
    engine = start(progression, vocations)
    with pytest.raises(ValueError, match="finished with end_run"):
        progression.career.report_run("victory", engine.state.revision)
    before = progression.store.conn.execute("SELECT phase, revision FROM run").fetchall()
    progression.career.report_run("battle", progression.state.run.revision)  # nothing new: nothing is written
    assert progression.store.conn.execute("SELECT phase, revision FROM run").fetchall() == before
    progression.career.end_run(engine.state.run_id, "defeat")
    with pytest.raises(ValueError, match="no run in progress"):
        progression.career.report_run("battle", 99)


def test_a_hero_without_a_snapshot_earns_nothing(progression: Progression, vocations):
    engine = Engine(packaged_content(), vocations)
    party = [progression.party_entry("hero_001", "front"), {"class_id": "scout", "row": "back"}]
    ok(engine.do(cmd.START_RUN, seed=3, party=party, run_id=progression.next_run_id(3)))
    progression.run_started(engine)
    win_battle(engine)
    assert [a["hero_id"] for a in progression.sync(engine)] == ["hero_001"]
    assert progression.state.heroes["hero_002"].mastery["scout"].points == 0


def test_a_squire_is_mastered_becomes_a_guardian_and_plays_on(progression: Progression, vocations):
    """The whole loop of the first slice, by the simulated player, through the save file."""
    content = packaged_content()
    result = runs_to_master(progression, content, vocations, PARTY, "hero_001", first_seed=1001)
    assert result["vocation_id"] == "squire" and 4 <= result["runs"] <= 14, result  # 14 points; up to 4 a run with the bonus
    hero = progression.state.heroes["hero_001"]
    assert (hero.mastery["squire"].rank, hero.mastery["squire"].points) == (8, 14)
    assert progression.claim("hero_001", "guardian").accepted and progression.change("hero_001", "guardian").accepted
    entry = progression.party_entry("hero_001", "front")
    assert entry["class_id"] == "guardian" and entry["hero"]["stats"]["max_hp"] == 17 + 1  # mastering the Squire gave +1 health
    played = play_saved_run(progression, content, vocations, PARTY, seed=2001)
    engine = played["engine"]
    assert engine.build("h01").vocation_id == "guardian" and engine.combat.combatants["h01"].max_hp == 18
    guardian_awards = [a for a in played["awards"] if a["hero_id"] == "hero_001"]
    assert guardian_awards and all(a["vocation_id"] == "guardian" for a in guardian_awards)
    # An advanced vocation at rank 1 needs threat 2: battle 1 (threat 1) records a zero award with the reason.
    assert (guardian_awards[0]["encounter_id"], guardian_awards[0]["denial_reason"]) == ("training_01", "UNDER_THREAT_CAP")
    assert progression.store.verify_event_chain(PROFILE_ID) > 12
    tree = progression.tree("hero_001")["career_tree"]["entries"]
    assert next(e for e in tree if e.get("vocation_id") == "guardian")["active"] is True
