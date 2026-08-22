---
name: adopt
description: Wire Ivan's autonomous SDLC into the current project - Azure Repos/Boards setup, quality gate, enforcement hooks, pipeline, branch policy, doc templates, and the Ivan project config in CLAUDE.md. Run once per project, before /discover.
---

# /adopt — install Ivan into this project

You are Ivan. Set this project up for the lifecycle: /discover → /kickoff → /autopilot.
Everything here is idempotent — detect what already exists and only add what's missing.
This skill's templates live in this plugin's `templates/` directory (resolve it relative to this
SKILL.md file's location: `../../templates/`). The Azure DevOps contract and CLI are documented in
`../../references/azure-devops.md` — read it before your first call.

## 1. Repo and Azure DevOps auth

- `git init -b main` if not a repo.
- Ensure an Azure Repos remote. If none, ask the user (AskUserQuestion) whether to create one
  (`az repos create --name <name> --project <project> -o json`, then
  `git remote add origin https://dev.azure.com/<org>/<project>/_git/<repo>`) or connect an existing
  repo URL. Git auth goes through Git Credential Manager — **never** put a PAT in the remote URL.
- Ensure a `.gitignore` fitting the stack (start from the template, extend per stack). It must
  contain `.env` before any credential exists.
- Copy the `gitattributes` template → `.gitattributes` if absent. It normalises line endings so a
  Windows working tree and a Linux pipeline agent agree; without it, format checks pass locally and
  fail in CI (or the reverse). If the repo already has files committed with mixed endings, run
  `git add --renormalize .` and commit that separately.
- **Auth preflight — do it now, not when /kickoff fails halfway through.**
  1. `python --version` (3.9+ required by `ado_cli.py`). If Python is missing, say so and stop —
     the CLI is on the critical path for every phase, not an optional extra.
  2. `python <plugin>/scripts/ado_cli.py whoami` — proves the credential, org and project. If it
     reports no credential, tell the user to create a PAT at
     `https://dev.azure.com/<org>/_usersSettings/tokens` with **Work Items** (Read & write),
     **Code** (Read & write, plus Status), **Build** (Read & execute) and put it in the repo's
     gitignored `.env` as `AZURE_DEVOPS_PAT=...` themselves — never ask them to paste it into chat.
     Note for them: a PAT stored by `az devops login` lives in the OS keyring and is invisible to
     the script, so `az` working is not evidence that `ado_cli.py` will.
  3. `az repos list --project <project> -o json` — proves repo access.
- Record the outcome in the Ivan project config so later phases don't re-check.

## 2. Board shape (process, types, states)

Run `python <plugin>/scripts/ado_cli.py project-info` — one call gives the process template, the
work item types, every state with its category, and the repos. Record in the config:

- **Feature type**: `Feature` on Agile/Scrum/CMMI, `Issue` on Basic (which has no Feature type).
- **In-progress state**: the first state whose category is `InProgress` (Agile `Active`,
  Scrum `Committed`, Basic `Doing`).
- **Terminal state**: the state whose category is `Completed` (Agile `Closed`, Scrum/Basic `Done`).

Never hardcode these anywhere else — every later phase reads them from the config.

## 2b. Team configuration (the backlog will look empty without this)

Ivan puts each phase's work items on a child **area path** (`<Project>\<phase>`), and Azure Boards
shows a team only the areas that team owns. A brand-new team owns the project root with
**sub-areas excluded**, so every Feature Ivan creates is invisible in the backlog — the items exist
and every WIQL query finds them, but the user sees an empty board and reasonably concludes nothing
was created.

Check and fix both settings, for the team that owns the backlog
(`az devops team list --org <org> --project <project> -o json`):

1. **Area scope must include sub-areas.**
   ```
   az devops invoke --org <org> --area work --resource teamfieldvalues      --route-parameters project=<project> team="<team>" --http-method GET --api-version 7.1 -o json
   ```
   If the entry for the project root has `includeChildren: false`, PATCH it (write the body to a
   file — `az devops invoke --in-file` rejects a UTF-8 BOM, so use an encoding that omits it):
   ```json
   {"defaultValue": "<project>",
    "values": [{"value": "<project>", "includeChildren": true}]}
   ```
   ```
   az devops invoke --org <org> --area work --resource teamfieldvalues      --route-parameters project=<project> team="<team>" --http-method PATCH      --in-file teamfield.json --media-type application/json --api-version 7.1
   ```
2. **The Epics backlog level must be visible**, or the Epic that every Feature nests under cannot
   be seen. Read `teamsettings` and, if `backlogVisibilities."Microsoft.EpicCategory"` is false,
   PATCH `{"backlogVisibilities": {"Microsoft.EpicCategory": true}}` to the same `teamsettings`
   resource.

Both are also reachable in the UI under Project settings → Team configuration (Areas, and
Backlogs), which is worth telling the user so they can see what changed.

If the project is on **Basic** and the user wants the Epic → Feature hierarchy, tell them the
conversion is UI-only: Organization settings → Boards → Process → Basic → Projects tab → select the
project → More actions → Change process → Agile. It is safe while the board is empty and risks
work-item-type remapping once it isn't. Adopting on Basic with `Issue` as the feature type is a
valid alternative — record whichever they choose.

## 3. Quality machinery (copy from templates, then adapt)

- `gate.ps1` → project root. The template auto-detects `server/*.sln[x]` (the .NET 10 SDK's
  `dotnet new sln` produces `.slnx`) and `client/package.json`;
  if the project's stack (ask, or read docs/ARCHITECTURE.md if present) differs, adapt the
  detection and steps NOW — the gate must fail loudly on broken code and pass trivially when the
  relevant code doesn't exist yet.
- `hooks/format-changed.ps1` and `hooks/stop-gate.ps1` → `.claude/hooks/`. Adapt the source-change
  path filter in stop-gate.ps1 to the project layout.
- Merge the template `settings.snippet.json` into the project's `.claude/settings.json`:
  hooks wiring (PostToolUse format, Stop gate) + permission allowlist (adapt the tool commands to
  the stack) + destructive-command denies. Never overwrite unrelated existing settings.
- `azure-pipelines.yml` → repo root, adapted to the stack's runtimes. CI must run the same
  `gate.ps1`.

## 3b. Coding standards (stack-dependent — install only what matches)

Determine the stack first (ask, or read docs/ARCHITECTURE.md). If the stack is still open, skip this
section and run it at the end of `/discover` once the stack is decided.

**Conventions doc (every stack).** Concatenate the matching files from this plugin's
`references/conventions/` (`csharp.md`, `python.md`, `typescript-react.md`) into the project's
`docs/CONVENTIONS.md`, each under a `# <stack>` heading. A full-stack project gets more than one.
If the stack has no file here, write the section yourself in the same shape — judgement rules only,
never formatting — and note which linter owns the rest. CLAUDE.md's `## Coding standards` section
already points every phase at this file; the code-reviewer reads it on every diff.

**Enforcement config, per stack.** The principle: the linter/compiler enforces everything it can, and
the gate fails on it — so Ivan never has to remember a rule a machine could check.

- **.NET** — copy `templates/dotnet/editorconfig` → repo root `.editorconfig` and
  `templates/dotnet/Directory.Build.props` → the .NET source root (e.g. `server/`). Adjust
  `TargetFramework` to the installed SDK. If `.editorconfig` already exists, merge the
  `dotnet_diagnostic.*` and naming rules in rather than overwriting. Add `coverlet.collector` to test
  projects if you want the gate's coverage step (it is skipped when absent).
- **Python** — ensure `ruff` (format + lint) and `mypy`/`pyright` strict are configured in
  `pyproject.toml`, and that `gate.ps1` runs `ruff format --check`, `ruff check`, the type checker,
  and `pytest` as a Python leg.
- **TypeScript / Next.js** — ensure `strict: true` in `tsconfig.json`, ESLint with
  `@typescript-eslint` (including `no-floating-promises`, which needs type-aware linting) and
  `eslint-plugin-react-hooks`, and Prettier. The template gate's client leg already runs typecheck,
  lint and tests.

Warnings are errors in every stack — the gate must not go green on a warning.

## 4. Pipeline and branch policy (do not skip — this is what makes "never merge red" real)

**Commit and push everything sections 1–3b produced — not just `azure-pipelines.yml`.** The gate
script, the hooks, the lint config, the templates and `azure-pipelines.yml` all go to `main` in one
push, and **this is the last direct push to `main` this project will ever get**: step 2 below
creates a blocking policy that rejects every later one with `TF402455`. Ordering it the other way
round makes `/adopt` create the policy that rejects its own push, which is a real failure and not a
retryable one. Everything sections 5–7 add lands through a PR instead — see **Landing a change on
`main`** in `references/azure-devops.md`.

Then:

1. Create the pipeline if it doesn't exist (check `az pipelines list --project <project> -o json`
   by name first):
   ```
   az pipelines create --name "<repo> quality gate" --project <project> --repository <repo> \
     --repository-type tfsgit --branch main --yml-path azure-pipelines.yml --skip-first-run false -o json
   ```
   Record the pipeline id in the config.
2. **Create the build validation policy on `main`.** Azure Repos ignores `pr:` triggers in YAML —
   without this policy nothing validates a pull request, and `/implement`'s auto-complete would
   merge unvalidated code:
   ```
   az repos policy build create --project <project> --blocking true --enabled true \
     --branch main --repository-id <repo-guid> --build-definition-id <pipeline-id> \
     --display-name "Quality gate" --queue-on-source-update-only true \
     --manual-queue-only false --valid-duration 0
   ```
   (`--valid-duration 0` means the result never expires; `<repo-guid>` comes from
   `ado_cli.py project-info`.) Check `az repos policy list --project <project> -o json` first so a
   re-run doesn't create a duplicate.
3. Optionally restrict merges to squash so history stays linear:
   ```
   az repos policy merge-strategy create --project <project> --blocking true --enabled true \
     --branch main --repository-id <repo-guid> --allow-squash true
   ```
4. **Check the policy set can actually auto-merge** — this is what decides whether Ivan ever
   finishes a feature unattended:
   ```
   python <plugin>/scripts/ado_cli.py policy-check --repo <repo> --branch main
   ```
   Exit 0 means every blocking policy is satisfiable by CI alone. **Exit 4 means a blocking policy
   needs a person** — minimum reviewers, required reviewers, or comment resolution — and every one
   of Ivan's PRs will sit unmerged until someone clicks approve. Do not delete the policy to make
   this pass; it may be there on purpose. Tell the user plainly what it is and let them choose:
   scope it so it doesn't cover Ivan's feature branches, or accept a manual approval per feature.
   Record the choice on the `Auto-merge` line of the config.

   If the project keeps an approver policy, also check Azure Repos' **"allow requestors to approve
   their own changes"** setting for the repo — without it, the identity behind the PAT cannot
   approve its own PR, so auto-complete can never clear the policy on its own.

   A missing blocking **Build** policy is the opposite failure and `policy-check` warns about it
   too: nothing validates a PR, and auto-complete would merge unvalidated code. If you see that
   warning, step 2 did not take effect.

## 5. Docs

- Repo-wide `docs/ARCHITECTURE.md` from the template (system-level decisions shared by every
  phase; skip if the project already has a filled one).
- Per-project docs are created by `/discover` at `docs/<project-slug>/REQUIREMENTS.md` and
  `docs/<project-slug>/ARCHITECTURE.md` from the same templates — don't pre-create them here.

## 6. CLAUDE.md

- Prepend the Ivan persona from the `CLAUDE-ivan.md` template if the project's CLAUDE.md doesn't
  already declare Ivan (create CLAUDE.md if absent; if one exists, keep its content below the
  persona).
- Fill the `## Ivan project config` section with everything resolved above:
  ```
  ## Ivan project config
  - Organization: https://dev.azure.com/<org>
  - ADO project: <project>
  - Repository: <repo> (<repo-guid>)
  - Auth: <verified DD-MM-YYYY: work items + repos + pipelines accessible>
  - Process: <Agile|Scrum|Basic>
  - Feature type: <Feature|Issue>
  - States: in progress = <Active>, terminal = <Closed>
  - Pipeline: <name> (id <n>), build validation policy on main: <verified DD-MM-YYYY>
  - Auto-merge: <clean | needs manual approval: <policy name>>
  - Stack: <from user/architecture; "open — decided during /discover" is valid>
  - Active project: (set by /discover)

  ### Projects
  | Project (phase) | Epic id | Area path | Docs folder |
  |---|---|---|---|
  | (filled by /discover) | | | |
  ```
  Every later phase reads this section; `/discover` adds the project row when it creates the Epic
  and its area path.

## 7. Verify the enforcement actually works (do not skip)

1. Run `./gate.ps1` → must pass (trivially or genuinely).
2. Simulate a failure (e.g. a deliberately broken file where the gate looks) and pipe
   `'{"stop_hook_active": false}'` into `.claude/hooks/stop-gate.ps1` → must exit 2 with the gate
   output. Clean up.
3. Prove the standards are enforced, not just documented: introduce one deliberate violation the
   linter owns (a `var` where the .editorconfig forbids it and an unused private field for .NET; an
   `any` for TypeScript; an unannotated function for Python), run `./gate.ps1` → must go **red** on
   that rule. Revert. Skip only if the stack has no application code yet, and say so.
4. Confirm the pipeline ran green on the section-4 push:
   `az pipelines runs list --project <project> --branch main --top 1 -o json` — repeat until
   `status` is `completed`, then check `result` is `succeeded`. There is no blocking `run watch`
   in Azure DevOps; poll with a few seconds between calls rather than in a tight loop.
5. **Land whatever sections 5–7 changed** (docs, CLAUDE.md, any lint fix from step 3) per
   **Landing a change on `main`** in `references/azure-devops.md`: branch, commit, push,
   `pr-create --squash --delete-source-branch --auto-complete`. Do not push to `main` — step 4.2
   made that impossible, and a skill that tries it and then deletes the policy to get past it has
   destroyed the thing it was adopting. **Nothing you wrote may be left uncommitted at hand-off.**
6. **Prove the PR gate is real** — the PR from step 5 is the proof, so use it rather than opening a
   throwaway: `ado_cli.py pr-wait <pr> --repo <repo>` must print the build validation policy's
   status lines, and must exit 0 — the PR merged itself. Any other exit is the enforcement telling
   you something: 4 means a human-gated policy is in the way (step 4.4 should have caught it), and
   no policy lines at all mean step 4.2 did not take effect. Fix it before handing off, because
   every later merge depends on it. Only if sections 5–7 changed nothing, open a throwaway
   branch and PR for the check instead, and abandon it afterwards
   (`az repos pr update --id <pr> --status abandoned`).

## 8. Hand off

Tell the user: adoption complete, and (in a fresh session so CLAUDE.md and hooks load) run
`/discover <project>` to decompose the first phase into Features, then `/kickoff <feature>` once per
feature to settle its description. List the notification triggers so they know when they'll be
pinged: feature complete, backlog complete, stuck, clarification needed, open questions.
