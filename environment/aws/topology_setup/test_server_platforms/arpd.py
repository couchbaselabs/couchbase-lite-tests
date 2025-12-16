#! /usr/bin/env python3

# NOTE: This is not meant to be used directly by the TDK, but
# rather as a reference to create a helper daemon just to work
# around the fact that there is no reasonable way to discover
# the IP address of an iOS device on the local network.

# To set it up, use the com.couchbase.arpd.plist launchd file
# included in this directory to run this script.  You can do this
# by copying it to the /Library/LaunchDaemons directory and
# running `sudo launchctl load /Library/LaunchDaemons/com.couchbase.arpd.plist`
# after that, there will be a socket open at /var/run/arpd.sock that
# can be used to query for the IP address of a device by its WiFi MAC address.

# PREREQUISITE: This requires a tool called `arping` to be installed.  On macOS,
# you can install it via Homebrew with `brew install arping`.

import grp
import os
import re
import signal
import socket
import subprocess
import sys

SOCK = "/var/run/arpd.sock"
GROUP = "staff"

if os.path.exists(SOCK):
    os.unlink(SOCK)

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.bind(SOCK)

gid = grp.getgrnam(GROUP).gr_gid
os.chown(SOCK, 0, gid)
os.chmod(SOCK, 0o660)

s.listen(1)


def cleanup(*_):
    try:
        os.unlink(SOCK)
    except FileNotFoundError:
        pass
    sys.exit(0)


signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

while True:
    conn, _ = s.accept()
    mac_query = conn.recv(1024).decode().strip()
    p = subprocess.run(["arping", "-c", "1", mac_query], capture_output=True)

    # Extract IP address from the line containing the CIDR
    out = p.stdout.decode(errors="ignore").splitlines()
    ip_addr = ""
    for line in out:
        if mac_query in line:
            m = re.search(r"from\s+(\d{1,3}(?:\.\d{1,3}){3})\s+\(", line)
            if m:
                ip_addr = m.group(1)
                break

    conn.send(ip_addr.encode())
    conn.close()
