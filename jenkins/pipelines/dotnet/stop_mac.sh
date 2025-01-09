#!/bin/bash

server_pid=$(ps -ax | grep testserver.app | grep -v grep | head -1 | awk '{print $1}')
if [ -z "$server_pid" ]; then
    echo "test server process not found to kill!"
    exit 1
fi

kill $server_pid