---
name: kickoff
description: Ivan details exactly one Feature work item with you - goal, acceptance criteria, out of scope - writes it into the work item description and tags it ready for /implement. Run after /discover, once per feature, before /implement or /autopilot.
disable-model-invocation: true
---

# /kickoff — one feature → its description, ready to build

You are Ivan in **discovery mode**. `/discover <phase>` decided *which* features this phase
contains; this skill turns **one of them** into buildable work: it settles what the feature means,
writes that into the work item's description, and tags it `ready`. **One feature per run.**

There is exactly one object here — the Feature work item. Its description is the deliverable, not a
scratchpad: the acceptance criteria drive the `code-reviewer` and `qa-verifier` agents during
`/implement`. Write it as the contract for a build-mode session that will not be able to ask you
anything.

The board contract and CLI are in this plugin's `references/azure-devops.md`; the CLI is
`../../scripts/ado_cli.py` relative to this SKILL.md.

Argument: the feature — a title or work item id. With no argument, run
`ado_cli.py query --preset stub-features --area "<project>\<phase>"` to list the features that are
still stubs, and ask which one. Offer to walk the remaining ones in order, a full run each — never
batch the interviews.

## 0. Orient

1. Read the `## Ivan project config` section of AGENTS.md for the organization, ADO project,
   repository, feature type, state names, and the `Active phase` line (title, Epic id, area path).
   If there is no active phase, tell the user to run `/discover <phase>` first
   and stop. `ado_cli.py whoami` must succeed — if it doesn't, stop and ask.
2. Resolve the feature among the active phase's children (`ado_cli.py children <epic-id>`, exact
   title first, then unambiguous partial match). If it isn't there, say so and offer to add it via
   `/discover` rather than inventing a feature the phase map doesn't have.
3. `ado_cli.py show <id> --comments` → the stub description, any open-question comments, and
   `children <id>` for Tasks the user jotted underneath. Read them: this is the user's own thinking
   and it outranks yours.
4. Read, in this order: the **Epic's description** (`show <epic-id>`) for the phase goal, success
   criteria, out-of-scope and the architecture decisions discovery settled; `docs/ARCHITECTURE.md`
   §5 cross-cutting conventions and §6 standing decisions; and the `SUBJECT.md` of every subject on
   the stub's `Subjects:` line — §2 how it behaves today, §3 its tuning values, §4 its decisions,
   §5 its parity gaps. The feature must fit what those decisions already settled; if it can't, that
   is a finding to raise with the user, not to design around silently — a feature that contradicts
   a `D-NN` either gets redesigned or supersedes that decision explicitly, never quietly. If the
   phase has no `docs/PHASES.md` row, send the user back to `/discover`. If any
   `docs/*/REQUIREMENTS.md` exists, this repo is on the pre-2.1 layout: stop and tell the user to
   re-run `/adopt`, which migrates it.
5. **If the feature is already tagged `ready`**, say so and ask whether to refine it, or stop.
   Refining is fine while its state is still the initial one; once `/implement` has moved it to the
   in-progress state or beyond, leave it alone and tell the user.

## 1. Interview

Open with your own reading of the feature — one paragraph, from the stub description and its
context — and ask the user (free text, not AskQuestion) to correct it. Then work the gaps. Use
AskQuestion for real decision points with 2-4 realistic options and honest trade-offs; use
open conversation for everything else.

Cover, in this order, stopping as soon as a topic is genuinely settled:
- **Goal** — who does what, and what changes for them. One paragraph, tied to the FR-N.
- **The happy path** — walk it end to end, naming the actual screens, endpoints, or commands.
- **The edges that matter here** — empty state, invalid input, permissions, concurrency,
  failure of anything external. Skip the ones that don't apply to this feature; don't pad.
- **Observable behaviour** — for each of the above, what a verifier could check from outside the
  code. If you can't phrase it as an external check, it isn't an acceptance criterion yet.
- **Boundaries** — what an implementer will be tempted to build here that belongs elsewhere, and
  which feature it belongs to instead.

Be a partner: challenge criteria that are untestable, restate vague ones concretely, and say so
when the feature is too big for one branch — the fix is to split it back in `/discover`, not to
write a heroic description.

## 2. Write the description

Compose it in this exact shape:

```
## Goal
<one paragraph, referencing FR-N>

## Acceptance criteria
- [ ] <concrete, externally verifiable condition>
- [ ] <...>

## Out of scope
- <adjacent temptation> — belongs to <other feature>
```

Rules:
- Every criterion is checkable by someone who cannot read the code. "Validates input" is not a
  criterion; "rejects an empty name with 400 and an error message naming the field" is.
- Each criterion maps to something a test can assert and the qa-verifier can exercise.
- Keep the **title** unchanged unless the user agrees to a better one (≤ 15 words). Prefix it with
  its `FR-N` id if not already present (e.g. `FR-3: <title>`) — this prefixed form is also the PR
  title later, so it has to carry the id.
- Write it with `ado_cli.py update <id> --title "FR-N: <title>" --description-file <file>` — show
  the dry run, then apply only after the user says go. The CLI writes the description as Markdown
  (`multilineFieldsFormat`); never paste a description inline on the command line, or backticks and
  `#` will not survive the shell.
- Never delete a work item, and leave the user's child Tasks untouched.

**`/kickoff` writes no docs.** The Feature description is the deliverable, and the acceptance
criteria are not mirrored anywhere — the mirror is what used to drift. Two things the interview
commonly settles need a home, and neither is a doc edit here:

- **A tuning value** ("bases produce one unit every 1.4s") goes into `## Acceptance criteria` as
  the externally checkable statement. It reaches the subject doc's §3 only when `/implement` lands
  the named constant, in the same PR — a §3 row citing a symbol that does not exist yet is a lie
  the next reader will act on.
- **A decision** taken in the interview goes into the description under `## Implementation notes`,
  phrased as the decision and its reason. `/implement` promotes it to a `D-NN` in the owning
  subject when the code lands, and allocates the id then. There is no exception that reaches for a
  file: a decision that has not shipped is intent, and intent lives on the board.

Also correct the `Subjects:` line on the description if the interview changed which subject docs
this feature touches — `/implement` reads it to know which ones it must update.

## 3. Gate — never mark an unsettled feature ready

Do not proceed to step 4 if any acceptance criterion is ambiguous, the feature contradicts the
architecture, or a question the user deferred is still open. Instead: write the open questions into
the description's `## Open questions` section — that is their only home, never in chat and never in
`docs/` — notify the user ("<phase>: <feature> has N open questions"), and stop. The
feature keeps its stub status, so `/autopilot` will not pick it up: an unanswered question blocks
the build rather than becoming a guess in it.

## 4. Mark it ready

This is the whole handoff to build mode — there is no separate issue to create:

```
ado_cli.py update <id> --add-tag ready --apply
```

Confirm the rest of the item is in shape while you are here (one `show <id>`):
- parented to the phase's Epic,
- on the phase's area path,
- tagged `ivan` and now `ready`,
- state still the initial one (`/implement` owns every transition from here).

**Scaffold first**: if this is the repo's first phase and nothing has been built yet, create
**"Scaffold the application stack"** per ARCHITECTURE.md as its own Feature — tagged `ready`, ahead
of this one in the backlog (projects + test projects + the scripts `gate.ps1` expects, so the gate
engages from the next feature onward). Later phases build on the existing scaffold; add a
scaffold-extension feature only if this phase introduces a new component.

## 5. Hand off

Report: the work item id and URL, and which of the phase's features are still stubs
(`query --preset stub-features --area "<project>\<phase>"`). Offer to continue with the next one.
Tell the user they can run `/implement <id>` now, or detail the rest and then `/autopilot` to drain
the whole backlog. Do NOT start implementing.
