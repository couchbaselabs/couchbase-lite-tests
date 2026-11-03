import asyncio
from enum import Enum
from typing import Final, assert_never, cast
from urllib.parse import urljoin, urlparse

import asyncstdlib
from opentelemetry.trace import get_tracer
from packaging.version import Version

from cbltest.api.database import Database
from cbltest.assertions import _assert_not_null
from cbltest.globals import CBLPyTestGlobal
from cbltest.request_types import PostResetRequestMethods
from cbltest.requests import RequestFactory, TestServerRequestType
from cbltest.responses import GetRootResponse, ServerVariant
from cbltest.version import VERSION


class CouchbaseLiteFeature(Enum):
    """CBL features that not every test server supports. Each value names the feature in skip messages."""

    # LiteCore-based platforms from 4.0.0. CBL JS and CBL React Native do not support them yet.
    VERSION_VECTORS = "version vectors"
    # CBL iOS and CBL Android from 3.3.0.
    MULTIPEER = "multipeer replication"
    # LiteCore-based platforms.
    LEGACY_P2P = "legacy peer-to-peer replication"
    # CBL JS does not support it.
    DELTA_SYNC = "delta sync"
    # The CBL JS WebSocket library cannot send them.
    CUSTOM_REPLICATOR_HEADERS = "custom replicator headers"
    # CBL React Native has no API for one.
    CUSTOM_CONFLICT_RESOLVER = "custom conflict resolver"
    # Only the CBL C test server implements it.
    PROPERTY_ENCRYPTION = "property encryption"


class TestServer:
    """
    A class for interacting with a Couchbase Lite test server
    """

    __dataset_base_url: Final[str] = (
        "https://media.githubusercontent.com/media/couchbaselabs/couchbase-lite-tests/refs/heads/main/dataset/server/dbs/"
    )

    @property
    def url(self) -> str:
        """Gets the URL of the test server being communicated with"""
        return self.__url

    @property
    def dataset_version(self) -> str:
        """Gets the dataset version of the test server instance"""
        return self.__dataset_version

    def __init__(
        self,
        request_factory: RequestFactory,
        index: int,
        url: str,
        dataset_version: str,
    ) -> None:
        self.__index = index
        self.__url = url
        self.__request_factory = request_factory
        self.__tracer = get_tracer(__name__, VERSION)
        self.__dataset_version = dataset_version

    @asyncstdlib.cached_property(asyncio.Lock)
    async def info(self) -> GetRootResponse:
        """Information about the running test server (fetched once)"""
        with self.__tracer.start_as_current_span("info"):
            request = self.__request_factory.create_request(TestServerRequestType.ROOT)
            resp = await self.__request_factory.send_request(self.__index, request)
            return cast(GetRootResponse, resp)

    async def supports(self, feature: CouchbaseLiteFeature) -> bool:
        """Returns whether this test server's CBL supports the given feature."""
        info = await self.info
        variant = info.variant
        version = Version(info.library_version.split("-")[0])
        match feature:
            case CouchbaseLiteFeature.VERSION_VECTORS:
                return variant not in ServerVariant.JS | ServerVariant.REACT_NATIVE and version >= Version("4.0.0")
            case CouchbaseLiteFeature.MULTIPEER:
                return variant in ServerVariant.IOS | ServerVariant.ANDROID and version >= Version("3.3.0")
            case CouchbaseLiteFeature.LEGACY_P2P:
                return variant not in ServerVariant.JS | ServerVariant.REACT_NATIVE
            case CouchbaseLiteFeature.DELTA_SYNC | CouchbaseLiteFeature.CUSTOM_REPLICATOR_HEADERS:
                return variant != ServerVariant.JS
            case CouchbaseLiteFeature.CUSTOM_CONFLICT_RESOLVER:
                return variant != ServerVariant.REACT_NATIVE
            case CouchbaseLiteFeature.PROPERTY_ENCRYPTION:
                return variant == ServerVariant.C
            case _:
                assert_never(feature)

    async def create_and_reset_db(
        self,
        db_names: list[str],
        dataset: str | None = None,
        collections: list[str] | None = None,
    ) -> list[Database]:
        """
        Creates and returns a set of Databases based on the given dataset

        :param db_names: A list of database names, each of which will become a database based on
                         the other two args
        :param dataset: The name of the dataset to use for creating the databases (if not specified
                        an empty database will be created).  Cannot be combined with collections.
        :param collections: The name of the collections to add after creating the database.  Cannot
                            be combined with dataset.
        """
        assert collections is None or dataset is None, "dataset and collections cannot both be specified"

        with self.__tracer.start_as_current_span("create_and_reset_db"):
            request = self.__request_factory.create_request(
                TestServerRequestType.RESET,
                name=CBLPyTestGlobal.running_test_name,
            )
            payload = cast(PostResetRequestMethods, request.payload)
            if dataset is not None:
                dataset_url = self.__dataset_base_url + self.__dataset_version + "/" + f"{dataset}.cblite2.zip"
                payload.add_dataset(dataset_url, db_names)
            else:
                payload.add_empty(db_names, collections)

            await self.__request_factory.send_request(self.__index, request)
            ret_val: list[Database] = []
            for db_name in db_names:
                ret_val.append(Database(self.__request_factory, self.__index, db_name))

            return ret_val

    async def new_session(self, id: str, url: str | None, tag: str | None) -> None:
        """
        Instructs this test server to log to the given LogSlurp instance

        :param url: The URL of the LogSlurp server
        :param id: The ID of the log to log to
        :param tag: The tag to use for this test server
        """
        with self.__tracer.start_as_current_span("new_session"):
            request = self.__request_factory.create_request(
                TestServerRequestType.NEW_SESSION,
                id=id,
                dataset_version=self.__dataset_version,
                url=url,
                tag=tag,
            )
            await self.__request_factory.send_request(self.__index, request)

    async def cleanup(self) -> None:
        """
        Resets the test server
        """
        with self.__tracer.start_as_current_span("create_and_reset_db"):
            request = self.__request_factory.create_request(TestServerRequestType.RESET)
            await self.__request_factory.send_request(self.__index, request)

    async def log(self, msg: str) -> None:
        """
        Sends a message to be logged on the server side.  Useful for debugging.
        """

        # I'll exclude this from telemetry since it's not really related to any testing
        request = self.__request_factory.create_request(
            TestServerRequestType.LOG,
            msg=msg,
        )
        await self.__request_factory.send_request(self.__index, request)

    def replication_url(self, db_name: str, port: int, tls: bool = False) -> str:
        """
        Returns the URL of the replication endpoint for this test server
        """
        ws_scheme = "ws://"  # For now not using secure
        if tls:
            ws_scheme = "wss://"
        _assert_not_null(db_name, "db_name")

        parsed = urlparse(self.url)
        if parsed.hostname:
            hostname = parsed.hostname
        elif parsed.netloc:
            hostname = parsed.netloc.split(":")[0]
        else:
            hostname = self.url.split("://")[-1].split(":")[0]
        replication_url = f"{ws_scheme}{hostname}:{port}"
        return urljoin(replication_url, db_name)
