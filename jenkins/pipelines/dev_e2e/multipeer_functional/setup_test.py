#!/usr/bin/env python3

import click
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))
sys.path.append(str(SCRIPT_DIR.parents[3]))

from jenkins.pipelines.shared.setup_test import setup_test_multi

def print_platform_spec(label: str, value: str | None) -> None:
    if value is not None:
        click.secho(f"    {label}: {value}", fg="cyan")

def edit_platform_map(dict: dict[str, str], key: str, value: str | None) -> None:
    if value is not None:
        dict[key] = value

@click.command()
@click.option("--ios", help="The version of iOS to use")
@click.option("--android", help="The version of Android to use")
@click.option("--dotnet", help="The version of .NET to use")
@click.option("--java", help="The version of Java to use")
@click.option("--c", help="The version of C to use")
@click.option("--global-version", help="The default version for all platforms")
@click.option("--private-key-path", help="The path to the private key file (if not default)")
@click.argument("sgw_version")
def main(
    ios: str | None,
    android: str | None,
    dotnet: str | None,
    java: str | None,
    c: str | None,
    global_version: str | None,
    sgw_version: str,
    private_key_path: str | None
):
    click.secho("🚀 Multiplatform CBL Setup", fg="blue", bold=True)
    click.secho(f"Platform specifications:", fg="cyan")
    print_platform_spec("Global Version", global_version)
    print_platform_spec("iOS", ios)
    print_platform_spec("Android", android)
    print_platform_spec(".NET", dotnet)
    print_platform_spec("Java", java)
    print_platform_spec("C", c)
    print_platform_spec("Sync Gateway Version", sgw_version)
    print_platform_spec("Private Key Path", private_key_path)
    click.echo()

    platform_map: dict[str, str] = {}
    if global_version:
        platform_map = {
            "ios": global_version,
            "android": global_version,
            "dotnet": global_version,
            "java": global_version,
            "c": global_version
        }

    edit_platform_map(platform_map, "ios", ios)
    edit_platform_map(platform_map, "android", android)
    edit_platform_map(platform_map, "dotnet", dotnet)
    edit_platform_map(platform_map, "java", java)
    edit_platform_map(platform_map, "c", c)

    try:
        # Use the proper multiplatform setup function
        config_file_in = SCRIPT_DIR / "config_multiplatform.json"
        topology_file_in = SCRIPT_DIR / "topology.json"
        setup_test_multi(
            platform_map,
            sgw_version,
            topology_file_in,
            config_file_in,
            "multipeer_functional",
            private_key_path
        )
        click.secho(
            "🎉 Setup completed successfully!", fg="green", bold=True
        )
    except Exception as e:
        click.secho(f"💥 Setup failed: {e}", fg="red", bold=True)
        sys.exit(1)

if __name__ == "__main__":
    main()