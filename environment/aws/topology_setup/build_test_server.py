#!/usr/bin/env python3

"""
This module builds and optionally uploads Couchbase Lite test servers to the latestbuilds server.
It includes functions for checking if an upload already exists, compressing the server package, and uploading the package via SFTP.

Functions:
    upload_exists(server: TestServer) -> bool:
        Check if the server package already exists on the latestbuilds server.

    main() -> None:
        Main function to build and optionally upload the Couchbase Lite test server.
"""

import os
import sys
from argparse import ArgumentParser
from io import TextIOWrapper
from pathlib import Path
from typing import cast

import click
import paramiko
import requests

if __name__ == "__main__":
    SCRIPT_DIR = Path(__file__).resolve().parent
    sys.path.append(str(SCRIPT_DIR.parents[2]))
    if isinstance(sys.stdout, TextIOWrapper):
        cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")

from environment.aws.common.io import sftp_progress_bar
from environment.aws.common.output import header
from environment.aws.topology_setup.test_server import TestServer


def upload_exists(server: TestServer) -> bool:
    """
    Check if the server package already exists on the latestbuilds server.

    Args:
        server (TestServer): The test server instance.

    Returns:
        bool: True if the server package exists, False otherwise.

    Raises:
        RuntimeError: If an unexpected status code is returned from the latestbuilds server.
    """
    url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/{server.latestbuilds_path}"
    response = requests.head(url)
    if response.status_code == 200:
        return True

    if response.status_code == 404:
        return False

    raise RuntimeError(
        f"Unexpected status code {response.status_code} from latestbuilds"
    )


def main() -> None:
    """
    Main function to build and optionally upload the Couchbase Lite test server.

    Parses command-line arguments to determine the platform, version, and whether to upload the built server.
    Builds the test server and uploads it to the latestbuilds server if requested.

    Raises:
        SystemExit: If the LATESTBUILDS_PASSWORD environment variable is not set or if the upload is not requested.
    """
    parser = ArgumentParser("Builds a given test server")
    parser.add_argument("platform", type=str, help="The platform to build")
    parser.add_argument("version", type=str, help="The version of CBL to use")
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload the built server to latestbuilds, if applicable",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="Enable CI mode (only build if necessary to upload)",
    )

    args = parser.parse_args()
    server = TestServer.create(args.platform, args.version)

    # if args.ci and upload_exists(server):
    #     click.secho("Server already exists on latestbuilds, skipping build", fg="green")
    #     exit(0)

    server.build()
    #
    # if not args.ci and not args.upload:
    #     click.secho("Upload not requested, skipping", fg="yellow")
    #     exit(0)
    #
    # if upload_exists(server):
    #     click.secho(
    #         "Server already exists on latestbuilds, skipping upload", fg="yellow"
    #     )
    #     exit(0)

    if "LATESTBUILDS_PASSWORD" not in os.environ:
        click.secho("LATESTBUILDS_PASSWORD env var is not set", fg="red")
        exit(1)

    package_path = Path(server.compress_package())
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        "latestbuilds.service.couchbase.com",
        username="couchbase",
        password=os.environ["LATESTBUILDS_PASSWORD"],
    )

    header("Uploading compressed server")
    sftp = ssh.open_sftp()
    sftp_progress_bar(
        sftp,
        package_path,
        f"/data/builds/latestbuilds/{server.latestbuilds_path}",
    )
    sftp.close()


if __name__ == "__main__":
    main()
else:
    raise RuntimeError(
        "This script is not intended to be imported as a module. Please run it directly."
    )
