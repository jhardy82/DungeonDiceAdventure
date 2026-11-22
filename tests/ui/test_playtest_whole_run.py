"""What a fifth AI playtester found by playing two whole runs (2026-11-21, after the second round), fixed here.

The findings are in ``docs/PLAYTEST_TEAM_2026-11-21.md``, section 8. One was a defect with a cause worth a
name: an enemy action's id counts the actions of one *battle*, and two readers took it for an id of the run.
"""

from __future__ import annotations

import pygame
import pytest

from battle_dice.app.controller import AppController, Screen
from battle_dice.career import evidence
from battle_dice.career.model import MasteryRow
from battle_dice.core import commands as cmd
from battle_dice.core import skills as battle_skills
from battle_dice.core.events import EventType
from battle_dice.core.models import CombatPhase
from battle_dice.core.view import battle_title, snapshot
from battle_dice.phone import screens as phone
from battle_dice.sim.policies import HeuristicPolicy
from battle_dice.ui import screens
from battle_dice.ui.toolkit import UI
from tests.conftest import force_slash, unit, win_battle
from tests.ui.test_evolution_ui import OPENED, Configured, Evolution, close_every_save  # noqa: F401 - the fixture closes the saves
from tests.ui.test_playtest_evolution import after_battle_one
from tests.ui.test_playtest_keys import engine_of, reacting
from tests.ui.test_ui_flow import SIZES, Play, font, record_text  # noqa: F401 - font is a fixture

STAGES = ("guard", "resource", "interrupt")


# --------------------------------------------------------------------------------------------
# F1: an enemy action's number starts again in every battle
# --------------------------------------------------------------------------------------------


def test_a_reaction_prompt_names_only_the_stages_of_its_own_enemy_action(tmp_path):
    """The playtester's run: in Battles 2 and 3 the prompt's header carried "no hero could react" notes of
    Battle 1's actions with the same number, piled them up, and showed them at a stage with a reaction on offer."""
    play = Play(tmp_path, ["squire", "scout", "scout"], seed=500)
    play.begin()
    engine, policy = engine_of(play), HeuristicPolicy()
    prompts = {1: 0, 2: 0}
    met_the_same_number_again = 0
    while not engine.finished():
        if not engine.needs_input():
            assert engine.do(cmd.ADVANCE_PHASE).accepted
            continue
        reaction = snapshot(engine)["reaction"]
        if reaction is not None:
            battle = engine.state.encounter_index + 1
            prompts[battle] += 1
            passed, stage = reaction["passed"], reaction["stage"]
            # Only stages before the one that is open, each once, in their order.
            assert passed == [name for name in STAGES[:STAGES.index(stage)] if name in passed], (battle, stage, passed)
            assert reaction["stage_number"] == STAGES.index(stage) + 1
            # What the header read before: every such note of the run that carries this action's number.
            by_number = [e.delta["stage"] for e in engine.events if e.type == EventType.REACTION_STAGE_SKIPPED
                         and e.intent_id == engine.combat.committed_intent.id and e.delta["reason"] == "no eligible reaction"]
            met_the_same_number_again += by_number != passed
        policy.act(engine)
    assert prompts[1] >= 2 and prompts[2] >= 4, prompts
    assert met_the_same_number_again > 0, "this run no longer meets an action number twice: the test needs another seed"


def test_the_header_of_a_guard_stage_never_says_no_hero_could_react_in_it(tmp_path, monkeypatch):
    """The same on the screen, with the notes of an earlier battle planted where the fault read them."""
    play = reacting(tmp_path)
    engine = engine_of(play)
    assert engine.combat.phase == CombatPhase.GUARD_WINDOW
    number = engine.combat.committed_intent.id
    selected = next(position for position, event in enumerate(engine.events) if event.type == EventType.INTENT_SELECTED and event.intent_id == number)
    before = engine.events[selected - 1]
    # An earlier battle's action with the same number, in which no hero could react at two stages.
    stale = [type(before)(seq=before.seq, tick=before.tick, actor_id=None, type=EventType.REACTION_STAGE_SKIPPED, intent_id=number,
                          before={}, delta={"stage": stage, "reason": "no eligible reaction"}, after={}) for stage in ("guard", "resource")]
    started = next(position for position, event in enumerate(engine.events) if event.type == EventType.BATTLE_STARTED)
    engine.events[started:started] = stale
    assert snapshot(engine)["reaction"]["passed"] == []
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert "Reaction window: stage 1 of 3: Guard   (Guard -> Resource -> Interrupt -> enemy action)" in drawn
    assert not [text for text in drawn if "no hero could react" in text]


def test_a_stage_the_player_skipped_is_not_one_in_which_no_hero_could_react(tmp_path, monkeypatch):
    play = reacting(tmp_path)
    play.ctrl.skip_stage()   # Interpose was on offer: the player let the Guard stage go
    play.app.frame(0)
    reaction = play.ctrl.view()["reaction"]
    assert (reaction["stage"], reaction["passed"]) == ("resource", [])
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert "Reaction window: stage 2 of 3: Resource   (Guard -> Resource -> Interrupt -> enemy action)" in drawn


def test_the_first_reaction_on_an_action_is_never_asked_for_twice_because_of_an_earlier_battle(tmp_path):
    """The same cause, found by reading: the controller remembered the *number* of the action it had reacted to.
    The same dice give the same numbers, so a new run's action with that number had its first reaction asked for
    twice ("A reaction was just used on this enemy action") although none had been used on it."""
    play = reacting(tmp_path)
    first_run = engine_of(play)
    number = first_run.combat.committed_intent.id
    play.key(pygame.K_1)
    assert len(first_run.combat.reactions_used) == 1

    play.ctrl.begin_run()  # the same party and the same dice again
    play.app.frame(0)
    engine = engine_of(play)
    assert engine is not first_run
    force_slash(engine)
    for hero_id in ("h01", "h02"):
        unit(engine, hero_id).corruption = 2
        unit(engine, hero_id).mana = 1
    play.until(lambda: play.ui.widget("react:h01") is not None and play.ui.widget("react:h01").enabled)
    assert engine.combat.committed_intent.id == number, "the arrangement gives the same action number again"
    assert engine.combat.reactions_used == []
    play.key(pygame.K_1)
    assert len(engine.combat.reactions_used) == 1 and not play.ctrl.question_open(), play.ctrl.message
    assert play.ctrl.message.startswith("Interpose used on ")


def test_a_second_reaction_that_waits_for_its_second_press_says_so_on_its_button(tmp_path, monkeypatch):
    """F10: only the status bar said it; the swap and the retry say it on the button as well."""
    play = reacting(tmp_path)
    play.key(pygame.K_1)   # Interpose: the first reaction on this enemy action
    play.key(pygame.K_1)   # Grounding, in the next stage: asked for once more
    assert play.ctrl.asked("react:h02") and len(play.combat.reactions_used) == 1
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    assert "Press again: Grounding" in drawn and "1. Grounding (Apprentice 2)" not in drawn and shortened == []
    play.key(pygame.K_1)
    assert len(play.combat.reactions_used) == 2
    drawn.clear()
    play.app.frame(0)
    assert not [text for text in drawn if text.startswith("Press again")]


def test_an_ally_button_that_waits_for_its_second_press_says_so_too(tmp_path, monkeypatch):
    play = reacting(tmp_path)
    play.key(pygame.K_1)
    play.click("react:h02:h01")
    assert play.ctrl.asked("react:h02:h01") and len(play.combat.reactions_used) == 1
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert drawn.count("Press again") == 1 and "Squire 1" in drawn, "the one button that was pressed says it; the hero is still named on its card"
    play.click("react:h02:h01")
    assert len(play.combat.reactions_used) == 2


# --------------------------------------------------------------------------------------------
# F2, F6, F11: the upgrade screen
# --------------------------------------------------------------------------------------------


def test_the_upgrade_screen_says_whose_cards_it_shows(tmp_path, monkeypatch):
    """F2: the three cards are one die's; the playtester chose the run's one upgrade without knowing that
    every other die had three more."""
    play = Play(tmp_path, ["squire", "scout"])
    after_battle_one(play)
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    assert "Step 1 of 2: choose one upgrade for one die (required)." in drawn
    assert "Upgrade cards: Squire 1, Iron d6" in drawn
    assert "These are this die's cards. Every die of every hero has its own three: choose a hero and a die on the left." in drawn
    drawn.clear()
    play.click("up:hero:h02")
    play.click("up:die:tools_d4")
    play.app.frame(0)
    assert "Upgrade cards: Scout 2, Tools d4" in drawn and "Upgrade cards: Squire 1, Iron d6" not in drawn
    assert play.ui.widget("up:die:tools_d4").tooltip == "Show the three upgrade cards for this die. Every die has its own three."
    assert shortened == []


def test_an_applied_upgrade_is_said_to_last_until_the_run_ends(tmp_path, monkeypatch):
    """F6: "through Battle 2" was wrong for a run with a third battle, where the die kept its upgrade."""
    play = Play(tmp_path, ["squire"])
    after_battle_one(play)
    play.key(pygame.K_1)
    play.key(pygame.K_a)
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    applied = next(text for text in drawn if " was applied to Squire 1's " in text)
    assert applied.endswith("It lasts until the run ends.") and "Battle 2" not in applied


@pytest.mark.parametrize("size", SIZES)
def test_what_recovery_gave_is_on_the_heros_button(tmp_path, monkeypatch, font, size):  # noqa: F811
    """F11: it was only in the status bar while the hero was pointed at. Every font shows one wording of it."""
    play = Play(tmp_path, ["squire", "scout"], size=size)
    play.ctrl.begin_run()
    engine = engine_of(play)
    unit(engine, "h01").hp = 3
    win_battle(engine)
    play.ctrl.refresh()
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    now, top = unit(engine, "h01").hp, unit(engine, "h01").max_hp
    assert now > 3
    wordings = [f"HP {now}/{top} (was 3)  MP 3  CR 0", f"HP {now}/{top} (+{now - 3})  MP 3  CR 0", f"HP {now}/{top} (+{now - 3}) MP 3 CR 0"]
    assert len([text for text in drawn if text in wordings]) == 1, [text for text in drawn if text.startswith("HP ")]
    assert f"HP {now}/{top}  MP 3  CR 0" not in drawn and shortened == []
    # A hero that lost nothing has nothing to say.
    scout = unit(engine, "h02")
    assert f"HP {scout.hp}/{scout.max_hp}  MP {scout.mana}  CR 0" in drawn


# --------------------------------------------------------------------------------------------
# F3, F4, F8, F12: mastery, in words a player can use
# --------------------------------------------------------------------------------------------


def test_an_award_says_what_earned_the_bonus_and_which_skill_does_nothing_yet():
    line = AppController.award_line
    base = {"name": "Recruit 2", "rank_before": 3, "rank_after": 4, "denial_reason": None, "base_points": 1}
    scout = {**base, "challenge_points": 1, "challenge_id": "status_into_attack", "skills_learned": ["Scout Marksman"], "skills_waiting": ["Scout Marksman"]}
    assert line(scout) == "Recruit 2 +2 with the bonus (a Status die with an Attack die), now rank 4, learned Scout Marksman (no effect in this version yet)."
    # A skill the rules know is named plainly; no bonus, no words about one.
    medic = {**base, "challenge_points": 0, "challenge_id": "prevent_3_damage", "skills_learned": ["Guardian Field Medic"], "skills_waiting": []}
    assert line(medic) == "Recruit 2 +1, now rank 4, learned Guardian Field Medic."
    # Several skills: those the rules know first, then the others with one note between them; no skill twice.
    learned = AppController._learned_text
    assert learned([{"skills_learned": ["A", "B"], "skills_waiting": ["A", "B"]}]) == ", learned A and B (no effect in this version yet)"
    assert learned([{"skills_learned": ["A"], "skills_waiting": ["A"]}, {"skills_learned": ["K", "A"]}]) == ", learned K; A (no effect in this version yet)"
    assert learned([{"skills_learned": ["K", "L"], "skills_waiting": []}]) == ", learned K, L" and learned([{"skills_learned": []}]) == ""
    # A challenge without player words is still a bonus.
    assert line({**base, "challenge_points": 1, "challenge_id": "ritual_complete", "skills_learned": []}) == "Recruit 2 +2 with the bonus, now rank 4."


def test_every_vocation_that_can_be_played_has_its_bonus_in_player_words(tmp_path):
    play = Evolution(tmp_path)
    catalog = play.link.catalog
    playable = [vocation_id for vocation_id in catalog.vocations if play.ctrl.playable(vocation_id)]
    assert {"squire", "apprentice", "scout", "guardian", "ranger"} <= set(playable)
    for vocation_id in playable:
        assert play.link.bonus_challenge(vocation_id) in AppController.BONUS_CHALLENGES, vocation_id
    # The words describe what is counted: no challenge is worded that the evidence does not know.
    assert set(AppController.BONUS_CHALLENGES) == set(evidence.COUNTED)
    assert play.ctrl.bonus_text("scout") == "1 point for a won battle. 1 more when this hero plays a Status die and an Attack die in one activation."
    assert AppController(log_dir=tmp_path / "plain").bonus_text("scout") == ""


def test_the_career_screen_says_what_earns_mastery_and_what_master_means(tmp_path, monkeypatch):
    """F4 and F8. "+2 with the bonus" was explained nowhere, and "master Scout" only on one of the two ways in."""
    play = Evolution(tmp_path)
    after_battle_one(play)
    play.ctrl.open_career("hero_001")
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    assert play.ctrl.career_view()["in_run"], "opened from the upgrade screen, where the subtitle is about changing vocation"
    assert "1 point for a won battle. 1 more when a shield from this hero's Defense die takes damage for another ally." in drawn
    play.click("career:guardian:select")
    play.app.frame(0)
    assert "Needs: master Squire (rank 8; now rank 2)." in drawn
    assert "1 point for a won battle. 1 more when shields this hero gave another ally, by a Defense die or by its reaction, take 3 or more damage from one enemy action." in drawn
    play.click("career:champion:select")   # in the catalog, not in the rules yet: nothing is promised about its mastery
    play.app.frame(0)
    assert play.ctrl.career_view()["bonus"] == "" and shortened == [] and play.app.render_faults == 0


def test_a_learned_skill_the_rules_do_not_know_is_announced_as_such(tmp_path):
    """F3: "learned Scout Marksman" stood on the screen where the player decides whether to risk a harder battle."""
    play = Evolution(tmp_path, recruits=("scout", "squire"))
    scout = play.link.state.heroes["hero_001"]
    rank_three = play.link.catalog.thresholds("scout")[3]
    scout.mastery["scout"] = MasteryRow("scout", 3, rank_three - 1)
    play.ctrl.begin_run()
    win_battle(engine_of(play))
    play.ctrl.refresh()
    award = next(a for a in play.link.last_awards if a["hero_id"] == "hero_001")
    assert (award["rank_after"], award["skills_learned"], award["skills_waiting"]) == (4, ["Scout Marksman"], ["Scout Marksman"])
    assert award["challenge_id"] == "status_into_attack"
    assert play.ctrl.awards_view()[0].endswith("now rank 4, learned Scout Marksman (no effect in this version yet).")
    assert "learned Scout Marksman (no effect in this version yet)" in play.ctrl.mastery_line()
    # The next battle teaches nothing: the skill is not announced a second time, in words or in the record.
    engine = engine_of(play)
    offer = next(o for dice in engine.state.upgrade_offers.values() for die in dice.values() for o in die)
    assert engine.do(cmd.CHOOSE_UPGRADE, hero_id=offer["hero_id"], die_id=offer["die_id"], offer_id=offer["offer_id"]).accepted
    assert engine.do(cmd.ADVANCE_PHASE).accepted
    win_battle(engine)
    play.ctrl.refresh()
    later = next(a for a in play.link.last_awards if a["hero_id"] == "hero_001" and a["battle"] == 2)
    assert (later["skills_learned"], later["skills_waiting"]) == ([], [])


def test_the_note_goes_by_itself_when_the_rules_learn_the_skill(tmp_path, monkeypatch):
    monkeypatch.setattr(battle_skills, "KNOWN", (*battle_skills.KNOWN, "scout_marksman"))
    play = Evolution(tmp_path, recruits=("scout", "squire"))
    play.link.state.heroes["hero_001"].mastery["scout"] = MasteryRow("scout", 3, play.link.catalog.thresholds("scout")[3] - 1)
    play.ctrl.begin_run()
    win_battle(engine_of(play))
    play.ctrl.refresh()
    award = next(a for a in play.link.last_awards if a["hero_id"] == "hero_001")
    assert (award["skills_learned"], award["skills_waiting"]) == (["Scout Marksman"], [])
    assert play.ctrl.awards_view()[0].endswith("now rank 4, learned Scout Marksman.")


def test_the_outcome_gives_the_whole_runs_mastery_and_counts_its_battles(tmp_path, monkeypatch):
    """F5 and F12: "Both battles won." after three, and only the last battle's mastery."""
    play = Evolution(tmp_path)
    play.to_the_decision()
    play.key(pygame.K_f)
    engine = engine_of(play)
    win_battle(engine)
    play.ctrl.refresh()
    drawn, shortened = record_text(monkeypatch)
    play.app.frame(0)
    assert play.ctrl.screen == Screen.OUTCOME and engine.state.outcome == "victory"
    assert "All three battles won. The run is complete." in drawn and "Mastery from this run" in drawn
    lines = play.ctrl.run_awards_view()
    assert lines == ["Recruit 1 +3 in 3 battles, rank 1 -> 4, learned Squire Anchor (no effect in this version yet).",
                     "Recruit 2 +3 in 3 battles, rank 1 -> 4, learned Scout Marksman (no effect in this version yet)."]
    assert set(lines) <= set(drawn) and shortened == []
    # The totals are the sums of what each battle's screen said.
    assert [sum(a["base_points"] + a["challenge_points"] for a in play.link.last_awards if a["hero_id"] == hero) for hero in ("hero_001", "hero_002")] == [3, 3]


def test_two_won_battles_are_still_both(tmp_path, monkeypatch):
    play = Evolution(tmp_path)
    play.to_the_decision()
    play.click("continue:stop")
    drawn, _ = record_text(monkeypatch)
    play.app.frame(0)
    assert "Both battles won. The run is complete." in drawn
    assert play.ctrl.run_awards_view() == ["Recruit 1 +2 in 2 battles, rank 1 -> 3.", "Recruit 2 +2 in 2 battles, rank 1 -> 3."]


def test_a_run_total_says_what_came_from_bonuses_and_why_nothing_was_earned(tmp_path):
    play = Evolution(tmp_path)
    play.to_the_decision()
    awards = play.link.last_awards
    for award in awards:
        if award["hero_id"] == "hero_001":      # as if every battle had brought the bonus
            award["challenge_points"] = 1
        else:                                   # as if this hero's vocation had been mastered before the run
            award.update(base_points=0, challenge_points=0, denial_reason="ALREADY_MASTERED", rank_before=8, rank_after=8)
    assert play.ctrl.run_awards_view() == ["Recruit 1 +4 in 2 battles (2 from bonuses), rank 1 -> 3.",
                                           "Recruit 2 +0 in 2 battles (its vocation is mastered), rank 8."]
    assert AppController(log_dir=tmp_path / "plain").run_awards_view() == []
    # A hero that took another vocation inside the run: the rank is the new vocation's, from where that one began.
    first, second = (a for a in awards if a["hero_id"] == "hero_001")
    first.update(vocation_id="squire", rank_before=8, rank_after=8, base_points=0, challenge_points=0, denial_reason="ALREADY_MASTERED")
    second.update(vocation_id="guardian", rank_before=1, rank_after=2, base_points=1, challenge_points=0)
    assert play.ctrl.run_awards_view()[0] == "Recruit 1 +1 in 2 battles, rank 1 -> 2."


def where_paragraphs_end(monkeypatch) -> dict[str, float]:
    """For every paragraph the screens draw from now on: the place after it, in the layout's own units."""
    ends: dict[str, float] = {}
    original = UI.paragraph

    def paragraph(self, x, y, text, *args, **kwargs):
        ends[text] = original(self, x, y, text, *args, **kwargs)
        return ends[text]

    monkeypatch.setattr(UI, "paragraph", paragraph)
    return ends


def drawn_height(play: Play, lines: list[str], width: int, size: int) -> int:
    """What the paragraphs take as the panels draw them: each line of text is the size plus 3, and 8 follow a hero."""
    return sum(len(play.ui.wrap_lines(line, width, size)) * (size + 3) + 8 for line in lines)


@pytest.mark.parametrize("size", SIZES)
def test_five_heroes_with_everything_to_say_fit_both_mastery_panels(tmp_path, monkeypatch, font, size):  # noqa: F811
    """The lines grew with these fixes (what earned the bonus, a skill without effect). The largest case the demo
    can make, five heroes with a bonus, a new rank and such a skill each, must still fit both panels in every font."""
    play = Evolution(tmp_path, recruits=("squire", "apprentice", "scout", "squire", "scout"), size=size)
    play.to_the_decision()
    longest = {"challenge_points": 1, "challenge_id": "prevent_3_damage", "skills_learned": ["Guardian Field Medic"], "skills_waiting": ["Guardian Field Medic"]}
    for award in play.link.last_awards:
        award.update(longest, rank_after=award["rank_before"] + 1)
    drawn, shortened = record_text(monkeypatch)
    ends = where_paragraphs_end(monkeypatch)
    play.app.frame(0)
    lines = play.ctrl.continue_view()["awards"]
    assert len(lines) == 5 and lines[0] == ("Recruit 1 +2 with the bonus (its shields took 3 damage for an ally), now rank 3, "
                                           "learned Guardian Field Medic (no effect in this version yet).")
    chosen = screens.award_size(play.ui, lines, 370, 264)
    assert drawn_height(play, lines, 370, chosen) <= 264, "the lines end inside the panel, above the two buttons"
    assert set(lines) <= set(drawn) and shortened == []
    assert max(ends[line] for line in lines) - 8 <= 470, "as drawn: inside the panel, which ends at 470"

    play.click("continue:stop")
    drawn.clear()
    play.app.frame(0)
    totals = play.ctrl.run_awards_view()
    assert totals[0] == "Recruit 1 +4 in 2 battles (2 from bonuses), rank 1 -> 3, learned Guardian Field Medic (no effect in this version yet)."
    chosen = screens.award_size(play.ui, totals, 286, 294)
    assert drawn_height(play, totals, 286, chosen) <= 294
    assert set(totals) <= set(drawn) and shortened == [] and play.app.render_faults == 0
    assert max(ends[line] for line in totals) - 8 <= 510, "as drawn: inside the panel, which ends at 510"


def test_award_lines_are_as_large_as_they_fit(tmp_path):
    play = Evolution(tmp_path)
    assert screens.award_size(play.ui, ["Recruit 1 +1."], 370, 264) == 14
    long = ["Recruit 1 +2 with the bonus (its shields took 3 damage for an ally), now rank 3, learned Guardian Field Medic (no effect in this version yet)."] * 5
    assert screens.award_size(play.ui, long, 370, 264) < screens.award_size(play.ui, long[:1], 370, 264) == 14
    assert screens.award_size(play.ui, long * 9, 370, 264) == 10, "what cannot fit at any size is set at the smallest"


# --------------------------------------------------------------------------------------------
# F7: what a run is, said the same way everywhere
# --------------------------------------------------------------------------------------------


def test_the_menu_and_the_battle_bar_agree_about_the_optional_third_battle(tmp_path, monkeypatch):
    plain = AppController(log_dir=tmp_path / "plain")
    assert plain.tagline() == "A turn-based tactical dice RPG. Two battles, one upgrade, every die face visible."
    play = Evolution(tmp_path)
    assert play.ctrl.tagline() == "A turn-based tactical dice RPG. Two battles and an optional third, one upgrade, every die face visible."
    play.ctrl.third_battle = False
    assert play.ctrl.tagline() == plain.tagline()
    play.ctrl.third_battle = True
    drawn, shortened = record_text(monkeypatch)
    play.ctrl.to_main_menu()
    play.app.frame(0)
    assert play.ctrl.screen == Screen.MAIN_MENU and play.ctrl.tagline() in drawn and shortened == []

    # In battle the bar counts the battles that must be fought; the optional one is counted once it is being fought.
    play.ctrl.new_run()
    play.ctrl.begin_run()
    drawn.clear()
    play.app.frame(0)
    assert play.ctrl.view()["battle_count"] == 3 and "Battle 1 of 2" in drawn and "Battle 1 of 3" not in drawn
    assert phone.screen(play.ctrl)["title"] == "Battle 1 of 2"
    play.ctrl.new_run()
    play.to_the_decision()
    view = play.ctrl.view()
    assert (view["battle"], view["battle_count"], view["optional_battles"]) == (2, 3, 1) and battle_title(view) == "Battle 2 of 2"
    assert battle_title({**view, "battle": 1}) == "Battle 1 of 2"
    play.key(pygame.K_f)
    drawn.clear()
    play.app.frame(0)
    assert battle_title(play.ctrl.view()) == "Battle 3 of 3" and "Battle 3 of 3" in drawn
    assert phone.screen(play.ctrl)["title"] == "Battle 3 of 3"


def test_a_run_without_the_third_battle_counts_two(tmp_path):
    play = Play(tmp_path, ["squire"])
    play.begin()
    view = play.ctrl.view()
    assert view["optional_battles"] == 0 and battle_title(view) == "Battle 1 of 2"
    assert screens.battle_title is battle_title, "both front ends take the title from one place"
