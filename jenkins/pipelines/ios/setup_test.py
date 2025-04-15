#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional
import click
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))

if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[2]))
    sys.stdout.reconfigure(encoding="utf-8")

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
        f"swift_ios",
        private_key,
    )

if __name__ == "__main__":
    cli_entry()
