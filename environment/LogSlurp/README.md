# LogSlurp server

This is a server that is meant to be like a slightly improved version of netcat.  It is capable of session scoped logging from multiple sources simultaneously, with facilities to then retrieve the resulting consolidated log.  The server works on a simple concept of creating a logging session, allowing multiple sources to write to the log, and then allowing the combined log to be retrieved.  The steps are as follows:

1. Start a new log session
2. Open a new log stream specifying the session you want to interact with, and a tag to identify the entity logging
3. Write log messages to the stream
4. Close all streams of the session
5. Finish the log session
6. Retrieve the log

The server will write messages to the log in the following format:

`{tag}: {timestamp} {message}`

The timestamp is generated on the server, to keep the log timestamp flow consistent, so logging a timestamp in the message on the client side is discouraged.

## Endpoints

### startNewLog

`HTTP POST` request with no body.  Begins a new logging session.  Returns the ID of the session for future use in other calls in the following format:

```
{
    "log_id": "<id>"
}
```

### openLogStream

`HTTP GET` and must be a websocket connection, or a 400 is returned.  Starts a connection for logging to the specified ID.  Uses the following headers:

```
CBL-Log-ID: <id from startNewLog>
CBL-Log-Tag: <identifier for the logging device>
```

`CBL-Log-ID` is required or a 400 is returned.  `CBL-Log-Tag` is optional but highly recommended.  After the connection is established, all text messages on the connection will be recorded in the log.

### finishLog

`HTTP POST` request to finish the logging session and free resources.  It uses the following _required_ header:

```
CBL-Log-ID: <id from startNewLog>
```

Note that the log is still retrievable after this call is made.

### retrieveLog

`HTTP GET` request to pull the consolidated log from the session.  It uses the following _required_ header.

```
CBL-Log-ID: <id from startNewLog>
```

## Use in the E2E Test environment

The expected use case for the log slurper looks like this:

- The Python test client creates a new (probably random) session id.
- The test client calls the slurper `/startNewLog` endpoint supplying the session id.  If the call is successful, the slurper is now awating logs for the new session
- The test client creates a unique 'tag' for each device involved in the test session. This tag will, essentially, name the device, during the logging session
- The test client notifies each device of the session id and the tag by which the device will identify itself.  For the TestServers, this is a call to /newSession

```
{
    "id": <session id>
    "logging": {
        "url": <logslurper hostname:port>  // note that this is NOT a url
        "tag": <device tag>                // as described above: the "name" of the device, for this session
    }
}
```

- Test devices open a websocket connection to the slurper:

```
GET ws://<slurper hostname:port>/openLogStream
CBL-Log-ID: <sessionId>
CBL-Log-Tag: <tag>
```

- If this call succeeds, test devices can log by sending simple text messages down the websocket connection
- At some point, presumeably the end of a test session, the python test client calls `/finishLog`
- In response to the call to `/finishLog`, the slurper will close all websocket connections for that session, and will refuse any new ones

## Building

There is a [Dockerfile](./LogSlurp/Dockerfile) that can be used to build an image for this server to be deployed as a service.  The resulting image will be bound to port 8180 (which can be forwarded to any host port with docker commands).

Alternatively, if the dotnet SDK is installed, building locally with `dotnet run` will run this service locally bound to port 5186.

## ClientLogger

There is also a console application in this repo called [ClientLogger](./ClientLogger/) which can be used to quickly test the server.  It will need to be edited to change the port based on whether the server is running locally or in Docker, but once that is done the program can also be run with `dotnet run`.  A message will appear requesting input text.  All input text is sent to the logging server, and when "quit" is typed the logs are fetched from the server as they would appear if a program tried to download them.

Example output:

> \> dotnet run<br />
Begin typing (type quit to quit)<br />
hello<br />
quit<br />
<br />
==== Retrieved ====<br />
ClientLogger: 2024-08-12 23:33:34,147 hello

The client logger can be used to test the implementation of a logger.  Do this:
- Start the log slurper
- Start the client logger.  It will print the id of the session it started with the slurper
- When the client logger loops asking for log messages let it sit
- Run your logger implementation. Use the session id from the client logger and an arbitrary "tag"
- Log a few things from your implementation.  Maybe type a couple of log messages at the client logger as well
- When you have enough logs to validate your implementation, type "quit" at the client logger
- The client logger will display the contents of the session, including the log messages you typed at it, along with the ones sent from your logger implementation, interleaved approprately.

