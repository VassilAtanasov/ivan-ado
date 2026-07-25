# ivan-sdlc — Ivan, an autonomous SDLC agent for Claude Code

**Ivan** is a Claude Code plugin that turns any repository into an autonomous software development
lifecycle: you describe the product, Ivan plans it with you, then builds it feature by feature —
gated, tested, reviewed, verified, and merged through PRs — pinging you only when something is
done or needs your decision.

## Planning in Workflowy

You plan in [Workflowy](https://workflowy.com/); Ivan reads and writes that outline through the
Workflowy API (`WORKFLOWY_API_KEY` in the repo's gitignored `.env`). Three levels matter:

| Level | Workflowy item | Maps to |
|---|---|---|
| 1 | repository — name matches the GitHub repo (`TradingBot`) | the repo; never auto-synced |
| 2 | project — one phase of iterative development | one GitHub Project + `docs/<project-slug>/` |
| 3 | feature — one shippable slice; its **note** is the feature description | one `feature` issue (body = the note), built by `/implement` |
| 4+ | notes, edge cases, open questions, later/maybe | raw material for discovery; never synced |

Workflowy is the source of truth for the **plan**, `docs/` for the **product truth**, GitHub for
**execution**. Writes to Workflowy are dry-run until you say go; Ivan never deletes, moves, or
completes a node. Details: [`references/workflowy.md`](references/workflowy.md).

## The lifecycle

The loop after `/adopt` runs **once per project (phase)** — you keep adding level-2 projects in
Workflowy and Ivan drains them one at a time:

```
/adopt  →  /discover <project>  →  /kickoff <feature>  →  /implement <issue>   →  /retrospective
 once       you + Ivan             you + Ivan,             Ivan alone             Ivan alone
 per repo   which features?        once per feature:       or /autopilot          (lessons +
                                   what does it mean?      to drain the board      follow-ups)
                                   → note + issue
```

| Skill | What it does |
|---|---|
| `/adopt` | Wires Ivan into the current repo: quality gate (`gate.ps1`), enforcement hooks, CI workflow, doc templates, permission allowlist, Workflowy key + root node, and the `## Ivan project config` section in CLAUDE.md. Idempotent. |
| `/discover <project>` | **Breadth, one run per project.** Decomposes one Workflowy project into its feature list: ideation → feature decomposition → architecture, seeded by what you already outlined. Writes the features back as level-3 items with stub notes and produces `docs/<project-slug>/REQUIREMENTS.md` + `ARCHITECTURE.md`. Resumable. |
| `/kickoff <feature>` | **Depth, one run per feature.** Interviews you about goal, happy path, edges, and boundaries; writes the description into that feature's Workflowy note (`## Goal`, `## Acceptance criteria`, `## Out of scope`); mirrors the criteria into REQUIREMENTS.md; then creates the GitHub issue with that note as its body verbatim, on the project's board (created on first use). Open questions block the issue instead of becoming guesses. |
| `/implement <issue>` | One issue end-to-end: branch → code + tests → gate → adversarial `code-reviewer` agent ∥ `qa-verifier` agent against the running app (run in parallel; fixes re-checked incrementally) → PR → CI green → squash-merge → `learning-coach` note. |
| `/autopilot` | Loops `/implement` over the active project's board until that phase is drained; circuit breaker stops and notifies you after 3 failed cycles on one issue; runs `/retrospective` when the run ends and points you at the next Workflowy project. |
| `/learning-coach` | Non-blocking artifact: writes a dated note to `docs/LEARNING-LOG.md` explaining the language concepts a shipped feature actually introduced (stack-aware). Auto-runs at `/implement` close-out; never gates or edits code. |
| `/retrospective` | Autonomous close-out for a run: records outcome + lessons to `docs/RETROSPECTIVE-LOG.md`, files concrete follow-ups as `follow-up`-labeled issues (never `feature`, so autopilot won't auto-build them), and safely returns to `main`. Auto-runs at the end of `/autopilot`. |

## Quality guarantees

1. **One gate script** (`gate.ps1`) — format check, build (warnings-as-errors), tests, typecheck, lint, optional coverage floor (`GATE_COVERAGE_MIN`) — run locally, by the Stop hook, and by CI. Server and client legs run in parallel; a green run stamps the working tree (`.gate-stamp`).
2. **Stop hook** — Ivan cannot end a working turn while the gate fails; the failure is fed back until fixed. Skips the re-run when the tree already matches the last green stamp.
3. **Fresh-context subagents** — `code-reviewer` (read-only, adversarial, no memory of writing the code) and `qa-verifier` (exercises the real running app per acceptance criterion).
4. **GitHub Actions CI** — same gate re-runs on every PR; merging on red is forbidden.
5. **Coding standards, machine-enforced first** — `/adopt` installs the stack's linter/compiler
   config (for .NET: `.editorconfig` + `Directory.Build.props`, so analyzer and style rules become
   build errors) and writes the judgement rules the tooling *can't* check into `docs/CONVENTIONS.md`,
   which the code-reviewer reads on every diff. Conventions ship for C#, Python and
   TypeScript/React/Next.js; other stacks get one written in the same shape.

## Tracking & notifications

GitHub Issues are the backlog, one GitHub Projects board per Workflowy project is the status view,
issue timelines are the live log (Ivan comments at every stage). Push notifications on: feature complete, backlog complete,
stuck (circuit breaker), clarification needed, open questions awaiting input.

## Install (once per machine)

```
claude plugin marketplace add VassilAtanasov/ivan-sdlc
claude plugin install ivan@ivan-sdlc
```

(or the `/plugin marketplace add` / `/plugin install` slash commands in an interactive session).
Private-repo note: cloning uses your git HTTPS credentials — `gh auth login` once if needed.
Restart the session after installing; skills load at session start.

Then in the project you want Ivan to run: `/adopt`, and follow the lifecycle above. `/discover`
and `/kickoff` additionally need Python 3.9+ and a Workflowy API key
(https://workflowy.com/api-key) in the repo's gitignored `.env` as `WORKFLOWY_API_KEY=...`.

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
already copied into projects by `/adopt` (gate.ps1, hooks, ci.yml, conventions, stack lint config)
are refreshed by re-running
`/adopt` in that project.

## Layout

```
.claude-plugin/plugin.json   plugin manifest (+ marketplace.json — this repo is its own marketplace)
skills/                      adopt, discover, kickoff, implement, autopilot, retrospective,
                             learning-coach
agents/                      code-reviewer, qa-verifier
scripts/                     workflowy_cli.py (Workflowy API helper used by discover + kickoff)
references/                  workflowy.md (API notes + the repo→project→feature outline contract)
references/conventions/      per-stack coding conventions installed as docs/CONVENTIONS.md by /adopt
templates/                   gate.ps1, hooks, ci.yml, CLAUDE-ivan.md, settings snippet, gitignore,
                             gitattributes, doc skeletons
templates/dotnet/            .editorconfig + Directory.Build.props (installed only for .NET stacks)
```

Reference implementation: https://github.com/VassilAtanasov/Mills
