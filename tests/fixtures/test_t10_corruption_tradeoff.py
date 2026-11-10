"""T10_corruption_tradeoff: Apprentice damage bonus at the threshold and backlash at the higher threshold."""

from tests.conftest import action, begin_hero, events_of, last_event, resolve_hero, start, unit


def _cast(corruption, shields=0, hp=9):
    engine = start("apprentice", "squire")  # goblin b1_e01, hex adept b1_e02
    hero = unit(engine, "h01")
    hero.corruption, hero.shields, hero.hp = corruption, shields, hp
    begin_hero(engine, "h01", arcane_d6=1, focus_d4=4)
    resolve_hero(engine, action("arcane_d6", "b1_e02"))
    return engine, hero


def test_t10_arcane_resonance_applies_at_three_corruption():
    engine, hero = _cast(corruption=2)
    result = events_of(engine, "action_resolved")[0].delta["results"][0]
    assert (result["base"], result["bonus"], result["effective"]) == (3, 0, 3)
    assert hero.corruption == 3 and unit(engine, "b1_e02").hp == 4

    engine, hero = _cast(corruption=3)
    result = events_of(engine, "action_resolved")[0].delta["results"][0]
    assert (result["bonus"], result["effective"]) == (1, 4)
    assert hero.corruption == 4 and unit(engine, "b1_e02").hp == 3
    assert events_of(engine, "corruption_backlash") == []  # 4 is below the backlash threshold


def test_t10_backlash_at_five_bypasses_shields_after_actions_resolve():
    engine, hero = _cast(corruption=4, shields=6)
    assert hero.corruption == 5
    assert (hero.hp, hero.shields) == (8, 6)
    backlash = last_event(engine, "corruption_backlash")
    assert backlash.delta["hp_damage"] == 1 and backlash.delta["absorbed"] == 0
    order = [e.type for e in engine.events if e.type in ("action_resolved", "corruption_backlash", "activation_ended")]
    assert order[-3:] == ["action_resolved", "corruption_backlash", "activation_ended"]


def test_t10_backlash_repeats_every_activation_until_cleansed():
    engine = start("apprentice", "squire")
    hero = unit(engine, "h01")
    hero.corruption = 6
    begin_hero(engine, "h01", arcane_d6=6, focus_d4=4)
    resolve_hero(engine)  # pass: backlash still applies
    assert hero.hp == 8
    begin_hero(engine, "h01", arcane_d6=5, focus_d4=4)  # Cleanse: 6 -> 4
    resolve_hero(engine, action("arcane_d6"))
    assert (hero.corruption, hero.hp) == (4, 8)
    assert len(events_of(engine, "corruption_backlash")) == 1


def test_t10_backlash_can_down_the_caster_and_applies_to_any_class():
    engine, hero = _cast(corruption=4, hp=1)
    assert hero.state == "downed" and last_event(engine, "combatant_downed").delta["id"] == "h01"

    squire_run = start("squire", "scout")
    squire = unit(squire_run, "h01")
    squire.corruption = 5
    begin_hero(squire_run, "h01", iron_d6=6, oath_d4=1)
    resolve_hero(squire_run)
    assert squire.hp == 13
