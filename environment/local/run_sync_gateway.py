#!/usr/bin/env python3
import json
import pathlib
import sys

import click
import requests
from cbltest.configparser import CouchbaseServerInfo

SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parent.parent))

from environment.aws import download_tool
from environment.aws.topology_setup.test_server_platforms.exe_bridge import ExeBridge

SYNC_GATEWAY_CONFIG_DIR = SCRIPT_DIR / "sync_gateway_config"
SYNC_GATEWAY_CONFIG = {
    "rosmar": SYNC_GATEWAY_CONFIG_DIR / "basic_sync_gateway_rosmar.json",
    "cbs": SYNC_GATEWAY_CONFIG_DIR / "basic_sync_gateway_cbs.json",
}
TEST_CONFIG = {
    "rosmar": SCRIPT_DIR / "rosmar_config.json",
    "cbs": SCRIPT_DIR / "cbs_config.json",
}


def get_cbs_version() -> str:
    """Query the Couchbase Server instance in cbs_config.json for its release version."""
    config = json.loads(TEST_CONFIG["cbs"].read_text())
    cbs_info = CouchbaseServerInfo(config["couchbase-servers"][0])

    r = requests.get(
        f"http://{cbs_info.hostname}:8091/pools",
        auth=(cbs_info.admin_user, cbs_info.admin_password),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["implementationVersion"].split("-")[0]


@click.command()
@click.option("--start", is_flag=True, help="Start the sync_gateway instance.")
@click.option("--stop", is_flag=True, help="Stop the running sync_gateway instance.")
@click.option(
    "--server",
    type=click.Choice(["rosmar", "cbs"]),
    help="The server type to use (required for --start).",
)
def main(start, stop, server):
    """Manage local Sync Gateway process."""
    if start == stop:
        raise click.UsageError("Exactly one of --start or --stop must be provided.")

    if start and not server:
        raise click.UsageError("--server is required when using --start.")

    exe_path = str(SCRIPT_DIR / "sync_gateway")

    # We only need config if starting
    config_path = None
    if start:
        config_path = str(SYNC_GATEWAY_CONFIG[server])
        if server == "cbs":
            cbs_version = get_cbs_version()
            download_tool.download_tool(download_tool.ToolName.BackupManager, cbs_version)

    bridge = ExeBridge(
        exe_path=exe_path,
        extra_args=[config_path] if config_path else [],
        log_filename="sync_gateway.log",
    )

    bridge.stop("localhost")
    if stop:
        return
    bridge.run("localhost")


if __name__ == "__main__":
    main()
