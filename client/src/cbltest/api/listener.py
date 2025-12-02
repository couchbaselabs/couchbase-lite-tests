from typing import cast

from opentelemetry.trace import get_tracer

from cbltest.api.database import Database
from cbltest.logging import cbl_error, cbl_trace
from cbltest.requests import TestServerRequestType
from cbltest.response_types import PostStartListenerResponseMethods
from cbltest.version import VERSION


class Listener:
    """A class representing the passive side of a replication inside of a test server"""

    def __init__(
        self,
        database: Database,
        collections: list[str],
        port: int | None = None,
        disable_tls: bool = False,
    ):
        self.database = database
        """The database that the listener will be serving"""

        self.collections = collections
        """The collections within the database that the listener will be serving"""

        self.port = port
        """
        The port that the listener will request to listen on
        (if None, the OS will choose).  Once start is called,
        this will be overwritten with the real port.  If
        stop is called, it will be set back to the original
        value
        """

        self.disable_tls = disable_tls
        """If True, TLS will be disabled for the listener"""

        self.__original_port = port
        self.__index = database._index
        self.__request_factory = database._request_factory
        self.__tracer = get_tracer(__name__, VERSION)
        self.__id: str = ""

    async def start(self) -> None:
        """Start listening for incoming connections"""
        with self.__tracer.start_as_current_span("start_listener"):
            request = self.__request_factory.create_request(
                TestServerRequestType.START_LISTENER,
                db=self.database.name,
                collections=self.collections,
                port=self.port,
                disable_tls=self.disable_tls,
            )
            resp = await self.__request_factory.send_request(self.__index, request)
            if resp.error is not None:
                cbl_error("Failed to start replicator (see trace log for details)")
                cbl_trace(resp.error.message)
                return

            cast_resp = cast(PostStartListenerResponseMethods, resp)
            self.port = cast_resp.port
            self.__id = cast_resp.listener_id

    async def stop(self) -> None:
        """Stop listening for incoming connections"""
        with self.__tracer.start_as_current_span("stop_listener"):
            request = self.__request_factory.create_request(
                TestServerRequestType.STOP_LISTENER,
                id=self.__id,
            )
            resp = await self.__request_factory.send_request(self.__index, request)
            if resp.error is not None:
                cbl_error("Failed to stop replicator (see trace log for details)")
                cbl_trace(resp.error.message)
                return

            self.port = self.__original_port
            self.__id = ""
