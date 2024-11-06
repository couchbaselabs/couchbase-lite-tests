#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/prepare_env.sh

banner "Executing build for .NET $DOTNET_VERSION iOS"

pushd $SCRIPT_DIR/../../../servers/dotnet/testserver
$HOME/.dotnet/dotnet build -f net$DOTNET_VERSION-ios -c Release -p:RuntimeIdentifier=ios-arm64 -v n
