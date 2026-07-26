# Workflowy — API notes and Ivan's outline contract

Read this when changing Workflowy behaviour in a skill, debugging a call, or interpreting a large
outline. Source: https://workflowy.com/api-reference/ (checked 2026-07-07).

## Ivan's outline contract

Workflowy is the **source of truth for the plan**; GitHub is the execution board; `docs/` is the
written product truth. The outline has exactly three meaningful levels:

| Level | Workflowy item | Maps to |
|---|---|---|
| 1 | Repository — name must match the GitHub repo (`TradingBot`) | the repo itself; never auto-synced |
| 2 | Project — one phase of iterative development | one GitHub Project (linked to the repo) + `docs/<project-slug>/` |
| 3 | Feature — one shippable slice; its **note** is the feature description | one GitHub issue labelled `feature` (body = the note), built by `/implement` |
| 4+ | Notes, edge cases, open questions, later/maybe | read as raw material by discovery; never synced to GitHub |

Item names are short (≤ 15 words). Everything longer — rationale, acceptance thinking, examples,
uncertainty — goes in the item's **note**.

Two skills fill this outline, and neither does the other's job:

- `/discover <project>` — breadth, one run per project: which level-3 features the project
  contains, each with a one-or-two-line stub note, plus its REQUIREMENTS/ARCHITECTURE docs.
- `/kickoff <feature>` — depth, one run per feature: settles the feature with the user, writes that
  item's note in issue-body shape (`## Goal`, `## Acceptance criteria` checklist,
  `## Out of scope`), and creates the GitHub issue with the note as its body verbatim. Open
  questions block the issue instead of becoming guesses.

## Authentication

`Authorization: Bearer <WORKFLOWY_API_KEY>`, key loaded from the environment or the repo `.env`.
Never print the key. `.env` must be gitignored.

## Useful endpoints

- `GET /api/v1/targets` — system targets and user shortcuts.
- `GET /api/v1/nodes?parent_id=<id>` — direct children; sort by `priority`.
- `GET /api/v1/nodes/:id` — one node.
- `POST /api/v1/nodes` — create under `parent_id`; `position` is `top` or `bottom`.
- `POST /api/v1/nodes/:id` — update `name`, `note`, or `layoutMode`.
- `POST /api/v1/nodes/:id/move` — move a node.
- `POST /api/v1/nodes/:id/complete` / `/uncomplete`.
- `DELETE /api/v1/nodes/:id` — permanent delete; never call it.
- `GET /api/v1/nodes-export` — flat export including `parent_id`; **rate-limited to 1 request per
  minute**, so resolve a node id once and use `children`/`outline` after that.

## Node fields

`id`, `parent_id` (export only), `name`, `note`, `priority`, `data.layoutMode`, `createdAt`,
`modifiedAt`, `completedAt`.

Workflowy URLs carry a 12-character short id: for `6ed4b9ca-256c-bf2e-bd70-d8754237b505` the short
id is `d8754237b505`. The CLI accepts a full id, a short id, or a pasted Workflowy URL.

## CLI

`scripts/workflowy_cli.py` in this plugin (resolve it relative to the calling SKILL.md:
`../../scripts/workflowy_cli.py`). Requires Python 3.9+; no third-party packages.

```powershell
python <plugin>/scripts/workflowy_cli.py search "TradingBot"
python <plugin>/scripts/workflowy_cli.py children <node-id-or-url>
python <plugin>/scripts/workflowy_cli.py outline <node-id-or-url> --max-depth 3
python <plugin>/scripts/workflowy_cli.py append-outline <node-id-or-url> --file plan.md
python <plugin>/scripts/workflowy_cli.py append-outline <node-id-or-url> --file plan.md --apply
python <plugin>/scripts/workflowy_cli.py update-node <node-id-or-url> --note-file note.md --apply
python <plugin>/scripts/workflowy_cli.py complete <node-id-or-url> --apply
python <plugin>/scripts/workflowy_cli.py complete <node-id-or-url> --undo --apply
```

`append-outline` and `update-node` are **dry-run unless `--apply`**. In an outline file, two-space
indentation is hierarchy and a line starting with `note:` attaches to the item above it instead of
creating a child.

## Safety

Read freely. Before any write, show the user the dry-run output and get an explicit go-ahead.
Never delete or move a node, and never rewrite an item the user wrote, unless the user asks for
that exact operation — prefer adding children or proposing an edit they can accept.

**Completion is the one autonomous write.** `/implement` runs
`complete <feature-node> --apply` after a feature's PR merges, so the outline reflects what has
shipped. It applies without a dry run because build mode has no user to ask, and it is
non-blocking — an unresolvable node or a failed call is reported and the pipeline continues.
`complete <node> --undo --apply` reverses it. No other node type is ever completed by Ivan.
