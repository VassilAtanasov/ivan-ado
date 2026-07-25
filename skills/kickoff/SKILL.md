---
name: kickoff
description: Ivan details exactly one Workflowy feature (level 3) with you - goal, acceptance criteria, out of scope - writes it into that item's note, and creates the GitHub issue on the project's board ready for /implement. Run after /discover, once per feature, before /implement or /autopilot.
---

# /kickoff — one feature → its description + its issue

You are Ivan in **discovery mode**. `/discover <project>` decided *which* features this phase
contains; this skill turns **one of them** into buildable work: it settles what the feature means,
writes that into the Workflowy note, and creates the GitHub issue from it. **One feature per run.**

The note is the deliverable and the issue body is a copy of it — not a scratchpad. Its acceptance
criteria drive the `code-reviewer` and `qa-verifier` agents during `/implement`. Write it as the
contract for a build-mode session that will not be able to ask you anything.

The outline contract and CLI are in this plugin's `references/workflowy.md`; the CLI is
`../../scripts/workflowy_cli.py` relative to this SKILL.md.

Argument: the feature — a name, node id, short id, or Workflowy URL. With no argument, list the
active project's level-3 items marking which already have issues, and ask which one. Offer to walk
the remaining ones in outline order, a full run each — never batch the interviews.

## 0. Orient

1. Read the `## Ivan project config` section of CLAUDE.md for GitHub owner/repo, the active
   project, and its registry row (Workflowy short id, docs folder, board number/ID, Status field
   IDs). If there is no active project, tell the user to run `/discover <project>` first and stop.
   `WORKFLOWY_API_KEY` must resolve — if it doesn't, stop and ask.
2. Resolve the feature under the active project's node (`children <project-node>`, exact name
   first, then unambiguous partial match). If it isn't there, say so and offer to add it via
   `/discover` rather than inventing a feature the project map doesn't have.
3. `outline <feature-node> --max-depth 3` → the stub note plus any level-4+ detail, edge cases, or
   later/maybe items the user jotted underneath. Read them: this is the user's own thinking and it
   outranks yours.
4. Read the project's `docs/<project-slug>/REQUIREMENTS.md` (its FR-N entry, the non-goals in §6)
   and `ARCHITECTURE.md` plus the repo-wide `docs/ARCHITECTURE.md`. The feature must fit the
   architecture already decided; if it can't, that is a finding to raise, not to design around
   silently. If the project docs are missing or half-filled, send the user back to `/discover`.
5. If an open issue already exists for this feature (one call:
   `gh issue list --repo <owner>/<repo> --label feature --state open --limit 100 --json
   number,title`, matched on title), say so and ask whether to refine the note and update that
   issue, or stop. Never create a duplicate.

## 1. Interview

Open with your own reading of the feature — one paragraph, from the stub note and its context —
and ask the user (free text, not AskUserQuestion) to correct it. Then work the gaps. Use
AskUserQuestion for real decision points with 2-4 realistic options and honest trade-offs; use
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
write a heroic note.

## 2. Write the note

Compose the note in this exact shape — it becomes the issue body unchanged:

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
- Keep the item **name** unchanged unless the user agrees to a better one (≤ 15 words).
- Show the `update-node --note-file` dry run, then apply only after the user says go. Never
  delete, move, or complete a node, and leave the user's level-4+ children untouched.

Then update this feature's FR-N entry in `docs/<project-slug>/REQUIREMENTS.md` with the same
acceptance conditions (the docs are the product truth; the note is its Workflowy face — they must
not drift), add anything the interview surfaced to §5 or §6, and commit the docs.

## 3. Gate — never create an issue from an unsettled feature

Do not proceed to step 4 if any acceptance criterion is ambiguous, the feature contradicts the
architecture, or a question the user deferred is still open. Instead: write the open questions into
the note's `## Open questions` section AND `docs/<project-slug>/REQUIREMENTS.md` §7 — never only in
chat — send a push notification ("<project>: <feature> has N open questions"), and stop. An
unanswered question blocks the issue rather than becoming a guess in the build.

## 4. Tracking infrastructure (idempotent — skip what already exists)

Follow the **GitHub access** rules in CLAUDE.md for every `gh` call.

- Label: `gh label create feature --repo <owner>/<repo> --color 1D76DB --description "Feature
  backlog item" --force` — `--force` is required, plain `create` fails once the label exists.
- Board: one GitHub Project **per Workflowy project**, titled exactly as the level-2 item. Look it
  up in the registry first (and skip the rest if it's there); else
  `gh project list --owner <owner> --limit 100 --format json` by exact title; else
  `gh project create --owner <owner> --title "<project name>" --format json` +
  `gh project link <number> --owner <owner> --repo <owner>/<repo>`. If a board with that title
  already exists, use it as-is — never edit an existing board's title, description, readme, or
  repo link.
- On first creation, RECORD the IDs in the project's registry row in CLAUDE.md (so no later
  session rediscovers them): project number, project ID
  (`gh project view <n> --owner <owner> --format json`),
  Status field ID and the option IDs for Todo / In Progress / Done
  (`gh project field-list <n> --owner <owner> --format json`). Commit the CLAUDE.md update.
- On first creation, tell the user to enable two built-in workflows in the board UI (not
  scriptable): Projects → board → ⋯ → Workflows → enable **Auto-add to project** (issues in the
  repo) and **Item closed → Done**. With several boards on one repo, auto-add fires for every
  board — if that's noisy, skip it and rely on the explicit `gh project item-add` below.
- **Scaffold first**: if this is the repo's first project and its board has no issues yet, create
  **"Scaffold the application stack"** per ARCHITECTURE.md before this feature's issue (projects +
  test projects + the scripts `gate.ps1` expects — so the gate engages from the next feature
  onward). Later projects build on the existing scaffold; add a scaffold-extension issue only if
  this phase introduces a new component.

## 5. Create the issue

- Title = the Workflowy item name (imperative feature name).
- Body = **the note verbatim** — you just wrote it in issue-body shape. Do not rewrite, summarize,
  or add source metadata; traceability lives in the FR-N entry in REQUIREMENTS.md.
- `gh issue create --repo <owner>/<repo> --label feature --title "<name>" --body-file <file>` —
  write the note to a temp file and use `--body-file`, never `--body`, so backticks, quotes, and
  `#` in the description survive the shell intact. Then
  `gh project item-add <number> --owner <owner> --url <issue-url>` and set Status to Todo using
  the registry's field and option IDs.
- If refining an existing issue (step 0.5), `gh issue edit <N> --repo <owner>/<repo> --body-file
  <file>` instead — only while its status is still Todo. Once it is In Progress or Done, leave it
  alone and tell the user.

## 6. Hand off

Report: the issue number and URL, the board URL, and which of the project's features still have no
issue. Offer to continue with the next one. Tell the user they can run `/implement <issue>` now, or
detail the rest and then `/autopilot` to drain the whole board. Do NOT start implementing.
