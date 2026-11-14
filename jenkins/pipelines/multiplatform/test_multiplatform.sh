#!/bin/bash

# Multiplatform CBL test runner
# Usage: ./test_multiplatform.sh "<platform>=<version> ..." <sgw_version> [--topology-file FILE]
#          [--dataset-version VERSION] [--stress] [--test-filter EXPR] [--setup-only]
# Runs every test in tests/multiplatform (all need more than one test server) unless --test-filter narrows it.
# With --stress it runs only the stress tests (tests/multiplatform/stress), with the backend they need.
# Examples:
#   ./test_multiplatform.sh "swift_ios=4.1.0 jak_android=4.1.0" 4.1.0
#   ./test_multiplatform.sh "swift_ios=4.1.0 dotnet_macos=4.1.0-18" 4.1.0 --test-filter test_delta_sync_replication

trap 'echo "$BASH_COMMAND (line $LINENO) failed, exiting..."; exit 1' ERR
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
source "$SCRIPT_DIR"/../shared/config.sh

function list_available_tests() {
  echo "📋 Available tests (found in $MULTIPLATFORM_TESTS_DIR):"

  if [ -d "$MULTIPLATFORM_TESTS_DIR" ]; then
    cd "$MULTIPLATFORM_TESTS_DIR"

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
    echo "  ❌ Multi-platform tests directory not found: $MULTIPLATFORM_TESTS_DIR"
  fi
}

function usage() {
  echo "Usage: $0 \"<platform>=<version> ...\" <sgw_version> [--topology-file FILE] [--dataset-version VERSION] [--stress] [--test-filter EXPR] [--setup-only]"
  echo "  <platform>=<version>: A test server platform (e.g. swift_ios, jak_android, dotnet_macos, c_windows)"
  echo "      and the CBL version to run on it: \"4\", \"4.1.0\" or \"4.1.0-18\". Each entry uses one test server of"
  echo "      that platform, in topology order; test servers left over are not used."
  echo "  <sgw_version>: Sync Gateway version to be deployed for the test."
  echo "  --topology-file: Topology file in $SCRIPT_DIR (default: topology.json)"
  echo "  --dataset-version: Version of CBL dataset to use (default: 4.0)"
  echo "  --stress: Run only the stress tests in tests/multiplatform/stress, which take over a day"
  echo "  --test-filter: An optional pytest -k filter expression"
  echo "  --setup-only: Only setup the test servers and backend, skip test execution"
  echo "  --list-tests: List the tests in tests/multiplatform and exit"
  exit 1
}

# Handle special flags
if [ $# -eq 1 ] && [ "$1" = "--list-tests" ]; then
  list_available_tests
  exit 0
fi

if [ "$#" -lt 2 ]; then usage; fi

PLATFORM_VERSIONS="$1"
SGW_VERSION="$2"
shift 2

# An empty --topology-file or --dataset-version (a blank Jenkins parameter) keeps these defaults.
TOPOLOGY_FILE="topology.json"
DATASET_VERSION="4.0"
STRESS=false
TEST_FILTER=""
SETUP_ONLY=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --topology-file)
      TOPOLOGY_FILE="${2:-$TOPOLOGY_FILE}"
      shift 2
      ;;
    --dataset-version)
      DATASET_VERSION="${2:-$DATASET_VERSION}"
      shift 2
      ;;
    --stress)
      STRESS=true
      shift
      ;;
    --test-filter)
      TEST_FILTER="$2"
      shift 2
      ;;
    --setup-only)
      SETUP_ONLY=true
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      ;;
  esac
done

section_start "$COLOR_CYAN" "INFRA SETUP"
# The Android test server is only built here when it is not downloaded. Add the JDK setting once, as the workspace
# (and so this file) persists across builds.
GRADLE_JAVA_HOME="org.gradle.java.home=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home"
GRADLE_PROPERTIES="$TEST_SERVER_DIR/jak/android/gradle.properties"
grep -qxF "$GRADLE_JAVA_HOME" "$GRADLE_PROPERTIES" || echo "$GRADLE_JAVA_HOME" >>"$GRADLE_PROPERTIES"
pushd "$SCRIPT_DIR" >/dev/null
# setup_multiplatform.py first checks the platform versions, the Sync Gateway version and the topology, logging
# every problem. Its exit code is passed on as is (bypassing the ERR trap's exit 1), so that the Jenkinsfile can
# tell a failed sanity check (SANITY_CHECK_EXIT_CODE, 3) from any other failure.
SETUP_STATUS=0
SETUP_ARGS=("$PLATFORM_VERSIONS" "$SGW_VERSION" "$TOPOLOGY_FILE" --setup-only)
if [ "$STRESS" = true ]; then SETUP_ARGS+=(--stress); fi
uv run setup_multiplatform.py "${SETUP_ARGS[@]}" || SETUP_STATUS=$?
if [ "$SETUP_STATUS" -ne 0 ]; then exit "$SETUP_STATUS"; fi
popd >/dev/null
section_end

# Exit early if setup-only mode
if [ "$SETUP_ONLY" = true ]; then
  echo "Setup completed. Exiting due to --setup-only flag."
  exit 0
fi

section_start "$COLOR_YELLOW" "RUN TESTS"
pushd "$MULTIPLATFORM_TESTS_DIR" >/dev/null
# Set environment variables to prevent output truncation
export COLUMNS=200
PYTEST_ARGS=(
  -v --no-header -W ignore::DeprecationWarning --config config.json
  --sgcollect-on-test-failure
  --cbcollect-on-test-failure
  --dataset-version "$DATASET_VERSION"
)
if [ "$STRESS" = true ]; then
  PYTEST_ARGS+=(--stress)
fi
if [ -n "$TEST_FILTER" ]; then
  PYTEST_ARGS+=(-k "$TEST_FILTER" --no-result-upload)
fi
uv run pytest "${PYTEST_ARGS[@]}"
popd >/dev/null
section_end
