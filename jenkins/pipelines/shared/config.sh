# This file should be sourced at the beginning of testing and teardown scripts

function create_venv() {
    if [ $# -lt 1 ]; then
        echo "Invalid call to create_venv()"
        exit 1
    fi

    PYTHON_VERSION=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
    REQUIRED_VERSION="${2:-3.10}"

    pip install uv
    uv venv --python $REQUIRED_VERSION $1
}

find_dir() {
    local dir=$(realpath $(dirname "$0"))
    while [ "$dir" != "/" ]; do
        if [ -d "$dir/$1" ]; then
            echo "$dir/$1"
            return 0
        fi
        dir=$(dirname "$dir")
    done
    echo "Error: '$1' directory not found in any parent directories." >&2
    return 1
}

print_box() {
    local content="$1"
    local title="$2"

    local max_length=$(echo "$content" | wc -L)
    local border=$(printf '%*s' $((max_length + 4)) | tr ' ' '-')

    local title_padding=$(( (max_length - ${#title}) / 2 ))
    printf "%*s%s\n" $((title_padding)) "" "$title"

    echo "$border"
    echo "$content" | while IFS= read -r line; do
        printf "| %-*s |\n" "$max_length" "$line"
    done
    echo "$border"
}

readonly PIPELINES_DIR=$(find_dir pipelines) || exit 1
readonly TESTS_DIR=$(find_dir tests) || exit 1
readonly ENVIRONMENT_DIR=$(find_dir environment) || exit 1
readonly TEST_SERVER_DIR=$(find_dir servers) || exit 1

readonly SHARED_PIPELINES_DIR="$PIPELINES_DIR/shared"
readonly DEV_E2E_PIPELINES_DIR="$PIPELINES_DIR/dev_e2e"
readonly DEV_E2E_TESTS_DIR="$TESTS_DIR/dev_e2e"
readonly QE_TESTS_DIR="$TESTS_DIR/QE"
readonly QE_PIPELINES_DIR="$PIPELINES_DIR/QE"
readonly AWS_ENVIRONMENT_DIR="$ENVIRONMENT_DIR/aws"

export PIPELINES_DIR TESTS_DIR ENVIRONMENT_DIR TEST_SERVER_DIR
export SHARED_PIPELINES_DIR DEV_E2E_PIPELINES_DIR DEV_E2E_TESTS_DIR AWS_ENVIRONMENT_DIR

content="PIPELINES_DIR: $PIPELINES_DIR
TESTS_DIR: $TESTS_DIR
ENVIRONMENT_DIR: $ENVIRONMENT_DIR
TEST_SERVER_DIR: $TEST_SERVER_DIR
SHARED_PIPELINES_DIR: $SHARED_PIPELINES_DIR
DEV_E2E_PIPELINES_DIR: $DEV_E2E_PIPELINES_DIR
DEV_E2E_TESTS_DIR: $DEV_E2E_TESTS_DIR
QE_TESTS_DIR: $QE_TESTS_DIR
QE_PIPELINES_DIR: $QE_PIPELINES_DIR
AWS_ENVIRONMENT_DIR: $AWS_ENVIRONMENT_DIR"

print_box "$content" "Defining the following values:"

unset -f find_dir
unset -f print_box
unset content