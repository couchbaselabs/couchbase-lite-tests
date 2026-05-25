"""
``python -m cbltest.greenboard_upload`` — aggregate JUnit XMLs + meta sidecars
in a results directory and push a single greenboard doc.

Invoked by every ``test.sh`` / ``run_test.sh`` at the end of a Jenkins build
via an EXIT trap. See :py:meth:`cbltest.greenboarduploader.GreenboardUploader.upload_from_results_dir`
for the aggregation + no-upload rules.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from cbltest.configparser import _parse_config
from cbltest.greenboarduploader import GreenboardUploader
from cbltest.logging import cbl_info, cbl_warning


@click.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the test config JSON (same one pytest was run with).",
)
@click.option(
    "--results-dir",
    required=True,
    type=click.Path(file_okay=False),
    help="Directory holding junit_*.xml + meta_*.json from all pytest runs "
    "in this Jenkins build.",
)
@click.option(
    "--upgrade-to",
    default=None,
    help="Target SGW version for upgrade tests; included on the doc as "
    "`upgradeTo`. Omit for non-upgrade pipelines.",
)
def main(config_path: str, results_dir: str, upgrade_to: str | None) -> None:
    parsed = _parse_config(config_path)
    if (
        parsed.greenboard_url is None
        or parsed.greenboard_username is None
        or parsed.greenboard_password is None
    ):
        cbl_info("No greenboard config in test config; skipping upload")
        return

    build_url = os.environ.get("BUILD_URL") or None

    try:
        GreenboardUploader.upload_from_results_dir(
            parsed.greenboard_url,
            parsed.greenboard_username,
            parsed.greenboard_password,
            Path(results_dir),
            build_url=build_url,
            upgrade_to=upgrade_to,
        )
    except Exception as e:
        # Never let an upload failure mask the underlying test exit code in
        # the shell trap — log and exit clean. The trap already ORs with
        # `|| true`, but be defensive here too.
        cbl_warning(f"Greenboard aggregator failed: {e}")
        sys.exit(0)


if __name__ == "__main__":
    main()
