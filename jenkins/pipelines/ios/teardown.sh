#!/bin/bash -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
SHARED_DIR="${SCRIPT_DIR}/../shared"

DEVICE_UDID="$("${SHARED_DIR}/ios_device.sh")"
if [[ -n "${DEVICE_UDID}" ]]; then
    echo "Device Found: ${DEVICE_UDID}"
    echo "Shutdown Test Server"
    "${SHARED_DIR}/ios_app.sh" stop "${DEVICE_UDID}" "com.couchbase.CBLTestServer-iOS"
fi

echo "Shutdown Environment"
pushd environment > /dev/null
docker compose logs cbl-test-sg > cbl-test-sg.log
docker compose down
popd > /dev/null
