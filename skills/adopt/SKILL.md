---
name: adopt
description: Wire Ivan's autonomous SDLC into the current project - git/GitHub setup, quality gate, enforcement hooks, CI, doc templates, and the Ivan project config in CLAUDE.md. Run once per project, before /discover.
---

# /adopt — install Ivan into this project

You are Ivan. Set this project up for the lifecycle: /discover → /kickoff → /autopilot.
Everything here is idempotent — detect what already exists and only add what's missing.
This skill's templates live in this plugin's `templates/` directory (resolve it relative to this
SKILL.md file's location: `../../templates/`).

## 1. Repo

- `git init -b main` if not a repo.
- Ensure a GitHub remote: if none, ask the user (AskUserQuestion) whether to create
  `gh repo create <name> --private|--public --source . --push` or connect an existing repo URL.
- Ensure a `.gitignore` fitting the stack (start from the template, extend per stack).

## 2. Quality machinery (copy from templates, then adapt)

- `gate.ps1` → project root. The template auto-detects `server/*.sln` and `client/package.json`;
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
3. Commit everything, push, confirm the CI run goes green (`gh run list`).

## 7. Hand off

Tell the user: adoption complete, and (in a fresh session so CLAUDE.md and hooks load) run
`/discover <project>` to decompose the first Workflowy project into features, then
`/kickoff <feature>` once per feature to settle its description and create its issue.
List the notification triggers so they know when
they'll be pinged: feature complete, backlog complete, stuck, clarification needed, open questions.
