#!/bin/bash -e

echo "Shutdown Test Server"
if [ -d "servers/c/build/out/bin" ]; then
    pushd servers/c/build/out/bin > /dev/null
    ios kill com.couchbase.CBLTestServer || true
    popd > /dev/null
fi

echo "Shutdown Environment"
pushd environment > /dev/null
docker compose logs cbl-test-sg > cbl-test-sg.log
docker compose down
popd > /dev/null
