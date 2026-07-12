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

## 3. Docs

- `REQUIREMENTS.md` and `ARCHITECTURE.md` templates → `docs/` (skip if the project already has
  filled versions).

## 4. CLAUDE.md

- Prepend the Ivan persona from the `CLAUDE-ivan.md` template if the project's CLAUDE.md doesn't
  already declare Ivan (create CLAUDE.md if absent; if one exists, keep its content below the
  persona).
- Add the `## Ivan project config` section with everything known so far:
  ```
  ## Ivan project config
  - GitHub: <owner>/<repo>
  - Stack: <from user/architecture; "open — decided during /discover" is valid>
  - Projects board: (created during /kickoff)
  - Status field IDs: (recorded during /kickoff)
  ```
  Every later phase reads this section; /kickoff appends the board IDs.

## 5. Verify the enforcement actually works (do not skip)

1. Run `./gate.ps1` → must pass (trivially or genuinely).
2. Simulate a failure (e.g. a deliberately broken file where the gate looks) and pipe
   `'{"stop_hook_active": false}'` into `.claude/hooks/stop-gate.ps1` → must exit 2 with the gate
   output. Clean up.
3. Commit everything, push, confirm the CI run goes green (`gh run list`).

## 6. Hand off

Tell the user: adoption complete, and (in a fresh session so CLAUDE.md and hooks load) run
`/discover` to start shaping the product. List the notification triggers so they know when
they'll be pinged: feature complete, backlog complete, stuck, clarification needed, open questions.
