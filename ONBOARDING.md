# Onboarding

This repo is large, but the shape is simple once the vocabulary clicks. Most
newcomer confusion is *conceptual*, not mechanical — so start here, not with
the build scripts.

Terms in **bold** below are defined precisely in [CONTEXT.md](CONTEXT.md). When
in doubt about a word, that glossary is the source of truth.

## The mental model

Three roles, and the thing that ties them together:

```
   ┌────────────────────┐        instructs        ┌──────────────────────────┐
   │   Client (TDK)      │ ──────────────────────▶ │      Test Servers        │
   │  Python `cbltest`   │                         │  C │ .NET │ iOS │ JVM │ JS │
   │  runs the Tests     │                         │ (one per CBL platform)   │
   └─────────┬───────────┘                         └────────────┬─────────────┘
             │ configures                                        │ replicates against
             ▼                                                   ▼
        ┌──────────────────────────── Backend ────────────────────────────┐
        │   Sync Gateway (SGW)   ◀────────────▶   Couchbase Server (CBS)   │
        └──────────────────────────────────────────────────────────────────┘
```

- The **Client** (the Python `cbltest` framework) is the brain. It runs the
  **Tests**, configures the **Backend**, and tells the **Test Servers** what to
  do. It is *not* a Couchbase Lite client app.
- A **Test Server** is a per-platform executable hosting one Couchbase Lite
  instance. The Client drives it; it does the actual CBL work. ("Test Server"
  is always two words — bare "server" is ambiguous here, see below.)
- The **Backend** is **Sync Gateway (SGW)** + **Couchbase Server (CBS)** — the
  cloud side the Test Servers replicate against.

> **The "server" trap:** three different things sound like "server" — the
> **Test Server**, **Sync Gateway**, and **Couchbase Server**. They are not
> interchangeable. The glossary bans the bare word for this reason.

### Topology vs. config.json

The other thing that trips people up: there are two JSON files and they are not
the same.

- A **Topology** describes the *shape you want provisioned* — which Test
  Servers (platforms, CBL versions), how many SGW/CBS, how they wire up. It is
  the **request** you hand the **Orchestrator**.
- **config.json** describes *where everything actually is* — Test Server URLs,
  SGW/CBS hostnames. It is the **contract pytest consumes**, and the single
  source of truth for a run.

config.json is normally **generated** from a Topology + the real IPs the
Orchestrator provisioned — so **don't hand-edit a generated config.json**. That
generation path is just the lowest-friction option, though: nothing stops you
writing a config.json by hand for a custom environment, or building a different
orchestrator entirely. config.json is the interface; the Topology/Orchestrator
is one (blessed) way to produce it.

## How a run actually happens (AWS)

AWS is the canonical path — it's what CI uses and what you should reach for
first. Full prerequisites and details live in
[environment/aws/README.md](environment/aws/README.md).

```
 Topology JSON  ──▶  Orchestrator  ──▶  config.json  ──▶  pytest
 (what to make)     (start_backend)    (where it is)     (the Tests)
```

1. **Authenticate:** `aws sso login` (see the orchestrator README for IAM
   prerequisites).
2. **Provision the Backend + Test Servers** from a Topology:
   ```bash
   cd environment/aws
   uv run python start_backend.py --topology topology_setup/topology.json
   ```
   This emits a `config.json` into the test suite directory.
3. **Run the Tests** against that config:
   ```bash
   cd tests/dev_e2e
   uv run pytest -x -v --config config.json test_basic_replication.py
   ```
4. **Tear it down** when finished:
   ```bash
   cd environment/aws
   uv run python stop_backend.py --topology topology_setup/topology.json
   ```

Starter Topology files for single-platform runs live in
`jenkins/pipelines/dev_e2e/<platform>/topologies/` (e.g.
`topology_single_macos.json`, `topology_single_ios.json`).

## I own a Test Server

You're responsible for one platform's Test Server under `servers/`. Each
platform follows the same chain — `download_cbl` → `build_*` → package — but the
toolchain differs (CMake for C, `dotnet` for .NET, Xcode for iOS, Gradle for
JVM, Vite/npm for JS). Your starting points:

- [servers/AGENTS.md](servers/AGENTS.md) — the per-platform build/run map.
- `servers/<your-platform>/` — your build scripts and platform README.
- In a Topology, your platform is named by a platform string (e.g. `c_macos`,
  `swift_ios`) with `download: true` to fetch a prebuilt Test Server, or
  `false`/omitted to build it. The prebuild Jenkins job builds and uploads these
  artifacts.

## I write Tests

Tests are Python codelets run inside the Client. Anatomy:

- Subclass `CBLTestClass`; decorate each test with
  `@pytest.mark.asyncio(loop_scope="session")`.
- Declare what the Test needs with topology markers:
  `@pytest.mark.min_test_servers(1)`, `@pytest.mark.min_sync_gateways(1)`,
  `@pytest.mark.min_couchbase_servers(1)`.
- Use the `cblpytest` fixture (`.test_servers[]`, `.sync_gateways[]`,
  `.couchbase_servers[]`, …) and the `dataset_path` fixture.
- Call `self.mark_test_step("…")` to narrate steps in the logs.

Run a single Test against an existing `config.json`:

```bash
cd tests/dev_e2e
uv run pytest -x -v --config config.json test_basic_replication.py::TestBasicReplication::test_push_pull
```

Start here:
[tests/AGENTS.md](tests/AGENTS.md) and [client/AGENTS.md](client/AGENTS.md).

## Next steps & custom environments

- **Repo-wide architecture:** [AGENTS.md](AGENTS.md) and
  [docs/architecture.agents.md](docs/architecture.agents.md).
- **Why is it built this way?** (per-platform Test Servers, a Python driver, a
  versioned protocol) — [docs/adr/](docs/adr/).
- **Custom / hand-rolled environment:** write your own `config.json` pointing at
  whatever Test Servers + Backend you control, and run pytest against it. No
  Orchestrator required.
- **Custom Sync Gateway builds (niche):** if you're iterating on a local or
  custom-built SGW, [environment/local/](environment/local/README.md) can run an
  in-memory `rosmar` SGW or a build from source against a locally-launched Test
  Server — e.g.
  `uv run environment/local/run_sync_gateway.py --start --server rosmar`, then
  `pytest --config environment/local/rosmar_config.json`. This is *not* the
  supported path for normal test runs; reach for AWS instead.

> The Docker environment under `environment/docker/` is **deprecated** — it may
> still work but is unmaintained.
