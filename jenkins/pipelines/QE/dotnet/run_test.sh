function usage() {
    echo "Usage: $0 <version> <platform> <sgw_version> [options]"
    echo "  version:      CBL version (e.g. 3.2.1-2)"
    echo "  platform:     The .NET platform to build (e.g. ios)"
    echo "  sgw_version:  Version of Sync Gateway to download and use"
    echo "  --dataset-version <ver>  Version of CBL dataset to use (default: 4.0)"
    echo "  --test-name <expr>       pytest -k expression, or a test path "
    echo "  --setup-only             Only build test server and setup backend, skip tests"
    exit 1
}

if [ $# -lt 3 ]; then usage; fi

cbl_version="$1"
platform="$2"
sgw_version="$3"
shift 3

SETUP_ONLY=false
DATASET_VERSION="4.0"
TEST_NAME=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dataset-version) DATASET_VERSION="${2:-}"; shift 2 ;;
        --test-name)       TEST_NAME="${2:-}";       shift 2 ;;
        --setup-only)      SETUP_ONLY=true;          shift   ;;
        "")                shift ;;   # tolerate empty args from Jenkins interpolation
        *) echo "Unknown option: $1"; usage ;;
    esac
done
[ -n "$DATASET_VERSION" ] || DATASET_VERSION="4.0"

pushd "$QE_TESTS_DIR" > /dev/null

export DEVELOPER_DIR="/Applications/Xcode-$DOTNET_XCODE_VERSION.app/"

PYTEST_ARGS=(
    -v --no-header
    -W ignore::DeprecationWarning
    --config config.json
    --dataset-version "$DATASET_VERSION"
    -m cbl
)

if [ -n "$TEST_NAME" ]; then
    if [[ "$TEST_NAME" == *".py"* ]]; then
        PYTEST_ARGS+=("$TEST_NAME")        # path
    else
        PYTEST_ARGS+=(-k "$TEST_NAME")     # keyword expression
    fi
fi

echo "pytest ${PYTEST_ARGS[*]}"
set +e
uv run pytest "${PYTEST_ARGS[@]}"
PYTEST_RC=$?
set -e
popd > /dev/null

if [ "$PYTEST_RC" -eq 5 ]; then
    echo "ERROR: no tests collected. TEST_NAME='${TEST_NAME}' matched nothing under -m cbl."
elif [ "$PYTEST_RC" -eq 4 ]; then
    echo "ERROR: pytest usage error. Check the expression: '${TEST_NAME}'"
fi
exit $PYTEST_RC