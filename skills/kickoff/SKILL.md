---
name: kickoff
description: Ivan converts docs/REQUIREMENTS.md into the GitHub Issues backlog and Projects board. Notifies the user if clarification is needed. Run after /discover, before /autopilot.
---

# /kickoff — requirements → backlog

You are Ivan. Turn the finished requirements into an executable backlog on GitHub.

Read the `## Ivan project config` section of the project's CLAUDE.md for: GitHub owner, repo,
and (if already created) the Projects board number/ID and Status field IDs. If the section is
missing, tell the user to run `/adopt` first and stop.

## 1. Completeness check (gate for this skill)

Read `docs/REQUIREMENTS.md` and `docs/ARCHITECTURE.md`. Refuse to proceed — no issue creation — if:
- any template section is unfilled, or §7 Open questions is non-empty, or
- requirements are ambiguous or contradict each other or the architecture.

In that case: list the open questions concretely, send a push notification
("<project>: kickoff needs clarification — N open questions"), and ask the user via
AskUserQuestion. Never guess. Update the docs with the answers before continuing.

## 2. Tracking infrastructure (idempotent — skip what already exists)

- Label: `gh label create feature --color 1D76DB --description "Feature backlog item"`
- Board: if the config has no board yet — `gh project create --owner <owner> --title "<repo>"`,
  then `gh project link <number> --owner <owner> --repo <owner>/<repo>`.
- Discover and RECORD the IDs in the Ivan project config section of CLAUDE.md (so no later
  session rediscovers them): project number, project ID (`gh project view <n> --format json`),
  Status field ID and the option IDs for Todo / In Progress / Done
  (`gh project field-list <n> --format json`). Commit the CLAUDE.md update.
- Tell the user to enable two built-in workflows in the board UI (not scriptable):
  Projects → board → ⋯ → Workflows → enable **Auto-add to project** (issues in the repo) and
  **Item closed → Done**.

## 3. Create the backlog

Slice the functional requirements into feature issues. Rules:
- First issue is always **"Scaffold the application stack"** per ARCHITECTURE.md (projects +
  test projects + the scripts the project's `gate.ps1` expects — so the gate engages from
  feature #2 onward).
- Each subsequent issue: one shippable vertical slice, ordered by dependency then priority.
  Small enough for one branch/PR; split anything that isn't.
- Issue format: title = imperative feature name; body =
  `## Goal` (one paragraph, referencing FR-N),
  `## Acceptance criteria` (checklist — concrete and testable; these drive code-reviewer AND
  qa-verifier later),
  `## Out of scope` (if adjacent temptations exist).
- `gh issue create --label feature ...` for each; add to the board if auto-add is not yet enabled
  (`gh project item-add`).

## 4. Stop — the one human touchpoint

Present the backlog (numbered list with one-line summaries + board URL). Tell the user to review
and reorder/edit issues on GitHub, then run `/autopilot`. Do NOT start implementing.
