# ivan-ado — Ivan, an autonomous SDLC agent for Claude Code on Azure DevOps

> **Port in progress.** This is the Azure DevOps fork of `ivan-sdlc`. Ported so far:
> the access layer (`scripts/ado_cli.py`), the board contract
> (`references/azure-devops.md`), `/adopt`, and the templates it installs.
> `/discover`, `/kickoff`, `/implement`, `/autopilot` and `/retrospective` still
> describe the Workflowy + GitHub flow below and are being converted next — do not
> rely on the sections marked *(pre-port)* until then.

**Ivan** is a Claude Code plugin that turns any repository into an autonomous software development
lifecycle: you describe the product, Ivan plans it with you, then builds it feature by feature —
gated, tested, reviewed, verified, and merged through PRs — pinging you only when something is
done or needs your decision.

## Planning in Workflowy *(pre-port)*

You plan in [Workflowy](https://workflowy.com/); Ivan reads and writes that outline through the
Workflowy API (`WORKFLOWY_API_KEY` in the repo's gitignored `.env`). Three levels matter:

| Level | Workflowy item | Maps to |
|---|---|---|
| 1 | repository — name matches the GitHub repo (`TradingBot`) | the repo; never auto-synced |
| 2 | project — one phase of iterative development | one GitHub Project + `docs/<project-slug>/` |
| 3 | feature — one shippable slice; its **note** is the feature description | one `feature` issue (body = the note), built by `/implement` |
| 4+ | notes, edge cases, open questions, later/maybe | raw material for discovery; never synced |

Workflowy is the source of truth for the **plan**, `docs/` for the **product truth**, GitHub for
**execution**. Writes to Workflowy are dry-run until you say go, and Ivan never deletes or moves a
node. The one autonomous write is the loop closing: `/implement` ticks a feature complete once its
PR merges, so the outline shows what has shipped. Details:
[`references/workflowy.md`](references/workflowy.md).

## The lifecycle *(pre-port)*

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
| `/implement <issue>` | One issue end-to-end **in its own git worktree** (safe to run several at once, on different issues): code + tests → gate → adversarial `code-reviewer` agent ∥ `qa-verifier` agent against the running app (run in parallel; fixes re-checked incrementally) → PR → CI green → squash-merge → tick the feature complete in Workflowy → `learning-coach` note. |
| `/autopilot` | Loops `/implement` over the active project's board until that phase is drained; circuit breaker stops and notifies you after 3 failed cycles on one issue; runs `/retrospective` when the run ends and points you at the next Workflowy project. |
| `/learning-coach` | Non-blocking artifact: writes a dated note to `docs/LEARNING-LOG.md` explaining the language concepts a shipped feature actually introduced (stack-aware). Auto-runs at `/implement` close-out; never gates or edits code. |
| `/retrospective` | Autonomous close-out for a run: records outcome + lessons to `docs/RETROSPECTIVE-LOG.md`, files concrete follow-ups as `follow-up`-labeled issues (never `feature`, so autopilot won't auto-build them), and safely returns to `main`. Auto-runs at the end of `/autopilot`. |

## Running several sessions at once

`/implement` (and `/autopilot`, which is just `/implement` in a loop) isolates each run in its own
git worktree, so two sessions can build two different issues at the same time without sharing a
checked-out branch or build output. `/discover` and `/kickoff` commit docs straight to `main`
instead of a branch, so they guard the push with a rebase-and-retry rather than a worktree. Neither
isolates a fixed network port two concurrently-running app instances would both bind to — see
**Concurrency** in the project's `CLAUDE.md` for the full picture.

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

## Tracking & notifications *(pre-port)*

GitHub Issues are the backlog, one GitHub Projects board per Workflowy project is the status view,
issue timelines are the live log (Ivan comments at every stage). Push notifications on: feature complete, backlog complete,
stuck (circuit breaker), clarification needed, open questions awaiting input.

## Install (once per machine)

```
claude plugin marketplace add VassilAtanasov/ivan-ado
claude plugin install ivan-ado@ivan-ado
```

To run it from a local checkout instead (what you want while the port is in flight):

```
claude plugin marketplace add C:\path\to\ivan-ado
claude plugin install ivan-ado@ivan-ado
```

(or the `/plugin marketplace add` / `/plugin install` slash commands in an interactive session).
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
    "ivan-ado": { "source": { "source": "github", "repo": "VassilAtanasov/ivan-ado" } }
  },
  "enabledPlugins": { "ivan-ado@ivan-ado": true }
}
```

## Update (after enhancing Ivan)

```
claude plugin marketplace update ivan-ado
```

All projects on the machine pick up the new version at their next session. Template files
already copied into projects by `/adopt` (gate.ps1, hooks, azure-pipelines.yml, conventions, stack lint config)
are refreshed by re-running
`/adopt` in that project.

## Layout

```
.claude-plugin/plugin.json   plugin manifest (+ marketplace.json — this repo is its own marketplace)
skills/                      adopt, discover, kickoff, implement, autopilot, retrospective,
                             learning-coach
agents/                      code-reviewer, qa-verifier
scripts/                     ado_cli.py (Azure DevOps REST helper — work items, comments, PRs,
                             the CI wait; every text-carrying write goes through it)
                             workflowy_cli.py (pre-port, removed once /discover + /kickoff land)
references/                  azure-devops.md (API notes + the Epic→Feature board contract)
                             workflowy.md (pre-port)
references/conventions/      per-stack coding conventions installed as docs/CONVENTIONS.md by /adopt
templates/                   gate.ps1, hooks, azure-pipelines.yml, CLAUDE-ivan.md, settings
                             snippet, gitignore, gitattributes, doc skeletons
templates/dotnet/            .editorconfig + Directory.Build.props (installed only for .NET stacks)
```

Reference implementation: https://github.com/VassilAtanasov/Mills
