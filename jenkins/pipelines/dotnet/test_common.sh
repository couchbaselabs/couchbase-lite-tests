#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

function usage() {
    echo "Usage: $0 <edition> <version> <build> [sgw_url]"
    echo "edition: enterprise or community (currently unused)"
    echo "version: CBL version (e.g. 3.2.1)"
    echo "build: CBL build number"
    echo "sgw_url: URL of Sync Gateway to download and use"
}

function prepare_dotnet() {
    source $SCRIPT_DIR/prepare_env.sh
    install_dotnet
    install_maui
    install_xharness
    copy_datasets
}

function modify_package() {
    nuget_package_ver="$1-b$(printf %04d $2)"
    $HOME/.dotnet/dotnet add $SCRIPT_DIR/../../../servers/dotnet/testserver.logic/testserver.logic.csproj package couchbase.lite.enterprise --version $nuget_package_ver
}

function begin_tests() {
    if [ $# -ne 2 ]; then
        echo "Incorrect number of args to begin_tests"
        exit 5
    fi

    pushd $SCRIPT_DIR/../../../tests
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    sed "s/{{test-server-ip}}/$1/g" $SCRIPT_DIR/config.json | sed "s/{{test-client-ip}}/$2/g" > config.json
    pytest -v --no-header --config config.json
    deactivate
}

function end_tests() {
    pushd $SCRIPT_DIR/../../../environment
    docker compose down
    popd
}