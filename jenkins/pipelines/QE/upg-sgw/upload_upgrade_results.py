#!/usr/bin/env python3
"""Upload combined upgrade test results to greenboard.

This script is called once at the end of an upgrade test pipeline
(test.sh / test_rolling.sh) after all pytest invocations have completed.

It reads the deferred results file (one JSON line per pytest session),
determines overall pass/fail, and uploads a single greenboard document
for the entire upgrade batch.

Environment variables (required):
    SGW_UPGRADE_RESULTS_FILE  — path to the JSONL results file
    SGW_UPGRADE_VERSIONS      — comma-separated ordered version list (e.g. "3.1.0,3.2.0,3.3.0")

Environment variables (optional):
    SGW_UPGRADE_PASSED        — set to "false" by the shell trap on failure;
                                 defaults to "true" (inferred from results file)

Usage from shell scripts:
    # On success (end of script):
    uv run python upload_upgrade_results.py --config ../../../tests/QE/config.json

    # On failure (in trap):
    SGW_UPGRADE_PASSED=false uv run python upload_upgrade_results.py --config ../../../tests/QE/config.json
"""

import json
import os
import sys
from pathlib import Path

import click


@click.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True),
    help="Path to the TDK config.json with greenboard credentials.",
)
def main(config_path: str) -> None:
    with open(config_path) as f:
        config = json.load(f)

    greenboard = config.get("greenboard")
    if not greenboard or not all(
        k in greenboard for k in ("hostname", "username", "password")
    ):
        print("Greenboard credentials not configured in config.json, skipping upload.")
        sys.exit(0)

    gb_url = greenboard["hostname"]
    gb_user = greenboard["username"]
    gb_pass = greenboard["password"]

    versions_str = os.environ.get("SGW_UPGRADE_VERSIONS")
    if not versions_str:
        print("ERROR: SGW_UPGRADE_VERSIONS not set.", file=sys.stderr)
        sys.exit(1)

    upgrade_path = [v.strip() for v in versions_str.split(",") if v.strip()]
    if len(upgrade_path) < 2:
        print(
            f"ERROR: Need at least 2 versions for upgrade path, got: {upgrade_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    target_version = upgrade_path[-1]

    # Determine pass/fail
    explicit_result = os.environ.get("SGW_UPGRADE_PASSED")
    if explicit_result is not None:
        passed = explicit_result.lower() != "false"
    else:
        # Infer from deferred results file
        results_file = os.environ.get("SGW_UPGRADE_RESULTS_FILE")
        if results_file and Path(results_file).exists():
            passed = True
            with open(results_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    if not entry.get("passed", False):
                        passed = False
                        break
        else:
            print("WARNING: No results file found, assuming failure.", file=sys.stderr)
            passed = False

    # Parse target build number from SGW_VERSION_UNDER_TEST if available
    version_under_test = os.environ.get("SGW_VERSION_UNDER_TEST", target_version)
    target_build = 0
    if "-" in version_under_test:
        try:
            target_build = int(version_under_test.split("-")[1].lstrip("b"))
        except (ValueError, IndexError):
            pass

    target_sgw_version = (
        version_under_test
        if "-" in version_under_test
        else f"{target_version}-{target_build}"
    )

    # Import here to avoid requiring cbltest deps at module level for CLI parsing
    from cbltest.greenboarduploader import GreenboardUploader

    uploader = GreenboardUploader(gb_url, gb_user, gb_pass)
    uploader.upload_upgrade_batch(
        upgrade_path=upgrade_path,
        target_sgw_version=target_sgw_version,
        target_build=target_build,
        passed=passed,
    )

    status = "PASSED" if passed else "FAILED"
    print(
        f"Greenboard upload complete: sgw-upgrade {' → '.join(upgrade_path)} [{status}]"
    )

    # Clean up results file
    results_file = os.environ.get("SGW_UPGRADE_RESULTS_FILE")
    if results_file and Path(results_file).exists():
        Path(results_file).unlink()


if __name__ == "__main__":
    main()
