#!/bin/bash
# Clean up after running Java Web Services tests

echo "Linux Web Service: Shutdown the Test Server"
pushd servers/jak/webservice > /dev/null
./gradlew appStop > /dev/null 2>&1 || true
popd > /dev/null

echo "Linux Web Service: Shutdown the environment"
pushd environment > /dev/null
docker compose down
