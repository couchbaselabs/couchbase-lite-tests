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
# This script builds and starts a CBL-C test server for local testing. Prior to running, this expects Couchbase
# Server and Sync Gateway running locally. The test server is built from source, so a C toolchain (cmake + a C/C++
# compiler) is required.
#
#
# Usage::
#
#   uv run environment/local/start_local.py
#   cd tests/dev_e2e
#   uv run pytest --config ../../environment/local/cbs_config.json
#
import pathlib
import sys

import click
import requests

SCRIPT_DIR = pathlib.Path(__file__).parent
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parent.parent))

from environment.aws import download_tool
from environment.aws.topology_setup import setup_topology

TOPOLOGY_CONFIG = SCRIPT_DIR / "topology.json"


@click.command()
@click.option(
    "--build-testserver",
    help="CBL-C version to build the test server from (e.g., 4.0.3). Defaults to the latest released version.",
)
@click.option(
    "--stop",
    is_flag=True,
    help="Stop the running local test server and exit (used during teardown).",
)
def main(build_testserver: str | None, stop: bool):
    if stop:
        stop_test_server()
        return

    # The test server is always built from source. Downloading a prebuilt
    # server requires a specific build number; a released version resolves to a
    # bare X.Y.Z that the latestbuilds download path cannot locate, so building
    # (which handles released versions via build number 0) is the reliable path.
    version = build_testserver or get_latest_released_cbl_c_version()
    cbl_version = f"{version}-0"

    config = {
        "test_servers": [
            {
                "location": "localhost",
                "download": False,
                "platform": get_cbl_platform(),
                "cbl_version": cbl_version,
            }
        ],
    }
    topology_config = setup_topology.TopologyConfig(config_input=config)

    setup_topology.main(topology_config)

    # hard code cbbackupmgr 8.0.0 for ease of use
    download_tool.download_tool(download_tool.ToolName.BackupManager, version="8.0.0")


def stop_test_server() -> None:
    """
    Stop the locally running CBL-C test server. The test server process is
    matched by name, so the version is irrelevant here.
    """
    config = {
        "test_servers": [
            {
                "location": "localhost",
                "download": False,
                "platform": get_cbl_platform(),
                "cbl_version": "0.0.0",
            }
        ],
    }
    topology_config = setup_topology.TopologyConfig(config_input=config)
    topology_config.stop_test_servers()


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
