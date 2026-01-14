import asyncio
from datetime import timedelta
from time import time
from typing import cast

from opentelemetry.trace import get_tracer

from cbltest.api.database import Database
from cbltest.api.error import CblTestError, CblTimeoutError
from cbltest.api.multipeer_replicator_types import (
    MultipeerReplicatorAuthenticator,
    MultipeerTransportType,
)
from cbltest.api.replicator import ReplicatorCollectionEntry
from cbltest.api.replicator_types import ReplicatorActivityLevel
from cbltest.api.x509_certificate import CertKeyPair, create_leaf_certificate
from cbltest.logging import cbl_error, cbl_trace
from cbltest.requests import TestServerRequestType
from cbltest.response_types import (
    MultipeerReplicatorStatusEntry,
    PostGetMultipeerReplicatorStatusResponseMethods,
    PostStartMultipeerReplicatorResponseMethods,
)
from cbltest.version import VERSION


class MultipeerReplicatorStatus:
    """
    A class representing the status of a Couchbase Lite multipeer replicator
    """

    @property
    def replicators(self) -> list[MultipeerReplicatorStatusEntry]:
        """Gets the list of replicators and their statuses"""
        return self.__replicators

    def __init__(self, replicators: list[MultipeerReplicatorStatusEntry]):
        self.__replicators = replicators


class MultipeerReplicator:
    """
    A class representing a Couchbase Lite multipeer replicator inside a test server
    """

    @property
    def peerGroupID(self) -> str:
        """Gets the peer group ID for the replicator"""
        return self.__peerGroupID

    @property
    def database(self) -> Database:
        """Gets the database for the replicator"""
        return self.__database

    @property
    def collections(self) -> list[ReplicatorCollectionEntry]:
        """Gets the collections for the replicator"""
        return self.__collections

    @property
    def identity(self) -> CertKeyPair:
        """Gets the identity used by the replicator"""
        return self.__identity

    def __init__(
        self,
        peerGroupID: str,
        database: Database,
        collections: list[ReplicatorCollectionEntry],
        *,
        authenticator: MultipeerReplicatorAuthenticator | None = None,
        identity: CertKeyPair | None = None,
        transports: MultipeerTransportType = MultipeerTransportType.ALL,
    ):
        self.__index = database._index
        self.__request_factory = database._request_factory
        self.__peerGroupID = peerGroupID
        self.__database = database
        self.__authenticator = authenticator
        self.__identity = (
            identity
            if identity is not None
            else create_leaf_certificate(f"Test Server {self.__index}")
        )
        assert transports.value != 0, "At least one transport type must be specified"
        assert len(collections) > 0, "At least one collection is required"
        self.__transports = transports
        self.__collections = collections
        self.__tracer = get_tracer(__name__, VERSION)
        self.__id: str = ""

    async def start(self) -> None:
        """
        Starts the multipeer replicator
        """
        with self.__tracer.start_as_current_span("start_multipeer_replicator"):
            req = self.__request_factory.create_request(
                TestServerRequestType.START_MULTIPEER_REPLICATOR,
                peerGroupID=self.__peerGroupID,
                database=self.__database.name,
                collections=self.__collections,
                identity=self.__identity,
                authenticator=self.__authenticator,
                transports=self.__transports.to_json(),
            )
            resp = await self.__request_factory.send_request(self.__index, req)
            if resp.error is not None:
                cbl_error(
                    "Failed to start multipeer replicator (see trace log for details)"
                )
                cbl_trace(resp.error.message)
                return None

            cast_resp = cast(PostStartMultipeerReplicatorResponseMethods, resp)
            self.__id = cast_resp.replicator_id

    async def stop(self) -> None:
        """
        Stops the multipeer replicator
        """
        with self.__tracer.start_as_current_span("stop_multipeer_replicator"):
            if not self.__id:
                cbl_error("Cannot stop multipeer replicator, it has not been started")
                return None

            req = self.__request_factory.create_request(
                TestServerRequestType.STOP_MULTIPEER_REPLICATOR,
                id=self.__id,
            )
            resp = await self.__request_factory.send_request(self.__index, req)
            if resp.error is not None:
                cbl_error(
                    "Failed to stop multipeer replicator (see trace log for details)"
                )
                cbl_trace(resp.error.message)
                return

            self.__id = ""

    async def get_status(self) -> MultipeerReplicatorStatus:
        """
        Gets the status of the multipeer replicator
        """
        with self.__tracer.start_as_current_span("get_multipeer_replicator_status"):
            if not self.__id:
                raise CblTestError("MultipeerReplicator start call has not completed!")

            req = self.__request_factory.create_request(
                TestServerRequestType.MULTIPEER_REPLICATOR_STATUS,
                id=self.__id,
            )
            resp = await self.__request_factory.send_request(self.__index, req)
            cast_resp = cast(PostGetMultipeerReplicatorStatusResponseMethods, resp)
            return MultipeerReplicatorStatus(cast_resp.replicators)

    async def wait_for_idle(
        self,
        interval: timedelta = timedelta(seconds=1),
        timeout: timedelta = timedelta(seconds=30),
    ) -> MultipeerReplicatorStatus:
        """
        Waits for a given timeout, polling at a set interval, until the Replicator changes to a desired state

        :param activity: The activity level to wait for
        :param interval: The polling interval (default 1s)
        :param timeout: The time limit to wait for the state change (default 30s)
        """
        with self.__tracer.start_as_current_span("wait_for"):
            assert interval.total_seconds() > 0.0, (
                "Zero interval makes no sense, try again"
            )
            assert timeout.total_seconds() >= 1.0, (
                "Timeout too short, must be at least 1 second"
            )

            all_idle = False
            start = time()
            next_status: MultipeerReplicatorStatus = MultipeerReplicatorStatus([])
            while not all_idle:
                elapsed = time() - start
                if elapsed > timeout.total_seconds():
                    raise CblTimeoutError("Timeout waiting for replicator status")

                next_status = await self.get_status()
                all_idle = len(next_status.replicators) > 0 and all(
                    r.status.activity == ReplicatorActivityLevel.IDLE
                    for r in next_status.replicators
                )
                if not all_idle:
                    await asyncio.sleep(interval.total_seconds())

            return next_status
