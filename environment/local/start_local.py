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
#   uv run pytest --config ../../environment/local/config.json
#
import pathlib
import sys

import requests

SCRIPT_DIR = pathlib.Path(__file__).parent
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parent.parent))

from environment.aws import download_tool
from environment.aws.topology_setup import setup_topology

TOPOLOGY_CONFIG = SCRIPT_DIR / "topology.json"


def main():
    config = {
        "test_servers": [
            {
                "location": "localhost",
                "download": True,
                "platform": get_cbl_platform(),
                "cbl_version": get_latest_released_cbl_c_version(),
            }
        ],
    }
    topology_config = setup_topology.TopologyConfig(config_input=config)

    setup_topology.main(topology_config)

    # hard code cbbackupmgr 8.0.0 for ease of use
    download_tool.download_tool(download_tool.ToolName.BackupManager, version="8.0.0")


def get_cbl_platform() -> str:
    """
    Return the name of the CBL platform to use.
    """
    if sys.platform == "win32":
        return "c_windows"
    elif sys.platform == "darwin":
        return "c_macos"
    elif sys.platform.startswith("linux"):
        return "c_linux_x86_64"
    raise Exception(f"Unsupported platform: {sys.platform}")


def get_latest_released_cbl_c_version() -> str:
    r = requests.get(
        "http://proget.build.couchbase.com:8080/api/latest_release?product=couchbase-lite-c"
    )
    r.raise_for_status()
    return r.json()["version"]


if __name__ == "__main__":
    main()
