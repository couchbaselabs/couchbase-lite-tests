# This file should be sourced at the beginning of testing and teardown scripts

function move_artifacts() {
    if [ -z "${TS_ARTIFACTS_DIR:-}" ]; then
        echo "Warning: TS_ARTIFACTS_DIR environment variable is not set. Artifacts will not be moved."
        return
    fi

    # Determine if we're in dev_e2e or QE based on current directory
    local current_dir=$(pwd)
    if [[ "$current_dir" == *"/dev_e2e"* ]]; then
        local src_dir=$(realpath $(dirname "${BASH_SOURCE[0]}")/../../../tests/dev_e2e)
    elif [[ "$current_dir" == *"/QE"* ]]; then
        local src_dir=$(realpath $(dirname "${BASH_SOURCE[0]}")/../../../tests/QE)
    else
        # Fallback: try to detect from the directory structure
        local script_dir=$(dirname "${BASH_SOURCE[0]}")
        if [[ "$script_dir" == *"/QE/"* ]]; then
            local src_dir=$(realpath $(dirname "${BASH_SOURCE[0]}")/../../../tests/QE)
        else
            local src_dir=$(realpath $(dirname "${BASH_SOURCE[0]}")/../../../tests/dev_e2e)
        fi
    fi
    
    local dst_dir="$src_dir/$TS_ARTIFACTS_DIR"

    echo "Moving artifacts to $dst_dir"

    mkdir -p "$dst_dir"
    mv "$src_dir/session.log" "$dst_dir/session.log" || true
    mv "$src_dir/http_log" "$dst_dir/http_log" || true
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

    local max_length=$(echo "$content" | awk '{ if (length > max) max = length } END { print max }')
    local border=$(printf '%*s' $((max_length + 4)) | tr ' ' '-')

    local title_padding=$(( (max_length - ${#title}) / 2 ))
    printf "%*s%s\n" $((title_padding)) "" "$title"

    echo "$border"
    echo "$content" | while IFS= read -r line; do
        printf "| %-*s |\n" "$max_length" "$line"
    done
    echo "$border"
}

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    if [[ -f $HOME/.local/bin/env ]]; then
        # Irritatingly sometimes uv doesn't create this file
        # but in that case we don't need it anyway
        source $HOME/.local/bin/env
    fi
fi

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