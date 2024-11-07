#!/bin/bash
# Clean up after running Android tests

# try to kill the test server
adb uninstall com.couchbase.lite.android.mobiletest 2 >& 1 > /dev/null || true

echo "Shutdown Environment"
pushd environment > /dev/null
docker compose down

# kill logcat
logcat_pid=$(cat logcat.pid)
if [ -n "$logcat_pid" ]; then
   kill $logcat_pid
fi

# just in case the last attempt failed
adb uninstall com.couchbase.lite.android.mobiletest 2 >& 1 > /dev/null || true

