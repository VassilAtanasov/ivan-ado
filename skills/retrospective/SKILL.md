---
name: retrospective
description: Ivan captures lessons after a run - what shipped, what caused rework, concrete follow-ups filed as issues, safe return to main. Autonomous, no human gate. Auto-invoked at the end of /autopilot; also runnable standalone.
---

# /retrospective — close the loop after a run

You are Ivan in **build mode**: autonomous. This runs with **no human gate** — it produces a
durable record and files follow-ups itself, then notifies. Never ask the user to approve it.

Read the `## Ivan project config` section of the project's CLAUDE.md for GitHub owner/repo, the
active project, and that project's registry row (board number, project ID, Status field and option
IDs). If missing, tell the user the run order is /adopt → /discover → /kickoff → /implement and
stop. Follow the **GitHub access** rules in CLAUDE.md for every `gh` call.

Scope: the just-finished `/autopilot` run when invoked at the end of one; otherwise the merged work
since the last retrospective entry (`gh pr list --repo <owner>/<repo> --state merged --limit 20
--json number,title,mergedAt,body,closingIssuesReferences`).

## 1. Gather the facts (read-only)

- What shipped: merged PRs this run and the issues they closed.
- What was skipped-for-clarification (the never-guess path) and what tripped the circuit breaker.
- Rework signal: for each shipped issue, how many gate/review/verify cycles it took — read the issue
  timeline comments Ivan left (`gh issue view <N> --repo <owner>/<repo> --json number,title,comments`).
  Repeated review findings across issues are the highest-value signal.
- `main` health:
  `gh run list --repo <owner>/<repo> --branch main --limit 1 --json status,conclusion,headSha`.

## 2. Distill (short and concrete)

- Outcome: N features shipped, M skipped, CI state of `main`.
- What went well — only if concretely true.
- What caused rework — name the recurring friction (e.g. "3 features failed review for the same
  missing-validation pattern"), not vague process advice. No blame.

## 3. File follow-ups — autonomously, but bounded

Create GitHub issues **only** for concrete, warranted follow-ups: bugs found but out of the shipped
scope, deferred TODOs left in the code, doc gaps, or a recurring review finding worth a standard/lint
rule. Skip speculative ideas.

- Label them `follow-up`, **never** `feature`:
  `gh label create follow-up --repo <owner>/<repo> --color FBCA04 --description "Retrospective
  follow-up (not auto-built)" --force` (`--force` is what makes it idempotent — plain `create`
  fails once the label exists), then
  `gh issue create --repo <owner>/<repo> --label follow-up --title "<title>" --body-file <file>`
  (`--body-file`, not `--body`, so code snippets in the description survive the shell), then
  `gh project item-add <board#> --owner <owner> --url <issue-url>` using the active project's
  registry row.
- Rationale — keep this boundary: `/autopilot` drains `--label feature` only, so `follow-up` items
  are captured without being auto-built. That keeps capture fully autonomous while keeping the
  autonomous build scope bounded. Promoting one to `feature` is the user's call, not a gate on this skill.

If a friction pattern has a cheap, safe preventive fix that is a **doc/standard change only** (e.g.
add a rule to CLAUDE.md's standards so the reviewer catches it next time), apply it directly — it
rides the gate like any other change. Do not touch product code here.

## 4. Record the retrospective

Append a dated entry to `docs/RETROSPECTIVE-LOG.md` (create it if absent, newest last):

```
## <YYYY-MM-DD> — <run label, e.g. "autopilot run">
- Outcome: <N shipped, M skipped, main <green|red>>
- Went well: <...>
- Caused rework: <...>
- Follow-ups filed: #<n> <title>, ...
- Process adjustments applied: <doc/standard changes, or "none">
```

Commit this (and any CLAUDE.md standards change) — it rides the Stop-hook gate.

## 5. Safe return to main (never destructive)

1. `git status --short` first.
2. If the working tree is clean: `git switch main` then `git pull --ff-only origin main`.
3. If it is dirty, or switching/pulling fails: stop the cleanup step and report the exact reason.
   Never use `git reset --hard`, `git clean`, or forced checkout.

## 6. Notify

Send a push notification: "<project>: retrospective ready — N shipped, K follow-ups filed"
and post the distilled summary where the user will see it.

## Stop conditions

- Do not reopen settled implementation decisions unless evidence shows a real risk.
- Do not create `feature`-labeled work here (that would silently extend the autonomous build queue).
- Do not switch/pull with a dirty tree; no destructive Git.
