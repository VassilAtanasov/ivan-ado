# Architecture

> Written collaboratively with Ivan during `/discover` (pass 3). Records the decisions, not just
> the diagram — future build-mode sessions follow this file. Status: **TEMPLATE — not yet filled**.
>
> Used in two places: `docs/ARCHITECTURE.md` holds the system-wide baseline shared by every phase,
> and `docs/<project-slug>/ARCHITECTURE.md` records what that phase adds or changes, deferring to
> the baseline for everything else.

## 1. Overview

<!-- One paragraph + optional ASCII diagram: major components and how they talk. -->

## 2. Stack

- Backend: <!-- e.g. ASP.NET Core, in server/ ; chosen during /adopt or /discover -->
- Frontend: <!-- e.g. React + TypeScript (Vite), in client/ -->
- Data: <!-- e.g. SQLite via EF Core; chosen during /discover -->
- Hosting target: <!-- local / cloud; chosen during /discover -->

## 2a. How to run it

<!-- Exact commands to start backend and frontend, and the ports. The qa-verifier agent follows
     this section literally. -->

## 3. Project layout

<!-- Directory structure once scaffolded, and what belongs where. -->

## 4. Key decisions

<!-- One entry per significant decision:
     D-1: <decision>. Considered: <alternatives>. Chosen because: <reason>. -->

## 5. Cross-cutting conventions

<!-- API shape (REST conventions, error format), validation strategy, state management on the client,
     database migration policy — whatever build-mode Ivan must apply consistently. -->
