#!/bin/bash
# Clean up after running Java Web Services tests

echo "Shutdown Environment"
pushd environment > /dev/null
docker compose down

