#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

source $SCRIPT_DIR/test_common.sh
source $SCRIPT_DIR/prepare_env.sh

banner "Shutdown Test Server for Mac Catalyst"
$SCRIPT_DIR/stop_mac.sh

banner "Shutdown Environment"
end_tests