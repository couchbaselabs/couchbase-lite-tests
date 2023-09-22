#!/bin/bash
# Clean up after running Android tests

# try to kill the test server
adb uninstall com.couchbase.lite.android.mobiletest 2 >& 1 > /dev/null || true

echo "Shutdown Environment"
pushd environment > /dev/null
docker compose down

# just in case the last attempt failed
adb uninstall com.couchbase.lite.android.mobiletest 2 >& 1 > /dev/null || true

