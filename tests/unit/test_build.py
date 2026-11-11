"""The hero build: the one place the rules read a hero's class data from (``core/build.py``)."""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from battle_dice.core import commands as cmd
from battle_dice.core import view
from battle_dice.core.build import HeroBuild, build_from_class
from battle_dice.core.engine import Engine
from battle_dice.core.events import state_hash
from battle_dice.core.models import DieDefinition
from tests.conftest import begin_hero, enemies, packaged_content, party_spec, rejected, start, unit

SOURCE = Path(__file__).resolve().parents[2] / "src" / "battle_dice"
CLASSES = ("squire", "apprentice", "scout")


@pytest.mark.parametrize("class_id", CLASSES)
def test_the_build_of_a_shipped_class_is_exactly_its_class_entry(class_id):
    content = packaged_content()
    cls = content.class_def(class_id)
    build = build_from_class(content, class_id)
    assert build.vocation_id == build.upgrade_family == class_id
    for name in ("name", "max_hp", "start_hp", "speed", "base_initiative", "max_mana", "start_mana",
                 "max_corruption", "start_corruption", "rerolls", "dice_capacity"):
        assert getattr(build, name) == cls[name], name
    assert list(build.starting_dice) == cls["starting_dice"] and list(build.bench_dice) == cls["bench_dice"]
    assert build.scheduling == cls["scheduling"] and build.passive == cls["passive"]
    assert build.reaction_id == cls["reaction"] and build.reaction == content.reactions[cls["reaction"]]
    assert build.dice == {}, "a shipped class brings no dice of its own: they are in the content"
    with pytest.raises(dataclasses.FrozenInstanceError):
        build.max_hp = 99  # type: ignore[misc]


def test_the_engine_holds_one_build_per_hero_from_run_start():
    engine = start("squire", "apprentice", "scout", "scout", content=packaged_content())
    assert [engine.build(h).vocation_id for h in ("h01", "h02", "h03", "h04")] == ["squire", "apprentice", "scout", "scout"]
    for hero in engine.combat.side("hero"):
        build = engine.build(hero.id)
        assert isinstance(build, HeroBuild)
        assert hero.archetype_id == build.vocation_id
        assert (hero.max_hp, hero.speed, hero.max_mana) == (build.max_hp, build.speed, build.max_mana)
        assert hero.equipped_dice_ids == list(build.starting_dice)
        assert engine.state.inventory[hero.id] == list(build.bench_dice)


def test_builds_are_not_part_of_the_hashed_run_state():
    """They are derived from the StartRun command and the content, so the state hash cannot depend on them."""
    engine = start("squire", content=packaged_content())
    before = state_hash(engine.state)
    engine._builds["h01"] = dataclasses.replace(engine.build("h01"), name="Renamed")
    assert state_hash(engine.state) == before


def test_a_rejected_start_leaves_no_builds_behind():
    engine = Engine(packaged_content())
    result = engine.do(cmd.START_RUN, seed=1, party=[{"class_id": "squire", "row": "front"}, {"class_id": "paladin", "row": "front"}])
    assert not result.accepted and "Unknown class" in (result.reason or "")
    assert engine._builds == {}
    assert engine.do(cmd.START_RUN, seed=1, party=party_spec("scout")).accepted
    assert engine.build("h01").vocation_id == "scout"


def test_a_die_the_build_brings_is_found_before_the_content():
    """Evolved vocations bring their own dice. Until then this is exercised with a stand-in die."""
    engine = start("squire", content=packaged_content())
    iron = engine.content.die("iron_d6")
    own = DieDefinition(id="iron_d6", name="Own Iron d6", affinity_class="squire", size=6, faces=list(iron.faces))
    engine._builds["h01"] = dataclasses.replace(engine.build("h01"), dice={"iron_d6": own})
    assert engine.die_for("h01", "iron_d6") is own and engine.base_die("h01", "iron_d6") is own
    assert engine.die_for("h01", "oath_d4") is engine.content.die("oath_d4")
    assert engine.base_die("h01", "no_such_die") is None


def test_the_rules_read_what_the_build_says_not_the_class_table():
    """Change one hero's build and only that hero changes: schedule, passive, rerolls and reaction."""
    engine = start("scout", "scout", content=packaged_content())
    squire = build_from_class(engine.content, "squire")
    engine._builds["h01"] = dataclasses.replace(
        engine.build("h01"), scheduling=squire.scheduling, passive=squire.passive, rerolls=0, reaction_id=squire.reaction_id,
        reaction=squire.reaction,
    )
    first, second = (view.combatant_view(engine, unit(engine, h)) for h in ("h01", "h02"))
    assert first["scheduling"]["label"] == "Single Commitment" and second["scheduling"]["label"] == "Exploit Combo"
    assert first["passive"]["id"] == "steadfast" and second["passive"]["id"] == "exploit_opening"
    assert first["reaction"]["id"] == "interpose" and second["reaction"]["id"] == "disrupt"
    begin_hero(engine, "h01", striker_d8=4, tools_d4=1)  # Poison and Quick Shot: a combo for a Scout
    turn = engine.combat.turn
    assert turn is not None and turn.rerolls_remaining == 0, "the build's rerolls, not the Scout's two"
    enemy = enemies(engine)[0].id
    combo = [{"die_id": "striker_d8", "target_ids": [enemy]}, {"die_id": "tools_d4", "target_ids": [enemy]}]
    rejected(engine.do(cmd.SET_ACTION_PLAN, actions=combo), "Single Commitment allows at most 1 action")


def test_no_rule_reads_the_class_table_directly():
    """The seam must not erode: in the rules, class data comes from ``engine.build(hero_id)`` only."""
    offenders = []
    for path in sorted((SOURCE / "core").glob("*.py")):
        if path.name != "build.py" and "class_def(" in path.read_text(encoding="utf-8"):
            offenders.append(path.name)
    assert offenders == [], f"read the hero's build instead of the class table in: {offenders}"
    by_hero = re.compile(r"class_def\([^)]*archetype_id")
    anywhere = [str(p.relative_to(SOURCE)) for p in sorted(SOURCE.rglob("*.py")) if by_hero.search(p.read_text(encoding="utf-8"))]
    assert anywhere == [], f"a hero's class is looked up by archetype in: {anywhere}"
