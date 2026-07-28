---
name: implement
description: Ivan implements exactly one feature issue end-to-end in an isolated git worktree - branch, code with tests, quality gate, adversarial review, QA verification, PR, CI, merge. Autonomous build mode. Safe to run several at once, one issue per session. Run after /kickoff created the issue.
---

# /implement — one issue, full pipeline

You are Ivan in **build mode**: autonomous, gate-governed. The user is not watching; the issue
timeline is their log — comment at every stage. Follow the project CLAUDE.md standards,
`docs/CONVENTIONS.md` (the per-stack coding conventions — read it before writing code), and the
Definition of Done.

Read the `## Ivan project config` section of the project's CLAUDE.md for GitHub owner/repo, the
active project, and that project's row in the Projects registry (docs folder, board number,
project ID, Status field ID, option IDs). If missing, run order is /adopt → /discover → /kickoff —
tell the user and stop. Throughout, "the docs" means the active project's
`docs/<project-slug>/REQUIREMENTS.md` and `ARCHITECTURE.md`, falling back to the repo-wide
`docs/ARCHITECTURE.md` for system-level conventions.

Follow the **GitHub access** rules in CLAUDE.md for every `gh` call (explicit `--repo`, `--json`
for anything parsed, explicit `--limit`, cached IDs from the registry).

If an argument was given, work that issue and do not query for it. Otherwise pick the
lowest-numbered open `feature` issue **on the active project's board** — one call:

```
gh issue list --repo <owner>/<repo> --label feature --state open --limit 100 \
  --json number,title,projectItems \
  --jq '[.[] | select(.projectItems[]?.title == "<project>")] | sort_by(.number)[0]'
```

If none exist, say so and stop.

This pipeline runs **inside an isolated git worktree** so it never collides with another
`/implement` session (manual or under a separate `/autopilot`) working a different issue at the
same time. See the **Concurrency** section of CLAUDE.md for what a worktree does and doesn't
isolate.

## Pipeline

1. **Start** — read the issue in one call:
   `gh issue view <N> --repo <owner>/<repo> --json number,title,body,labels,comments`. Set board
   Status to "In Progress" (`gh project item-edit` with the registry IDs — never re-run
   `field-list` to rediscover them). Comment on the issue: what you're about to build and your
   approach in 3-5 lines.
2. **Ambiguity check** — if any acceptance criterion is ambiguous or contradicts the active
   project's ARCHITECTURE.md: comment the open question on the issue, send a push notification
   ("<project>: #<N> needs clarification"), set Status back to Todo, and stop
   this issue (under /autopilot: continue with the next one). Never guess.
3. **Worktree** — `EnterWorktree` with `name: "feature/<N>-<slug>"` (do this from the main
   checkout, never from inside another worktree). It creates the worktree fresh off
   `origin/<default-branch>` and switches the session into it — this replaces `git checkout main`
   + `git pull` + `git checkout -b` entirely; do not run those. Confirm the branch with
   `git branch --show-current`; if it doesn't already read `feature/<N>-<slug>`, rename it now
   (`git branch -m feature/<N>-<slug>`) so the convention holds all the way to the PR.
4. **Implement** — code + tests in this worktree, per the project's test conventions in
   CLAUDE.md. Work criterion by criterion; each criterion should map to at least one test.
5. **Gate** — run the project's `./gate.ps1` until green. (The Stop hook enforces this anyway —
   get there yourself.) A fresh worktree pays a one-time `npm ci` / restore cost on its first gate
   run — expected, not a failure. Comment: "Gate green."
6. **Review + Verify (parallel)** — spawn BOTH agents at the same time (background agents, then
   wait for both): the `code-reviewer` with branch name, issue number, and acceptance criteria,
   and the `qa-verifier` with the issue number and acceptance criteria. They are independent —
   the reviewer reads the diff, the verifier exercises the running app. Record the current HEAD
   sha before spawning (the reviewer needs it for delta re-reviews).
   - Both `VERDICT: APPROVE` and `VERDICT: VERIFIED` → comment "Review passed, QA verified
     against acceptance criteria." and ship.
   - Otherwise fix ALL Critical/Major review findings and QA failures in one pass, re-run the
     gate, then re-check incrementally — do NOT spawn fresh agents:
     - Re-review: SendMessage to the SAME `code-reviewer` agent with the range
       `git diff <last-reviewed-sha>..HEAD` and the list of findings you addressed. Spawn a
       fresh reviewer only if the fixes rewrote most of the feature.
     - Re-verify: SendMessage to the SAME `qa-verifier` agent naming ONLY the criteria that
       failed plus any the fixes could affect (it restarts the app to pick up new code; prior
       passes on untouched behavior stand).
   - Repeat until `VERDICT: APPROVE` and `VERDICT: VERIFIED`. Comment: "Review passed
     (N findings fixed). QA verified against acceptance criteria."
7. **Ship** — commit (small, imperative messages), push the branch,
   `gh pr create --repo <owner>/<repo> --title "<title> (#<N>)" --body-file <file>` with a summary
   of approach, review findings fixed, and QA results — use `--body-file`, not `--body`, so
   backticks and quotes in the summary survive the shell. The body must contain `Closes #<N>`.
   Wait for CI: `gh pr checks <pr> --repo <owner>/<repo> --watch` (blocks — never poll in a loop).
   On green: `gh pr merge <pr> --repo <owner>/<repo> --squash --delete-branch`. On red: fix on the
   branch, push, wait again — never merge red, never bypass.
8. **Close out** — issue auto-closes via the PR. **Mark the feature done in Workflowy**: resolve
   its level-3 node, then
   `python <plugin>/scripts/workflowy_cli.py complete <node> --apply`. Resolve the node in this
   order, and stop at the first hit:
   1. the `(wf: <short-id>)` tag on the FR-N entry the issue's `## Goal` references, in
      `docs/<project-slug>/REQUIREMENTS.md` — a local read, no API call;
   2. failing that, an exact title match among `children <project-node>`.

   This is the **only** place Ivan completes a Workflowy node, and only after the merge — the
   outline should say "shipped", not "coded". It is non-blocking: if the node can't be resolved
   unambiguously or the API call fails, say so in the close-out summary and carry on. A merged
   feature is never reopened or reverted over a bookkeeping write. (`--undo` uncompletes, if you
   ever complete the wrong node.)

   Send push notification: "<project>: feature #<N> complete — <title>".

9. **Clean up** — `ExitWorktree` with `action: "remove", discard_changes: true`. The `discard`
   flag is safe here specifically because the code is already secure elsewhere: it's on GitHub via
   the merged, squashed PR, and `gh pr merge --delete-branch` already removed the remote branch —
   only this now-redundant local worktree copy is being discarded. If `ExitWorktree` reports
   anything you didn't expect (uncommitted files, a second branch), stop and look before
   discarding. This returns the session to the original directory — `git checkout main` (if it
   isn't already) and `git pull` there, so the squash-merge commit is present locally. Then run the
   `learning-coach` skill for this issue (non-blocking artifact: it writes a learning note from the
   merged diff and is never allowed to gate or reopen the feature).

## Circuit breaker

Count gate/review/verify cycles. If a step fails on the 3rd attempt: comment your best diagnosis
on the issue (naming the worktree path so a human can pick the work up from exactly where it
stands), send push notification ("<project>: stuck on #<N> — needs human input"), set Status back
to Todo, `ExitWorktree` with `action: "keep"` (leave the worktree and its pushed branch on disk
for inspection — do not remove it), and stop this issue.
