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
        max_retries: int = 70,
        retry_delay: int = 1,
    ) -> None:
        """
        Wait until every node in the cluster serves the database, re-reads its config and
        reports it Online, polling all nodes concurrently.  Only for waits on something
        outside our control, such as a restored bucket or a node that is still starting:
        after a config write, :func:`_refresh_database_config` gets there without polling.

        :param db_name: Database name to poll.
        :param max_retries: Number of polls before timing out, for each wait a node makes.
        :param retry_delay: Seconds between polls.
        """
        await asyncio.gather(
            *(
                sg._wait_for_db_online(db_name, max_retries=max_retries, retry_delay=retry_delay)
                for sg in self.__sync_gateways
            )
        )

    async def _refresh_database_config(self, db_name: str, *, skip: SyncGateway | None = None) -> None:
        """
        Make every node apply the database config from the bucket now, rather than at
        its next config poll.  A node returns only once it has applied the config, and
        a node that has not loaded the database at all loads it here, so a caller that
        has just written the config does not need to poll for it to land.

        :param db_name: The database whose config the nodes must reload.
        :param skip: A node that has applied this config already.  A re-read re-opens the
            database even when the config has not changed, which the node that took the
            write does not need.
        :raises CblSyncGatewayBadResponseError: if a node has no config for the database
        """
        await asyncio.gather(*(sg._refresh_database_config(db_name) for sg in self.__sync_gateways if sg is not skip))

    async def create_database(self, db_name: str, config: DatabaseConfig) -> None:
        """
        Create a database on one node of the cluster, and make every node apply the
        config that was just written before returning.

        :param db_name: The name of the database to create
        :param config: The configuration of the database to create
        """
        node = self.random_node
        await node._put_database(db_name, config)
        await self._refresh_database_config(db_name, skip=node)

    async def wait_for_no_database(self, db_name: str) -> None:
        """
        Wait until no node in the cluster serves db_name, polling all nodes concurrently.

        :param db_name: Database name to poll.
        """
        async with asyncio.TaskGroup() as group:
            for sg in self.__sync_gateways:
                group.create_task(sg._wait_for_database_gone(db_name))

    async def delete_database(self, db_name: str) -> None:
        """
        Delete a database from the cluster, and wait until no node serves it.

        A database that no node serves is not an error.

        :param db_name: The name of the database to delete
        :raises TimeoutError: if a node is still serving the database when the wait budget
            runs out
        :raises CblSyncGatewayBadResponseError: if the delete fails for any other reason
        """
        await self.random_node._delete_database(db_name)
        await self.wait_for_no_database(db_name)

    async def update_database_config(self, db_name: str, config: DatabaseConfig) -> None:
        """
        Update the config of an existing database on one node of the cluster, and make
        every node apply it before returning.

        :param db_name: The name of the database to update
        :param config: The configuration to apply
        """
        node = self.random_node
        await node._update_database_config(db_name, config)
        await self._refresh_database_config(db_name, skip=node)
