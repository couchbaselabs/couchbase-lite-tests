# Couchbase Lite Functional Testing Client

This is the repo for interacting with the 2023 testing server meant for
driving Couchbase Lite.  Tests can be written using this SDK and stored
in this repo, and then run using `pytest`.  In its essence, this is an
HTTP request factory with a lot of telemetry and logging built in to try
to be as accurate as possible about what happened when a test fails.

## How to use

You can see an example in `src/cli.py` (specifically the api() method)
but the basic flow so far is:

1. Create a `CBLPyTest` object
2. Grab the resulting couchbase server, sync gateway, and test server object(s)
3. Use the above API objects to interact with the environment.

## How to build

To build the client, create a venv using python v7-11 (v13 is known incompatible)
Activate the venv and use `pip install -r requirements.txt` to assemble the
required packages.

This module can be installed locally by using `pip install .` from this
directory.  It can be packaged for deployment using `python -m build .`
from this directory.

## How to install (Couchbase internal)

You can install this SDK with the following command: 

`pip install cbltest --extra-index-url https://proget.sc.couchbase.com/pypi/mobile-python/simple`

## Configuration

There is only one required file to configure the SDK, and some optional settings
in addition.  The schema for the required JSON file is hosted at
https://packages.couchbase.com/couchbase-lite/testserver.schema.json.
You can enable autocomplete and validation in IDEs that support it
(such as Visual Studio Code) by including a `$schema` key in your JSON:

```javascript
{
    "$schema": "https://packages.couchbase.com/couchbase-lite/testserver.schema.json",
    ...
}
```

