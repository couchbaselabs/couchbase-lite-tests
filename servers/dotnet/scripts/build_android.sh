#!/bin/bash -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

source $SCRIPT_DIR/prepare_env.sh

banner "Executing build for .NET $DOTNET_VERSION Android"

pushd $SCRIPT_DIR/..
$HOME/.dotnet/dotnet publish -f net$DOTNET_VERSION-android
