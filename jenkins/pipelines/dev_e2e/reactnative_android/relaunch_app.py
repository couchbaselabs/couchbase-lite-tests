#!/usr/bin/env python3
"""Re-launch the React Native test server app right before pytest starts.

setup_test.py installs the APK and does an initial launch which warms up ART
optimisation and JS-bundle compilation on the device.  By the time pytest
starts, the app may have exhausted its built-in reconnect attempts against
port 8765 (which is not yet bound).  This script force-stops and re-launches
the app so it makes a fresh connection attempt right when the pytest WebSocket
server binds its port, ensuring it connects within the 90-second timeout.
"""

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))

if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[3]))
    from environment.aws.common.io import configure_terminal_encoding

    configure_terminal_encoding()

from environment.aws.topology_setup.setup_topology import TopologyConfig

TOPOLOGY_FILE = (
    SCRIPT_DIR.parents[3]
    / "environment"
    / "aws"
    / "topology_setup"
    / "topology.json"
)


def main() -> None:
    topology = TopologyConfig(TOPOLOGY_FILE)
    topology.relaunch_test_servers()


if __name__ == "__main__":
    main()
