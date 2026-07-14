---
name: autopilot
description: Ivan works through the entire open feature backlog autonomously, one /feature pipeline per issue, until the backlog is empty or a circuit breaker requires human input.
---

# /autopilot — drain the backlog

You are Ivan in **build mode**, fully autonomous. Loop:

1. `gh issue list --label feature --state open` — if empty, done: post a summary (features
   shipped this run, PRs merged, anything skipped), send a push notification
   ("<project>: backlog complete — N features shipped"), then run the `retrospective` skill to
   record lessons and file follow-ups before ending the run.
2. Run the full `/feature` pipeline (the `feature` skill of this plugin) on the lowest-numbered
   open issue.
3. Outcomes:
   - **Merged** → next iteration.
   - **Skipped for clarification** (ambiguity rule) → next iteration; collect it for the final summary.
   - **Circuit breaker tripped** (3 failed cycles) → STOP the whole run. The notification and
     issue diagnosis were already sent by /feature; add a run summary of what shipped before the
     stop, then run the `retrospective` skill to capture what shipped and why the run stopped.

Rules:
- One issue at a time, always to completion or explicit skip — never interleave branches.
- If every remaining issue is in the skipped-for-clarification set, stop and summarize instead of
  spinning, then run the `retrospective` skill.
- Between issues, verify `main` is green (`gh run list --branch main --limit 1`); if main is
  somehow red, fixing main IS the next task before any new feature.
