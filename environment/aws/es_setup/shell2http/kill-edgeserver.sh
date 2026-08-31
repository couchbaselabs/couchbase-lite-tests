#!/bin/bash

# Stop Edge Server and do not return until it has let go of its listening port.
#
# Returning mid-shutdown means the next /start-edgeserver races it and dies with
# "Address already in use", stranding the host for every test that follows.

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

# The RPM installs a systemd unit and starts it, so on a freshly provisioned host
# Edge Server is service-managed: signalling its process just makes systemd spawn
# another one and the port never frees. The service has to be stopped first. After
# provisioning the tests run Edge Server by hand with setsid, which systemd knows
# nothing about, so the signal escalation below is still needed.
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
