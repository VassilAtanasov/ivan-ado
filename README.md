# Ivan — an autonomous SDLC agent on Azure DevOps

**Ivan** is a Cursor plugin (Claude Code kept as a second manifest) that turns any Azure DevOps
repository into an autonomous software development lifecycle: you describe the product, Ivan plans
it with you on Azure Boards, then builds it feature by feature — gated, tested, reviewed, verified,
and merged through pull requests — notifying you only when something is done or needs your
decision.

## Planning in Azure Boards

The plan and the backlog are the same objects — there is no second system to keep in sync:

| Work item | Is | Maps to |
|---|---|---|
| the ADO team project + its Azure Repo | the repository | never auto-created |
| **Epic** | one phase of iterative development | an **Area Path** of the same name + a row in `docs/PHASES.md` (an Epic touches N subject docs, not one folder) |
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

## Documentation model

| Artifact | Owns | Written by |
|---|---|---|
| **Feature description** (board) | per-feature product truth: `## Goal` / `## Acceptance criteria` / `## Out of scope` / `## Open questions` | `/kickoff` |
| **Epic description** (board) | per-phase product truth: goal, success criteria, out of scope, architecture decisions | `/discover` |
| **`docs/ARCHITECTURE.md`** | the single system doc: stack, how to run it, layout, cross-cutting conventions, standing decisions `S-N`, the **subject map** (§7), the global **decision index** (§8) | `/adopt`, then `/implement` |
| **`docs/<area>/<subject>/SUBJECT.md`** | one long-lived subject: how it behaves today, tuning values, the `D-NN` it owns, parity vs the reference product | `/implement` |
| **`docs/PHASES.md`** | the ledger joining phases to the subjects they touched | `/discover`, closed by `/retrospective` |

**The board holds what we intend to be true; `docs/` holds what is true and why.** An Epic is a
slice of *time*; a subject doc is a slice of the *system* — one Epic touches N subjects, so
**Epic ↔ docs folder is not 1:1** and `docs/PHASES.md` is the only place they are joined.

**`/implement` is the only thing that writes into `docs/`.** `/discover` and `/kickoff` read them
so they do not re-decide what is settled, and record their conclusions on the work item; the
promotion to a `D-NN` happens in the same PR as the code. A decision that has not shipped is
intent, and intent lives on the board. **Decision ids are global and permanent** — never
renumbered, never reused.

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
| `/adopt` | Wires Ivan into the current repo. Settles the **stack profile** first (detect → confirm → record: stack, layout, app shape, run commands, QA tooling, supply-chain check), then installs everything that depends on it: quality gate (`gate.ps1`) with the right legs, coding conventions and lint config, enforcement hooks for **both Cursor and Claude Code**, `azure-pipelines.yml`, the **build validation branch policy** on `main`, doc templates, and the `## Ivan project config` section in `AGENTS.md` (plus a one-line `CLAUDE.md` shim). Idempotent, and it proves the gate, both hook shapes, the supply-chain step and the QA tooling before handing off. |
| `/discover <phase>` | **Breadth, one run per phase.** Decomposes one Epic into its feature list. Creates Feature work items with stub descriptions, ensures the phase's area path, writes the phase goal into the Epic description, and appends the phase's row to `docs/PHASES.md`. Resumable. |
| `/kickoff <feature>` | **Depth, one run per feature.** Interviews you; writes `## Goal`, `## Acceptance criteria`, `## Out of scope` into the work item description; tags it `ready`. Writes no docs — the description is the contract. |
| `/implement <id>` | One work item end-to-end **in its own git worktree** (agent root moved into that worktree before any edits): code + tests → gate → adversarial `code-reviewer` (read-only) ∥ `qa-verifier` against the running app → PR with auto-complete → branch policy green → server-side squash-merge → terminal state. |
| `/autopilot` | Loops `/implement` over the phase's `ready` backlog until it's drained; circuit breaker stops and notifies you after 3 failed cycles on one item; runs `/retrospective` when the run ends. |
| `/retrospective` | Autonomous close-out: records outcome + lessons to `docs/RETROSPECTIVE-LOG.md`, files follow-ups tagged `follow-up` (never `ready`), and safely returns to `main`. |

## Running several sessions at once

`/implement` isolates each run in its own git worktree and **moves the agent root into it**, so two
sessions can build two different work items at the same time without sharing a checked-out branch
or having file edits land in the main checkout. `/discover` and `/kickoff` land their docs through
a short-lived branch and an auto-completing squash PR — branch policies on `main` reject a direct
push, docs included. Neither isolates a fixed network port — see **Concurrency** in the project's
`AGENTS.md`.

## Quality guarantees

1. **One gate script** (`gate.ps1`) — format, build (warnings-as-errors), tests, typecheck, lint,
   dependency advisories, optional coverage floor — run locally, by the Stop hook, and by CI.
2. **Supply chain in the gate** — every leg ends with an advisory check. A skipped local check
   still fails the branch policy.
3. **Stop hook (both editors)** — Ivan cannot end a working turn while the gate fails. Cursor
   re-prompts via `followup_message` (`loop_limit` 30). Claude Code uses exit 2 + stderr.
4. **Push deny while the stamp is stale** — Cursor `beforeShellExecution` denies `git push` /
   `az repos pr` when `.gate-stamp` does not match the working tree (`failClosed: true`).
5. **Fresh-context subagents** — `code-reviewer` (read-only) and `qa-verifier` (running app, browser
   tools when the recorded QA tooling is a browser).
6. **Azure Pipelines + a build validation branch policy** — merging on red is impossible
   server-side. Auto-complete merges the moment policies pass.

## Install

### Cursor (normal use)

**Customize → Add Marketplace → Import from Github** → this repo → Install `ivan` (user or project
scope). Enable **Auto Refresh** and the Cursor GitHub App so pushes to the tracked branch re-index
(at most every 10 minutes). Bump `version` in `.cursor-plugin/plugin.json` in the same commit you
ship; the version string itself is not what triggers the update. Manual **Refresh** in marketplace
settings is the fallback; a stale IDE cache may need Refresh + uninstall/reinstall.

**Import from Github adds a marketplace catalog.** It does not import a plugin folder. After the
catalog lists Ivan, you still Install `ivan`.

If the importer rejects `source: "./"`, the marketplace entry may need `source` pointing at a
subfolder; today this repo is a single-plugin root (`source: "./"`).

### Cursor (this checkout, uncommitted work)

There is no file watcher. After you edit skills, agents, or the manifest:

```powershell
powershell -NoProfile -File scripts/install-cursor.ps1
```

(`pwsh` also works if PowerShell 7 is on PATH.)

That copies this checkout to `%USERPROFILE%\.cursor\plugins\local\ivan`. Then **Developer: Reload
Window** (sometimes a new chat). An already-running `/implement` keeps the old skill text until
reload.

Alternatively: **Customize → Plugins → Add → From Local Path** pointed at this checkout (or the
copy under `plugins\local\ivan`). Same reload requirement.

Do **not** use `/add-plugin` / `install_plugin` (first-party slugs only). Do **not** install Ivan
as a personal skill under `~/.cursor/skills/`.

### Claude Code

```
claude plugin marketplace add VassilAtanasov/ivan-ado
claude plugin install ivan@ivan
```

Local checkout: `claude plugin marketplace add C:\path\to\ivan-ado` then
`claude plugin install ivan@ivan`. Restart the session after installing.

### Two different installs

Putting Ivan **into the editor** (GitHub marketplace, From Local Path, or `plugins/local`) is not
the same as `/adopt` copying `gate.ps1` + hooks **into an app repo**.

### Prerequisites

Checked by `/adopt`'s preflight: **Python 3.9+** (every phase calls `ado_cli.py`), the **Azure CLI**
with the `azure-devops` extension, and an Azure DevOps **PAT** — Work Items (Read & write), Code
(Read & write + Status), Build (Read & execute) — as `AZURE_DEVOPS_PAT` in the repo's gitignored
`.env`. A PAT stored by `az devops login` lives in the OS keyring and is invisible to the CLI, so
`az` working is not evidence that Ivan will.

Then in the project you want Ivan to run: `/adopt`. In Cursor Agent auto-run, allow `git`, `az`,
`python`, and `pwsh *gate.ps1*` (and the hook scripts under `.claude/hooks/`).

## Update

**Cursor:** push to the branch the marketplace tracks (usually `main`). Auto Refresh + GitHub App
re-index; otherwise Refresh in marketplace settings. Reload Window after a local copy-install.

**Claude Code:** `claude plugin marketplace update ivan`. Template files already copied into
projects (`gate.ps1`, hooks, `azure-pipelines.yml`, conventions) are refreshed by re-running
`/adopt` in that project.

2.2 is a breaking adopt layout for existing projects (`AGENTS.md`, dual hooks). Re-run `/adopt` to
migrate: it renames a filled `CLAUDE.md` to `AGENTS.md` and writes the shim.

## Layout

```
.cursor-plugin/plugin.json     Cursor plugin manifest (v2.2.0)
.cursor-plugin/marketplace.json Cursor marketplace catalog (Import from Github)
.claude-plugin/plugin.json     Claude Code manifest (same version)
.claude-plugin/marketplace.json Claude Code marketplace
skills/                        adopt, discover, kickoff, implement, autopilot, retrospective
agents/                        code-reviewer, qa-verifier
rules/                         ivan.mdc (persona only; project config stays in AGENTS.md)
scripts/                       ado_cli.py, install-cursor.ps1
references/                    azure-devops.md, conventions/
templates/                     gate.ps1, AGENTS-ivan.md, hooks/, cursor/, claude/, doc skeletons
```

The quality gate is **not** in the plugin's own hooks — `/adopt` installs it per project.
