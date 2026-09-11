#!/usr/bin/env python3
"""Upload one aggregate greenboard document for a rolling SGW upgrade run.

Reads per-iteration results recorded by the greenboard pytest fixture and
emits a single doc to greenboard with the full iteration history plus a
``failedAt`` marker pointing at the first failed step (if any).
"""

import json
import sys
from pathlib import Path

import click

SCRIPT_DIR = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[3]))

from cbltest.greenboarduploader import GreenboardUploader


@click.command()
@click.option("--config", "config_path", required=True, type=click.Path(exists=True))
@click.option("--results-file", required=True, type=click.Path())
def cli_entry(config_path: str, results_file: str) -> None:
    cfg = json.loads(Path(config_path).read_text())
    gb = cfg.get("greenboard")
    if not gb:
        click.echo("No greenboard section in config; nothing to upload.", err=True)
        return

    if not Path(results_file).exists():
        click.echo(
            f"Results file {results_file} does not exist; nothing to upload.",
            err=True,
        )
        return

    uploader = GreenboardUploader(gb["hostname"], gb["username"], gb["password"])
    uploader.upload_upgrade_batch(results_file)


if __name__ == "__main__":
    cli_entry()
