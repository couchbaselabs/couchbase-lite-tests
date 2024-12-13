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
    if [ $# -ne 1 ]; then
        echo "No version provided to copy_datasets!"
        exit 1
    fi

    banner "Copying dataset resources v$1"

    mkdir -p $SCRIPT_DIR/../../../servers/dotnet/testserver/Resources/Raw
    pushd $SCRIPT_DIR/../../../servers/dotnet/testserver/Resources/Raw
    cp -fv $SCRIPT_DIR/../../../dataset/server/dbs/$1/*.zip .
    cp -Rfv $SCRIPT_DIR/../../../dataset/server/blobs .
    popd
}