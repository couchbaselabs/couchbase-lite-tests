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
        after a config write, :func:`_wait_for_database_config` covers the same ground
        against the config that was written.

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

    async def _wait_for_database_config(self, db_name: str, sentinel: str) -> None:
        """
        Wait until every node runs the config the given sentinel marks, polling all nodes
        concurrently.  A node that did not serve the database before loads it as it picks
        the config up, and comes online in the background, so pair this with
        :func:`_wait_for_db_state_online`.

        :param db_name: The database whose config the nodes must pick up.
        :param sentinel: The value the write to one node returned.
        :raises TimeoutError: if a node is not running the config once the polls run out
        """
        await asyncio.gather(*(sg._wait_for_database_config(db_name, sentinel) for sg in self.__sync_gateways))

    async def _wait_for_db_state_online(self, db_name: str) -> None:
        """
        Wait until every node reports the database Online, without asking any of them to
        re-read the config first.

        :param db_name: Database name to poll.
        """
        await asyncio.gather(*(sg._wait_for_db_state_online(db_name) for sg in self.__sync_gateways))

    async def create_database(self, db_name: str, config: DatabaseConfig) -> None:
        """
        Create a database on one node of the cluster, and make every node apply the
        config that was just written and bring the database online before returning.

        :param db_name: The name of the database to create
        :param config: The configuration of the database to create
        """
        sentinel = await self.random_node._put_database(db_name, config)
        await self._wait_for_database_config(db_name, sentinel)
        await self._wait_for_db_state_online(db_name)

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
        every node apply it and bring the database online again before returning.

        :param db_name: The name of the database to update
        :param config: The configuration to apply
        """
        sentinel = await self.random_node._update_database_config(db_name, config)
        await self._wait_for_database_config(db_name, sentinel)
        await self._wait_for_db_state_online(db_name)
