import json
from abc import ABC, abstractmethod
from importlib import import_module
from typing import cast
from urllib.parse import urljoin
from uuid import uuid4

from aiohttp import ClientResponse, ClientSession

from cbltest.api.error import CblTestError, CblTestServerBadResponseError
from cbltest.configparser import TransportType
from cbltest.globals import CBLPyTestGlobal
from cbltest.logging import cbl_trace, cbl_warning
from cbltest.request_types import GetRootRequest, TestServerRequest, TestServerResponse
from cbltest.websocket_router import WebSocketRouter


class RequestTransport(ABC):
    @abstractmethod
    async def send(
        self, request: TestServerRequest, message_no: int
    ) -> TestServerResponse:
        pass


class _RequestHttpTransport(RequestTransport):
    def __init__(self, url: str, session: ClientSession):
        self.__url = url
        self.__session = session

    async def send(
        self, request: TestServerRequest, message_no: int
    ) -> TestServerResponse:
        cbl_trace(f"Sending {self} to {self.__url}")
        headers = {}
        headers["Accept"] = "application/json"
        if request.version > 0:
            headers["CBLTest-API-Version"] = str(request.version)
            headers["CBLTest-Client-ID"] = str(request.uuid)
            headers["CBLTest-Request-ID"] = str(uuid4())

        if CBLPyTestGlobal.running_test_name is not None:
            headers["CBLTest-Test-Name"] = CBLPyTestGlobal.running_test_name

        data: str | None = None
        if request.payload is not None:
            headers["Content-Type"] = "application/json"
            data = request.payload.serialize()

        resp = await self.__session.request(
            request.method,
            urljoin(self.__url, request.http_name),
            headers=headers,
            data=data,
        )

        resp_version_header = resp.headers.get("CBLTest-API-Version")
        uuid = resp.headers.get("CBLTest-Server-ID")
        if uuid is None:
            raise CblTestError("Missing CBLTest-Server-ID header from response")

        resp_version = (
            int(resp_version_header) if resp_version_header is not None else 0
        )
        if resp_version != request.version:
            if resp_version == 0:
                cbl_warning(
                    "Server did not set a response version, using request version..."
                )
                resp_version = request.version
            elif request.version != 0:
                cbl_warning(
                    f"Response version for {resp_version} does not match request version {request.version}!"
                )

        if isinstance(request, GetRootRequest):
            ret_val = await cast(GetRootRequest, request)._create_response(
                cast(str, uuid), http=resp
            )
        else:
            ret_val = await self._create_response(
                type(request), resp, resp_version, cast(str, uuid)
            )

        cbl_trace(f"Received {ret_val} from {self.__url}")
        if not resp.ok:
            raise CblTestServerBadResponseError(
                resp.status, ret_val, f"{self} returned {resp.status}"
            )

        return ret_val

    async def _create_response(
        self, request_type: type, resp: ClientResponse, version: int, uuid: str
    ) -> TestServerResponse:
        module = import_module(f"cbltest.v{version}.responses")
        class_name = request_type.__name__.replace("Request", "Response")
        response_class = getattr(module, class_name)
        content: dict = {}
        if resp.content_length != 0:
            content_type = resp.headers["Content-Type"]
            if "application/json" not in content_type:
                cbl_warning(
                    f"Non-JSON response body received from server ({content_type}), ignoring..."
                )
            else:
                content = await resp.json()

        return cast(TestServerResponse, response_class(resp.status, uuid, content))


class _RequestWebSocketTransport(RequestTransport):
    def __init__(self, url: str, ws_router: WebSocketRouter):
        self.__url = url
        self.__ws_router = ws_router

    async def send(
        self, request: TestServerRequest, message_no: int
    ) -> TestServerResponse:
        if request.payload is not None:
            data = cast(dict, request.payload.to_json())
        else:
            data = {}

        data["ts_id"] = message_no
        data["ts_command"] = f"/{request.http_name}"

        cbl_trace(f"Sending {self} to {self.__url}")
        if request.version > 0:
            data["ts_clientID"] = request.uuid
            data["ts_apiVersion"] = request.version
            data["ts_requestID"] = str(uuid4())

        if CBLPyTestGlobal.running_test_name is not None:
            data["ts_testName"] = CBLPyTestGlobal.running_test_name

        future = self.__ws_router.register(data["ts_id"])
        ws_conn = self.__ws_router.get_websocket_for_write(self.__url)
        await ws_conn.send_str(json.dumps(data))
        resp = await future

        resp_version = cast(int, resp.get("ts_apiVersion", 0))
        uuid = resp.get("ts_serverID")
        if uuid is None:
            raise CblTestError("Missing ts_serverID from response")

        if resp_version != request.version:
            if resp_version == 0:
                cbl_warning(
                    "Server did not set a response version, using request version..."
                )
                resp_version = request.version
            elif request.version != 0:
                cbl_warning(
                    f"Response version for {resp_version} does not match request version {request.version}!"
                )

        if isinstance(request, GetRootRequest):
            ret_val = await cast(GetRootRequest, request)._create_response(
                cast(str, uuid), ws_payload=resp
            )
        else:
            ret_val = self._create_response(
                type(request), resp, resp_version, cast(str, uuid)
            )

        cbl_trace(f"Received {ret_val} from {self.__url}")
        if ret_val.status_code != 200:
            raise CblTestServerBadResponseError(
                ret_val.status_code, ret_val, f"{self} returned {ret_val.status_code}"
            )

        return ret_val

    def _create_response(
        self, request_type: type, ws_payload: dict, version: int, uuid: str
    ) -> TestServerResponse:
        module = import_module(f"cbltest.v{version}.responses")
        class_name = request_type.__name__.replace("Request", "Response")
        response_class = getattr(module, class_name)

        status = 200
        error = cast(dict | None, ws_payload.get("ts_error"))
        if error is not None:
            status = cast(int, error.get("code", 500))

        return cast(TestServerResponse, response_class(status, uuid, ws_payload))


class RequestTransportFactory:
    @staticmethod
    def get_transport(
        transport_type: TransportType,
        url: str,
        *,
        session: ClientSession | None,
        ws_router: WebSocketRouter | None,
    ) -> RequestTransport:
        if transport_type == TransportType.HTTP:
            if session is None:
                raise ValueError("ClientSession is required for HTTP transport")

            return _RequestHttpTransport(url, session)
        elif transport_type == TransportType.WS:
            if ws_router is None:
                raise ValueError("WebSocketRouter is required for WebSocket transport")

            return _RequestWebSocketTransport(url, ws_router)
        else:
            raise ValueError(f"Unknown transport type '{transport_type}'")
