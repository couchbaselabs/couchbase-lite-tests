# Domain Glossary

## Core Product and System Terms

- **CBL (Couchbase Lite):** Embedded database SDK under test on device/server platforms.
- **TDK (Test Development Kit):** Internal name for this system test harness repository.
- **CBS (Couchbase Server):** Backend database server used by Sync Gateway and tests.
- **SGW (Sync Gateway):** Sync and access layer between CBL clients and CBS.
- **ES (Edge Server):** Additional backend component used by QE edge-server scenarios.
- **LogSlurp:** Log aggregation service used during environment/test runs.

## Testing and Framework Terms

- **`cbltest`:** Python framework in `client/src/cbltest` that drives tests and server requests.
- **Test Server:** Platform-specific executable/service (C, .NET, iOS, JVM, JS) controlled by `cbltest`.
- **`cblpytest` fixture:** Session fixture exposing `test_servers`, `sync_gateways`, `couchbase_servers`, and more.
- **Topology markers:** Pytest markers such as `min_test_servers`, `min_sync_gateways`, `min_couchbase_servers`.
- **`dataset_path` fixture:** Shared path to `dataset/sg` in each test suite.
- **`cluster_cleanup`:** Framework-wide autouse fixture (`cbltest.plugins.cluster_cleanup`) that removes all SGW databases and CBS/Rosmar buckets before every test.

## Versioning and Protocol Terms

- **API v1 / v2:** Request/response compatibility layers in `client/src/cbltest/v1` and `v2`.
- **Request registration:** Decorators `@register_request` / `@register_body` bind request types to API versions.
- **Version negotiation:** Startup check that connected test servers agree on supported API version.
- **`upg_sgw` marker:** SGW upgrade-focused test path.

## Infrastructure Terms

- **Topology file:** JSON describing SGW/CBS/ES/LB/test-server composition and versions.
- **Platform bridge:** Abstraction in `environment/aws/topology_setup/test_server_platforms` for install/run/stop.
- **Prebuild test server:** Pipeline/script path that builds and uploads server artifacts before test execution.
- **`uv` workspace:** Root project + `client` member managed by Astral `uv`.

## CI/CD Terms

- **`pre-commit.yml`:** GitHub workflow running the full pre-commit hook suite over all files.
- **`python_verify.yml`:** GitHub workflow for `client/tests`.
- **Pre-commit hooks:** Lint/format/type/commit standards, enforced locally and in CI.
- **Jenkins `setup_test.py`:** Platform pipeline setup scripts following a shared template.

## Common Acronyms

- **P2P:** Peer-to-peer replication
- **XDCR:** Cross datacenter replication scenario (test context)
- **OTel:** OpenTelemetry
- **LB:** Load balancer

## Unknowns

- Internal expansion of some historical acronyms in older pipeline naming (`jak`, etc.) beyond observed usage.
