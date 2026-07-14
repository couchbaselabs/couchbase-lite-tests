import asyncio
import random

import tenacity

from cbltest.api.syncgateway import ResyncState, SyncGateway
from cbltest.utils import retry_assert


class SyncGatewayCluster:
    """
    A cluster of Sync Gateway nodes, for operations that must coordinate across all
    of them.
    """

    def __init__(self, sync_gateways: list[SyncGateway]):
        if not sync_gateways:
            raise ValueError("At least one Sync Gateway must be provided")
        self.__sync_gateways = sync_gateways
        self.__round_robin_index = 0

    @property
    def sync_gateways(self) -> list[SyncGateway]:
        """Gets the Sync Gateway nodes that make up this cluster"""
        return self.__sync_gateways

    @property
    def round_robin_node(self) -> SyncGateway:
        """
        Gets the next Sync Gateway node in the cluster, cycling through all nodes in
        order across successive accesses.
        """
        node = self.__sync_gateways[self.__round_robin_index]
        self.__round_robin_index = (self.__round_robin_index + 1) % len(
            self.__sync_gateways
        )
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
        Wait until every node in the cluster reports the database as Online, polling
        all nodes concurrently.

        :param db_name: Database name to poll.
        :param max_retries: Number of polls before timing out.
        :param retry_delay: Seconds between polls.
        """
        await asyncio.gather(
            *(
                sg._wait_for_db_online(
                    db_name, max_retries=max_retries, retry_delay=retry_delay
                )
                for sg in self.__sync_gateways
            )
        )

    async def take_database_offline(self, db_name: str) -> None:
        """
        Takes database offline on one node and waits for all cluster nodes to reflect it.

        Args:
            db_name: Database name.
        """
        await self.round_robin_node.take_database_offline(db_name)
        await asyncio.gather(
            *(
                sg._wait_for_database_state(db_name, "Offline")
                for sg in self.__sync_gateways
            )
        )

    async def update_sync_function(
        self,
        db_name: str,
        sync_function: str,
        *,
        scope: str,
        collection: str,
    ) -> None:
        """
        Updates a collection's sync function on one node and waits for all cluster nodes to reflect it.

        Args:
            db_name: Database name.
            sync_function: Sync function source code.
            scope: Target scope.
            collection: Target collection.
        """
        await self.round_robin_node.update_sync_function(
            db_name, sync_function, scope=scope, collection=collection
        )

        async def _wait_for_sync_function(sg: SyncGateway) -> None:
            async def _poll() -> None:
                config = await sg.get_database_config(db_name)
                scopes = config.get("scopes", {})
                scope_config = scopes.get(scope, {})
                collections = scope_config.get("collections", {})
                col_config = collections.get(collection, {})
                actual = col_config.get("sync")
                assert actual == sync_function, (
                    f"Sync function for {db_name}.{scope}.{collection} not yet "
                    f"propagated to node {sg.hostname}:{sg.port}"
                )

            # Config updates persist via CBS and poll independently, which takes longer to converge.
            await retry_assert(
                _poll, tenacity.wait_fixed(2), tenacity.stop_after_delay(30)
            )

        await asyncio.gather(
            *(_wait_for_sync_function(sg) for sg in self.__sync_gateways)
        )

    async def wait_for_resync_state(
        self, db_name: str, expected_state: ResyncState
    ) -> None:
        """
        Waits for all cluster nodes to converge on the expected resync state.

        Resync state changes are not instantly cluster-wide, so convergence must
        be verified before sending follow-up actions to other nodes.

        Args:
            db_name: Database name to poll.
            expected_state: The ResyncState every node must converge on.
        """
        await asyncio.gather(
            *(
                sg._wait_for_resync_state(db_name, expected_state)
                for sg in self.__sync_gateways
            )
        )

    async def wait_for_db_gone(
        self,
        db_name: str,
        max_retries: int = 30,
        retry_delay: int = 2,
    ) -> None:
        """
        Wait until every node in the cluster no longer lists the database, polling
        all nodes concurrently.

        :param db_name: Database name to poll.
        :param max_retries: Number of polls before timing out.
        :param retry_delay: Seconds between polls.
        """
        await asyncio.gather(
            *(
                sg._wait_for_db_gone(
                    db_name, max_retries=max_retries, retry_delay=retry_delay
                )
                for sg in self.__sync_gateways
            )
        )

    async def wait_for_no_databases(self, bucket_name: str) -> None:
        """
        Wait until every node in the cluster no longer backs any database with the
        given bucket, polling all nodes concurrently.

        :param bucket_name: Bucket name to check for.
        """
        await asyncio.gather(
            *(sg._wait_for_no_databases(bucket_name) for sg in self.__sync_gateways)
        )
