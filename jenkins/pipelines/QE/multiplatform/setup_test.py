#!/usr/bin/env python3

import json
import os
import sys
from io import TextIOWrapper
from pathlib import Path
from typing import cast

import click

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))

if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[3]))
    if isinstance(sys.stdout, TextIOWrapper):
        cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")

from environment.aws.start_backend import script_entry as start_backend
from environment.aws.topology_setup.setup_topology import TopologyConfig
from jenkins.pipelines.shared.setup_test import resolved_version


def setup_multiplatform_test(
    platform_versions: dict,
    dataset_version: str,
    sgw_version: str,
    private_key: str | None = None,
    couchbase_version: str = "7.6",
    public_key_name: str = "jborden",
    setup_dir: str = "QE",
) -> None:
    """
    Sets up a multiplatform testing environment with platform-specific CBL versions.

    Args:
        platform_versions: Dict mapping platform names to their versions (e.g., {"ios": "3.1.5", "android": "3.2.3"})
        dataset_version: CBL dataset version to use
        sgw_version: Sync Gateway version to use
        private_key: Optional SSH private key path
        couchbase_version: Couchbase Server version
        public_key_name: SSH public key name
        setup_dir: Setup directory name
    """
    topology_file_in = SCRIPT_DIR / "topology.json"
    config_file_in = SCRIPT_DIR / "config_multiplatform.json"

    config_file_out = SCRIPT_DIR.parents[2] / "tests" / setup_dir / "config.json"
    topology_file_out = (
        SCRIPT_DIR.parents[3]
        / "environment"
        / "aws"
        / "topology_setup"
        / "topology.json"
    )

    # Handle multiplatform case - if platform_versions is empty, topology is already composed
    if not platform_versions:
        # Multiplatform mode: topology is already written by setup_multiplatform.py
        # We just need to proceed with backend setup using the existing topology
        pass
    else:
        # Regular mode: read template and compose topology
        with open(topology_file_in) as fin:
            topology = json.load(fin)
            topology["$schema"] = "topology_schema.json"

            # Handle include path
            if "include" in topology and str(topology["include"]).endswith(
                "default_topology.json"
            ):
                old_include = Path(str(topology["include"]))
                if not old_include.is_absolute():
                    absolute_include = (topology_file_in.parent / old_include).resolve()
                    if not absolute_include.is_relative_to(topology_file_out.parent):
                        topology["include"] = str(absolute_include)
                    else:
                        new_include = absolute_include.relative_to(
                            topology_file_out.parent
                        )
                        topology["include"] = str(new_include)

            # Set defaults for Couchbase Server and Sync Gateway
            topology["defaults"] = {
                "cbs": {
                    "version": resolved_version("couchbase-server", couchbase_version),
                },
                "sgw": {
                    "version": resolved_version("sync-gateway", sgw_version),
                },
            }
            topology["tag"] = "multiplatform"

            # Replace template variables with actual platform versions
            for ts in topology["test_servers"]:
                # Replace dataset version template
                if ts.get("dataset_version") == "{{dataset_version}}":
                    ts["dataset_version"] = dataset_version

                # Replace platform-specific CBL version templates
                platform = ts.get("platform", "")
                if (
                    platform == "swift_ios"
                    and ts.get("cbl_version") == "{{ios_version}}"
                ):
                    ts["cbl_version"] = platform_versions.get("ios", "3.1.5")
                elif (
                    platform == "jak_android"
                    and ts.get("cbl_version") == "{{android_version}}"
                ):
                    ts["cbl_version"] = platform_versions.get("android", "3.2.3")
                elif (
                    platform == "dotnet"
                    and ts.get("cbl_version") == "{{dotnet_version}}"
                ):
                    ts["cbl_version"] = platform_versions.get("dotnet", "3.2.3")
                elif platform == "c" and ts.get("cbl_version") == "{{c_version}}":
                    ts["cbl_version"] = platform_versions.get("c", "3.2.3")

            with open(topology_file_out, "w") as fout:
                json.dump(topology, fout, indent=4)

    # Start the backend setup
    topology_config = TopologyConfig(str(topology_file_out))
    start_backend(
        topology_config,
        public_key_name,
        str(config_file_in),
        private_key=private_key,
        tdk_config_out=str(config_file_out),
    )


def parse_platform_configs(platform_configs: str) -> dict:
    """
    Parse platform configuration string into a dictionary of versions.

    Args:
        platform_configs: String like "android:3.2.3:6 ios:3.1.5" or "multiplatform"

    Returns:
        Dict mapping platform names to full versions with build numbers
    """
    # Handle special case where topology is already composed
    if platform_configs.strip().lower() == "multiplatform":
        # Return empty dict - topology is already set up, we just need config.json creation
        return {}

    versions = {}
    for config in platform_configs.split():
        if ":" in config:
            parts = config.split(":")
            platform = parts[0]

            if len(parts) >= 3:
                # Format: platform:version:build -> version-build
                version = f"{parts[1]}-{parts[2]}"
            elif len(parts) == 2:
                # Format: platform:version -> version-1 (default build)
                version = f"{parts[1]}-1"
            else:
                version = parts[1]

            versions[platform.lower()] = version
    return versions


@click.command()
@click.argument("platform_configs")
@click.argument("dataset_version")
@click.argument("sgw_version")
@click.option(
    "--private_key",
    help="The private key to use for the SSH connection (if not default)",
)
def cli_entry(
    platform_configs: str,
    dataset_version: str,
    sgw_version: str,
    private_key: str | None,
) -> None:
    """
    Setup multiplatform testing environment with platform-specific CBL versions.

    PLATFORM_CONFIGS: Space-separated platform specifications (e.g., "android:3.2.3 ios:3.1.5")
    DATASET_VERSION: CBL dataset version to use
    SGW_VERSION: Sync Gateway version to use
    """
    # Parse platform versions from the configuration string
    platform_versions = parse_platform_configs(platform_configs)

    click.echo("Setting up multiplatform environment with :")
    for platform, version in platform_versions.items():
        click.echo(f"  {platform}: CBL v{version}")

    setup_multiplatform_test(
        platform_versions,
        dataset_version,
        sgw_version,
        private_key,
        setup_dir="QE",
    )


if __name__ == "__main__":
    cli_entry()
