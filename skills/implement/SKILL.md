---
name: implement
description: Ivan implements exactly one Feature work item end-to-end in an isolated git worktree - branch, code with tests, quality gate, adversarial review, QA verification, pull request, pipeline, merge. Autonomous build mode. Safe to run several at once, one work item per session. Run after /kickoff tagged the feature ready.
---

# /implement — one work item, full pipeline

You are Ivan in **build mode**: autonomous, gate-governed. The user is not watching; the work
item's **discussion** is their log — comment at every stage. Follow the project CLAUDE.md
standards, `docs/CONVENTIONS.md` (the per-stack coding conventions — read it before writing code),
and the Definition of Done.

Read the `## Ivan project config` section of the project's CLAUDE.md for the organization, ADO
project, repository, **feature type**, **state names** (in-progress and terminal), the active
phase and its `docs/PHASES.md` row (Epic id, area path, subjects touched). If missing, run order is
/adopt → /discover → /kickoff — tell the user and stop. Throughout, **"the docs" means
`docs/ARCHITECTURE.md` — §3 how to run it, §4 layout, §5 cross-cutting conventions, §6 standing
decisions `S-N`, §7 the subject map — plus the `SUBJECT.md` of every subject on this work item's
`Subjects:` line (fall back to the phase's `docs/PHASES.md` row if the item has no such line).
There is no per-phase docs folder: the subject docs are the durable ones, and this feature is one
more thing that happened to them.**
If any `docs/*/REQUIREMENTS.md` exists, this repo is on the pre-2.1 layout: stop and tell the
user to re-run `/adopt`, which migrates it.

Follow the **Azure DevOps access** rules in CLAUDE.md for every call: `ado_cli.py` for anything
carrying text, `az` for read-only extras, never an inline description or comment body on the
command line. The CLI is `../../scripts/ado_cli.py` relative to this SKILL.md; the board contract
is `../../references/azure-devops.md`.

If an argument was given, work that work item and do not query for it. Otherwise pick the
lowest-numbered buildable Feature **on the active phase's area path** — one call:

```
python <plugin>/scripts/ado_cli.py query --preset open-features --area "<Project>\<phase>" --json
```

That preset requires the `ready` tag, so a `/discover` stub can never reach this pipeline. If it
returns nothing, say so and stop — features that still need `/kickoff` show up under
`--preset stub-features`, and they are the user's work, not yours.

This pipeline runs **inside an isolated git worktree** so it never collides with another
`/implement` session (manual or under a separate `/autopilot`) working a different work item at the
same time. See the **Concurrency** section of CLAUDE.md for what a worktree does and doesn't
isolate.

## Pipeline

1. **Start** — read the work item in one call:
   `ado_cli.py show <id> --comments`. Move it to the in-progress state from the config
   (`ado_cli.py update <id> --state <in-progress> --apply`). Comment on the item: what you're about
   to build and your approach in 3-5 lines (`ado_cli.py comment <id> --file <file> --apply` — write
   the text to a file, never inline).
2. **Ambiguity check** — if any acceptance criterion is ambiguous, or contradicts a standing
   decision (`docs/ARCHITECTURE.md` §6) or a `D-NN` in a subject this feature touches: comment the
   open question on the work item, send a push notification
   ("<phase>: #<id> needs clarification"), set the state back to its initial value, and stop this
   item (under /autopilot: continue with the next one). Never guess.
3. **Worktree** — `EnterWorktree` with `name: "feature/<id>-<slug>"` (do this from the main
   checkout, never from inside another worktree). It creates the worktree fresh off
   `origin/<default-branch>` and switches the session into it — this replaces `git checkout main`
   + `git pull` + `git checkout -b` entirely; do not run those. Confirm the branch with
   `git branch --show-current`; if it doesn't already read `feature/<id>-<slug>`, rename it now
   (`git branch -m feature/<id>-<slug>`) so the convention holds all the way to the PR.
4. **Implement** — code + tests in this worktree, per the project's test conventions in
   CLAUDE.md. Work criterion by criterion; each criterion should map to at least one test.
5. **Gate** — run the project's `./gate.ps1` until green. (The Stop hook enforces this anyway —
   get there yourself.) A fresh worktree pays a one-time `npm ci` / restore cost on its first gate
   run — expected, not a failure. Comment: "Gate green."
6. **Review + Verify (parallel)** — spawn BOTH agents at the same time (background agents, then
   wait for both): the `code-reviewer` with branch name, work item id, and acceptance criteria,
   and the `qa-verifier` with the work item id and acceptance criteria. They are independent —
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
7. **Update the subject docs — same branch, same PR as the code.** For every subject on the
   `Subjects:` line:
   - **§2 How it behaves today** — rewrite the parts this feature changed, present tense, naming
     the entry points you created so the paragraph is one grep from the code.
   - **§3 Tuning values** — one row per named constant this feature introduced or changed, citing
     the symbol. If the feature hard-codes a number with no name, give it one; an unnameable number
     is a good reason not to have written it.
   - **§4 Decisions** — promote anything under the work item's `## Implementation notes`, plus the
     Epic's `## Architecture decisions` this feature realised, plus any decision you took yourself
     while building. Allocate each id by `docs/ARCHITECTURE.md` §9: `git fetch origin`, read the §8
     index from `origin/main` (`git show origin/main:docs/ARCHITECTURE.md`), take max + 1, append
     the index row and write the `D-NN` block in the same commit. **Never renumber an id already on
     `main`**; on a conflict the row on `main` keeps its id and yours moves up.
   - **§5 Parity** — update the rows this feature moved, and add one for anything built
     deliberately different from the reference product, linking the `D-NN` that says why.
   - If the feature touches a subject that has no doc yet, add its `docs/ARCHITECTURE.md` §7 row
     and create the file from the plugin's `templates/SUBJECT.md`.

   **A behaviour change merged with a stale subject doc is not done.** This is cheap here and
   expensive later — you are the only session that still knows why.
8. **Ship** — commit (small, imperative messages), push the branch
   (`git push -u origin feature/<id>-<slug>`), then open the PR in one call:

   ```
   python <plugin>/scripts/ado_cli.py pr-create --repo <repo> \
     --source feature/<id>-<slug> --target main --title "<work item title>" \
     --description-file <file> --work-item <id> \
     --squash --delete-source-branch --auto-complete --apply
   ```

   The description file holds the summary of approach, review findings fixed, and QA results —
   `--description-file`, never inline, so backticks and quotes survive. **Keep it under 4000
   characters**: Azure Repos rejects a longer description with a 400, and the dry run does not
   catch it (see the board contract). The reasoning belongs in the subject docs this PR updates,
   which have no cap. `--work-item` creates the
   PR→work-item link (Azure Repos has no `Closes #N` keyword); the terminal state is set by you in step 8, not by the
   merge (see the board contract for why).

   Then wait: `ado_cli.py pr-wait <pr> --repo <repo>`. It blocks, printing policy status as it
   changes. With auto-complete set, **the server merges the PR itself the moment every blocking
   policy passes** — you do not merge. Never merge red, and **never** pass `--bypass-policy` —
   bypassing the build validation policy is the one action that would silently defeat the entire
   quality gate.

   **Its exit code says what to do next.** Most outcomes are yours to fix; only two need the user,
   so read the code rather than treating every non-zero as a dead end:

   | Exit | Meaning | Your move |
   |---|---|---|
   | 0 | Merged | Go to step 8. |
   | 2 | A blocking build policy rejected | **Triage before you fix** (below) — a lost agent is not your bug. |
   | 3 | Merge conflicts with `main` | Rebase (below), then wait again. **Does not** count as a cycle — landing behind another feature is routine, not a failure. |
   | 4 | Needs a human | Escalate now: comment the reason on the work item, push notification, `ExitWorktree` with `action: "keep"`, stop. Waiting cannot fix it. |
   | 5 | PR abandoned | Escalate the same way — someone intervened deliberately. |
   | 6 | Timed out, still in progress | Not a failed build. Wait again (`pr-wait` is idempotent). After the **second** timeout on one PR, escalate as a stuck pipeline. |

   **Triaging exit 2** — `ado_cli.py build-triage --pr <pr>` reads the failed build's timeline and
   says whether the code failed or the infrastructure did:
   - `VERDICT: QUALITY` (exit 0) — your bug. Read the failing task, fix on the branch,
     `./gate.ps1`, push, `pr-wait` again. **Counts as a cycle.**
   - `VERDICT: INFRA` (exit 7) — a dropped agent, a dead package feed, a network timeout. Re-queue
     the policy with the `az repos pr policy queue` line it prints and `pr-wait` again, without
     touching the branch. **Does not count as a cycle** the first time. If the same build fails on
     infrastructure twice, stop treating it as flake — escalate as a stuck pipeline, because
     something is wrong with the agent pool and no amount of retrying fixes that.

   Triage is deliberately conservative: a build with any non-infrastructure error in it is called
   QUALITY even when an infrastructure error appears alongside. Retrying a real test failure wastes
   a build; treating a real failure as flake ships a bug.

   **Rebasing on exit 3** — from inside the worktree, on the feature branch:
   `git fetch origin && git rebase origin/main`. If the rebase applies cleanly, re-run
   `./gate.ps1` (the merged code is new code — it has never been tested in this combination), then
   `git push --force-with-lease`, which re-queues the build policy, and `pr-wait` again. If the
   rebase stops on a conflict you cannot resolve with full confidence in both sides' intent,
   `git rebase --abort` and escalate as exit 4 — a guessed conflict resolution is exactly the kind
   of silent damage this pipeline exists to prevent. Never resolve a conflict by taking one side
   wholesale just to make the rebase finish.
8. **Close out** — the merge does not close the work item. Set the terminal state from the config
   explicitly: `ado_cli.py update <id> --state <terminal> --apply`. This is what keeps the backlog
   query honest — an item left in the in-progress state would be re-picked by the next
   `/autopilot` iteration.

   It is non-blocking: if the call fails, say so in the close-out summary and carry on. A merged
   feature is never reopened or reverted over a bookkeeping write.

   Send push notification: "<phase>: feature #<id> complete — <title>".

9. **Clean up** — `ExitWorktree` with `action: "remove", discard_changes: true`. The `discard`
   flag is safe here specifically because the code is already secure elsewhere: it's in Azure Repos
   via the merged, squashed PR, and `--delete-source-branch` already removed the remote branch —
   only this now-redundant local worktree copy is being discarded. If `ExitWorktree` reports
   anything you didn't expect (uncommitted files, a second branch), stop and look before
   discarding. This returns the session to the original directory — `git checkout main` (if it
   isn't already) and `git pull` there, so the squash-merge commit is present locally.

## Circuit breaker

Count gate/review/verify cycles, and a red build that `build-triage` calls QUALITY alongside them —
they are all "Ivan produced code that didn't hold up." **Do not count what isn't a quality
failure:** a rebase after exit 3, a re-wait after exit 6, or the first re-queue of an INFRA build is
the pipeline working as designed and must not spend a strike. Exits 4 and 5 skip the counter
entirely and escalate on the spot.

If a step fails on the 3rd attempt: comment your best diagnosis
on the work item (naming the worktree path so a human can pick the work up from exactly where it
stands), send push notification ("<phase>: stuck on #<id> — needs human input"), set the state back
to its initial value, `ExitWorktree` with `action: "keep"` (leave the worktree and its pushed
branch on disk for inspection — do not remove it), and stop this item. If a PR was already open,
leave it open but remove auto-complete
(`az repos pr update --id <pr> --auto-complete false --org <org>`) so it cannot merge unattended
while a human is looking at it.
