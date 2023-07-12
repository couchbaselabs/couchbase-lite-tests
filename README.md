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
* servers - A test server for each CBL platform.  Servers run on their platform and accept instructions from the client to run tests
* spec - Documentation:  The specification for this system.
* tests - The python codelets that are run in the client to configure an environment and then instruct connected servers to run a test in that environment.

## Running tests

You will need more than one terminal window.

In the first, from the `docker` folder, start the environment:

'docker compose up'

Wait until the Sync Gateway is up and stable.  Leave that window to monitor the
SGW log.

From a new window, start a server.  This will probably entail building a server
application for your favorite device, installing it, and running it.  Once it is
running it should tell you its URL.  You will need this in a moment.

Next, from the tests directory, set up a python environment:

```
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

Tests run inside the test client framework.  You will have to install the client
to run the tests.  The easiest way to do this is to install the test client
image from Proget.

```
pip install cbltest --extra-index-url https://proget.sc.couchbase.com/pypi/mobile-python/simple
```

This should work fine, as long as you aren't changing the client code (if you
are, there are instructions on how to build the test client from source, in
`test/README.md`)

Edit the file `config.example.json` so that the value of the key "test-servers"
is a JSON array containing the URL of your server (started above).  E.g.:

```
"test-servers": ["http://192.168.100.104:8080"]
```

You should now be able to run all of the tests in one of the test files
(test\_basic_replication.py in this example) like this:

```
pytest --config config.example.json test_basic_replication.py
```


