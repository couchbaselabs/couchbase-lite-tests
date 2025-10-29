#!/usr/bin/env python3

import os
import sys
from io import TextIOWrapper
from pathlib import Path
from typing import cast

import click

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))

if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[3]))
    if isinstance(sys.stdout, TextIOWrapper):
        cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")

from jenkins.pipelines.shared.setup_test import setup_test


@click.command()
@click.argument("cbl_version")
@click.argument("sgw_version")
@click.option(
    "--private_key",
    help="The private key to use for the SSH connection (if not default)",
)
def cli_entry(
    cbl_version: str,
    sgw_version: str,
    private_key: str | None,
) -> None:
    setup_test(
        cbl_version,
        sgw_version,
        SCRIPT_DIR / "topology.json",
        SCRIPT_DIR / "config.json",
        "swift_ios",
        private_key,
        setup_dir="QE",
    )


if __name__ == "__main__":
    cli_entry()
