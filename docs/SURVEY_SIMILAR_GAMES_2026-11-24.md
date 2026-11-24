# How similar games handle the scenarios we are deciding (survey, 2026-11-24)

The owner asked for a survey of a variety of similar games. This is it: what other games do in the
situations Battle Dice is deciding right now, where that agrees with our decisions (D-36 to D-38),
and where it does not.

## 1. Conclusions first

| Our scenario | What most other games do | Where we stand |
|--------------|--------------------------|----------------|
| Enemies that debuff instead of attacking | Bound the enemy's choices by an authored set: a die's six faces, a turn schedule, a rule against repeating a move, a cooldown or a use limit. None of the dice games needs a "no status twice" rule, because status sits on a few faces or turns | D-38's "never a status twice running" is Slay the Spire's kind of rule. Two cautions from the survey, in section 3 |
| Whom an enemy attacks, and ties | Two schools. **Random and shown** (Slice & Dice, Pokémon, Into the Breach). **By position, and said** (Dragon Quest, Final Fantasy I, Monster Train, Dicefolk, Gloomhaven's stated focus rules) | Our fault was a rule that was hidden and absolute. D-38's seeded draw puts us in the first school, which fits a game that shows the intent. The second school is a real alternative, not a mistake |
| Shown intent with reactions | Most games that show intent have **no** reaction windows. Those that have them (Baldur's Gate 3, Solasta, Magic Arena) all built tools to cut prompts | We combine both. Our many prompts with five heroes (finding ST-9) are the cost every such game had to deal with |
| Difficulty by party size | Careful games author each size (Gloomhaven, Pathfinder 2e). Formula games disagree on the curve | Our table per party size is the careful way. The survey warns against deriving one size from another |
| Win rate target | Roguelikes sit at 9 to 25% for all players. No published rule for a "good" first difficulty was found | Our 70 to 85% is far above that. It is nearer a tactics campaign, and it is the rate of an informed player: a ceiling |
| The optional harder battle | Usually paid for before the fight, built to feel different, and risky: the Heart of Slay the Spire ends about half the runs that reach it | Ours is a free choice afterwards, at about 75% with a Guardian. It has its own reward (mastery at a threat that nothing else gives) |
| Class progression | Our "8 ranks, points per won battle, advanced needs mastery" is the Dragon Quest VI model | Dragon Quest asks 120 to 200 battles for a basic vocation. Ours is far cheaper, as it must be with 2 or 3 battles a run |
| Balancing with a simulated player | Known pitfall: the simulated player's habits end up in the numbers | We met exactly that this week (decision log 7.43) |

**Nothing in the survey says that a decision of D-36 to D-38 is wrong.** It shows three places where
other games chose differently for good reasons, and four improvements worth considering. Both lists
are in sections 3 and 4.

## 2. How this was made, and how sure it is

- Three research threads on the web, each told to give a source for every claim and to mark what it
  could not confirm: dice-based games with a party; enemy choice, target choice and reactions in
  turn-based games; scaling, optional fights, progression and simulated players.
- **Limit:** most pages could not be opened directly from this environment and were read through a
  search service's extracts, so some were seen only in part. Claims below carry a source; those
  marked *(unverified)* are recollection, and *(player claim)* is a forum statement.
- **My own checks:** I opened three sources that bear on our decisions. The Dragon Quest VI table of
  battles per rank is as quoted. The Dicey Dungeons developer post on enemy AI and the Gloomhaven
  focus rules exist and say what is described; I did not re-read every figure in them.
- Not found, and said so: stated developer targets for win rate or turns per battle (only Into the
  Breach's four to five turns is on record); Banner Saga; Tactics Ogre; Wildermyth's class pacing.

## 3. Where other games chose differently from us

**3.1 A rule per enemy does not stop a group.** Slay the Spire's limits are per enemy, and some
enemies are meant to debuff most turns. Dragon Quest limits certain actions to once per turn for a
whole monster group. Our rule is per enemy and global: four enemies can still all use a status
ability in the same round, and no enemy can be a "debuffer" by design.
*What we know:* under the new rule attacks are about 40% of enemy abilities at every party size
(decision log 7.43). *What we do not know:* how often a whole round is statuses only.

**3.2 The cause may be the priority, not the repetition.** Pokémon and Darkest Dungeon treat "the
target does not have the status yet" as a weight or a filter. Battle Brothers scores every option and
draws by weight, so an attack always keeps a chance. Dicey Dungeons scores damage above any status.
Our enemies put such a status in a tier above every attack; D-38 keeps the tier and adds an
exception. We measured the plain weighted draw (variant B, decision log 7.42): it wins 5% of runs
with today's tables, so it would need a far larger retune. The approved rule is the smaller change.

**3.3 Order as an open tactic.** Dragon Quest attacks party slots at about 40/30/20/10 and the
recent remake says so. Final Fantasy I uses 50/25/12.5/12.5. In Monster Train and Dicefolk the front
unit is the one that is hit, and arranging units is the game. D-38 removes the order as a factor.
We keep one positional rule that is stated: a standing front row shields the back row from melee.

**3.4 Strict "hurt most, then most wounded" is focus fire.** Darkest Dungeon mixes weighted wishes
with randomness; Slice & Dice is random unless a monster carries a named keyword ("Heavy": the hero
with most health; "Eliminate": the one with least). Named, visible targeting habits give enemies
character and soften snowballing. Ours all choose the same way.

**3.5 The optional fight is usually bought and is usually a coin flip.** Slay the Spire's fourth act
needs three keys, each paid for during the run. Monster Train's extra boss stakes the unlocks of the
normal final boss as well. Ours costs nothing before, and is won three times in four with a Guardian.
That was the owner's own target (D-27), so this is a difference to know about, not a fault.

## 4. Improvements worth considering (nothing here is decided)

| Idea | Seen in | What it would do for us | Size |
|------|---------|-------------------------|------|
| A setting per reaction: ask, use by itself, never | Baldur's Gate 3 | Cuts the prompts with four and five heroes; a cheap reaction can fire by itself | Medium: settings, controller, tests |
| Say before a battle that it gives a hero no mastery | Dragon Quest hides it and players are confused by it; Darkest Dungeon makes heroes refuse | Ours says it after the battle ("+0: this battle is too easy for its rank"). Before is when it helps | Small |
| Keep the old simulated player beside the new one | An indie developer's account: "improving the bot destroyed the baseline" | Two rulers: one frozen for comparison over time, one improved. We are about to replace policy 2 with policy 3 | Small: both are in the code already |
| A targeting habit per enemy kind, shown on the intent | Slice & Dice keywords, Dragon Quest traits | Enemies that differ in whom they hunt; a visible reason for each attack | Medium to large: rules, content, balance |

Smaller observations that confirm what we have:

- **Two rerolls with dice that can be kept** is Slice & Dice's rule too. Blank faces are common.
- **A choice of three upgrades** is the norm (Astrea, Die in the Dungeon, SpellRogue, Tamarak
  Trail). Several let the player decline for currency; we have no currency, so nothing to decline for.
- **Showing the enemy's intent before the player commits** is universal in this family.
- **Bounding a last battle on both sides** (a floor against one lucky burst, a ceiling against a
  slog) is how the Heart is built. D-38's "a quarter longer" moves ours in that direction.

## 5. The tables

### 5.1 How enemies choose, and how spam is limited

| Game | What it does | Source |
|------|--------------|--------|
| Slay the Spire | Fixed rotations, or random move sets with code against repeating a move too often; limits are per enemy; some buffs have a use limit | Ars Technica interview transcript; slaythespire.wiki.gg |
| Dragon Quest 3 to 11 | Six to eight action slots per monster, random or in rotation; some actions once per turn for a whole monster group | Japanese Dragon Quest dictionary wiki; dqrta.com |
| Pokémon (third and fourth generation AI) | Every move starts at 100; a status move loses 10 when the target already has a status | Decompiled source (pret/pokeemerald); pokemow.com |
| Darkest Dungeon | Weighted wishes per monster, one of them "has the hero the status?", and cooldowns; after a stun the hero resists the next one better | Official modding guide; wiki |
| Battle Brothers | Every behaviour is scored, weak ones dropped, then a weighted draw | Developer blog 27 |
| Wildermyth | Abilities carry a priority and a cooldown; the developers' tutorial limits one to once per turn "or else the AI will just spam it" | Developer devlog; wiki |
| Slice & Dice | Each monster is a six-sided die that rolls before the player; a status is on some faces only | Help text; forum and wiki |
| Dicey Dungeons | The enemy searches its possible moves and scores them: damage highest, poison next, other statuses half | Developer blog (distractionware.com, 2018) |
| SpellRogue, Die in the Dungeon | Authored intents on a turn schedule, damage turns alternating with buff or debuff turns | Game wikis |
| Astrea, Dicefolk | Enemies roll their own visible dice; in Dicefolk the player decides the order they resolve in | Game wikis; reviews |
| Too Many Bones | Enemies roll attack and defense dice; special skills need enough "bones" faces in that turn | Rulebook |

### 5.2 Whom enemies attack

| Game | Rule | Told to the player? | Source |
|------|------|---------------------|--------|
| Slice & Dice | Random among living heroes; keywords force most or least health; shown before the player acts | Yes | Help text; wiki |
| Pokémon | Each move scored per target; ties drawn at random | No | Decompiled source |
| Into the Breach | Target chosen at random when the enemy acts, then drawn on the board | Yes | Developers' talk (GDC) |
| Dragon Quest | By party slot, about 40/30/20/10; some monsters hunt the weakest or the rear | Partly | Dictionary wiki |
| Final Fantasy I | By party slot, 50/25/12.5/12.5 | Not in the game *(unverified)* | Wiki; guide |
| Monster Train, Dicefolk | The front unit is hit | Yes | Guides; wiki |
| Gloomhaven | Stated focus rules: least movement, then nearest, then earlier initiative | Yes, rulebook | Rules reference |
| Too Many Bones | Nearest; ties by the enemy's icon; remaining ties: the players choose | Yes | Rulebook |
| Darkest Dungeon 1 and 2 | Weighted wishes (random, marked, least health); taunt and stealth as visible tokens in the second game | Partly | Modding guide; wiki |
| Final Fantasy Tactics | A value from health and from statuses the unit already has | No | Reverse-engineered (forum) |

### 5.3 Shown intent and reactions

| Game | What it does | Source |
|------|--------------|--------|
| Slay the Spire, Into the Breach, Slice & Dice, Monster Train | Intent shown; no reactions at all | Interviews; developers' talk |
| Baldur's Gate 3 | Each reaction: on, off, or ask; one asked reaction per character per event | bg3.wiki |
| Solasta | A prompt per reaction with a countdown; a shield prompt appears only when it could change the result | Developer diary; patch notes |
| XCOM, Wildermyth, Hearthstone | Committed in advance on one's own turn, then automatic | Wikis; interview |
| Gloomhaven | One decision outside one's turn: take the damage or lose a card | Rulebook |
| Magic Arena | Passes by itself where a response is rare; the player sets stops | Guides |

### 5.4 Party size, win rates, the optional fight, battle length

| Topic | Game | What it does or shows | Source |
|-------|------|-----------------------|--------|
| Party size | Gloomhaven | Monsters authored per number of characters; one player running several: one level harder | Rules |
| Party size | Pathfinder 2e | A budget for four, plus or minus a fixed amount per character; "add or remove enemies rather than making one tougher" | Rules reference |
| Party size | D&D 5e (2014) | Fewer than three characters: the next higher difficulty multiplier | Basic rules |
| Party size | Too Many Bones | Enemy budget = day times number of heroes | Rulebook |
| Party size | Monster Hunter Wilds | Monster health 100 / 163 / 200 / 234% for one to four players | Forum answer citing a post |
| Party size | Divinity: Original Sin 2 | "Lone Wolf" buffs parties of one or two, and overshoots | Wikis |
| Win rate | Slay the Spire | About 9% of all runs won; over 60% for top players | Run-data analysis |
| Win rate | Monster Train, Hades | 13% of owners beat the fourth difficulty step; 44.5% of owners ever finished a run | Achievement figures (seen in summaries only) |
| Win rate | Slice & Dice | Top players about 99% on Hard *(player claim)* | Forum |
| Win rate | XCOM 2 | Players read 85% as near-certain; the game quietly helps on the easy setting | Designer interview |
| Optional fight | Slay the Spire, fourth act | Paid with three keys; the Heart ends 48 to 53% of runs that reach it; damage cap and a growing buff bound its length | Wiki; data analysis; guide |
| Optional fight | Monster Train | Losing to the extra boss also cancels the normal boss's unlocks | Wiki |
| Optional fight | Slice & Dice, Die in the Dungeon, SpellRogue | Take the reward and fight an extra set; elites give an upgrade | Wikis; guides |
| Optional fight | Dungeon Roll (dice board game) | After each level: stop and bank, or go on and risk the experience | Rules |
| Length | Into the Breach | Four to five turns, fixed; the designers found it by accident and kept it | Developers' talk |
| Length | Darkest Dungeon | Stalling is punished after three quiet rounds | Wiki |
| Length | Too Many Bones | After round five, fatigue rounds until the battle ends | Rulebook |

### 5.5 Class progression, and simulated players

| Game or source | What it does or reports | Source |
|----------------|-------------------------|--------|
| Dragon Quest VI | Eight ranks counted in battles won: 120 to 200 for a basic vocation, 200 to 300 for an advanced one; advanced vocations need two or three mastered ones | Fan site table (checked) |
| Dragon Quest VI and VII | Above an area's level cap a battle gives no vocation credit; the game does not say so | Guides; forum threads |
| Final Fantasy Tactics | Points per action; new jobs open at partial levels, not at mastery | Design blog; guide |
| Fire Emblem | Experience shrinks as the level rises; a hidden "internal level" slows re-classing | Wiki |
| Darkest Dungeon | Heroes refuse quests two or more levels below them | Wiki |
| Slay the Spire developers | Balanced from logged runs; a card looked too strong because it was mostly found late in winning runs | Developers' talk; article |
| King (Candy Crush) | Agents trained on human moves predicted difficulty better than search bots | Conference paper abstract |
| Ticket to Ride study | Hand-written agents per play style found rule holes; results were "biased toward those playstyles" | Paper |
| Two indie developers | Nightly bot runs; "improving the bot destroyed the baseline"; fix: one frozen bot and one human-like bot | Blog; interview |

## 6. Sources

The research threads read about 150 pages or extracts. The ones the claims above rest on:

- Slay the Spire: slaythespire.wiki.gg (Shapes, Multiplayer); foxrow.com/slay-the-spire-statistical-analysis;
  slay-the-spire.fandom.com/wiki/Act_4; thegamer.com (fourth act guide);
  gamedeveloper.com (how the developers use data); Ars Technica interview transcript
- Slice & Dice: tann.itch.io devlog (version 2.0); slice-and-dice.fandom.com (Heavy, Thorn);
  minmax.wiki/slice-and-dice; forum.quartertothree.com thread
- Dicey Dungeons: distractionware.com/blog/2018/12/how-enemy-ai-works-in-dicey-dungeons/
- Dragon Quest: wikiwiki.jp/dqdic3rd (action patterns; party order); dqrta.com;
  woodus.com/den/games/dq6ds/voc_battles_needed.php; strategywiki.org (Dragon Quest VI vocations)
- Darkest Dungeon: official modding guide (Steam); darkestdungeon.wiki.gg (Stun, Tokens, Stalling,
  Retreating, Resolve Level)
- Gloomhaven: rules.dized.com (monster focus); github.com/m-ender/gloomhaven-rules; havenhints.com
- Pokémon: github.com/pret/pokeemerald (battle_ai_script_commands.c); pokemow.com/Gen4/TrainerAI
- Battle Brothers: developer blog 27 (battlebrothersgame.com/?p=1150, read on a mirror)
- Baldur's Gate 3 and Solasta: bg3.wiki/wiki/Reactions; solasta-game.com developer diary 1
- Into the Breach: the developers' postmortem talk (transcript)
- Monster Train: monster-train.fandom.com (The Last Divinity, Pact Shards)
- Other dice games: astrea.wiki.gg; spellrogue.wiki.gg; dieinthedungeon.miraheze.org;
  dicefolk.wiki.gg; rulebooks of Too Many Bones, One Deck Dungeon, Dice Throne Adventures and
  Roll Player Adventures
- Party size: 2e.aonprd.com (encounter budget); dndbeyond.com basic rules 2014;
  deeprockgalactic.wiki.gg; dos2.wiki (Lone Wolf)
- Progression: designoriented.net (jobs in Final Fantasy Tactics); fireemblemwiki.org/wiki/Level
- Simulated players: nealen.net/papers/DeMesentier2017AI.pdf; dl.acm.org/doi/10.1109/CIG.2018.8490442;
  metah.dev (balance bot post); nature.com/articles/s41467-019-12552-4 (the "85% rule" for learning)
