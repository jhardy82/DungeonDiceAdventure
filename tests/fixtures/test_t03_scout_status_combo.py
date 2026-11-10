"""T03_scout_status_combo: Status resolves before Attack and the passive damage bonus applies."""

from tests.conftest import action, begin_hero, events_of, resolve_hero, start, unit


def test_t03_status_resolves_first_and_attack_gains_exploit_opening():
    engine = start("scout")
    begin_hero(engine, "h01", striker_d8=4, tools_d4=1)  # Poison + Quick Shot
    resolve_hero(engine, action("tools_d4", "b1_e01"), action("striker_d8", "b1_e01"))  # listed Attack first
    resolved = events_of(engine, "action_resolved")
    assert [e.delta["name"] for e in resolved] == ["Poison", "Quick Shot"]
    shot = resolved[1].delta["results"][0]
    assert (shot["base"], shot["bonus"], shot["effective"]) == (1, 1, 2)
    goblin = unit(engine, "b1_e01")
    assert goblin.hp == 4 and goblin.stacks_of("poison") == 1


def test_t03_attack_alone_gets_no_bonus():
    engine = start("scout")
    begin_hero(engine, "h01", striker_d8=4, tools_d4=1)
    resolve_hero(engine, action("tools_d4", "b1_e01"))
    shot = events_of(engine, "action_resolved")[0].delta["results"][0]
    assert (shot["bonus"], shot["effective"]) == (0, 1)
    assert unit(engine, "b1_e01").hp == 5


def test_t03_weaken_combo_also_grants_the_bonus_and_targets_may_differ():
    engine = start("scout", "scout")  # goblin b1_e01, hex adept b1_e02
    begin_hero(engine, "h01", striker_d8=6, tools_d4=2)  # Hamstring (Weaken) + Quick Shot
    resolve_hero(engine, action("striker_d8", "b1_e01"), action("tools_d4", "b1_e02"))
    assert unit(engine, "b1_e01").stacks_of("weaken") == 1
    assert unit(engine, "b1_e02").hp == 7 - 2
