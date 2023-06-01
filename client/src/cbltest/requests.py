from __future__ import annotations
from abc import ABC, abstractmethod
from json import loads
from pathlib import Path
from shutil import rmtree
from typing import cast
from urllib.parse import urljoin
from uuid import UUID, uuid4
from requests import Request, Response, Session
from importlib import import_module

from .configparser import ParsedConfig
from .logging import cbl_error, cbl_info, cbl_trace, cbl_warning
from .responses import GetRootResponse, TestServerResponse
from .version import available_api_version

class TestServerRequestBody(ABC):
    """The base class from which all request bodies derive"""

    @property
    def version(self) -> int:
        """The API version of the request body (must match the request itself)"""
        return self.__version

    def __init__(self, version: int):
        self.__version = available_api_version(version)

    @abstractmethod
    def serialize(self) -> str:
        pass

class TestServerRequest:
    """The base class from which all requests derive, and in which all work is done"""
    __next_id: int = 1

    @property
    def number(self) -> int:
        """Gets the number of this request (to match it with a response in the http log)"""
        return self.__id
    
    @property
    def payload(self) -> TestServerRequestBody:
        """Gets the body of the request.  The actual type is simply the request typename with 'Body' appended.
        
        E.g. PostResetRequest -> PostResetRequestBody"""
        return self.__payload
    
    def __init__(self, version: int, uuid: UUID, http_name: str, payload_type = None, 
                 method: str = "post", payload: TestServerRequestBody = None):
        # For those subclassing this, usually all you need to do is call this constructor
        # filling out the appropriate information via args
        if payload is not None and payload_type is not None:
            assert(isinstance(payload, payload_type))

        self.__version = available_api_version(version)
        self.__uuid = uuid
        self.__payload = payload
        self.__id = TestServerRequest.__next_id 
        TestServerRequest.__next_id += 1
        self.__http_name = http_name
        self.__method = method

    def _create_request(self, url: str) -> Request:
        full_url = urljoin(url, self.__http_name)
        return Request(self.__method, full_url)
    
    def _http_name(self) -> str:
        return f"v1 {self.__method.capitalize()} /{self.__http_name}"
    
    def _create_response(self, r: Response, version: int, uuid: str) -> TestServerResponse:
        module = import_module(f"cbltest.v{version}.responses")
        class_name = type(self).__name__.replace("Request", "Response")
        response_class = getattr(module, class_name)
        content: dict = {}
        if len(r.content) != 0:
            content_type = r.headers["Content-Type"]
            if "application/json" not in content_type:
                cbl_warning(f"Non-JSON response body received from server ({content_type}), ignoring...")
            else:
                content = loads(r.content)

        return cast(TestServerResponse, response_class(self.__id, r.status_code, uuid, content))
    
    def send(self, url: str, session: Session = None) -> TestServerResponse:
        """
        Send the request to the specified URL, though `RequestFactory.send_request` is preferred.
        
        :param url: The URL to send the request to
        :param session: The requests library session to use when transmitting the HTTP message
        """
        cbl_trace(f"Sending {self} to {url}")
        r = self._create_request(url)
        r.headers["Accept"] = "application/json"
        if self.__version > 0:
            r.headers["CBLTest-API-Version"] = str(self.__version)
            r.headers["CBLTest-Client-ID"] = str(self.__uuid)
        
        if self.__payload is not None:
            r.data = self.__payload.serialize()

        r.prepare()
        if session is not None:
            resp = session.send(session.prepare_request(r))
        else:
            with Session() as s:
                resp = s.send(s.prepare_request(r))

        resp_version_header = resp.headers.get("CBLTest-API-Version")
        uuid = resp.headers.get("CBLTest-Server-ID")
        resp_version = int(resp_version_header) if resp_version_header is not None else 0
        if resp_version != self.__version:
            if resp_version == 0:
                cbl_warning("Server did not set a response version, using request version...")
                resp_version = self.__version
            elif self.__version != 0:
                cbl_warning(f"Response version for {resp_version} does not match request version {self.__version}!")

        ret_val = self._create_response(resp, resp_version, uuid)
        cbl_trace(f"Received {ret_val} from {url}")
        if not resp.ok:
            cbl_warning(f"{self} was not successful ({resp.status_code})")
        return ret_val
    
    def __str__(self) -> str:
        return f"-> {self.__uuid} v{self.__version} {self.__method.upper()} /{self.__http_name} #{self.__id}"

# Only this request is not versioned
class GetRootRequest(TestServerRequest):
    """
    The GET / request.  This API endpoint is not versioned and can be used to
    verify the API version of the server, among other things
    """
    def __init__(self, uuid: UUID):
        super().__init__(0, uuid, "", method="get")
    
    def _create_response(self, r: Response, version: int, uuid: str) -> TestServerResponse:
        return GetRootResponse(self.number, r.status_code, uuid, loads(r.content))


class RequestFactory:
    """
    This class is responsible for creating requests to send to the test server in a way
    that is auditable and understandable, as well as reusing any state set.

    It will be created by :class:`CBLPyTest` using the parsed configuration.  It will log
    every HTTP request and response into a folder called "http_log"
    """
    @property
    def version(self) -> int:
        """Gets the API version that this factory is using"""
        return self.__version
    
    def __init__(self, config: ParsedConfig):
        self.__record_path = Path("http_log")
        if self.__record_path.exists():
            rmtree(self.__record_path)

        self.__record_path.mkdir()

        self.__uuid = uuid4()
        self.__session = Session()
        self.__version = available_api_version(config.api_version)
        self.__server_urls = config.test_servers
        cbl_info(f"RequestFactory created with API version {self.__version} ({self.__uuid})")
        

    def _create_request(self, name: str, payload: TestServerRequestBody = None) -> TestServerRequest:
        if self.__version != payload.version:
            raise ValueError(f"Request factory version {self.__version} does not match payload version {payload.version}!")
        
        module = import_module(f"cbltest.v{self.__version}.requests")
        request_class = getattr(module, name)
        if payload is None:
            return cast(TestServerRequest, request_class(self.__uuid))
        
        return cast(TestServerRequest, request_class(self.__uuid, payload))

    def create_get_root(self) -> TestServerRequest:
        """Creates a GET / request"""
        return GetRootRequest(self.__uuid)
    
    def create_post_reset(self, payload: TestServerRequestBody) -> TestServerRequest:
        """Creates a POST /reset request"""
        if payload is None:
            raise ValueError("No payload provided!")
        
        return self._create_request("PostResetRequest", payload)
    
    def create_post_get_all_document_ids(self, payload: TestServerRequestBody) -> TestServerRequest:
        """Creates a POST /getAllDocumentIDs request"""
        if payload is None:
            raise ValueError("No payload provided!")
        
        return self._create_request("PostGetAllDocumentIDsRequest", payload)
    
    def create_post_snapshot_documents(self, payload: TestServerRequestBody) -> TestServerRequest:
        """Creates a POST /snapshotDocuments request"""
        if payload is None:
            raise ValueError("No payload provided!")
        
        return self._create_request("PostSnapshotDocumentsRequest", payload)
    
    def create_post_update_database(self, payload: TestServerRequestBody) -> TestServerRequest:
        """Creats a POST /updateDatabase request"""
        if payload is None:
            raise ValueError("No payload provided!")
        
        return self._create_request("PostUpdateDatabaseRequest", payload)
    
    def send_request(self, index: int, r: TestServerRequest) -> TestServerResponse:
        """Sends a request to the URL at the provided index (as indexes by test_servers in
        the JSON configuration file)"""
        url = self.__server_urls[index]
        send_log_path = self.__record_path / f"{r.number:05d}_begin.txt"
        with open(send_log_path, "x") as fout:
            fout.write(str(r))
            fout.write("\n\n")
            fout.write(r.payload.serialize() if r.payload is not None else "")
        
        try:
            ret_val = r.send(url, self.__session)
        except Exception as e:
            cbl_error(f"Failed to send {r}")
            recv_log_path = self.__record_path / f"{r.number:05d}_error.txt"
            with open(recv_log_path, "x") as fout:
                fout.write(str(e))

            return None
        
        recv_log_path = self.__record_path / f"{r.number:05d}_end.txt"
        with open(recv_log_path, "x") as fout:
            fout.write(str(ret_val))
            fout.write("\n\n")
            fout.write(ret_val.serialize_payload())

        return ret_val
    
    
