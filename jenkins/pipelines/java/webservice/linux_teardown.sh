#!/bin/bash
# Clean up after running Java Web Services tests

echo "Kill the test server"
pushd servers/jak/webservice > /dev/null
./gradlew appStop > /dev/null 2>&1 || true
rm -rf app/server.url
popd > /dev/null

echo "Shutdown Environment"
pushd environment > /dev/null
docker compose down

