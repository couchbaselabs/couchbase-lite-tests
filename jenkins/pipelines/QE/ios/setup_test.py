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
@click.argument("cbl_versions", type=VersionType())
@click.argument("sgw_versions", type=VersionType())
def cli_entry(
    cbl_versions: list[str],
    sgw_versions: list[str],
) -> None:
    """CBL_VERSIONS and SGW_VERSIONS are comma-separated version lists, e.g. "4.0.0,4.1.0".

    A single value is also accepted, e.g. "4.0.0".
    """
    setup_test(
        cbl_versions,
        sgw_versions,
        SCRIPT_DIR / "topology_single_device.json",
        SCRIPT_DIR / "config.json",
        "swift_ios",
        setup_dir="QE",
    )


if __name__ == "__main__":
    cli_entry()
