"""Hero builds from the vocation catalog, and the feature gate that hands the catalog to the engine.

Phase 1 of Class Evolution (``docs/class_evolution/FDD_v0.2.md``). The gate is off by default;
these tests switch it on by giving the engine the catalog directly.
"""

from __future__ import annotations

import dataclasses
import importlib.resources
import os
import subprocess
import sys

import pytest

from battle_dice import features
from battle_dice.app.controller import AppController
from battle_dice.content.loader import ContentError
from battle_dice.content.vocations import (
    CATALOG_PATH,
    SCHEMA_PATH,
    VocationCatalog,
    load_catalog,
    load_vocation_catalog,
    vocation_gaps,
)
from battle_dice.core import commands as cmd
from battle_dice.core.build import BuildNotSupported, build_from_class
from battle_dice.core.engine import Engine
from tests.conftest import packaged_content, rejected

NOVICES = ("squire", "apprentice", "scout")
#: The vocations the rules cannot run yet, each with one engine gap its refusal must name.
NOT_YET = {
    "spellblade": "face_corruption_cost",
    "duelist": "schedule_first_slot_categories",
    "arcanist": "schedule_slot_tag_filter",
    "shadowbinder": "passive_sequence_remove_corruption",
    "champion": "passive_reaction_shield_bonus",
    "archmage": "schedule_three_slots",
    "hero": "schedule_distinct_categories",
    "trickster": "passive_paid_reroll",
    "dragon_knight": "passive_reaction_shield_bonus",
}


@pytest.fixture(scope="module")
def catalog() -> VocationCatalog:
    return load_vocation_catalog(packaged_content())


# --------------------------------------------------------------------------------------------
# The catalog as a source of builds
# --------------------------------------------------------------------------------------------


def test_the_catalog_ships_inside_the_package():
    """The wheel and the Windows build take their data from the package folder."""
    folder = importlib.resources.files("battle_dice.content") / "class_evolution"
    assert (folder / "vocation_catalog.json").is_file() and (folder / "vocation_catalog.schema.json").is_file()
    assert CATALOG_PATH.is_file() and SCHEMA_PATH.is_file() and CATALOG_PATH.parent.name == "class_evolution"


def test_every_vocation_is_either_playable_or_refused_with_a_reason(catalog):
    assert sorted(catalog.builds) == ["apprentice", "guardian", "ranger", "scout", "squire"]
    assert set(catalog.unsupported) == set(NOT_YET)
    assert len(catalog.builds) + len(catalog.unsupported) == 14
    assert catalog.version == "0.3.0" and len(catalog.sha256) == 64
    assert all(catalog.known(v) for v in [*catalog.builds, *catalog.unsupported]) and not catalog.known("paladin")


@pytest.mark.parametrize("class_id", NOVICES)
def test_a_novice_build_from_the_catalog_is_the_shipped_class(catalog, class_id):
    assert catalog.build(class_id) == build_from_class(packaged_content(), class_id)


def test_the_ranger_build(catalog):
    content = packaged_content()
    ranger = catalog.build("ranger")
    raw = next(v for v in load_catalog()["vocations"] if v["id"] == "ranger")
    assert (ranger.vocation_id, ranger.name, ranger.upgrade_family) == ("ranger", "Ranger", "scout")
    for name in ("max_hp", "start_hp", "speed", "base_initiative", "max_mana", "start_mana", "max_corruption",
                 "start_corruption", "rerolls", "dice_capacity"):
        assert getattr(ranger, name) == raw[name], name
    assert ranger.starting_dice == ("ranger_d8", "ranger_d4") and ranger.bench_dice == ()
    # Its dice are its own, built by the game's content loader; the shipped content does not know them.
    assert sorted(ranger.dice) == ["ranger_d4", "ranger_d8"] and "ranger_d8" not in content.dice
    assert [die.affinity_class for die in ranger.dice.values()] == ["ranger", "ranger"]
    assert [len(ranger.dice[d].faces) for d in ("ranger_d8", "ranger_d4")] == [8, 4]
    # Schedule, passive and reaction are shapes the shipped rules already implement.
    scout = catalog.build("scout").schedule
    assert (ranger.schedule.slots, ranger.schedule.order, ranger.schedule.max_actions) == (scout.slots, scout.order, scout.max_actions)
    assert ranger.schedule.label == "Status then Attack"
    assert (ranger.passive["type"], ranger.passive["amount"]) == ("combo_attack_bonus", 1)
    assert "engine_support" not in ranger.passive and "attack_tag_invariant" not in ranger.passive
    assert ranger.reaction_id == "disrupt" and ranger.reaction == content.reactions["disrupt"]


@pytest.mark.parametrize(("vocation_id", "gap"), sorted(NOT_YET.items()))
def test_a_vocation_that_needs_an_engine_gap_is_refused_by_name(catalog, vocation_id, gap):
    with pytest.raises(BuildNotSupported) as refusal:
        catalog.build(vocation_id)
    assert f"'{vocation_id}' cannot be played yet" in str(refusal.value) and gap in str(refusal.value)
    raw = load_catalog()
    assert gap in vocation_gaps(raw, next(v for v in raw["vocations"] if v["id"] == vocation_id))


def test_the_skill_gap_alone_does_not_block_a_vocation():
    raw = load_catalog()
    ranger = next(v for v in raw["vocations"] if v["id"] == "ranger")
    assert ranger["skills_learned"] and vocation_gaps(raw, ranger) == []


def test_a_catalog_with_a_problem_is_refused_whole(tmp_path):
    text = CATALOG_PATH.read_text(encoding="utf-8").replace('"content_version": "1.3.1"', '"content_version": "1.2.1"', 1)
    broken = tmp_path / "vocation_catalog.json"
    broken.write_text(text, encoding="utf-8")
    with pytest.raises(ContentError) as error:
        load_vocation_catalog(packaged_content(), broken)
    assert any("vocation catalog: baseline" in problem for problem in error.value.problems)


def test_engine_file_names_are_checked_only_where_the_sources_are(tmp_path):
    """The standalone Windows build has no source files on disk; the catalog must still load there."""
    from battle_dice.content import vocations

    raw = load_catalog()
    assert vocations._gap_problems(raw) == []
    assert vocations._gap_problems(raw, tmp_path) == [], "no sources here: nothing to check"
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")
    missing = vocations._gap_problems(raw, tmp_path)
    assert len(missing) == len(raw["engine_gaps"]) and all("which does not exist" in problem for problem in missing)


def test_the_catalog_hash_follows_its_content(tmp_path):
    changed = tmp_path / "vocation_catalog.json"
    changed.write_text(CATALOG_PATH.read_text(encoding="utf-8").replace('"name": "Ranger"', '"name": "Pathfinder"', 1), encoding="utf-8")
    original, other = load_vocation_catalog(packaged_content()), load_vocation_catalog(packaged_content(), changed)
    assert original.sha256 != other.sha256 and other.build("ranger").name == "Pathfinder"
    assert load_vocation_catalog(packaged_content()).sha256 == original.sha256


# --------------------------------------------------------------------------------------------
# The engine with and without the catalog
# --------------------------------------------------------------------------------------------


def party(*members: tuple[str, str]) -> list[dict[str, str]]:
    return [{"class_id": class_id, "row": row} for class_id, row in members]


def test_without_the_catalog_an_evolved_vocation_is_an_unknown_class():
    engine = Engine(packaged_content())
    assert engine.vocations is None
    rejected(engine.do(cmd.START_RUN, seed=1, party=party(("ranger", "back"))), "Unknown class 'ranger'")
    assert not engine.started and engine.vocation_catalog_pin is None


def test_with_the_catalog_a_playable_vocation_starts_a_run_and_the_run_names_the_catalog(catalog):
    engine = Engine(packaged_content(), catalog)
    assert engine.do(cmd.START_RUN, seed=1, party=party(("squire", "front"), ("ranger", "back"))).accepted
    assert engine.build("h01") == build_from_class(engine.content, "squire") and engine.build("h02") is catalog.build("ranger")
    ranger = engine.combat.combatants["h02"]
    assert (ranger.archetype_id, ranger.name, ranger.max_hp, ranger.speed) == ("ranger", "Ranger 2", 11, 14)
    assert ranger.equipped_dice_ids == ["ranger_d8", "ranger_d4"] and engine.state.inventory["h02"] == []
    assert engine.die_for("h02", "ranger_d8") is catalog.build("ranger").dice["ranger_d8"]
    pin = {"version": catalog.version, "sha256": catalog.sha256}
    assert engine.vocation_catalog_pin == pin
    assert engine.events[0].type == "run_started" and engine.events[0].delta["vocation_catalog"] == pin


def test_with_the_catalog_an_unplayable_or_unknown_vocation_is_rejected_and_nothing_starts(catalog):
    engine = Engine(packaged_content(), catalog)
    reason = rejected(engine.do(cmd.START_RUN, seed=1, party=party(("squire", "front"), ("duelist", "front"))), "cannot be played yet")
    assert "passive_attack_after_category_bonus" in reason
    rejected(engine.do(cmd.START_RUN, seed=1, party=party(("paladin", "front"))), "Unknown class 'paladin'")
    assert not engine.started and engine._builds == {} and engine.events == []
    assert engine.do(cmd.START_RUN, seed=1, party=party(("ranger", "back"))).accepted


def test_a_party_of_shipped_classes_does_not_name_the_catalog_even_with_the_gate_on(catalog):
    engine = Engine(packaged_content(), catalog)
    assert engine.do(cmd.START_RUN, seed=1, party=party(("squire", "front"), ("scout", "back"))).accepted
    assert engine.vocation_catalog_pin is None and "vocation_catalog" not in engine.events[0].delta


def test_the_rangers_upgrade_offers_come_from_the_scouts_catalogs(catalog):
    """An evolved hero's Reforge and Imbue cards are its upgrade family's."""
    from battle_dice.sim.policies import HeuristicPolicy

    engine = Engine(packaged_content(), catalog)
    assert engine.do(cmd.START_RUN, seed=4, party=party(("squire", "front"), ("ranger", "back"))).accepted
    policy = HeuristicPolicy()
    while engine.state.phase != "upgrade":
        assert not engine.finished(), "the seeded run should reach the upgrade screen"
        if engine.needs_input():
            policy.act(engine)
        else:
            assert engine.do(cmd.ADVANCE_PHASE).accepted
    scout_faces = set(engine.content.upgrades["reforge_faces"]["scout"]) | set(engine.content.upgrades["imbue_faces"]["scout"])
    names = {engine.content.upgrade_faces[f].name for f in scout_faces}
    offers = [o for dice in engine.state.upgrade_offers["h02"].values() for o in dice if o["kind"] in ("reforge", "imbue")]
    assert offers and {o["after"]["name"] for o in offers} <= names


# --------------------------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------------------------


def test_every_gate_is_off_by_default():
    assert features.resolve((), {}) == frozenset()
    assert features.describe(frozenset()) == ""
    assert features.KNOWN_FEATURES == ("class_evolution_v1",)


@pytest.mark.parametrize(
    ("flags", "environ"),
    [
        (["class_evolution_v1"], {}),
        ([], {"BATTLE_DICE_FEATURES": "class_evolution_v1"}),
        ([" class_evolution_v1 "], {"BATTLE_DICE_FEATURES": " class_evolution_v1 , "}),
    ],
)
def test_a_gate_is_switched_on_by_the_flag_or_the_environment(flags, environ):
    enabled = features.resolve(flags, environ)
    assert enabled == frozenset({"class_evolution_v1"})
    assert features.describe(enabled) == "features: class_evolution_v1"


def test_an_unknown_gate_is_refused():
    with pytest.raises(ValueError, match="Unknown feature\\(s\\): turbo. Known: class_evolution_v1."):
        features.resolve(["turbo"], {})
    with pytest.raises(ValueError, match="turbo"):
        features.resolve([], {"BATTLE_DICE_FEATURES": "class_evolution_v1,turbo"})


def test_the_controller_hands_the_catalog_to_the_engine_only_when_the_gate_is_on(tmp_path, catalog):
    off = AppController(fixed_seed=1, log_dir=tmp_path / "off")
    assert off.features == frozenset() and off.vocations is None
    off.new_run()
    off.add_hero("squire")
    off.begin_run()
    assert off.engine is not None and off.engine.vocations is None

    on = AppController(fixed_seed=1, log_dir=tmp_path / "on", features=["class_evolution_v1"])
    assert on.vocations is not None and on.vocations.sha256 == catalog.sha256
    on.new_run()
    on.add_hero("squire")
    on.begin_run()
    assert on.engine is not None and on.engine.vocations is on.vocations
    # The same party gives the same run: the gate changes nothing for shipped classes.
    assert [dataclasses.asdict(e) for e in on.engine.events] == [dataclasses.asdict(e) for e in off.engine.events]


def test_the_command_line_reports_and_validates_the_gate(capsys):
    from battle_dice.__main__ import main

    assert main(["--version"]) == 0
    assert "features" not in capsys.readouterr().out
    assert main(["--version", "--feature", "class_evolution_v1"]) == 0
    assert capsys.readouterr().out.strip().endswith("features: class_evolution_v1")
    with pytest.raises(SystemExit) as stop:
        main(["--version", "--feature", "turbo"])
    assert stop.value.code == 2 and "Unknown feature(s): turbo" in capsys.readouterr().err


def run_python(code: str, **extra_env: str) -> str:
    env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy", **extra_env}
    env.pop("BATTLE_DICE_FEATURES", None) if "BATTLE_DICE_FEATURES" not in extra_env else None
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120, check=True)
    return done.stdout.strip().splitlines()[-1]


def test_with_the_gate_off_the_game_never_loads_the_catalog_module():
    """Fixture CE-01: no progression data is read while the gate is off."""
    code = (
        "import sys, tempfile\n"
        "import battle_dice.__main__, battle_dice.ui.app, battle_dice.sim.runner, battle_dice.replay_cli\n"
        "from battle_dice import features\n"
        "from battle_dice.app.controller import AppController\n"
        "c = AppController(fixed_seed=1, log_dir=tempfile.mkdtemp(), features=features.resolve())\n"
        "c.new_run(); c.add_hero('scout'); c.begin_run()\n"
        "print(c.engine is not None, 'battle_dice.content.vocations' in sys.modules)\n"
    )
    assert run_python(code) == "True False"
    assert run_python(code, BATTLE_DICE_FEATURES="class_evolution_v1") == "True True"
