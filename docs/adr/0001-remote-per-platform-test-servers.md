# Per-platform Test Servers driven over a uniform remote API

Couchbase Lite ships as an embedded SDK in many languages (C, .NET, Swift,
Java/Kotlin, JavaScript) running on many OSes and real devices. There is no
single process or language that can load every CBL variant, and system-level
behavior (replication, P2P, on-device storage) only reproduces faithfully on
the real platform. So instead of testing CBL in-process, we run a thin
**Test Server** on each platform that hosts a real CBL instance and exposes a
uniform remote API, and drive all of them from one external **Client**.

The compelling reason to disconnect the driver this way is **coordination**: a
single test run often spans multiple processes across multiple machines and real
devices (e.g. several CBL peers replicating with each other and with a shared
Backend). Driving them from one external Client lets a single test orchestrate
that whole distributed cast in lockstep — something an in-process or
single-device approach cannot do. A previous attempt used largely the same
architecture; this iteration keeps it for the same reason.

This is the root of the system's apparent complexity: the extra moving parts
(per-platform servers, a remote protocol, network transport) buy us *one* test
definition that coordinates *real* CBL across *every* platform and machine in a
single run.

## Considered Options

- **Per-platform native test suites** (XCTest for iOS, JUnit for JVM, etc.) —
  rejected: every scenario would be reimplemented N times and drift across
  platforms; cross-platform scenarios (e.g. a Swift peer replicating with a
  .NET peer) become impossible to express in a single platform's framework.
- **In-process bindings into one driver language** — rejected: can't cover
  real devices (iOS/Android) or the full platform matrix, masks
  platform-specific behavior, and — decisively — can't coordinate multiple
  independent peers/processes across machines in one run.

## Consequences

- A network protocol now sits between test logic and CBL — see
  [ADR-0003](0003-versioned-test-server-api.md) for how it is versioned.
- Most platforms need real hardware/VMs, which drives the multi-node provisioning
  in `environment/aws/`.
