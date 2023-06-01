# Couchbase Lite Functional Testing Client

This is the repo for interacting with the 2023 testing server meant for driving Couchbase Lite.  Tests can be written using this SDK and stored in this repo, and then run using `pytest`.  In its essence, this is an HTTP request factory with a lot of telemetry and logging built in to try to be as accurate as possible about what happened when a test fails.

## How to use

You can see an example in `src/cli.py` bu the basic flow so far is:

1. Create a `CBLPyTest` object
2. Grab the resulting request factory
3. Make and send requests to the remote server

## How to build

This module can be installed locally by using `pip install .` from this directory.  It can be packaged for deployment using `python -m build .` from this directory.

## Configuration

There is only one required file to configure the SDK, and some optional settings in addition

```json
{
    // Required
    // The addresses of the running test servers
    "test-servers": ["address[:port]", "address[:port]"],

    // The addresses of the running sync gateways
    "sync-gateways": ["address[:port]", "address[:port]"],

    // The addresses of the running couchbase servers
    "couchbase-servers":["address[:port]", "address[:port]"],

    // The API version to conform to when creating requests
    "api-version": 1,

    // Optional
    // The certs to use to connect to TLS sync gateways
    "sync-gateways-tls-certs": ["filename", "filename"],

    // The greenboard config to use to upload results (not yet implemented)
    "greenboard": {
        "url": "address[:port]",
        "username": "username",
        "password": "password"
    }
}
```

