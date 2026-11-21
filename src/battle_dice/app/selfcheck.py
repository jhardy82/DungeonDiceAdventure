"""A self-check that needs no screen: one whole run through the real controller, and a save written and read back.

The game's own self-check (``python -m battle_dice --smoke-test``) draws every screen with pygame. This one is
for where those screens are not used, such as the phone app: it proves that the rules, the content, the
controller and the save work on that platform. The run is played by the simulated player, as the other one is.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from battle_dice import RULES_VERSION
from battle_dice.app.controller import AppController, Screen
from battle_dice.features import CLASS_EVOLUTION
from battle_dice.sim.policies import HeuristicPolicy

PARTY = ("squire", "apprentice", "scout")
#: More steps than any run takes; a run that does not end is a fault, not a long run.
STEP_LIMIT = 20000


class SelfCheckFailed(RuntimeError):
    """The self-check found a fault. The message says which."""


def run(folder: Path | str, seed: int = 1) -> dict[str, Any]:
    """Play a run with saved heroes inside ``folder`` and read the save again. Returns what was found.

    Raises :class:`SelfCheckFailed` with the reason when anything is not as it must be. Nothing outside
    ``folder`` is read or written.
    """
    folder = Path(folder)
    controller = AppController(fixed_seed=seed, log_dir=folder / "logs", features=[CLASS_EVOLUTION], save_dir=folder / "saves")
    try:
        link = controller.progression
        if link is None:
            raise SelfCheckFailed(f"the save could not be opened: {controller.progression_error}")
        controller.new_run()
        for class_id in PARTY:
            controller.add_hero(class_id)  # with saved heroes this recruits one and puts it into the party
        if [member["class_id"] for member in controller.party] != list(PARTY):
            raise SelfCheckFailed(f"party setup produced {controller.party}: {controller.message}")
        controller.begin_run()
        engine = controller.engine
        if engine is None:
            raise SelfCheckFailed(f"the run did not start: {controller.message}")
        policy, steps = HeuristicPolicy(), 0
        while not engine.finished():
            if engine.needs_input():
                policy.act(engine)
            else:
                engine.do("AdvancePhase")
            controller.refresh()
            steps += 1
            if controller.screen == Screen.ERROR:
                raise SelfCheckFailed(f"the controller reported a fault:\n{controller.error_text}")
            if steps > STEP_LIMIT:
                raise SelfCheckFailed("the run did not finish")
        if controller.screen != Screen.OUTCOME:
            raise SelfCheckFailed(f"expected the outcome screen, got {controller.screen}")
        if controller.log_path is None or not controller.log_path.exists():
            raise SelfCheckFailed(f"the event log was not written: {controller.log_error}")
        if len(link.state.heroes) != len(PARTY) or not link.last_awards:
            raise SelfCheckFailed("the heroes or what they earned did not reach the save")
        ranks = sorted((hero_id, sum(row.rank for row in hero.mastery.values())) for hero_id, hero in link.state.heroes.items())
        result = {
            "outcome": engine.state.outcome, "events": len(engine.events), "steps": steps, "battles": len(engine.state.battle_records),
            "rules": RULES_VERSION, "content": controller.content.content_version, "python": sys.version.split()[0],
            "heroes_saved": len(ranks), "save_file": str(link.path),
        }
    finally:
        controller.close()
    # The save, read again by a controller that knows nothing of the run: the same heroes at the same ranks.
    again = AppController(log_dir=folder / "logs", features=[CLASS_EVOLUTION], save_dir=folder / "saves")
    try:
        if again.progression is None:
            raise SelfCheckFailed(f"the save could not be opened again: {again.progression_error}")
        read = sorted((hero_id, sum(row.rank for row in hero.mastery.values())) for hero_id, hero in again.progression.state.heroes.items())
        if read != ranks:
            raise SelfCheckFailed(f"the save read back differs: wrote {ranks}, read {read}")
    finally:
        again.close()
    result["save_read_back"] = True
    result["pygame_loaded"] = "pygame" in sys.modules
    return result


def report_line(result: dict[str, Any]) -> str:
    """One line for a log: every value of the result, in a fixed order."""
    return ("BATTLE DICE SELF-CHECK OK: " + " ".join(
        f"{key}={result[key]}" for key in ("outcome", "battles", "events", "rules", "content", "python", "heroes_saved", "save_read_back", "pygame_loaded")))
