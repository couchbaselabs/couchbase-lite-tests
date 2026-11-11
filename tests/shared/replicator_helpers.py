from datetime import timedelta

from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import ReplicatorActivityLevel, ReplicatorStatus
from cbltest.api.testserver import TestServer
from cbltest.responses import ServerVariant


async def wait_for_refused_connection(
    replicator: Replicator,
    test_server: TestServer,
    interval: timedelta = timedelta(seconds=1),
    timeout: timedelta = timedelta(seconds=30),
) -> ReplicatorStatus:
    """
    Waits for the Replicator to stop, and asserts that the server refused its WebSocket upgrade with
    HTTP 401 (error code 10401).  A browser cannot see the status of a refused upgrade, so on CBL JS this asserts
    -1 "Failed to connect" instead.  Use wait_for_error when the server sends its status any other way,
    such as after the upgrade, or in reply to the _session request CBL JS makes for basic auth.

    :param replicator: The Replicator to wait on
    :param test_server: The test server that runs the Replicator
    :param interval: The polling interval (default 1s)
    :param timeout: The time limit to wait for the replicator to stop (default 30s)
    """
    stopped = ReplicatorActivityLevel.STOPPED
    if (await test_server.info).variant == ServerVariant.JS:
        return await replicator.wait_for_error(stopped, interval, timeout, code=-1, message="Failed to connect")
    return await replicator.wait_for_error(stopped, interval, timeout, code=10401)


async def wait_for_no_access_error(
    replicator: Replicator,
    test_server: TestServer,
    interval: timedelta = timedelta(seconds=1),
    timeout: timedelta = timedelta(seconds=30),
) -> ReplicatorStatus:
    """
    Waits for the Replicator to stop, and asserts that Edge Server refused it because the user has no
    access to any collection of the database.  Native platforms get the refusal at the WebSocket upgrade.
    CBL JS sends basic auth to _session first, and Edge Server refuses it there with a different message.

    :param replicator: The Replicator to wait on
    :param test_server: The test server that runs the Replicator
    :param interval: The polling interval (default 1s)
    :param timeout: The time limit to wait for the replicator to stop (default 30s)
    """
    if (await test_server.info).variant == ServerVariant.JS:
        message = "No read or write access to this database"
    else:
        message = "No accessible collections for sync"
    return await replicator.wait_for_error(
        ReplicatorActivityLevel.STOPPED, interval, timeout, code=10403, message=message
    )
