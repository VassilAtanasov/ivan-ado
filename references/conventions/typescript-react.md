# TypeScript / React / Next.js conventions

Rules Ivan follows when writing TypeScript, and the code-reviewer enforces on the diff.
Formatting is NOT here — Prettier and ESLint own that and the gate fails on them. Everything below
is a judgement the tooling cannot make.

## Typing

- `strict: true`. `any` is a finding — use `unknown` and narrow. `as` casts need a comment naming
  the invariant; `as any` and non-null `!` are findings.
- `@ts-ignore` is a finding; `@ts-expect-error` with a reason is the only accepted form.
- Type the boundary, not the internals: data arriving from network, forms, `localStorage`, or env is
  parsed and validated (e.g. Zod) before it is trusted — never cast into shape.
- Derive types (`ReturnType`, `z.infer`, generated API types) rather than restating them by hand.

## React

- Components are pure with respect to render: no mutation of props/state, no side effects outside
  effects/handlers.
- `useEffect` is for synchronising with something outside React. Deriving state from props in an
  effect is a finding — compute it during render.
- Every effect that starts something (subscription, timer, fetch) cleans it up, and every async
  effect handles unmount/abort (`AbortController`).
- Complete dependency arrays. Suppressing the lint rule requires a comment naming why.
- Keys are stable ids, never array indices for lists that reorder.
- State lives at the lowest common owner; server data belongs in a query cache, not duplicated into
  `useState`.

## Next.js

- Server Components by default; `"use client"` only where interactivity or browser APIs require it,
  pushed as far down the tree as possible.
- Secrets stay server-side. Anything in `NEXT_PUBLIC_*` is public — a token there is a finding.
- Server Actions and route handlers validate their input and re-check authorisation; the client
  having hidden a button is not access control.
- Be explicit about caching and revalidation on data fetches rather than relying on the default.
- `next/image` and `next/font` over raw tags; no layout-shifting unsized media.

## Errors and async

- No floating promises — await, return, or explicitly handle. Every rejection path is handled.
- Errors surfaced to the user are actionable; failures are never silently swallowed in a `catch`.
- Never `dangerouslySetInnerHTML` with anything derived from user input.

## Structure

- Named exports; default exports only where the framework requires them (pages, layouts).
- No barrel files that re-export whole directories — they defeat tree-shaking and cause cycles.
- Business logic lives outside components in plain testable functions.

## Tests

- Behaviour through the public surface: Testing Library queries by role and text, not by test id or
  component internals.
- Mock at the network boundary (MSW), not your own modules.
- A test that renders and asserts nothing meaningful is hollow.
- Every bug fix lands with a test that fails without the fix.
