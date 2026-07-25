# Python conventions

Rules Ivan follows when writing Python, and the code-reviewer enforces on the diff.
Formatting and import order are NOT here — `ruff format` / `ruff check` own those and the gate
fails on them. Everything below is a judgement the tooling cannot make.

## Typing

- Every function that is not a local closure has annotated parameters and return type.
- `mypy --strict` (or `pyright` strict) runs in the gate. `Any` is a finding unless a comment names
  the untyped boundary that forces it; the same goes for `# type: ignore` — it carries the specific
  error code and a reason.
- Model absence as `T | None` and narrow it; do not rely on falsiness (`if not x` hides `0`/`""`).

## Structure

- Functions do one thing; no side effects at import time. Module top level defines things — it does
  not connect, read files, or start work.
- `if __name__ == "__main__":` guards every entry point.
- Prefer dataclasses (or Pydantic models at I/O boundaries) over dicts for structured data that
  crosses a function boundary.
- No mutable default arguments (`def f(x: list = [])`).

## Errors

- Catch specific exceptions. Bare `except:` and `except Exception:` without re-raise or logging with
  `exc_info` are findings.
- Never swallow: an `except: pass` needs a comment naming the condition it tolerates.
- Raise domain-specific exceptions; do not use exceptions for ordinary control flow.
- Clean up with context managers, not `try/finally` written by hand.

## Async

- Do not block the event loop: no `time.sleep`, no synchronous HTTP/database calls inside `async
  def`. Offload CPU-bound or blocking calls (`asyncio.to_thread`).
- Do not fire-and-forget: keep a reference to every `create_task` and await or cancel it.
- Async resources are closed (`async with`); shared clients are created once, not per call.

## Data and dependencies

- Dependencies are pinned in a lockfile that is checked in.
- No secrets in source; configuration comes from the environment, validated once at startup into a
  typed settings object.
- Never build SQL by string interpolation — parameterise, or use the ORM.
- Never `pickle` untrusted data; no `eval`/`exec` on external input; `subprocess` without
  `shell=True`.

## Logging

- The `logging` module, not `print`, in library and application code.
- Lazy interpolation (`logger.info("loaded %s", n)`), never f-strings in the log call.
- Never log secrets, tokens, or personal data.

## Tests

- `pytest`. Behaviour, not implementation — a test that only asserts a mock was called is hollow.
- Fixtures over setup code; parametrise instead of copy-pasting cases.
- Patch where the name is used, not where it is defined; mock at the boundary (HTTP, clock, file
  system), not your own internals.
- Every bug fix lands with a test that fails without the fix.
