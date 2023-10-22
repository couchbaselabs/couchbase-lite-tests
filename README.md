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
* environment - The docker compose script that creates and runs the environment
* jenkins - The jenkins pipelines and the docker compose for running the Jenkins server.
* servers - A test server for each CBL platform.  Servers run on their platform and accept instructions from the client to run tests
* spec - Documentation:  The specification for this system.
* tests - The python codelets that are run in the client to configure an environment and then instruct connected servers to run a test in that environment.

## Running tests

### Requirements

1. [Docker](https://www.docker.com/get-started)
2. [Python 3.7 - 3.10](https://www.python.org/downloads)
3. [OpenSSL 1.1 for CBS Python SDK](https://docs.couchbase.com/python-sdk/current/hello-world/start-using-sdk.html)

### Steps

1. Open a terminal window and start the environment by running the `./start_environment.py` script in the environment folder.
   The script will start CBS and SG in the docker container in the background and wait until SG is successfully started before exiting.
   ```
   cd environment
   ./start_environment.py
   ```
   
2. Build and run the test server of the platform that you want to test.
   * [C](https://github.com/couchbaselabs/couchbase-lite-tests/tree/main/servers/c)
   * Android
   * .Net
   * iOS
     
3. From the tests directory, set up a python virtual environment:
   ```
   cd tests
   python3 -m venv venv
   . venv/bin/activate
   pip install -r requirements.txt
   ```
   * You may need to use `python<version>` command e.g. `python3.10` if you already have `python3` for the other version.
   * You only need to create the python venv once. To reactivate run `. venv/bin/activate`, and to deactivate run `deactivate`.
   * When you update the repo or the Python TDK code, run `pip install ../client` to update the TDK.

4. Edit the file `config.example.json` with the URL of your Test server started in the Step 2.
   ```
   "test-servers": ["http://192.168.100.104:8080"]
   ```
5. Run the pytest tests as examples below.
   ```
   # Run one test file:
   pytest --config config.example.json test_basic_replication.py

   # Run all tests:
   pytest --config config.example.json

   # Run all with detail and without deprecation warning:
   pytest -v --no-header -W ignore::DeprecationWarning --config config.example.json
   ```
