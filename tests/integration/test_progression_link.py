"""The link between a run and the saved careers of its heroes (Class Evolution Phase 4, step C).

Until now a test had to hand a run's results to the career rules itself. ``app.progression`` does
it: the party from saved heroes with build snapshots, a mastery award per hero and battle, the
run's phase, and its end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from battle_dice import settings
from battle_dice.app.progression import PACES, PRESETS, PROFILE_ID, SAVE_FILE, Progression, with_pace
from battle_dice.content.vocations import VocationCatalog, load_catalog, load_vocation_catalog
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


# --------------------------------------------------------------------------------------------
# The demo's tuning: mastery pace, roster size, and what a new profile starts with
# --------------------------------------------------------------------------------------------


def test_a_faster_pace_asks_for_fewer_points_and_never_for_fewer_ranks():
    raw = load_catalog()
    normal, fast, very_fast = (with_pace(raw, pace)["mastery"]["rank_thresholds_by_group"] for pace in ("normal", "fast", "very_fast"))
    assert with_pace(raw, "normal") is raw, "the normal pace is the catalog itself"
    assert normal["novice"] == [0, 1, 2, 3, 5, 7, 10, 14] and fast["novice"] == [0, 1, 2, 3, 4, 5, 6, 7]
    assert normal["advanced"] == [0, 2, 4, 7, 10, 14, 18, 24] and fast["advanced"] == [0, 1, 2, 4, 5, 7, 9, 12]
    assert very_fast["advanced"] == very_fast["novice"] == [0, 1, 2, 3, 4, 5, 6, 7]  # a rank per point is the fastest there is
    for table in (fast, very_fast):
        for group, thresholds in table.items():
            assert len(thresholds) == 8 and thresholds[0] == 0 and all(a < b for a, b in zip(thresholds, thresholds[1:], strict=False)), group
            assert all(mine <= theirs for mine, theirs in zip(thresholds, normal[group], strict=True))
    assert raw["mastery"]["rank_thresholds_by_group"]["novice"] == [0, 1, 2, 3, 5, 7, 10, 14], "the catalog itself is not altered"
    assert PACES == settings.PACES and PRESETS == settings.PRESETS, "the settings offer exactly what the save link knows"


@pytest.mark.parametrize(("preset", "heroes", "first"), [
    ("fresh", 0, None),
    ("squire_near_mastery", 3, ("squire", 7, 13, ["squire", "apprentice", "scout"])),
    ("guardian_unlocked", 3, ("guardian", 1, 0, ["squire", "apprentice", "scout", "guardian"])),
    ("guardian_mastered", 3, ("guardian", 8, 24, ["squire", "apprentice", "scout", "guardian"])),
])
def test_a_new_profile_starts_as_its_preset_says(tmp_path: Path, preset, heroes, first):
    link = Progression(tmp_path, packaged_content(), preset=preset, clock=lambda: "2026-11-12T10:00:00Z")
    assert len(link.state.heroes) == heroes
    if first is not None:
        hero = link.state.heroes["hero_001"]
        active, rank, points, unlocked = first
        assert (hero.active_vocation_id, hero.mastery[active].rank, hero.mastery[active].points, hero.unlocked_vocations) == (active, rank, points, unlocked)
        assert [h.active_vocation_id for h in link.state.heroes.values()][1:] == ["scout", "apprentice"]
        assert ("guardian_field_medic" in hero.learned_skills) == (preset == "guardian_mastered")
        # The mastered Guardian starts with its skill equipped, so the demo shows it working at once.
        assert hero.equipped_skills == ({0: "guardian_field_medic"} if preset == "guardian_mastered" else {})
        # Handed-out mastery is in the event log under its own name, with its reason.
        granted = link.store.conn.execute("SELECT event_json FROM progression_event_log WHERE event_type = 'MasteryGranted'").fetchall()
        assert granted and all(f"demo preset {preset}" in row[0] for row in granted)
    link.store.verify_event_chain(PROFILE_ID)
    link.close()
    # The preset is for a new profile only: opening the save again with another preset changes nothing.
    again = Progression(tmp_path, packaged_content(), preset="guardian_mastered")
    assert len(again.state.heroes) == heroes and (first is None or again.state.heroes["hero_001"].mastery[first[0]].points == first[2])
    if preset == "guardian_mastered":
        assert again.state.heroes["hero_001"].equipped_skills == {0: "guardian_field_medic"}, "an equipped skill is saved"
    again.close()


def test_an_unknown_preset_is_refused_and_leaves_no_half_made_profile_open(tmp_path: Path):
    with pytest.raises(ValueError, match="Unknown start preset 'everything'"):
        Progression(tmp_path, packaged_content(), preset="everything")
    with pytest.raises(ValueError, match="Unknown mastery pace 'instant'"):
        Progression(tmp_path, packaged_content(), mastery_pace="instant")
    assert not (tmp_path / SAVE_FILE).exists(), "a wrong name is refused before any file is made"


def test_changing_the_pace_re_ranks_the_heroes_from_their_points_and_says_so_in_the_log(tmp_path: Path, vocations):
    link = Progression(tmp_path, packaged_content(), preset="squire_near_mastery")
    assert link.state.heroes["hero_001"].mastery["squire"].rank == 7  # 13 of 14 points
    link.close()
    fast = Progression(tmp_path, packaged_content(), mastery_pace="fast")
    hero = fast.state.heroes["hero_001"]
    assert (hero.mastery["squire"].rank, hero.mastery["squire"].points) == (8, 13)  # 13 points are more than the 7 a fast pace asks
    events = fast.store.conn.execute("SELECT event_json FROM progression_event_log WHERE event_type = 'RanksRederived'").fetchall()
    assert len(events) == 1 and "mastery pace fast" in events[0][0] and '"from":7' in events[0][0] and '"to":8' in events[0][0]
    assert fast.claim("hero_001", "guardian").accepted, "a Squire mastered at the faster pace can become a Guardian"
    fast.close()
    # Opened again at the same pace nothing is re-derived, so no second event is written.
    same = Progression(tmp_path, packaged_content(), mastery_pace="fast")
    assert same.store.conn.execute("SELECT COUNT(*) FROM progression_event_log WHERE event_type = 'RanksRederived'").fetchone()[0] == 1
    same.close()
    # Back at the normal pace the rank follows the points again; what was claimed stays claimed.
    normal = Progression(tmp_path, packaged_content())
    hero = normal.state.heroes["hero_001"]
    assert hero.mastery["squire"].rank == 7 and "guardian" in hero.unlocked_vocations
    normal.store.verify_event_chain(PROFILE_ID)
    normal.close()


def test_a_faster_pace_masters_a_squire_in_fewer_runs(tmp_path: Path, vocations):
    content = packaged_content()
    runs = {}
    for pace in ("normal", "very_fast"):
        link = Progression(tmp_path / pace, content, mastery_pace=pace)
        assert link.recruit("squire").accepted and link.recruit("scout").accepted
        runs[pace] = runs_to_master(link, content, vocations, PARTY, "hero_001", first_seed=1001)["runs"]
        link.close()
    assert runs["very_fast"] < runs["normal"] and runs["very_fast"] <= 4, runs


def test_the_roster_size_is_a_setting(tmp_path: Path):
    link = Progression(tmp_path, packaged_content(), roster_limit=2)
    assert link.recruit("squire").accepted and link.recruit("scout").accepted
    full = link.recruit("scout")
    assert (full.error_code, full.error_details) == ("ROSTER_FULL", {"roster_limit": 2, "heroes": 2})
    link.close()


# --------------------------------------------------------------------------------------------
# Skills (Phase 4, step E)
# --------------------------------------------------------------------------------------------


@pytest.fixture()
def medic(tmp_path: Path):
    """A new profile with a mastered Guardian (Field Medic equipped), a Scout and an Apprentice."""
    link = Progression(tmp_path, packaged_content(), preset="guardian_mastered", clock=lambda: "2026-11-12T10:00:00Z")
    yield link
    link.close()


def test_the_skills_of_a_hero_say_what_is_equipped_and_why_another_cannot_be(medic: Progression):
    view = medic.skills("hero_001")
    assert (view["capacity"], view["used"], view["vocation_name"]) == (4, 0, "Guardian")
    assert [row["skill_id"] for row in view["rows"]] == ["squire_anchor", "guardian_field_medic"]
    anchor, field_medic = view["rows"]
    assert (field_medic["name"], field_medic["taught_by"], field_medic["cost"], field_medic["equipped"], field_medic["slot_index"]) == (
        "Guardian Field Medic", "Guardian", 0, True, 0)
    assert field_medic["in_battle"] and field_medic["problem"] is None
    assert (anchor["taught_by"], anchor["cost"], anchor["equipped"], anchor["slot_index"], anchor["in_battle"]) == ("Squire", 1, False, None, False)
    assert anchor["problem"] == "Not in this version yet: the rules of battle do not know this skill."
    assert medic.skills("hero_002") == {"capacity": 2, "used": 0, "vocation_name": "Scout", "rows": []}


def test_a_skill_is_taken_off_and_put_back_in_the_first_free_slot(medic: Progression):
    hero = medic.state.heroes["hero_001"]
    assert medic.unequip_skill("hero_001", "guardian_field_medic").accepted and hero.equipped_skills == {}
    assert medic.skills("hero_001")["rows"][1]["problem"] is None, "a learned skill that fits can be equipped"
    assert medic.unequip_skill("hero_001", "guardian_field_medic").accepted and hero.equipped_skills == {}, "taking off what is not on changes nothing"
    assert medic.equip_skill("hero_001", "squire_anchor").accepted  # the career rules allow it; only the screen holds it back
    assert medic.equip_skill("hero_001", "guardian_field_medic").accepted
    assert hero.equipped_skills == {0: "squire_anchor", 1: "guardian_field_medic"}
    assert medic.skills("hero_001")["used"] == 1 and medic.snapshot("hero_001")["skills"] == ["squire_anchor", "guardian_field_medic"]
    assert medic.unequip_skill("hero_001", "squire_anchor").accepted and hero.equipped_skills == {1: "guardian_field_medic"}
    assert medic.equip_skill("hero_001", "squire_anchor").accepted and hero.equipped_skills == {0: "squire_anchor", 1: "guardian_field_medic"}
    # The skill that is named is the one taken off, whichever slot it is in.
    assert medic.unequip_skill("hero_001", "guardian_field_medic").accepted and hero.equipped_skills == {0: "squire_anchor"}


def test_away_from_its_vocation_a_skill_costs_capacity_the_hero_may_not_have(medic: Progression):
    assert medic.change("hero_001", "squire").accepted
    hero = medic.state.heroes["hero_001"]
    assert hero.equipped_skills == {}, "Field Medic needs 3 capacity away from the Guardian; a Squire has 2"
    field_medic = medic.skills("hero_001")["rows"][1]
    assert (field_medic["cost"], field_medic["problem"]) == (3, "Needs 3 capacity; 2 of 2 is free.")
    refused = medic.equip_skill("hero_001", "guardian_field_medic")
    assert not refused.accepted and refused.error_code == "CAPACITY_EXCEEDED"


def test_an_equipped_skill_goes_into_the_run_and_works_there(medic: Progression, vocations):
    from battle_dice.core import skills
    from tests.conftest import action, begin_hero, commit, down, finish_activation, unit

    engine = start(medic, vocations)
    assert engine.build("h01").skills == (skills.FIELD_MEDIC,) and engine.build("h02").skills == ()
    locked = medic.unequip_skill("hero_001", "guardian_field_medic")
    assert not locked.accepted and locked.error_code == "PHASE_LOCKED", "a build does not change during a run"
    down(engine, "h02")
    begin_hero(engine, "h01", guardian_d4=1, guardian_d6=5)
    unit(engine, "h01").mana = 2
    commit(engine, action("guardian_d6", "h02"))
    finish_activation(engine)
    assert (unit(engine, "h02").state, unit(engine, "h02").hp) == ("standing", 1)
    medic.sync(engine)  # the save follows the run as before; a revival changes nothing in what it records
    assert medic.state.run is not None and medic.state.run.phase == "battle"


def test_whole_runs_with_field_medic_equipped_end_and_replay(vocations):
    """Eight whole runs by the informed simulated player. It uses the skill when it can pay for it (seed 503)."""
    from battle_dice.core import skills
    from battle_dice.core.events import EventType, events_hash, state_hash
    from battle_dice.core.replay import export_run, verify
    from battle_dice.sim.policies import play_run

    shape = [("guardian", "front"), ("scout", "back"), ("apprentice", "back")]
    used: dict[int, int] = {}
    for seed in range(500, 508):
        party = [{"class_id": class_id, "row": row, "hero": {"hero_id": f"hero_{n:03d}", "skills": [skills.FIELD_MEDIC] if class_id == "guardian" else []}}
                 for n, (class_id, row) in enumerate(shape, start=1)]
        engine = Engine(packaged_content(), vocations)
        ok(engine.do(cmd.START_RUN, seed=seed, party=party, encounters=["training_04"]))
        play_run(engine, HeuristicPolicy())
        assert engine.finished()
        battle = 0
        per_battle: dict[int, int] = {}
        for event in engine.events:
            if event.type == EventType.BATTLE_STARTED:
                battle = event.delta["battle"]
            elif event.type == EventType.ACTION_RESOLVED and event.delta.get("name") == "Heal (Field Medic)":
                per_battle[battle] = per_battle.get(battle, 0) + 1
        assert all(count == 1 for count in per_battle.values()), "once per encounter"
        used[seed] = sum(per_battle.values())
        if used[seed]:
            again = verify(packaged_content(), export_run(engine))
            assert (events_hash(again.events), state_hash(again.state)) == (events_hash(engine.events), state_hash(engine.state))
    assert used[503] == 1, used
