#!/bin/bash

if [ "$#" -lt 3 ]; then
    echo "Usage: $0 <ACTION>  <DEVICE_UDID> <APP_PATH_OR_BUNDLE_ID>"
    echo "Actions:" 
    echo "  start <DEVICE_UDID> <APP-PATH> : Install and launch the app"
    echo "  stop <DEVICE_UDID> <APP-BUNDLE-ID>  : Terminate the app"
    exit 1
fi

ACTION=${1}
UDID=${2}
APP_OR_BUNDLE_ID=${3}

# Function to get the app's executable path based on the bundle ID
get_exe_path() {
    local DEVICE_UDID=${1}
    local BUNDLE_ID=${2}
    APP_PATH_OUTPUT=$(xcrun devicectl device info apps --device "${DEVICE_UDID}" --bundle-id "${BUNDLE_ID}" --hide-headers --hide-default-columns --columns path)

    # Extract the line after "Apps installed:"
    local EXE_PATH
    EXE_PATH=$(echo "${APP_PATH_OUTPUT}" | awk '/Apps installed:/{getline; print}')
    echo "${EXE_PATH}"
}

# Function to get the PID of the running app based on the app path
get_pid() {
    local DEVICE_UDID=${1}
    local APP_PATH=${2}
    local PID
    PID=$(xcrun devicectl device info processes --device "${DEVICE_UDID}" | grep "${APP_PATH}" | awk '{print $1}')
    echo "${PID}"
}

# Start action: install and launch the app
if [ "${ACTION}" == "start" ]; then
    # The second parameter is the app path
    APP_PATH=${APP_OR_BUNDLE_ID}

    # Get the absolute path of APP_PATH
    APP_PATH=$(realpath "${APP_PATH}")

    # Get the app's bundle identifier
    BUNDLE_ID=$(defaults read "${APP_PATH}/Info.plist" CFBundleIdentifier)
    if [ -z "${BUNDLE_ID}" ]; then
        echo "Failed to read CFBundleIdentifier from ${APP_PATH}."
        exit 1
    fi

    # Install the app on the connected device
    echo "Installing the app..."
    xcrun devicectl device install app --device "${UDID}" "${APP_PATH}"

    # Launch the app
    echo "Launching the app with bundle ID: ${BUNDLE_ID}..."
    xcrun devicectl device process launch --device "${UDID}" "${BUNDLE_ID}"

# Stop action: terminate the app
elif [ "${ACTION}" == "stop" ]; then
    # The second parameter is the app bundle ID
    BUNDLE_ID=${APP_OR_BUNDLE_ID}

    # Get the app's path to find its PID
    EXE_PATH=$(get_exe_path "${UDID}" "${BUNDLE_ID}")
    if [ -z "${EXE_PATH}" ]; then
        echo "App is not installed on the device. Nothing to terminate"
        exit 0
    fi

    # Terminate the app if it's running
    PID=$(get_pid "${UDID}" "${EXE_PATH}")
    if [ -n "${PID}" ]; then
        echo "Terminating the app with PID: ${PID}..."
        xcrun devicectl device process terminate --device "${UDID}" --pid "${PID}"
    else
        echo "App is not running. Nothing to terminate."
    fi

else
    echo "Invalid action."
    exit 1
fi