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
from jenkins.pipelines.shared.setup_test import TopologyConfig

if __name__ == "__main__":
    if isinstance(sys.stdout, TextIOWrapper):
        cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")


# Configuration for supported platforms
SUPPORTED_PLATFORMS = {
    "android": {
        "script_path": "../android/android_tests.sh",
        "param_format": "simple",  # version, dataset_version, sgw_version, [private_key], [--setup-only]
    },
    "ios": {
        "script_path": "../ios/test.sh",
        "param_format": "ios",  # edition, version, build, dataset_version, sgw_version, private_key, [--setup-only]
    },
    "dotnet": {
        "script_path": "../dotnet/run_test.sh",
        "param_format": "target_os",  # version, dataset_version, target_os, sgw_version, [private_key], [--setup-only]
    },
    "c": {
        "script_path": "../c/run_test.sh",
        "param_format": "target_os",  # version, dataset_version, target_os, sgw_version, [private_key], [--setup-only]
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
        # Use IP address instead of hostname to avoid DNS issues
        url = f"http://172.23.113.15:8080/api/get_version?product={product_name}&version={version}&ee=true"
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
    - android:3.2.3:6 (explicit build)
    - dotnet:windows:3.2.0 (auto-fetch for specific OS)
    - dotnet:windows:3.2.0:8 (explicit build for specific OS)

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
            # Format: platform:target_os:version[:build]
            target_os = parts[1]
            version = parts[2]
            build = parts[3] if len(parts) > 3 else None
        else:
            # Format: platform:version[:build]
            target_os = None  # Will be set to default later
            version = parts[1]
            build = parts[2] if len(parts) > 2 else None

        # Auto-fetch build if not specified
        if build is None:
            if auto_fetch_builds:
                try:
                    build = fetch_latest_build(platform, version)
                    build = str(build)  # Convert to string for consistency
                except Exception as e:
                    click.secho(
                        f"Warning: Failed to fetch build number for {platform} v{version}: {e}",
                        fg="yellow",
                    )
                    build = "1"  # Fallback
                    click.secho(
                        f"Using build number '{build}' as fallback for {platform}",
                        fg="yellow",
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
    platform_key: str, target_os: str | None = None
) -> list[Path]:
    """
    Get appropriate topology files for a platform, with optional OS specification.

    Args:
        platform_key: Platform identifier (ios, android, dotnet, java, c)
        target_os: Optional OS specification (windows, macos, linux, android, ios)

    Returns:
        List of topology file paths to use
    """
    QE_dir = SCRIPT_DIR.parents[1] / "QE" / platform_key

    if platform_key == "ios":
        # iOS has single topology
        topology_file = QE_dir / "topology_single_device.json"
        return [topology_file] if topology_file.exists() else []

    elif platform_key == "android":
        # Android has single topology
        topology_file = QE_dir / "topology_single_device.json"
        return [topology_file] if topology_file.exists() else []

    elif platform_key in ["dotnet", "java", "c"]:
        # Multi-OS platforms - check for topologies directory
        topologies_dir = QE_dir / "topologies"
        if not topologies_dir.exists():
            # Fallback to single topology file
            topology_file = QE_dir / "topology_single_device.json"
            return [topology_file] if topology_file.exists() else []

        topology_files = []

        if target_os:
            # Specific OS requested
            if target_os == "linux":
                # Handle Linux variants
                linux_files = list(topologies_dir.glob("topology_single_linux*.json"))
                if linux_files:
                    topology_files.extend(linux_files)
            else:
                topology_file = topologies_dir / f"topology_single_{target_os}.json"
                if topology_file.exists():
                    topology_files.append(topology_file)
        else:
            # Default: use all available topologies for the platform
            topology_files = list(topologies_dir.glob("topology_single_*.json"))

        return topology_files

    return []


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
    platform_versions: dict[str, dict[str, str]], dataset_version: str
) -> dict[str, Any]:
    """
    Compose a multiplatform topology from platform-specific topology files.

    Args:
        platform_versions: Dictionary of platform versions, builds, and target OS
        dataset_version: Dataset version to use

    Returns:
        Composed topology dictionary
    """
    composed_topology: dict[str, Any] = {
        "$schema": "topology_schema.json",
        "test_servers": [],
        "include": "default_topology.json",
    }

    for platform_key, version_info in platform_versions.items():
        platform, target_os = parse_platform_key(platform_key)

        if target_os:
            click.echo(
                f"Loading topology for {platform_key} ({platform} on {target_os})..."
            )
        else:
            click.echo(f"Loading topology for {platform_key}...")

        # Get topology files for this platform with OS specification
        topology_files = get_platform_topology_files(platform, target_os)

        if not topology_files:
            if target_os:
                click.secho(
                    f"Warning: No topology files found for {platform} on {target_os}",
                    fg="yellow",
                )
            else:
                click.secho(
                    f"Warning: No topology files found for {platform}", fg="yellow"
                )
            continue

        # Use the first available topology (or the specific OS topology if found)
        topology_file = topology_files[0]
        click.echo(f"Using topology: {topology_file.name}")

        try:
            with open(topology_file) as f:
                platform_topology = json.load(f)

                # Extract test servers from platform topology
                if "test_servers" in platform_topology:
                    for server in platform_topology["test_servers"]:
                        # Update with our version and dataset
                        server["cbl_version"] = version_info["full_version"]
                        server["dataset_version"] = dataset_version
                        composed_topology["test_servers"].append(server)
                        click.echo(
                            f"Added {server['platform']} server for {platform_key} with CBL {version_info['full_version']}"
                        )

        except Exception as e:
            click.secho(f"Error loading topology for {platform_key}: {e}", fg="red")
            continue

    return composed_topology


def run_platform_specific_setup(
    platform_key: str,
    full_version: str,
    dataset_version: str,
    sgw_version: str,
    private_key: str | None = None,
    target_os: str | None = None,
) -> None:
    """
    Run platform-specific main scripts that handle their own complete setup.

    Args:
        platform_key: Platform identifier (ios, android, dotnet, java, c)
        full_version: Full CBL version (e.g., "3.2.3-6")
        dataset_version: Dataset version
        sgw_version: Sync Gateway version
        private_key: Optional private key path
        target_os: Optional target OS (windows, macos, linux, etc.)
    """
    QE_dir = SCRIPT_DIR.parents[1] / "QE" / platform_key

    if not QE_dir.exists():
        click.secho(
            f"Warning: No QE setup found for {platform_key}, skipping platform-specific setup",
            fg="yellow",
        )
        return

    if target_os:
        click.echo(
            f"Running platform-specific setup for {platform_key} ({target_os})..."
        )
    else:
        click.echo(f"Running platform-specific setup for {platform_key}...")

    # Find and run the main platform script
    if platform_key == "android":
        main_script = QE_dir / "android_tests.sh"
        if main_script.exists():
            # Android script expects: <cbl_version> <dataset_version> <sg_version> [private_key_path]
            # Android expects combined version (e.g., "3.2.3-6")
            cmd = ["bash", str(main_script), full_version, dataset_version, sgw_version]
            if private_key:
                cmd.append(private_key)
            else:
                cmd.append("")  # Android script expects 4 parameters
            click.echo(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, cwd=str(QE_dir))
        else:
            click.secho(f"Warning: android_tests.sh not found in {QE_dir}", fg="yellow")

    elif platform_key == "ios":
        main_script = QE_dir / "test.sh"
        if main_script.exists():
            # iOS test.sh expects: <edition> <version> <build_num> <dataset_version> <sgw_version> [private_key]
            # iOS needs SEPARATE version and build number parameters
            if "-" in full_version:
                version, build_num = full_version.split("-", 1)
            else:
                version, build_num = full_version, "1"

            cmd = [
                "bash",
                str(main_script),
                "enterprise",
                version,
                build_num,
                dataset_version,
                sgw_version,
            ]
            if private_key:
                cmd.append(private_key)
            else:
                cmd.append("")  # iOS script expects 6 parameters
            click.echo(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, cwd=str(QE_dir))
        else:
            click.secho(f"Warning: test.sh not found in {QE_dir}", fg="yellow")

    elif platform_key == "dotnet":
        # .NET has different scripts for different OS
        if target_os == "windows":
            main_script = QE_dir / "run_test.ps1"
            if main_script.exists():
                # .NET expects: <version> <dataset_version> <platform> <sgw_version> [private_key_path]
                # .NET expects combined version (e.g., "3.2.3-6")
                cmd = [
                    "powershell",
                    "-File",
                    str(main_script),
                    full_version,
                    dataset_version,
                    target_os or "windows",
                    sgw_version,
                ]
                if private_key:
                    cmd.append(private_key)
                click.echo(f"Running: {' '.join(cmd)}")
                subprocess.run(cmd, check=True, cwd=str(QE_dir))
            else:
                click.secho(f"Warning: run_test.ps1 not found in {QE_dir}", fg="yellow")
        else:
            main_script = QE_dir / "run_test.sh"
            if main_script.exists():
                cmd = [
                    "bash",
                    str(main_script),
                    full_version,
                    dataset_version,
                    target_os or "macos",
                    sgw_version,
                ]
                if private_key:
                    cmd.append(private_key)
                click.echo(f"Running: {' '.join(cmd)}")
                subprocess.run(cmd, check=True, cwd=str(QE_dir))
            else:
                click.secho(f"Warning: run_test.sh not found in {QE_dir}", fg="yellow")

    elif platform_key in ["java", "c"]:
        # Java and C platforms
        main_script = QE_dir / "run_test.sh"
        if main_script.exists():
            # C expects: <version> <dataset_version> <platform> <sgw_version> [private_key_path]
            # C expects combined version (e.g., "3.2.3-6")
            cmd = [
                "bash",
                str(main_script),
                full_version,
                dataset_version,
                target_os or "linux",
                sgw_version,
            ]
            if private_key:
                cmd.append(private_key)
            click.echo(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, cwd=str(QE_dir))
        else:
            click.secho(f"Warning: run_test.sh not found in {QE_dir}", fg="yellow")

    click.echo(f"Platform-specific setup completed for {platform_key}")


def setup_multiplatform_test(
    platform_versions_str: str,
    dataset_version: str,
    sgw_version: str,
    config_file_in: Path,
    topology_tag: str,
    private_key: str | None = None,
    couchbase_version: str = "7.6",
    public_key_name: str = "jborden",
    setup_dir: str = "QE",
    auto_fetch_builds: bool = True,
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

    click.echo("Parsing platform versions...")
    platforms = parse_platform_versions(platform_versions_str, auto_fetch_builds)

    click.echo("Composing multiplatform topology...")
    # Convert platforms list to the expected dictionary format
    platform_versions_dict = {}
    for platform_info in platforms:
        platform_key = platform_info["platform_key"]
        platform_versions_dict[platform_key] = {
            "full_version": f"{platform_info['version']}-{platform_info['build']}"
        }
    topology = compose_multiplatform_topology(platform_versions_dict, dataset_version)

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
    click.echo(f"Composed topology with {len(topology['test_servers'])} test servers")
    # Start backend
    topology_config = TopologyConfig(str(topology_file_out))
    start_backend(
        topology_config,
        public_key_name,
        str(config_file_in),
        private_key=private_key,
        tdk_config_out=str(config_file_out),
    )


@click.command()
@click.argument("platform_versions")
@click.argument("dataset_version")
@click.argument("sgw_version")
@click.argument("private_key_path", required=False)
@click.option(
    "--no-auto-fetch", is_flag=True, help="Disable automatic build number fetching"
)
@click.option(
    "--setup-only", is_flag=True, help="Only setup platforms, do not run tests"
)
def main(
    platform_versions: str,
    dataset_version: str,
    sgw_version: str,
    private_key_path: str | None,
    no_auto_fetch: bool,
    setup_only: bool,
):
    """
    Setup multiplatform CBL testing environment.

    PLATFORM_VERSIONS: Space-separated list of platform specifications
    DATASET_VERSION: CBL dataset version to use
    SGW_VERSION: Sync Gateway version to use
    PRIVATE_KEY_PATH: Optional path to SSH private key
    """

    click.secho("🚀 Multiplatform CBL Setup", fg="blue", bold=True)
    click.secho(f"Platform specifications: {platform_versions}", fg="cyan")
    click.secho(f"Dataset version: {dataset_version}", fg="cyan")
    click.secho(f"SGW version: {sgw_version}", fg="cyan")
    if private_key_path:
        click.secho(f"Private key: {private_key_path}", fg="cyan")
    click.echo()

    try:
        # Use the proper multiplatform setup function
        config_file_in = SCRIPT_DIR / "config_multiplatform.json"
        setup_multiplatform_test(
            platform_versions,
            dataset_version,
            sgw_version,
            config_file_in,
            "multiplatform",
            private_key_path,
            auto_fetch_builds=not no_auto_fetch,
        )
        click.secho(
            "🎉 Multiplatform setup completed successfully!", fg="green", bold=True
        )
    except Exception as e:
        click.secho(f"💥 Setup failed: {e}", fg="red", bold=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
