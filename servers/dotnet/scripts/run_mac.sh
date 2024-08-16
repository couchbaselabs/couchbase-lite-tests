#!/bin/bash -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
pushd $SCRIPT_DIR/..

app_location=$(find bin/Release/net8.0-maccatalyst -name "*.app")
if [ -z "$app_location" ]; then
    echo "Unable to find app to run, was it built?"
    exit 1
fi

open $app_location