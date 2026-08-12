# main and release/* branch strategy

## Context

This repo builds a per-platform **test server** against a specific version of the
Couchbase Lite (CBL) SDK, then drives it from a Python test suite. The CBL SDK API
changes across versions: signatures change and symbols are added or removed, so
test-server source written for a newer CBL line will not compile against an older
one (new API cannot be referenced when building against a version that lacks it).

The traditional way to support multiple versions from a single branch is
conditional compilation (`#if`-style guards keyed on the SDK version). We rejected
that for two reasons:

1. The differences are not merely additive feature flags — they are breaking API
   changes, so guards would metastasize across every platform's test-server code
   and rot quickly.
2. The JVM (`jak`) test server has **no** preprocessor or conditional-compilation
   mechanism at all, making the approach outright impossible for at least one
   platform in the matrix.

## Decision

We keep long-lived `release/X.Y` branches, one per CBL **version line** (3.2, 3.3,
4.0, …), with a deliberate split of authority:

- **Test-server source** is version-specific. For a given `CBL_VERSION`, the
  prebuild pipeline derives `release/<major>.<minor>` and builds the test server
  from that branch. If no such branch exists, it falls back to `main`
  (see `jenkins/pipelines/prebuild/Jenkinsfile`, "Determine Branch"). So `main`
  always holds the test-server source for the current/in-development CBL line;
  each `release/X.Y` is a frozen-compatible snapshot for a shipped line.

- **Tests always come from `main`.** The test-run pipelines check out `main` and
  run its `tests/`. The `tests/` directory that exists on a `release/X.Y` branch
  is a stale byproduct of the branch point — it is never executed and must never
  be consulted by a human or an AI agent. There is **no enforcement** of this;
  it rests on pipeline discipline (the test-run job never checks out a release
  branch) and word of mouth.

### Lifecycle & propagation

- A `release/X.Y` branch is created **lazily** — only when `main`'s test-server
  code first adopts API that is incompatible with the X.Y SDK line. It captures
  the last state compatible with that line.
- Propagation is **forward-only**: fixes land on `main`, then are cherry-picked
  back to the release branches that still need them. Release branches never merge
  into `main`.

## Consequences

- `main` stays clean of per-version compatibility cruft; version divergence lives
  in branches instead of in-source guards.
- The cost is duplicated `tests/` content on release branches that is meaningless
  and actively misleading. Anyone (or any agent) working on a `release/X.Y` branch
  must treat `tests/` as non-authoritative; only test-server code (`servers/`,
  build scripts, and their dependencies) is meaningful there. A warning belongs in
  each release branch's `AGENTS.md`/`README`.
