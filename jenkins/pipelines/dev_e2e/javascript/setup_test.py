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

from jenkins.pipelines.shared.setup_test import parse_versions, setup_test


@click.command()
@click.argument("cbl_version")
@click.argument("sgw_version")
def cli_entry(
    cbl_version: str,
    sgw_version: str,
) -> None:
    setup_test(
        parse_versions(cbl_version),
        parse_versions(sgw_version),
        SCRIPT_DIR / "topology_single_host.json",
        SCRIPT_DIR / "config.json",
        "js",
    )


if __name__ == "__main__":
    cli_entry()
