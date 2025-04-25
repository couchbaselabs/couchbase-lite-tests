#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from io import TextIOWrapper
from pathlib import Path
from typing import Optional, cast

import click

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[2]))
    if isinstance(sys.stdout, TextIOWrapper):
        cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")

from jenkins.pipelines.shared.setup_test import setup_test


@click.command()
@click.argument("platform")
@click.argument("cbl_version")
@click.argument("dataset_version")
@click.argument("sgw_version")
@click.option(
    "--cbs_version",
    default="7.6",
    help="The Couchbase Server version to use for the test (default: 7.6.x)",
)
@click.option(
    "--private_key",
    help="The private key to use for the SSH connection (if not default)",
)
def cli_entry(
    platform: str,
    cbl_version: str,
    dataset_version: str,
    sgw_version: str,
    private_key: Optional[str],
    cbs_version: str,
) -> None:
    setup_test(
        cbl_version,
        dataset_version,
        sgw_version,
        SCRIPT_DIR / "topologies" / f"topology_single_{platform}.json",
        SCRIPT_DIR / "config_aws.json",
        f"dotnet_{platform}",
        private_key,
        cbs_version,
    )


if __name__ == "__main__":
    cli_entry()
