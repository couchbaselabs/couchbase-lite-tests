# For others looking to analyze what this file does, it basically performs two steps.
# The first step is creating an appropriate topology JSON file.  It rewrites the $schema
# and include property so that the relative paths are correct for the destination
# directory, adds a tag for the platform, and sets the CBL version to use in the
# test server.  Currently all of the tests that we are running use a single test
# server, a single sync gateway, and a single Couchbase Server, and this will
# be reflected in the topology file.
#
# The second step is to create a Topology instance from the resulting JSON file
# and then pass that information, along with other basically hard coded info,
# to the start_backend function which will handle the actual setup.

import json
import os
from pathlib import Path
from typing import Any, cast

import click
import requests

from environment.aws.download_tool import download_tool, ToolName
from environment.aws.start_backend import script_entry as start_backend
from environment.aws.topology_setup.setup_topology import TopologyConfig

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))


def ts_to_topology(ts_platform: str) -> str:
    if ts_platform.startswith("swift"):
        return "ios"

    if ts_platform == "jak_android":
        return "android"

    if ts_platform.startswith("jak_"):
        return "java"

    if ts_platform.startswith("dotnet_"):
        return "dotnet"

    if ts_platform.startswith("c_"):
        return "c"

    raise ValueError(f"Unknown test server platform: {ts_platform}")


def resolved_version(product: str, version: str) -> str:
    if len(version.split(".")) >= 3:
        return version

    r = requests.get(
        f"http://proget.build.couchbase.com:8080/api/latest_release?product={product}&version={version}"
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"Failed to get latest version for {product} {version}: {r.text}"
        )

    return cast(str, r.json()["version"])


def get_platform_version(version_map: dict[str, str], platform: str) -> str:
    if platform in version_map:
        return version_map[platform]

    raise ValueError(f"Platform {platform} not found in version map: {version_map}")


def setup_test_multi(
    cbl_version_map: dict[str, str],
    sgw_version: str,
    topology_file_in: Path,
    config_file_in: Path,
    topology_tag: str,
    private_key: str | None = None,
    couchbase_version: str = "7.6",
    public_key_name: str = "jborden",
    setup_dir: str = "dev_e2e",
) -> None:
    """
    Sets up a testing environment with the specified CBL version and Sync Gateway version.
    """
    config_file_out = SCRIPT_DIR.parents[2] / "tests" / setup_dir / "config.json"
    topology_file_out = (
        SCRIPT_DIR.parents[2]
        / "environment"
        / "aws"
        / "topology_setup"
        / "topology.json"
    )
    assert topology_file_in.exists() and topology_file_in.is_file(), (
        f"Topology file {topology_file_in} does not exist."
    )
    assert config_file_in.exists() and config_file_in.is_file(), (
        f"Config file {config_file_in} does not exist."
    )
    assert os.access(topology_file_in, os.R_OK), (
        f"Topology file {topology_file_in} is not readable."
    )
    assert os.access(config_file_in, os.R_OK), (
        f"Config file {config_file_in} is not readable."
    )
    assert topology_file_out.parent.exists() and os.access(
        topology_file_out.parent, os.W_OK
    ), (
        f"Output directory {topology_file_out.parent} does not exist or is not writeable."
    )
    assert config_file_out.parent.exists() and os.access(
        config_file_out.parent, os.W_OK
    ), f"Output directory {config_file_out.parent} does not exist or is not writeable."
    assert topology_file_out.exists() is False or os.access(
        topology_file_out, os.W_OK
    ), f"Output file {topology_file_out} already exists and is not writeable."
    assert config_file_out.exists() is False or os.access(config_file_out, os.W_OK), (
        f"Output file {config_file_out} already exists and is not writeable."
    )

    couchbase_server_version = resolved_version("couchbase-server", couchbase_version)

    with open(topology_file_in) as fin:
        topology = cast(dict[str, Any], json.load(fin))
        topology["$schema"] = "topology_schema.json"
        if "include" in topology and str(topology["include"]).endswith(
            "default_topology.json"
        ):
            old_include = Path(str(topology["include"]))
            if not old_include.is_absolute():
                absolute_include = (topology_file_in.parent / old_include).resolve()
                if not absolute_include.is_relative_to(topology_file_out.parent):
                    click.secho(f"When requesting include '{old_include}'", fg="yellow")
                    click.secho(
                        f"Resolved path {absolute_include} is not relative to {topology_file_out.parent}",
                        fg="yellow",
                    )
                    click.secho(
                        "Setting include to absolute path instead of adjusted relative",
                        fg="yellow",
                    )
                    topology["include"] = str(absolute_include)
                else:
                    new_include = absolute_include.relative_to(topology_file_out.parent)
                    topology["include"] = str(new_include)

        topology["defaults"] = {
            "cbs": {
                "version": couchbase_server_version
            },
            "sgw": {
                "version": resolved_version("sync-gateway", sgw_version),
            },
        }
        topology["tag"] = topology_tag
        for ts in topology["test_servers"]:
            platform = cast(str, ts.get("platform"))
            ts["cbl_version"] = get_platform_version(
                cbl_version_map, ts_to_topology(platform)
            )

        with open(topology_file_out, "w") as fout:
            json.dump(topology, fout, indent=4)

    download_tool(ToolName.BackupManager, couchbase_server_version)
    
    topology_obj = TopologyConfig(str(topology_file_out))
    start_backend(
        topology_obj,
        public_key_name,
        str(config_file_in),
        private_key=private_key,
        tdk_config_out=str(config_file_out),
    )


def setup_test(
    cbl_version: str,
    sgw_version: str,
    topology_file_in: Path,
    config_file_in: Path,
    topology_tag: str,
    private_key: str | None = None,
    couchbase_version: str = "7.6",
    public_key_name: str = "jborden",
    setup_dir: str = "dev_e2e",
) -> None:
    """
    Sets up a testing environment with the specified CBL version and Sync Gateway version.
    """
    default_dict = {
        "ios": cbl_version,
        "android": cbl_version,
        "java": cbl_version,
        "dotnet": cbl_version,
        "c": cbl_version,
    }

    setup_test_multi(
        default_dict,
        sgw_version,
        topology_file_in,
        config_file_in,
        topology_tag,
        private_key,
        couchbase_version,
        public_key_name,
        setup_dir,
    )


assert __name__ != "__main__", "This script should not be run directly."
