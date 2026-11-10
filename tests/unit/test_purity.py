"""The rules engine, content layer, RNG and simulator must not depend on pygame (section 14.1)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import battle_dice

PACKAGE = Path(battle_dice.__file__).parent
PURE = ["core", "content", "sim", "app"]


def test_no_pygame_import_in_pure_packages():
    offenders = []
    files = [PACKAGE / "rng.py", PACKAGE / "__init__.py"]
    for folder in PURE:
        files += sorted((PACKAGE / folder).rglob("*.py"))
    for path in files:
        if re.search(r"^\s*(import|from)\s+pygame\b", path.read_text(encoding="utf-8"), flags=re.MULTILINE):
            offenders.append(str(path.relative_to(PACKAGE)))
    assert offenders == []


def test_engine_runs_without_loading_pygame():
    script = (
        "import sys\n"
        "from battle_dice.core.engine import Engine\n"
        "from battle_dice.sim.policies import HeuristicPolicy, play_run\n"
        "e = Engine()\n"
        "e.do('StartRun', seed=1, party=[{'class_id': 'scout', 'row': 'back'}])\n"
        "play_run(e, HeuristicPolicy())\n"
        "assert not any(m == 'pygame' or m.startswith('pygame.') for m in sys.modules), 'pygame was imported'\n"
        "print(e.state.outcome)\n"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() in ("victory", "defeat")


def test_no_global_random_module_in_rules_code():
    offenders = []
    for folder in ("core", "content"):
        for path in sorted((PACKAGE / folder).rglob("*.py")):
            if re.search(r"^\s*(import|from)\s+random\b", path.read_text(encoding="utf-8"), flags=re.MULTILINE):
                offenders.append(path.name)
    assert offenders == []
