import asyncio
import random

from cbltest.api.syncgateway import ResyncState, SyncGateway


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

    async def take_database_offline(
        self,
        db_name: str,
        max_retries: int = 70,
        retry_delay: int = 1,
    ) -> None:
        """
        Take a database offline by POSTing {"offline": true} to its /_config endpoint
        on one node, then wait until every node in the cluster reports the database as
        Offline, polling all nodes concurrently.

        :param db_name: Database name to take offline.
        :param max_retries: Number of polls before timing out.
        :param retry_delay: Seconds between polls.
        """
        await self.round_robin_node._set_database_offline(db_name)
        await asyncio.gather(
            *(
                sg._wait_for_db_offline(
                    db_name, max_retries=max_retries, retry_delay=retry_delay
                )
                for sg in self.__sync_gateways
            )
        )

    async def update_sync_function(
        self,
        db_name: str,
        sync_function: str,
        *,
        scope: str = "_default",
        collection: str = "_default",
        max_retries: int = 30,
        retry_delay: int = 2,
    ) -> None:
        """
        Updates the sync function for a collection on one node, then waits for every
        node in the cluster to converge on the resulting config version (identified
        by its ETag).

        :param db_name: The name of the database to update.
        :param sync_function: The new sync function body.
        :param scope: The scope containing the collection (default '_default').
        :param collection: The collection to update the sync function for (default '_default').
        :param max_retries: Number of polls before timing out.
        :param retry_delay: Seconds between polls.
        """
        etag = await self.round_robin_node.update_sync_function(
            db_name, sync_function, scope=scope, collection=collection
        )
        assert etag is not None, (
            f"Sync Gateway did not return an ETag when updating the sync "
            f"function for {db_name}"
        )
        await asyncio.gather(
            *(
                sg._wait_for_config_etag(
                    db_name, etag, max_retries=max_retries, retry_delay=retry_delay
                )
                for sg in self.__sync_gateways
            )
        )

    async def wait_for_resync_state(
        self,
        db_name: str,
        state: ResyncState,
        max_retries: int = 30,
        retry_delay: int = 1,
    ) -> None:
        """
        Wait until every node in the cluster's resync status converges on the given
        state, polling all nodes concurrently.

        :param db_name: Database name to poll.
        :param state: The resync state to wait for.
        :param max_retries: Number of polls before timing out.
        :param retry_delay: Seconds between polls.
        """
        await asyncio.gather(
            *(
                sg._wait_for_resync_state(
                    db_name, state, max_retries=max_retries, retry_delay=retry_delay
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
