from __future__ import annotations
from abc import abstractmethod
from enum import Enum
from pathlib import Path
from shutil import rmtree
from typing import cast, Optional, Type
from urllib.parse import urljoin
from uuid import UUID, uuid4
from aiohttp import ClientSession, ClientResponse
from importlib import import_module
from typing import Any

from .configparser import ParsedConfig
from .logging import cbl_error, cbl_info, cbl_trace, cbl_warning
from .responses import GetRootResponse, TestServerResponse
from .version import available_api_version
from .httplog import get_next_writer
from .api.jsonserializable import JSONSerializable
from .api.error import CblTestError, CblTestServerBadResponseError
from .globals import CBLPyTestGlobal

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

    def __str__(self) -> str:
        return self.value
    

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
    def payload(self) -> Optional[TestServerRequestBody]:
        """Gets the body of the request.  The actual type is simply the request typename with 'Body' appended.
        
        E.g. PostResetRequest -> PostResetRequestBody"""
        return self.__payload
    
    def __init__(self, version: int, uuid: UUID, http_name: str, payload_type: Optional[Type] = None, 
                 method: str = "post", payload: Optional[TestServerRequestBody] = None):
        # For those subclassing this, usually all you need to do is call this constructor
        # filling out the appropriate information via args
        if payload is not None and payload_type is not None:
            assert isinstance(payload, payload_type), f"Incorrect payload type for request (expecting '{payload_type}')"

        self.__version = available_api_version(version)
        self.__uuid = uuid
        self.__payload = payload
        self.__http_name = http_name
        self.__method = method
        self.__test_name = CBLPyTestGlobal.running_test_name
    
    def _http_name(self) -> str:
        return f"v1 {self.__method.capitalize()} /{self.__http_name}"
    
    async def _create_response(self, r: ClientResponse, version: int, uuid: str) -> TestServerResponse:
        module = import_module(f"cbltest.v{version}.responses")
        class_name = type(self).__name__.replace("Request", "Response")
        response_class = getattr(module, class_name)
        content: dict = {}
        if r.content_length != 0:
            content_type = r.headers["Content-Type"]
            if "application/json" not in content_type:
                cbl_warning(f"Non-JSON response body received from server ({content_type}), ignoring...")
            else:
                content = await r.json()

        return cast(TestServerResponse, response_class(r.status, uuid, content))
    
    async def send(self, url: str, session: Optional[ClientSession] = None) -> TestServerResponse:
        """
        Send the request to the specified URL, though `RequestFactory.send_request` is preferred.
        
        :param url: The URL to send the request to
        :param session: The requests library session to use when transmitting the HTTP message
        """
        cbl_trace(f"Sending {self} to {url}")
        headers = {}
        headers["Accept"] = "application/json"
        if self.__version > 0:
            headers["CBLTest-API-Version"] = str(self.__version)
            headers["CBLTest-Client-ID"] = str(self.__uuid)

        if self.__test_name is not None:
            headers["CBLTest-Test-Name"] = self.__test_name
        
        data: str | None = None
        if self.__payload is not None:
            headers["Content-Type"] = "application/json"
            data = self.__payload.serialize() 

        if session is not None:
            resp = await session.request(self.__method, urljoin(url, self.__http_name), headers=headers, data=data)
        else:
            async with ClientSession() as s:
                resp = await s.request(self.__method, urljoin(url, self.__http_name), headers=headers, data=data)

        resp_version_header = resp.headers.get("CBLTest-API-Version")
        uuid = resp.headers.get("CBLTest-Server-ID")
        if uuid is None:
            raise CblTestError("Missing CBLTest-Server-ID header from response")
        
        resp_version = int(resp_version_header) if resp_version_header is not None else 0
        if resp_version != self.__version:
            if resp_version == 0:
                cbl_warning("Server did not set a response version, using request version...")
                resp_version = self.__version
            elif self.__version != 0:
                cbl_warning(f"Response version for {resp_version} does not match request version {self.__version}!")

        ret_val = await self._create_response(resp, resp_version, cast(str, uuid))
        cbl_trace(f"Received {ret_val} from {url}")
        if not resp.ok:
            raise CblTestServerBadResponseError(resp.status, ret_val, f"{self} returned {resp.status}")

        return ret_val
    
    def __str__(self) -> str:
        test_name = self.__test_name if self.__test_name is not None else "test name not set!"
        return f"({test_name}) -> {self.__uuid} v{self.__version} {self.__method.upper()} /{self.__http_name}"

# Only this request is not versioned
class GetRootRequest(TestServerRequest):
    """
    The GET / request.  This API endpoint is not versioned and can be used to
    verify the API version of the server, among other things
    """
    def __init__(self, uuid: UUID):
        super().__init__(0, uuid, "", method="get")
    
    async def _create_response(self, r: ClientResponse, version: int, uuid: str) -> TestServerResponse:
        return GetRootResponse(r.status, uuid, await r.json())


class RequestFactory:
    """
    This class is responsible for creating requests to send to the test server in a way
    that is auditable and understandable, as well as reusing any state set.

    It will be created by :class:`CBLPyTest` using the parsed configuration.  It will log
    every HTTP request and response into a folder called "http_log"
    """

    __first_run: bool = True

    @property
    def version(self) -> int:
        """Gets the API version that this factory is using"""
        return self.__version
    
    def __init__(self, config: ParsedConfig):
        self.__record_path = Path("http_log")
        if RequestFactory.__first_run and self.__record_path.exists():
            rmtree(self.__record_path)

        RequestFactory.__first_run = False

        if not self.__record_path.exists():
            self.__record_path.mkdir()

        self.__uuid = uuid4()
        self.__session = ClientSession()
        self.__version = available_api_version(config.api_version)
        self.__server_urls = config.test_servers
        cbl_info(f"RequestFactory created with API version {self.__version} ({self.__uuid})")
        

    def _create_request(self, name: str, payload: Optional[TestServerRequestBody] = None) -> TestServerRequest:
        if payload is not None and self.__version != payload.version:
            raise ValueError(f"Request factory version {self.__version} does not match payload version {payload.version}!")
        
        module = import_module(f"cbltest.v{self.__version}.requests")
        request_class = getattr(module, name)
        if payload is None:
            return cast(TestServerRequest, request_class(self.__uuid))
        
        return cast(TestServerRequest, request_class(self.__uuid, payload))
    
    def create_request(self, type: TestServerRequestType, payload: Optional[TestServerRequestBody] = None) -> TestServerRequest:
        """
        Creates a request to send.

        :param type: The type of request to create
        :param payload: The payload to send with the request
        """
        if type != TestServerRequestType.ROOT and payload is None:
            raise ValueError("No payload provided!")
        
        return GetRootRequest(self.__uuid) if type == TestServerRequestType.ROOT else self._create_request(str(type), payload)
    
    async def send_request(self, index: int, r: TestServerRequest) -> TestServerResponse:
        """Sends a request to the URL at the provided index (as indexes by test_servers in
        the JSON configuration file)"""
        writer = get_next_writer()
        url = self.__server_urls[index]
        writer.write_begin(str(r), r.payload.serialize() if r.payload is not None else "")
        
        try:
            ret_val = await r.send(url, self.__session)
        except CblTestServerBadResponseError as e:
            cbl_error(f"Failed to send {r} ({str(e)})")
            msg = f"{str(e)}\n\n{e.response.serialize()}"
            writer.write_error(msg)
            raise
        except Exception as e:
            cbl_error(f"Failed to send {r} ({str(e)})")
            writer.write_error(str(e))
            raise
        
        writer.write_end(str(ret_val), ret_val.serialize())
        return ret_val
    
    
