import asyncio
import random
from collections.abc import Sequence

from cbltest.api.syncgateway import SyncGateway


class SyncGatewayCluster:
    """
    A cluster of Sync Gateway nodes, for operations that must coordinate across all
    of them.
    """

    def __init__(self, sync_gateways: Sequence[SyncGateway]):
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
        Wait until every node in the cluster reports the database as Online, polling
        all nodes concurrently.

        :param db_name: Database name to poll.
        :param max_retries: Number of polls before timing out.
        :param retry_delay: Seconds between polls.
        """
        await asyncio.gather(
            *(
                sg._wait_for_db_online(db_name, max_retries=max_retries, retry_delay=retry_delay)
                for sg in self.__sync_gateways
            )
        )

    async def wait_for_no_databases(self) -> None:
        """
        Wait until every node in the cluster has no databases at all, polling all
        nodes concurrently.
        """
        await asyncio.gather(*(sg._wait_for_no_databases() for sg in self.__sync_gateways))
