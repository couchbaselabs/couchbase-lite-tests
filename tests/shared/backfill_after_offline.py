from collections.abc import Awaitable, Callable

from cbltest.api.database import Database
from cbltest.api.error import CblTestError
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.api.syncgateway import SyncGateway


async def backfill_after_offline(
    db: Database,
    sync_gateway: SyncGateway,
    db_name: str,
    authenticator: ReplicatorAuthenticator,
    while_offline: Callable[[], Awaitable[None]],
    collections: list[ReplicatorCollectionEntry] | None = None,
) -> Replicator:
    """
    Simulates a device that is offline while something changes on Sync Gateway, then
    reconnects and backfills.

    There is nothing to explicitly disconnect: for a one-shot (non-continuous) replicator,
    the window between one run stopping and the next one starting already *is* offline
    from Sync Gateway's point of view. This helper runs `while_offline` in that window --
    e.g. to revoke a channel and/or compact its history -- then starts a fresh one-shot
    pull replicator and returns it (already started and stopped) so the caller can assert
    on what backfilled via its `document_updates`.

    Sync Gateway auto-prunes the oldest per-channel history entries once a document
    accumulates more churn than `DocumentHistoryMaxEntriesPerChannel`, independent of the
    compact endpoint. Callers driving churn during `while_offline` should keep it to the
    minimum needed for the scenario so the test isn't accidentally exercising that
    auto-pruning instead of (or in addition to) the compact endpoint under test.

    :param db: The local CBL database to pull into
    :param sync_gateway: The Sync Gateway node to pull from
    :param db_name: The Sync Gateway database name
    :param authenticator: Credentials for the pull
    :param while_offline: An async callback performing the Sync-Gateway-side mutation(s)
        that happen during the simulated offline window
    :param collections: The collections to pull (defaults to the default collection)
    :return: The pull `Replicator`, already started and stopped
    :raises CblTestError: If the backfill replicator itself errors out
    """
    await while_offline()

    replicator = Replicator(
        db,
        sync_gateway.replication_url(db_name),
        replicator_type=ReplicatorType.PULL,
        authenticator=authenticator,
        collections=collections if collections is not None else [ReplicatorCollectionEntry()],
        enable_document_listener=True,
        pinned_server_cert=sync_gateway.tls_cert(),
    )
    await replicator.start()
    status = await replicator.wait_for(ReplicatorActivityLevel.STOPPED)
    if status.error is not None:
        raise CblTestError(
            f"Backfill replicator failed after offline window: "
            f"({status.error.domain} / {status.error.code}) {status.error.message}"
        )

    return replicator
