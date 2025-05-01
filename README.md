# couchbase-lite-tests

This is the Couchbase Lite System Test Harness.  It runs the
system tests (tests requiring more than one device, e.g., a
Couchbase Lite instance and a Sync Gateway) needed to verify
a Couchbase Lite release.

The system consists of 4 components:

* An environment, built with docker compose, that contains one Couchbase Server and one Sync Gateway.
* The "client", a  test harness written in python, that can configure the environment, run tests, and reports their results
* The tests, also written in python.  Test are run within the client.  They use it to configure the environment and then instruct servers to run tests in that environment.
* Per-platform "servers".  The tests use the client instruct the server to run a specific test

## What's here

* README.md - this file
* client - A python framework that configures the environment, runs tests and reports their results
* dataset - A collection datasets used in tests.  Each dataset appears in two formats, as a cblite2 db, and as raw JSON
* environment - Scripts and such for setting up and tearing down a backend environment
* jenkins - The jenkins pipelines and the docker compose for running the Jenkins server.
* servers - A test server for each CBL platform.  Servers run on their platform and accept instructions from the client to run tests
* spec - Documentation:  The specification for this system.
* tests - The python codelets that are run in the client to configure an environment and then instruct connected servers to run a test in that environment.

## Running tests

### Requirements

1. [Docker](https://www.docker.com/get-started)
2. [Python 3.10+](https://www.python.org/downloads)
3. [OpenSSL 1.1 for CBS Python SDK](https://docs.couchbase.com/python-sdk/current/hello-world/start-using-sdk.html)
4. [Git LFS](https://git-lfs.com)

### Steps

1. Clone the repository.
   ```
   $ git clone https://github.com/couchbaselabs/couchbase-lite-tests.git
   ```
   This repository uses Git LFS to store binary dataset files. Ensure that you have [Git LFS](https://git-lfs.com) installed, and run `git lfs install` once to setup the extension hook before cloning the repository.

2. From the jenkins/pipelines directory of your choice, run the relevant script (such as run_test.ps1, test.sh, etc) with the various arguments regarding versions of things to use.

### Contributing

Notice that this repo has a .pre-commit-config.yaml file, which means it is ready to use with the [pre-commit](https://pre-commit.com/#intro) python tool.  Essentially, after you clone this repo you should run 

```
pip install pre-commit
pre-commit install
```

After that git pre-commit validation will check various things for you to ensure adherence to best practices and standards.