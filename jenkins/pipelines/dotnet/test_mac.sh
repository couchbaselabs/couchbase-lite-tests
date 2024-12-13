#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source $SCRIPT_DIR/test_common.sh

if [ $# -lt 3 ]; then
    usage
    exit 1
fi

cbl_version=$1
cbl_build=$2
dataset_version=$3
sgw_url="$4"

prepare_dotnet $dataset_version

modify_package $cbl_version $cbl_build
$SCRIPT_DIR/build_mac.sh
$SCRIPT_DIR/run_mac.sh
$SCRIPT_DIR/../shared/setup_backend.sh $sgw_url

begin_tests localhost localhost