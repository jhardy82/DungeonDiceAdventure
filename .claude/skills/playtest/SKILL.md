---
name: playtest
description: Playtest Battle Dice as a player would, step by step through the real screens, and report findings that can be reproduced. Use when asked to playtest the game, to try a feature as a player, or to send out playtesters.
---

# Playtesting Battle Dice

You play the real game through its real screens. You do not read its code. You report what a
player would run into, with the exact steps that reproduce it.

## 1. What you are and are not

- **You are a player with a role** (section 6). Stay in that role.
- **You know only what the screen tells you**, plus what your role allows you to read.
- **Do not read** `src/`, `tests/` or `docs/DECISION_LOG.md`. Reading how something is built
  makes you blind to what a player cannot know. (`README.md` only if your role says so.)
- **Do not change anything in the repository.** Write only inside your session folder.
- **What you cannot judge:** fun, feel, animation, sound, speed, tired eyes. Say so; do not guess.

## 2. The driver

Run every command from the repository root. `DIR` is your own session folder (you are given one).

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B tools/playtest_screen.py --session DIR start
```

```bash
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B tools/playtest_screen.py --session DIR do key:n click:add:squire
```

| Command | What it does |
|---------|--------------|
| `start [--size 960x540] [--seed 500] [--fixed-seed N] [--feature class_evolution_v1]` | Begins a session at the main menu and prints the screen |
| `do ACTION [ACTION ...]` | Applies the actions in order and prints **what changed** on the screen |
| `do --full ACTION ...` | The same, but prints the whole screen |
| `look` | Prints the whole screen |
| `undo [N]` | Takes back the last N actions |
| `log` | Lists the actions of the session |

| Action | Meaning |
|--------|---------|
| `click:KEY` | Click a control. `KEY` is the name in the CONTROLS list. Clicking a control that is off is allowed: the game answers |
| `hover:KEY` | Rest the pointer on a control and read its help in the status bar |
| `key:NAME` | Press a key: a letter, a digit, `escape`, `enter`, `space`, `tab`, `shift+tab`, `backspace`, `up`, `down`, `left`, `right` |
| `type:DIGITS` | Press digit keys one after another |
| `clickxy:X,Y` | Click a point of the 1280x720 layout |
| `wait:MS` | Let time pass |

How it behaves:

- **A session is a list of actions.** Every command plays the whole list again from a fresh
  start (new settings, new save). So a session always reproduces, and `undo` is exact.
- **After each action the game runs on until it waits for you**, as it does for a person.
- **The printed screen** lists every text, panel by panel, then every control with its state.
  A control that is off shows the game's reason. A text that the game cut short is marked
  `[CUT OFF ...]`.
- **`NOTHING CHANGED ON THE SCREEN`** means exactly that. If you expected a change, that is a
  finding.
- **A screenshot** of the last screen is saved on every command. Open it with the Read tool
  when the look of the screen matters (overlap, alignment, something hidden, colours). The
  text view does not show those.
- **Use several sessions.** One per scenario keeps each action list short. Name them
  `DIR/run1`, `DIR/settings`, and so on.
- **Keep calls few.** Put obvious steps into one `do`. Stay inside the command budget you are
  given. Use `look` only when you need the whole screen again.
- **Never play blind to save commands.** A chain of keys pressed without reading the screens is
  not play. If the budget runs out, stop and say what was not covered. Do not report on a
  stretch you did not read.
- **The seed is the driver's.** The first run of a session has seed 500 (or `--seed N`) and each
  further run the next number, also while the game says "Dice seed: random". That is how a
  session stays repeatable; it is not a fault of the game.
- **Help text delay.** `hover:KEY` shows the help of the next frame. If the setting "Help text
  delay" is on, follow it with `wait:MS` to let the delay pass.

## 3. How to play

1. **Say what you are about to try and what you expect** (one line, in your notes) before each
   decision that matters. A finding is the gap between that and what happened.
2. **Read the whole screen first** on every new screen (`do --full` or `look`).
3. **Play like your role.** A first-time player presses what looks obvious. A careful player
   reads the help. A tester of limits does what nobody planned for.
4. **Write down confusion when it happens**, not afterwards. "I did not know what G70 means" is
   a finding even if you work it out later.
5. **Check numbers.** When the screen predicts a result (damage, shield, healing, a chance),
   note it, act, and compare with what the log and the health values show afterwards.
6. **Finish what your role asks for**, then explore until your command budget is used.

## 4. What counts as a finding

| Kind | Example |
|------|---------|
| Defect | The game shows an error screen; a number on screen is wrong; a control does nothing |
| Missing information | The player must decide and the screen does not say what a choice does |
| Confusing | A word, label or message that can be read two ways, or contradicts another |
| Layout | Texts overlap, are cut off, sit outside their panel, are too small to tell apart |
| Unreachable | Something cannot be done with the keys (or with the mouse) alone |
| Balance or pacing | A choice that never matters; a battle that feels decided by one roll; too many prompts. Mark these as impressions: one player cannot measure them |

Severity:

- **Blocker:** the run cannot go on, or data is lost.
- **High:** a player is misled into a bad decision, or cannot find a needed function.
- **Medium:** confusing or awkward, but a player gets through.
- **Low:** wording, polish, small layout faults.

## 5. The report

**The report is your final message**, in the format below. Do not write it to a file: a
subagent's report files are refused. Reproduce every Blocker, High and Medium finding once more
**in a fresh session** before you report it, and give that session's action list.

```markdown
# Playtest report: <role>

## Coverage
- Sessions: <folder>: <what was played>, <number of actions>
- Seeds, window sizes, settings used
- Not covered: <what you did not get to, and why>

## Findings
| ID | Severity | Kind | Finding in one sentence |
|----|----------|------|-------------------------|

### F1. <title>
- **Steps:** session folder and the action list (or the action numbers) that lead there
- **What the screen showed:** quoted text, and the screenshot path if the look matters
- **What I expected, and why:** from the player's point of view
- **Reproduced:** yes, in <fresh session folder> / no (say why)

## What worked well
- Observed, not assumed. One line each.

## Impressions I cannot prove
- Balance, pacing, clarity over time. Marked as impressions.
```

Rules for the report:

- **Quote the screen exactly.** Do not paraphrase a message you report as wrong.
- **Keep "what happened" apart from "what it means".**
- **No finding without steps.** If you cannot reproduce it, say so and keep it under
  "Impressions".
- **Say what you did not test.** An empty section is a claim that everything was covered.
- Begin the final message with the number of findings by severity and the three most important
  ones in one line each; the full report follows.

## 6. Roles

See `roles.md` in this folder. Each role says who you are, what you may read, what to play and
what to watch for.

## 7. Limits of this kind of playtest

- An AI reading a text view is more patient and more literal than a person. It finds missing
  and wrong information. It does not get bored, frustrated or delighted.
- Motion starts switched off in the driver, and the Settings screen says so. Switched on (M in a
  battle, or Settings), the driver lets the dice finish rolling before it prints a screen. Timing
  and motion themselves are still not seen.
- It does not replace a person playing on a real display.
