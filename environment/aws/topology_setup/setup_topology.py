#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This module sets up the topology for Couchbase Lite tests on AWS. It includes classes and functions for managing clusters,
Sync Gateway instances, and test servers. It also provides functionality to read configurations from Terraform and manage
the lifecycle of test servers.

Classes:
    ClusterConfig: A class to store the configuration of a Couchbase Server cluster.
    ClusterInput: A class to parse and store input configuration for a Couchbase Server cluster.
    SyncGatewayInput: A class to parse and store input configuration for a Sync Gateway instance.
    SyncGatewayConfig: A class to store the configuration of a Sync Gateway instance.
    TestServerInput: A class to parse and store input configuration for a test server.
    TestServerConfig: A class to store the configuration of a test server.
    TopologyConfig: A class to manage the overall topology configuration, including clusters, Sync Gateway instances, and test servers.

Functions:
    main(topology: TopologyConfig) -> None:
        Main function to run the test servers based on the provided topology configuration.
"""

import json
import subprocess
from pathlib import Path
from time import sleep
from typing import Dict, Final, List, Optional, cast

import requests

from environment.aws.common.output import header
from environment.aws.topology_setup.test_server import TestServer

SCRIPT_DIR = Path(__file__).resolve().parent


class ClusterConfig:
    """
    A class to store the configuration of a Couchbase Server cluster.

    Attributes:
        public_hostnames (List[str]): The public hostnames of the cluster nodes.
        internal_hostnames (List[str]): The internal hostnames of the cluster nodes.
    """

    @property
    def public_hostnames(self) -> List[str]:
        return self.__public_hostnames

    @property
    def internal_hostnames(self) -> List[str]:
        return self.__internal_hostnames

    def __init__(self, public_hostnames: List[str], internal_hostnames: List[str]):
        self.__public_hostnames = public_hostnames
        self.__internal_hostnames = internal_hostnames


class ClusterInput:
    """
    A class to parse and store input configuration for a Couchbase Server cluster.

    Attributes:
        server_count (int): The number of servers in the cluster.
    """

    __server_count_key: Final[str] = "server_count"

    @property
    def server_count(self) -> int:
        return self.__server_count

    def __init__(self, config: Optional[Dict] = None):
        if config is not None:
            if self.__server_count_key not in config:
                raise ValueError(
                    f"Missing required key '{self.__server_count_key}' in cluster configuration"
                )

            self.__server_count: int = int(config[self.__server_count_key])

    def create_config(
        self, public_hostnames: List[str], internal_hostnames: List[str]
    ) -> ClusterConfig:
        """
        Create a ClusterConfig instance from the provided hostnames.

        Args:
            public_hostnames (List[str]): The public hostnames of the cluster nodes.
            internal_hostnames (List[str]): The internal hostnames of the cluster nodes.

        Returns:
            ClusterConfig: The created ClusterConfig instance.
        """
        return ClusterConfig(public_hostnames, internal_hostnames)


class SyncGatewayInput:
    """
    A class to parse and store input configuration for a Sync Gateway instance.

    Attributes:
        cluster_index (int): The index of the cluster to which the Sync Gateway belongs.
    """

    @property
    def cluster_index(self) -> int:
        return self.__cluster_index

    def __init__(self, cluster_index: int):
        self.__cluster_index = cluster_index


class SyncGatewayConfig:
    """
    A class to store the configuration of a Sync Gateway instance.

    Attributes:
        hostname (str): The hostname of the Sync Gateway instance.
        cluster_hostname (str): The hostname of the cluster to which the Sync Gateway belongs.
    """

    @property
    def hostname(self) -> str:
        return self.__hostname

    @property
    def cluster_hostname(self) -> str:
        return self.__cluster_hostname

    def __init__(self, hostname: str, cluster_hostname: str):
        self.__hostname = hostname
        self.__cluster_hostname = cluster_hostname


class TestServerInput:
    """
    A class to parse and store input configuration for a test server.

    Attributes:
        location (str): The location of the test server.
        cbl_version (str): The version of Couchbase Lite to use.
        dataset_version (str): The version of the dataset to use.
        platform (str): The platform of the test server.
        download (bool): Whether to download the test server package.
    """

    @property
    def location(self) -> str:
        return self.__location

    @property
    def cbl_version(self) -> str:
        return self.__cbl_version

    @property
    def dataset_version(self) -> str:
        return self.__dataset_version

    @property
    def platform(self) -> str:
        return self.__platform

    @property
    def download(self) -> bool:
        return self.__download

    def __init__(
        self,
        location: str,
        cbl_version: str,
        dataset_version: str,
        platform: str,
        download: bool,
    ):
        self.__location = location
        self.__cbl_version = cbl_version
        self.__dataset_version = dataset_version
        self.__platform = platform
        self.__download = download


class TestServerConfig:
    """
    A class to store the configuration of a test server.

    Attributes:
        ip_address (str): The IP address of the test server.
        cbl_version (str): The version of Couchbase Lite used by the test server.
        platform (str): The platform of the test server.
    """

    @property
    def ip_address(self) -> str:
        return self.__ip_address

    @property
    def cbl_version(self) -> str:
        return self.__cbl_version

    @property
    def platform(self) -> str:
        return self.__platform

    def __init__(self, ip_address: str, cbl_version: str, platform: str):
        self.__ip_address = ip_address
        self.__cbl_version = cbl_version
        self.__platform = platform


class TopologyConfig:
    """
    A class to manage the overall topology configuration, including clusters, Sync Gateway instances, and test servers.

    Attributes:
        total_cbs_count (int): The total number of Couchbase Server nodes.
        total_sgw_count (int): The total number of Sync Gateway instances.
        clusters (List[ClusterConfig]): The list of cluster configurations.
        sync_gateways (List[SyncGatewayConfig]): The list of Sync Gateway configurations.
        test_servers (List[TestServerConfig]): The list of test server configurations.
        wants_logslurp (bool): Whether Logslurp is desired.
        logslurp (Optional[str]): The Logslurp configuration.
    """

    __clusters_key: Final[str] = "clusters"
    __sync_gateways_key: Final[str] = "sync_gateways"
    __cluster_key: Final[str] = "cluster"
    __test_servers_key: Final[str] = "test_servers"
    __logslurp_key: Final[str] = "logslurp"
    __include_key: Final[str] = "include"
    __tag_key: Final[str] = "tag"

    def __init__(self, config_file: Optional[str] = None):
        if config_file is None:
            config_file = str((SCRIPT_DIR / "default_topology.json").resolve())

        self.__clusters: List[ClusterConfig] = []
        self.__sync_gateways: List[SyncGatewayConfig] = []
        self.__sync_gateway_inputs: List[SyncGatewayInput] = []
        self.__cluster_inputs: List[ClusterInput] = []
        self.__test_server_inputs: List[TestServerInput] = []
        self.__test_servers: List[TestServerConfig] = []
        self._wants_logslurp: Optional[bool] = None
        self.__logslurp: Optional[str] = None
        self.__tag: str = ""

        with open(config_file, "r") as fin:
            config = cast(Dict, json.load(fin))
            if self.__clusters_key in config:
                raw_clusters = cast(List[Dict], config[self.__clusters_key])
                for raw_cluster in raw_clusters:
                    self.__cluster_inputs.append(ClusterInput(raw_cluster))

            if self.__sync_gateways_key in config:
                raw_entry = cast(List[Dict], config[self.__sync_gateways_key])
                for raw_server in raw_entry:
                    cluster_index = int(raw_server[self.__cluster_key])
                    if cluster_index < 0 or cluster_index >= len(self.__cluster_inputs):
                        raise ValueError(f"Invalid cluster index '{cluster_index}'")

                    self.__sync_gateway_inputs.append(SyncGatewayInput(cluster_index))

            if self.__test_servers_key in config:
                raw_servers = cast(
                    List[Dict[str, str]], config[self.__test_servers_key]
                )
                for raw_server in raw_servers:
                    self.__test_server_inputs.append(
                        TestServerInput(
                            raw_server["location"],
                            raw_server["cbl_version"],
                            raw_server["dataset_version"],
                            raw_server["platform"],
                            cast(bool, raw_server.get("download", False)),
                        )
                    )

            if self.__logslurp_key in config:
                self._wants_logslurp = cast(bool, config[self.__logslurp_key])

            if self.__include_key in config:
                include_file = str(
                    (SCRIPT_DIR / cast(str, config[self.__include_key])).resolve()
                )
                sub_config = TopologyConfig(include_file)
                self.__cluster_inputs.extend(sub_config.__cluster_inputs)
                self.__sync_gateway_inputs.extend(sub_config.__sync_gateway_inputs)
                self.__test_server_inputs.extend(sub_config.__test_server_inputs)
                if self._wants_logslurp is None:
                    self._wants_logslurp = sub_config._wants_logslurp

            if self.__tag_key in config:
                self.__tag = cast(str, config[self.__tag_key])

    @property
    def total_cbs_count(self) -> int:
        return sum([cluster.server_count for cluster in self.__cluster_inputs])

    @property
    def total_sgw_count(self) -> int:
        return len(self.__sync_gateway_inputs)

    @property
    def clusters(self) -> List[ClusterConfig]:
        return self.__clusters

    @property
    def sync_gateways(self) -> List[SyncGatewayConfig]:
        return self.__sync_gateways

    @property
    def test_servers(self) -> List[TestServerConfig]:
        return self.__test_servers

    @property
    def wants_logslurp(self) -> bool:
        return self._wants_logslurp is not None and self._wants_logslurp

    @property
    def logslurp(self) -> Optional[str]:
        return self.__logslurp

    @property
    def tag(self) -> str:
        return self.__tag

    def read_from_terraform(self):
        """
        Read the topology configuration from Terraform outputs.

        Raises:
            Exception: If any Terraform command fails.
        """
        cbs_command = ["terraform", "output", "-json", "couchbase_instance_public_ips"]
        result = subprocess.run(cbs_command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(
                f"Command '{' '.join(cbs_command)}' failed with exit status {result.returncode}: {result.stderr}"
            )

        cbs_ips = cast(List[str], json.loads(result.stdout))

        cbs_command = ["terraform", "output", "-json", "couchbase_instance_private_ips"]
        result = subprocess.run(cbs_command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(
                f"Command '{' '.join(cbs_command)}' failed with exit status {result.returncode}: {result.stderr}"
            )

        cbs_internal_ips = cast(List[str], json.loads(result.stdout))
        self.apply_server_hostnames(cbs_ips, cbs_internal_ips)

        sgw_command = [
            "terraform",
            "output",
            "-json",
            "sync_gateway_instance_public_ips",
        ]
        result = subprocess.run(sgw_command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(
                f"Command '{' '.join(sgw_command)}' failed with exit status {result.returncode}: {result.stderr}"
            )

        sgw_ips = cast(List[str], json.loads(result.stdout))
        self.apply_sgw_hostnames(sgw_ips)

        if self._wants_logslurp:
            logslurp_command = ["terraform", "output", "logslurp_instance_public_ip"]
            result = subprocess.run(logslurp_command, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(
                    f"Command '{' '.join(logslurp_command)}' failed with exit status {result.returncode}: {result.stderr}"
                )

            self.__logslurp = cast(str, json.loads(result.stdout))

    def resolve_test_servers(self):
        """
        Resolve the IP addresses of the test servers based on their locations.
        """
        for test_server_input in self.__test_server_inputs:
            test_server = TestServer.create(
                test_server_input.platform,
                test_server_input.cbl_version,
                test_server_input.dataset_version,
            )
            bridge = test_server.create_bridge()
            bridge.validate(test_server_input.location)
            self.__test_servers.append(
                TestServerConfig(
                    bridge.get_ip(test_server_input.location),
                    test_server_input.cbl_version,
                    test_server_input.platform,
                )
            )

    def run_test_servers(self):
        """
        Run the test servers based on their configurations.
        """
        for test_server_input in self.__test_server_inputs:
            test_server = TestServer.create(
                test_server_input.platform,
                test_server_input.cbl_version,
                test_server_input.dataset_version,
            )

            if test_server_input.download:
                test_server.download()
            else:
                test_server.build()

            bridge = test_server.create_bridge()
            bridge.validate(test_server_input.location)
            bridge.install(test_server_input.location)
            bridge.run(test_server_input.location)
            port = 5555 if test_server_input.platform.startswith("dotnet") else 8080
            ip = bridge.get_ip(test_server_input.location)
            for _ in range(0, 30):
                try:
                    requests.get(f"http://{ip}:{port}")
                    return
                except requests.exceptions.ConnectionError:
                    print(
                        f"Failed to connect to test server at {ip}:{port}, retrying in 1s..."
                    )
                    sleep(1)
                    pass

            raise RuntimeError(
                f"Test server failed to start at {test_server_input.location}"
            )

    def stop_test_servers(self):
        """
        Stop the running test servers.
        """
        TestServer.initialize()
        for test_server_input in self.__test_server_inputs:
            test_server = TestServer.create(
                test_server_input.platform,
                test_server_input.cbl_version,
                test_server_input.dataset_version,
            )
            bridge = test_server.create_bridge()
            bridge.validate(test_server_input.location)
            bridge.stop(test_server_input.location)

    def apply_sgw_hostnames(self, hostnames: List[str]):
        """
        Apply the Sync Gateway hostnames to the configuration.

        Args:
            hostnames (List[str]): The list of Sync Gateway hostnames.
        """
        for sgw_input in self.__sync_gateway_inputs:
            cluster = self.__clusters[sgw_input.cluster_index]
            sgw = SyncGatewayConfig(hostnames.pop(0), cluster.internal_hostnames[0])
            self.__sync_gateways.append(sgw)

    def apply_server_hostnames(
        self, server_hostnames: List[str], server_internal_hostnames: List[str]
    ):
        """
        Apply the server hostnames to the configuration.

        Args:
            server_hostnames (List[str]): The list of server public hostnames.
            server_internal_hostnames (List[str]): The list of server internal hostnames.
        """
        i = 0
        for cluster_input in self.__cluster_inputs:
            hostnames = server_hostnames[i : i + cluster_input.server_count]
            internal_hostnames = server_internal_hostnames[
                i : i + cluster_input.server_count
            ]
            cluster = ClusterConfig(hostnames, internal_hostnames)
            self.__clusters.append(cluster)
            i += cluster_input.server_count

    def dump(self):
        """
        Print the resulting topology configuration.
        """
        header("Resulting topology")
        i = 1
        for cluster in self.__clusters:
            print(f"Cluster {i}:")
            for i in range(0, len(cluster.public_hostnames)):
                print(
                    f"\t{cluster.public_hostnames[i]} / {cluster.internal_hostnames[i]}"
                )

            i += 1

        if len(self.__clusters) > 0:
            print()

        i = 1
        for sgw in self.__sync_gateways:
            print(f"Sync Gateway {i}: {sgw.hostname} -> {sgw.cluster_hostname}")
            i += 1

        if len(self.__sync_gateways) > 0:
            print()

        if self.__logslurp is not None:
            print(f"Logslurp: {self.__logslurp}")
            print()

        i = 1
        for test_server in self.__test_servers:
            print(f"Test Server {i}:")
            print(f"\tPlatform: {test_server.platform}")
            print(f"\tCBL Version: {test_server.cbl_version}")
            print(f"\tIP Address: {test_server.ip_address}")
            i += 1

        if len(self.__test_servers) > 0:
            print()


def main(topology: TopologyConfig) -> None:
    """
    Main function to run the test servers based on the provided topology configuration.

    Args:
        topology (TopologyConfig): The topology configuration.
    """
    topology.run_test_servers()
