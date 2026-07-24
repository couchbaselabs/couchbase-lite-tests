#!/usr/bin/env python3

"""
CLI entry point that downloads a prebuilt Couchbase Lite test server package
for a given platform and version.

Functions:
    main() -> None:
        Parses platform/version from argv and downloads the matching test
        server package via TestServer.download().
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
    Parses `platform` and `version` from argv, then downloads the matching
    prebuilt test server package via TestServer.download().
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
