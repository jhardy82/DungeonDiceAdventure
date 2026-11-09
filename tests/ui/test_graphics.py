"""Pixel-art assets, whole-number scaling and presentation-only animation."""

from __future__ import annotations

import os

for _variable in ("SDL_VIDEODRIVER", "SDL_AUDIODRIVER"):
    if not os.environ.get(_variable):
        os.environ[_variable] = "dummy"

from importlib import resources  # noqa: E402

import pygame  # noqa: E402
import pytest  # noqa: E402

from battle_dice.app.controller import AppController, Screen  # noqa: E402
from battle_dice.core.events import state_hash  # noqa: E402
from battle_dice.sim.policies import HeuristicPolicy  # noqa: E402
from battle_dice.ui.animation import Animator  # noqa: E402
from battle_dice.ui.app import GameApp  # noqa: E402
from battle_dice.ui.artwork import AssetStore  # noqa: E402

ASSETS = resources.files("battle_dice.ui").joinpath("assets")


@pytest.fixture()
def store():
    pygame.display.init()
    pygame.display.set_mode((64, 64))
    return AssetStore()


def start_battle(tmp_path, size=(1280, 720), animations=True):
    controller = AppController(fixed_seed=7, log_dir=tmp_path / "logs")
    app = GameApp(controller, size=size, headless=True, animations=animations)
    controller.new_run()
    for class_id in ("squire", "apprentice", "scout"):
        controller.add_hero(class_id)
    controller.begin_run()
    app.frame(0)
    return app, controller


# --------------------------------------------------------------------------------------------
# Manifest and licences
# --------------------------------------------------------------------------------------------


def test_every_manifest_sprite_loads_as_16x16_pixel_art(store):
    assert store.load_all() == len(store.keys()) == 23
    assert store.missing == set()
    for key in store.keys():
        surface = store.base(key)
        assert surface.get_size() == (16, 16), key
        assert surface.get_flags() & pygame.SRCALPHA, key


def test_sprite_folder_and_manifest_list_exactly_the_same_files(store):
    on_disk = sorted(p.name for p in ASSETS.joinpath("sprites").iterdir() if p.name.endswith(".png"))
    listed = sorted(entry["file"] for entry in store.manifest["sprites"].values())
    assert on_disk == listed


def test_every_game_concept_has_a_sprite(store, content):
    sprites = set(store.keys())
    for archetype in list(content.classes) + list(content.enemies):
        assert store.combatant_key(archetype) in sprites, archetype
    for category in ("attack", "defense", "healing", "status", "resource"):
        assert store.category_key(category) in sprites
    assert store.category_key("blank") is None  # a Blank face shows no action icon
    for kind in content.balance["statuses"]:
        assert store.status_key(kind) in sprites
    for die in content.dice.values():
        assert store.die_key(die.size) in sprites
    backdrop = store.manifest["backdrop"]
    assert set(backdrop["floor"]) | {backdrop["wall"]} <= sprites


def test_third_party_art_is_cc0_and_credited(store):
    manifest = store.manifest
    credits = ASSETS.joinpath("CREDITS.md").read_text(encoding="utf-8")
    used_sources = {entry["source"] for entry in manifest["sprites"].values()}
    assert used_sources == {"kenney-tiny-dungeon", "original"}
    kenney = manifest["sources"]["kenney-tiny-dungeon"]
    assert kenney["licence"] == "CC0 1.0" and "Kenney" in kenney["author"]
    assert "Tiny Dungeon" in credits and "Creative Commons Zero" in credits and kenney["url"] in credits
    for key, entry in manifest["sprites"].items():
        assert f"`{key}`" in credits, f"{key} is not credited"
        if entry["source"] == "kenney-tiny-dungeon":
            assert isinstance(entry["tile"], int)
    assert manifest["sprites"]["enemy_goblin"]["modified"]  # the recolour is declared


# --------------------------------------------------------------------------------------------
# Whole-number scaling
# --------------------------------------------------------------------------------------------


def test_fit_scale_is_always_a_whole_number_of_at_least_one():
    assert AssetStore.fit_scale((16, 16), (44, 44)) == 2
    assert AssetStore.fit_scale((16, 16), (33, 33)) == 2
    assert AssetStore.fit_scale((16, 16), (31, 31)) == 1
    assert AssetStore.fit_scale((16, 16), (96, 96)) == 6
    assert AssetStore.fit_scale((16, 16), (5, 5)) == 1  # never zero: a too-small slot still draws at 1x
    assert AssetStore.fit_scale((16, 16), (200, 40)) == 2


def test_scaled_sprites_are_exact_multiples_and_cached(store):
    for scale in (1, 2, 3, 6):
        surface = store.scaled("hero_squire", scale)
        assert surface.get_size() == (16 * scale, 16 * scale)
    assert store.scaled("hero_squire", 3) is store.scaled("hero_squire", 3)
    grey = store.scaled("hero_squire", 2, "grey")
    pixel = grey.get_at((16, 16))
    assert pixel.r == pixel.g == pixel.b
    # Nearest-neighbour: every 2x2 block of the enlarged sprite is one flat colour.
    doubled, base = store.scaled("enemy_goblin", 2), store.base("enemy_goblin")
    for x in range(16):
        for y in range(16):
            assert doubled.get_at((2 * x, 2 * y)) == doubled.get_at((2 * x + 1, 2 * y + 1)) == base.get_at((x, y))


@pytest.mark.parametrize("size, expected", [((1280, 720), 2), ((960, 540), 2), ((1920, 1080), 4)])
def test_combatant_sprites_use_a_whole_number_scale_at_each_window_size(tmp_path, size, expected):
    app, _ = start_battle(tmp_path, size=size)
    ui = app.ui
    ui.begin(app.surface)
    assert ui.sprite("hero_squire", 3, 21, 44, 44) == expected
    ui.end()


def test_a_missing_sprite_draws_a_placeholder_and_never_raises(tmp_path):
    app, _ = start_battle(tmp_path)
    ui = app.ui
    ui.begin(app.surface)
    assert ui.sprite("no_such_sprite", 10, 10, 40, 40) == 0
    assert ui.sprite(None, 10, 10, 40, 40) == 0
    ui.end()
    assert ui.assets.missing == {"no_such_sprite"}
    assert ui.assets.scaled("no_such_sprite", 2) is None


def test_a_full_run_references_only_sprites_that_exist(tmp_path):
    app, controller = start_battle(tmp_path)
    engine, policy = controller.engine, HeuristicPolicy()
    seen = set()
    while not engine.finished():
        if engine.needs_input():
            policy.act(engine)
        else:
            engine.do("AdvancePhase")
        controller.refresh()
        app.frame(30)
        seen.add(controller.screen)
    app.frame(30)
    assert {Screen.BATTLE, Screen.OUTCOME} <= seen
    assert app.ui.assets.missing == set()


# --------------------------------------------------------------------------------------------
# Animation is presentation-only
# --------------------------------------------------------------------------------------------


class FakeEvent:
    def __init__(self, kind, delta, actor_id=None):
        self.type, self.delta, self.actor_id = kind, delta, actor_id


class FakeEngine:
    started = True

    def __init__(self):
        self.events = []


def test_events_become_floating_numbers():
    animator, engine = Animator(), FakeEngine()
    animator.sync(engine)  # first sight of a run: history is not replayed
    engine.events.append(FakeEvent("action_resolved", {"results": [
        {"type": "damage", "target": "b1_e01", "hp_damage": 2, "absorbed": 1},
        {"type": "shield", "target": "h01", "gained": 3},
        {"type": "heal", "target": "h02", "healed": 2, "revived": False},
        {"type": "apply_status", "target": "b1_e01", "status": "poison", "applied": [{"result": "applied"}]},
        {"type": "gain_mana", "target": "h03", "gained": 1},
        {"type": "gain_mana", "target": "h03", "gained": 0},
    ]}, actor_id="h01"))
    engine.events.append(FakeEvent("poison_tick", {"hp_damage": 1}, actor_id="b1_e01"))
    engine.events.append(FakeEvent("combatant_downed", {"id": "h02"}))
    animator.sync(engine)
    texts = [(f.target_id, f.text) for f in animator.floaters]
    assert texts == [
        ("b1_e01", "-2"), ("b1_e01", "blocked 1"), ("h01", "+3 SH"), ("h02", "+2"), ("b1_e01", "PSN"),
        ("h03", "+1 MP"), ("b1_e01", "-1"), ("h02", "DOWNED"),
    ]
    assert [f.lane for f in animator.floaters if f.target_id == "b1_e01"] == [0, 1, 2, 3]  # stacked, not overlapping
    animator.sync(engine)
    assert len(animator.floaters) == 8  # the same events are never consumed twice
    animator.update(animator.float_ms + 1)
    assert animator.floaters == [] and not animator.busy()


def test_dice_tumble_cycles_faces_then_settles_on_the_real_result():
    animator, engine = Animator(), FakeEngine()
    animator.sync(engine)
    engine.events.append(FakeEvent("dice_rolled", {"die_id": "iron_d6"}, actor_id="h01"))
    animator.sync(engine)
    assert animator.is_tumbling("iron_d6")
    shown = set()
    for _ in range(6):
        shown.add(animator.tumbling_face("iron_d6", 6, 3))
        animator.update(60)
    assert len(shown) > 2 and all(0 <= face < 6 for face in shown)
    animator.update(animator.tumble_ms)
    assert not animator.is_tumbling("iron_d6")
    assert animator.tumbling_face("iron_d6", 6, 3) == 3


def test_hp_bar_eases_toward_the_real_value():
    animator = Animator()
    animator.update(16, {"h01": 14})
    assert animator.shown_hp("h01", 14) == 14.0
    animator.update(16, {"h01": 6})
    first = animator.shown_hp("h01", 6)
    assert 6 < first < 14
    for _ in range(200):
        animator.update(16, {"h01": 6})
    assert animator.shown_hp("h01", 6) == 6.0
    animator.update(16, {})
    assert "h01" not in animator.display_hp


def test_reduced_motion_shows_final_values_immediately():
    animator, engine = Animator(enabled=False), FakeEngine()
    animator.sync(engine)
    engine.events.append(FakeEvent("dice_rolled", {"die_id": "iron_d6"}))
    engine.events.append(FakeEvent("combatant_downed", {"id": "h01"}))
    animator.sync(engine)
    animator.update(16, {"h01": 3})
    assert animator.active_floaters() == [] and not animator.is_tumbling("iron_d6")
    assert animator.tumbling_face("iron_d6", 6, 2) == 2
    assert animator.shown_hp("h01", 3) == 3.0 and animator.pulse() == 1.0


def test_fast_mode_shortens_animations():
    animator = Animator()
    normal = (animator.float_ms, animator.tumble_ms)
    animator.fast = True
    assert animator.float_ms < normal[0] and animator.tumble_ms < normal[1]


def test_animation_never_changes_rules_state_or_random_streams(tmp_path):
    app, controller = start_battle(tmp_path)
    engine = controller.engine
    while not engine.needs_input():
        engine.do("AdvancePhase")
    engine.do("RollDice")
    controller.refresh()
    before = (state_hash(engine.state), len(engine.events), len(engine.command_log),
              {name: stream.draws for name, stream in engine.state.rng.items()})
    saw_tumble = False
    for _ in range(40):
        app.frame(33)
        saw_tumble = saw_tumble or bool(app.ui.anim.tumbles)
    assert saw_tumble
    after = (state_hash(engine.state), len(engine.events), len(engine.command_log),
             {name: stream.draws for name, stream in engine.state.rng.items()})
    assert after == before


def test_m_key_toggles_animation_and_the_flag_starts_it_off(tmp_path):
    app, controller = start_battle(tmp_path)
    assert app.ui.anim.enabled
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m, mod=0, unicode="m"))
    assert not app.ui.anim.enabled and "reduced motion" in controller.message
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m, mod=0, unicode="m"))
    assert app.ui.anim.enabled

    quiet, _ = start_battle(tmp_path, animations=False)
    assert not quiet.ui.anim.enabled


def test_backdrop_is_drawn_and_cached_per_window_size(tmp_path):
    app, _ = start_battle(tmp_path)
    ui = app.ui
    app.frame(0)
    assert (1280, 394, 1) in ui._backdrops  # the battle backdrop, keyed by its pixel size
    cached = dict(ui._backdrops)
    colours = {tuple(app.surface.get_at((x, y)))[:3] for x in range(10, 470, 3) for y in range(200, 460, 3)}
    assert len(colours) > 2  # tiled floor with speckled and rubble tiles, not a flat fill
    wall = {tuple(app.surface.get_at((x, 84)))[:3] for x in range(10, 470, 3)}
    assert wall and not wall <= colours  # the top row is the wall tile, a different palette
    for _ in range(5):
        app.frame(16)
    assert ui._backdrops == cached  # redrawn frames reuse the cached surface
    assert all(ui._backdrops[key] is cached[key] for key in cached)


def test_status_badges_and_text_are_both_drawn_on_a_card(tmp_path):
    from battle_dice.core.models import StatusInstance

    app, controller = start_battle(tmp_path)
    engine = controller.engine
    hero = engine.combat.combatants["h01"]
    hero.status_instances.append(StatusInstance("st9001", "poison", "test", "h01", 1, 2, 0))
    hero.status_instances.append(StatusInstance("st9002", "weaken", "test", "h01", 1, 2, 0))
    used: list[str] = []
    original = app.ui.sprite

    def recording(key, *args, **kwargs):
        used.append(key)
        return original(key, *args, **kwargs)

    app.ui.sprite = recording
    app.frame(0)
    assert {"status_poison", "status_weaken"} <= set(used)
    view = next(c for c in controller.view()["combatants"] if c["id"] == "h01")
    assert [s["glyph"] for s in view["statuses"]] == ["PSN", "WKN"]  # the text cue is still produced
    assert app.ui.assets.missing == set()
