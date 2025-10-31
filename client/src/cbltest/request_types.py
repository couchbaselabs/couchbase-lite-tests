from abc import abstractmethod
from typing import Any, cast
from uuid import UUID

from aiohttp import ClientResponse

from cbltest.api.jsonserializable import JSONSerializable
from cbltest.globals import CBLPyTestGlobal
from cbltest.responses import GetRootResponse, TestServerResponse
from cbltest.version import available_api_version


class TestServerRequestBody(JSONSerializable):
    """The base class from which all request bodies derive"""

    @property
    def version(self) -> int:
        """The API version of the request body (must match the request itself)"""
        return self.__version

    def __init__(self, version: int):
        self.__version = available_api_version(version)

    @abstractmethod
    def to_json(self) -> Any:
        pass


class TestServerRequest:
    """The base class from which all requests derive, and in which all work is done"""

    @property
    def payload(self) -> TestServerRequestBody | None:
        """Gets the body of the request.  The actual type is simply the request typename with 'Body' appended.

        E.g. PostResetRequest -> PostResetRequestBody"""
        return self.__payload

    @property
    def version(self) -> int:
        """Gets the API version of the request"""
        return self.__version

    @property
    def uuid(self) -> str:
        """Gets the UUID of the client sending this request"""
        return str(self.__uuid)

    @property
    def http_name(self) -> str:
        """Gets the HTTP endpoint name of this request"""
        return self.__http_name

    @property
    def method(self) -> str:
        """Gets the HTTP method of this request"""
        return self.__method

    def __init__(
        self,
        version: int,
        uuid: UUID,
        http_name: str,
        payload_type: type | None = None,
        method: str = "post",
        payload: TestServerRequestBody | None = None,
    ):
        # For those subclassing this, usually all you need to do is call this constructor
        # filling out the appropriate information via args
        if payload is not None and payload_type is not None:
            assert isinstance(payload, payload_type), (
                f"Incorrect payload type for request (expecting '{payload_type}')"
            )

        self.__version = available_api_version(version)
        self.__uuid = uuid
        self.__payload = payload
        self.__http_name = http_name
        self.__method = method
        self.__test_name = CBLPyTestGlobal.running_test_name

    def __str__(self) -> str:
        test_name = (
            self.__test_name if self.__test_name is not None else "test name not set!"
        )
        return f"({test_name}) -> {self.__uuid} v{self.__version} {self.__method.upper()} /{self.__http_name}"


# Only this request is not versioned
class GetRootRequest(TestServerRequest):
    """
    The GET / request.  This API endpoint is not versioned and can be used to
    verify the API version of the server, among other things
    """

    def __init__(self, uuid: UUID):
        super().__init__(0, uuid, "", method="get")

    async def _create_response(
        self,
        uuid: str,
        *,
        http: ClientResponse | None = None,
        ws_payload: dict | None = None,
    ) -> TestServerResponse:
        if http is not None:
            return GetRootResponse(http.status, uuid, await http.json())

        if ws_payload is None:
            raise ValueError("Both http and ws_payload were None for GetRootRequest")

        status = 200
        error = cast(dict | None, ws_payload.get("ts_error"))
        if error is not None:
            status = cast(int, error.get("code", 500))

        return GetRootResponse(status, uuid, ws_payload)
