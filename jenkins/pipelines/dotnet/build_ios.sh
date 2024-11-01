#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
source $SCRIPT_DIR/prepare_env.sh

banner "Executing build for .NET $DOTNET_VERSION iOS"

export DEVELOPER_DIR="/Applications/Xcode-16.1.0.app/"
export MD_APPLE_SDK_ROOT=$DEVELOPER_DIR
pushd $SCRIPT_DIR/../../../servers/dotnet/testserver
security unlock-keychain -p $KEYCHAIN_PASSWORD
$HOME/.dotnet/dotnet build -f net$DOTNET_VERSION-ios -c Release -p:RuntimeIdentifier=ios-arm64 -v n
