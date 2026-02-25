# Couchbase Lite Functional Testing Client

This is the repo for interacting with the 2023 testing server meant for
driving Couchbase Lite.  Tests can be written using this SDK and stored
in this repo, and then run using `pytest`.  In its essence, this is an
HTTP request factory with a lot of telemetry and logging built in to try
to be as accurate as possible about what happened when a test fails.

## How to use

You can see many examples in the tests directory in the root of this repo.  As long
as you run them with `uv run` then this module automatically gets built and installed.

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

