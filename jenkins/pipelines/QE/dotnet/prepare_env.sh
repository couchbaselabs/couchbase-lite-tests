#!/bin/bash -e

export PATH="/opt/homebrew/bin:/opt/homebrew/opt/util-linux/bin:$PATH"
export DOTNET_ROOT=$HOME/.dotnet9
export DOTNET_SDK_VERSION="9.0.3xx"
export DOTNET_RUNTIME_VERSION="8.0"
export DOTNET_XCODE_VERSION="26.4.1"

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

PREPARE_DOTNET_SCRIPT="$SCRIPT_DIR/prepare_dotnet.sh"

if [ ! -f $PREPARE_DOTNET_SCRIPT ]; then
    echo "Downloading prepare_dotnet.sh..."
    curl -L https://raw.githubusercontent.com/couchbaselabs/couchbase-mobile-tools/refs/heads/master/dotnet_testing_env/prepare_dotnet_new.sh -o $PREPARE_DOTNET_SCRIPT
fi

source $PREPARE_DOTNET_SCRIPT