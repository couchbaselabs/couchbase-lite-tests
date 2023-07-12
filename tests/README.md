## For Python Tests

Alright!  If you want to start playing around with running the python tests
here is some info for you:

Standard python stuff:

* python -m venv venv
* source venv/bin/activate
* pip install -r requirements.txt

Make sure to use python between v3.7 and 3.10.  NOT 3.11

After that there are two ways you can install the test framework into the tests
folder for consumption.  Either:

`pip install ../client`

which builds it from "source", or installing it from proget

`pip install cbltest --extra-index-url https://proget.sc.couchbase.com/pypi/mobile-python/simple`

There are three tests in this folder corresponding to the first three
tests in the 001-basic-replication.md spec. They are not entirely complete
but do actually test something.  If you want to run all three you will need
to make sure that there is at least 1 GiB of RAM available for the server
cluster during config since the tests will create 2 512 MiB buckets.
(The first test uses the `names` bucket and the second two use `travel`).
I created an "example" config file, which is likely to  be the one we will use
for our tests.  It is called `config.example.json`.

The command, once you've started the environment from the tests folder is:

`pytest --config config.example.json test_basic_replication.py -k <test_name>`

Or leave off the -k to run all tests in that file.  For every http request that
the framework directly issues, it will log the request and the response in a
folder called http_logs. This will help follow the conversation of the test.
Also full debug level logging from the framework will be written to the
testserver.log file.  The console level logging is controlled by the
`--cbl-log-level` argument to pytest (`--log-level` was already taken).

There are a few more arguments that pytest will understand that are specific to
this test framework but they are not relevant at the moment (they are in the
spec).

I learned a lot about the way that python works through this process.  The
"build" is still a bunch of python source files but setup in such a way so that
it knows that it is good to go as-is with a given python version or version(s).

This framework is pure python so it runs anywhere, but the couchbase python sdk
is built on top of C++ so it needs to restrict versions.  If you try to install
on a version that is not "built" for it will fall back to building from source,
which can be complicated as I found out during the couchbase python sdk build
