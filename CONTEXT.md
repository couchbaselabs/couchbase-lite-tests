# Couchbase Lite System Test Harness (TDK)

The system that drives per-platform Couchbase Lite test servers against a
Sync Gateway + Couchbase Server backend to verify a Couchbase Lite release.
This glossary fixes the words newcomers most often confuse. It is a glossary
only — no implementation details, no decisions (those live in `docs/adr/`).

## Language

### The three things that sound like "server"

Never write bare "server" in docs — it collides three ways. Always disambiguate:

**Test Server**:
The per-platform executable (C, .NET, iOS, JVM, JS) that hosts a Couchbase
Lite instance and runs operations on command from the Client. Always two
words. Built against a specific CBL SDK version: from `release/X.Y` for
shipped version lines, from `main` for the current line.
_Avoid_: server, test-server, CBL server

**Sync Gateway (SGW)**:
The sync and access layer between Couchbase Lite and Couchbase Server. Part of
the Backend.
_Avoid_: gateway, sg

**Couchbase Server (CBS)**:
The backend database behind Sync Gateway. Part of the Backend.
_Avoid_: server, couchbase, cb server

**Backend**:
Sync Gateway + Couchbase Server together — the cloud side a Test Server
replicates against. Provisioned on AWS for CI.
_Avoid_: cloud, environment, infra

### Driving the tests

**Client (TDK)**:
The Python framework (`cbltest`) that configures the Backend, instructs Test
Servers, and reports results. It is the orchestrator, not a Couchbase Lite
client app.
_Avoid_: harness, framework, driver, app

**Test**:
A Python codelet (pytest function) run inside the Client that configures a
Backend and instructs Test Servers. Distinct from the operations a Test Server
performs on its behalf.
_Avoid_: test case, scenario

### What runs where

**Topology**:
A declarative description of the shape to provision — which Test Servers (and
platforms/versions), how many SGW/CBS, how they wire together. The request you
hand the Orchestrator.
_Avoid_: layout, setup, environment spec

**Config (config.json)**:
The contract pytest consumes: where everything actually lives (Test Server
URLs, SGW/CBS hostnames). The single source of truth for a run. Usually
generated from a Topology + real IPs by the Orchestrator, but can be written by
hand for a custom environment — generation is just the least-friction path.
_Avoid_: settings, test config

**Orchestrator**:
The tooling under `environment/aws/` that takes a Topology, provisions the
Backend and Test Servers, and emits a Config. One way to produce a Config, not
the only possible one.
_Avoid_: provisioner, deployer

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
