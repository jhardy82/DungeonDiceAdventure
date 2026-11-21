# Playtest roles

One role per playtester. A team is any set of these. Each role has its own session folder.

| Role | Who you are | You may read | Start with |
|------|-------------|--------------|------------|
| `first-timer` | You have never seen the game | Only the screen (the in-game Controls help counts as the screen) | `start` |
| `keyboard-only` | You cannot or will not use a mouse | Only the screen | `start` |
| `mouse-only` | You never touch the keyboard | Only the screen | `start` |
| `settings-auditor` | You change every setting before you trust a game | The "Settings" section of `README.md` | `start` |
| `evolution-medic` | You follow the README's tour, run 1 | `README.md` | `start` (switch Class Evolution on in Settings) |
| `evolution-change` | You follow the README's tour, run 2 | `README.md` | `start` (switch Class Evolution on in Settings) |
| `breaker` | You try to break it | Only the screen | `start`, then also `start --size 960x540` |
| `strategist` | You want to win and check the game's numbers | The "How to play" section of `README.md` | `start --seed 500`, then 501, 502 |

## first-timer

- **Play:** from the main menu, one whole run with a party you choose, to victory or defeat.
- **Rule:** press what looks obvious. Do not open the Controls help until you are stuck; note
  the moment you needed it.
- **Watch for:** the first screen where you did not know what to do; words you had to guess
  (abbreviations, numbers without a unit); a decision you made without understanding it; what
  the game told you after the run about how you played.

## keyboard-only

- **Play:** one whole run, and a visit to Controls, Settings (all four groups) and the pause
  menu, using only `key:` actions. No `click:`, no `hover:`.
- **Watch for:** anything you cannot reach or cannot leave; where the focus goes after Tab and
  whether you can tell where it is; keys shown on screen that do something else or nothing;
  the same key meaning two things on one screen.

## mouse-only

- **Play:** the same as `keyboard-only`, using only `click:` and `hover:` actions.
- **Watch for:** anything that needs a key (typing a seed, speed, motion, skipping); help text
  you only get by resting the pointer, and whether it tells you enough; controls that are too
  small or too close (open the screenshot).

## settings-auditor

- **Play:** every setting in all four groups through every value, and check on the screen that
  each one does what its help says. Then: "Reset all settings to defaults"; Settings from the
  pause menu during a battle (which settings are locked, and is the reason given); the dice
  seed on the New Run screen (type one, a random one, wrong input, a very long number).
- **Then:** play at least one battle with Text size Large and High contrast on, and open the
  screenshots.
- **Watch for:** a setting whose effect you cannot see; help text that does not match what
  happens; a value that is not kept; anything cut off or overlapping at Large or in High
  contrast.

## evolution-medic

- **Play:** the README's "tour of the slice", run 1: the start "A Guardian with Field Medic",
  the career and skills screens, a battle in which an ally goes down and Field Medic is used,
  the upgrade, Battle 2, then "Fight On" into the third battle.
- **Watch for:** any step of the tour that does not work as written; whether the game itself,
  without the README, would have led you there; what the screen says about mastery after each
  battle.

## evolution-change

- **Play:** the README's "tour of the slice", run 2: the start "A Guardian at rank 1", make the
  hero a Squire again, win Battle 1, change to Guardian on the upgrade screen, fight Battle 2
  as a Guardian. Then: recruit heroes until the roster refuses; try to change vocation at
  moments when it should not be possible and read the reason.
- **Watch for:** what changes for the hero at the change (health, mana, dice, upgrade cards)
  and whether the screen says so; reasons for refusals; anything about a locked vocation that
  stays unexplained.

## breaker

- **Play:** no plan. Abandon a run and start another. Retry after a defeat. Modify the party
  after a run. Pause, open Settings, come back. Press keys that are not offered. Click things
  that are off. Parties of one and of five. Do things in the wrong order. Repeat at 960x540.
- **Watch for:** an error screen; a `DRAWING FAULTS` line; a state you cannot leave; a message
  that is left over from before; a number that cannot be right; anything different at 960x540.
- **Report every crash with its full action list**, even if you cannot explain it.

## strategist

- **Play:** three runs with different party sizes (two, three and five heroes), trying to win:
  use rerolls, keep dice, reactions, the rows, the upgrade.
- **Check the numbers:** each time the screen predicts a result, write it down, then compare
  with the combat log and the health values after the action. At least ten checks.
- **Watch for:** a prediction that was wrong; a rule you could not have known; choices that
  never mattered; how many decisions a battle takes (count them).
