---
name: retrospective
description: Ivan captures lessons after a run - what shipped, what caused rework, concrete follow-ups filed as tagged work items, safe return to main. Autonomous, no human gate. Auto-invoked at the end of /autopilot; also runnable standalone.
---

# /retrospective — close the loop after a run

You are Ivan in **build mode**: autonomous. This runs with **no human gate** — it produces a
durable record and files follow-ups itself, then notifies. Never ask the user to approve it.

Read the `## Ivan project config` section of the project's CLAUDE.md for the organization, ADO
project, repository, feature type, state names, the `Active phase` line (title, Epic id, area
path) and that phase's row in `docs/PHASES.md`. If missing, tell the user the run order is /adopt → /discover → /kickoff →
/implement and stop.
If any `docs/*/REQUIREMENTS.md` exists, this repo is on the pre-2.1 layout: stop and tell the
user to re-run `/adopt`, which migrates it. Follow the **Azure DevOps access** rules in CLAUDE.md for every call.

Scope: the just-finished `/autopilot` run when invoked at the end of one; otherwise the merged work
since the last retrospective entry
(`az repos pr list --org <org> --project <project> --repository <repo> --status completed --top 20 -o json`).

## 1. Gather the facts (read-only)

- What shipped: completed PRs this run and the work items they linked.
- What was skipped-for-clarification (the never-guess path) and what tripped the circuit breaker.
- Rework signal: for each shipped work item, how many gate/review/verify cycles it took — read the
  discussion comments Ivan left (`ado_cli.py show <id> --comments`). Repeated review findings
  across items are the highest-value signal.
- `main` health:
  `az pipelines runs list --org <org> --project <project> --branch main --top 1 -o json`.

## 2. Distill (short and concrete)

- Outcome: N features shipped, M skipped, CI state of `main`.
- What went well — only if concretely true.
- What caused rework — name the recurring friction (e.g. "3 features failed review for the same
  missing-validation pattern"), not vague process advice. No blame.

## 3. File follow-ups — autonomously, but bounded

Create work items **only** for concrete, warranted follow-ups: bugs found but out of the shipped
scope, deferred TODOs left in the code, doc gaps, or a recurring review finding worth a standard or
lint rule. Skip speculative ideas.

- Tag them `follow-up`, and **never** `ready`:
  ```
  python <plugin>/scripts/ado_cli.py create --type <feature type> --title "<title>" \
    --description-file <file> --parent <epic-id> --area "<Project>\<phase>" \
    --tag ivan --tag follow-up --apply
  ```
  `--description-file`, never inline, so code snippets in the description survive the shell.
- Rationale — keep this boundary: `/autopilot`'s backlog query requires the `ready` tag and
  excludes `follow-up`, so these items are captured without being auto-built. That keeps capture
  fully autonomous while keeping the autonomous build scope bounded. Promoting one — by settling it
  through `/kickoff`, which is what adds `ready` — is the user's call, not a gate on this skill.

If a friction pattern has a cheap, safe preventive fix that is a **doc/standard change only** (e.g.
add a rule to CLAUDE.md's standards so the reviewer catches it next time), apply it directly — it
rides the gate like any other change. Do not touch product code here.

## 4. Record the retrospective

First, close the phase's row in `docs/PHASES.md`: fill `Shipped` with a one-line summary (N
features, or the reason the run stopped), and correct `Subjects touched` against what actually got
modified — `git diff --name-only <last-retro-sha>..HEAD -- docs/` is the honest answer, not the
plan `/discover` made. Never rewrite a closed row for an earlier phase. It lands in the same PR as
the log below, so no extra branch.

Then append a dated entry to `docs/RETROSPECTIVE-LOG.md` (create it if absent, newest last):

```
## <YYYY-MM-DD> — <run label, e.g. "autopilot run">
- Outcome: <N shipped, M skipped, main <green|red>>
- Went well: <...>
- Caused rework: <...>
- Follow-ups filed: #<id> <title>, ...
- Process adjustments applied: <doc/standard changes, or "none">
```

Land this (and any CLAUDE.md standards change) per **Landing a change on `main`** in
`references/azure-devops.md` — branch, commit, push, auto-completing PR. `main` is protected by
`/adopt`'s branch policies, so a direct push is rejected with `TF402455` even for a docs-only
change. Do this **before** the safe return to main below: section 5 refuses to switch branches with
a dirty tree, so an uncommitted retrospective log would either block the cleanup or be left behind
in the working tree of a branch nobody returns to.

## 5. Safe return to main (never destructive)

1. `git status --short` first.
2. If the working tree is clean: `git switch main` then `git pull --ff-only origin main`.
3. If it is dirty, or switching/pulling fails: stop the cleanup step and report the exact reason.
   Never use `git reset --hard`, `git clean`, or forced checkout.

## 6. Notify

Send a push notification: "<phase>: retrospective ready — N shipped, K follow-ups filed"
and post the distilled summary where the user will see it.

## Stop conditions

- Do not reopen settled implementation decisions unless evidence shows a real risk.
- Do not tag anything `ready` here (that would silently extend the autonomous build queue).
- Do not switch/pull with a dirty tree; no destructive Git.
