#!/usr/bin/env python3
"""Update only the SGW version in topology.json without resetting other components."""

import json
import sys
from pathlib import Path
from typing import cast

import requests

SCRIPT_DIR = Path(__file__).parent


def resolved_version(product: str, version: str) -> str:
    """Resolve a version to full semantic version format."""
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


def update_sgw_version(topology_file: Path, sgw_version: str) -> None:
    """Update only the SGW version in the topology file."""
    if not topology_file.exists():
        raise FileNotFoundError(f"Topology file not found: {topology_file}")

    # Load topology
    with open(topology_file) as f:
        topology = json.load(f)

    # Resolve the full SGW version
    sgw_version_resolved = resolved_version("sync-gateway", sgw_version)

    # Update only the SGW version in defaults (preserve everything else)
    if "defaults" not in topology:
        topology["defaults"] = {}
    if "sgw" not in topology["defaults"]:
        topology["defaults"]["sgw"] = {}

    topology["defaults"]["sgw"]["version"] = sgw_version_resolved

    # Write back
    with open(topology_file, "w") as f:
        json.dump(topology, f, indent=4)

    print(f"Updated topology SGW version to: {sgw_version_resolved}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <topology_file> <sgw_version>")
        sys.exit(1)

    topology_file = Path(sys.argv[1])
    sgw_version = sys.argv[2]

    update_sgw_version(topology_file, sgw_version)
