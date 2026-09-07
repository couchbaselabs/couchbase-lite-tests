#!/bin/bash

# Stop Edge Server and do not return until it has let go of its listening port, so that
# the next /start-edgeserver does not race it.

ES_BIN="/opt/couchbase-edge-server/bin/couchbase-edge-server"
CONFIG="/opt/couchbase-edge-server/etc/config.json"
WAIT_PER_SIGNAL=20 # x 0.5s

# The port comes from the config the server was started on, since a test is free to
# configure any port it likes.
PORT="$(jq -r '(.interface // "0.0.0.0:59840") | split(":") | last' "$CONFIG" 2>/dev/null)"
if [[ -z "$PORT" || "$PORT" == "null" ]]; then
  PORT=59840
fi

es_pids() {
  pgrep -f "$ES_BIN" || true
}

port_busy() {
  [[ -n "$(sudo ss -ltnH "sport = :$PORT" 2>/dev/null)" ]]
}

stopped() {
  [[ -z "$(es_pids)" ]] && ! port_busy
}

# Stop the packaged service, if the RPM installed one. Tests run Edge Server by hand, so
# the signal escalation below covers that case.
if systemctl cat couchbase-edge-server.service >/dev/null 2>&1; then
  sudo systemctl stop couchbase-edge-server.service >/dev/null 2>&1 || true
fi

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
