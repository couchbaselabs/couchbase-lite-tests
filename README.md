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

1. [Python 3.10+](https://www.python.org/downloads)
2. [OpenSSL 1.1 for CBS Python SDK](https://docs.couchbase.com/python-sdk/current/hello-world/start-using-sdk.html)
3. [Git LFS](https://git-lfs.com)

### Environment Configuration

The tests use a configuration JSON file to get information about the environment in which they are running. As you might notice, there is a [JSON Schema](https://packages.couchbase.com/couchbase-lite/testserver.schema.json) for it, so that will tell you more about the structure.  Here is an example.

```json
{
  "$schema": "https://packages.couchbase.com/couchbase-lite/testserver.schema.json",
  "api-version": 1,
  "test-servers": [
    {
      "url": "http://<url1>:8080"
    },
    {
      "url": "http://<url2>:8080"
    }
  ],
  "couchbase-servers": [
    {
      "hostname": "<url3>"
    }
  ],
  "sync-gateways": [
    {
      "hostname": "<url4>"
    }
  ]
}
```

This particular example indicates that there are two test servers running, along with one Sync Gateway and a Couchbase Server at the URLs provided.  Normally you don't write this file yourself, but rather generate it using [the orchestrator](environment/aws/README.md).

### Steps for Running Tests Only (i.e. I want to act like Jenkins)

1. Clone the repository.
   ```
   $ git clone https://github.com/couchbaselabs/couchbase-lite-tests.git
   ```
   This repository uses Git LFS to store binary dataset files. Ensure that you have [Git LFS](https://git-lfs.com) installed, and run `git lfs install` once to setup the extension hook before cloning the repository.

2. Complete the prerequisites in [the orchestrator](environment/aws/README.md).

3. From the jenkins/pipelines directory of your choice, run the relevant script (such as run_test.ps1, test.sh, etc) with the various arguments regarding versions of things to use.

### Steps for Running Test Diagnostically (i.e. I want to act like a developer triaging an issue)

1. Complete the prerequisites in [the orchestrator](environment/aws/README.md).

2. Create a topology file and set up your backend environment (refer to the same README as 1)

3. Using pytest, run the test you are interested in running (repeat as many times as you'd like)

4. Tip: You can access SGW logs by sending http requests to port 20000 on that machine (http://<ec2-address>:20000/sg_debug.log for example)

5. Tip: If you have LogSlurp enabled, session.log will appear after a normal session finish containing the logs of all test servers and the TDK client interlaced.

### Contributing

Notice that this repo has a .pre-commit-config.yaml file, which means it is ready to use with the [pre-commit](https://pre-commit.com/#intro) python tool.  Essentially, after you clone this repo you should run 

```
pip install pre-commit
pre-commit install
```

After that git pre-commit validation will check various things for you to ensure adherence to best practices and standards.
