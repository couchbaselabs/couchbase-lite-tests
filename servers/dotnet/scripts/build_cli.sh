#!/bin/bash -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

source $SCRIPT_DIR/prepare_env.sh

install_dotnet

banner "Copying datasets"

mkdir -p $SCRIPT_DIR/../testserver.cli/Resources/
pushd $SCRIPT_DIR/../testserver.cli/Resources/
cp -f $SCRIPT_DIR/../../../dataset/server/dbs/*.zip .
cp -Rf $SCRIPT_DIR/../../../dataset/server/blobs .
popd

pushd $SCRIPT_DIR/../testserver.cli
banner "Executing build for .NET $DOTNET_VERSION CLI"
$DOTNET_ROOT/dotnet publish testserver.cli.csproj -c Release -f net8.0