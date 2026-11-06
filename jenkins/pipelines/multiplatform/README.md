# Multiplatform CBL Testing

Runs `tests/multiplatform` — the tests that need more than one test server (peer-to-peer, multipeer, and several
clients replicating with one Sync Gateway) — against several test servers at once, each on its own platform and CBL
version.

## Usage

```bash
./test_multiplatform.sh "<platform>=<version> ..." <sgw_version> [--topology-file FILE] \
    [--dataset-version VERSION] [--test-filter EXPR] [--setup-only]
```

```bash
# Two iPhones on the latest 4.x
./test_multiplatform.sh "swift_ios=4 swift_ios=4" 4

# An iPhone and an Android device on different versions, only the no-conflicts tests
./test_multiplatform.sh "swift_ios=4.1.0 jak_android=4.1.0-18" 4.1.0 --test-filter no_conflicts

# C and .NET on the agent itself
./test_multiplatform.sh "c_macos=4 dotnet_macos=4" 4
```

| Argument | Meaning |
|---|---|
| `<platform>=<version> ...` | One entry per test server to use. `<platform>` is a test server platform: `swift_ios`, `jak_android`, `jak_desktop`, `jak_webservice`, `dotnet_macos`, `dotnet_windows`, `dotnet_ios`, `dotnet_android`, `c_macos`, `c_windows`, `c_linux_x86_64`, `c_ios`, `c_android`. `<version>` is `4`, `4.1`, `4.1.0` (each meaning its latest build) or `4.1.0-18` (that build). |
| `<sgw_version>` | Sync Gateway version, in the same forms. |
| `--topology-file` | Topology file in this directory (default `topology.json`). |
| `--dataset-version` | CBL dataset version (default `4.0`). |
| `--test-filter` | A pytest `-k` expression. Without it, every test in `tests/multiplatform` runs. |
| `--setup-only` | Set up the backend and test servers, then stop before the tests. |
| `--list-tests` | List the tests in `tests/multiplatform` and exit (the only argument). |

## How test servers are chosen

`topology.json` lists every device and host the `qe-mac-india` agent can reach: 8 iPhones, 8 Android devices, and
`c_macos` and `dotnet_macos` on the agent itself, plus one Couchbase Server and one Sync Gateway. A platform's Nth
entry in `PLATFORM_VERSIONS` gets that platform's Nth test server in the topology, and test servers no entry asks
for are left out of the run. So one topology covers every combination of the devices it lists, and a new device
only needs adding there.

Tests that need more test servers than the entries give are skipped, like any test whose `min_*` markers the
topology cannot meet.

## Sanity checks

Before anything is provisioned, `setup_multiplatform.py` checks the input against the topology and the build
server, and lists every problem it finds at once:

- each entry names a known platform and a well-formed version;
- the topology has enough test servers of each platform for the entries;
- every CBL version, and the Sync Gateway version, exists on ProGet, and a pinned build is on latestbuilds.

A failed check exits with code 3. The Jenkinsfile then marks the build UNSTABLE rather than FAILED, since the
input, not the product, is at fault.

## Jenkins

`Jenkinsfile` runs on `qe-mac-india`, and takes:

| Parameter | Default | Meaning |
|---|---|---|
| `PLATFORM_VERSIONS` | `swift_ios=4 swift_ios=4` | As above. |
| `SGW_VERSION` | `4` | As above. |
| `TS_DATASET_VERSION` | `auto` | `auto` uses 3.2 if any platform runs CBL 3.x, else 4.0. |
| `TS_TEST_FILTER` | empty | A pytest `-k` expression; empty runs every test. |
| `TOPOLOGY_FILE` | `topology.json` | Topology file in this directory. |
| `RUN_PREBUILD` | true | Prebuild each requested platform and version first. |

Before prebuilding, it rejects a CBL version that cannot replicate with the Sync Gateway version, and stops early
(UNSTABLE) if the topology has too few test servers for the entries. After the run, `teardown.sh` stops the
backend and moves the pytest output into `tests/multiplatform/multiplatform/`, which is archived.

## Files

```
multiplatform/
├── Jenkinsfile                 # Jenkins pipeline
├── test_multiplatform.sh        # Sets up the backend and test servers, then runs pytest in tests/multiplatform
├── setup_multiplatform.py      # Sanity checks, then the shared setup_test() on the test servers used
├── topology.json               # Every test server the agent can reach, and the Sync Gateway backend
├── config_multiplatform.json   # TDK config template
├── teardown.sh                 # Stops the backend and moves the artifacts
└── latest_successful_build.sh  # Standalone lookup of a version's latest build on ProGet
```
