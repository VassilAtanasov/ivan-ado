# ivan-sdlc — Ivan, an autonomous SDLC agent for Claude Code

**Ivan** is a Claude Code plugin that turns any repository into an autonomous software development
lifecycle: you describe the product, Ivan plans it with you, then builds it feature by feature —
gated, tested, reviewed, verified, and merged through PRs — pinging you only when something is
done or needs your decision.

## The lifecycle

```
/adopt  →  /discover  →  /kickoff  →  /autopilot ( = /feature × N )  →  /retrospective
 once       you + Ivan     Ivan          Ivan alone                       Ivan alone
 per repo   collaborate    (asks only    (per feature: build, ship,       (lessons +
                           if unclear)    then a /learning-coach note)      follow-ups)
```

| Skill | What it does |
|---|---|
| `/adopt` | Wires Ivan into the current repo: quality gate (`gate.ps1`), enforcement hooks, CI workflow, doc templates, permission allowlist, and the `## Ivan project config` section in CLAUDE.md. Idempotent. |
| `/discover` | Guided interview: product ideation → functionality discovery → architecture. Produces `docs/REQUIREMENTS.md` + `docs/ARCHITECTURE.md`. Resumable. |
| `/kickoff` | Requirements → GitHub Issues backlog (acceptance criteria per feature) + Projects Kanban board. Refuses to guess: notifies you and asks if anything is ambiguous. |
| `/feature` | One issue end-to-end: branch → code + tests → gate → adversarial `code-reviewer` agent ∥ `qa-verifier` agent against the running app (run in parallel; fixes re-checked incrementally) → PR → CI green → squash-merge → `learning-coach` note. |
| `/autopilot` | Loops `/feature` over the whole backlog; circuit breaker stops and notifies you after 3 failed cycles on one issue; runs `/retrospective` when the run ends. |
| `/learning-coach` | Non-blocking artifact: writes a dated note to `docs/LEARNING-LOG.md` explaining the language concepts a shipped feature actually introduced (stack-aware). Auto-runs at feature close-out; never gates or edits code. |
| `/retrospective` | Autonomous close-out for a run: records outcome + lessons to `docs/RETROSPECTIVE-LOG.md`, files concrete follow-ups as `follow-up`-labeled issues (never `feature`, so autopilot won't auto-build them), and safely returns to `main`. Auto-runs at the end of `/autopilot`. |

## Quality guarantees

1. **One gate script** (`gate.ps1`) — build (warnings-as-errors), tests, typecheck, lint — run locally, by the Stop hook, and by CI. Server and client legs run in parallel; a green run stamps the working tree (`.gate-stamp`).
2. **Stop hook** — Ivan cannot end a working turn while the gate fails; the failure is fed back until fixed. Skips the re-run when the tree already matches the last green stamp.
3. **Fresh-context subagents** — `code-reviewer` (read-only, adversarial, no memory of writing the code) and `qa-verifier` (exercises the real running app per acceptance criterion).
4. **GitHub Actions CI** — same gate re-runs on every PR; merging on red is forbidden.

## Tracking & notifications

GitHub Issues are the backlog, a GitHub Projects board is the status view, issue timelines are the
live log (Ivan comments at every stage). Push notifications on: feature complete, backlog complete,
stuck (circuit breaker), clarification needed, open questions awaiting input.

## Install (once per machine)

```
claude plugin marketplace add VassilAtanasov/ivan-sdlc
claude plugin install ivan@ivan-sdlc
```

(or the `/plugin marketplace add` / `/plugin install` slash commands in an interactive session).
Private-repo note: cloning uses your git HTTPS credentials — `gh auth login` once if needed.
Restart the session after installing; skills load at session start.

Then in the project you want Ivan to run: `/adopt`, and follow the lifecycle above.

A project can additionally pin Ivan in its `.claude/settings.json` — this **declares** the
marketplace and keeps the plugin enabled for everyone, but each collaborator still runs the
two install commands once on their machine:

```json
{
  "extraKnownMarketplaces": {
    "ivan-sdlc": { "source": { "source": "github", "repo": "VassilAtanasov/ivan-sdlc" } }
  },
  "enabledPlugins": { "ivan@ivan-sdlc": true }
}
```

## Update (after enhancing Ivan)

```
claude plugin marketplace update ivan-sdlc
```

All projects on the machine pick up the new version at their next session. Template files
already copied into projects by `/adopt` (gate.ps1, hooks, ci.yml) are refreshed by re-running
`/adopt` in that project.

## Layout

```
.claude-plugin/plugin.json   plugin manifest (+ marketplace.json — this repo is its own marketplace)
skills/                      adopt, discover, kickoff, feature, autopilot, retrospective, learning-coach
agents/                      code-reviewer, qa-verifier
templates/                   gate.ps1, hooks, ci.yml, CLAUDE-ivan.md, settings snippet, doc skeletons
```

Reference implementation: https://github.com/VassilAtanasov/Mills
