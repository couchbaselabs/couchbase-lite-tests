import asyncio

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
        self.__sync_gateways = sync_gateways

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
                sg.wait_for_db_online(
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
                sg.wait_for_db_gone(
                    db_name, max_retries=max_retries, retry_delay=retry_delay
                )
                for sg in self.__sync_gateways
            )
        )
