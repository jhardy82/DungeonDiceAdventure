"""T13_upgrade_swap: the mandatory upgrade persists and cannot be removed via the optional swap."""

import pytest

from battle_dice.core import commands as cmd
from battle_dice.core.models import RunPhase
from battle_dice.core.view import snapshot
from tests.conftest import begin_hero, last_event, ok, rejected, start, unit, win_battle


def _won(*party, seed=1):
    engine = start(*party, seed=seed)
    win_battle(engine)
    assert engine.state.phase == RunPhase.UPGRADE
    return engine


def test_t13_upgrade_is_mandatory_before_battle_two():
    engine = _won("squire", "scout")
    rejected(engine.do(cmd.ADVANCE_PHASE), "upgrade must be chosen")
    rejected(engine.do(cmd.SWAP_DIE, hero_id="h01", out_die_id="oath_d4", in_die_id="bulwark_d4"), "after the mandatory upgrade")
    rejected(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="iron_d6", offer_id="h01:iron_d6:9"), "not offered")
    rejected(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="striker_d8", offer_id="h01:iron_d6:1"), "does not have die")
    rejected(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h02", die_id="striker_d8", offer_id="h01:iron_d6:1"), "not offered")
    assert engine.state.phase == RunPhase.UPGRADE and engine.state.upgrades == []


@pytest.mark.parametrize("party", [("squire",), ("apprentice",), ("scout",), ("squire", "apprentice", "scout")])
def test_t13_three_valid_offers_per_equipped_die(party, content):
    engine = _won(*party, seed=9)
    cap = content.balance["upgrades"]["face_power_cap"]
    for hero_id, dice in engine.state.upgrade_offers.items():
        hero = unit(engine, hero_id)
        assert sorted(dice) == sorted(hero.equipped_dice_ids)
        for die_id, offers in dice.items():
            die = engine.die_for(hero_id, die_id)
            assert len(offers) == 3
            assert len({(o["kind"], o["face_index"], o["after"]["id"]) for o in offers}) == 3
            for offer in offers:
                before, after = offer["before"], offer["after"]
                assert 0 <= offer["face_index"] < die.size
                assert before["id"] == die.faces[offer["face_index"]].id
                assert after["power"] <= cap
                if offer["kind"] == "sharpen":
                    assert before["category"] != "blank" and after["category"] == before["category"]
                    status = [e for e in before["effects"] if e["type"] == "apply_status"]
                    if status:  # Poison / Weaken: +1 duration, never stack magnitude
                        new_status = [e for e in after["effects"] if e["type"] == "apply_status"][0]
                        assert new_status["duration"] == status[0]["duration"] + 1 and after["power"] == before["power"]
                    else:
                        assert after["power"] == before["power"] + 1
                elif offer["kind"] == "reforge":
                    assert before["category"] == "blank" and after["category"] in ("attack", "defense", "resource")
                    assert after["id"] in content.upgrades["reforge_faces"][hero.archetype_id]
                else:
                    assert after["id"] in content.upgrades["imbue_faces"][hero.archetype_id]
    if "squire" in party:  # oath_d4 has no Blank, so Reforge is replaced by the next valid option
        assert "reforge" not in [o["kind"] for o in engine.state.upgrade_offers["h01"]["oath_d4"]]
        assert "reforge" in [o["kind"] for o in engine.state.upgrade_offers["h01"]["iron_d6"]]


def test_t13_offers_are_seeded_and_can_be_forced_for_fixtures():
    assert _won("squire", "scout", seed=4).state.upgrade_offers == _won("squire", "scout", seed=4).state.upgrade_offers

    engine = start("squire")
    engine.force_draws("rewards", [2])  # first rewards draw rotates h01/iron_d6's Sharpen order to face 3
    win_battle(engine)
    sharpen = engine.state.upgrade_offers["h01"]["iron_d6"][0]
    assert (sharpen["kind"], sharpen["face_index"], sharpen["before"]["name"]) == ("sharpen", 2, "Guard")
    assert sharpen["after"]["power"] == 4


def test_t13_upgrade_creates_a_versioned_die_for_that_hero_only(content):
    engine = _won("squire", "squire")
    offer = engine.state.upgrade_offers["h01"]["iron_d6"][0]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="iron_d6", offer_id=offer["offer_id"]))
    assert engine.state.phase == RunPhase.EQUIPMENT
    upgraded = engine.die_for("h01", "iron_d6")
    assert upgraded.definition_version == 2 and upgraded.size == 6 and len(upgraded.faces) == 6
    assert upgraded.faces[offer["face_index"]].id == offer["after"]["id"]
    changed = [i for i in range(6) if upgraded.faces[i].signature() != content.die("iron_d6").faces[i].signature()]
    assert changed == [offer["face_index"]]
    assert engine.die_for("h02", "iron_d6") is content.die("iron_d6")  # the other Squire is untouched
    assert content.die("iron_d6").definition_version == 1  # the catalog definition is never mutated
    applied = last_event(engine, "upgrade_applied").delta
    assert (applied["from_version"], applied["to_version"]) == (1, 2)
    rejected(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h02", die_id="iron_d6", offer_id="h02:iron_d6:1"), "only be chosen once")
    assert len(engine.state.upgrades) == 1


def test_t13_optional_swap_cannot_remove_the_upgrade():
    engine = _won("squire", "scout")
    offer = engine.state.upgrade_offers["h01"]["iron_d6"][0]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="iron_d6", offer_id=offer["offer_id"]))

    view = snapshot(engine)["upgrade"]["heroes"][0]
    assert [(e["die"]["id"], e["locked"]) for e in view["equipped"]] == [("iron_d6", True), ("oath_d4", False)]
    assert {s["out_die_id"]: s["allowed"] for s in view["bench"][0]["swaps"]} == {"iron_d6": False, "oath_d4": True}

    rejected(engine.do(cmd.SWAP_DIE, hero_id="h01", out_die_id="iron_d6", in_die_id="bulwark_d4"), "locked")
    rejected(engine.do(cmd.SWAP_DIE, hero_id="h01", out_die_id="oath_d4", in_die_id="venom_d4"), "not on")
    rejected(engine.do(cmd.SWAP_DIE, hero_id="h02", out_die_id="tools_d4", in_die_id="bulwark_d4"), "not on")
    rejected(engine.do(cmd.SWAP_DIE, hero_id="h01", out_die_id="striker_d8", in_die_id="bulwark_d4"), "does not have die")

    ok(engine.do(cmd.SWAP_DIE, hero_id="h01", out_die_id="oath_d4", in_die_id="bulwark_d4"))
    hero = unit(engine, "h01")
    assert hero.equipped_dice_ids == ["iron_d6", "bulwark_d4"] and len(hero.equipped_dice_ids) == 2
    assert engine.state.inventory["h01"] == ["oath_d4"]
    assert engine.die_for("h01", "iron_d6").definition_version == 2  # the upgrade survived the swap
    assert engine.state.swaps_used == {"h01": 1}

    # One swap per hero (rules 1.1.0): the same hero cannot swap again, not even back.
    rejected(engine.do(cmd.SWAP_DIE, hero_id="h01", out_die_id="bulwark_d4", in_die_id="oath_d4"), "already used its optional swap")
    after = snapshot(engine)["upgrade"]
    assert [h["swaps_remaining"] for h in after["heroes"]] == [0, 1] and after["swaps_remaining"] == 1
    assert all(not s["allowed"] for s in after["heroes"][0]["bench"][0]["swaps"])
    assert cmd.SWAP_DIE in engine.permissible_commands()

    # A different hero still has its own swap.
    ok(engine.do(cmd.SWAP_DIE, hero_id="h02", out_die_id="tools_d4", in_die_id="venom_d4"))
    assert unit(engine, "h02").equipped_dice_ids == ["striker_d8", "venom_d4"]
    assert engine.state.inventory["h02"] == ["tools_d4"]
    assert engine.state.swaps_used == {"h01": 1, "h02": 1}
    assert cmd.SWAP_DIE not in engine.permissible_commands()  # every hero has used its swap
    assert engine.die_for("h01", "iron_d6").definition_version == 2

    ok(engine.do(cmd.ADVANCE_PHASE))
    begin_hero(engine, "h01", bulwark_d4=3, iron_d6=offer["face_index"] + 1)
    rolled = {d["die_id"]: d["face"]["name"] for d in snapshot(engine)["hero_turn"]["dice"]}
    assert rolled == {"bulwark_d4": "Tend", "iron_d6": offer["after"]["name"]}
    rejected(engine.do(cmd.SWAP_DIE, hero_id="h01", out_die_id="bulwark_d4", in_die_id="oath_d4"), "between battles")


def test_t13_swap_is_optional_and_a_new_run_has_no_upgrade():
    engine = _won("scout")
    offer = engine.state.upgrade_offers["h01"]["tools_d4"][0]
    ok(engine.do(cmd.CHOOSE_UPGRADE, hero_id="h01", die_id="tools_d4", offer_id=offer["offer_id"]))
    ok(engine.do(cmd.ADVANCE_PHASE))  # zero swaps is allowed
    assert engine.state.phase == RunPhase.BATTLE and engine.state.swaps_used == {}

    retry = start("scout")  # Retry Same Party / Modify Party both begin a brand-new run
    assert retry.state.upgrades == [] and retry.state.die_overrides == {}
    assert retry.die_for("h01", "tools_d4").definition_version == 1
    assert unit(retry, "h01").equipped_dice_ids == ["striker_d8", "tools_d4"]
