#!/usr/bin/env python3

import json
import os
import subprocess
import sys
from io import TextIOWrapper
from pathlib import Path
from typing import Any, cast

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(str(SCRIPT_DIR.parents[3]))

import click
import requests

from environment.aws.start_backend import script_entry as start_backend
from environment.aws.topology_setup.test_server import TestServer
from jenkins.pipelines.shared.setup_test import TopologyConfig

if __name__ == "__main__":
    if isinstance(sys.stdout, TextIOWrapper):
        cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")

# Configuration for supported platforms
SUPPORTED_PLATFORMS = {
    "android": {
        "script_path": "../android/android_tests.sh",
        "param_format": "simple",  # version, sgw_version, [private_key], [--setup-only]
    },
    "ios": {
        "script_path": "../ios/test.sh",
        "param_format": "ios",  # edition, version, build, sgw_version, private_key, [--setup-only]
    },
    "dotnet": {
        "script_path": "../dotnet/run_test.sh",
        "param_format": "target_os",  # version, target_os, sgw_version, [private_key], [--setup-only]
    },
    "c": {
        "script_path": "../c/run_test.sh",
        "param_format": "target_os",  # version, target_os, sgw_version, [private_key], [--setup-only]
    },
}


def fetch_latest_build(platform: str, version: str) -> str:
    """
    Fetch the latest successful build number for a platform and version.

    Args:
        platform: CBL platform (android, ios, etc.)
        version: CBL version (e.g., 3.2.3)

    Returns:
        Build number as string

    Raises:
        Exception if API call fails or no build found
    """
    # Map platform names to API product names
    platform_map = {
        "android": "android",
        "ios": "ios",
        "dotnet": "net",
        "java": "java",
        "c": "c",
    }

    if platform not in platform_map:
        raise ValueError(f"Unsupported platform: {platform}")

    product_name = f"couchbase-lite-{platform_map[platform]}"

    try:
        # Use IP address instead of hostname to avoid DNS issues (it works while being connected to vpn.couchbase.com)
        url = f"http://proget.build.couchbase.com:8080/api/get_version?product={product_name}&version={version}&ee=true"
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        data = response.json()
        build_number = data.get("BuildNumber")

        if build_number is None:
            raise ValueError(f"No BuildNumber found in response: {data}")

        return str(build_number)  # Convert to string before returning

    except Exception as e:
        raise Exception(f"Failed to fetch latest build for {platform} v{version}: {e}")


def parse_platform_versions(
    platform_versions: str, auto_fetch_builds: bool = True
) -> list[dict]:
    """
    Parse platform version specifications.

    Supports multiple formats:
    - android:3.2.3 (auto-fetch latest build)
    - android:3.2.3-6 (explicit build)
    - dotnet:windows:3.2.0 (auto-fetch for specific OS)
    - dotnet:windows:3.2.0-8 (explicit build for specific OS)

    Args:
        platform_versions: Space-separated platform specifications
        auto_fetch_builds: Whether to auto-fetch build numbers when not specified

    Returns:
        List of platform info dictionaries
    """
    platforms = []

    for spec in platform_versions.split():
        parts = spec.split(":")

        if len(parts) < 2:
            raise click.BadParameter(f"Invalid platform specification: {spec}")

        platform = parts[0].lower()

        if platform not in SUPPORTED_PLATFORMS:
            raise click.BadParameter(f"Unsupported platform: {platform}")

        # Handle different platform specification formats
        if platform in ["dotnet", "c"] and len(parts) >= 3:
            # Format: platform:target_os:version[-build]
            target_os = parts[1]
            version_build = parts[2]

            # Check if version contains build number
            if "-" in version_build:
                version, build = version_build.split("-", 1)
            else:
                version = version_build
                build = None
        else:
            # Format: platform:version[-build]
            target_os = None  # Will be set to default later
            version_build = parts[1]

            # Check if version contains build number
            if "-" in version_build:
                version, build = version_build.split("-", 1)
            else:
                version = version_build
                build = None

        # Auto-fetch build if not specified
        if build is None:
            if auto_fetch_builds:
                try:
                    build = fetch_latest_build(platform, version)
                    build = str(build)  # Convert to string for consistency
                except Exception as e:
                    raise click.BadParameter(
                        f"Failed to fetch build number for {platform} v{version}: {e}. "
                        f"Please specify build number explicitly (e.g., {platform}:{version}-<build>)"
                    )
            else:
                # When auto-fetch is disabled but no explicit build provided, error
                raise click.BadParameter(
                    f"Platform {platform} missing build number and auto-fetch is disabled"
                )

        # Store the parsed platform info
        platform_key = f"{platform}_{target_os}" if target_os else platform

        platform_info = {
            "platform": platform,
            "platform_key": platform_key,
            "version": version,
            "build": build,
            "target_os": target_os,
            "script_path": SUPPORTED_PLATFORMS[platform]["script_path"],
            "param_format": SUPPORTED_PLATFORMS[platform]["param_format"],
        }

        platforms.append(platform_info)

        click.secho(f"✓ {platform_key}: CBL v{version}-{build}", fg="green")

    return platforms


def get_platform_topology_files(
    platform_key: str,
    target_os: str | None = None,
    topology_file: str = "topology.json",
) -> list[Path]:
    """
    Get appropriate topology files for a platform, with optional OS specification.

    Args:
        platform_key: Platform identifier (ios, android, dotnet, java, c)
        target_os: Optional OS specification (windows, macos, linux, android, ios)
        topology_file: Optional topology file

    Returns:
        List of topology file paths to use
    """

    # For multiplatform setup, always use the multiplatform topology file
    multiplatform_topology = SCRIPT_DIR / Path(topology_file)

    if multiplatform_topology.exists():
        return [multiplatform_topology]

    # Fallback to individual platform topology files if multiplatform topology doesn't exist
    topology_files = []

    # Base topology file patterns to search for
    topology_patterns = [
        f"topology_{platform_key}.json",
        "topology_single_device.json",
        "topology_single_host.json",
        "topology.json",
    ]

    # Platform-specific directories to search
    platform_dirs = []

    if target_os:
        # If target OS is specified, look in platform_targetOS directory
        platform_dirs.append(SCRIPT_DIR.parent / f"{platform_key}_{target_os}")
        platform_dirs.append(SCRIPT_DIR.parent / platform_key / target_os)

    # Always check the base platform directory
    platform_dirs.append(SCRIPT_DIR.parent / platform_key)

    for platform_dir in platform_dirs:
        if platform_dir.exists():
            for pattern in topology_patterns:
                default_topology_file = platform_dir / Path(pattern)
                if default_topology_file.exists():
                    topology_files.append(default_topology_file)
                    # Return the first match for each directory
                    break

    return topology_files


def parse_platform_key(platform_key: str) -> tuple[str, str | None]:
    """
    Parse a platform key back into platform and target_os.

    Args:
        platform_key: Key like "dotnet_windows", "ios", "c_linux"

    Returns:
        Tuple of (platform, target_os) where target_os may be None
    """
    if "_" in platform_key:
        platform, target_os = platform_key.split("_", 1)
        return platform, target_os
    else:
        return platform_key, None


def compose_multiplatform_topology(
    platform_versions: dict[str, dict[str, str]], topology_file: str = ""
) -> dict[str, Any]:
    """
    Compose a multiplatform topology from platform-specific topology files.

    Args:
        platform_versions: Dictionary of platform versions, builds, and target OS
        topology_file: Optional topology file else it picks default topology file

    Returns:
        Composed topology dictionary
    """
    composed_topology: dict[str, Any] = {
        "$schema": "topology_schema.json",
        "test_servers": [],
        "sync_gateways": [],
        "clusters": [],
        "logslurp": True,
    }

    # Create a mapping of platform names to their expected test server platforms
    platform_to_server_map = {
        "android": "jak_android",
        "ios": "swift_ios",
        "dotnet": ["dotnet_windows", "dotnet_macos", "dotnet_ios", "dotnet_android"],
        "java": ["jak_desktop", "jak_webservice"],
        "c": ["c_windows", "c_macos", "c_linux_x86_64", "c_ios", "c_android"],
    }

    # Process each platform
    for platform_key, version_info in platform_versions.items():
        click.echo(f"Loading topology for {platform_key}...")

        # Get topology files for this platform
        topology_files = get_platform_topology_files(
            platform_key, topology_file=topology_file
        )
        if not topology_files:
            click.secho(
                f"Warning: No topology files found for {platform_key}, skipping...",
                fg="yellow",
            )
            continue

        # Use the first topology file found
        topology_file1 = topology_files[0]
        click.echo(f"Using topology: {topology_file1.name}")

        try:
            with open(topology_file1) as f:
                platform_topology = json.load(f)

                # Get the expected server platform(s) for this platform
                expected_server_platforms = platform_to_server_map.get(
                    platform_key, [platform_key]
                )
                if isinstance(expected_server_platforms, str):
                    expected_server_platforms = [expected_server_platforms]

                # Extract test servers from platform topology that match this platform
                if "test_servers" in platform_topology:
                    for server in platform_topology["test_servers"]:
                        # Only add servers that match the current platform being processed
                        server_platform = server.get("platform", "")
                        if server_platform in expected_server_platforms:
                            # Update with our version
                            server["cbl_version"] = version_info["full_version"]
                            composed_topology["test_servers"].append(server)
                            click.echo(
                                f"Added {server['platform']} server for {platform_key} with CBL {version_info['full_version']}"
                            )
                if "logslurp" in platform_topology:
                    composed_topology["logslurp"] = platform_topology["logslurp"]
                if "clusters" in platform_topology:
                    composed_topology["clusters"] = platform_topology["clusters"]
                if "sync_gateways" in platform_topology:
                    composed_topology["sync_gateways"] = platform_topology[
                        "sync_gateways"
                    ]

        except Exception as e:
            click.secho(f"Error loading topology for {platform_key}: {e}", fg="red")
            continue

    return composed_topology


def run_platform_specific_setup(
    platform_key: str,
    full_version: str,
    sgw_version: str,
    private_key: str | None = None,
    target_os: str | None = None,
) -> None:
    """
    Run platform-specific setup scripts.

    Args:
        platform_key: Platform identifier (ios, android, dotnet, java, c)
        full_version: Full version string (version-build)
        sgw_version: Sync Gateway version
        private_key: Optional SSH private key path
        target_os: Optional OS specification (windows, macos, linux, android, ios)
    """
    QE_dir = SCRIPT_DIR.parent

    # Find and run the main platform script
    if platform_key == "android":
        main_script = QE_dir / "android_tests.sh"
        if main_script.exists():
            # Android script expects: <cbl_version> <sg_version> [private_key_path]
            # Android expects combined version (e.g., "3.2.3-6")
            cmd = ["bash", str(main_script), full_version, sgw_version]
            if private_key:
                cmd.append(private_key)
            else:
                cmd.append("")  # Android script expects 3 parameters
            click.echo(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, cwd=str(QE_dir))
        else:
            click.secho(f"Warning: android_tests.sh not found in {QE_dir}", fg="yellow")

    elif platform_key == "ios":
        main_script = QE_dir / "test.sh"
        if main_script.exists():
            # iOS test.sh expects: <edition> <version> <build_num> <sgw_version> [private_key]
            # iOS needs SEPARATE version and build number parameters
            if "-" in full_version:
                version, build_num = full_version.split("-", 1)
            else:
                raise click.BadParameter(
                    f"iOS platform requires explicit build number. Please specify as ios:{full_version}-<build>"
                )

            cmd = [
                "bash",
                str(main_script),
                "enterprise",
                version,
                build_num,
                sgw_version,
            ]
            if private_key:
                cmd.append(private_key)
            else:
                cmd.append("")  # iOS script expects 5 parameters
            click.echo(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, cwd=str(QE_dir))
        else:
            click.secho(f"Warning: test.sh not found in {QE_dir}", fg="yellow")


def setup_multiplatform_test(
    platform_versions_str: str,
    sgw_version: str,
    config_file_in: Path,
    topology_tag: str,
    private_key: str | None = None,
    couchbase_version: str = "7.6.4",
    public_key_name: str = "jborden",
    setup_dir: str = "QE",
    auto_fetch_builds: bool = True,
    topology_file: str = "",
) -> None:
    """
    Sets up a multiplatform testing environment with platform-specific CBL versions and topologies.
    """
    config_file_out = SCRIPT_DIR.parents[3] / "tests" / setup_dir / "config.json"
    topology_file_out = (
        SCRIPT_DIR.parents[3]
        / "environment"
        / "aws"
        / "topology_setup"
        / "topology.json"
    )

    assert config_file_in.exists() and config_file_in.is_file(), (
        f"Config file {config_file_in} does not exist."
    )

    click.secho("🚀 MULTIPLATFORM CBL TEST SETUP", fg="green")
    click.secho("===============================", fg="green")
    click.secho(f"📋 Platform configurations: {platform_versions_str}", fg="green")
    click.secho(f"🔄 SG version: {sgw_version}", fg="green")
    click.secho(f"🔑 Private key: {private_key or '~/.ssh/jborden.pem'}", fg="green")
    click.echo()

    # Parse platform versions
    platforms = parse_platform_versions(platform_versions_str, auto_fetch_builds)

    # Convert platforms list to the expected dictionary format
    platform_versions_dict = {}
    for platform_info in platforms:
        platform_key = platform_info["platform_key"]
        platform_versions_dict[platform_key] = {
            "full_version": f"{platform_info['version']}-{platform_info['build']}"
        }
    topology = compose_multiplatform_topology(
        platform_versions_dict, topology_file=topology_file
    )

    # Set topology defaults (use versions as-is for local testing)
    topology["defaults"] = {
        "cbs": {
            "version": couchbase_version,
        },
        "sgw": {
            "version": sgw_version,
        },
    }
    topology["tag"] = topology_tag

    # Write composed topology
    with open(topology_file_out, "w") as fout:
        json.dump(topology, fout, indent=4)

    topology_config = TopologyConfig(str(topology_file_out))

    # Then start backend and set up devices
    click.secho("\n🔧 PHASE 1: SETTING UP CBL TEST SERVERS", fg="green")
    click.secho("=======================================", fg="green")
    click.secho("🏗️ Using centralized multiplatform setup...", fg="green")
    click.echo()

    start_backend(
        topology_config,
        public_key_name,
        str(config_file_in),
        private_key=private_key,
        tdk_config_out=str(config_file_out),
    )


@click.command()
@click.argument("platform_versions")
@click.argument("sgw_version")
@click.argument("topology_file", required=False)
@click.option(
    "--no-auto-fetch", is_flag=True, help="Disable automatic build number fetching"
)
@click.option(
    "--setup-only", is_flag=True, help="Only setup platforms, do not run tests"
)
def main(
    platform_versions: str,
    sgw_version: str,
    topology_file: str = "",
    no_auto_fetch: bool = False,
    setup_only: bool = False,
):
    """
    Setup multiplatform CBL testing environment.

    PLATFORM_VERSIONS: Space-separated list of platform specifications
    SGW_VERSION: Sync Gateway version to use
    Optional:
    topology_file: Topology file to use
    """
    private_key_path = os.path.expanduser("~/.ssh/jborden.pem")

    click.secho("🚀 Multiplatform CBL Setup", fg="blue", bold=True)
    click.secho(f"Platform specifications: {platform_versions}", fg="cyan")
    click.secho(f"SGW version: {sgw_version}", fg="cyan")
    click.secho(f"Private key: {private_key_path} (hardcoded)", fg="cyan")
    click.echo()

    try:
        # Use the proper multiplatform setup function
        config_file_in = SCRIPT_DIR / "config_multiplatform.json"
        setup_multiplatform_test(
            platform_versions,
            sgw_version,
            config_file_in,
            "multiplatform",
            private_key_path,
            auto_fetch_builds=not no_auto_fetch,
            topology_file=topology_file,
        )
        click.secho(
            "🎉 Multiplatform setup completed successfully!", fg="green", bold=True
        )
    except Exception as e:
        click.secho(f"💥 Setup failed: {e}", fg="red", bold=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
