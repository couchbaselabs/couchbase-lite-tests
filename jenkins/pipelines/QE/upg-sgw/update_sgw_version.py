#!/usr/bin/env python3
"""Update only the SGW version in topology.json without resetting other components."""

import json
import sys
from pathlib import Path
from typing import cast

import requests

SCRIPT_DIR = Path(__file__).parent


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


def update_sgw_version(
    topology_file: Path, sgw_version: str, sgw_index: int | None = None
) -> None:
    """Update the SGW version in the topology file.

    If sgw_index is provided, only that specific node's version is updated
    (per-node override). Otherwise, the global default is updated for all nodes.
    """
    if not topology_file.exists():
        raise FileNotFoundError(f"Topology file not found: {topology_file}")

    with open(topology_file) as f:
        topology = json.load(f)

    sgw_version_resolved = resolved_version("sync-gateway", sgw_version)

    if sgw_index is not None:
        sgw_list = topology.get("sync_gateways", [])
        if sgw_index < 0 or sgw_index >= len(sgw_list):
            raise ValueError(
                f"SGW index {sgw_index} out of range (topology has {len(sgw_list)} nodes)"
            )
        sgw_list[sgw_index]["version"] = sgw_version_resolved
        print(f"Updated SGW node {sgw_index} version to: {sgw_version_resolved}")
    else:
        if "defaults" not in topology:
            topology["defaults"] = {}
        if "sgw" not in topology["defaults"]:
            topology["defaults"]["sgw"] = {}
        topology["defaults"]["sgw"]["version"] = sgw_version_resolved
        print(f"Updated topology default SGW version to: {sgw_version_resolved}")

    with open(topology_file, "w") as f:
        json.dump(topology, f, indent=4)


if __name__ == "__main__":
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        print(f"Usage: {sys.argv[0]} <topology_file> <sgw_version> [sgw_index]")
        sys.exit(1)

    topology_file = Path(sys.argv[1])
    sgw_version = sys.argv[2]
    sgw_index = int(sys.argv[3]) if len(sys.argv) == 4 else None

    update_sgw_version(topology_file, sgw_version, sgw_index)
