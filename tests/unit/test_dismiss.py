"""Dismissing a hero (owner decision D-35, playtest finding R3).

A full roster could not be emptied. A hero can now be dismissed between runs. It leaves the roster for good;
what it earned stays in the save's history, and its id and number are never given to another hero.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from battle_dice.career.catalog import CareerCatalog
from battle_dice.career.model import CareerState, Profile, RunInfo
from battle_dice.career.service import CareerService
from battle_dice.career.store import SqliteProfileStore, StoredCareerService
from battle_dice.content.vocations import load_catalog
from tests.conftest import packaged_content

PROFILE = "profile_demo"


@pytest.fixture(scope="module")
def catalog() -> CareerCatalog:
    return CareerCatalog(load_catalog(), packaged_content())


def recruit(command_id: str, starting_class: str = "squire") -> dict:
    return {"type": "RecruitHero", "command_id": command_id, "state_revision": 0, "params": {"starting_class": starting_class}}


def dismiss(command_id: str, hero_id: str, revision: int = 0) -> dict:
    return {"type": "DismissHero", "command_id": command_id, "state_revision": revision, "params": {"hero_id": hero_id}}


def service_with(catalog: CareerCatalog, heroes: int) -> CareerService:
    service = CareerService(catalog, CareerState(Profile(PROFILE)))
    for number in range(1, heroes + 1):
        assert service.submit(recruit(f"recruit-{number}")).accepted
    return service


def test_a_dismissed_hero_leaves_the_roster_and_the_event_says_who(catalog):
    service = service_with(catalog, 2)
    result = service.submit(dismiss("d-1", "hero_001"))
    assert result.accepted and [event["type"] for event in result.events] == ["HeroDismissed"]
    assert {key: result.events[0][key] for key in ("hero_id", "display_name", "vocation_id")} == {
        "hero_id": "hero_001", "display_name": "Recruit 1", "vocation_id": "squire"}
    assert list(service.state.heroes) == ["hero_002"] and service.state.dismissed == ["hero_001"]


def test_dismissing_makes_room_in_a_full_roster_and_the_number_is_not_given_out_again(catalog):
    service = service_with(catalog, 2)
    service.roster_limit = 2
    full = service.submit(recruit("recruit-3"))
    assert (full.result, full.error_code) == ("rejected", "ROSTER_FULL")
    assert service.submit(dismiss("d-1", "hero_002")).accepted
    assert service.submit(recruit("recruit-4", "scout")).accepted
    assert [(hero.hero_id, hero.display_name) for hero in service.state.heroes.values()] == [("hero_001", "Recruit 1"), ("hero_003", "Recruit 3")]
    # Also when the newest hero of all was dismissed and nobody is left.
    for number, hero_id in enumerate(list(service.state.heroes)):
        assert service.submit(dismiss(f"d-{number + 2}", hero_id)).accepted
    assert service.state.heroes == {} and service.submit(recruit("recruit-5")).accepted
    assert list(service.state.heroes) == ["hero_004"]


@pytest.mark.parametrize(("phase", "accepted"), [("battle", False), ("upgrade", False), ("equipment", False), ("victory", True), ("defeat", True)])
def test_a_hero_is_dismissed_between_runs_only(catalog, phase, accepted):
    service = service_with(catalog, 1)
    service.state.run = RunInfo("run-1", phase)
    result = service.submit(dismiss("d-1", "hero_001"))
    assert result.accepted is accepted and result.error_code == (None if accepted else "PHASE_LOCKED")
    assert ("hero_001" in service.state.heroes) is not accepted and service.state.dismissed == (["hero_001"] if accepted else [])
    assert service.between_runs() is accepted


def test_a_refused_or_repeated_dismissal_changes_nothing(catalog):
    service = service_with(catalog, 1)
    stale = service.submit(dismiss("d-1", "hero_001", revision=7))
    assert (stale.result, stale.error_code) == ("rejected", "REVISION_CONFLICT") and "hero_001" in service.state.heroes
    assert service.submit(dismiss("d-2", "hero_001")).accepted
    events = len(service.state.events)
    again = service.submit(dismiss("d-2", "hero_001"))
    assert again.accepted and again.duplicate and len(service.state.events) == events and service.state.dismissed == ["hero_001"]
    with pytest.raises(ValueError, match="Unknown hero 'hero_001'"):
        service.submit(dismiss("d-3", "hero_001"))  # it is not on the roster any more: no command reaches it


def test_the_save_keeps_the_dismissal_and_the_heros_history(catalog, tmp_path: Path):
    path = tmp_path / "save.sqlite"
    store = SqliteProfileStore(path, catalog)
    store.import_state(CareerState(Profile(PROFILE)))
    stored = StoredCareerService(store, PROFILE)
    for number in (1, 2):
        assert stored.submit(recruit(f"recruit-{number}")).accepted
    assert stored.grant_mastery("hero_001", "squire", 3, "arranged by the test").accepted
    assert stored.submit(dismiss("d-1", "hero_001", revision=stored.state.heroes["hero_001"].revision)).accepted
    store.close()

    with SqliteProfileStore(path, catalog) as reopened:
        again = StoredCareerService(reopened, PROFILE)
        assert list(again.state.heroes) == ["hero_002"] and again.state.dismissed == ["hero_001"]
        # The row is marked, not removed: what points at it is whole, and what it earned can still be read.
        (marked,) = reopened.conn.execute("SELECT dismissed_at FROM hero WHERE hero_id = 'hero_001'").fetchone()
        assert marked and reopened.conn.execute("SELECT dismissed_at FROM hero WHERE hero_id = 'hero_002'").fetchone() == (None,)
        assert reopened.conn.execute("SELECT mastery_points FROM hero_vocation_mastery WHERE hero_id = 'hero_001' AND vocation_id = 'squire'").fetchone() == (3,)
        assert reopened.conn.execute("PRAGMA foreign_key_check").fetchall() == []
        types = [row[0] for row in reopened.conn.execute("SELECT event_type FROM progression_event_log ORDER BY event_seq")]
        assert types[-1] == "HeroDismissed" and reopened.verify_event_chain(PROFILE) == len(types)
        assert again.submit(recruit("recruit-3")).accepted and list(again.state.heroes) == ["hero_002", "hero_003"]


def test_a_dismissal_that_cannot_be_saved_is_not_kept_in_memory(catalog, tmp_path: Path):
    store = SqliteProfileStore(tmp_path / "save.sqlite", catalog)
    store.import_state(CareerState(Profile(PROFILE)))
    stored = StoredCareerService(store, PROFILE)
    assert stored.submit(recruit("recruit-1")).accepted
    store.fault_after = "unlock_insert"
    with pytest.raises(Exception, match="unlock_insert"):
        stored.submit(dismiss("d-1", "hero_001"))
    store.fault_after = None
    assert list(stored.state.heroes) == ["hero_001"] and stored.state.dismissed == []
    assert store.conn.execute("SELECT dismissed_at FROM hero WHERE hero_id = 'hero_001'").fetchone() == (None,)
    store.close()
