"""The build's own description files must at least be readable.

Found with pull request 44: a step's name with a colon in it ("... (not the package: it asks for 3.15)")
made ``ci.yml`` unreadable, and GitHub then ran none of its jobs, without a word. A pull request with
missing checks looks green. This test reads the files the way that fault breaks them; it needs no
YAML library (the game has none among its requirements).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).resolve().parents[2] / ".github" / "workflows").glob("*.yml"))
KEY_VALUE = re.compile(r"^(?P<indent>\s*)(?:- )?(?P<key>[A-Za-z_][\w.-]*):\s+(?P<value>\S.*)$")


def plain_values(text: str) -> list[tuple[int, str, str]]:
    """(line number, key, value) of every ``key: value`` line whose value is written plain: not quoted, not a
    block, not a list or mapping in brackets. Lines inside a block (``run: |``) are somebody else's language."""
    found, block_indent = [], None
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if block_indent is not None:
            if indent > block_indent:
                continue
            block_indent = None
        match = KEY_VALUE.match(line)
        if not match:
            continue
        value = match["value"]
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            block_indent = indent
        elif value[0] not in "\"'[{&*!":
            found.append((number, match["key"], value))
    return found


def faults(text: str) -> list[str]:
    said = []
    for number, key, value in plain_values(text):
        if re.search(r":(\s|$)", value):
            said.append(f"line {number}: the value of '{key}' holds a colon followed by a space; put the value in quotes")
        if re.search(r"\s#", value):
            said.append(f"line {number}: the value of '{key}' holds ' #', which starts a comment; put the value in quotes")
    return said


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)
def test_no_plain_value_in_a_workflow_file_breaks_the_file(path):
    assert faults(path.read_text(encoding="utf-8")) == []


def test_the_check_finds_the_fault_of_pull_request_44_and_leaves_sound_lines_alone():
    assert len(WORKFLOWS) >= 3
    broken = "    steps:\n      - name: Install what the tests need (not the package: it asks for 3.15)\n        run: python -m pip install x\n"
    assert faults(broken) == ["line 2: the value of 'name' holds a colon followed by a space; put the value in quotes"]
    sound = ('      - name: "Install (not the package: it asks for 3.15)"\n        run: |\n          echo "a: b"  # said: so\n'
             "        env:\n          GROUP: android-${{ github.ref }}\n          TIME: 12:30\n        with: {a: b}\n")
    assert faults(sound) == []
    assert faults("      - name: Build  # the wheel\n") == ["line 1: the value of 'name' holds ' #', which starts a comment; put the value in quotes"]
