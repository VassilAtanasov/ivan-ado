# <Subject> — <one line: what this part of the system is>

> Long-lived subject doc. It outlives every phase: `/implement` updates it as behaviour lands.
> Path: `docs/systems/<system>/SUBJECT.md` (mirrors a system in the reference product) or
> `docs/platform/<area>/SUBJECT.md` (no counterpart in it). With no reference product, a flat
> `docs/subjects/<subject>/SUBJECT.md`.
> Reference counterpart: <name in the reference product> | none.
> Implementation status: not started | partial | at parity | deliberately divergent.
> **Open questions do not live here** — they live on the Feature or Epic they block.
> Status: **TEMPLATE — not yet filled**.

## 1. Purpose and boundary

<!-- What this subject owns, in one paragraph. Then what it explicitly does NOT own, naming the
     neighbouring subject that does. A boundary that names no neighbour is not a boundary. -->

## 2. How it behaves today

<!-- Present tense, and only what is merged. The arguments for and against a feature belong on the
     board, not here. Name the entry points in source (type / file / function) so a reader can get
     from this paragraph to the code in one grep. -->

## 3. Tuning values

<!-- Every number this subject's behaviour depends on, cited BY NAME from source. Never restate a
     value without naming the symbol that owns it — the name is what makes drift greppable. A value
     with no source symbol yet is still a decision, not a tuning value: leave it out. -->

| Constant | Value | Source symbol | Why this value |
|---|---|---|---|
| | | `<File>.<SYMBOL>` | <rationale, or D-NN> |

## 4. Decisions

<!-- Ids are global across the repository and permanent — allocate per docs/ARCHITECTURE.md §9 and
     add the matching index row in the same commit. Newest last. -->

### D-NN — <title>
- **Decision:** <what was decided>
- **Considered:** <the real alternatives, and why each lost>
- **Because:** <the reason, at this system's actual scale>
- **Consequences:** <what this now forbids or forces elsewhere>

## 5. Parity vs <reference>

<!-- Delete this section for a subject with no counterpart in the reference product. Link the gap
     ledger's rows rather than restating them. -->

| Behaviour in <reference> | Here | Status | Notes |
|---|---|---|---|
| | | at parity / partial / missing / deliberately different | <D-NN when different on purpose> |

## 6. Related subjects

<!-- The subjects this one talks to, and the shape of the contact (event, call, shared state). -->
