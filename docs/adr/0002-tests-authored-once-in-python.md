# Tests authored once in Python, not per-platform

Given per-platform Test Servers ([ADR-0001](0001-remote-per-platform-test-servers.md)),
the test logic itself lives in one place: Python (`pytest` + `aiohttp`),
in the `cbltest` Client. Each scenario is written once and runs against every
platform's Test Server by sending the same sequence of remote commands. Python
was chosen as the driver language because it was the language most familiar
across both the development and QE departments at the time — the people who
author and maintain the tests.

## Considered Options

- **Author tests in each platform's native language/framework** — rejected for
  the divergence and duplication reasons in ADR-0001.
- **A bespoke test DSL/config format** — rejected: a real programming language
  with async, fixtures, and assertions is more expressive and lower-maintenance
  than a custom runner.

## Consequences

- Test authors need only Python + the `cbltest` API, never the target
  platform's toolchain.
- The Client must speak a stable contract to servers written in five different
  languages — hence the versioned API in
  [ADR-0003](0003-versioned-test-server-api.md).
