from typing import cast

from opentelemetry.trace import get_tracer

from cbltest.api.database import Database
from cbltest.api.multipeer_replicator_types import MultipeerReplicatorAuthenticator
from cbltest.api.replicator import ReplicatorCollectionEntry
from cbltest.api.x509_certificate import CertKeyPair, create_leaf_certificate
from cbltest.logging import cbl_error, cbl_trace
from cbltest.requests import TestServerRequestType
from cbltest.v1.requests import (
    PostGetMultipeerReplicatorStatusRequestBody,
    PostStartMultipeerReplicatorRequestBody,
    PostStopMultipeerReplicatorRequestBody,
)
from cbltest.v1.responses import (
    MultipeerReplicatorStatusEntry,
    PostGetMultipeerReplicatorStatusResponse,
    PostStartMultipeerReplicatorResponse,
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
    ):
        assert database._request_factory.version == 1, (
            "This version of the cbl test API requires request API v1"
        )
        self.__index = database._index
        self.__request_factory = database._request_factory
        self.__peerGroupID = peerGroupID
        self.__database = database
        self.__authenticator = authenticator
        self.__identity = (
            identity if identity is not None else create_leaf_certificate("anonymous")
        )
        assert len(collections) > 0, "At least one collection is required"
        self.__collections = collections
        self.__tracer = get_tracer(__name__, VERSION)
        self.__id: str = ""

    async def start(self) -> None:
        """
        Starts the multipeer replicator
        """
        with self.__tracer.start_as_current_span("start_multipeer_replicator"):
            payload = PostStartMultipeerReplicatorRequestBody(
                self.__peerGroupID,
                self.__database.name,
                self.__collections,
                self.__identity,
                authenticator=self.__authenticator,
            )

            req = self.__request_factory.create_request(
                TestServerRequestType.START_MULTIPEER_REPLICATOR, payload
            )
            resp = await self.__request_factory.send_request(self.__index, req)
            if resp.error is not None:
                cbl_error(
                    "Failed to start multipeer replicator (see trace log for details)"
                )
                cbl_trace(resp.error.message)
                return None

            cast_resp = cast(PostStartMultipeerReplicatorResponse, resp)
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
                PostStopMultipeerReplicatorRequestBody(self.__id),
            )
            resp = await self.__request_factory.send_request(self.__index, req)
            if resp.error is not None:
                cbl_error(
                    "Failed to stop multipeer replicator (see trace log for details)"
                )
                cbl_trace(resp.error.message)
                return

            self.__id = ""

    async def get_status(self) -> MultipeerReplicatorStatus | None:
        """
        Gets the status of the multipeer replicator
        """
        with self.__tracer.start_as_current_span("get_multipeer_replicator_status"):
            if not self.__id:
                cbl_error(
                    "Cannot get status of multipeer replicator, it has not been started"
                )
                return None

            req = self.__request_factory.create_request(
                TestServerRequestType.MULTIPEER_REPLICATOR_STATUS,
                PostGetMultipeerReplicatorStatusRequestBody(self.__id),
            )
            resp = await self.__request_factory.send_request(self.__index, req)
            if resp.error is not None:
                cbl_error(
                    "Failed to get multipeer replicator status (see trace log for details)"
                )
                cbl_trace(resp.error.message)
                return None

            cast_resp = cast(PostGetMultipeerReplicatorStatusResponse, resp)
            return MultipeerReplicatorStatus(cast_resp.replicators)
