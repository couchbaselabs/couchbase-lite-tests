#!/bin/bash
# Runs the endpoint script in "$@", under `timeout` when the request sends ?timeout=<seconds>.
# timeout sends SIGTERM to the script's whole process group, then SIGKILL 1s later if it is still running.

if [[ ! "${QUERY_STRING:-}" =~ (^|&)timeout=([0-9]+(\.[0-9]+)?)(&|$) ]]; then
  exec "$@"
fi

SECONDS_ALLOWED="${BASH_REMATCH[2]}"
timeout --kill-after=1 "$SECONDS_ALLOWED" "$@"
STATUS=$?

NAME=$(basename "$1")
if [[ $STATUS -eq 124 ]]; then
  echo "$NAME timed out after ${SECONDS_ALLOWED}s"
elif [[ $STATUS -eq 137 ]]; then
  echo "$NAME was killed by SIGKILL, either because it ignored SIGTERM at the ${SECONDS_ALLOWED}s timeout or from elsewhere"
elif [[ $STATUS -gt 128 ]]; then
  echo "$NAME was killed by signal $((STATUS - 128))"
fi
exit $STATUS
