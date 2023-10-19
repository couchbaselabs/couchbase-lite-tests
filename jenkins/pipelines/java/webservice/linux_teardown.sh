#!/bin/bash
# Clean up after running Java Web Services tests

echo "Kill the test server"
pushd servers/jak/webservice > /dev/null
./gradlew appStop || true
rm -rf server.url server.pid
popd > /dev/null

echo "Shutdown Environment"
pushd environment > /dev/null
docker compose down

