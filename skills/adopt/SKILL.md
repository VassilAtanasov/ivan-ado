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

Commit and push `azure-pipelines.yml` first, then:

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
4. Commit and push to `main`, then confirm the pipeline ran green:
   `az pipelines runs list --project <project> --branch main --top 1 -o json` — repeat until
   `status` is `completed`, then check `result` is `succeeded`. There is no blocking `run watch`
   in Azure DevOps; poll with a few seconds between calls rather than in a tight loop.
5. **Prove the PR gate is real**: open a throwaway branch with a trivial change, create a PR
   (`ado_cli.py pr-create --repo <repo> --source <branch> --title "policy check"`), and confirm the
   build validation policy appears and runs (`ado_cli.py pr-wait <pr> --repo <repo>` prints the
   policy status lines). Abandon the PR afterwards
   (`az repos pr update --id <pr> --status abandoned`) and delete the branch. If no policy shows
   up, step 4.2 did not take effect — fix it before handing off, because every later merge depends
   on it.

## 8. Hand off

Tell the user: adoption complete, and (in a fresh session so CLAUDE.md and hooks load) run
`/discover <project>` to decompose the first phase into Features, then `/kickoff <feature>` once per
feature to settle its description. List the notification triggers so they know when they'll be
pinged: feature complete, backlog complete, stuck, clarification needed, open questions.
