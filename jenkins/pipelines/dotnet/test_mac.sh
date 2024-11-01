#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source $SCRIPT_DIR/test_common.sh

sgw_url="$4"
if [ $# -lt 3 ]; then
    usage
    exit 1
fi

prepare_dotnet

modify_package $2 $3
$SCRIPT_DIR/build_mac.sh
$SCRIPT_DIR/run_mac.sh
$SCRIPT_DIR/../shared/setup_backend.sh $sgw_url

begin_tests localhost localhost