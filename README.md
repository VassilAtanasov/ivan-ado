# ivan-ado — Ivan, an autonomous SDLC agent for Claude Code on Azure DevOps

**Ivan** is a Claude Code plugin that turns any Azure DevOps repository into an autonomous software
development lifecycle: you describe the product, Ivan plans it with you on Azure Boards, then builds
it feature by feature — gated, tested, reviewed, verified, and merged through pull requests —
pinging you only when something is done or needs your decision.

## Planning in Azure Boards

The plan and the backlog are the same objects — there is no second system to keep in sync:

| Work item | Is | Maps to |
|---|---|---|
| the ADO team project + its Azure Repo | the repository | never auto-created |
| **Epic** | one phase of iterative development | an **Area Path** of the same name + `docs/<project-slug>/` |
| **Feature** | one shippable slice; its **Description** is the feature description | built by `/implement`; tagged `ivan`, plus `ready` once `/kickoff` settles it |
| **Task** children, comments | notes, edge cases, open questions | raw material for discovery; never built directly |

Azure Boards is the source of truth for the **plan and the execution**, `docs/` for the **product
truth**. Interactive writes are dry-run until you say go, and Ivan never deletes a work item — the
CLI has no delete command. The autonomous writes are the state transitions: `/implement` moves a
Feature to the in-progress state when it starts and to the terminal state after its PR merges, so
the board shows what has shipped. Details:
[`references/azure-devops.md`](references/azure-devops.md).

**The `ready` tag is the boundary between planning and building.** `/discover` creates Features
tagged `ivan`; only `/kickoff` adds `ready`, and only after every acceptance criterion is settled;
`/autopilot` builds nothing without it. That is what stops a one-line placeholder being built as a
guess.

## The lifecycle

The loop after `/adopt` runs **once per phase** — you keep adding Epics and Ivan drains them one at
a time:

```
/adopt  →  /discover <phase>  →  /kickoff <feature>  →  /implement <id>   →  /retrospective
 once       you + Ivan           you + Ivan,             Ivan alone           Ivan alone
 per repo   which features?      once per feature:       or /autopilot        (lessons +
                                 what does it mean?      to drain the         follow-ups)
                                 → description + ready   backlog
```

| Skill | What it does |
|---|---|
| `/adopt` | Wires Ivan into the current repo: quality gate (`gate.ps1`), enforcement hooks, `azure-pipelines.yml`, the **build validation branch policy** on `main`, doc templates, permission allowlist, board-shape detection, and the `## Ivan project config` section in CLAUDE.md. Idempotent, and it proves the enforcement fires before handing off. |
| `/discover <phase>` | **Breadth, one run per phase.** Decomposes one Epic into its feature list: ideation → feature decomposition → architecture, seeded by what's already on the board. Creates the Feature work items with stub descriptions, ensures the phase's area path, and produces `docs/<project-slug>/REQUIREMENTS.md` + `ARCHITECTURE.md`. Resumable. |
| `/kickoff <feature>` | **Depth, one run per feature.** Interviews you about goal, happy path, edges, and boundaries; writes `## Goal`, `## Acceptance criteria`, `## Out of scope` into the work item's description as Markdown; mirrors the criteria into REQUIREMENTS.md; then tags it `ready`. Open questions block the tag instead of becoming guesses. |
| `/implement <id>` | One work item end-to-end **in its own git worktree** (safe to run several at once, on different items): code + tests → gate → adversarial `code-reviewer` agent ∥ `qa-verifier` agent against the running app (parallel; fixes re-checked incrementally) → PR with auto-complete → branch policy green → server-side squash-merge (self-healing: rebases on conflict, fixes red builds, waits out slow ones) → terminal state. |
| `/autopilot` | Loops `/implement` over the phase's `ready` backlog until it's drained; circuit breaker stops and notifies you after 3 failed cycles on one item; runs `/retrospective` when the run ends and points you at what still needs `/kickoff` or the next Epic. |
| `/retrospective` | Autonomous close-out for a run: records outcome + lessons to `docs/RETROSPECTIVE-LOG.md`, files concrete follow-ups as work items tagged `follow-up` (never `ready`, so autopilot won't auto-build them), and safely returns to `main`. Auto-runs at the end of `/autopilot`. |

## Running several sessions at once

`/implement` (and `/autopilot`, which is just `/implement` in a loop) isolates each run in its own
git worktree, so two sessions can build two different work items at the same time without sharing a
checked-out branch or build output. `/discover` and `/kickoff` commit docs straight to `main`
instead of a branch, so they guard the push with a rebase-and-retry rather than a worktree. Neither
isolates a fixed network port two concurrently-running app instances would both bind to — see
**Concurrency** in the project's `CLAUDE.md` for the full picture.

## Quality guarantees

1. **One gate script** (`gate.ps1`) — format check, build (warnings-as-errors), tests, typecheck, lint, optional coverage floor (`GATE_COVERAGE_MIN`) — run locally, by the Stop hook, and by CI. Server and client legs run in parallel; a green run stamps the working tree (`.gate-stamp`).
2. **Stop hook** — Ivan cannot end a working turn while the gate fails; the failure is fed back until fixed. Skips the re-run when the tree already matches the last green stamp.
3. **Fresh-context subagents** — `code-reviewer` (read-only, adversarial, no memory of writing the code) and `qa-verifier` (exercises the real running app per acceptance criterion).
4. **Azure Pipelines + a build validation branch policy** — the same gate re-runs on every PR, and
   the policy makes merging on red impossible server-side rather than a rule Ivan has to obey.
5. **Merges that heal themselves** — the PR is the enforcement point (Azure Repos ignores `pr:`
   triggers, so a branch policy is the only pre-merge check that exists), but it is not a place
   Ivan waits for you. `pr-wait` classifies every outcome by exit code: a red build gets fixed on
   the branch, a branch that fell behind `main` gets rebased and force-pushed, a slow build gets
   waited out. Only a human-gated policy, an abandoned PR, or a conflict Ivan can't resolve with
   confidence in both sides' intent reaches you.
6. **Coding standards, machine-enforced first** — `/adopt` installs the stack's linter/compiler
   config (for .NET: `.editorconfig` + `Directory.Build.props`, so analyzer and style rules become
   build errors) and writes the judgement rules the tooling *can't* check into `docs/CONVENTIONS.md`,
   which the code-reviewer reads on every diff. Conventions ship for C#, Python and
   TypeScript/React/Next.js; other stacks get one written in the same shape.

## Tracking & notifications

Feature work items are the backlog, the phase's area path is the status view, and each item's
**discussion** is the live log (Ivan comments at every stage). Push notifications on: feature
complete, backlog complete, stuck (circuit breaker), clarification needed, open questions awaiting
input.

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

Prerequisites, checked by `/adopt`'s preflight: **Python 3.9+** (every phase calls `ado_cli.py`),
the **Azure CLI** with the `azure-devops` extension, and an Azure DevOps **PAT** — Work Items
(Read & write), Code (Read & write + Status), Build (Read & execute) — as `AZURE_DEVOPS_PAT`, in
your environment or in the repo's gitignored `.env`. A PAT stored by `az devops login` lives in the
OS keyring and is invisible to the CLI, so `az` working is not evidence that Ivan will.

Then in the project you want Ivan to run: `/adopt`, and follow the lifecycle above.

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
skills/                      adopt, discover, kickoff, implement, autopilot, retrospective
agents/                      code-reviewer, qa-verifier
scripts/                     ado_cli.py (Azure DevOps REST helper — work items, comments, PRs,
                             the CI wait; every text-carrying write goes through it)
references/                  azure-devops.md (API notes + the Epic→Feature board contract)
references/conventions/      per-stack coding conventions installed as docs/CONVENTIONS.md by /adopt
templates/                   gate.ps1, hooks, azure-pipelines.yml, CLAUDE-ivan.md, settings
                             snippet, gitignore, gitattributes, doc skeletons
templates/dotnet/            .editorconfig + Directory.Build.props (installed only for .NET stacks)
```

Reference implementation: https://github.com/VassilAtanasov/Mills
