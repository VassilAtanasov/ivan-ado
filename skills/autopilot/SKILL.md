---
name: autopilot
description: Ivan works through the active phase's ready feature backlog autonomously, one /implement pipeline per work item, until the backlog is empty or a circuit breaker requires human input.
---

# /autopilot — drain the backlog

You are Ivan in **build mode**, fully autonomous. You drain **one phase's** backlog: the active
phase in the `## Ivan project config` registry, or the one named as the argument (set it active
before starting). Loop:

1. List the buildable Features on that phase's area path — **one call** (see the Azure DevOps
   access rules in CLAUDE.md):

   ```
   python <plugin>/scripts/ado_cli.py query --preset open-features --area "<Project>\<phase>" --json
   ```

   The preset requires the `ready` tag, so features `/kickoff` hasn't settled yet stay out of the
   queue by construction.

   If empty, this phase is done: post a summary (features shipped this run, PRs merged, anything
   skipped), send a push notification ("<phase>: complete — N features shipped"), then run the
   `retrospective` skill to record lessons and file follow-ups before ending the run. Then check
   `--preset stub-features --area "<Project>\<phase>"`: if features remain undetailed, name them and
   tell the user to run `/kickoff` on them. If the phase is genuinely exhausted and the board has a
   later Epic, name it and tell the user to run `/discover <next>` — do not start it yourself.
2. Run the full `/implement` pipeline (the `implement` skill of this plugin) on the
   lowest-numbered work item from step 1, **passing the id explicitly** so it does not re-run the
   query you just ran.
3. Outcomes:
   - **Merged** → next iteration.
   - **Skipped for clarification** (ambiguity rule) → next iteration; collect it for the final summary.
   - **Circuit breaker tripped** (3 failed cycles) → STOP the whole run. The notification and
     work item diagnosis were already sent by /implement; add a run summary of what shipped before
     the stop, then run the `retrospective` skill to capture what shipped and why the run stopped.

Rules:
- One work item at a time, always to completion or explicit skip — never interleave branches. Each
  `/implement` call isolates itself in its own git worktree and cleans up on exit (see
  **Concurrency** in CLAUDE.md), so this loop can safely run alongside a separate manual
  `/implement` session working a different item.
- If every remaining item is in the skipped-for-clarification set, stop and summarize instead of
  spinning, then run the `retrospective` skill.
- Between items, verify `main` is green:
  `az pipelines runs list --org <org> --project <project> --branch main --top 1 -o json` — check
  `status` is `completed` and `result` is `succeeded`. If main is somehow red, fixing main IS the
  next task before any new feature.
