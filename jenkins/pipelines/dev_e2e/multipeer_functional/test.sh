#!/bin/bash -e

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

dataset_version="4.0"
setup_args=()
# Get arguments for pytest, and send the rest to setup_test
while [[ $# -gt 0 ]]; do
    case "$1" in
        --*)
            if [[ "$1" == "--dataset-version" ]]; then
                dataset_version="$2"
            else
                setup_args+=("$1" "$2")
            fi
            shift 2
            ;;
        *)
            echo "Unknown argument: $1"
            exit 1
            ;;
    esac
done

# Phase 1: Setup all platforms using centralized multiplatform setup
echo "🔧 PHASE 1: SETTING UP CBL TEST SERVERS"
echo "======================================="
cd "$SCRIPT_DIR"

# Create virtual environment for setup
create_venv venv
source venv/bin/activate
uv pip install -r $AWS_ENVIRONMENT_DIR/requirements.txt

# Use the centralized multiplatform setup script
echo "🚀 Running setup..."
python3 setup_test.py "${setup_args[@]}"
SETUP_SUCCESS=$?
deactivate

if [ $SETUP_SUCCESS -ne 0 ]; then
    echo "💥 SETUP PHASE FAILED!"
    echo "Setup script failed. Check the logs above for details."
    exit 1
fi

echo ""
echo "✅ ALL PLATFORMS SETUP COMPLETED!"
echo ""

# Phase 2: Run the coordinated test
echo "🧪 PHASE 2: RUNNING MULTIPEER FUNCTIONAL TESTS"
echo "========== PYTEST OUTPUT START =========="

pushd "${DEV_E2E_TESTS_DIR}" > /dev/null
create_venv venv
source venv/bin/activate
uv pip install -r requirements.txt

if pytest -v --no-header --config config.json --dataset-version=$dataset_version test_multipeer.py; then
    echo "========== PYTEST OUTPUT END =========="
    echo ""
    echo "🎉 COORDINATED TEST PASSED!"
    TEST_RESULT=0
else
    echo "========== PYTEST OUTPUT END =========="
    echo ""
    echo "💥 COORDINATED TEST FAILED!"
    TEST_RESULT=1
fi

deactivate
popd > /dev/null

# Final results
echo ""
echo "📊 MULTIPLATFORM TEST RESULTS:"
echo "================================"
echo "🔧 Setup Phase: ✅ SUCCESS (All platforms ready)"

if [ $TEST_RESULT -eq 0 ]; then
    echo "🧪 Test Phase: ✅ SUCCESS"
    echo ""
    echo "🎉 MULTIPLATFORM TEST COMPLETED SUCCESSFULLY!"
    echo "All CBL test servers are running and the coordinated test passed."
else
    echo "🧪 Test Phase: ❌ FAILED"
    echo ""
    echo "💥 MULTIPLATFORM TEST FAILED!"
    echo "CBL test servers are running but the coordinated test failed."
fi

echo ""
echo "💡 Tip: All CBL test servers are still running for debugging if needed."
echo "💡 Check http_log/ and testserver.log for detailed test execution logs."

exit $TEST_RESULT 