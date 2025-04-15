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
@click.argument("cbl_version")
@click.argument("dataset_version")
@click.argument("sgw_version")
@click.option(
    "--private_key",
    help="The private key to use for the SSH connection (if not default)",
)
def cli_entry(
    cbl_version: str,
    dataset_version: str,
    sgw_version: str,
    private_key: Optional[str],
) -> None:
    setup_test(
        cbl_version,
        dataset_version,
        sgw_version,
        SCRIPT_DIR / "topology_single_device.json",
        SCRIPT_DIR / "config.json",
        "swift_ios",
        private_key,
    )


if __name__ == "__main__":
    cli_entry()
