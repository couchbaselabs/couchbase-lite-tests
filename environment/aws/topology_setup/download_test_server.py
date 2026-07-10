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

import sys
from argparse import ArgumentParser
from io import TextIOWrapper
from pathlib import Path

if __name__ == "__main__":
    SCRIPT_DIR = Path(__file__).resolve().parent
    sys.path.append(str(SCRIPT_DIR.parents[2]))
    if isinstance(sys.stdout, TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")

from environment.aws.topology_setup.test_server import TestServer


def main() -> None:
    """
    Main function to build and optionally upload the Couchbase Lite test server.

    Parses command-line arguments to determine the platform, version, and whether to upload the built server.
    Builds the test server and uploads it to the latestbuilds server if requested.

    Raises:
        SystemExit: If the LATESTBUILDS_PASSWORD environment variable is not set or if the upload is not requested.
    """
    parser = ArgumentParser("Downloads a given test server")
    parser.add_argument("platform", type=str, help="The platform to build")
    parser.add_argument("version", type=str, help="The version of CBL to use")

    args = parser.parse_args()
    server = TestServer.create(args.platform, args.version)
    server.download()


if __name__ == "__main__":
    main()
else:
    raise RuntimeError(
        "This script is not intended to be imported as a module. Please run it directly."
    )
