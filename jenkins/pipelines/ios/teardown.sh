#!/bin/bash -e

echo "Shutdown Test Server"
if [ -d "servers/ios/build" ]; then
    pushd servers/ios/build > /dev/null
    ios kill com.couchbase.CBLTestServer-iOS || true
    popd > /dev/null
fi

echo "Shutdown Environment"
pushd environment > /dev/null
docker compose logs cbl-test-sg > cbl-test-sg.log
docker compose down
popd > /dev/null
