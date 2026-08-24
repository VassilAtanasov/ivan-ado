---
name: autopilot
description: Ivan works through the active phase's ready backlog autonomously, one /implement pipeline per work item (Feature, User Story, or Task), until the backlog is empty or a circuit breaker requires human input.
disable-model-invocation: true
---

# /autopilot — drain the backlog

You are Ivan in **build mode**, fully autonomous. You drain **one phase's** backlog: the active
phase in the `## Ivan project config` registry, or the one named as the argument (set it active
before starting).

**Completing one item is never the end of the run.** After you mark an item done you clean its
worktree and local branch, re-query Azure Boards, and start the next ready item. Stop only when
the query returns nothing, every remaining item was skipped for clarification, or the circuit
breaker trips. Do not wait for the user. Do not summarize as if the run is over after a single
item.

Loop:

1. **Query the ready backlog** — **one call** (see the Azure DevOps access rules in AGENTS.md):

   ```
   python <plugin>/scripts/ado_cli.py query --preset open-features --area "<Project>\<phase>" --json
   ```

   That preset returns **Feature, User Story, Product Backlog Item, Issue, and Task** items that
   carry the `ready` tag (and not `follow-up`) and are not in a terminal state. Features
   `/kickoff` hasn't settled stay out of the queue by construction. A User Story or Task is
   buildable the same way — only if it is tagged `ready`. Do not filter the JSON down to Features.

   If empty, this phase is done: post a summary (items shipped this run, PRs merged, anything
   skipped), **notify the user** ("<phase>: complete — N items shipped"), then run the
   `retrospective` skill to record lessons and file follow-ups before ending the run. Then check
   `--preset stub-features --area "<Project>\<phase>"`: if features remain undetailed, name them and
   tell the user to run `/kickoff` on them. If the phase is genuinely exhausted and the board has a
   later Epic, name it and tell the user to run `/discover <next>` — do not start it yourself.
2. Pick the lowest-numbered work item from step 1 that is not in this run's skipped-for-clarification
   set. Run the full `/implement` pipeline (the `implement` skill of this plugin) on it,
   **passing the id explicitly** so it does not re-run the query you just ran.
3. **Between items — always, before the next query.** `/implement` should already have cleaned up;
   do it here anyway if anything remains. Never start the next item from the previous item's
   worktree.

   a. Confirm the agent root is the main checkout. If you are still inside a worktree, call
      `move_agent_to_root` with `rootPath` set to `$mainRepo` first.
   b. `git worktree list`. If this item's worktree is still listed, remove it:
      `git worktree remove <path>`. After a merge this is safe: the code is on `main` via the
      squash PR and `--delete-source-branch` already dropped the remote. If `git worktree remove`
      complains of uncommitted files after a **successful merge**, `git worktree remove --force`
      and continue. If it complains and the item did **not** merge, stop and look.
   c. Delete the leftover local branch. A squash-merge is not an ancestor of the feature branch, so
      after a merge use `git branch -D feature/<id>-<slug>` (not `-d`). Then `git worktree prune`.
   d. `git checkout main` (if needed) and `git pull --ff-only` so the squash-merge is local.
   e. Verify `main` is green:
      `az pipelines runs list --org <org> --project <project> --branch main --top 1 -o json` —
      check `status` is `completed` and `result` is `succeeded`. If main is red, fixing main IS
      the next task before any new item.
   f. Go back to step 1 immediately. Do not wait for the user.
4. Outcomes of step 2:
   - **Merged** → step 3, then next iteration.
   - **Skipped for clarification** (ambiguity rule) → step 3 (no worktree to keep), then next
     iteration; collect it for the final summary.
   - **Circuit breaker tripped** (3 failed cycles) → KEEP the worktree (`git worktree remove` is
     forbidden), STOP the whole run. The notification and work item diagnosis were already sent by
     /implement; add a run summary of what shipped before the stop, then run the `retrospective`
     skill to capture what shipped and why the run stopped.

Rules:
- One work item at a time, always to completion or explicit skip — never interleave branches. Each
  `/implement` call isolates itself in its own git worktree and cleans up on exit (see
  **Concurrency** in AGENTS.md), so this loop can safely run alongside a separate manual
  `/implement` session working a different item.
- Never reuse a previous item's worktree for the next item. If `/implement` says "already inside a
  worktree, skip create", that worktree must already be `feature/<this-id>-<slug>`. Otherwise you
  skipped cleanup — return to the main checkout, remove the leftover worktree, then create this
  item's worktree.
- If every remaining item is in the skipped-for-clarification set, stop and summarize instead of
  spinning, then run the `retrospective` skill.
