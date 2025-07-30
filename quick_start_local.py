# Quick start local creates a local development environment with Couchbase Server, Sync Gateway, and Test Server.
# This writes a config.json file to the current directory, which can be used to run pytest.

# Example usage::
#
#   uv run -- quick_start_local.py --test-server-type c --cbl-version 3.2.4 --cbl-build-number 9 --dataset-version 3.2
#   uv run pytest --config config.json tests/dev_e2e/test_basic_replication.py
#
# /// script
# requires-python = ">=3.10"
# ///

import argparse
import enum
import json
import pathlib
import subprocess
import sys

CBL_DEFAULT_VERSION = "3.2.4"
CBL_DEFAULT_BUILD_NUMBER = "9"
DATASET_DEFAULT_VERSION = "3.2"


class TestServerType(str, enum.Enum):
    C = "c"


def parse_args(cmdline: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an integration test setup with Couchbase Server, Sync Gateway, and Test Server running local."
    )
    parser.add_argument(
        "--test-server-type",
        choices=list(TestServerType),
        type=TestServerType,
        required=True,
    )
    parser.add_argument(
        "--cbl-edition", choices=["community", "enterprise"], default="enterprise"
    )
    parser.add_argument("--cbl-version", type=str, default=CBL_DEFAULT_VERSION)
    parser.add_argument(
        "--cbl-build-number", type=str, default=CBL_DEFAULT_BUILD_NUMBER
    )
    parser.add_argument("--dataset-version", type=str, default=DATASET_DEFAULT_VERSION)
    return parser.parse_args(cmdline)


def main(cmdline: list[str]) -> None:
    args = parse_args(cmdline)
    write_config()
    start_containers()
    build_testserver(
        args.test_server_type,
        args.cbl_edition,
        args.cbl_version,
        args.cbl_build_number,
        args.dataset_version,
    )
    start_testserver(args.test_server_type)


def write_config() -> None:
    config = {
        "schema": "https://raw.githubusercontent.com/couchbaselabs/cbl-test-sg/main/config.schema.json",
        "test-servers": [
            {"url": "http://localhost:8080", "dataset_version": DATASET_DEFAULT_VERSION}
        ],
        "sync-gateways": [{"hostname": "localhost", "tls": False}],
        "couchbase-servers": [{"hostname": "localhost"}],
        "api-version": 1,
    }
    with pathlib.Path("config.json").open("w") as f:
        json.dump(config, f, indent=2)


def start_testserver(server_type: TestServerType) -> None:
    testserver = (
        pathlib.Path(__file__).parent / "servers" / server_type / "build" / "testserver"
    )
    subprocess.run(["pkill", "testserver"])
    subprocess.Popen(
        [f"{testserver} 2>&1 > testserver.log"],
        cwd=pathlib.Path(__file__).parent / "servers" / "c",
        start_new_session=True,
        shell=True,
    )


def build_testserver(
    server_type: TestServerType,
    edition: str,
    version: str,
    build_number: str,
    dataset_version: str,
) -> None:
    if server_type != TestServerType.C:
        raise ValueError(f"Unsupported test server type: {server_type}")
    subprocess.run(
        [
            "/bin/bash",
            "-c",
            f"./build_macos.sh {edition} {version} {build_number} {dataset_version}",
        ],
        cwd=pathlib.Path(__file__).parent / "servers" / "c" / "scripts",
        check=True,
    )


def start_containers() -> None:
    subprocess.run(
        ["python", "start_environment.py"],
        cwd=pathlib.Path(__file__).parent / "environment",
        check=True,
    )


if __name__ == "__main__":
    main(sys.argv[1:])
