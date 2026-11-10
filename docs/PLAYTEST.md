# Battle Dice: scenario-based playtest

- **Date:** 2026-11-10. **Build:** rules 1.1.1, content 1.2.1 (`main` at `23ec4ae`).
- **Executed by:** scripted personas and a screen-driven session in a headless container.
- **Not covered:** play by a person. Section 6 is a ready-to-run session script for that.

## 1. Summary

| # | Finding | Severity | Evidence |
|--:|---------|----------|----------|
| 1 | Action previews show base numbers, never the number that will happen. A weakened Jab reads "1 melee damage" and deals 0. | High | Scenario T3; `core/view.py` never calls the bonus or penalty functions |
| 2 | A first-time player who presses the obvious buttons wins 8% of runs, less than random play (16%). Nothing prompts the two habits that decide runs: rerolling and reacting. | High | Personas P1, P2, P3; screen session U1 |
| 3 | The choices between battles do not change who wins. Worst upgrade against best: 1 point. Bench die swapped in: 0 points. | Medium | Personas P5, P8 |
| 4 | The rules allow swapping a hero's main die for the bench d4, with no warning. It costs 21 points. | Medium | Persona P9 |
| 5 | A player who does not react is asked to react 1.3 to 1.5 times per hero turn. One two-battle run took 230 inputs, 64 of them "Skip Stage". | Medium | Screen session U1; personas |
| 6 | Rerolling carries almost no risk. "Reroll until the die shows its best face" loses only 4 points. | Medium | Persona P7 |
| 7 | The status bar says "rules 1.2.1". That number is the content version; the rules are 1.1.1. | Low (defect) | `ui/screens.py` line 105 |
| 8 | During a reaction decision the status bar still reads "Plan locked. Resolving." | Low | Screen session U1 |
| 9 | Dice that are in the plan still carry the label "will reroll". | Low | Screen session U1 |

**What works** (each observed, not assumed): an illegal plan is refused with the rule that forbids
it; a protected target says why; a revival face says what it revives to; an empty roll leads to a
clear "choose a die, or Pass"; skill matters (informed 90%, random 16%); no single habit wins
(always-attack 73%, always-defend 66%); 16% of informed wins came after a hero had fallen.

No game behaviour was changed by this playtest. The findings are for the owner to prioritise.

## 2. Method

Four established practices, adapted to what can be executed without a person at the keyboard.

| Practice | Source | How it is used here |
|----------|--------|---------------------|
| Task scenarios: give the player a goal, observe, and keep "what happened" apart from "what it means" | Game-design course and practitioner guides (links in section 7) | Every scenario has a goal, a start state and an observation list; section 4 records observations before section 1 interprets them |
| RITE (Rapid Iterative Testing and Evaluation): fix a problem as soon as it is understood, then test again | Medlock, Wixon and colleagues, Microsoft games user research | The scenario set is a re-runnable tool, so each fix can be re-tested the same day (section 5) |
| Playability heuristics: judge game play, mechanics and usability as separate areas | Desurvire and colleagues (HEP, later PLAY) | The three scenario groups below; the screen session is judged on usability only |
| Procedural personas: scripted players that each stand for one style of play | Holmgard, Green, Liapis and Togelius, 2019 | Twelve personas, each the informed player with one habit changed |

**Limits.** Personas measure whether a mechanic changes who wins, not whether it is fun. The
screen session was played by an AI model reading screenshots, which finds missing or wrong
information but cannot stand in for a person's patience, confusion or enjoyment.

## 3. Scenario catalogue

### Group A. Does each mechanic matter? (personas)

- **Set-up:** shipped content, six parties in their suggested rows (each class solo; Squire +
  Apprentice + Scout; that trio plus a Squire; that four plus a Scout), seeds 0-79, 480 runs
  per persona.
- **Reference:** the informed player (simulated player version 2, decision log 7.6).
- **Prediction** written before the 80-seed run (a 2-seed smoke run of the tool had been seen).
  The noise on a 480-run difference is about 3 points.

| ID | Question | Persona: the one habit changed | Prediction | Result against informed (90.2%) | Verdict |
|----|----------|-------------------------------|------------|-------------------------------:|---------|
| P1 | Does skill matter? | `newcomer`: no rerolls, no reactions, first usable die on the first target | At least 20 points lower | -82.5 (7.7%) | Yes, and steeply |
| P1b | Where is the floor? | `uninformed`: random legal decisions | Below the newcomer | -74.6 (15.6%), **above** the newcomer | Prediction wrong |
| P2 | Do rerolls matter? | `no_reroll` | At least 10 lower | -48.7 | Yes: the largest single habit |
| P3 | Do reactions matter? | `no_reaction` | At least 5 lower | -24.4 | Yes |
| P4 | Does aiming matter? | `random_target` | At least 5 lower | -6.9 | Yes, modestly |
| P5 | Does the upgrade matter? | `worst_upgrade` | At least 3 lower | -1.2 | **No** (within noise) |
| P6 | Does one habit win? | `attacker`, `defender` | Both at least 5 lower | -17.1, -24.0 | No dominant habit |
| P7 | Is rerolling a real decision? | `gambler`: keep a die only on its best face | At least 5 lower | -4.0 | **Weak**: over-rolling is barely punished |
| P8 | Is the bench die a real choice? | `bench_swapper`: bench d4 in for the starting d4 | At least 3 points either way | -0.2 | **No** |
| P9 | Can a swap hurt? | `main_die_swapper`: bench d4 in for the d6 or d8 | Not predicted (found during the run) | -21.0 | Yes: an unguarded trap |
| P10 | Does formation matter? | informed, every row inverted | At least 10 lower | trio -2.5, four -56.2, five -10.0 | Only for some parties |

Play-experience measures from the same runs:

| Measure | Informed | Newcomer | Defender |
|---------|---------:|---------:|---------:|
| Runs lost in Battle 1 | 4.2% | 72.1% | 6.5% |
| Decisions per run (median) | 182 | 132 | 417 |
| Hero turns with nothing done | 2.7% | 4.6% | 7.8% |
| Rerolls used per hero turn (of 2) | 1.67 | 0 | 1.68 |
| Reaction prompts per hero turn | 0.40 | 1.47 | 0.28 |
| Health left at victory | 77% | 38% | 82% |
| Wins after a hero had fallen | 15.9% | 0% | 22.0% |

- The informed player wins 100% with five of the six parties, so differences are compressed at
  the top. The class balance retune in progress addresses that; the personas should be re-run on
  the retuned content.
- Decisions per run by party, informed: solo Scout 55, solo Apprentice 73, trio 181, solo
  Squire 184, four 300, five 339.

### Group B. First session through the real screens

- **U1 goal:** from the main menu, play a whole run as a first-time player, using only what the
  screen says. Party: Squire, Apprentice, Scout. Seed 21, 1280x720.
- **Driver:** real key and mouse events sent to the game; a screenshot at every new situation.

### Group C. Tactical situations (forced rolls, real screens)

| ID | Situation | What the player needs to learn from the screen |
|----|-----------|-----------------------------------------------|
| T1 | Squire rolls Strike and clicks the back-row Hex Adept | Why the click is refused |
| T2 | An ally is down and the Squire rolls Rally | That Rally can target the fallen ally, and what it does |
| T3 | A weakened Squire rolls Jab | How much damage it will really deal |
| T4 | Blank and a useless face, no rerolls left | What to do next |
| T6 | The Squire is at the shield cap when an enemy attacks | Whether a wasted Interpose is offered |

## 4. Observations (what happened)

### U1. First session

| Step | Inputs | Observed |
|------|-------:|----------|
| Menu to first hero turn | 5 | Menu, party set-up and the first "Roll Dice (R)" each name the next key. The status bar reads "rules 1.2.1". |
| First roll | 1 | Both dice show their face, rules text and odds. Each die is labelled "will reroll" before the player has chosen anything. |
| Aim Shot at the Hex Adept, then add Quick Shot | 4 | The second action is refused with "Exploit Combo: two actions are only allowed as Status first, then Attack." Confirm is disabled. Both dice read "IN PLAN" and still "will reroll". |
| First reaction prompt | 0 | The panel names the enemy action, its target and the reaction offered (Grounding). The status bar still reads "Plan locked. Resolving." |
| Battle 1 as a newcomer | 157 | 33 hero turns and 39 reaction prompts, every one skipped. Battle won. |
| Upgrade screen | 4 | Starting Battle 2 without an upgrade is refused: "A dice upgrade must be applied before Battle 2." |
| Battle 2 as a newcomer | 64 | 10 hero turns, 25 reaction prompts. Defeat. |
| Defeat screen | 0 | Shows "Rerolls used 0" and "Reactions used 0" among eleven figures. No advice. |

### Tactical situations

| ID | Observed |
|----|----------|
| T1 | "Hex Adept is protected: melee must target the standing front row first." Targeting stays open. |
| T2 | Rally reads "heal 2 (revives to 2 HP); costs 1 mana". The fallen Apprentice is selectable and stands up with 2 HP. |
| T3 | Jab reads "1 melee damage". With one Weaken stack it deals 0. The penalty appears only in the combat log, after the action. |
| T4 | "No action selected. Choose a die, or Pass." A further R gives "No rerolls remaining this activation." |
| T6 | Interpose is offered for the Squire at 12 of 12 shields. Using it spends 1 mana for nothing. |

## 5. Interpretation and suggested responses

Each is a suggestion for the owner, not a change that was made.

1. **Show the real number (finding 1).** The game promises "every die face visible", and the
   planner is where a player decides. Show the effective amount when it differs from the base:
   "1 melee damage (0 while weakened)". The same gap exists for the Squire's Steadfast +1 and the
   Scout's combo +1, because no preview calls `effects.damage_breakdown` or `effects.shield_bonus`.
2. **Teach rerolls and reactions (finding 2).** A newcomer loses 72% of runs in Battle 1. Small
   options: a one-line hint on the first roll ("R rerolls every die you have not kept"); on the
   defeat screen, one sentence when rerolls or reactions were never used.
3. **Give the between-battle choices weight, or say they are flavour (findings 3 and 4).** With
   one upgrade in a two-battle run, no card changes the result. Block or warn on swapping out the
   larger die.
4. **Cut prompts that need no decision (finding 5).** Options: one key that skips all three
   stages for the current enemy action; do not offer Interpose at the shield cap.
5. **Decide whether rerolls should cost something (finding 6).** As it stands the best habit is
   close to "always reroll", which adds inputs without adding a decision. This is a design
   question for the owner.
6. **Small fixes (findings 7 to 9).** Label the version correctly; set a status line when a
   reaction decision opens; hide "will reroll" on dice that are in the plan.

**Re-test loop (RITE).** After any change, re-run the personas and compare with the table in
section 3:

```bash
python tools/playtest_scenarios.py --seeds 80 --jobs 4 --out playtest_results.json
```

`--content-dir DIR` runs the same scenarios on a candidate content set.

## 6. Session script for a human playtest

One person who has not played, about 30 minutes, the game on a real Windows display.

- **Before:** start a screen recording. Say: "We are testing the game, not you. Please say what
  you are thinking as you play." Do not explain any rule.
- **During:** stay silent. Write down what the player does and says, with the time. Do not
  write what you think it means.

| Task given to the player | Watch for | Success |
|--------------------------|-----------|---------|
| 1. "Start a game with any three heroes." | Hesitation on the party screen; whether rows are noticed | Battle 1 starts within 2 minutes |
| 2. "Take your first turn." | Whether Roll, Keep, Use and Confirm are found unaided; whether a reroll is tried | A plan is confirmed without help |
| 3. "An enemy is about to act. Decide what to do." | Whether the reaction panel is read or skipped unread | The player can say what the reaction would do |
| 4. "Tell me how much damage this attack will do." (ask when a hero is weakened) | Whether the answer matches what happens | The stated number is the real number |
| 5. "Finish the battle." | Number of times Skip Stage is pressed; sighs, comments on pace | Battle ends; note the time |
| 6. "Choose an upgrade." | Whether before and after faces are compared | The player can say why they chose it |
| 7. "Play to the end, then try again." | Reaction to the outcome screen; whether Retry is found | A second run is started |

- **After:** ask three questions and record the answers word for word. "What was the game asking
  you to do?" "What was the most confusing moment?" "What would make you play again?"
- **Between players:** if a problem is clear and the fix is clear, fix it before the next player
  and note which build each player saw.

## 7. Sources

- RITE method: [Wikipedia](https://en.wikipedia.org/wiki/RITE_Method); Medlock, Wixon, McGee
  and Welsh, "The Rapid Iterative Test and Evaluation Method", in
  [Cost-Justifying Usability](https://www.globalspec.com/reference/42299/203279/chapter-17-the-rapid-iterative-test-and-evaluation-method-better-products-in-less-time) (2005).
- Session structure and observation discipline:
  [Playtesting 105: how to measure qualitatively](https://www.gamedeveloper.com/design/playtesting-105-how-to-measure-qualitatively);
  [in-person playtest script template](https://lively-kernel.org/lively4/gs/playtesting/templates/playtest-script-in-person.md).
  These are practitioner guides, not peer-reviewed studies.
- Think-aloud in games: [Playing Aloud: Leveraging Game Commentary Culture for Playtesting](https://igi-global.com/article/playing-aloud/296705).
- Playability heuristics: Desurvire and colleagues, Heuristics to Evaluate Playability (HEP),
  [CHI 2004](https://hci.rwth-aachen.de/materials/conferences/CHI2004/2p1509.pdf);
  Desurvire and Wiberg, Principles of Game Playability (PLAY),
  [LNCS 5621, 2009](https://link.springer.com/doi/10.1007/978-3-642-02774-1_60). Only the
  category structure was used; the full heuristic list was not retrieved.
- Procedural personas: Holmgard, Green, Liapis and Togelius, "Automated Playtesting with
  Procedural Personas through MCTS with Evolved Heuristics",
  [IEEE Transactions on Games, 2019](https://www.antoniosliapis.com/papers/automated_playtesting_with_procedural_personas_through_mcts_with_evolved_heuristics.pdf).
  The personas here are hand-written heuristics, not evolved MCTS agents.
