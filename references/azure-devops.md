# Azure DevOps — API notes and Ivan's board contract

Read this when changing Azure DevOps behaviour in a skill, debugging a call, or interpreting a
board. Source: Azure DevOps REST API 7.1 and the `azure-devops` CLI extension (checked 2026-08-21).

## Ivan's board contract

Azure Boards is the source of truth for the **plan and the execution at once** — this is the
difference from the Workflowy/GitHub arrangement it replaces, where the plan and the backlog were
two copies of the same text. `docs/` remains the written **product truth**.

| Level | Work item | Maps to |
|---|---|---|
| 1 | the **ADO team project** (e.g. `MW3`) and its Azure Repo | the repo itself; never auto-created |
| 2 | **Epic** — one phase of iterative development, plus an **Area Path** of the same name | `docs/<project-slug>/`; the Area Path is the backlog filter |
| 3 | **Feature** — one shippable slice; its **Description** is the feature description | built by `/implement`; tagged `ivan`, and `ready` once `/kickoff` has settled it |
| 4+ | **Task** children, description bullets, discussion comments | raw material for discovery; never built directly |

Titles are short (≤ 15 words) and carry the `FR-N` prefix (`FR-3: <name>`). Everything longer —
rationale, acceptance criteria, examples — goes in the **Description**, in this exact shape:

```
## Goal
<one paragraph, referencing FR-N>

## Acceptance criteria
- [ ] <concrete, externally verifiable condition>

## Out of scope
- <adjacent temptation> — belongs to <other feature>
```

Two skills fill the board, and neither does the other's job:

- `/discover <project>` — breadth, one run per phase: which Features the Epic contains, each with a
  one-or-two-line stub description, plus its REQUIREMENTS/ARCHITECTURE docs.
- `/kickoff <feature>` — depth, one run per Feature: settles it with the user, writes the full
  description, and adds the **`ready`** tag. **There is no second object to create** — the Feature
  *is* the backlog item. Open questions block the feature instead of becoming guesses.

**The `ready` tag is the discovery→build boundary.** With one object per feature there is nothing
else to distinguish a `/discover` stub from a settled feature — on GitHub that job was done by the
issue's existence. `/discover` tags features `ivan`; only `/kickoff` adds `ready`; `/autopilot`
builds nothing without it. Removing that filter would let autopilot build a one-line placeholder as
a guess.

`/implement` sets `System.State` to `Active` at start, links the merged PR, then sets the terminal
state (`Closed` on Agile) itself — see **PR → work item** below for why that last step is explicit.

## States and types are process-dependent

Never hardcode them. `/adopt` runs `ado_cli.py project-info` once and records the resolved names in
the Ivan project config; every later phase reads them from there.

| Process | Phase | Feature | Buildable | States |
|---|---|---|---|---|
| **Agile** (MW3) | Epic | Feature | Feature | New → Active → Resolved → Closed |
| Scrum | Epic | Feature | Product Backlog Item | New → Approved → Committed → Done |
| Basic | Epic | *(none)* | Issue | To Do → Doing → Done |

Basic has no `Feature` type — a Basic project must be converted (Organization settings → Boards →
Process → Basic → Projects → Change process) or `/adopt` must fall back to `Issue`.

## Authentication

`ado_cli.py` resolves a credential in this order:

1. `AZURE_DEVOPS_PAT` — from the environment or the repo's gitignored `.env`. Sent as
   `Authorization: Basic base64(":" + PAT)`.
2. `AZURE_DEVOPS_EXT_PAT` — the same variable the `az devops` extension honours.
3. `SYSTEM_ACCESSTOKEN` — the pipeline-run token, so the same script works inside CI.
4. `az account get-access-token` for resource `499b84ac-1321-427f-aa17-267ca6975798` — works when
   the user has run `az login`.

PAT scopes: **Work Items** (Read & write), **Code** (Read & write, plus Status for PR policies),
**Build** (Read & execute). Never print the token; `.env` must be gitignored before the key exists.

Note that a PAT stored by `az devops login` lives in the OS keyring and is **not** readable by the
script — `az` commands will work while `ado_cli.py` reports no credential. That is the expected
symptom of a missing `.env`.

Org and project resolve from `--org`/`--project`, then `AZURE_DEVOPS_ORG_URL`/
`AZURE_DEVOPS_PROJECT`, then `~/.azure/azuredevops/config` — so a machine already configured with
`az devops configure -d` needs no extra setup.

## Markdown is opt-in, per field

Large text fields (Description, Repro Steps, Acceptance Criteria) are **HTML by default**. Sending
Markdown into an HTML field renders it as literal text. The fix is a second JSON-Patch op on every
write:

```json
[
  {"op": "add", "path": "/fields/System.Description", "value": "## Goal\n..."},
  {"op": "add", "path": "/multilineFieldsFormat/System.Description", "value": "Markdown"}
]
```

`ado_cli.py` always emits both (`description_ops`). A work item reports its stored formats back as
`multilineFieldsFormat: {"System.Description": "markdown"}`. `az boards work-item create/update`
**cannot** send the second op — this is the main reason the skills use the Python CLI rather than
`az` for work item writes. Once a field is Markdown it cannot return to HTML, which suits Ivan.

## Useful endpoints (all under `https://dev.azure.com/<org>/`)

- `_apis/connectionData` — authenticated user id (needed to set auto-complete on a PR).
- `_apis/projects/<project>?includeCapabilities=true` — project GUID and process template.
- `<project>/_apis/wit/workitemtypes` and `.../workitemtypes/<type>/states` — type and state names.
- `<project>/_apis/wit/wiql` (POST) — WIQL query; returns **ids only**, so follow with a batch read.
- `<project>/_apis/wit/workitems?ids=…&fields=…` — batch read, max 200 ids per call.
- `<project>/_apis/wit/workitems/$<Type>` (POST, `application/json-patch+json`) — create.
- `<project>/_apis/wit/workitems/<id>` (PATCH, same media type) — update.
- `<project>/_apis/wit/workItems/<id>/comments` — discussion (api-version `7.1-preview.4`).
- `<project>/_apis/wit/classificationnodes/areas` — list/create area paths.
- `<project>/_apis/git/repositories/<repo>/pullrequests` — create/read PRs.
- `<project>/_apis/policy/evaluations?artifactId=vstfs:///CodeReview/CodeReviewId/<projectId>/<prId>`
  — branch policy status for a PR (this is the "are the checks green" call).

## CLI

`scripts/ado_cli.py` in this plugin (resolve it relative to the calling SKILL.md:
`../../scripts/ado_cli.py`). Requires Python 3.9+; no third-party packages.

```powershell
python <plugin>/scripts/ado_cli.py whoami
python <plugin>/scripts/ado_cli.py project-info
python <plugin>/scripts/ado_cli.py query --preset open-features --area "MW3\Phase 1"
python <plugin>/scripts/ado_cli.py query --preset stub-features --area "MW3\Phase 1"
python <plugin>/scripts/ado_cli.py show 42 --comments
python <plugin>/scripts/ado_cli.py children 7
python <plugin>/scripts/ado_cli.py create --type Feature --title "FR-3: ..." --description-file note.md --parent 7 --area "MW3\Phase 1" --tag ivan --apply
python <plugin>/scripts/ado_cli.py update 42 --description-file note.md --state Active --apply
python <plugin>/scripts/ado_cli.py comment 42 --file msg.md --apply
python <plugin>/scripts/ado_cli.py area ensure "Phase 1" --apply
python <plugin>/scripts/ado_cli.py pr-create --repo MW3 --source feature/42-slug --title "... (#42)" --description-file pr.md --work-item 42 --squash --delete-source-branch --auto-complete --apply
python <plugin>/scripts/ado_cli.py pr-wait 15 --repo MW3
python <plugin>/scripts/ado_cli.py pr-link 42 --pr 15 --repo MW3 --apply
```

Every write is **dry-run unless `--apply`**, printing the exact JSON-Patch document first. Every
text-carrying argument takes a **file** (`--description-file`, `--file`), never an inline string —
this is what keeps backticks, quotes and `#` in a description intact through PowerShell.

`--json` on any read command emits raw JSON for parsing.

## Backlog queries

The autopilot backlog is one WIQL call, filtered server-side (`--preset open-features`):

```wiql
SELECT [System.Id] FROM WorkItems
WHERE [System.TeamProject] = @project
  AND [System.WorkItemType] = 'Feature'
  AND [System.AreaPath] UNDER 'MW3\Phase 1'
  AND [System.State] NOT IN ('Closed', 'Removed', 'Done', 'Resolved')
  AND [System.Tags] CONTAINS 'ready'
  AND NOT [System.Tags] CONTAINS 'follow-up'
ORDER BY [System.Id]
```

The other presets: `stub-features` is the same query inverted on `ready` — what `/kickoff` still
has to detail — and `follow-ups` lists what `/retrospective` filed. Tags, not types, separate
follow-ups and stubs from buildable work, so `/autopilot` never auto-builds either.

## PR → work item

Azure Repos has **no `Closes #N` keyword**. The link is an explicit relation, and completion does
not close the item:

1. `pr-create --work-item <id>` links the work item at creation (or `pr-link` afterwards).
2. `--auto-complete --squash --delete-source-branch` hands completion to the server, which will
   only merge once every **blocking branch policy** passes.
3. `--transition-work-items` (the `az` flag) moves the item to the *next* state — Active → Resolved
   on Agile, **not** Closed. Ivan therefore does **not** use it: `/implement` sets the terminal
   state explicitly after the merge, so the backlog query can never re-pick shipped work.

## Landing a change on `main`

**Every phase of the SDLC ends by landing its work — never by leaving it in the working tree.** A
skill that writes a file and stops has produced nothing durable: `/discover`'s REQUIREMENTS.md is
the one artifact that cannot be reconstructed from the board, because the board holds titles and
stubs while the docs hold the reasoning. The rule is the same for every skill that writes to the
repo: **commit at the end of each phase, and land it before reporting done.** If you reach a
skill's Exit and `git status` still shows uncommitted changes you made, that is a bug in the run.

**`main` is protected, so "push to `main`" does not work.** `/adopt` §4.2 creates a *blocking*
build-validation policy and a squash-only merge-strategy policy on `main`. Once they exist, a direct
push is rejected by the server:

```
! [remote rejected] main -> main (TF402455: Pushes to this branch are not permitted;
  you must use a pull request to update this branch.)
```

This is not a failure to retry, and `git pull --rebase` does not help — the branch simply cannot be
written to directly. **Docs-only changes are not exempt.** The sequence, for every skill:

1. `git switch -c <docs|chore>/<short-slug>` and commit there. Never commit a message with `-m`;
   write it to a file and use `git commit -F <file>`, and write that file **without a BOM**.
2. `git push -u origin <branch>`.
3. `ado_cli.py pr-create --repo <repo> --source <branch> --title "..." --description-file <file>
   --squash --delete-source-branch --auto-complete --apply`, adding `--work-item <id>` when the
   change belongs to one. **`--squash` is not optional** — the merge-strategy policy rejects a PR
   without it before the build even reports.
4. Report the PR URL. Auto-complete merges it once the blocking policies pass, so a skill does not
   have to block on `pr-wait` for a docs change — but it must **say** the change is landing via a
   PR rather than implying it is already on `main`.

**The one exception is `/adopt` before it creates the policies.** Adoption's own scaffolding commit
(gate, hooks, pipeline, templates, CLAUDE.md config) has to reach `main` for the pipeline to exist
at all, and at that moment no policy is protecting the branch — so it pushes directly, and it must
do so **before** §4.2 runs. Ordering it the other way makes `/adopt` create the policy that rejects
its own push.

If a push to `main` is rejected in any other skill, do not weaken or delete the policy to get past
it. Open the PR.

## CI

- **`pr:` triggers in YAML are ignored for Azure Repos.** PR validation runs only if a **build
  validation branch policy** exists on `main`. `/adopt` creates it (`az repos policy build create`)
  and must verify it fires — without it, auto-complete merges unvalidated code.
- `trigger.paths.exclude` in `azure-pipelines.yml` replaces the Actions `paths-ignore` for
  doc-only pushes to `main`.
- There is no blocking watch equivalent to `gh pr checks --watch`; `ado_cli.py pr-wait` polls the
  PR plus its policy evaluations with backoff. **Its exit code classifies the outcome**, because
  the caller's next move differs completely per case: `0` merged, `2` a blocking build policy
  rejected (fixable on the branch), `3` the branch no longer merges cleanly (rebase and
  force-push), `4` only a human can move it forward, `5` abandoned, `6` timed out while still
  making progress, `1` an error. Skills must branch on the code — treating every non-zero as
  failure is what turns a routine rebase into a page to the user.
- Two conditions would otherwise hang until the timeout, so `pr-wait` reports them the moment it
  sees them: **merge conflicts** (`mergeStatus == "conflicts"` produces no rejected policy, so the
  PR simply never completes) and a PR **parked behind a human-gated policy** — minimum reviewers,
  required reviewers, or comment resolution — with every automated policy already green. Neither
  improves by waiting.
- A PR with every blocking policy approved but **no auto-complete set** will sit forever; `pr-wait`
  calls that out rather than timing out on it.

## Safety

Read freely. Before any write in an interactive phase (`/discover`, `/kickoff`), show the user the
dry-run patch document and get an explicit go-ahead. **Never delete a work item** — the REST
`DELETE` with `destroy=true` is unrecoverable and `ado_cli.py` deliberately has no delete command.
Never rewrite a description the user wrote unless they asked for that exact edit; prefer adding a
child Task or proposing an edit they can accept.

**State changes are the autonomous writes.** `/implement` sets `Active` at start and the terminal
state after the PR merges, without a dry run, because build mode has no user to ask. A failed state
write is reported and the pipeline continues — a merged feature is never reverted over a
bookkeeping call. Nothing else is transitioned by Ivan.
