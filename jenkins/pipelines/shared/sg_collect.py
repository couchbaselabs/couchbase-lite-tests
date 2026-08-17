#!/usr/bin/env python3

"""
Standalone SGCollect runner for the Jenkins teardown / post path.

Runs sgcollect_info on every Sync Gateway node listed in a TDK config file, in
parallel, and downloads each resulting zip into a local directory. It is meant to
be invoked from the Jenkinsfile ``post { always }`` block -- i.e., OUTSIDE the
pytest process -- so that SGW diagnostics are captured even when a run times out
or is aborted, cases where an in-process pytest fixture never gets to run because
pytest itself is killed.

The parallel collection/download itself lives in ``cbltest.api.syncgateway``
(``run_sgcollects``); this module only turns a config file into the list of
Sync Gateway clients and reports a summary.
"""

import asyncio
import json
import sys
from pathlib import Path

import click
from cbltest.api.syncgateway import SyncGateway, run_sgcollects
from cbltest.configparser import ParsedConfig, SyncGatewayInfo


def build_sync_gateways(config_path: str) -> list[SyncGateway]:
    """
    Construct a SyncGateway admin client for every node in the TDK config.

    Args:
        config_path: Path to the TDK JSON config file.

    Returns:
        The reachable Sync Gateway clients (unreachable nodes are logged and skipped).
    """
    # Use the public ParsedConfig rather than cbltest's private _parse_config,
    # since this CLI lives outside the cbltest package. click already verified
    # the path exists.
    with open(config_path) as fin:
        parsed = ParsedConfig(json.load(fin))
    sync_gateways: list[SyncGateway] = []
    for sg in parsed.sync_gateways:
        info = SyncGatewayInfo(sg)
        try:
            # An unreachable node fails here rather than mid-collection.
            sync_gateways.append(
                SyncGateway(
                    info.hostname,
                    info.rbac_user,
                    info.rbac_password,
                    info.admin_port,
                    info.uses_tls,
                )
            )
        except Exception as e:
            click.echo(f"sgcollect: cannot reach SGW {info.hostname}, skipping: {e}", err=True)
    return sync_gateways


@click.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True),
    help="Path to the TDK JSON config listing the sync-gateways to collect from",
)
@click.option(
    "--output-dir",
    default=".",
    help="Local directory to download the sgcollect zips into",
)
def cli_entry(config_path: str, output_dir: str) -> None:
    sync_gateways = build_sync_gateways(config_path)
    if not sync_gateways:
        click.echo("sgcollect: no reachable Sync Gateway nodes; nothing to collect.")
        return

    out_dir = Path(output_dir).resolve()
    collected = asyncio.run(run_sgcollects(sync_gateways, out_dir))
    click.echo(f"sgcollect: downloaded {len(collected)}/{len(sync_gateways)} node(s) to {out_dir}")
    if len(collected) < len(sync_gateways):
        sys.exit(1)


if __name__ == "__main__":
    cli_entry()
