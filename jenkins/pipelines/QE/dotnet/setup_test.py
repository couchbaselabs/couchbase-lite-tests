#!/usr/bin/env python3

import os
import sys
from io import TextIOWrapper
from pathlib import Path

import click

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[3]))
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

from jenkins.pipelines.shared.setup_test import VersionType, setup_test


@click.command()
@click.argument("platform")
@click.argument("cbl_versions", type=VersionType())
@click.argument("sgw_versions", type=VersionType())
@click.option(
    "--cbs_version",
    default="7.6",
    help="The Couchbase Server version to use for the test (default: 7.6.x)",
)
def cli_entry(
    platform: str,
    cbl_versions: list[str],
    sgw_versions: list[str],
    cbs_version: str,
) -> None:
    """CBL_VERSIONS and SGW_VERSIONS are comma-separated version lists, e.g. "4.0.0,4.1.0".

    A single value is also accepted, e.g. "4.0.0".
    """
    setup_test(
        cbl_versions,
        sgw_versions,
        SCRIPT_DIR / "topologies" / f"topology_single_{platform}.json",
        SCRIPT_DIR / "config_aws.json",
        f"dotnet_{platform}",
        cbs_version,
        setup_dir="QE",
    )


if __name__ == "__main__":
    cli_entry()
