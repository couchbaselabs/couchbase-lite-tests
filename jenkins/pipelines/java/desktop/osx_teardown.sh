#!/bin/bash
# Clean up after running Java Web Services tests

echo "OSX Desktop: Shutdown the Test Server"
pushd servers/jak/desktop > /dev/null
if [ -f "server.pid" ]; then kill $(cat server.pid); fi
popd > /dev/null

echo "OSX Desktop: Shutdown the environment"
pushd environment > /dev/null
docker compose down
