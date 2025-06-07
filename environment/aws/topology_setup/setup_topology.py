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
from typing import Final, cast

import click
import requests

from environment.aws.common.output import header
from environment.aws.topology_setup.test_server import TestServer

SCRIPT_DIR = Path(__file__).resolve().parent


class DefaultProperty:
    """
    Like an optional, but with a default value
    """

    @property
    def value(self) -> str:
        return self.__value if self.__value is not None else self.__default_value

    @property
    def is_set(self) -> bool:
        return self.__value is not None

    def __init__(self, default_value: str):
        self.__default_value = default_value
        self.__value: str | None = None

    def set_value(self, value: str):
        self.__value = value

    def __str__(self) -> str:
        return self.value


class CouchbaseServerDefaults:
    __cbs_key: Final[str] = "cbs"
    __version_key: Final[str] = "version"
    __default_version: Final[str] = "7.6.4"

    @property
    def version(self) -> DefaultProperty:
        return self.__version

    def __init__(self, parent: dict):
        self.__version = DefaultProperty(self.__default_version)
        if self.__cbs_key not in parent:
            return

        cbs_defaults = cast(dict, parent[self.__cbs_key])
        if self.__version_key not in cbs_defaults:
            return

        self.__version.set_value(cast(str, cbs_defaults[self.__version_key]))


class SyncGatewayDefaults:
    __sgw_key: Final[str] = "sgw"
    __version_key: Final[str] = "version"
    __default_version: Final[str] = "3.2.2"

    @property
    def version(self) -> DefaultProperty:
        return self.__version

    def __init__(self, parent: dict):
        self.__version = DefaultProperty(self.__default_version)
        if self.__sgw_key not in parent:
            return

        sgw_defaults = cast(dict, parent[self.__sgw_key])
        if self.__version_key not in sgw_defaults:
            return

        self.__version.set_value(cast(str, sgw_defaults[self.__version_key]))


class ConfigDefaults:
    __defaults_key: Final[str] = "defaults"

    @property
    def CouchbaseServer(self) -> CouchbaseServerDefaults:
        return self.__cbs_defaults

    @property
    def SyncGateway(self) -> SyncGatewayDefaults:
        return self.__sgw_defaults

    def __init__(self, parent: dict):
        defaults = {}
        if self.__defaults_key in parent:
            defaults = cast(dict, parent[self.__defaults_key])

        self.__cbs_defaults = CouchbaseServerDefaults(defaults)
        self.__sgw_defaults = SyncGatewayDefaults(defaults)

    def extend(self, other: "ConfigDefaults"):
        if other.CouchbaseServer.version.is_set:
            if self.CouchbaseServer.version.is_set:
                raise Exception(
                    "Both main and included file are setting default CBS version"
                )

            self.CouchbaseServer.version.set_value(other.CouchbaseServer.version.value)

        if other.SyncGateway.version.is_set:
            if self.SyncGateway.version.is_set:
                raise Exception(
                    "Both main and included file are setting default SGW version"
                )

            self.SyncGateway.version.set_value(other.SyncGateway.version.value)


class ClusterConfig:
    """
    A class to store the configuration of a Couchbase Server cluster.

    Attributes:
        public_hostnames (List[str]): The public hostnames of the cluster nodes.
        internal_hostnames (List[str]): The internal hostnames of the cluster nodes.
    """

    @property
    def public_hostnames(self) -> list[str]:
        return self.__public_hostnames

    @property
    def internal_hostnames(self) -> list[str]:
        return self.__internal_hostnames

    @property
    def version(self) -> str:
        return self.__version

    def __init__(
        self, version: str, public_hostnames: list[str], internal_hostnames: list[str]
    ):
        self.__version = version
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

    @property
    def version(self) -> str:
        return self.__version

    def __init__(self, version: str, config: dict | None = None):
        if config is not None:
            if self.__server_count_key not in config:
                raise ValueError(
                    f"Missing required key '{self.__server_count_key}' in cluster configuration"
                )

            self.__server_count: int = int(config[self.__server_count_key])

        self.__version = version

    def create_config(
        self, public_hostnames: list[str], internal_hostnames: list[str]
    ) -> ClusterConfig:
        """
        Create a ClusterConfig instance from the provided hostnames.

        Args:
            public_hostnames (List[str]): The public hostnames of the cluster nodes.
            internal_hostnames (List[str]): The internal hostnames of the cluster nodes.

        Returns:
            ClusterConfig: The created ClusterConfig instance.
        """
        return ClusterConfig(self.version, public_hostnames, internal_hostnames)


class SyncGatewayInput:
    """
    A class to parse and store input configuration for a Sync Gateway instance.

    Attributes:
        cluster_index (int): The index of the cluster to which the Sync Gateway belongs.
    """

    @property
    def cluster_index(self) -> int:
        return self.__cluster_index

    @property
    def version(self) -> str:
        return self.__version

    def __init__(self, cluster_index: int, version: str):
        self.__cluster_index = cluster_index
        self.__version = version


class SyncGatewayConfig:
    """
    A class to store the configuration of a Sync Gateway instance.

    Attributes:
        version (str): The version of the Sync Gateway instance to install.
        hostname (str): The hostname of the Sync Gateway instance.
        internal_hostname (str): The EC2 internal hostname of the Sync Gateway instance.
        cluster_hostname (str): The hostname of the cluster to which the Sync Gateway belongs.
    """

    @property
    def version(self) -> str:
        return self.__version

    @property
    def hostname(self) -> str:
        return self.__hostname

    @property
    def internal_hostname(self) -> str:
        return self.__internal_hostname

    @property
    def cluster_hostname(self) -> str:
        return self.__cluster_hostname

    def __init__(
        self, version: str, hostname: str, internal_hostname: str, cluster_hostname: str
    ):
        self.__version = version
        self.__hostname = hostname
        self.__internal_hostname = internal_hostname
        self.__cluster_hostname = cluster_hostname


class LoadBalancerInput:
    """
    A class to parse and store input configuration for a load balancer.

    Attributes:
        sync_gateways (List[int]): The list of Sync Gateway indices associated with the load balancer.
    """

    @property
    def sync_gateways(self) -> list[int]:
        return self.__sync_gateways

    def __init__(self, sync_gateways: list[int]):
        self.__sync_gateways = sync_gateways


class LoadBalancerConfig:
    """
    A class to store the configuration of a load balancer.

    Attributes:
        hostname (str): The hostname of the load balancer.
        sync_gateways (List[int]): The list of Sync Gateway indices associated with the load balancer.
    """

    @property
    def hostname(self) -> str:
        return self.__hostname

    @property
    def upstreams(self) -> list[str]:
        return self.__upstreams

    def __init__(self, hostname: str, upstreams: list[str]):
        self.__hostname = hostname
        self.__upstreams = upstreams


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
    def dataset_version(self) -> str:
        return self.__dataset_version

    @property
    def platform(self) -> str:
        return self.__platform

    def __init__(
        self, ip_address: str, cbl_version: str, dataset_version: str, platform: str
    ):
        self.__ip_address = ip_address
        self.__cbl_version = cbl_version
        self.__dataset_version = dataset_version
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
    __load_balancers_key: Final[str] = "load_balancers"
    __logslurp_key: Final[str] = "logslurp"
    __include_key: Final[str] = "include"
    __tag_key: Final[str] = "tag"
    __version_key: Final[str] = "version"

    def __init__(
        self,
        config_file: str | None = None,
        parent_defaults: ConfigDefaults | None = None,
    ):
        if config_file is None:
            config_file = str((SCRIPT_DIR / "default_topology.json").resolve())

        self.__defaults = ConfigDefaults({})
        self.__clusters: list[ClusterConfig] = []
        self.__sync_gateways: list[SyncGatewayConfig] = []
        self.__sync_gateway_inputs: list[SyncGatewayInput] = []
        self.__cluster_inputs: list[ClusterInput] = []
        self.__test_server_inputs: list[TestServerInput] = []
        self.__test_servers: list[TestServerConfig] = []
        self.__load_balancers: list[LoadBalancerConfig] = []
        self.__load_balancer_inputs: list[LoadBalancerInput] = []
        self._wants_logslurp: bool | None = None
        self.__logslurp: str | None = None
        self.__tag: str = ""

        with open(config_file) as fin:
            config = cast(dict, json.load(fin))

            self.__defaults = ConfigDefaults(config)
            if parent_defaults is not None:
                self.__defaults.extend(parent_defaults)

            if self.__clusters_key in config:
                raw_clusters = cast(list[dict], config[self.__clusters_key])
                for raw_cluster in raw_clusters:
                    version = (
                        cast(str, raw_cluster[self.__version_key])
                        if self.__version_key in raw_cluster
                        else str(self.__defaults.CouchbaseServer.version)
                    )
                    self.__cluster_inputs.append(ClusterInput(version, raw_cluster))

            if self.__sync_gateways_key in config:
                raw_entry = cast(list[dict], config[self.__sync_gateways_key])
                for raw_server in raw_entry:
                    cluster_index = int(raw_server[self.__cluster_key])
                    if cluster_index < 0 or cluster_index >= len(self.__cluster_inputs):
                        raise ValueError(f"Invalid cluster index '{cluster_index}'")

                    version = (
                        cast(str, raw_server[self.__version_key])
                        if self.__version_key in raw_server
                        else str(self.__defaults.SyncGateway.version)
                    )
                    self.__sync_gateway_inputs.append(
                        SyncGatewayInput(cluster_index, version)
                    )

            if self.__test_servers_key in config:
                raw_servers = cast(
                    list[dict[str, str]], config[self.__test_servers_key]
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

            if self.__load_balancers_key in config:
                raw_balancers = cast(
                    list[dict[str, list[int]]], config[self.__load_balancers_key]
                )
                for raw_balancer in raw_balancers:
                    sgw_indices = raw_balancer["sync_gateways"]
                    for sgw_index in sgw_indices:
                        if sgw_index < 0 or sgw_index >= len(
                            self.__sync_gateway_inputs
                        ):
                            raise ValueError(
                                f"Invalid Sync Gateway index '{sgw_index}'"
                            )

                    self.__load_balancer_inputs.append(LoadBalancerInput(sgw_indices))

            if self.__logslurp_key in config:
                self._wants_logslurp = cast(bool, config[self.__logslurp_key])

            if self.__include_key in config:
                include_file = str(
                    (
                        Path(str(config_file)).parent
                        / cast(str, config[self.__include_key])
                    ).resolve()
                )
                sub_config = TopologyConfig(include_file, self.__defaults)
                self.__cluster_inputs.extend(sub_config.__cluster_inputs)
                self.__sync_gateway_inputs.extend(sub_config.__sync_gateway_inputs)
                self.__load_balancer_inputs.extend(sub_config.__load_balancer_inputs)
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
    def total_lb_count(self) -> int:
        return len(self.__load_balancer_inputs)

    @property
    def clusters(self) -> list[ClusterConfig]:
        return self.__clusters

    @property
    def sync_gateways(self) -> list[SyncGatewayConfig]:
        return self.__sync_gateways

    @property
    def test_servers(self) -> list[TestServerConfig]:
        return self.__test_servers

    @property
    def load_balancers(self) -> list[LoadBalancerConfig]:
        return self.__load_balancers

    @property
    def wants_logslurp(self) -> bool:
        return self._wants_logslurp is not None and self._wants_logslurp

    @property
    def logslurp(self) -> str | None:
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

        cbs_ips = cast(list[str], json.loads(result.stdout))

        cbs_command = ["terraform", "output", "-json", "couchbase_instance_private_ips"]
        result = subprocess.run(cbs_command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(
                f"Command '{' '.join(cbs_command)}' failed with exit status {result.returncode}: {result.stderr}"
            )

        cbs_internal_ips = cast(list[str], json.loads(result.stdout))
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

        sgw_ips = cast(list[str], json.loads(result.stdout))

        sgw_command = [
            "terraform",
            "output",
            "-json",
            "sync_gateway_instance_private_ips",
        ]
        result = subprocess.run(sgw_command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(
                f"Command '{' '.join(sgw_command)}' failed with exit status {result.returncode}: {result.stderr}"
            )

        sgw_internal_ips = cast(list[str], json.loads(result.stdout))
        self.apply_sgw_hostnames(sgw_ips, sgw_internal_ips)

        lb_command = [
            "terraform",
            "output",
            "-json",
            "load_balancer_instance_public_ips",
        ]
        result = subprocess.run(lb_command, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(
                f"Command '{' '.join(lb_command)}' failed with exit status {result.returncode}: {result.stderr}"
            )

        lb_ips = cast(list[str], json.loads(result.stdout))
        self.apply_lb_hostnames(lb_ips)

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
                test_server_input.platform, test_server_input.cbl_version
            )
            bridge = test_server.create_bridge()
            bridge.validate(test_server_input.location)
            self.__test_servers.append(
                TestServerConfig(
                    bridge.get_ip(test_server_input.location),
                    test_server_input.cbl_version,
                    test_server_input.dataset_version,
                    test_server_input.platform,
                )
            )

    def run_test_servers(self):
        """
        Run the test servers based on their configurations.
        """
        for test_server_input in self.__test_server_inputs:
            test_server = TestServer.create(
                test_server_input.platform, test_server_input.cbl_version
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
                    click.secho(
                        f"Failed to connect to test server at {ip}:{port}, retrying in 1s...",
                        fg="yellow",
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
                test_server_input.platform, test_server_input.cbl_version
            )
            bridge = test_server.create_bridge()
            bridge.validate(test_server_input.location)
            bridge.stop(test_server_input.location)

    def apply_sgw_hostnames(self, hostnames: list[str], internal_hostnames: list[str]):
        """
        Apply the Sync Gateway hostnames to the configuration.

        Args:
            hostnames (List[str]): The list of Sync Gateway hostnames.
        """
        for sgw_input in self.__sync_gateway_inputs:
            cluster = self.__clusters[sgw_input.cluster_index]
            sgw = SyncGatewayConfig(
                sgw_input.version,
                hostnames.pop(0),
                internal_hostnames.pop(0),
                cluster.internal_hostnames[0],
            )
            self.__sync_gateways.append(sgw)

    def apply_server_hostnames(
        self, server_hostnames: list[str], server_internal_hostnames: list[str]
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
            cluster = ClusterConfig(
                cluster_input.version, hostnames, internal_hostnames
            )
            self.__clusters.append(cluster)
            i += cluster_input.server_count

    def apply_lb_hostnames(self, hostnames: list[str]):
        """
        Apply the load balancer hostnames to the configuration.

        Args:
            hostnames (List[str]): The list of load balancer hostnames.
        """
        if len(self.__sync_gateways) == 0:
            raise Exception(
                "apply_sgw_hostnames must be called prior to apply_lb_hostnames"
            )

        for lb_input in self.__load_balancer_inputs:
            sgw_hostnames = []
            for sgw_index in lb_input.sync_gateways:
                sgw_hostnames.append(self.__sync_gateways[sgw_index].internal_hostname)

            lb = LoadBalancerConfig(hostnames.pop(0), sgw_hostnames)
            self.__load_balancers.append(lb)

    def dump(self):
        """
        Print the resulting topology configuration.
        """
        header("Resulting topology")
        i = 1
        for cluster in self.__clusters:
            click.echo(f"Cluster {i} ({cluster.version}):")
            for i in range(0, len(cluster.public_hostnames)):
                click.echo(
                    f"\t{cluster.public_hostnames[i]} / {cluster.internal_hostnames[i]}"
                )

            i += 1

        if len(self.__clusters) > 0:
            click.echo()

        i = 1
        for sgw in self.__sync_gateways:
            click.echo(
                f"Sync Gateway {i} ({sgw.version}): {sgw.hostname} -> {sgw.cluster_hostname}"
            )
            i += 1

        if len(self.__sync_gateways) > 0:
            click.echo()

        i = 1
        for lb in self.__load_balancers:
            click.echo(f"Load Balancer {i}: {lb.hostname}")
            for up in lb.upstreams:
                click.echo(f"\t{up}")

        if self.__logslurp is not None:
            click.echo(f"Logslurp: {self.__logslurp}")
            click.echo()

        i = 1
        for test_server in self.__test_servers:
            click.echo(f"Test Server {i}:")
            click.echo(f"\tPlatform: {test_server.platform}")
            click.echo(f"\tCBL Version: {test_server.cbl_version}")
            click.echo(f"\tDataset Version: {test_server.dataset_version}")
            click.echo(f"\tIP Address: {test_server.ip_address}")
            i += 1

        if len(self.__test_servers) > 0:
            click.echo()


def main(topology: TopologyConfig) -> None:
    """
    Main function to run the test servers based on the provided topology configuration.

    Args:
        topology (TopologyConfig): The topology configuration.
    """
    topology.run_test_servers()
