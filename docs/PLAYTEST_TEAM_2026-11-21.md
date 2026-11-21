# Battle Dice: playtest by a team of eight AI playtesters

- **Date:** 2026-11-21. **Build:** `main` at `8680286` (rules 1.1.1, content 1.3.1, catalog 0.5.0).
- **Asked for by the owner:** "Teach subagents how to playtest the game and send out a team."
- **Played by:** eight AI agents, each with one role, through the real screens with
  `tools/playtest_screen.py`. The guide and the roles are in `.claude/skills/playtest/`.
- **Not covered:** play by a person. An AI reading a text view finds missing and wrong
  information; it does not get bored, frustrated or delighted, and it sees no animation.

## 1. Summary

- **No blocker.** No error screen and no drawing fault in 7,374 player actions over 51 sessions
  (fresh replays of the same steps counted again), including one role that only tried to break
  the game.
- **137 findings were reported** (9 high, 43 medium, 85 low). Merged, they are **about 45
  different things**. Several were found by four to eight testers independently.
- **Seven are high:**

| # | Finding | Found by | Checked |
|--:|---------|---------:|---------|
| 1 | The "Now ..." prediction is wrong for the second action of a combo: the die card says "Now deals 0 (Weaken -1)" and the attack deals 1 | 3 | Replayed; cause read in the code |
| 2 | Changing vocation back and forth on the upgrade screen heals the hero for free (12/15 became 18/18) | 1 | Replayed |
| 3 | After a won battle, no screen says what mastery was earned (the README says the upgrade screen does) | 2 | Replayed; cause read in the code |
| 4 | Corruption backlash (1 HP at each activation from corruption 5) is explained nowhere and is not in the plan's prediction | 5 | Rule read in the code |
| 5 | The enemy panel says "a higher weight is chosen more often", but a hidden priority puts a status ability first | 3 | Rule read in the code |
| 6 | The upgrade card "Imbue" can change nothing but a name ("Strike: 3 melee damage" to "Heavy Blow: 3 melee damage") | 2 | Content read: the two faces are identical |
| 7 | The dice seed cannot be set with the mouse, although the main menu says every screen works with mouse or keyboard | 1 | Known from the code |

- **What held up:** 60 or more predictions were checked against the log and the health values;
  all were right except finding 1. Every control that was off gave its reason. Every screen
  could be used and left by keyboard alone, and by mouse alone except for typing a seed.

## 2. Method

- **The driver.** Each tester plays through `tools/playtest_screen.py`: it sends the key presses
  and clicks a player makes, and returns the screen as text (every text panel by panel, every
  control with its state and the game's reason when it is off) and a screenshot. A session is a
  list of actions that is replayed from a fresh start on every call, so every finding comes
  with steps that reproduce it.
- **The guide** (`.claude/skills/playtest/SKILL.md`): play like a player, do not read the code,
  say what you expect before you act, quote the screen exactly, keep "what happened" apart from
  "what it means", reproduce every finding of medium severity or higher in a fresh session.
- **Verification.** A tester's finding is a claim. The findings marked "Replayed" were played
  again by the session lead with the tester's own steps; "read in the code" or "content read"
  means the cause or the rule was found there.

| Role | What it played | Actions in all its sessions | Findings (high, medium, low) |
|------|----------------|--------:|------------------------------|
| First-timer | One whole run knowing only the screen; won | 858 | 1, 5, 11 |
| Keyboard-only | A run and all menus without a mouse; Battle 2 lost | 1,283 | 2, 5, 8 |
| Mouse-only | The same without a keyboard; Battle 1 won, then abandoned | 521 | 1, 6, 12 |
| Settings auditor | Every setting and value; a battle at Large text and High contrast | 569 | 0, 4, 11 |
| Evolution, Field Medic | README tour, run 1; Field Medic used; Battle 2 lost | 1,055 | 1, 5, 8 |
| Evolution, vocation change | README tour, run 2; refusals; roster limits; Battle 2 lost | 1,499 | 1, 8, 12 |
| Breaker | Wrong orders, abandoned runs, 960x540, odd parties | 947 | 0, 7, 12 |
| Strategist | One full run with two heroes, won; 29 number checks | 642 | 3, 3, 11 |

**Not reached by anyone:** a won Battle 2 with Class Evolution on, the "stop or fight on"
decision, the third battle. Three testers lost Battle 2; each had played part of it with blind
key sequences to stay inside a command budget, so those losses say little about balance.

## 3. Findings

"Testers" is how many of the eight reported it independently.

### 3.1 Defects: the game does or says something wrong

| ID | Finding | Testers | Checked |
|----|---------|--------:|---------|
| D1 | Wrong "Now" prediction on the die card of a planned combo attack (the plan's own prediction is right; the die card does not know the plan) | 3 | Replayed |
| D2 | Free heal by changing vocation back and forth (the carried-over health is rounded up at every change) | 1 | Replayed |
| D3 | Mastery earned is not shown after a battle: the "Mastery: ..." status line is overwritten at once, and the upgrade screen has no panel | 2 | Replayed |
| D4 | The plan line "If the target is gone: retargets (...); cancels if none." is cut off, at Normal and Large | 8 | Replayed |
| D5 | Internal names on screen, cut off: "Used this intent: Apprentice 2: groun...", "... rx_guardia..." | 6 | Not replayed |
| D6 | The status bar keeps an old message: "Plan locked. Resolving." while the next hero waits for its roll; others after a screen change | 6 | Not replayed |
| D7 | "Order (O)" is enabled with two planned actions but does nothing, silently, when the rules fix the order | 2 | Read in the code |
| D8 | M in a battle switches motion on while Settings shows "Off (reduced motion)"; changing any setting switches it off again | 1 | Not replayed |
| D9 | Changing any setting resizes the window to the Settings size, also when it was sized by the launch option (and, by the code, when dragged) | 1 | Read in the code |
| D10 | The combat log credits the Guardian's shield bonus to "Steadfast", the Squire's passive | 1 | Not replayed |
| D11 | "Roster (8 of 6 heroes)" after the roster size is lowered below the number of heroes | 2 | Not replayed |
| D12 | The Career screen shows a vocation's base health ("HP 17") while the hero has more (19) from mastery; nothing explains it | 2 | Not replayed |
| D13 | The reaction prompt quotes an attack's damage without Weaken ("4 ranged damage" when 3 will land) | 1 | Not replayed |
| D14 | A capped amount gets no "Now" line: "heal 3" healed 2; "+2 mana" gave 1 | 1 | Not replayed |
| D15 | The log's breakdown does not add up when a hit is larger than the remaining health ("takes 1 damage [3 base, -1 Weaken]") | 2 | Not replayed |
| D16 | Dice still say "will reroll" when no reroll is left | 3 | Not replayed |
| D17 | Downed heroes show "React 1"; defeated enemies keep statuses and a gauge on their cards | 2 | Not replayed |
| D18 | A seed locked by the launch option still says "press D for a random seed" | 1 | Not replayed |
| D19 | The main menu's help for Settings promises "the dice seed", which is no longer there; the Controls help leaves Settings out of the pause menu | 2 | Not replayed |

### 3.2 Rules and content: needs a decision

| ID | Finding | Testers | Checked |
|----|---------|--------:|---------|
| R1 | The upgrade card "Imbue" can replace a face by one that is identical in every respect but its name (Strike and Heavy Blow; Heavy Guard and Bulwark) | 2 | Content read |
| R2 | D2 again: the fix changes how health is carried over at a vocation change | 1 | Replayed |
| R3 | A full roster cannot be emptied: there is no way to dismiss one hero | 2 | Not replayed |
| R4 | Every hero has all three starting classes open: "Squire 1" can become a Scout at once and is then listed as "Squire 1   Scout, rank 1" | 2 | Not replayed |
| R5 | A slower Mastery pace takes "mastered" away but keeps the vocation it had opened | 1 | Not replayed |

### 3.3 One key, two meanings

| ID | Finding | Testers |
|----|---------|--------:|
| K1 | With one legal target the game picks it without saying so. The second key press the player is used to ("die, then target") then removes the action, or spends another reaction | 5 |
| K2 | While a target is being chosen, a die button reads "Cancel (2)" although pressing 2 picks target 2 | 2 |
| K3 | R is Roll and Reroll in battle and "Retry Same Party" on the outcome screen: it starts a new run at once, and the result screen is gone unread | 3 |
| K4 | Target numbers do not follow the hero names when a hero is down: for the Field Medic heal "Scout 2" is key 3 | 1 |
| K5 | The dice order flips at a vocation change: the Squire's Die 1 is the d6, the Guardian's is the d4 | 1 |
| K6 | The Controls help says "Esc clears" the focus ring; Esc leaves the screen. The ring is also dropped after hotkeys, against the help | 1 |

### 3.4 Safeguards

| ID | Finding | Testers |
|----|---------|--------:|
| S1 | "Abandon Run" throws a run away on one click, while Pass and both resets ask first | 2 |
| S2 | "Reset the saved profile" is confirmed by a second click on the same button, so a double-click deletes every hero | 2 |
| S3 | After a click, a different and costly button can sit under the resting pointer (a 1-mana reaction, then a 2-mana one; "Abandon Run", then "Quit") | 1 |
| S4 | The bench swap is final on one click | 2 |

### 3.5 Missing information

| ID | Finding | Testers |
|----|---------|--------:|
| M1 | Corruption: backlash from 5, what 6/6 means and the "!" are explained nowhere; the plan does not predict the health loss | 5 |
| M2 | "A higher weight is chosen more often" hides the real rule: lethal first, then a status the target does not have, then the weights | 3 |
| M3 | An enemy action often resolves with no reaction prompt, or the prompt starts at "stage 2 of 3", with no reason; cards show "React 1" when no reaction is possible | 3 |
| M4 | The first decision of a run is a reaction prompt about corruption and mana, before any hero has acted | 2 |
| M5 | Party setup does not say what party size or rows change (enemy numbers and health follow the party size); in battle nothing says why melee cannot reach the back row | 3 |
| M6 | Unexplained shorthand: "speed" on a die face, "Initiative", "Tick", "v1", "React 1" | 4 |
| M7 | The outcome screen gives eleven raw totals, a file path and "use --seed" (a launch option), and nothing about how the player did | 5 |
| M8 | A vocation change shows no numbers before the button is pressed; the bench die disappears silently; the hero keeps the name of its first class and no battle screen names its vocation | 3 |
| M9 | "HP partly recovered" gives no amount | 2 |
| M10 | Field Medic: the die says "(cannot revive)" and "Field Medic: revive at 5 HP" together; a revived hero keeps its Poison | 1 |
| M11 | Wording: "One targeted ally" (means the ally the enemy targets); "to all enemies" on an enemy's card; "Add a Apprentice"; "Asked twice" (asks once); "Click to change." for a keyboard user; "-0 magnitude" | 5 |
| M12 | "Battle speed at start" changed from the pause menu changes the running battle at once | 2 |

### 3.6 Mouse and keyboard reach

| ID | Finding | Testers |
|----|---------|--------:|
| A1 | The dice seed cannot be typed with the mouse | 1 |
| A2 | Battle speed and motion have no clickable control in a battle | 1 |
| A3 | A class sheet cannot be read by keyboard before a hero of that class is added | 1 |
| A4 | Some keys that work are not shown, and the same function has different keys on different screens (Back, Controls, Start Battle 2) | 1 |

### 3.7 Layout

| ID | Finding | Testers |
|----|---------|--------:|
| L1 | A unit card with two statuses changes its notation ("WKN x1 (2)", "PSN 1(2) WKN 1(2)", "P1(1) W2(1-2)") and drops the gauge number | 7 |
| L2 | Text size Large: lines of one block have two sizes; on the Controls screen the four longest paragraphs stay small although half the screen is empty | 2 |
| L3 | Enemy names are shortened next to a TARGET or DEFEATED mark ("Goblin Skirmis... 1"), and DEFEATED touches the name | 2 |
| L4 | At Large the title "Recovery and Upgrade" touches the picture beside it | 1 |
| L5 | At 960x540 "Order" and "Clear" are about 66 x 17 pixels, 3 pixels apart, beside "Pass" | 1 |
| L6 | Resting the pointer on a unit card replaces the combat log; after a target click the log stays hidden | 2 |
| L7 | The save file path is cut off when the folder path is long | 4 |

### 3.8 Impressions that one player cannot prove

- **Pacing.** Battles feel long and "slow rather than dangerous". Measured by the strategist for
  two heroes: about 21 hero turns, 14 reaction prompts, 28 rerolls and 130 inputs a battle. The
  first-timer: 42 activations to remove 33 enemy health in Battle 1.
- **Prompts with one sensible answer.** Grounding on an ally with no corruption is free mana.
- **Statuses dominate.** Enemies keep heroes weakened and poisoned; shields then matter little.
- **The tour's second run** (Guardian and Scout) may lead into a Battle 2 that party rarely wins.
- **A blind win.** The first-timer won Battle 2 pressing "die 1, first target" without reading.

These are questions for the simulator, not conclusions.

## 4. What worked well (observed, not assumed)

- All predictions on same-target plans, shields, capped mana in the plan line, Weaken on enemy
  attacks, upgraded faces and the outcome totals matched the log (60 or more checks).
- Every control that was off gave a reason in plain words.
- An illegal plan is refused with the rule that forbids it.
- Settings: every value was kept, both resets did what they say, the locks during a run give
  their reason, a launch option is shown honestly ("On (launch flag)").
- The README's tours worked as written as far as they were played.
- Refusals in the Career screen name the hero's own state ("Needs: master Scout (now rank 3).").
- Five heroes against five enemies fit the battle screen without overlap.

## 5. Faults of the playtest itself

- The guide told testers to write a report file; subagents are not allowed to, so most reports
  came back as text. The guide is corrected.
- The driver's `hover` waited a full second, which hid the "Help text delay" setting. Corrected:
  `hover` shows the help of the next frame, and `wait:MS` lets the delay pass.
- The driver gives every run of a session a known seed, so "Dice seed: random" always led to
  seed 500. One tester reported that as a fault of the game. The guide now says so.
- The command budget was too small for the strategist's three runs; one full run fitted.
- Three testers played the end of a battle with blind key sequences to save commands. The guide
  now forbids that for anything they report on.

## 6. What is fixed (owner decision D-34, 2026-11-21)

The owner decided: fix every defect and every case of missing information that needs no design
decision; keep the single-target shortcut but make it safe; ask once more before "Abandon Run",
"Retry" and the profile reset; fix both rule faults (R1, R2). Details: `docs/DECISION_LOG.md`,
section 7.32.

| Batch | Findings | State |
|-------|----------|-------|
| 1. Predictions and the battle screen | D1, D4, D5, D6, D7, D10, D13, D14, D15, D16, D17, M1, M2 | Fixed |
| 2. Keys, safeguards, reach | K1 to K4, K6, S1, S2, S3 (reactions), A1, A2, D8, D9, D18, D19, M12 | Fixed |
| 3. Class Evolution information | D3, D11, D12, K5, M8, M10 | Fixed |
| 4. Rules | R1 (Imbue), R2 and D2 (free heal) | Fixed (rules 1.1.2) |
| 5. Other information and layout | M3, M5, M6, M7 (the seed line), M9, M11 (five wordings), L4, L7, A3, S4 | Fixed |
| Not changed, with the reason for each | M4, M7 (the totals), M11 ("one targeted ally"), L1, L2, L3, L5, L6, A4, S3 (Abandon, then Quit) | Decision log, section 7.36 |
| Not decided by the owner | R3 (dismiss a hero), R4 (starting classes), R5 (mastery pace) | Waiting |

Of the 57 findings with an ID, 44 are fixed, 3 are fixed in part (S3, M7, M11), 7 are left as
they are with a reason, and 3 wait for the owner.
