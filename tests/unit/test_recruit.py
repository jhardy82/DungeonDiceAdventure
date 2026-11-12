"""Recruiting heroes (Class Evolution Phase 4, step C).

Owner decision of 2026-11-11 (D-27): heroes are recruited at party setup, free of charge, and a
profile holds at most 12. A recruit is one of the three starting classes and, like every hero in
the acceptance fixtures, has all three unlocked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from battle_dice.career.catalog import CareerCatalog
from battle_dice.career.model import CareerState, Profile, RunInfo
from battle_dice.career.service import ROSTER_LIMIT, CareerService, state_view
from battle_dice.career.store import SqliteProfileStore, StoredCareerService
from battle_dice.content.vocations import load_catalog
from tests.conftest import packaged_content

PROFILE = "profile_demo"


@pytest.fixture(scope="module")
def catalog() -> CareerCatalog:
    return CareerCatalog(load_catalog(), packaged_content())


def recruit(command_id: str, starting_class: str, **params: str) -> dict:
    return {"type": "RecruitHero", "command_id": command_id, "state_revision": 0, "params": {"starting_class": starting_class, **params}}


def new_service(catalog: CareerCatalog) -> CareerService:
    return CareerService(catalog, CareerState(Profile(PROFILE)))


def test_a_recruit_is_a_starting_class_with_all_three_unlocked(catalog):
    service = new_service(catalog)
    result = service.submit(recruit("cmd-1", "squire"))
    assert result.accepted and result.error_code is None
    assert [event["type"] for event in result.events] == ["HeroRecruited", "VocationClaimed", "VocationClaimed", "VocationClaimed"]
    assert result.events[0] == {"type": "HeroRecruited", "event_id": f"{PROFILE}:0", "event_seq": 0,
                                "hero_id": "hero_001", "vocation_id": "squire", "display_name": "Squire 1"}
    hero = service.state.heroes["hero_001"]
    assert (hero.active_vocation_id, hero.origin_vocation_id, hero.display_name) == ("squire", "squire", "Squire 1")
    assert hero.unlocked_vocations == catalog.starting_classes() == ["squire", "apprentice", "scout"]
    assert {v: (row.rank, row.points) for v, row in hero.mastery.items()} == dict.fromkeys(hero.unlocked_vocations, (1, 0))
    assert hero.eligibility_state == "eligible" and hero.revision == 0 and hero.dice == [] and hero.equipped_skills == {}
    assert hero.unlock_routes == dict.fromkeys(hero.unlocked_vocations, "route_0")


def test_recruits_get_the_next_number_and_a_name_from_their_class(catalog):
    service = new_service(catalog)
    for number, starting_class in enumerate(["squire", "scout", "apprentice", "squire"], start=1):
        assert service.submit(recruit(f"cmd-{number}", starting_class)).accepted
    assert [(h.hero_id, h.display_name) for h in service.state.heroes.values()] == [
        ("hero_001", "Squire 1"), ("hero_002", "Scout 2"), ("hero_003", "Apprentice 3"), ("hero_004", "Squire 4")]


def test_the_same_recruit_command_sent_again_recruits_nobody_new(catalog):
    service = new_service(catalog)
    assert service.submit(recruit("cmd-1", "squire")).accepted
    again = service.submit(recruit("cmd-1", "squire"))
    assert again.accepted and again.duplicate and len(service.state.heroes) == 1
    assert service.submit(recruit("cmd-1", "scout")).error_code == "COMMAND_ID_REUSED"


def test_the_roster_holds_twelve_heroes(catalog):
    service = new_service(catalog)
    assert service.roster_limit == ROSTER_LIMIT == 12
    for number in range(12):
        assert service.submit(recruit(f"cmd-{number}", "scout")).accepted
    before, events = state_view(service), len(service.state.events)
    full = service.submit(recruit("cmd-13", "scout"))
    assert (full.result, full.error_code, full.error_details) == ("rejected", "ROSTER_FULL", {"roster_limit": 12, "heroes": 12})
    assert state_view(service) == before and len(service.state.events) == events and "cmd-13" not in service.state.processed
    service.roster_limit = 13  # the limit is a setting; the default is the owner's decision
    assert service.submit(recruit("cmd-13", "scout")).accepted


def test_only_a_starting_class_can_be_recruited(catalog):
    service = new_service(catalog)
    for not_a_start in ("guardian", "hero", "paladin"):
        with pytest.raises(ValueError, match="is not a starting class"):
            service.submit(recruit("cmd-x", not_a_start))
    assert service.state.heroes == {} and service.state.events == []


def test_nobody_is_recruited_inside_a_run_or_for_another_catalog(catalog):
    service = new_service(catalog)
    service.state.run = RunInfo("run_0001", "battle")
    assert service.submit(recruit("cmd-1", "squire")).error_code == "PHASE_LOCKED"
    service.state.run = RunInfo("run_0001", "equipment")
    assert service.submit(recruit("cmd-1", "squire")).error_code == "PHASE_LOCKED"
    service.state.run = RunInfo("run_0001", "victory")  # the run is over: party setup again
    assert service.submit(recruit("cmd-1", "squire")).accepted
    assert service.submit(recruit("cmd-2", "squire", catalog_version="0.0.1")).error_code == "CONTENT_MIGRATION_REQUIRED"
    # When both fail, the registry's order decides: the catalog version first, then the phase, then the roster.
    service.state.run = RunInfo("run_0002", "battle")
    service.roster_limit = 1
    assert service.submit(recruit("cmd-3", "squire")).error_code == "PHASE_LOCKED"
    assert service.submit(recruit("cmd-3", "squire", catalog_version="0.0.1")).error_code == "CONTENT_MIGRATION_REQUIRED"


def test_a_recruit_can_claim_and_change_like_any_hero(catalog):
    service = new_service(catalog)
    assert service.submit(recruit("cmd-1", "squire")).accepted
    change = {"type": "ChangeVocation", "command_id": "cmd-2", "state_revision": 0,
              "params": {"hero_id": "hero_001", "target_vocation_id": "scout"}}
    assert service.submit(change).accepted and service.state.heroes["hero_001"].active_vocation_id == "scout"
    claim = {"type": "ClaimVocation", "command_id": "cmd-3", "state_revision": 1,
             "params": {"hero_id": "hero_001", "target_vocation_id": "guardian"}}
    assert service.submit(claim).error_code == "PREREQUISITE_UNMET"  # the Squire is not mastered yet


def test_recruits_are_saved_and_come_back_after_the_file_is_reopened(catalog, tmp_path: Path):
    path = tmp_path / "save.sqlite"
    store = SqliteProfileStore(path, catalog, clock=lambda: "2026-11-12T08:00:00Z")
    store.import_state(CareerState(Profile(PROFILE)))
    saved = StoredCareerService(store, PROFILE)
    assert saved.submit(recruit("cmd-1", "squire")).accepted and saved.submit(recruit("cmd-2", "apprentice")).accepted
    rows = store.conn.execute("SELECT hero_id, origin_vocation_id, active_vocation_id, display_name FROM hero ORDER BY rowid").fetchall()
    assert rows == [("hero_001", "squire", "squire", "Squire 1"), ("hero_002", "apprentice", "apprentice", "Apprentice 2")]
    assert store.conn.execute("SELECT COUNT(*) FROM hero_vocation_unlock").fetchone()[0] == 6
    assert store.verify_event_chain(PROFILE) == 8  # per recruit: one HeroRecruited and three claims
    store.close()
    with SqliteProfileStore(path, catalog) as reopened:
        again = StoredCareerService(reopened, PROFILE)
        assert state_view(again.service) == state_view(saved.service)
        assert again.submit(recruit("cmd-2", "apprentice")).duplicate  # the repeated command is answered from the file
        assert again.submit(recruit("cmd-3", "scout")).accepted and "hero_003" in again.state.heroes


def test_a_rejected_recruit_writes_nothing_to_the_file(catalog, tmp_path: Path):
    store = SqliteProfileStore(tmp_path / "save.sqlite", catalog, clock=lambda: "2026-11-12T08:00:00Z")
    store.import_state(CareerState(Profile(PROFILE)))
    saved = StoredCareerService(store, PROFILE)
    saved.service.roster_limit = 0
    counts = lambda: [store.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("hero", "progression_event_log", "processed_command")]  # noqa: E731
    before = counts()
    assert saved.submit(recruit("cmd-1", "squire")).error_code == "ROSTER_FULL"
    assert counts() == before == [0, 0, 0]
    store.close()
