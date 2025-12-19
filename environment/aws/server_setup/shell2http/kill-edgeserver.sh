#!/bin/bash

PID=$(ps -ax | grep [e]dge-server | awk '{print $1}')
if [[ "$PID" == "" ]]; then
    echo "Running process not found"
    exit 0
fi

kill -SIGHUP $PID
