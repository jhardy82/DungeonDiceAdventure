"""Upgrade cards that change nothing are not cards (rules 1.1.2, owner decision D-34).

A playtester was offered "Strike: 3 melee damage" to "Heavy Blow: 3 melee damage" as one of the three
cards of the one mandatory upgrade. The two faces differ in their name and in nothing the rules read.
"""

from __future__ import annotations

from battle_dice.core.engine import Engine
from battle_dice.core.models import RunPhase, to_plain
from tests.conftest import packaged_content, start, win_battle


def _won(*party: str, seed: int = 1) -> Engine:
    """Battle 1 of the shipped game is won: the upgrade cards are dealt."""
    engine = start(*party, seed=seed, content=packaged_content())
    win_battle(engine)
    assert engine.state.phase == RunPhase.UPGRADE
    return engine


# --------------------------------------------------------------------------------------------
# Rules 1.1.2 (owner decision D-34): an Imbue card that changes nothing but a name is not offered
# --------------------------------------------------------------------------------------------


def _same_but_for_the_name(offer: dict) -> bool:
    before, after = offer["before"], offer["after"]
    keys = ("category", "power", "target_scope", "range_type", "action_speed", "mana_cost", "can_revive", "effects")
    return all(before[key] == after[key] for key in keys) and sorted(before["tags"]) == sorted(after["tags"])


def test_two_faces_with_other_names_and_the_same_mechanics_are_the_same_to_the_rules():
    from battle_dice.core.models import FaceDefinition

    content = packaged_content()
    strike = content.die("iron_d6").faces[0]
    heavy_blow = content.upgrade_faces["im_sq_heavy_blow"]
    assert (strike.name, heavy_blow.name) == ("Strike", "Heavy Blow") and strike.signature() != heavy_blow.signature()
    assert strike.mechanics() == heavy_blow.mechanics(), "3 melee damage, by either name"
    guard, bulwark = content.die("iron_d6").faces[2], content.upgrade_faces["im_sq_bulwark"]
    assert guard.mechanics() != bulwark.mechanics(), "Guard gives 3 shield, Bulwark 4"
    spell = FaceDefinition(**{**to_plain(strike), "tags": ["melee", "spell"]})
    assert spell.mechanics() != strike.mechanics(), "a tag the rules read makes another face"


def test_no_offered_card_changes_nothing_but_a_name():
    """Under rules 1.1.1 about one card in seventy did (21 of 1,440 over these seeds and parties)."""
    seen = empty = 0
    for seed in range(300, 340):
        for party in (["squire"], ["squire", "scout"], ["squire", "apprentice", "scout"]):
            engine = _won(*party, seed=seed)
            for dice in engine.state.upgrade_offers.values():
                for offers in dice.values():
                    assert len(offers) == 3, "the next valid card takes the place of the one that is not offered"
                    seen += len(offers)
                    empty += sum(_same_but_for_the_name(offer) for offer in offers)
    assert seen >= 1000 and empty == 0


def test_the_card_that_is_not_offered_any_more_was_offered_before(monkeypatch):
    """The same seeds under the old rule, where the name alone made a face another face."""
    from battle_dice.core.models import FaceDefinition

    monkeypatch.setattr(FaceDefinition, "mechanics", FaceDefinition.signature)
    found = None
    for seed in range(300, 340):
        engine = _won("squire", seed=seed)
        offers = [offer for dice in engine.state.upgrade_offers.values() for die in dice.values() for offer in die]
        found = next((offer for offer in offers if _same_but_for_the_name(offer)), None)
        if found is not None:
            break
    assert found is not None and (found["kind"], found["before"]["name"], found["after"]["name"]) == ("imbue", "Strike", "Heavy Blow")
    monkeypatch.undo()
    now = _won("squire", seed=seed).state.upgrade_offers[found["hero_id"]][found["die_id"]]
    replaced = next(offer for offer in now if offer["offer_id"] == found["offer_id"])
    assert not _same_but_for_the_name(replaced), "in its place stands a card that changes the die"
