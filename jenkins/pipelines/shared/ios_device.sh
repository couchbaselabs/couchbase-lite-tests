#!/bin/bash

# Check for the optional 'all' argument
output_all=false
if [[ "$1" == "all" ]]; then
    output_all=true
fi

# Get the list of connected devices
device_list=$(xcrun devicectl list devices --hide-default-columns --hide-headers --columns state udid | grep -E 'connected|available')

# Check if there are any connected devices
if [[ -z "$device_list" ]]; then
    exit 0
fi

# Output based on whether 'all' option is provided
if $output_all; then
    # Print all connected UDIDs
    echo "$device_list" | awk '{print $NF}'
else
    # Print only the first connected UDID
    first_connected_udid=$(echo "$device_list" | head -n 1 | awk '{print $NF}')
    echo "$first_connected_udid"
fi