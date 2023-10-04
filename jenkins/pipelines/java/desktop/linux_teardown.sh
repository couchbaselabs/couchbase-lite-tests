#!/bin/bash
# Clean up after running Java Web Services tests

echo "Kill the test server"
pushd servers/jak/desktop > /dev/null
if [ -f "server.pid" ]; then kill `cat server.pid`; fi
rm -rf server.url server.pid
popd > /dev/null

echo "Shutdown Environment"
pushd environment > /dev/null
docker compose down

