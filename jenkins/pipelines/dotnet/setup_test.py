#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys
from argparse import ArgumentParser
from pathlib import Path

SCRIPT_DIR = Path(os.path.dirname(os.path.realpath(__file__)))

if __name__ == "__main__":
    sys.path.append(str(SCRIPT_DIR.parents[2]))
    sys.stdout.reconfigure(encoding="utf-8")

from environment.aws.start_backend import main as start_backend
from environment.aws.topology_setup.setup_topology import TopologyConfig

if __name__ == "__main__":
    parser = ArgumentParser(description="Setup a .NET testing environment")

    parser.add_argument("platform", type=str, help="The platform to setup")
    parser.add_argument("version", type=str, help="The version of CBL to use")
    parser.add_argument(
        "sgw_url", type=str, help="The URL of the Sync Gateway to download"
    )
    parser.add_argument(
        "--private_key",
        type=str,
        help="The private key to use for the SSH connection (if not default)",
    )
    args = parser.parse_args()

    topology_file = str(SCRIPT_DIR.parents[2] / "environment" / "aws" / "topology.json")
    with open(
        str(SCRIPT_DIR / "topologies" / f"topology_single_{args.platform}.json"), "r"
    ) as fin:
        topology = json.load(fin)
        topology["$schema"] = "topology_schema.json"
        topology["include"] = "default_topology.json"
        topology["tag"] = args.platform
        topology["test_servers"][0]["cbl_version"] = args.version
        with open(topology_file, "w") as fout:
            json.dump(topology, fout, indent=4)

    topology = TopologyConfig(topology_file)
    start_backend(
        topology,
        "jborden",
        args.sgw_url,
        str(SCRIPT_DIR / "config_aws.json"),
        private_key=args.private_key,
        tdk_config_out=str(SCRIPT_DIR.parents[2] / "tests" / "config.json"),
    )
