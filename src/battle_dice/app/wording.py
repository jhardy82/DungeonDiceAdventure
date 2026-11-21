"""How the game words what it says for a device without keys or a pointer.

The controller's messages are written for a desktop: "Roll the dice (R).", "Press again to ...",
"press its number or click it". A phone has a finger. A controller made with ``touch=True`` says
every message through :func:`touch_wording` (Android plan, phase 1). A desktop controller says its
messages as they are written, so nothing changes there.

``tests/unit/test_wording.py`` reads every message in the controller's source and fails when one
still names a key, a press or a click after this function has worded it.
"""

from __future__ import annotations

import re

#: A key named in brackets after a word: " (R)", " (Z, X)", " (Enter)", " (Esc cancels)".
_KEY_HINT = re.compile(r"\s*\((?:[A-Z](?:, [A-Z])*|Esc|Enter|Esc cancels)\)")
#: Whole phrases that are worded differently for a finger. Checked before the single words below.
_PHRASES = (
    (": press its number or click it", ": tap it"),
    ("press D to type a seed", "tap to type a seed"),
    ("press D for a random seed", "tap for a random seed"),
    ("type digits, Enter to set, Esc to cancel", "type digits, then set or cancel"),
    ("Enter sets it, Esc cancels.", "Then set it or cancel."),
    ("Shorten it, or press Esc.", "Shorten it, or cancel."),
)
_WORDS = (
    (re.compile(r"\bPress\b"), "Tap"),
    (re.compile(r"\bpress\b"), "tap"),
    (re.compile(r"\bClick\b"), "Tap"),
    (re.compile(r"\bclick\b"), "tap"),
)
#: What must not be left in a message for touch: a key in brackets, a key by name, a press, a click.
LEFT_OVER = re.compile(r"\((?:[A-Z](?:, [A-Z])*|Esc[^)]*|Enter)\)|\b(?:Esc|Enter)\b|\b[Pp]ress(?:es|ed)?\b|\b[Cc]lick")


def touch_wording(text: str) -> str:
    """A message without key names, and with "tap" where a desktop presses or clicks.

    "Roll the dice (R)." becomes "Roll the dice."; "Press again to abandon this run." becomes
    "Tap again to abandon this run.". Wording a message twice changes nothing more.
    """
    text = _KEY_HINT.sub("", text)
    for said, for_touch in _PHRASES:
        text = text.replace(said, for_touch)
    for word, for_touch in _WORDS:
        text = word.sub(for_touch, text)
    return text
