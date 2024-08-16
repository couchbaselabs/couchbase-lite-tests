#!/bin/bash -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

source $SCRIPT_DIR/prepare_env.sh

banner "Executing build for .NET $DOTNET_VERSION Mac Catalyst..."

pushd $SCRIPT_DIR/..
$HOME/.dotnet/dotnet builc -f net$DOTNET_VERSION-maccatalyst -c Release