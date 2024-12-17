#!/bin/bash -e

EDITION=${1}
CBL_VERSION=${2}
CBL_BLD_NUM=${3}
CBL_DATASET_VERSION=${4}
SGW_URL=${4}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
SHARED_DIR="${SCRIPT_DIR}/../shared"
TEST_SERVER_DIR="${SCRIPT_DIR}/../../../servers/ios"
TESTS_DIR="${SCRIPT_DIR}/../../../tests"

# Find a connected iOS device:
DEVICE_UDID="$("${SHARED_DIR}/ios_device.sh")"
if [[ -z "${DEVICE_UDID}" ]]; then
    echo "No iOS device found." && exit 1
else
    echo "iOS Device: ${DEVICE_UDID}"
fi

# Build Test Server App:
echo "Build Test Server App"
pushd "${TEST_SERVER_DIR}" > /dev/null
./scripts/build.sh device ${EDITION} ${CBL_VERSION} ${CBL_BLD_NUM} ${CBL_DATASET_VERSION}

# Install and run Test Server App:
echo "Run Test Server"
"${SHARED_DIR}/ios_app.sh" start "${DEVICE_UDID}" "./build/TestServer-iOS.app"
popd > /dev/null

# Start Environment:
echo "Start environment"
"${SHARED_DIR}/setup_backend.sh" "${SGW_URL}"

# Run Tests :
echo "Run tests..."

# Find Test Server IP:
TEST_SERVER_IP=$(dns-sd -t 1 -B _testserver._tcp | tail -1 | awk '{gsub(/-/, ".",  $7)} {print $7}')
if [[ -z "${TEST_SERVER_IP}" ]]; then
    echo "Cannot find Test Server IP" && exit 1
else
    echo "Test Server IP: ${TEST_SERVER_IP}"
fi

# Find Test Client IP:
TEST_CLIENT_IP=$(ifconfig en0 | grep "inet " | awk '{print $2}')
if [[ -z "${TEST_CLIENT_IP}" ]]; then
    echo "Cannot find Test Server IP" && exit 1
else
    echo "Test Client IP: ${TEST_CLIENT_IP}"
fi

pushd "${TESTS_DIR}" > /dev/null
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
sed "s/{{test-server-ip}}/${TEST_SERVER_IP}/g" $SCRIPT_DIR/config.json | sed "s/{{test-client-ip}}/${TEST_CLIENT_IP}/g" > config.json
pytest -v --no-header -W ignore::DeprecationWarning --config config.json
deactivate
popd > /dev/null
