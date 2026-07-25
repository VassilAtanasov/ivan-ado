# C# / .NET conventions

Rules Ivan follows when writing C#, and the code-reviewer enforces on the diff.
Style and formatting are NOT here — `.editorconfig` + `Directory.Build.props` own those and the
gate fails on them. Everything below is a judgement the tooling cannot make.

## Nullability

- `<Nullable>enable</Nullable>` is on. Model absence in the type: `string?`, not a null comment.
- The null-forgiving operator `!` is a claim you must justify. Allowed only with a trailing comment
  naming the invariant that makes it safe (`// validated in ctor`). Never to silence a build error.
- Public entry points validate arguments (`ArgumentNullException.ThrowIfNull`,
  `ArgumentException.ThrowIfNullOrWhiteSpace`) rather than trusting callers across an assembly
  boundary.

## Async

- `async void` only for event handlers. Everything else returns `Task`/`Task<T>`/`ValueTask`.
- Never `.Result`, `.Wait()`, or `GetAwaiter().GetResult()` on a Task in application code.
- Accept and propagate `CancellationToken` through every async call chain that crosses I/O.
  A method with I/O and no `CancellationToken` parameter is a finding.
- Suffix async methods `Async`. In libraries use `ConfigureAwait(false)`; in ASP.NET Core app code
  it is unnecessary — do not scatter it.
- Do not fire-and-forget. If a task is intentionally unawaited, it is explicitly discarded with a
  comment explaining who observes its failure.

## Types and structure

- One public type per file; file name matches the type.
- Types are `sealed` unless designed for inheritance. Prefer composition over inheritance.
- `record` for value-like data (DTOs, events, results), `class` for things with identity/behavior.
- Immutable by default: `init` accessors, `IReadOnlyList<T>`/`IReadOnlyDictionary<,>` on public
  surfaces. Never expose a mutable collection field.
- No static mutable state.

## Dependency injection

- Constructor injection only. No service locator, no `IServiceProvider` injected into app services.
- Depend on abstractions you own; register concrete implementations at the composition root.
- Lifetimes must not be captive: never inject a Scoped service into a Singleton. `DbContext` is
  Scoped — anything holding one is Scoped or narrower.

## Errors

- Exceptions for exceptional conditions, not control flow. Expected failures (validation, not-found,
  conflict) are modelled in the return type or mapped to a status, not thrown-and-caught locally.
- Never `catch (Exception)` without either rethrowing or logging with the exception object.
- Never swallow: an empty catch block is a finding.
- Rethrow with `throw;`, never `throw ex;` (destroys the stack trace).

## Resources and time

- Anything `IDisposable`/`IAsyncDisposable` is disposed — `using`/`await using` or ownership passed
  to DI. `HttpClient` comes from `IHttpClientFactory`, never `new`ed per call.
- `DateTimeOffset.UtcNow` over `DateTime.Now`. Time is injected (`TimeProvider`) anywhere it is
  asserted in a test.
- `Guid.CreateVersion7()` for identifiers that are stored or ordered.

## Data access (EF Core)

- Read-only queries use `AsNoTracking()`.
- No N+1: include or project what you need in one query; never query inside a loop over entities.
- Never materialise a whole table to filter in memory — the filter belongs in the `IQueryable`.
- Migrations are checked in and reviewed like code.

## Logging and configuration

- Structured logging with message templates (`_logger.LogInformation("Loaded {Count}", count)`),
  never string interpolation into the template.
- Never log secrets, tokens, credentials, or personal data.
- Configuration is bound to strongly typed options (`IOptions<T>`) and validated at startup, not
  read by magic string at point of use.

## Tests

- Behaviour, not implementation. A test that asserts a mock was called and nothing else is hollow.
- Data access and HTTP endpoints are covered by integration tests (real database — Testcontainers
  or in-process host), not by mocking the `DbContext`.
- One logical assertion per test; the name says the behaviour
  (`Withdraw_InsufficientFunds_Throws`).
- Every bug fix lands with a test that fails without the fix.

## Suppressions

- `#pragma warning disable` and `[SuppressMessage]` require a comment naming the concrete
  constraint that forces them. An unjustified suppression is a finding.
