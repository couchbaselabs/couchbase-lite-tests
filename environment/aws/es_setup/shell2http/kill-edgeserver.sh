#!/bin/bash

# Stop Edge Server and do not return until it has actually let go of its
# listening port.
#
# Returning while the process is still shutting down means the next
# /start-edgeserver races it and dies with "Address already in use", which
# strands the host for every test that follows. So this escalates
# SIGHUP -> SIGTERM -> SIGKILL and only returns once no edge-server process
# remains and the port is free.

ES_BIN="/opt/couchbase-edge-server/bin/couchbase-edge-server"
PORT="${ES_PORT:-59840}"
WAIT_PER_SIGNAL=20 # x 0.5s

es_pids() {
  pgrep -f "$ES_BIN" || true
}

port_busy() {
  [[ -n "$(sudo ss -ltnH "sport = :$PORT" 2>/dev/null)" ]]
}

stopped() {
  [[ -z "$(es_pids)" ]] && ! port_busy
}

if stopped; then
  echo "Running process not found"
  exit 0
fi

for sig in HUP TERM KILL; do
  pids="$(es_pids)"
  if [[ -n "$pids" ]]; then
    # shellcheck disable=SC2086 # deliberate word splitting: one signal, many pids
    sudo kill -"$sig" $pids 2>/dev/null
  fi

  for _ in $(seq 1 "$WAIT_PER_SIGNAL"); do
    if stopped; then
      echo "Edge server stopped"
      exit 0
    fi
    sleep 0.5
  done

  echo "Edge server still holding port $PORT after SIG$sig, escalating"
done

echo "Edge server did not stop: port $PORT still in use by pid(s) $(es_pids)"
exit 1
