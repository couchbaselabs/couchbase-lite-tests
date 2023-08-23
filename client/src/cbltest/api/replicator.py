import asyncio
from itertools import islice
from time import time
from typing import List, cast, Optional, Set

from cbltest.logging import cbl_error, cbl_trace
from cbltest.v1.responses import PostGetReplicatorStatusResponse, PostStartReplicatorResponse
from cbltest.v1.requests import PostGetReplicatorStatusRequestBody, PostStartReplicatorRequestBody
from cbltest.requests import TestServerRequestType
from cbltest.api.error import CblTestError, CblTimeoutError
from cbltest.api.database import Database
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel, ReplicatorAuthenticator, ReplicatorCollectionEntry, 
    ReplicatorType, ReplicatorStatus, ReplicatorDocumentEntry, WaitForDocumentEventEntry)

class Replicator:
    """
    A class representing a Couchbase Lite replicator inside of a test server
    """
    @property
    def database(self) -> Database:
        """Gets the database that this replicator is using"""
        return self.__database
    
    @property
    def endpoint(self) -> str:
        """Gets the remote endpoint URL that this replicator is using"""
        return self.__endpoint
    
    @property
    def is_started(self) -> bool:
        """Returns `True` if the replicator has started"""
        return self.__id != ""
    
    @property
    def document_updates(self) -> List[ReplicatorDocumentEntry]:
        """
        Gets the list of document updates received from the server and caches them.
        
        .. note:: These entries will persist indefinitely until 
            :func:`clear_document_entries()<cbltest.api.replicator.Replicator.clear_document_entries>`
            is called

        
        """
        return self.__document_updates

    def __init__(self, database: Database, endpoint: str, replicator_type: ReplicatorType = ReplicatorType.PUSH_AND_PULL,
                 continuous: bool = False, authenticator: Optional[ReplicatorAuthenticator] = None, reset: bool = False,
                 collections: List[ReplicatorCollectionEntry] = [], enable_document_listener: bool = False,
                 enable_auto_purge: bool = True):
        assert database._request_factory.version == 1, "This version of the cbl test API requires request API v1"
        self.__database = database
        self.__index = database._index
        self.__request_factory = database._request_factory
        self.__endpoint = endpoint
        self.__id: str = ""
        self.__document_updates: List[ReplicatorDocumentEntry] = []
        self.replicator_type: ReplicatorType = replicator_type
        """The direction of the replicator"""

        self.continuous: bool = continuous
        """Whether or not this replicator is continuous"""

        self.authenticator: Optional[ReplicatorAuthenticator] = authenticator
        """The authenticator to use, if any"""

        self.reset: bool = reset
        """Whether or not to restart the replicator from the beginning"""

        self.collections: List[ReplicatorCollectionEntry] = collections if collections is not None else []
        """The collections to use in this replication"""

        self.enable_document_listener: bool = enable_document_listener
        """If True, document updates will be present in calls to get_status"""

        self.enable_auto_purge: bool = enable_auto_purge
        """If True (default) auto purge is enabled for the replicator so documents will be automatically
        removed when access is lost"""

    def add_default_collection(self) -> None:
        """A convenience method for adding the default config for the default collection, if desired"""
        self.collections.append(ReplicatorCollectionEntry())

    def clear_document_updates(self) -> None:
        """Clears the cached document updates received so far by the server"""
        self.__document_updates.clear()

    async def start(self) -> None:
        """
        Sends a replicatorStart request to the remote server
        """
        payload = PostStartReplicatorRequestBody(self.__database.name, self.__endpoint)
        payload.replicatorType = self.replicator_type
        payload.continuous = self.continuous
        payload.authenticator = self.authenticator
        payload.enableDocumentListener = self.enable_document_listener
        payload.enableAutoPurge = self.enable_auto_purge
        payload.reset = self.reset
        payload.collections = self.collections
        req = self.__request_factory.create_request(TestServerRequestType.START_REPLICATOR, payload)
        resp = await self.__request_factory.send_request(self.__index, req)
        if resp.error is not None:
            cbl_error("Failed to start replicator (see trace log for details)")
            cbl_trace(resp.error.message)
            return None
        
        cast_resp = cast(PostStartReplicatorResponse, resp)
        self.__id = cast_resp.replicator_id

    async def get_status(self) -> ReplicatorStatus:
        """Sends a getReplicatorStatus message to the server and returns the results"""
        if not self.is_started:
            raise CblTestError("Replicator start call has not completed!")
        
        payload = PostGetReplicatorStatusRequestBody(self.__id)
        req = self.__request_factory.create_request(TestServerRequestType.REPLICATOR_STATUS, payload)
        resp = await self.__request_factory.send_request(self.__index, req)
        cast_resp = cast(PostGetReplicatorStatusResponse, resp)
        self.__document_updates.extend(cast_resp.documents)
        return ReplicatorStatus(cast_resp.progress, cast_resp.activity, cast_resp.replicator_error)
    
    async def wait_for(self, activity: ReplicatorActivityLevel, interval: float = 1.0, 
                       timeout: float = 30.0) -> ReplicatorStatus:
        """
        Waits for a given timeout, polling at a set interval, until the Replicator changes to a desired state

        :param activity: The activity level to wait for
        :param interval: The polling interval (default 1s)
        :param timeout: The time limit to wait for the state change
        """
        assert interval > 0.0, "Zero interval makes no sense, try again"
        assert timeout > 1.0, "Timeout too short, must be at least 1 second"

        status_matches = False
        start = time()
        while not status_matches:
            elapsed = time() - start
            if(elapsed > timeout):
                raise CblTimeoutError("Timeout waiting for replicator status")
            
            next_status = await self.get_status()
            status_matches = next_status.activity == activity
            if not status_matches:
                await asyncio.sleep(interval)

            
        return next_status
        
    async def wait_for_doc_events(self, events: Set[WaitForDocumentEventEntry], max_retries: int = 5) -> ReplicatorStatus:
        """
        This function will wait for a continuous replicator to become idle, and then check for document
        replication events to determine if it has reached a certain point or not.

        :param events: The events to check for on the replicator
        :param max_retries: The max number of retries before giving up (default 5)
        """
        assert self.continuous, "wait_for_doc_events not applicable for non-continuous replicator"
        events = events.copy()
        iteration = 0
        processed = 0
        while iteration < max_retries:
            status = await self.wait_for(ReplicatorActivityLevel.IDLE)
            assert status.error is None, \
                f"Error waiting for replicator: ({status.error.domain} / {status.error.code}) {status.error.message}"
            
            # Skip the ones we previously looked at to save time
            for event in islice(self.document_updates, processed, None):
                entry = WaitForDocumentEventEntry(event.collection, event.document_id)
                if entry in events:
                    events.remove(entry)

                processed += 1

            if len(events) == 0:
                return status
            
            await asyncio.sleep(0.5)
            iteration += 1

        raise CblTimeoutError("Timeout waiting for document update events")
