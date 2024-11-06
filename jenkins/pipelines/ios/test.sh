#!/bin/bash -e

EDITION=${1}
VERSION=${2}
BLD_NUM=${3}
SGW_URL=${4}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
SHARED_DIR="${SCRIPT_DIR}/../shared"
TEST_SERVER_DIR="${SCRIPT_DIR}/../../../servers/ios"
TESTS_DIR="${SCRIPT_DIR}/../../../tests"

# Find a connected iOS device:
DEVICE_UDID="$("${SHARED_DIR}/ios_device.sh")"
if [[ -z "${DEVICE_UDID}" ]]; then
    echo "No connected device found." && exit 1
else
    echo "Connected device found: ${DEVICE_UDID}"
fi

# Build Test Server App:
echo "Build Test Server App"
pushd "${TEST_SERVER_DIR}" > /dev/null
./scripts/build.sh device ${EDITION} ${VERSION} ${BLD_NUM}

# Install and run Test Server App:
echo "Run Test Server"
"${SHARED_DIR}/ios_app.sh" start "${DEVICE_UDID}" "./build/TestServer-iOS.app"
popd > /dev/null

# Start Environment :
echo "Start environment"
"${SHARED_DIR}/setup_backend.sh" "${SGW_URL}"

# Run Tests :
echo "Run tests"
pushd "${TESTS_DIR}"
python3.10 -m venv venv
. venv/bin/activate
pip install -r requirements.txt

rm -f "config.ios.json" || true
cp "${SCRIPT_DIR}/config.ios.json" .
pytest -v --no-header -W ignore::DeprecationWarning --config config.ios.json
deactivate
popd
