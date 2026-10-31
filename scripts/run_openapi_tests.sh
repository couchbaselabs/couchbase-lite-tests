#!/usr/bin/env bash
#
# Runs the tests marked `openapi` (the REST API conformance tests) on this host: Sync Gateway on
# rosmar, and Edge Server in Docker. No Couchbase Server or Couchbase Lite test server is needed.
#
# Usage:
#   scripts/run_openapi_tests.sh --es-version 1.1.1-0
#   scripts/run_openapi_tests.sh --sgw-only -- -k admin_api
#
# Starting Sync Gateway on rosmar stops the Sync Gateways that this checkout started before.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_DIR="$REPO_ROOT/environment/local"

usage() {
  cat <<EOF
Usage: $0 [options] [-- pytest args]

  --es-version VERSION  Edge Server version, for example 1.1.1-0. Required unless --sgw-only.
  --sgw-only            Run only the Sync Gateway tests.
  --es-only             Run only the Edge Server tests.
  --git-tag TAG         Build Sync Gateway from this tag or branch. By default the script reuses
                        environment/local/sync_gateway, and builds main only if it is missing.
  --keep                Leave Sync Gateway and Edge Server running after the tests.
EOF
}

es_version=""
run_sgw=true
run_es=true
git_tag=""
keep=false
pytest_args=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --es-version)
      [[ $# -ge 2 ]] || {
        usage >&2
        exit 2
      }
      es_version="$2"
      shift 2
      ;;
    --sgw-only)
      run_es=false
      shift
      ;;
    --es-only)
      run_sgw=false
      shift
      ;;
    --git-tag)
      [[ $# -ge 2 ]] || {
        usage >&2
        exit 2
      }
      git_tag="$2"
      shift 2
      ;;
    --keep)
      keep=true
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    --)
      shift
      pytest_args=("$@")
      break
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if ! $run_sgw && ! $run_es; then
  echo "--sgw-only and --es-only cannot be combined." >&2
  exit 2
fi
if $run_es && [[ -z $es_version ]]; then
  echo "--es-version is required unless --sgw-only is set." >&2
  exit 2
fi

cleanup() {
  if $keep; then
    echo "Leaving the servers running. Stop them with:"
    echo "  uv run environment/local/start_edge_server.py --stop"
    echo "  uv run environment/local/start_local.py --stop-sync-gateway"
    return
  fi
  if $run_es; then
    uv run "$LOCAL_DIR/start_edge_server.py" --stop || true
  fi
  uv run "$LOCAL_DIR/start_local.py" --stop-sync-gateway || true
}

if [[ -n $git_tag ]]; then
  sgw_build=(--git-tag "$git_tag")
elif [[ -x $LOCAL_DIR/sync_gateway ]]; then
  sgw_build=(--skip-sync-gateway-build)
else
  sgw_build=(--git-tag main)
fi

cd "$REPO_ROOT"
trap cleanup EXIT

# Edge Server also needs a Sync Gateway config to start from, so Sync Gateway always starts.
uv run "$LOCAL_DIR/start_local.py" --server rosmar --skip-testserver "${sgw_build[@]}"
sgw_config="$(cat "$LOCAL_DIR/topology_config")"
if $run_es; then
  uv run "$LOCAL_DIR/start_edge_server.py" --version "$es_version"
fi

# --rootdir stops pytest from taking its rootdir from the --config path.
status=0
if $run_sgw; then
  (cd tests/dev_e2e && uv run pytest -v --rootdir . -m openapi --config "$sgw_config" ${pytest_args[@]+"${pytest_args[@]}"}) || status=1
fi
if $run_es; then
  (cd tests/QE && uv run pytest -v --rootdir . -m openapi \
    --config "$LOCAL_DIR/edge_server/topology_config.json" ${pytest_args[@]+"${pytest_args[@]}"}) || status=1
fi
exit $status
