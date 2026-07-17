import asyncio
import random

from cbltest.api.syncgateway import SyncGateway


class SyncGatewayCluster:
    """
    A cluster of Sync Gateway nodes, for operations that must coordinate across all
    of them.
    """

    @property
    def sync_gateways(self) -> list[SyncGateway]:
        """Gets the Sync Gateway nodes that make up this cluster"""
        return self.__sync_gateways

def __init__(self, sync_gateways: list[SyncGateway]):
    if not sync_gateways:
        raise ValueError("At least one Sync Gateway must be provided")
    self.__sync_gateways = sync_gateways
    self.__round_robin_index = 0

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

    async def wait_for_no_databases(self, bucket_name: str) -> None:
        """
        Wait until every node in the cluster no longer backs any database with the
        given bucket, polling all nodes concurrently.

        :param bucket_name: Bucket name to check for.
        """
        await asyncio.gather(
            *(sg._wait_for_no_databases(bucket_name) for sg in self.__sync_gateways)
        )
