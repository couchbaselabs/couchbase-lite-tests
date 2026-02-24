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
        sys.stdout.reconfigure(encoding="utf-8")

from jenkins.pipelines.shared.setup_test import setup_test


@click.command()
@click.argument("platform")
@click.argument("cbl_version")
@click.argument("sgw_version")
def cli_entry(
    platform: str,
    cbl_version: str,
    sgw_version: str,
) -> None:
    setup_test(
        cbl_version,
        sgw_version,
        SCRIPT_DIR / "topologies" / f"topology_single_{platform}.json",
        SCRIPT_DIR / "config.json",
        f"c_{platform}",
    )


if __name__ == "__main__":
    cli_entry()
