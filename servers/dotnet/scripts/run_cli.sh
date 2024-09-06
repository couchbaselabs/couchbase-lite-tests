#!/bin/bash -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

source $SCRIPT_DIR/prepare_env.sh

$SCRIPT_DIR/../testserver.cli/bin/Release/net$DOTNET_VERSION/publish/testserver.cli &