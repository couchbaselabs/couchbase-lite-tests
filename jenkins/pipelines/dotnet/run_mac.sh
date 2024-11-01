#!/bin/bash -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
pushd $SCRIPT_DIR/../../../servers/dotnet/testserver

app_location=$PWD/bin/Release/net8.0-maccatalyst/testserver.app
if [ -z "$app_location" ]; then
    echo "Unable to find app to run, was it built?"
    exit 1
fi

source $SCRIPT_DIR/prepare_env.sh
banner "Running $app_location"
open $app_location