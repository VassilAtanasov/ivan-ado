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

## 3. Stack profile — detect, confirm, record

Everything in sections 3a–3d is stack-dependent, so settle the stack **here**, once, and write it
down. Never infer it again later from whatever files happen to be lying around.

1. **Detect before asking** — read the repo. A solution or `*.csproj` → .NET; `package.json` → Node
   (read it: React/Next/Vue, the test runner, the package manager from the lockfile);
   `pyproject.toml` or `requirements.txt` → Python (framework from its dependencies);
   `docs/ARCHITECTURE.md` if an earlier phase already decided. Note the **layout** (where server
   code lives, where client code lives) and the **app shape** — HTTP API, browser UI, CLI, desktop,
   worker, library. The shape is what decides what the `qa-verifier` needs.
2. **Confirm or ask** — put the detected profile to the user with AskUserQuestion, detected answer
   first. An empty repo has nothing to detect, so ask outright; if the answer is "not decided yet",
   record `Stack: open — decided during /discover` and **skip 3b–3d**, which `/discover` runs at
   the end of its architecture pass instead. Never guess a stack into existence: a gate built for
   the wrong stack passes trivially forever, and every later phase believes it is protected.
3. **Record it in the Ivan project config** (section 6 writes the file; these are the lines):
   ```
   - Stack: <e.g. .NET 10 minimal API + React 19/Vite, or "open — decided during /discover">
   - Layout: <server code root, client code root — the paths gate.ps1 detects>
   - App shape: <http-api | browser-ui | cli | desktop | worker | library> (may be several)
   - Run commands: <what starts each component locally, and how to override its port>
   - QA tooling: <what the qa-verifier drives the app with — see 3d>
   - Supply chain: <the advisory check per stack — see 3c>
   ```
   `App shape` and `Run commands` are read by the `qa-verifier` on every feature; `Layout` is what
   `gate.ps1`'s detection must match. A wrong line here degrades a whole class of verification to
   "UNVERIFIABLE" without anything going red, so get them right while the user is in the room.

## 3a. Quality machinery (copy from templates, then adapt to the profile)

- `gate.ps1` → project root. The template ships three legs — .NET (`server/`, `src/`, root), Node
  (`client/`, `web/`, `frontend/`, root) and Python (`pyproject.toml` at root, `server/`, `api/`,
  `src/`) — each ending in a supply-chain step, and it passes trivially until application code
  exists. **Delete the legs this project does not have and correct the detection roots to the
  `Layout` line**; do not leave the guesses in. A stack with no leg in the template gets one
  written in the same shape: format check → build/typecheck (warnings as errors) → tests →
  advisory check.
- `hooks/format-changed.ps1` and `hooks/stop-gate.ps1` → `.claude/hooks/`. `stop-gate.ps1`'s
  source filter is an *exclude* list (docs, markdown, `.claude/`), so it keeps firing whatever the
  layout is — leave it alone unless the project has another prose-only directory to add. Extend
  `format-changed.ps1`'s `switch` with a formatter per language in the profile (`ruff format` for
  `.py`, and so on).
- Merge the template `settings.snippet.json` into the project's `.claude/settings.json`: hooks
  wiring (PostToolUse format, Stop gate) + permission allowlist (adapt to the stack — add
  `Bash(ruff:*)`, `Bash(pytest:*)`, `Bash(npx playwright:*)` as the profile requires) +
  destructive-command denies. Never overwrite unrelated existing settings.
- `azure-pipelines.yml` → repo root — section 4 covers adapting it. CI must run the same
  `gate.ps1`, with the same tools installed.

## 3b. Coding standards (stack-dependent — install only what matches)

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
  `pyproject.toml`, and point the gate's Python leg at the right root. The leg picks `pyright` when
  `pyproject.toml` has a `[tool.pyright]` section and `mypy` otherwise.
- **TypeScript / Next.js** — ensure `strict: true` in `tsconfig.json`, ESLint with
  `@typescript-eslint` (including `no-floating-promises`, which needs type-aware linting) and
  `eslint-plugin-react-hooks`, and Prettier. The gate's client leg runs `npm run typecheck`,
  `npm run lint` and `npm test`, so those scripts must exist in `package.json` — a missing script
  failing the leg is the correct outcome, not something to work around.

Warnings are errors in every stack — the gate must not go green on a warning.

## 3c. Supply chain (the last step of every gate leg)

Ivan adds dependencies unattended, so a known-vulnerable package has to be a red gate rather than
something a person notices later. The template gate already runs the check per leg; your job is to
make sure the tool it calls is present and configured, and to record the choice on the
`Supply chain` config line.

- **.NET** — `dotnet list package --vulnerable --include-transitive`, parsed for High/Critical.
  (The command exits 0 whatever it finds, which is why the gate parses its output instead of
  trusting the exit code.) Nothing to install. Consider a `nuget.config` pinning the feed, so a
  package cannot be resolved from an unexpected source.
- **Node** — `npm audit --audit-level=high`, which needs a committed `package-lock.json`; the gate
  fails when the lockfile is missing, because unpinned dependencies cannot be audited at all. For
  pnpm/yarn, swap in `pnpm audit --audit-level high` / `yarn npm audit --severity high` and fix the
  lockfile check to match.
- **Python** — `pip-audit --strict`. Add `pip-audit` to the project's dev dependencies so the CI
  agent and the developer machine both have it; the gate fails loudly when it is absent rather than
  skipping the check in silence.
- Whatever the stack, the check **runs in CI too**. An agent that cannot reach the advisory
  database turns it into a permanent red, so verify it passes in section 7 before handing off, and
  if the org proxies its feeds, record what the check talks to.

There is one escape hatch, `GATE_SKIP_SUPPLY_CHAIN=1`, for genuinely offline local work. Tell the
user it exists and that it is never valid in CI or as a way to get a PR merged — the pipeline does
not set it, so skipping locally still fails the branch policy.

## 3d. QA tooling (what the `qa-verifier` will actually need)

The `qa-verifier` exercises the **running application**, one acceptance criterion at a time. What
that takes depends on the app shape, and a missing tool does not fail loudly — the verifier reports
`UNVERIFIABLE` and the feature ships on the strength of unit tests alone. Work the answer out now,
from the app shape, and install it:

| App shape | The verifier needs | Do this during adoption |
|---|---|---|
| HTTP API | an HTTP client + the run command | `Invoke-RestMethod`/`curl` are already there; confirm the API starts and how its port is overridden |
| Browser UI | a real browser driver | `npx playwright install --with-deps chromium`, or the project's existing E2E runner — never add a second one |
| CLI | the built binary and a shell | confirm the build produces a runnable entry point |
| Worker / queue | a way to inject a message and observe the effect | note the local queue or emulator and how to start it |
| Persistence (any) | a restartable data store | note the container/service command and how to reset it |
| Library only | no running app — say so | record that criteria are verified through the test suite instead |

Then:

1. **Ask only what you cannot determine** (AskUserQuestion): which E2E runner, if none exists;
   whether a local database or container is expected to be running; what seed data or credentials a
   verification pass needs. Never ask the user to paste a secret — a required one goes in the
   gitignored `.env` under a documented key name.
2. **Record `Run commands` and `QA tooling`**, including the **port override** for every component
   (`ASPNETCORE_URLS`, `PORT`, a `--port` flag). `/implement` runs in a worktree, so two
   verification passes can run at once; without an override the second binds a taken port and looks
   like a broken feature.
3. **Prove it once, now**: start the app with the recorded command on a non-default port and hit it
   with the recorded client (or drive one page with the browser driver). What does not work during
   adoption, with the user present, will not work unattended at 2am.
4. If there is no runnable app yet, say so and record the intent. The "Scaffold the application
   stack" feature `/kickoff` schedules first is what makes it real, and these lines must be filled
   in when that feature lands.

## 4. Pipeline and branch policy (do not skip — this is what makes "never merge red" real)

**Commit and push everything sections 1–3d produced — not just `azure-pipelines.yml`.** The gate
script, the hooks, the lint config, the templates and `azure-pipelines.yml` all go to `main` in one
push, and **this is the last direct push to `main` this project will ever get**: step 2 below
creates a blocking policy that rejects every later one with `TF402455`. Ordering it the other way
round makes `/adopt` create the policy that rejects its own push, which is a real failure and not a
retryable one. Everything sections 5–7 add lands through a PR instead — see **Landing a change on
`main`** in `references/azure-devops.md`.

Then:

0. **Adapt `azure-pipelines.yml` to the stack profile before creating the pipeline.** The agent
   must be able to run every step the local gate runs, or CI goes red on a missing tool rather
   than on a defect:
   - one installer task per runtime **actually in the profile** — delete the rest. `UseDotNet@2`
     pinned to the SDK the project builds with, `NodeTool@0` for a Node leg, `UsePythonVersion@0`
     plus the dev-dependency install for a Python leg.
   - the **supply-chain tools** from 3c (`pip-audit` for Python; `dotnet`/`npm` already carry
     theirs). The pipeline must never set `GATE_SKIP_SUPPLY_CHAIN`.
   - the **QA tooling** from 3d, but only if the gate itself runs those tests — a Playwright E2E
     suite in the gate needs `npx playwright install --with-deps chromium` on the agent; a browser
     driver used only by the local `qa-verifier` does not belong in CI.
   - a service container or database the tests need, and any `variables:` the run commands expect.
   - the pool image: `ubuntu-latest` unless the stack needs Windows (a desktop UI, an IIS-hosted
     app, a Windows-only dependency), in which case `windows-latest` — and then re-check that
     `gate.ps1` behaves the same on both.
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
  - Stack: <from section 3; "open — decided during /discover" is valid>
  - Layout: <server code root, client code root — the paths gate.ps1 detects>
  - App shape: <http-api | browser-ui | cli | desktop | worker | library>
  - Run commands: <per component: what starts it, and the port override>
  - QA tooling: <what the qa-verifier drives the app with>
  - Supply chain: <the advisory check per stack, and anything it needs network access to>
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
4. **Prove the supply-chain step runs** — `./gate.ps1` output must contain the advisory step for
   every leg, and it must have executed rather than been skipped. If the project has no
   dependencies yet, the step passing on an empty set is fine; what must not happen is the step
   being absent. Do not test it by introducing a real vulnerable package.
5. **Prove the QA tooling works** (3d step 3) if you have not already: the app starts on an
   overridden port and answers the recorded client. Skip only if there is no runnable app yet, and
   say so.
6. Confirm the pipeline ran green on the section-4 push:
   `az pipelines runs list --project <project> --branch main --top 1 -o json` — repeat until
   `status` is `completed`, then check `result` is `succeeded`. There is no blocking `run watch`
   in Azure DevOps; poll with a few seconds between calls rather than in a tight loop.
7. **Land whatever sections 5–7 changed** (docs, CLAUDE.md, any lint fix from step 3) per
   **Landing a change on `main`** in `references/azure-devops.md`: branch, commit, push,
   `pr-create --squash --delete-source-branch --auto-complete`. Do not push to `main` — step 4.2
   made that impossible, and a skill that tries it and then deletes the policy to get past it has
   destroyed the thing it was adopting. **Nothing you wrote may be left uncommitted at hand-off.**
8. **Prove the PR gate is real** — the PR from step 7 is the proof, so use it rather than opening a
   throwaway: `ado_cli.py pr-wait <pr> --repo <repo>` must print the build validation policy's
   status lines, and must exit 0 — the PR merged itself. Any other exit is the enforcement telling
   you something: 4 means a human-gated policy is in the way (step 4.4 should have caught it), and
   no policy lines at all mean step 4.2 did not take effect. Fix it before handing off, because
   every later merge depends on it. Only if sections 5–7 changed nothing, open a throwaway
   branch and PR for the check instead, and abandon it afterwards
   (`az repos pr update --id <pr> --status abandoned`).

## 8. Hand off

Show the user the recorded stack profile — stack, layout, app shape, run commands, QA tooling,
supply-chain check — and say plainly which parts you proved and which are still promises (an empty
repo cannot prove its run commands). They are the lines every later phase trusts without
re-deriving, so a correction now is cheap and a correction after ten features is not.

Tell the user: adoption complete, and (in a fresh session so CLAUDE.md and hooks load) run
`/discover <project>` to decompose the first phase into Features, then `/kickoff <feature>` once per
feature to settle its description. List the notification triggers so they know when they'll be
pinged: feature complete, backlog complete, stuck, clarification needed, open questions.
