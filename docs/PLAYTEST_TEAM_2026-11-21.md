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
| 6. Decided by the owner on 2026-11-21 (D-35) | R3 (a hero can be dismissed), R4 (a recruit's name says no class), R5 (a vocation opened at a faster pace stays open, and the screen says so) | Fixed (decision log, section 7.38) |

Of the 57 findings with an ID, 47 are fixed, 3 are fixed in part (S3, M7, M11), and 7 are left
as they are with a reason. None waits for a decision.

## 7. Second round: the build after the fixes (2026-11-21)

Under the owner's standing rule of that day (always fix what is found broken; leave things better
than found), four AI playtesters played `main` after pull request 44: the build with all the fixes
above, hero dismissal and the new recruit names.

### 7.1 Method and coverage

| Role | What it played | Driver commands |
|------|----------------|-----------------|
| Roster auditor | Dismissing heroes, "Recruit N" names, the Mastery pace note, the README's second tour run | about 80 |
| Keyboard only | Menus, all four Settings groups, the pause menu, the Career screen, the seed, part of a battle, keys only | 83 |
| Breaker | Every "press again" safeguard, the seed entry, parties of one and five, 1280 x 720 and 960 x 540 | about 85 |
| Strategist | 24 checks of a predicted number against what then happened, over three party sizes | 80 |

- **No error screen, no drawing fault, no text cut off by the game's own check, no state without
  a way out**, at either window size.
- **Numbers:** 22 of 24 predictions matched exactly. Both misses were one gap (ST-1 below).
- **Earlier findings:** every one of the 57 that was re-checked was confirmed fixed or was one of
  those left with a reason, apart from K2 and D14, which were fixed in part (KB-3 and ST-1 below
  finish them).
- **Not covered by this round:** none of the four finished a battle inside its budget. The
  upgrade screen, the die swap, Battle 2, the outcome screen and the mastery lines after a battle
  were not played. The automated tour (`tests/ui/test_demo_tour.py`) plays them; a player did
  not.

### 7.2 Findings and what was done

IDs: RA roster auditor, KB keyboard only, BR breaker, ST strategist. All were Medium or Low.

| ID | Finding | State |
|----|---------|-------|
| RA-1, BR-1, BR-2, BR-3 | **A "press again" question stayed open while the player did something else.** An armed Dismiss survived selecting another vocation; the Retry question survived ten seconds, Tab and other keys; the defaults question stayed open beside the profile question; a second reaction asked by key but not by a click on its ally | **Fixed, in one place.** Every key press and click now tells the controller which control took it. A question ends when anything but its own control is used, when a key reaches no control, when eight seconds pass, or when the player leaves the place. Its text then leaves the status bar. The reset to defaults, the profile reset and the die swap, which had flags of their own, end the same way |
| BR-7 | An armed Abandon button no longer said where it leads | Fixed: "Press again: abandon, main menu" |
| KB-1 | B was an unlabelled Back on the Career screen and "Begin Encounter" on the screen behind it: C, B, B started a run | Fixed: B is not Back on the Career screen |
| KB-2 | The focus ring vanished after "Remove", so each removal began again from the top | Fixed: on the same screen the ring moves to the nearest control before the one that went away |
| KB-3 | During a target choice the other die still read "Use (2)" while 2 picked a target | Fixed |
| KB-5 | Mouse words for a keyboard player: "Remove (click)", "Party (click a hero to inspect)" | Fixed |
| KB-7 | Controls had a key on the main menu and none in the pause menu | Fixed: C in both. S is still Skip in a battle and Settings in the pause menu: two screens, not changed |
| KB-8 | "Motion off (M)" in a battle while Settings said "On"; "Rolling ..." beside controls that were on (in three reports) | **The driver's fault, not the game's**, fixed in the driver: its motion setting now says what it does, and it lets dice settle before it prints |
| ST-1 | Cleanse printed "-2 corruption (self)" with no "Now" line and removed 1, or nothing | Fixed: "Now -1 corruption (Apprentice 2 has 1 corruption)" |
| ST-4 | The die card cut off a long "Now" line: "... Squire 1 has 9 of at ..." | Fixed: it takes two lines |
| ST-5 | "Poison x1, 2 activations left" during an activation whose damage had landed | Fixed: for the acting unit, "this activation and 1 more" |
| ST-6 | A reaction's log line gave no amounts | Fixed: "... reacts with Grounding on Squire 1: Squire 1 loses 1 corruption; Apprentice 2 gains 1 mana." |
| ST-7, BR-5 | "Next stage:" while the stage was the same; "the only ally it could help" for one it could not | Fixed: "Another reaction is possible: ..."; "the only ally it can be used on" |
| ST-8 | "More heroes meet more and tougher enemies": measured, each enemy of a larger party has less health | Fixed: "More heroes meet more enemies." |
| RA-2, RA-7 | After a slower Mastery pace the Skills tab kept skills without a word, and the setting's help named only the faster direction | Fixed: the help says both directions and what stays; the Skills tab says "A skill learned at an earlier Mastery pace stays learned." |
| RA-3, RA-4 | Battle cards and the Career title named a recruit without its class | Fixed: "Recruit 1, Squire" on the card where there is room, and in the title |
| RA-5 | "is now a Apprentice", "as a Apprentice" | Fixed |
| RA-6 | 12 heroes, roster size 6: "The roster is full (6 heroes). ... dismiss a hero" | Fixed: it says how many must go, or to raise the size |
| RA-8 | The party was emptied by a visit to Settings | Fixed for a change of pace or roster size (the heroes are the same). Switching Class Evolution still empties it |
| RA-9 | The hero's picture touched a line of text on the Career screen | Fixed |
| BR-4 | A die with one legal ally still asked for its target; a reaction with one did not | Fixed: picked and named, as one legal enemy is |
| BR-6 | Seed entry dropped digits after the 20th without a word; a number too large closed the entry | Fixed: it says why, and stays open for a correction |

### 7.3 Not changed, with the reason for each

| ID | Finding | Why it stands |
|----|---------|---------------|
| ST-2 | "No hero could react to this enemy action." while a hero shows "React 1", with no reason | The reason (here: Grounding would have changed nothing) is not in the event the log is written from. Recording it changes the event format, which is a rules version. Proposed for the next one |
| ST-3 | Enemies re-apply Weaken and Poison as soon as they end and almost never attack (one battle, impression) | The enemies' rule of choice is content and balance. It needs the simulator and an owner decision |
| ST-9 | With five heroes one enemy action can open three reaction prompts | Pacing, an impression; belongs with the pacing question still open (Checkpoint 2) |
| KB-4 | Reaction rows are numbered from 1 in each stage, not by the hero's place | A second reaction on one enemy action is asked for once more, which guards the costly slip. Renumbering is a change of keys for the owner to decide |
| KB-6 | Dismiss, Retry and Abandon are confirmed by a second press of the same control | Owner decision D-34 ("ask once more"). The question now ends when anything else is done |
| BR-8 | "Order (O)" and "Clear (C)" are small at 960 x 540 | L5 of the first round, left with its reason in the decision log, section 7.36 |
| RA-2 (part) | The health a mastery rank adds goes when a slower pace lowers the rank | It follows the rank by rule. The setting's help now says so before the click |
| L1, L3 | Two statuses replace the gauge number; a long enemy name is shortened beside "TARGET 1" | As in section 7.36 |

**For the owner:** ST-3 (should enemies attack more?), ST-2 (reasons in the event log, with the
next rules version) and KB-4 (reaction keys by the hero's place).

**Answered on 2026-11-22 (D-36):** ST-3 is measured and brought back with options (decision
log, section 7.42); ST-2 goes with the next rules change; KB-4 stays as it is.

**ST-3, measured.** One player's impression in one battle; so it was counted over whole
simulated runs: the informed simulated player, every party composition of each size, seeds 300
to 309, both battles (`rules 1.1.2`, content `1.3.1`).

| Heroes | Runs | Enemy actions | Attacks | Statuses |
|--------|------|---------------|---------|----------|
| 1 | 30 | 624 | 48% | 47% |
| 2 | 60 | 2,473 | 25% | 71% |
| 3 | 100 | 4,918 | 17% | 80% |
| 4 | 150 | 9,357 | 22% | 76% |
| 5 | 210 | 16,661 | 15% | 83% |

- The impression holds: with two or more heroes, at least three of four enemy actions are a
  Weaken or a Poison. The enemies' rule prefers a status on a hero who does not have one, and a
  status lasts two activations.
- What it means for a player (the strategist's words, not measured): shields and Interpose
  rarely matter, and heroes mostly deal their damage at -1.
- Changing it changes the balance (the target is 70 to 85% wins per party size), so it is an
  owner decision with a simulator run, not a fix.

**Tally of this round:** 34 findings (roster auditor 9, keyboard 8, breaker 8, strategist 9; no
Blocker, no High). 28 are fixed, one of them in part (KB-7). 6 are left with a reason (ST-2,
ST-3, ST-9, KB-4, KB-6, BR-8).

## 8. A fifth playtester: two whole runs (2026-11-21)

Section 7.1 ended with what the second round had not covered: no playtester had finished a battle.
A fifth one ("finisher") was sent to play whole runs on the same build, after the fixes of section 7.

### 8.1 Method and coverage

- **Run 1, as shipped:** Battle 1 won, the upgrade screen, Battle 2 won, the outcome screen. 217 actions.
- **Run 2, Class Evolution:** Battle 1, the upgrade screen with Career, Battle 2, the stop-or-fight
  screen, **the third battle chosen and won**, the outcome screen, the roster. 302 actions. In a
  separate session the other branch (End Run: Victory) was taken to its outcome screen.
- Seed 500, a Squire and two Scouts, 1280 x 720, default settings. About 166 driver commands.
  Every finding was reproduced in a fresh session, apart from two Low ones that are plain from the text.
- **A shortcut the playtester named:** in Run 2 the first two battles were replayed from Run 1's key
  list and checked at each stop against Run 1's health, mana and statuses (they matched exactly).
  Only Battle 3 of Run 2 was read turn by turn.
- **What held:** no error screen, no drawing fault, no text cut off. Every prediction that was checked
  came true. All eleven numbers of the outcome screen were right in three outcome screens, checked
  against the playtester's own count. Recovery, the upgrade card, the upgraded die in Battle 2, the
  swap that asks first, and the mastery lines agreed with one another and with the roster afterwards.
- **Not covered:** a defeat and its outcome screen (a lone Scout that passed every turn was still at
  full health after 45 actions, and the attempt was stopped); a confirmed die swap; a completed
  Retry; a change of vocation; the Apprentice; parties other than three; 960 x 540; Settings.

### 8.2 Findings and what was done

12 findings: no Blocker, no High, 4 Medium, 8 Low. Each was checked in the code before it was fixed.

| ID | Finding | State |
|----|---------|-------|
| F1 (Medium) | **The reaction prompt's header carried "no hero could react" notes of earlier enemy actions**, piled them up ("Guard and Resource and Guard and Resource"), and showed them at a Guard stage that offered a reaction. It was the first thing on screen in Battles 2 and 3 | **Fixed. A defect with one cause:** an enemy action's id counts the actions of one battle and starts again in the next. The header collected the notes by that id over the whole run. It now reads back only to where this action was chosen |
| (found by reading) | The same cause in a second place: the "a reaction was just used on this enemy action, press again" question remembered the *id* of the action. A later battle's or a new run's action with the same number then had its first reaction asked for twice | Fixed: the question asks the rules, which keep the reactions of one enemy action. A test reproduces it with a second run of the same dice |
| F2 (Medium) | The upgrade screen never said that its three cards belong to the selected hero's selected die. The playtester chose the run's one upgrade without knowing that every other die had three more | Fixed: the panel is titled "Upgrade cards: Squire 1, Iron d6", the step reads "choose one upgrade for one die", and a line says that every die of every hero has its own three |
| F3 (Medium) | "learned Scout Marksman" was announced as a reward, on the screen where the player decides whether to risk a harder battle. The skill cannot be equipped and does nothing in this version | Fixed: "learned Scout Marksman (no effect in this version yet)". The note goes by itself when the rules learn the skill |
| F4 (Medium) | "+2 with the bonus" was explained nowhere | Fixed: the line says what earned it ("with the bonus (a Status die with an Attack die)"), and the Career screen has a Mastery line for each vocation that can be played: "1 point for a won battle. 1 more when ..." |
| F5 | "Both battles won." after three won battles | Fixed: "All three battles won." |
| F6 | "It lasts through Battle 2" for an upgrade that was still there in Battle 3 | Fixed: "It lasts until the run ends." |
| F7 | With Class Evolution on, the menu said "Two battles, one upgrade" while the battle bar said "Battle 1 of 3" for a third battle that is optional | Fixed: the menu says "Two battles and an optional third"; the bar counts the battles that must be fought ("Battle 1 of 2") and the optional one once it is being fought ("Battle 3 of 3"). The phone screens take the title from the same place |
| F8 | "Needs: master Scout (now rank 3)" did not say what "master" means when the Career screen was opened from the upgrade screen | Fixed: "master Scout (rank 8; now rank 3)", wherever it is read |
| F9 | Statuses on a unit card were written three ways: "PSN x1 (2)", "PSN 1(2) WKN 1(2)", "P1(2) W1(2) S2(1)" | **Fixed in part.** One and two statuses are now written the same way ("PSN x1(2) WKN x1(2)"). The shortest form, used when three kinds are on one unit, stays: with the "x" it does not fit the card in the widest font at 960 x 540 (tried, measured by the layout test) |
| F10 | A second reaction on one enemy action needs two presses, and only the status bar said so | Fixed: the button reads "Press again: Disrupt", an ally button "Press again", as the swap and the retry do |
| F11 | What recovery gave a hero was only in the status bar while the hero was pointed at | Fixed: on the hero's button, "HP 12/14 (was 7)", or "(+5)" where a font leaves less room |
| F12 | The victory screen showed mastery for the last battle only, and no tips | Fixed for mastery: "Mastery from this run", one line per hero with the total, what came from bonuses, the ranks and the skills. **Tips are as designed:** they appear when a whole mechanic went unused (no reroll, no reaction), and the playtester had used both |

### 8.3 Impressions, kept as impressions

One party, one seed. None of these was changed; each is for the owner.

| Impression | What is known |
|------------|---------------|
| The third battle, announced as harder (threat 4 of 5), was the easiest of the three for this party: 26 activations against 30 and 33, and 2 health lost | Checked in the content: for three heroes its enemies have 36 health in all (two Blight Captains at 13, a Hex Adept at 10) against 45 in Battle 2, and they hit harder (4 instead of 3). Its table was tuned by a simulated player for parties with a Guardian (Checkpoint 1, accepted by the owner). This party had none |
| Enemies used Dirty Trick, Poison Dart and War Cry far more than damage; no hero was ever in danger | The second report of this (ST-3 in section 7.3). Measured there: with three heroes, 17% of enemy actions are attacks |
| Many reaction prompts: 8 reactions used in Run 1, 13 in Run 2 | ST-9 in section 7.3, with the pacing question |

**Measured since (owner decision D-36, decision log section 7.42):**

- The third battle is not easier in general: without a Guardian it is won less often than Battle 2
  at every party size (46 to 73% against 74 to 85%). For this playtester's party it is as easy as
  it felt (97%). It is a short battle, which is what the impression caught.
- Enemies seldom attack because a status on a hero who has none always comes first. That rule holds
  the difficulty: with enemies choosing by weight alone, 5% of runs are won instead of 77%.

**Tally of the fifth playtester:** 12 findings. 11 fixed (F9 in part), 1 half of F12 as designed.
One more fault of the same cause as F1 was found by reading and fixed.

**A consequence of the fixes, handled with them:** the mastery lines are longer now. With five
heroes they could have run out of the two mastery panels, so both panels size their text by
measuring. The largest case is drawn by a test in every font at both window sizes.
