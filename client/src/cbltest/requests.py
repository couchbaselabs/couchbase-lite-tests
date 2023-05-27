from __future__ import annotations
from abc import ABC, abstractmethod
from json import loads
from pathlib import Path
from shutil import rmtree
from typing import cast
from uuid import UUID, uuid4
from requests import Request, Response, Session, get
from importlib import import_module

from .logging import cbl_info, cbl_trace, cbl_warning
from .responses import GetRootResponse, TestServerResponse
from . import available_api_version

class TestServerRequestBody(ABC):
    @property
    def version(self) -> int:
        return self.__version

    def __init__(self, version: int):
        self.__version = available_api_version(version)

    @abstractmethod
    def serialize(self) -> str:
        pass

class TestServerRequest(ABC):
    __next_id: int = 1

    @property
    def number(self) -> int:
        return self.__id
    
    @property
    def payload(self) -> TestServerRequestBody:
        return self.__payload

    def __init__(self, version: int, uuid: UUID, payload: TestServerRequestBody = None):
        self.__version = available_api_version(version)
        self.__uuid = uuid
        self.__payload = payload
        self.__id = TestServerRequest.__next_id 
        TestServerRequest.__next_id += 1

    @abstractmethod
    def _create_request(self, url: str) -> Request:
        return None
    
    def _create_response(self, r: Response, version: int) -> TestServerResponse:
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

        return cast(TestServerResponse, response_class(self.__id, r.status_code, version, content))
    
    @abstractmethod
    def _http_name(self) -> str:
        return 
    
    def send(self, url: str, session: Session = None) -> TestServerResponse:
        cbl_trace(f"Sending {self}")
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
        resp_version = int(resp_version_header) if resp_version_header is not None else 0
        if resp_version != self.__version:
            if resp_version == 0:
                cbl_warning("Server did not set a response version, using request version...")
                resp_version = self.__version
            else:
                cbl_warning(f"Response version for {resp_version} does not match request version {self.__version}!")

        ret_val = self._create_response(resp, resp_version)
        cbl_trace(f"Received {ret_val}")
        if not resp.ok:
            cbl_warning(f"{self}\nwas not successful ({resp.status_code})")
        return ret_val
    
    def __str__(self) -> str:
        return f"-> {self._http_name()} #{self.__id}"

# Only this request is not versioned
class GetRootRequest(TestServerRequest):
    def __init__(self, uuid: UUID):
        super().__init__(0, uuid)

    def _create_request(self, url: str) -> Request:
        return Request("get", url)
    
    def _create_response(self, r: Response, version: int) -> TestServerResponse:
        return GetRootResponse(self.number, r.status_code, loads(r.content))
    
    def _http_name(self) -> str:
        return "GET /"


class RequestFactory:
    @property
    def version(self) -> int:
        return self.__version
    
    def __init__(self, server_url: str):
        self.__record_path = Path("http_log")
        if self.__record_path.exists():
            rmtree(self.__record_path)

        self.__record_path.mkdir()
        self.__base_url = server_url

        self.__uuid = uuid4()
        request = self.create_get_root()
        self.__session = Session()
        response = self.send_request(request)
        self.__version = available_api_version(response.version)
        cbl_info(f"RequestFactory created with API version {self.__version}")
        

    def _create_request(self, name: str, payload: TestServerRequestBody = None) -> TestServerRequest:
        if self.__version != payload.version:
            raise ValueError(f"Request factory version {self.__version} does not match payload version {payload.version}!")
        
        module = import_module(f"cbltest.v{self.__version}.requests")
        request_class = getattr(module, name)
        if payload is None:
            return cast(TestServerRequest, request_class(self.__uuid))
        
        return cast(TestServerRequest, request_class(self.__uuid, payload))

    def create_get_root(self) -> TestServerRequest:
        return GetRootRequest(self.__uuid)
    
    def create_post_reset(self, payload: TestServerRequestBody) -> TestServerRequest:
        if payload is None:
            raise ValueError("No payload provided!")
        
        return self._create_request("PostResetRequest", payload)
    
    def create_post_get_all_document_ids(self, payload: TestServerRequestBody) -> TestServerRequest:
        if payload is None:
            raise ValueError("No payload provided!")
        
        return self._create_request("PostGetAllDocumentIDsRequest", payload)
    
    def create_post_snapshot_documents(self, payload: TestServerRequestBody) -> TestServerRequest:
        if payload is None:
            raise ValueError("No payload provided!")
        
        return self._create_request("PostSnapshotDocumentsRequest", payload)
    
    def send_request(self, r: TestServerRequest) -> TestServerResponse:
        send_log_path = self.__record_path / f"{r.number:05d}_begin"
        with open(send_log_path, "x") as fout:
            fout.write(str(r))
            fout.write("\n\n")
            fout.write(r.payload.serialize() if r.payload is not None else "")
        
        ret_val = r.send(self.__base_url, self.__session)
        recv_log_path = self.__record_path / f"{r.number:05d}_end"
        with open(recv_log_path, "x") as fout:
            fout.write(str(ret_val))
            fout.write("\n\n")
            fout.write(ret_val.serialize_payload())

        return ret_val
    
    
