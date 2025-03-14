import os
import sys
from argparse import ArgumentParser
from pathlib import Path

import paramiko
import requests

if __name__ == "__main__":
    SCRIPT_DIR = Path(__file__).resolve().parent
    sys.path.append(str(SCRIPT_DIR.parents[2]))

from environment.aws.common.io import sftp_progress_bar
from environment.aws.common.output import header
from environment.aws.topology_setup.test_server import TestServer


def upload_exists(server: TestServer, version: str) -> bool:
    url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/{server.latestbuilds_path(version)}"
    response = requests.head(url)
    if response.status_code == 200:
        return True

    if response.status_code == 404:
        return False

    raise RuntimeError(
        f"Unexpected status code {response.status_code} from latestbuilds"
    )


if __name__ == "__main__":
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
    server = TestServer.create(args.platform)

    if args.ci and upload_exists(server, args.version):
        print("Server already exists on latestbuilds, skipping build")
        exit(0)

    server.build(args.version)

    if not args.ci and not args.upload:
        print("Upload not requested, skipping")
        exit(0)

    if upload_exists(server, args.version):
        print("Server already exists on latestbuilds, skipping upload")
        exit(0)

    if "LATESTBUILDS_PASSWORD" not in os.environ:
        print("LATESTBUILDS_PASSWORD env var is not set")
        exit(1)

    package_path = Path(server.compress_package())
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        "latestbuilds.service.couchbase.com",
        username="couchbase",
        password=os.environ["LATESTBUILDS_PASSWORD"],
    )

    print(f"/data/builds/latestbuilds/{server.latestbuilds_path(args.version)}")
    header("Uploading compressed server")
    sftp = ssh.open_sftp()
    sftp_progress_bar(
        sftp,
        package_path,
        f"/data/builds/latestbuilds/{server.latestbuilds_path(args.version)}",
    )
    sftp.close()
