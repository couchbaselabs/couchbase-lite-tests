# LogSlurp server

This is a server that is meant to be like a slightly improved version of netcat.  It is capable of session scoped logging from multiple sources simultaneously, with facilities to then retrieve the resulting consolidated log.

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

## Building

There is a [Dockerfile](./LogSlurp/Dockerfile) that can be used to build an image for this server to be deployed as a service.  The resulting image will be bound to port 8180 (which can be forwarded to any host port with docker commands).

Alternatively, if the dotnet SDK is installed, building locally with `dotnet run` will run this service locally bound to port 5186.

## ClientLogger

There is also a console application in this repo called [ClientLogger](./ClientLogger/) which can be used to quickly test the server.  It will need to be edited to change the port based on whether the server is running locally or in Docker, but once that is done the program can also be run with `dotnet run`.  A message will appear requesting input text.  All input text is sent to the logging server, and when "quit" is typed the logs are fetched from the server as they would appear if a program tried to download them.

Example output:

> \>dotnet run<br />
Begin typing (type quit to quit)<br />
hello<br />
world<br />
quit<br />
<br />
==== Retrieved ====<br />
ClientLogger: hello<br />
ClientLogger: world