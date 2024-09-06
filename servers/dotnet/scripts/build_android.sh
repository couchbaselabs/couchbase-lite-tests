#!/bin/bash -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

source $SCRIPT_DIR/prepare_env.sh

install_dotnet
install_maui
copy_datasets

banner "Executing build for .NET $DOTNET_VERSION Android"

pushd $SCRIPT_DIR/../testserver
$HOME/.dotnet/dotnet publish -f net$DOTNET_VERSION-android
