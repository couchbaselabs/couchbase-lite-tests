# This file should be sourced at the beginning of testing and teardown scripts

function move_artifacts() {
  if [ -z "${TS_ARTIFACTS_DIR:-}" ]; then
    echo "Warning: TS_ARTIFACTS_DIR environment variable is not set. Artifacts will not be moved."
    return
  fi

  # Determine the suite's tests dir from the CALLING script's path
  # (${BASH_SOURCE[1]} = the teardown.sh that invoked this), NOT from the
  # current working directory. Teardown scripts pushd into environment/aws
  # before calling this, so pwd is unreliable and would always fall through
  # to dev_e2e -- silently skipping QE artifacts. The caller path always
  # lives under /QE/ or /dev_e2e/. An explicit dir may also be passed as $1.
  local src_dir="${1:-}"
  if [ -z "$src_dir" ]; then
    if [[ "${BASH_SOURCE[1]:-}" == *"/QE/"* ]]; then
      src_dir="$QE_TESTS_DIR"
    else
      src_dir="$DEV_E2E_TESTS_DIR"
    fi
  fi

  local dst_dir="$src_dir/$TS_ARTIFACTS_DIR"

  echo "Moving artifacts to $dst_dir"

  # The workspace persists across builds, so stale artifacts (e.g. an old
  # http_log dir referencing IPs from a prior run) would otherwise linger
  # alongside this build's output.
  rm -rf "$dst_dir"
  mkdir -p "$dst_dir"
  mv "$src_dir/session.log" "$dst_dir/session.log" || true
  # session.log is the full LogSlurp DEBUG aggregate and can reach ~100 MB,
  # which stalls the Jenkins artifact download behind the reverse proxy.
  # Compress it (text → ~10x smaller) so it stays downloadable; browsers and
  # curl fetch the .gz fine and it decompresses with gunzip/`zless`.
  # Compression must never abort teardown -- a failure here would skip
  # stop_backend and leak EC2 instances -- so keep the raw log and continue.
  if [ -f "$dst_dir/session.log" ]; then
    gzip -f "$dst_dir/session.log" ||
      echo "Warning: failed to gzip session.log; leaving it uncompressed"
  fi
  mv "$src_dir/http_log" "$dst_dir/http_log" || true
  # Include the JUnit XML so each platform's results are preserved per
  # artifacts dir in a multi-pipeline (matrix) build.
  mv "$src_dir/junit_result.xml" "$dst_dir/junit_result.xml" || true
  # SGW diagnostics downloaded by run_sgcollects() (via --sgcollect-on-test-failure)
  # into the pytest cwd when a test fails; moving them here gets them archived
  # (and later purged) by Jenkins retention. Files are named
  # "<safe_host>-sgcollectinfo-*.zip" (see SyncGateway.run_sgcollect() in
  # cbltest). Purge zips left by earlier builds first — the workspace
  # persists and zips have unique names, so they'd accumulate into every
  # build's archive.
  rm -f "$dst_dir"/*-sgcollectinfo-*.zip
  mv "$src_dir"/*-sgcollectinfo-*.zip "$dst_dir/" 2>/dev/null || true
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

  local title_padding=$(((max_length - ${#title}) / 2))
  printf "%*s%s\n" $((title_padding)) "" "$title"

  echo "$border"
  echo "$content" | while IFS= read -r line; do
    printf "| %-*s |\n" "$max_length" "$line"
  done
  echo "$border"
}

# Colored, timed section banners for Jenkins console output (rendered by the
# ansiColor('xterm') pipeline option; the raw escape codes are harmless on a
# plain terminal too). Usage: section_start "$COLOR_CYAN" "INFRA SETUP" ...
# work... ; the next section_start call (or script exit, via the EXIT trap
# below) closes the previous section and prints how long it took.
readonly COLOR_RESET='\033[0m'
readonly COLOR_CYAN='\033[1;36m'
readonly COLOR_YELLOW='\033[1;33m'
readonly COLOR_GREEN='\033[1;32m'

_section_color=""
_section_label=""
_section_start_ts=""

_format_duration() {
  local total=$1 h m s
  h=$((total / 3600))
  m=$(((total % 3600) / 60))
  s=$((total % 60))
  if [ "$h" -gt 0 ]; then
    printf '%dh%dm%ds' "$h" "$m" "$s"
  elif [ "$m" -gt 0 ]; then
    printf '%dm%ds' "$m" "$s"
  else
    printf '%ds' "$s"
  fi
}

# Closes whichever section is currently open (no-op if none is). Registered
# as an EXIT trap so the closing banner -- and the duration -- still prints
# even if the section's work fails (set -e / the caller's ERR trap exits the
# script from inside the section), not just on a clean finish.
_section_close() {
  [ -z "$_section_label" ] && return 0
  local end_ts
  end_ts=$(date +%s)
  echo -e "${_section_color}=== ${_section_label} END (took $(_format_duration $((end_ts - _section_start_ts)))) ===${COLOR_RESET}"
  _section_label=""
}

section_start() {
  _section_close
  _section_color="$1"
  _section_label="$2"
  _section_start_ts=$(date +%s)
  echo -e "${_section_color}=== ${_section_label} START ===${COLOR_RESET}"
}

trap _section_close EXIT

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
