import asyncio
import random
from collections.abc import Sequence

from cbltest.api.syncgateway import DatabaseConfig, SyncGateway
from cbltest.globals import CBLPyTestGlobal


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
        version = await self._put_database(db_name, config)
        await self.wait_for_db_online(db_name, version)

    async def _put_database(self, db_name: str, config: DatabaseConfig) -> str | None:
        """
        Create a database on one node of the cluster (the PUT phase only), without
        waiting for it to come online on any node.

        Private: `create_database` bundles this with `wait_for_db_online` for ordinary
        callers; `CouchbaseCluster.create_database` calls this directly so its own
        timeout handling isn't also exposed to the wait-for-online phase's unrelated
        timeouts. Every caller of this method shares the CBG-5733 timeout handling below,
        so it fires equally for `CouchbaseCluster.create_database` and for every test that
        calls `SyncGatewayCluster.create_database` (or this method) directly.

        :param db_name: The name of the database to create
        :param config: The configuration of the database to create
        :return: The version of the resulting config, or None if not reported
        """
        try:
            return await self.random_node._put_database(db_name, config)
        except TimeoutError:
            # CBG-5733: Sync Gateway can retry a stuck CBS index install forever instead of
            # surfacing it, so the client just sees this PUT call time out.  Record that this
            # signature occurred -- but only when Sync Gateway is actually backed by a real
            # Couchbase Server (Rosmar has no indexer to stall) -- for the cbcollect_session
            # fixture to act on once the whole test session finishes, the same way
            # sgcollect/es_collect wait for session end rather than collecting from inside the
            # failing test.  A cluster with `using_rosmar` false is always backed by at least
            # one real Couchbase Server node -- CouchbaseCluster.__init__ enforces that for
            # every cluster the framework builds -- so this needs no other node to check.
            if not self.sync_gateways[0].using_rosmar:
                CBLPyTestGlobal.cbcollect_needed = True
            raise

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
        Update the config of an existing database on one node of the cluster, and wait
        until every node reports it online with the config that was just written.

        :param db_name: The name of the database to update
        :param config: The configuration to apply
        """
        version = await self.random_node._update_database_config(db_name, config)
        await self.wait_for_db_online(db_name, version)
