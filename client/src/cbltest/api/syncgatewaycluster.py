import asyncio
import random
from collections.abc import Sequence

from cbltest.api.syncgateway import DatabaseConfig, SyncGateway


class SyncGatewayCluster:
    """
    A cluster of Sync Gateway nodes, for operations that must coordinate across all
    of them.
    """

    def __init__(self, sync_gateways: Sequence[SyncGateway]) -> None:
        if not sync_gateways:
            raise ValueError("At least one Sync Gateway must be provided")
        self.__sync_gateways = sync_gateways
        self.__round_robin_index = 0

    @property
    def sync_gateways(self) -> Sequence[SyncGateway]:
        """Gets the Sync Gateway nodes that make up this cluster"""
        return self.__sync_gateways

    @property
    def round_robin_node(self) -> SyncGateway:
        """
        Gets the next Sync Gateway node in the cluster, cycling through all nodes in
        order across successive accesses.
        """
        node = self.__sync_gateways[self.__round_robin_index]
        self.__round_robin_index = (self.__round_robin_index + 1) % len(self.__sync_gateways)
        return node

    @property
    def random_node(self) -> SyncGateway:
        """Gets a uniformly random Sync Gateway node from the cluster."""
        return random.choice(self.__sync_gateways)

    async def wait_for_db_online(
        self,
        db_name: str,
        version: str | None = None,
        max_retries: int = 70,
        retry_delay: int = 1,
    ) -> None:
        """
        Wait until every node in the cluster reports the database as Online, polling
        all nodes concurrently.

        :param db_name: Database name to poll.
        :param version: If given, also wait until every node serves this config version.
        :param max_retries: Number of polls before timing out.
        :param retry_delay: Seconds between polls.
        """
        await asyncio.gather(
            *(
                sg._wait_for_db_online(db_name, version=version, max_retries=max_retries, retry_delay=retry_delay)
                for sg in self.__sync_gateways
            )
        )

    async def create_database(self, db_name: str, config: DatabaseConfig) -> None:
        """
        Create a database on one node of the cluster, and wait until every node
        reports it online with the config that was just written.

        :param db_name: The name of the database to create
        :param config: The configuration of the database to create
        """
        version = await self.random_node._put_database(db_name, config)
        await self.wait_for_db_online(db_name, version)

    async def update_database_config(self, db_name: str, config: DatabaseConfig) -> None:
        """
        Update the config of an existing database on one node of the cluster, and wait
        until every node reports it online with the config that was just written.

        :param db_name: The name of the database to update
        :param config: The configuration to apply
        """
        version = await self.random_node._update_database_config(db_name, config)
        await self.wait_for_db_online(db_name, version)
