#!/bin/bash -e

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

# Phase 1: Setup all platforms using centralized multiplatform setup
echo "🔧 PHASE 1: SETTING UP CBL TEST SERVERS"
echo "======================================="
cd "$SCRIPT_DIR"

# Use the centralized multiplatform setup script
echo "🚀 Running setup..."
uv run --project $AWS_ENVIRONMENT_DIR/pyproject.toml setup_test.py $@
SETUP_SUCCESS=$?

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

if uv run pytest -v --no-header --config config.json test_multipeer.py; then
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