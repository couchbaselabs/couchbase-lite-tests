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

from jenkins.pipelines.shared.setup_test import setup_test


@click.command()
@click.argument("cbl_version")
@click.argument("sgw_version")
@click.option(
    "--topology-file",
    type=click.Path(exists=True),
    default=None,
    help="Override the default topology file (defaults to topology.json in this directory)",
)
def cli_entry(
    cbl_version: str,
    sgw_version: str,
    topology_file: str | None,
) -> None:
    topo = Path(topology_file) if topology_file else SCRIPT_DIR / "topology.json"
    setup_test(
        cbl_version,
        sgw_version,
        topo,
        SCRIPT_DIR / "config.json",
        "upg-sgw",
        setup_dir="QE",
    )


if __name__ == "__main__":
    cli_entry()
