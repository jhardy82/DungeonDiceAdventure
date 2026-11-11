# ADR-CE-001: A hero has exactly one active vocation

| Field | Value |
|-------|-------|
| Status | **Accepted.** Approved by the owner with FDD v0.2 on 2026-11-11 |
| Date | 2026-11-11 |
| Decides | Question Q15 of BD-UNIFIED-FDD-001 v0.1 (delegated to the designer) |
| Cited by | FDD v0.1 (its Q15 resolution) and fixture CE-17; never written until now |

## Decision

- A hero has **exactly one active vocation** at any time.
- The active vocation alone decides the hero's schedule, starting dice, native passive, native
  reaction, dice capacity and base stats.
- Other mastered vocations contribute only through two budgeted channels:
  - **Inherited skills**, equipped within the active vocation's inheritance capacity.
  - **Permanent stat rewards**, capped per hero (health +2, mana +1, speed +1).
- **Dice (owner decision, 2026-11-11):** a vocation may equip its own dice, plus the dice of the
  starting class it grew from (its family). It may equip no other vocation's dice. This is
  narrower than the free mixing rejected below: a family's dice were written for the same
  schedule shapes, and the catalog validator checks every such die against the vocation's rules.
- A command that asks for a second active vocation is rejected with
  `UNSUPPORTED_SECONDARY_VOCATION` and changes nothing.
- The active vocation changes only between encounters, never during a battle. Combat reads a
  fixed build snapshot taken when the encounter starts.

## Context

- The shipped rules give every class one schedule (for example "status, then attack"), one
  passive and one reaction, and the three reaction stages run in a fixed order: Guard, Resource,
  Interrupt.
- v0.1 chose one active vocation under the delegated question Q15 and pointed to this record
  for the reasoning, but the record did not exist.

## Alternatives considered

| Alternative | What it would allow | Why it was not chosen |
|-------------|---------------------|-----------------------|
| Two active vocations at once | A hero uses both schedules, passives and reactions | Two schedules can demand different first actions in one activation, and two reactions can claim the same stage. Every pair of vocations would need its own conflict rule and its own balance check: 91 pairs for 14 vocations, on top of 11,627 party compositions. |
| A primary vocation and a weaker secondary one | The secondary adds its passive or reaction only | Still doubles the reactions offered per enemy action, which the playtest already found too many (finding 5). Needs a rule for which reaction wins a stage. |
| Free mixing of dice from any mastered vocation | A hero equips any die it has earned | A schedule is written for its own dice. Foreign dice make some schedules impossible to satisfy and others trivially strong. |

## Consequences

- **Simpler rules.** The engine's planning, timeline and reaction code keep one schedule, one
  passive and one reaction per hero. No conflict rules are needed.
- **A bounded balance surface.** Each vocation is balanced on its own, plus its skill loadouts.
- **Less build freedom.** A hero who has mastered five vocations still plays as one of them. The
  inherited-skill budget is the only way to combine them.
- **Persistence.** The `hero` table has one `active_vocation_id` column, and a trigger requires
  that vocation to be unlocked for the hero.

## What a later second vocation would need

This decision defers a secondary vocation; it does not forbid one. Adding it later needs:

1. A rule for combining two schedules in one activation, or a rule that only the primary has one.
2. A rule for which reaction is offered at each stage, with at most one reaction per hero per
   enemy action kept.
3. A new column or table for the secondary vocation, and a schema migration.
4. A new decision record that replaces this one, and removal of
   `UNSUPPORTED_SECONDARY_VOCATION` from the code registry.
5. A fresh balance pass over vocation pairs.

## Verification

- Fixture CE-17 ("One active vocation only") specifies the rejection.
- The persistence tests check the trigger on `hero.active_vocation_id`.
