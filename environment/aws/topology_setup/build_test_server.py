import os
from argparse import ArgumentParser

import paramiko
import requests

from environment.aws.common.io import sftp_progress_bar
from environment.aws.common.output import header
from environment.aws.topology_setup.test_server import TestServer


def latestbuilds_url() -> str:
    pass


if __name__ == "__main__":
    parser = ArgumentParser("Builds a given test server")
    parser.add_argument("platform", type=str, help="The platform to build")
    parser.add_argument("version", type=str, help="The version of CBL to use")
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload the built server to latestbuilds, if applicable",
    )
    args = parser.parse_args()

    if "LATESTBUILDS_PASSWORD" not in os.environ:
        print("LATESTBUILDS_PASSWORD env var is not set")
        exit(1)

    server = TestServer.create(args.platform)
    # server.build(args.version)

    if not args.upload:
        print("Upload not requested, skipping")
        exit(0)

    url = f"https://latestbuilds.service.couchbase.com/builds/latestbuilds/{server.latestbuilds_path}"
    response = requests.head(url)
    if response.status_code == 200:
        print("Server already exists on latestbuilds, skipping upload")
        exit(0)

    if response.status_code != 404:
        print(f"Unexpected status code {response.status_code} from latestbuilds")
        exit(1)

    package_path = server.compress_package()
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
