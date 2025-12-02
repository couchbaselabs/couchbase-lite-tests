from __future__ import annotations

import importlib
import traceback
from enum import Enum
from pathlib import Path
from shutil import rmtree
from typing import cast
from uuid import UUID, uuid4

from aiohttp import ClientSession

from .api.error import CblTestServerBadResponseError
from .api.jsonserializable import JSONSerializable
from .configparser import ParsedConfig, TransportType
from .httplog import get_next_writer
from .logging import cbl_error, cbl_info
from .request_types import GetRootRequest, TestServerRequest
from .requests_transport import RequestTransportFactory
from .responses import TestServerResponse, _response_registry
from .websocket_router import WebSocketRouter


class TestServerRequestType(Enum):
    ROOT = "GetRootRequest"
    RESET = "PostResetRequest"
    ALL_DOC_IDS = "PostGetAllDocumentsRequest"
    UPDATE_DB = "PostUpdateDatabaseRequest"
    START_REPLICATOR = "PostStartReplicatorRequest"
    REPLICATOR_STATUS = "PostGetReplicatorStatusRequest"
    SNAPSHOT_DOCS = "PostSnapshotDocumentsRequest"
    VERIFY_DOCS = "PostVerifyDocumentsRequest"
    PERFORM_MAINTENANCE = "PostPerformMaintenanceRequest"
    RUN_QUERY = "PostRunQueryRequest"
    GET_DOCUMENT = "PostGetDocumentRequest"
    NEW_SESSION = "PostNewSessionRequest"
    LOG = "PostLogRequest"
    START_LISTENER = "PostStartListenerRequest"
    STOP_LISTENER = "PostStopListenerRequest"
    START_MULTIPEER_REPLICATOR = "PostStartMultipeerReplicatorRequest"
    STOP_MULTIPEER_REPLICATOR = "PostStopMultipeerReplicatorRequest"
    MULTIPEER_REPLICATOR_STATUS = "PostGetMultipeerReplicatorStatusRequest"

    def __str__(self) -> str:
        return self.value


_request_registry: dict[tuple[TestServerRequestType, int], type] = {}
_body_registry: dict[tuple[TestServerRequestType, int], type] = {}


def register_request(request_type: TestServerRequestType, version: int | list[int]):
    def deco(cls: type[TestServerRequest]) -> type:
        if isinstance(version, list):
            for v in version:
                _request_registry[(request_type, v)] = cls
        else:
            _request_registry[(request_type, version)] = cls
        return cls

    return deco


def register_body(request_type: TestServerRequestType, version: int | list[int]):
    def deco(cls: type[JSONSerializable]) -> type:
        if isinstance(version, list):
            for v in version:
                _body_registry[(request_type, v)] = cls
        else:
            _body_registry[(request_type, version)] = cls
        return cls

    return deco


class RequestFactory:
    """
    This class is responsible for creating requests to send to the test server in a way
    that is auditable and understandable, as well as reusing any state set.

    It will be created by :class:`CBLPyTest` using the parsed configuration.  It will log
    every HTTP request and response into a folder called "http_log"
    """

    __first_run: bool = True

    def __init__(self, config: ParsedConfig):
        self.__record_path = Path("http_log")
        self.__version = 0
        if RequestFactory.__first_run:
            if self.__record_path.exists():
                rmtree(self.__record_path)

        RequestFactory.__first_run = False

        if not self.__record_path.exists():
            self.__record_path.mkdir()

        self.__uuid = uuid4()
        self.__server_infos: list[tuple[str, TransportType]] = []
        self.__session = ClientSession()
        ws_urls: list[str] = []
        for ts in config.test_servers:
            transport = cast(str, ts.get("transport", TransportType.HTTP.value)).lower()
            next_url = cast(str, ts.get("url"))
            if transport == TransportType.HTTP.value:
                self.__server_infos.append((next_url, TransportType.HTTP))
            else:
                ws_urls.append(next_url)
                self.__server_infos.append((next_url, TransportType.WS))

        self.__ws_router = WebSocketRouter(ws_urls)

        cbl_info(f"RequestFactory created ({self.__uuid})")

    @property
    def version(self) -> int:
        """Gets the API version that this factory is using"""
        assert self.__version > 0, "API version not set"
        return self.__version

    @version.setter
    def version(self, value: int) -> None:
        assert self.__version == 0, "API version can only be set once"
        self.__version = value

        for api_version in range(1, self.__version + 1):
            importlib.import_module(f"cbltest.v{api_version}.requests")
            importlib.import_module(f"cbltest.v{api_version}.responses")

        for request_tuple in _request_registry:
            version = request_tuple[1]
            request_cls = _request_registry[request_tuple]
            if (request_cls, version) not in _response_registry:
                raise ValueError(
                    f"Response type for '{request_cls}' not registered for version {version}!"
                )

        cbl_info(
            f"RequestFactory ({self.__uuid}) initialized for version {self.__version}"
        )

    @property
    def uuid(self) -> UUID:
        """Gets the UUID identifying this request factory"""
        return self.__uuid

    async def start(self) -> None:
        await self.__ws_router.start()

    def _create_request(
        self, type: TestServerRequestType, **kwargs
    ) -> TestServerRequest:
        if (type, self.__version) not in _request_registry:
            raise ValueError(
                f"Request type '{type}' not registered for version {self.__version}"
            )

        request_class = _request_registry[(type, self.__version)]
        payload = self._create_body(type, **kwargs)
        return cast(
            TestServerRequest, request_class(self.__version, self.__uuid, payload)
        )

    def create_request(
        self, type: TestServerRequestType, **kwargs
    ) -> TestServerRequest:
        """
        Creates a request to send.

        :param type: The type of request to create
        :param payload: The payload to send with the request
        """
        return (
            GetRootRequest(self.__uuid)
            if type == TestServerRequestType.ROOT
            else self._create_request(type, **kwargs)
        )

    def _create_body(
        self, type: TestServerRequestType, **kwargs
    ) -> JSONSerializable | None:
        if type == TestServerRequestType.ROOT:
            return None

        if (type, self.__version) not in _body_registry:
            raise ValueError(
                f"Request body type '{type}' not registered for version {self.__version}"
            )

        body_class = _body_registry[(type, self.__version)]
        return cast(JSONSerializable, body_class(**kwargs))

    async def send_request(
        self, index: int, r: TestServerRequest
    ) -> TestServerResponse:
        """Sends a request to the URL at the provided index (as indexes by test_servers in
        the JSON configuration file)"""
        writer = get_next_writer()
        server_info = self.__server_infos[index]
        header = f"{r} @ TS-{index}"
        writer.write_begin(
            header, r.payload.serialize() if r.payload is not None else ""
        )

        try:
            transport = RequestTransportFactory.get_transport(
                server_info[1],
                server_info[0],
                session=self.__session,
                ws_router=self.__ws_router,
            )
            ret_val = await transport.send(r, writer.num)
        except CblTestServerBadResponseError as e:
            cbl_error(f"Failed to send {r} to {server_info[0]} ({str(e)})")
            msg = f"{str(e)}\n\n{e.response.serialize()}"
            writer.write_error(msg)
            raise
        except Exception as e:
            cbl_error(f"Failed to send {r} to {server_info[0]} ({str(e)})")
            writer.write_error(traceback.format_exc())
            raise

        writer.write_end(str(ret_val), ret_val.serialize())
        return ret_val

    async def close(self) -> None:
        await self.__ws_router.stop()
        if not self.__session.closed:
            await self.__session.close()
