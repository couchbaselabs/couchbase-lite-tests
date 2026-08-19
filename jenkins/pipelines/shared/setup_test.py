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

from environment.aws.download_tool import ToolName, download_tool
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

    if ts_platform == "js":
        return "js"

    raise ValueError(f"Unknown test server platform: {ts_platform}")


def resolved_version(product: str, version: str) -> str:
    if len(version.split(".")) >= 3:
        return version

    r = requests.get(f"http://proget.build.couchbase.com:8080/api/latest_release?product={product}&version={version}")
    if r.status_code != 200:
        raise RuntimeError(f"Failed to get latest version for {product} {version}: {r.text}")

    return cast(str, r.json()["version"])


def get_platform_version(version_map: dict[str, str], platform: str) -> str:
    if platform in version_map:
        return version_map[platform]

    raise ValueError(f"Platform {platform} not found in version map: {version_map}")


def parse_versions(value: str) -> list[str]:
    """
    Splits a comma-separated CLI argument into a list of versions. An empty
    (or whitespace-only) argument is valid and yields an empty list, meaning
    "no version of this kind requested".
    """
    return [v.strip() for v in value.split(",") if v.strip()]


class VersionType(click.ParamType):
    """
    A click parameter that accepts a comma-separated list of versions
    (e.g. "4.0.0,4.1.0") and hands the command a list[str] via `parse_versions`.
    """

    name = "versions"

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> list[str]:
        # click applies conversion to defaults as well, which may already be a list.
        if isinstance(value, list):
            return cast(list[str], value)

        return parse_versions(str(value))


def distribute_versions(versions: list[str], count: int) -> list[str]:
    """
    Assigns one version per index up to `count`, positionally: index 0 gets
    versions[0], index 1 gets versions[1], etc. Once `versions` is exhausted,
    the last entry repeats for all remaining indices.
    """
    if not versions:
        raise ValueError("At least one version must be provided")

    return [versions[min(i, len(versions) - 1)] for i in range(count)]


def setup_test(
    cbl_versions: list[str],
    sgw_versions: list[str] | None,
    topology_file_in: Path,
    config_file_in: Path,
    topology_tag: str,
    couchbase_version: str = "7.6",
    setup_dir: str = "dev_e2e",
) -> None:
    """
    Sets up a testing environment with the specified CBL version(s) and Sync Gateway version(s).

    `cbl_versions` is assigned positionally to `topology_file_in`'s test_servers, and
    `sgw_versions` positionally to its sync_gateways (only meaningful when sync_gateways
    is defined directly in that file rather than pulled in via `include`). In both cases,
    once the version list is exhausted the last entry repeats (see `distribute_versions`).

    Pass `None` for `sgw_versions` if the topology doesn't use Sync Gateway at all; a
    throwaway version is substituted internally. An empty list is rejected, since that
    usually means a version argument was mis-parsed rather than intentionally omitted.
    """
    config_file_out = SCRIPT_DIR.parents[2] / "tests" / setup_dir / "config.json"
    topology_file_out = SCRIPT_DIR.parents[2] / "environment" / "aws" / "topology_setup" / "topology.json"
    assert topology_file_in.exists() and topology_file_in.is_file(), f"Topology file {topology_file_in} does not exist."
    assert config_file_in.exists() and config_file_in.is_file(), f"Config file {config_file_in} does not exist."
    assert os.access(topology_file_in, os.R_OK), f"Topology file {topology_file_in} is not readable."
    assert os.access(config_file_in, os.R_OK), f"Config file {config_file_in} is not readable."
    assert topology_file_out.parent.exists() and os.access(topology_file_out.parent, os.W_OK), (
        f"Output directory {topology_file_out.parent} does not exist or is not writeable."
    )
    assert config_file_out.parent.exists() and os.access(config_file_out.parent, os.W_OK), (
        f"Output directory {config_file_out.parent} does not exist or is not writeable."
    )
    assert topology_file_out.exists() is False or os.access(topology_file_out, os.W_OK), (
        f"Output file {topology_file_out} already exists and is not writeable."
    )
    assert config_file_out.exists() is False or os.access(config_file_out, os.W_OK), (
        f"Output file {config_file_out} already exists and is not writeable."
    )

    if sgw_versions is None:
        sgw_versions = ["0.0.0"]  # throwaway; topology doesn't use Sync Gateway
    elif not sgw_versions:
        raise ValueError("At least one sgw version must be provided, or pass None if the topology does not use it.")

    couchbase_server_version = resolved_version("couchbase-server", couchbase_version)
    resolved_sgw_versions = [resolved_version("sync-gateway", version) for version in sgw_versions]

    with open(topology_file_in) as fin:
        topology = cast(dict[str, Any], json.load(fin))
        topology["$schema"] = "topology_schema.json"
        if "include" in topology and str(topology["include"]).endswith("default_topology.json"):
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
            "cbs": {"version": couchbase_server_version},
            "sgw": {
                "version": resolved_sgw_versions[0],
            },
        }
        topology["tag"] = topology_tag

        test_servers = cast(list[dict[str, Any]], topology["test_servers"])
        assigned_cbl_versions = distribute_versions(cbl_versions, len(test_servers))
        for ts, version in zip(test_servers, assigned_cbl_versions):
            ts["cbl_version"] = version

        if "sync_gateways" in topology:
            sync_gateways = cast(list[dict[str, Any]], topology["sync_gateways"])
            assigned_sgw_versions = distribute_versions(resolved_sgw_versions, len(sync_gateways))
            for sgw, version in zip(sync_gateways, assigned_sgw_versions):
                sgw["version"] = version

        with open(topology_file_out, "w") as fout:
            json.dump(topology, fout, indent=4)

    download_tool(ToolName.BackupManager, couchbase_server_version)

    topology_obj = TopologyConfig(str(topology_file_out))
    start_backend(
        topology_obj,
        str(config_file_in),
        str(config_file_out),
    )


assert __name__ != "__main__", "This script should not be run directly."
