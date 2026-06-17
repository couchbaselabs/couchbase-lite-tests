#!/bin/bash
# Run dev_e2e pytest for React Native Jenkins pipelines.
#
# If a previous run left failed tests (recorded in .rn_failed_tests_<platform>.txt
# or discoverable from junit/log artifacts in the workspace), only those tests run.
# Otherwise the full suite runs with --maxfail=7. Failures are saved for the next build.
#
# Usage (from reactnative_{ios,android}/test.sh, after pushd to DEV_E2E_TESTS_DIR):
#   run_rn_dev_e2e_pytest.sh ios|android

set -uo pipefail

RN_PLATFORM="${1:?platform required: ios or android}"
COLLECT_SCRIPT="${SHARED_PIPELINES_DIR}/collect_failed_pytest_tests.py"
FAILED_LIST="${DEV_E2E_TESTS_DIR}/.rn_failed_tests_${RN_PLATFORM}.txt"
JUNIT="${DEV_E2E_TESTS_DIR}/junit_${RN_PLATFORM}.xml"
PYTEST_LOG="${DEV_E2E_TESTS_DIR}/pytest_${RN_PLATFORM}.log"

PYTEST_COMMON=(
    -v
    -W ignore::DeprecationWarning
    --config config.json
    --dataset-version "${DATASET_VERSION}"
    --ignore=test_multipeer.py
    -k "not listener and not multipeer and not custom_conflict"
    --tb=short
    --timeout=300
    --junitxml="${JUNIT}"
)

run_pytest() {
    uv run pytest "$@" "${PYTEST_COMMON[@]}" 2>&1 | tee "${PYTEST_LOG}"
    return "${PIPESTATUS[0]}"
}

save_failed_tests() {
    uv run python "${COLLECT_SCRIPT}" --junit "${JUNIT}" --log "${PYTEST_LOG}" \
        > "${FAILED_LIST}.new" || true
    if [ -s "${FAILED_LIST}.new" ]; then
        mv "${FAILED_LIST}.new" "${FAILED_LIST}"
        echo "Recorded $(wc -l < "${FAILED_LIST}" | tr -d ' ') failed test(s) for the next build:"
        cat "${FAILED_LIST}"
    else
        rm -f "${FAILED_LIST}.new"
    fi
}

discover_failed_tests_from_artifacts() {
    local repo_root
    repo_root="$(cd "${DEV_E2E_TESTS_DIR}/.." && pwd)"
    local lastfailed="${repo_root}/.pytest_cache/v/cache/lastfailed"
    local candidates=(
        "${JUNIT}"
        "${DEV_E2E_TESTS_DIR}/junit_result.xml"
        "${PYTEST_LOG}"
    )
    local junit_arg="" log_arg=""
    for path in "${candidates[@]}"; do
        if [ -f "${path}" ]; then
            case "${path}" in
                *.xml) junit_arg="${path}" ;;
                *) log_arg="${path}" ;;
            esac
        fi
    done
    local lastfailed_arg=""
    if [ -f "${lastfailed}" ]; then
        lastfailed_arg="${lastfailed}"
    fi
    if [ -n "${junit_arg}" ] || [ -n "${log_arg}" ] || [ -n "${lastfailed_arg}" ]; then
        uv run python "${COLLECT_SCRIPT}" \
            ${junit_arg:+--junit "${junit_arg}"} \
            ${log_arg:+--log "${log_arg}"} \
            ${lastfailed_arg:+--lastfailed "${lastfailed_arg}"} \
            > "${FAILED_LIST}.discovered" 2>/dev/null || true
        if [ -s "${FAILED_LIST}.discovered" ]; then
            mv "${FAILED_LIST}.discovered" "${FAILED_LIST}"
        else
            rm -f "${FAILED_LIST}.discovered"
        fi
    fi
}

if [ ! -f "${FAILED_LIST}" ] || [ ! -s "${FAILED_LIST}" ]; then
    discover_failed_tests_from_artifacts
fi

if [ -f "${FAILED_LIST}" ] && [ -s "${FAILED_LIST}" ]; then
    echo "=== Re-running $(wc -l < "${FAILED_LIST}" | tr -d ' ') failed test(s) from previous run ==="
    cat "${FAILED_LIST}"
    mapfile -t FAILED_TESTS < "${FAILED_LIST}"
    set +e
    run_pytest "${FAILED_TESTS[@]}"
    EXIT=$?
    set -e
else
    echo "=== Running full dev_e2e suite ==="
    set +e
    run_pytest --maxfail=7
    EXIT=$?
    set -e
fi

if [ "${EXIT}" -ne 0 ]; then
    save_failed_tests
    exit "${EXIT}"
fi

rm -f "${FAILED_LIST}"
echo "All tests passed; cleared failed-test list for the next build"
exit 0
