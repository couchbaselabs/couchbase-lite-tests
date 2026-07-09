#!/usr/bin/env python3
import pathlib
import sys

import click

SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parent.parent))

from environment.aws.topology_setup.test_server_platforms.exe_bridge import ExeBridge


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
        config_dir = SCRIPT_DIR / "sync_gateway_config"
        config_file = (
            "basic_sync_gateway_rosmar.json"
            if server == "rosmar"
            else "basic_sync_gateway_cbs.json"
        )
        config_path = str(config_dir / config_file)

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
