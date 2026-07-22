# Couchbase Lite System Test Harness

Glossary of terms whose meaning in this repo differs from their common usage.
This file is a glossary only — no implementation details, no decisions (those
live in `docs/adr/`).

## Branching

**release/X.Y branch**:
A long-lived branch holding **test-server source** frozen at the last state
compatible with the Couchbase Lite `X.Y` version line. It is *not* a release of
this repository and *not* a short-lived stabilization branch. Its `tests/`
directory is a stale byproduct and is never authoritative.
_Avoid_: release branch (in the gitflow sense), stabilization branch.

**main**:
The single authoritative source of **tests**, always. Also the test-server source
for the current/in-development CBL version line.

**CBL version line**:
A Couchbase Lite `major.minor` series (e.g. `3.2`, `4.0`) whose SDK shares a
compatible API surface. Each line maps to at most one `release/X.Y` branch.
_Avoid_: release, version (unqualified).

**test server**:
A per-platform binary built against a specific CBL SDK version and driven by the
Python test suite. Built from `release/X.Y` for shipped lines, from `main` for the
current line.
