# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = [
#     "click>=8.3.1",
#     "paramiko>=4.0.0",
#     "psutil>=7.2.2",
#     "requests>=2.32.5",
#     "tqdm>=4.67.3",
# ]
# ///
#
# This script sets up a test server for local testing. Prior to running, this expects Couchbase Server and Sync
# Gateway running locally. See config.json if need to modify to configuration.
#
#
# Usage::
#
#   uv run environment/local/start_local.py
#   cd tests/dev_e2e
#   uv run pytest --config ../../environment/local/config.json5
#
import pathlib
import sys

SCRIPT_DIR = pathlib.Path(__file__).parent
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parent.parent))

from environment.aws import download_tool
from environment.aws.topology_setup import setup_topology

TOPOLOGY_CONFIG = SCRIPT_DIR / "topology.json"


def main():
    topology_config = setup_topology.TopologyConfig(TOPOLOGY_CONFIG)
    setup_topology.main(topology_config)

    # hard code cbbackupmgr 8.0.0 for ease of use
    download_tool.download_tool(download_tool.ToolName.BackupManager, version="8.0.0")


if __name__ == "__main__":
    main()
