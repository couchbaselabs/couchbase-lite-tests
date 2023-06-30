import asyncio
from time import time
from typing import List, cast

from cbltest.logging import cbl_error, cbl_trace
from cbltest.v1.responses import PostGetReplicatorStatusResponse, PostStartReplicatorResponse
from cbltest.v1.requests import PostGetReplicatorStatusRequestBody, PostStartReplicatorRequestBody
from cbltest.requests import TestServerRequestType
from cbltest.api.error import CblTestError, CblTimeoutError
from cbltest.api.database import Database
from cbltest.api.replicator_types import ReplicatorActivityLevel, ReplicatorAuthenticator, ReplicatorCollectionEntry, ReplicatorType, ReplicatorStatus

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
        return self.__id is not None

    def __init__(self, database: Database, endpoint: str, replicator_type: ReplicatorType = ReplicatorType.PUSH_AND_PULL,
                 continuous: bool = False, authenticator: ReplicatorAuthenticator = None, reset: bool = False,
                 collections: List[ReplicatorCollectionEntry] = []):
        assert(database._request_factory.version == 1)
        self.__database = database
        self.__index = database._index
        self.__request_factory = database._request_factory
        self.__endpoint = endpoint
        self.__id: str = None
        self.replicator_type = replicator_type
        """The direction of the replicator"""

        self.continuous = continuous
        """Whether or not this replicator is continuous"""

        self.authenticator = authenticator
        """The authenticator to use, if any"""

        self.reset = reset
        """Whether or not to restart the replicator from the beginning"""

        self.collections = collections if collections is not None else []
        """The collections to use in this replication"""

    def add_default_collection(self) -> None:
        """A convenience method for adding the default config for the default collection, if desired"""
        self.collections.append(ReplicatorCollectionEntry())

    async def start(self) -> None:
        """
        Sends a replicatorStart request to the remote server
        """
        payload = PostStartReplicatorRequestBody(self.__database.name, self.__endpoint)
        payload.replicatorType = self.replicator_type
        payload.continuous = self.continuous
        payload.authenticator = self.authenticator
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
        if resp.error is not None:
            cbl_error("Failed to get replicator status (see trace log for details)")
            cbl_trace(resp.error.message)
            return None
        
        cast_resp = cast(PostGetReplicatorStatusResponse, resp)
        return ReplicatorStatus(cast_resp.progress, cast_resp.activity, cast_resp.replicator_error)
    
    async def wait_for(self, activity: ReplicatorActivityLevel, interval: float = 1.0, 
                       timeout: float = 30.0) -> ReplicatorStatus:
        """
        Waits for a given timeout, polling at a set interval, until the Replicator changes to a desired state

        :param activity: The activity level to wait for
        :param interval: The polling interval (default 1s)
        :param timeout: The time limit to wait for the state change
        """
        assert(interval > 0.0)
        assert(timeout > 1.0)

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
        

        
