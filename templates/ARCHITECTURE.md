# Architecture — <system name>

> **The single system doc for this repository: `docs/ARCHITECTURE.md`. There is exactly one.**
> It owns everything true across phases; per-subject truth lives in the subject docs listed in §7.
> Created by `/adopt`, extended by `/implement` as it builds.
>
> **Who writes what.** The board holds what we *intend* to be true — a Feature's goal and
> acceptance criteria, an Epic's phase goal. `docs/` holds what *is* true and why. `/discover` and
> `/kickoff` read these docs and write only to the board; **`/implement` is the only thing that
> writes into `docs/`**, in the same pull request as the code that makes the statement true.
>
> Status: **TEMPLATE — not yet filled**.

## 1. What this is

<!-- One paragraph: the product, and who it is for. If this system mirrors an existing product — a
     clone, a port, a replacement — name it and its version here, because it is the baseline every
     subject doc measures parity against in its §5. "Reference: none" is a valid answer. -->

## 2. Stack

<!-- Backend / Frontend / Data / Hosting target. Keep it in step with the Ivan project config's
     Stack line in CLAUDE.md. -->

## 3. How to run it

<!-- The exact commands to build, test and start each component, and the port override for each.
     The qa-verifier agent follows this section literally, so it must be current and complete — one
     canonical description, never a chain of per-phase deltas. Keep it identical to the config's
     Run commands line; if they disagree, fix both. -->

## 4. Project layout

<!-- Directory structure and what belongs where, including where docs/ subjects live. -->

## 5. Cross-cutting conventions

<!-- API shape, error format, validation strategy, state management, migration policy, logging —
     whatever build-mode Ivan must apply consistently in every subject. One list, in force, never a
     cumulative chain of "phase N's conventions still hold, these are the additions".
     Not coding style: that is docs/CONVENTIONS.md, owned by the linters. -->

## 6. Standing decisions

<!-- System-wide rules and permanent non-goals. Ids are global and permanent, never renumbered.
     S-1: <rule>. Because: <reason>. Status: active | superseded by S-N. -->

## 7. Subject map

<!-- Every long-lived subject folder. Add the row before creating the folder. A subject is a
     long-lived part of the SYSTEM — a sensible chapter heading three phases from now — never a
     phase, a sprint, or a feature. -->

| Subject | Path | Owns | Reference counterpart |
|---|---|---|---|
| | `docs/systems/<system>/` | | <name in the reference product> |
| | `docs/platform/<area>/` | | — (no counterpart) |

## 8. Decision index

<!-- Every decision in this repository, exactly once, ascending. APPEND ONLY. Ids are global and
     PERMANENT — never renumbered, never reused; a gap left by an abandoned branch is fine and is
     never filled. The full text lives in the owning subject doc's §4. Allocation is §9. -->

| D | Decision | Owner | Phase |
|---|---|---|---|

## 9. Doc conventions

Fixed rules for maintaining these documents. Do not edit per project.

- **`/implement` is the only writer.** `/discover` and `/kickoff` read these files so they do not
  re-decide what is settled, and record their own conclusions on the work item — an Epic
  description for a phase-wide decision, `## Implementation notes` on a Feature for a
  feature-scoped one. `/implement` promotes those to a `D-NN` in the same pull request as the code
  that makes them true. A decision that has not shipped is *intent*, and intent lives on the board.
- **Adding a subject**: add the §7 row, then create `<path>/SUBJECT.md` from the plugin's template.
- **Allocating a decision id**: read §8 from `origin/main`
  (`git fetch origin && git show origin/main:docs/ARCHITECTURE.md`), take max + 1, append one row
  at the end of the table, and write the `D-NN` block into the owning subject file **in the same
  commit**. Because rows are appended one per line in ascending order, two branches taking the same
  id conflict textually at that line rather than duplicating silently. On such a conflict the row
  already on `main` keeps the id; renumber yours to the next free id — heading, index row and every
  reference — in the same rebase. **An id that has reached `main` is frozen forever.**
- **A reversed decision is never deleted or renumbered.** Note it in the Decision column as
  *superseded by D-N* and leave the row.
- **A number is documented only once it has a name.** A `Tuning values` row cites the source symbol
  that owns the constant; a row citing a symbol that does not exist is a lie the next reader will
  act on. If a feature hard-codes a number with no name, give it one — an unnameable number is a
  good reason not to have written it.
- **Open questions never live in `docs/`.** They live on the work item they block, written once.
