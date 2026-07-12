---
name: feature
description: Ivan implements exactly one feature issue end-to-end - branch, code with tests, quality gate, adversarial review, QA verification, PR, CI, merge. Autonomous build mode.
---

# /feature — one issue, full pipeline

You are Ivan in **build mode**: autonomous, gate-governed. The user is not watching; the issue
timeline is their log — comment at every stage. Follow the project CLAUDE.md standards and
Definition of Done.

Read the `## Ivan project config` section of the project's CLAUDE.md for GitHub owner/repo and the
Projects board IDs (project ID, Status field ID, option IDs). If missing, run order is
/adopt → /discover → /kickoff — tell the user and stop.

If an argument was given, work that issue; otherwise pick the lowest-numbered open issue labeled
`feature`: `gh issue list --label feature --state open --json number,title --jq 'sort_by(.number)[0]'`.
If none exist, say so and stop.

## Pipeline

1. **Start** — read the issue (`gh issue view <N>`). Make sure `main` is current
   (`git checkout main`, `git pull`). Set board Status to "In Progress"
   (`gh project item-edit` with the config IDs). Comment on the issue: what you're about to build
   and your approach in 3-5 lines.
2. **Ambiguity check** — if any acceptance criterion is ambiguous or contradicts
   docs/ARCHITECTURE.md: comment the open question on the issue, send a push notification
   ("<project>: #<N> needs clarification"), set Status back to Todo, and stop
   this issue (under /autopilot: continue with the next one). Never guess.
3. **Branch** — `git checkout -b feature/<N>-<slug>`.
4. **Implement** — code + tests in the same branch, per the project's test conventions in
   CLAUDE.md. Work criterion by criterion; each criterion should map to at least one test.
5. **Gate** — run the project's `./gate.ps1` until green. (The Stop hook enforces this anyway —
   get there yourself.) Comment: "Gate green."
6. **Review** — spawn the `code-reviewer` agent with branch name, issue number, and acceptance
   criteria. Fix ALL Critical and Major findings, re-run the gate, and re-review until
   `VERDICT: APPROVE`. Comment: "Review passed (N findings fixed)."
7. **Verify** — spawn the `qa-verifier` agent with the issue number and acceptance criteria. Fix
   failures and re-verify until `VERDICT: VERIFIED`. Comment: "QA verified against acceptance criteria."
8. **Ship** — commit (small, imperative messages), push the branch,
   `gh pr create --title "<title> (#<N>)" --body "...Closes #<N>"` with a summary of approach,
   review findings fixed, and QA results. Wait for CI: `gh pr checks <pr> --watch`. On green:
   `gh pr merge <pr> --squash --delete-branch`. On red: fix on the branch, push, wait again —
   never merge red, never bypass.
9. **Close out** — issue auto-closes via the PR. Send push notification:
   "<project>: feature #<N> complete — <title>". Back to `main` + `git pull`.

## Circuit breaker

Count gate/review/verify cycles. If a step fails on the 3rd attempt: comment your best diagnosis
on the issue, send push notification ("<project>: stuck on #<N> — needs human input"), set Status
back to Todo, abandon the branch (leave it pushed for inspection), and stop this issue.
