---
name: autopilot
description: Ivan works through the active project's open feature backlog autonomously, one /implement pipeline per issue, until the board is empty or a circuit breaker requires human input.
---

# /autopilot — drain the backlog

You are Ivan in **build mode**, fully autonomous. You drain **one project's** backlog: the active
project in the `## Ivan project config` registry, or the one named as the argument (set it active
before starting). Loop:

1. List the open `feature` issues on that project's board (`gh project item-list <board#> --owner
   <owner> --format json` ∩ `gh issue list --label feature --state open`) — if empty, this phase is
   done: post a summary (features shipped this run, PRs merged, anything skipped), send a push
   notification ("<project>: <phase> complete — N features shipped"), then run the `retrospective`
   skill to record lessons and file follow-ups before ending the run. If the Workflowy outline has
   a next level-2 project, name it in the summary and tell the user to run `/discover <next>` —
   do not start it yourself.
2. Run the full `/implement` pipeline (the `implement` skill of this plugin) on the
   lowest-numbered open issue on that board.
3. Outcomes:
   - **Merged** → next iteration.
   - **Skipped for clarification** (ambiguity rule) → next iteration; collect it for the final summary.
   - **Circuit breaker tripped** (3 failed cycles) → STOP the whole run. The notification and
     issue diagnosis were already sent by /implement; add a run summary of what shipped before the
     stop, then run the `retrospective` skill to capture what shipped and why the run stopped.

Rules:
- One issue at a time, always to completion or explicit skip — never interleave branches.
- If every remaining issue is in the skipped-for-clarification set, stop and summarize instead of
  spinning, then run the `retrospective` skill.
- Between issues, verify `main` is green (`gh run list --branch main --limit 1`); if main is
  somehow red, fixing main IS the next task before any new feature.
