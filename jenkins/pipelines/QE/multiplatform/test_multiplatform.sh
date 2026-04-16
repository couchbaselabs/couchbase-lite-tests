#!/bin/bash

# Multiplatform CBL test runner
# Usage: ./test_multiplatform.sh "platform1:version1[-build1] platform2:version2[-build2]..." <sgw_version> [test_name] topology-file
# Examples:
#   ./test_multiplatform.sh "android:3.2.3 ios:3.1.5" 3.2.3
#   ./test_multiplatform.sh "android:3.2.3 ios:3.1.5" 3.2.3 "test_delta_sync.py::TestDeltaSync::test_delta_sync_replication"

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
source $SCRIPT_DIR/../../shared/config.sh

function list_available_tests() {
    echo "📋 Available tests (found in $QE_TESTS_DIR):"

    if [ -d "$QE_TESTS_DIR" ]; then
        cd "$QE_TESTS_DIR"

        # Find all test files and extract test methods
        for test_file in test_*.py; do
            if [ -f "$test_file" ]; then
                echo "  📄 $test_file:"
                # Extract class and method names using grep
                grep -n "class Test" "$test_file" 2>/dev/null | while read -r line; do
                    class_name=$(echo "$line" | sed 's/.*class \([^(]*\).*/\1/')
                    echo "    📁 $class_name:"
                    # Find test methods in this class
                    grep -n "def test_" "$test_file" 2>/dev/null | while read -r method_line; do
                        method_name=$(echo "$method_line" | sed 's/.*def \([^(]*\).*/\1/')
                        echo "      🧪 $test_file::$class_name::$method_name"
                    done
                done
                echo ""
            fi
        done
    else
        echo "  ❌ QE tests directory not found: $QE_TESTS_DIR"
    fi
}

function usage() {
    echo "Usage: $0 \"platform1:version1[-build1] platform2:version2[-build2]...\" <sgw_version> [test_name] topology-file"
    echo ""
    echo "Supported platforms: android, ios, dotnet, c, java"
    echo ""
    echo "Examples:"
    echo "  # Auto-fetch latest builds with default test:"
    echo "  $0 \"android:3.2.3 ios:3.1.5\" 3.2.3"
    echo ""
    echo "  # With specific test:"
    echo "  $0 \"android:3.2.3 ios:3.1.5\" 3.2.3 \"test_no_conflicts.py::TestNoConflicts::test_multiple_cbls_updates_concurrently_with_push\""
    echo ""
    echo "  # With explicit builds:"
    echo "  $0 \"android:3.2.3 ios:3.1.5-6\" 3.2.3"
    echo ""
    echo "  # List available tests:"
    echo "  $0 --list-tests"
    echo ""
    echo "Common tests:"
    echo "  - test_delta_sync.py::TestDeltaSync::test_delta_sync_utf8_strings (default)"
    echo "  - test_delta_sync.py::TestDeltaSync::test_delta_sync_replication"
    echo "  - test_no_conflicts.py::TestNoConflicts::test_no_conflicts_basic"
    echo "  - test_replication_eventing.py::TestReplicationEventing::test_replication_eventing"
    echo "  - Or any other pytest test specification"
    exit 1
}

# Handle special flags
if [ $# -eq 1 ] && [ "$1" = "--list-tests" ]; then
    list_available_tests
    exit 0
fi

if [ $# -lt 2 ] || [ $# -gt 4 ]; then
    usage
fi

PLATFORM_CONFIGS="$1"
SG_VERSION="$2"
TEST_NAME="${3:-test_delta_sync.py::TestDeltaSync::test_delta_sync_replication}"
TOPOLOGY_FILE="$SCRIPT_DIR/${4:-topology.json}"

# Validate inputs
if [ -z "$PLATFORM_CONFIGS" ]; then
    echo "❌ Error: Platform configurations cannot be empty"
    usage
fi

if [ -z "$SG_VERSION" ]; then
    echo "❌ Error: SG version cannot be empty"
    usage
fi

if [ ! -f "$TOPOLOGY_FILE" ]; then
    echo "❌ Error: Topology file not found: $TOPOLOGY_FILE"
    exit 1
fi

echo "🚀 MULTIPLATFORM CBL TEST SETUP"
echo "==============================="
echo "📋 Platform configurations: $PLATFORM_CONFIGS"
echo "🔄 SG version: $SG_VERSION"
echo "🧪 Test: $TEST_NAME"
echo " Topology: $TOPOLOGY_FILE"

# Parse platform configurations
IFS=' ' read -ra PLATFORM_ARRAY <<< "$PLATFORM_CONFIGS"
UNIQUE_PLATFORMS=()
PLATFORM_VERSIONS=()
PLATFORM_BUILDS=()

for config in "${PLATFORM_ARRAY[@]}"; do
    IFS=':' read -ra CONFIG_PARTS <<< "$config"

    if [ ${#CONFIG_PARTS[@]} -lt 2 ]; then
        echo "❌ Error: Invalid platform configuration: $config"
        echo "   Expected format: platform:version[-build] or platform:os:version[-build]"
        exit 1
    fi

    platform="${CONFIG_PARTS[0]}"

    # Handle multi-OS platforms (dotnet, c) that can have format: platform:os:version[-build]
    if [ ${#CONFIG_PARTS[@]} -eq 3 ] && [[ "$platform" == "dotnet" || "$platform" == "c" ]]; then
        # Format: platform:os:version[-build]
        target_os="${CONFIG_PARTS[1]}"
        version_with_build="${CONFIG_PARTS[2]}"
    else
        # Format: platform:version[-build]
        target_os=""
        version_with_build="${CONFIG_PARTS[1]}"
    fi

    # Parse version and build from version_with_build (format: version-build or just version)
    if [[ "$version_with_build" == *"-"* ]]; then
        version="${version_with_build%-*}"  # Extract version part (everything before last dash)
        build="${version_with_build##*-}"  # Extract build part (everything after last dash)
    else
        version="$version_with_build"
        build=""
    fi

    # Validate platform
    case "$platform" in
        android|ios|dotnet|c|java)
            ;;
        *)
            echo "❌ Error: Unsupported platform: $platform"
            echo "   Supported platforms: android, ios, dotnet, c, java"
            exit 1
            ;;
    esac

    UNIQUE_PLATFORMS+=("$platform")
    PLATFORM_VERSIONS+=("$version")
    PLATFORM_BUILDS+=("$build")
done

echo "Platforms to setup: ${UNIQUE_PLATFORMS[*]}"
echo ""

# Phase 1: Setup all platforms using centralized multiplatform setup
echo "🔧 PHASE 1: SETTING UP CBL TEST SERVERS"
echo "======================================="
echo "org.gradle.java.home=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home" >> $SCRIPT_DIR/../../../../servers/jak/android/gradle.properties
echo "🏗️ Using centralized multiplatform setup..."
cd "$SCRIPT_DIR"

# Use the centralized multiplatform setup script
echo "🚀 Running multiplatform setup..."
uv run setup_multiplatform.py "$PLATFORM_CONFIGS" "$SG_VERSION" "$TOPOLOGY_FILE" --setup-only
SETUP_SUCCESS=$?

if [ $SETUP_SUCCESS -ne 0 ]; then
    echo "💥 SETUP PHASE FAILED!"
    echo "Multiplatform setup script failed. Check the logs above for details."
    exit 1
fi

echo ""
echo "✅ ALL PLATFORMS SETUP COMPLETED!"
echo ""

# Phase 2: Run the coordinated test
echo "🧪 PHASE 2: RUNNING COORDINATED TEST"
echo "==================================="
echo "🎯 Test: $TEST_NAME"
echo ""

# Run tests following the same pattern as individual platform scripts
echo "🏃 Running coordinated test across all platforms..."
echo "========== PYTEST OUTPUT START =========="

pushd "${QE_TESTS_DIR}" > /dev/null

# Set environment variables to prevent output truncation
export COLUMNS=200

if uv run pytest -v --no-header -W ignore::DeprecationWarning --config config.json "$TEST_NAME"; then
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
echo "📋 Platform Summary:"
for platform in "${UNIQUE_PLATFORMS[@]}"; do
    case "$platform" in
        android) echo "🤖 Android: CBL test server running" ;;
        ios) echo "🍎 iOS: CBL test server running" ;;
        dotnet) echo "🔷 .NET: CBL test server running" ;;
        c) echo "⚙️ C: CBL test server running" ;;
        java) echo "☕ Java: CBL test server running" ;;
    esac
done

echo ""
echo "💡 Tip: All CBL test servers are still running for debugging if needed."
echo "💡 Check http_log/ and testserver.log for detailed test execution logs."

exit $TEST_RESULT
