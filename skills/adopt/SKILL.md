---
name: adopt
description: Wire Ivan's autonomous SDLC into the current project - git/GitHub setup, quality gate, enforcement hooks, CI, doc templates, and the Ivan project config in CLAUDE.md. Run once per project, before /discover.
---

# /adopt — install Ivan into this project

You are Ivan. Set this project up for the lifecycle: /discover → /kickoff → /autopilot.
Everything here is idempotent — detect what already exists and only add what's missing.
This skill's templates live in this plugin's `templates/` directory (resolve it relative to this
SKILL.md file's location: `../../templates/`).

## 1. Repo and GitHub auth

- `git init -b main` if not a repo.
- Ensure a GitHub remote: if none, ask the user (AskUserQuestion) whether to create
  `gh repo create <name> --private|--public --source . --push` or connect an existing repo URL.
- Ensure a `.gitignore` fitting the stack (start from the template, extend per stack).
- Copy the `gitattributes` template → `.gitattributes` if absent. It normalises line endings so a
  Windows working tree and a Linux CI runner agree; without it, format checks pass locally and fail
  in CI (or the reverse). If the repo already has files committed with mixed endings, run
  `git add --renormalize .` and commit that separately.
- **Auth preflight — do it now, not when /kickoff fails halfway through.** Run `gh auth status`,
  then prove Projects access with `gh project list --owner <owner> --limit 1`. If that call fails
  with "Resource not accessible by personal access token", stop and tell the user which fix
  applies:
  - a classic PAT needs the `project` scope (`gh auth refresh --scopes project`);
  - a fine-grained PAT needs **Projects: Read and write**;
  - and if `GITHUB_TOKEN`/`GH_TOKEN` is set in the environment, `gh` uses it in preference to its
    keyring and `gh auth refresh` cannot upgrade it — the variable has to be fixed or unset.
  Record the outcome in the Ivan project config so later phases don't re-check.

## 2. Quality machinery (copy from templates, then adapt)

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
- `ci.yml` → `.github/workflows/ci.yml`, adapted to the stack's runtimes. CI must run the same
  `gate.ps1`.

## 2b. Coding standards (stack-dependent — install only what matches)

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

## 3. Workflowy (the planning source of truth)

Ivan plans in Workflowy: level 1 = this repository, level 2 = projects (phases of iterative
development), level 3 = features. See this plugin's `references/workflowy.md` for the full
contract and the CLI (`../../scripts/workflowy_cli.py` relative to this SKILL.md).

- Check `python --version` (3.9+ required by the CLI). If Python is missing, say so and continue —
  everything except `/discover` and `/kickoff` still works.
- `WORKFLOWY_API_KEY`: verify it resolves from the environment or a repo `.env`. If it doesn't,
  tell the user to create a key at https://workflowy.com/api-key and put it in `.env` as
  `WORKFLOWY_API_KEY=...` themselves — never ask them to paste it into chat. Ensure `.env` is in
  `.gitignore` before the key exists.
- Resolve the level-1 node whose name matches the repo name (`workflowy_cli.py search "<repo>"`,
  rate-limited to 1/min). If none exists, tell the user to create it in Workflowy with a one-line
  note, and offer to bootstrap its first level-2 project node once it exists.
- Record the node's short id in the Ivan project config as `Workflowy root`.

## 4. Docs

- Repo-wide `docs/ARCHITECTURE.md` from the template (system-level decisions shared by every
  phase; skip if the project already has a filled one).
- Per-project docs are created by `/discover` at `docs/<project-slug>/REQUIREMENTS.md` and
  `docs/<project-slug>/ARCHITECTURE.md` from the same templates — don't pre-create them here.

## 5. CLAUDE.md

- Prepend the Ivan persona from the `CLAUDE-ivan.md` template if the project's CLAUDE.md doesn't
  already declare Ivan (create CLAUDE.md if absent; if one exists, keep its content below the
  persona).
- Add the `## Ivan project config` section with everything known so far:
  ```
  ## Ivan project config
  - GitHub: <owner>/<repo>
  - GitHub auth: <verified DD-MM-YYYY: issues/PRs + Projects v2 accessible>
  - Stack: <from user/architecture; "open — decided during /discover" is valid>
  - Workflowy root: <short id> (level-1 item "<repo>")
  - Active project: (set by /discover)

  ### Projects
  | Project (Workflowy level 2) | wf short id | Docs folder | Board # | Project ID | Status field / Todo / In Progress / Done |
  |---|---|---|---|---|---|
  | (filled by /discover and /kickoff) | | | | | |
  ```
  Every later phase reads this section; /discover adds the project row, /kickoff fills its board IDs.

## 6. Verify the enforcement actually works (do not skip)

1. Run `./gate.ps1` → must pass (trivially or genuinely).
2. Simulate a failure (e.g. a deliberately broken file where the gate looks) and pipe
   `'{"stop_hook_active": false}'` into `.claude/hooks/stop-gate.ps1` → must exit 2 with the gate
   output. Clean up.
3. Prove the standards are enforced, not just documented: introduce one deliberate violation the
   linter owns (a `var` where the .editorconfig forbids it and an unused private field for .NET; an
   `any` for TypeScript; an unannotated function for Python), run `./gate.ps1` → must go **red** on
   that rule. Revert. Skip only if the stack has no application code yet, and say so.
4. Commit everything, push, then confirm CI goes green with
   `gh run watch --repo <owner>/<repo>` — it blocks until the run finishes. Do not use
   `gh run list` here: immediately after a push the run may not exist yet, so listing once races
   it and reports the previous run (or nothing).

## 7. Hand off

Tell the user: adoption complete, and (in a fresh session so CLAUDE.md and hooks load) run
`/discover <project>` to decompose the first Workflowy project into features, then
`/kickoff <feature>` once per feature to settle its description and create its issue.
List the notification triggers so they know when
they'll be pinged: feature complete, backlog complete, stuck, clarification needed, open questions.
