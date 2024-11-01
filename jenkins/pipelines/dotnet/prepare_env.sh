#!/bin/bash -e

export DOTNET_ROOT=$HOME/.dotnet
export DOTNET_VERSION="8.0"
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

PREPARE_DOTNET_SCRIPT="$SCRIPT_DIR/prepare_dotnet.sh"

if [ ! -f $PREPARE_DOTNET_SCRIPT ]; then
    echo "Downloading prepare_dotnet.sh..."
    curl -L https://raw.githubusercontent.com/couchbaselabs/couchbase-mobile-tools/refs/heads/master/dotnet_testing_env/prepare_dotnet_new.sh -o $PREPARE_DOTNET_SCRIPT
fi

source $PREPARE_DOTNET_SCRIPT

function copy_datasets() {
    banner "Copying dataset resources"

    mkdir -p $SCRIPT_DIR/../../../servers/dotnet/testserver/Resources/Raw
    pushd $SCRIPT_DIR/../../../servers/dotnet/testserver/Resources/Raw
    cp -fv $SCRIPT_DIR/../../../dataset/server/dbs/*.zip .
    cp -Rfv $SCRIPT_DIR/../../../dataset/server/blobs .
    popd
}