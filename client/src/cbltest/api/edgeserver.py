import ssl
from abc import ABC, abstractmethod
import json
from json import dumps, loads
from operator import truediv
from pathlib import Path
from symbol import raise_stmt
from typing import Dict, List, Tuple, cast, Any, Optional
from urllib.parse import urljoin

from aiohttp import ClientSession, BasicAuth, TCPConnector
from couchbase.pycbc_core import result
from opentelemetry.trace import get_tracer
from setuptools.command.setopt import config_file
from varname import nameof

from cbltest.api.error import CblEdgeServerBadResponseError
from cbltest.api.jsonserializable import JSONSerializable, JSONDictionary
from cbltest.assertions import _assert_not_null
from cbltest.httplog import get_next_writer
from cbltest.jsonhelper import _get_typed_required
from cbltest.logging import cbl_warning, cbl_info
from cbltest.logging import cbl_error, cbl_trace
from cbltest.version import VERSION
from cbltest.utils import assert_not_null
from cbltest.api.syncgateway import AllDocumentsResponseRow, AllDocumentsResponse, DocumentUpdateEntry, RemoteDocument, CouchbaseVersion
from deprecated import deprecated

from cbltest.api.error import CblTestError
from cbltest.api.remoteshell import RemoteShellConnection


class EdgeServerVersion(CouchbaseVersion):
    """
    A class for parsing Edge Server Version
    """

    def parse(self, input: str) -> Tuple[str, int]:
        first_lparen = input.find("(")
        first_semicol = input.find(";")
        if first_lparen == -1 or first_semicol == -1:
            return ("unknown", 0)

        return input[0:first_lparen], int(input[first_lparen + 1:first_semicol])

class BulkDocOperation(JSONSerializable):
    # optype should be  "create", "update" or "delete". by default it is create
    def __init__(self,body:dict,_id:str=None,rev:str=None,optype:str="create"):
        if optype == "update":
            if _id is None:
                optype = "create"
            if rev is None:
                raise CblTestError("Update cannot be performed without rev id")
            body["_rev"]=rev
        if optype == "delete":
            if _id is None:
                raise CblTestError("Delete cannot be performed without id")
            if rev is None:
                raise CblTestError("Delete cannot be performed without rev id")
            body["_deleted"]=True
            body["_rev"] = rev
        body["_id"]=_id
        self._body = body
        self._id = _id

    @property
    def body(self) -> dict:
        return self._body
    def to_json(self):
        return self._body

class EdgeServer:
    """
    A class for interacting with a given Edge Server instance
    """

    def __init__(self, url: str):
        self.__tracer = get_tracer(__name__, VERSION)
        config_file="./environment/edge_server/config/config.json"
        port,secure,certfile,keyfile,admin_user,databases,is_anonymous_auth=self._decode_config_file(config_file)
        self.__secure: bool = secure
        self.__hostname: str = url
        self.__port: int = port
        self.__certfile:str=certfile
        self.__keyfile:str=keyfile
        self.__admin_user:str=admin_user
        self.__databases:dict=databases
        self.__anonymous_auth: bool=is_anonymous_auth
        self.__config_file:str=config_file
        # if not session:
        scheme = "https://" if secure else "http://"
        if self.__anonymous_auth:
            self.__session: ClientSession = self._create_session(secure, scheme, url, port,None)
        else:
            self.__session: ClientSession = self._create_session(secure, scheme, url, port,BasicAuth(admin_user[0].get("user"), admin_user[0].get("password"), "ascii"))
        # else:
        #     self.__session = session

    def _decode_config_file(self,config_file:str):
        with open(config_file, 'r',encoding='utf-8') as file:
            config_content = file.read()
            try:
                config = json.loads(config_content)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in configuration file: {e}")

        # Validate and extract top-level keys
        databases = config.get("databases")
        if not databases or not isinstance(databases, dict):
            raise ValueError("Missing or invalid 'databases' configuration.")

        https = config.get("https", {})
        interface = config.get("interface", "0.0.0.0:59840")
        port = interface.split(":")[1]
        # logging_config = config.get("logging", {})
        users = config.get("users", "")
        enable_anonymous_users = config.get("enable_anonymous_users", False)
        # replications = config.get("replications", [])
        cert_path,key_path="",""
        # Validate HTTPS configuration
        if https:
            cert_path = https.get("tls_cert_path")
            key_path = https.get("tls_key_path")
            if not cert_path or not key_path:
                raise ValueError("HTTPS configuration must include 'tls_cert_path' and 'tls_key_path'.")
        result=[]
        if len(users)>0:
            with open(users, 'r', encoding='utf-8') as file:
                user_content = file.read()
                try:
                    config = json.loads(user_content)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in configuration file: {e}")
                for username, details in users.items():
                    if "admin" in details.get("roles", []):
                        result.append({
                            "user": username,
                            "password": details["password"]
                        })



        # Return parsed configuration as a tuple
        return port, https,cert_path,key_path, result,databases, enable_anonymous_users

    def _create_session(self, secure: bool, scheme: str, url: str, port: int,
                        auth: Optional[BasicAuth]) -> ClientSession:
        if secure:
            ssl_context = ssl.create_default_context(cadata=self.tls_cert())
            ssl_context.check_hostname = False
            return ClientSession(f"{scheme}{url}:{port}", auth=auth, connector=TCPConnector(ssl=ssl_context))
        else:
            return ClientSession(f"{scheme}{url}:{port}", auth=auth)

    def _build_curl_command(self, method: str, path: str, headers: Optional[Dict[str, str]] = None,
                            data: Optional[Dict] = None, params: Optional[Dict[str, str]] = None) -> str:
        curl_command = f"curl -X {method.upper()} {self.__hostname}:{self.__port}{path}"
        if headers:
            for key, value in headers.items():
                curl_command += f" -H \"{key}: {value}\""
        if data:
            curl_command += f" -d '{json.dumps(data)}'"
        if params:
            curl_command += f" {' '.join([f'--{k}={v}' for k, v in params.items()])}"

        return curl_command

    async def _send_request(self, method: str, path: str, payload: Optional[JSONSerializable] = None,
                            params: Optional[Dict[str, str]] = None, session: Optional[ClientSession] = None,curl:bool=False) -> Any:
        if session is None:
            session = self.__session

        with self.__tracer.start_as_current_span(f"send_request",
                                                 attributes={"http.method": method, "http.path": path}):
            headers = {"Content-Type": "application/json"} if payload is not None else None
            data = "" if payload is None else payload.serialize()
            if curl:
                return self._build_curl_command(method, path, headers=headers, data=payload, params=params)
            writer = get_next_writer()
            writer.write_begin(f"Edge Server [{self.__hostname}] -> {method.upper()} {path}", data)
            resp = await session.request(method, path, data=data, headers=headers, params=params)
            if resp.content_type.startswith("application/json"):
                ret_val = await resp.json()
                data = dumps(ret_val, indent=2)
            else:
                data = await resp.text()
                ret_val = data
            writer.write_end(f"Edge Server [{self.__hostname}] <- {method.upper()} {path} {resp.status}", data)
            if not resp.ok:
                raise CblEdgeServerBadResponseError(resp.status, f"{method} {path} returned {resp.status}")

            return ret_val

    async def get_version(self,curl:bool=False) -> CouchbaseVersion:
        scheme = "https://" if self.__secure else "http://"
        async with self._create_session(self.__secure, scheme, self.__hostname, self.__port, None) as s:
            resp = await self._send_request("get", "/", session=s, curl=curl)
            if curl:
                return resp
            assert isinstance(resp, dict)
            resp_dict = cast(dict, resp)
            raw_version = _get_typed_required(resp_dict, "version", str)
            assert "/" in raw_version
            return EdgeServerVersion(raw_version.split("/")[1])

    def tls_cert(self) -> Optional[str]:
        if not self.__secure:
            cbl_warning("Edge Server instance not using TLS, returning empty tls_cert...")
            return None

        return ssl.get_server_certificate((self.__hostname, self.__port))


    async def get_all_documents(self, db_name: str, scope: str = "",
                                collection: str = "",curl:bool=False):
        with self.__tracer.start_as_current_span("get_all_documents", attributes={"cbl.database.name": db_name,
                                                                                  "cbl.scope.name": scope,
                                                                                  "cbl.collection.name": collection}):
            resp = await self._send_request("get", f"/{db_name}{scope}{collection}/_all_docs",curl=curl)
            if curl:
                return resp
            assert isinstance(resp, dict)
            return AllDocumentsResponse(cast(dict, resp))


    async def delete_document(self, doc_id: str, revid: str, db_name: str, scope: str = "",
                              collection: str = "",curl:bool=False):

        with self.__tracer.start_as_current_span("delete_document", attributes={"cbl.database.name": db_name,
                                                                                "cbl.scope.name": scope,
                                                                                "cbl.collection.name": collection,
                                                                                "cbl.document.id": doc_id}):
            if "@" in revid:
                new_rev_id = await self._replaced_revid(doc_id, revid, db_name, scope, collection)
            else:
                new_rev_id = revid

            return await self._send_request("delete", f"/{db_name}{scope}{collection}/{doc_id}",
                                     params={"rev": new_rev_id},curl=curl)


    async def get_document(self, db_name: str, doc_id: str, scope: str = "", collection: str = "",curl:bool=False):
        with self.__tracer.start_as_current_span("get_document", attributes={"cbl.database.name": db_name,
                                                                             "cbl.scope.name": scope,
                                                                             "cbl.collection.name": collection,
                                                                             "cbl.document.id": doc_id}):
            response = await self._send_request("get", f"/{db_name}{scope}{collection}/{doc_id}?show_cv=true",curl)
            if curl:
                return response
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server get /doc (not JSON)")

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                if cast_resp["reason"] == "missing" or cast_resp["reason"] == "deleted":
                    return None

                raise CblEdgeServerBadResponseError(500,
                                                     f"Get doc from edge server had error '{cast_resp['reason']}'")

            return RemoteDocument(cast_resp)

    async def get_all_dbs(self,curl:bool=False):
        with self.__tracer.start_as_current_span("get all database"):
            response= await self._send_request("get","/_all_dbs",curl=curl)
            if curl:
                return response
            if not isinstance(response, list):
                raise ValueError("Inappropriate response from edge server get /_all_dbs (not list)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"get all database from edge server had error '{cast_resp['reason']}'")
            return cast_resp

    async def get_active_tasks(self,curl:bool=False) :
        with self.__tracer.start_as_current_span("get all active tasks"):
            response= await self._send_request("get","/_active_tasks",curl=curl)
            if curl:
                return response
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server get /_active_tasks (not JSON)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"get all active tasks from edge server had error '{cast_resp['reason']}'")
            return cast_resp

    async def get_db_info(self, db_name:str,scope:str="",collection:str="",curl:bool=False):
        with self.__tracer.start_as_current_span("get database info", attributes={"cbl.database.name": db_name,
                                                                                  "cbl.scope.name": scope,
                                                                                  "cbl.collection.name": collection}):
            response= await self._send_request("get",f"/{db_name}{scope}{collection}",curl=curl)
            if curl:
                return response
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server get /  (not JSON)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"get detabase info  from edge server had error '{cast_resp['reason']}'")
            return cast_resp

    async def start_replication(self, source: str, target: str,user: str,
             password:str,bidirectional: bool,continuous: bool,collections: Optional[List[str]] = None,channels: Optional[List[str]] = None,
             doc_ids: Optional[List[str]] = None,
             headers: Optional[Dict[str, str]] = None,
             trusted_root_certs: Optional[str] = None,
             pinned_cert: Optional[str] = None,
             session_cookie: Optional[str] = None,
             openid_token: Optional[str] = None,
             tls_client_cert: Optional[str] = None,
             tls_client_cert_key: Optional[str] = None,curl:bool=False):
        with self.__tracer.start_as_current_span("Start Replication with Edge Server", attributes={"cbl.source.name": source,
                                                                                  "cbl.target.name": target,
                                                                                  "cbl.collection.name": collections}):

            payload: Dict[str, Any] = {
                "source": source,
                "target": target,
                "bidirectional": bidirectional,
                "continuous": continuous,
                "collections": collections,
                "channels": channels,
                "doc_ids": doc_ids,
                "headers": headers
            }

            if trusted_root_certs:
                payload["trusted_root_certs"] = trusted_root_certs
            if pinned_cert:
                payload["pinned_cert"] = pinned_cert
            if user:
                payload["user"] = user
            if password:
                payload["password"] = password
            if session_cookie:
                payload["session_cookie"] = session_cookie
            if openid_token:
                payload["openid_token"] = openid_token
            if tls_client_cert:
                payload["tls_client_cert"] = tls_client_cert
            if tls_client_cert_key:
                payload["tls_client_cert_key"] = tls_client_cert_key

            response = await self._send_request("post","_replicate",JSONDictionary(payload),curl=curl)
            if curl:
                return response
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server post /_replicate (not JSON)")

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"start replication with edge server had error '{cast_resp['reason']}'")
            return cast_resp.session_id

    async def replication_status(self, replicator_id:str,curl:bool=False):
        with self.__tracer.start_as_current_span("get replication status with Edge Server", attributes={"cbl.replicator.id": replicator_id}):

            response = await self._send_request("get",f"_replicate{replicator_id}",curl=curl)
            if curl:
                return response
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server get status  /_replicate (not JSON)")

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"get replication status with Edge Server had error '{cast_resp['reason']}'")
            return cast_resp

    async def all_replication_status(self,curl:bool=False):
        with self.__tracer.start_as_current_span("All Replication status with Edge Server"):

            response = await self._send_request("get","_replicate",curl=curl)
            if curl:
                return response
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server get all status  /_replicate (not JSON)")

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"get all replication status with Edge Server had error '{cast_resp['reason']}'")
            return cast_resp

    async def stop_replication(self, replicator_id:str,curl:bool=False):
        with self.__tracer.start_as_current_span("Stop Replication with Edge Server", attributes={"cbl.replicator.id": replicator_id}):

            response = await self._send_request("post","_replicate",payload=JSONDictionary({"cancel":replicator_id}))
            if curl:
                return response
            if response and not isinstance(response, dict) :
                raise ValueError("Inappropriate response from edge server  stop  /_replicate (not JSON)")

            cast_resp = cast(dict, response) if response else {}
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"stop replication  with Edge Server had error '{cast_resp['reason']}'")


    async def changes_feed(self,db_name:str,scope:str="",collection:str="",since: Optional[int] = 0,feed: Optional[str] = "normal",limit: Optional[int] = None,filter_type: Optional[str] = None,doc_ids: Optional[List[str]] = None,
            include_docs: Optional[bool] = False,active_only: Optional[bool] = False,descending: Optional[bool] = False,heartbeat: Optional[int] = None,timeout: Optional[int] = None ,curl:bool=False):
        with self.__tracer.start_as_current_span("Changes feed", attributes={"cbl.database.name": db_name,
                                                                                  "cbl.scope.name": scope,
                                                                                  "cbl.collection.name": collection,"since":since}):
            body = {
                "since": since,
                "feed": feed,
                "limit": limit,
                "filter": filter_type,
                "doc_ids": doc_ids,
                "include_docs": include_docs,
                "active_only": active_only,
                "descending": descending,
                "heartbeat": heartbeat,
                "timeout": timeout,
            }
            payload= {k: v for k, v in body.items() if v is not None}
            response = await self._send_request("post", f"{db_name}{scope}{collection}/_changes", payload=JSONDictionary(payload),curl=curl)
            if curl:
                return response
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server post /_changes (not JSON)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"get changes feed with Edge Server had error '{cast_resp['reason']}'")
            return cast_resp
    async def named_query(self,db_name:str,scope:str="",collection:str="",name:str=None,params:Dict=None,curl:bool=False):
        with self.__tracer.start_as_current_span("Named query", attributes={"cbl.database.name": db_name,
                                                                                  "cbl.scope.name": scope,
                                                                                  "cbl.collection.name": collection}):
            payload={"name":name}
            if params is not None:
                payload["params"]=params
            response = await self._send_request("post",f"{db_name}{scope}{collection}/_query",payload=JSONDictionary(payload),curl=curl)
            if curl:
                return response
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server post   /_query (not JSON)")

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                        f"named query with Edge Server had error '{cast_resp['reason']}'")
            return cast_resp

    async def adhoc_query(self,db_name:str,scope:str="",collection:str="",query:str=None,params:Dict=None,curl:bool=False):
        with self.__tracer.start_as_current_span("Adhoc query", attributes={"cbl.database.name": db_name,
                                                                                  "cbl.scope.name": scope,
                                                                                  "cbl.collection.name": collection}):
            payload={"query":query}
            if params is not None:
                payload["params"]=params
            response = await self._send_request("post",f"{db_name}{scope}{collection}/_query",payload=JSONDictionary(payload),curl=curl)
            if curl:
                return response
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server adhoc query (not JSON)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"adhoc query with Edge Server had error '{cast_resp['reason']}'")
            return cast_resp

    async def kill_server(self,ip_address: str, port: int = 59840) -> bool:
        with self.__tracer.start_as_current_span("kill edge server", attributes={"ip": ip_address, "port": port}):
            ssh_client=RemoteShellConnection(ip_address, port)
            await ssh_client.connect()
            success=await ssh_client.kill_edge_server()
            ssh_client.close()
            return success


    async def start_server(self,ip_address: str) -> bool:
        with self.__tracer.start_as_current_span("start edge server", attributes={"ip": ip_address}):
            ssh_client=RemoteShellConnection(ip_address)
            await ssh_client.connect()
            success= await ssh_client.start_edge_server(self.__secure,self.__config_file,self.__certfile,self.__keyfile)
            ssh_client.close()
            return success

    async def add_document_auto_id(self,document: dict,db_name:str,scope:str="",collection:str="",curl:bool=False):
        with self.__tracer.start_as_current_span("add document with auto ID", attributes={"cbl.database.name": db_name,
                                                                                  "cbl.scope.name": scope,
                                                                                  "cbl.collection.name": collection}):
            response = await self._send_request("post",f"{db_name}{scope}{collection}/",payload=JSONDictionary(document),curl=curl)
            if curl:
                return response
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server add doc auto ID (not JSON)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"add document with auto ID Edge Server had error '{cast_resp['reason']}'")
            return cast_resp

    async def add_document_with_id(self,document: dict,id:str,db_name:str,scope:str="",collection:str="",curl:bool=False)->dict:
        with self.__tracer.start_as_current_span("add document with ID", attributes={"cbl.database.name": db_name,
                                                                                  "cbl.scope.name": scope,
                                                                                  "cbl.collection.name": collection}):
            response = await self._send_request("put",f"{db_name}{scope}{collection}/{id}",payload=JSONDictionary(document),curl=curl)
            if curl:
                return response
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server add doc (not JSON)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"add document with ID Edge Server had error '{cast_resp['reason']}'")
            return cast_resp

    async def delete_sub_document(self, id:str,revid:str,key:str,db_name: str, scope: str = "", collection: str = "",curl:bool=False) -> dict:
        with self.__tracer.start_as_current_span("delete sub-document", attributes={
            "cbl.database.name": db_name,
            "cbl.scope.name": scope,
            "cbl.collection.name": collection
        }):
            # Perform the DELETE request to the edge server
            response = await self._send_request(
                "delete", f"{db_name}{scope}{collection}/{id}/{key}?revid={revid}",curl=curl
            )
            if curl:
                return response
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server delete sub-document (not JSON)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"delete sub-document Edge Server had error '{cast_resp['reason']}'")
            return cast_resp

    async def put_sub_document(self, id:str,revid:str,key:str,db_name: str, scope: str = "", collection: str = "",value=None,curl:bool=False) -> dict:
        with self.__tracer.start_as_current_span("put sub-document", attributes={
            "cbl.database.name": db_name,
            "cbl.scope.name": scope,
            "cbl.collection.name": collection
        }):

            response = await self._send_request(
                "put", f"{db_name}{scope}{collection}/{id}/{key}?revid={revid}",payload=JSONDictionary({key: value}),curl=curl
            )
            if curl:
                return response

            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server put sub-document (not JSON)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"put sub-document Edge Server had error '{cast_resp['reason']}'")
            return cast_resp

    async def get_sub_document(self, id:str,key:str,db_name: str, scope: str = "", collection: str = "",curl:bool=False):
        with self.__tracer.start_as_current_span("get sub-document", attributes={
            "cbl.database.name": db_name,
            "cbl.scope.name": scope,
            "cbl.collection.name": collection
        }):

            resp = await self._send_request(
                "get", f"{db_name}{scope}{collection}/{id}/{key}",curl=curl
            )
            if curl:
                return resp
            if isinstance(resp, dict):
                cast_resp = cast(dict, resp)
                if "error" in cast_resp:
                    raise CblEdgeServerBadResponseError(500,
                                                        f"get sub-document Edge Server had error '{cast_resp['reason']}'")
                return cast_resp
            else:
                return resp


    async def bulk_doc_op(self,docs:List[BulkDocOperation],db_name: str, scope: str = "", collection: str = "",new_edits:bool=True,curl:bool=False):
        with self.__tracer.start_as_current_span("bulk_documents_operation", attributes={"cbl.database.name": db_name,
                                                                                 "cbl.scope.name": scope,
                                                                               "cbl.collection.name": collection}):
            body = {"docs": list(u.body for u in docs), "new_edits": new_edits}
            resp=await self._send_request("post", f"/{db_name}{scope}{collection}/_bulk_docs",
                                     JSONDictionary(body),curl=curl)
            if curl:
                return resp
            if not isinstance(resp, dict):
                raise ValueError("Inappropriate response from edge server  bulk doc op (not JSON)")

            cast_resp = cast(dict, resp)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"bulk_documents_operation Edge Server had error '{cast_resp['reason']}'")
            return cast_resp

    async def blip_sync(self,db_name: str, scope: str = "", collection: str = "",curl:bool=False):
        with self.__tracer.start_as_current_span("get web socket connection for client ", attributes={
            "cbl.database.name": db_name,
            "cbl.scope.name": scope,
            "cbl.collection.name": collection
        }):

            resp = await self._send_request(
                "get", f"{db_name}{scope}{collection}/_blipsync",curl=curl
            )
            if curl:
                return resp
            if resp and not isinstance(resp, dict) :
                raise ValueError("Inappropriate response from edge server get /_blipsync (not JSON)")
            cast_resp = cast(dict, resp) if resp else {}
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(500,
                                                    f"get web socket connection for client with Edge Server had error '{cast_resp['reason']}'")







