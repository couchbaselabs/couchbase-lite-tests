import json
import urllib.parse
import uuid
from json import dumps
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast
from urllib.parse import urljoin

import pyjson5 as json5  # type: ignore[import-not-found]
from aiohttp import BasicAuth, ClientSession
from opentelemetry.trace import get_tracer

from cbltest.api.error import CblEdgeServerBadResponseError, CblTestError
from cbltest.api.jsonserializable import JSONDictionary, JSONSerializable
from cbltest.api.syncgateway import (
    AllDocumentsResponse,
    CouchbaseVersion,
    RemoteDocument,
)
from cbltest.assertions import _assert_not_null
from cbltest.httplog import get_next_writer
from cbltest.jsonhelper import _get_typed_required
from cbltest.version import VERSION


class EdgeServerVersion(CouchbaseVersion):
    """
    A class for parsing Edge Server Version
    """

    def parse(self, input: str) -> Tuple[str, int]:
        first_lparen = input.find("(")
        first_semicol = input.find(";")
        if first_lparen == -1 or first_semicol == -1:
            return ("unknown", 0)

        return input[0:first_lparen], int(input[first_lparen + 1 : first_semicol])


class BulkDocOperation(JSONSerializable):
    # optype should be  "create", "update" or "delete". by default it is create
    def __init__(
        self,
        body: dict,
        _id: Optional[str] = None,
        rev: Optional[str] = None,
        optype: str = "create",
    ):
        if _id is None:
            _id = body.get("_id")
        if optype == "update":
            if _id is None:
                optype = "create"
                _id = str(uuid.uuid4())
            if rev is None:
                raise CblTestError("Update cannot be performed without rev id")
            body["_rev"] = rev
        if optype == "delete":
            if _id is None:
                raise CblTestError("Delete cannot be performed without id")
            if rev is None:
                raise CblTestError("Delete cannot be performed without rev id")
            body["_deleted"] = True
            body["_rev"] = rev
        body["_id"] = _id
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

    def __init__(
        self,
        url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        config_file=None,
    ):
        self.__tracer = get_tracer(__name__, VERSION)
        if config_file is None:
            repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
            config_file = str(
                repo_root / "environment" / "edge_server" / "config" / "config.json"
            )
        port, secure, mtls, certfile, keyfile, is_auth, databases, is_anonymous_auth = (
            self._decode_config_file(config_file)
        )
        self.__secure: bool = secure
        self.__mtls: bool = mtls
        self.__hostname: str = url
        self.__port: int = port
        self.__certfile: str = certfile
        self.__keyfile: str = keyfile
        self.__databases: dict = databases
        self.__anonymous_auth: bool = is_anonymous_auth
        self.__config_file: str = config_file
        self.__auth_name = "admin_user"
        self.__auth_password = "password"
        self.__auth = is_auth
        ws_scheme = "wss://" if secure else "ws://"
        self.__replication_url = f"{ws_scheme}{url}:{port}"
        self.scheme = "https://" if secure else "http://"
        self.__session: ClientSession
        if self.__anonymous_auth:
            self.__session = self._create_session(self.scheme, url, port, None)
        else:
            self.__session = self._create_session(
                self.scheme,
                url,
                port,
                BasicAuth(self.__auth_name, self.__auth_password, "ascii"),
            )
        self.__shell_session: ClientSession = self._create_session(
            "http://", url, 20001, None
        )

    @property
    def hostname(self) -> str:
        return self.__hostname

    def _decode_config_file(self, config_file: str):
        with open(config_file, "r", encoding="utf-8") as file:
            config_content = file.read()
        config = json5.loads(config_content)

        # Validate and extract top-level keys
        databases = config.get("databases")
        if not databases or not isinstance(databases, dict):
            raise ValueError("Missing or invalid 'databases' configuration.")

        https = config.get("https", False)
        interface = config.get("interface", "0.0.0.0:59840")
        port = interface.split(":")[1]
        enable_anonymous_users = config.get("enable_anonymous_users", False)
        cert_path, key_path = "", ""
        mtls = False
        if https:
            cert_path = https.get("tls_cert_path")
            key_path = https.get("tls_key_path")
            if not cert_path or not key_path:
                raise ValueError(
                    "HTTPS configuration must include 'tls_cert_path' and 'tls_key_path'."
                )
            client_cert_path = https.get("client_cert_path", False)
            if client_cert_path:
                mtls = True
            https = True
        users = True if config.get("users", False) else False
        # Return parsed configuration as a tuple
        return (
            port,
            https,
            mtls,
            cert_path,
            key_path,
            users,
            databases,
            enable_anonymous_users,
        )

    def _create_session(
        self, scheme: str, url: str, port: int, auth: Optional[BasicAuth]
    ) -> ClientSession:
        return ClientSession(f"{scheme}{url}:{port}", auth=auth)

    async def _send_request(
        self,
        method: str,
        path: str,
        payload: Optional[JSONSerializable] = None,
        params: Optional[Dict[str, str]] = None,
        session: Optional[ClientSession] = None,
        shell: bool = False,
    ) -> Any:
        if shell:
            session = self.__shell_session
        if session is None:
            session = self.__session

        with self.__tracer.start_as_current_span(
            "send_request", attributes={"http.method": method, "http.path": path}
        ):
            headers = (
                {"Content-Type": "application/json"} if payload is not None else None
            )
            data = "" if payload is None else payload.serialize()
            writer = get_next_writer()
            writer.write_begin(
                f"Edge Server [{self.__hostname}] -> {method.upper()} {path}", data
            )
            resp = await session.request(
                method, path, data=data, headers=headers, params=params
            )

            if resp.content_type.startswith("application/json"):
                ret_val = await resp.json()
                data = dumps(ret_val, indent=2)
            else:
                data = await resp.text()
                ret_val = data
            writer.write_end(
                f"Edge Server [{self.__hostname}] <- {method.upper()} {path} {resp.status}",
                data,
            )

            if not resp.ok:
                raise CblEdgeServerBadResponseError(
                    resp.status, f"{method} {path} returned {resp.status} for {payload}"
                )

            return ret_val

    def keyspace_builder(
        self, db_name: str = "", scope: str = "", collection: str = ""
    ):
        keyspace = db_name
        if scope:
            keyspace += f".{scope}"
        if collection:
            keyspace += f".{collection}"
        return keyspace

    async def get_version(self) -> CouchbaseVersion:
        scheme = "https://" if self.__secure else "http://"
        async with self._create_session(
            scheme, self.__hostname, self.__port, None
        ) as s:
            resp = await self._send_request("get", "/", session=s)
            assert isinstance(resp, dict)
            resp_dict = cast(dict, resp)
            raw_version = _get_typed_required(resp_dict, "version", str)
            assert "/" in raw_version
            return EdgeServerVersion(raw_version.split("/")[1])

    async def get_all_documents(
        self,
        db_name: str,
        scope: str = "",
        collection: str = "",
        descending=False,
        endkey=None,
        keys=None,
        startkey=None,
        include_docs=False,
    ):
        with self.__tracer.start_as_current_span(
            "get_all_documents",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            keyspace = self.keyspace_builder(db_name, scope, collection)
            query_params = []
            if descending:
                query_params.append("descending=true")
            if endkey:
                query_params.append(f"endkey={urllib.parse.quote(endkey)}")
            if keys:
                keys_json = json.dumps(keys)  # Convert to JSON
                encoded_keys = urllib.parse.quote(keys_json)  # URL-encode
                query_params.append(f"keys={encoded_keys}")
            if startkey:
                query_params.append(f"startkey={urllib.parse.quote(startkey)}")
            if include_docs:
                query_params.append("include_docs=true")
            request_url = f"?{'&'.join(query_params)}" if query_params else ""
            resp = await self._send_request(
                "get", f"/{keyspace}/_all_docs{request_url}"
            )
            assert isinstance(resp, dict)
            return AllDocumentsResponse(cast(dict, resp))

    async def delete_document(
        self,
        doc_id: str,
        revid: str,
        db_name: str,
        scope: str = "",
        collection: str = "",
        expires: int = 0,
        ttl: int = 0,
    ):
        with self.__tracer.start_as_current_span(
            "delete_document",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            keyspace = self.keyspace_builder(db_name, scope, collection)
            params = [f"rev={revid}"]
            if expires != 0:
                params.append(f"expires={expires}")
            if ttl != 0:
                params.append(f"ttl={ttl}")
            qp = "?" + "&".join(params)
            return await self._send_request("delete", f"/{keyspace}/{doc_id}{qp}")

    async def get_document(
        self,
        db_name: str,
        doc_id: str,
        scope: str = "",
        collection: str = "",
        revid: Optional[str] = None,
    ):
        with self.__tracer.start_as_current_span(
            "get_document",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            keyspace = self.keyspace_builder(db_name, scope, collection)
            response = await self._send_request("get", f"/{keyspace}/{doc_id}")
            if not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from edge server get /doc (not JSON)"
                )

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                if cast_resp["reason"] == "missing" or cast_resp["reason"] == "deleted":
                    return None

                raise CblEdgeServerBadResponseError(
                    500, f"Get doc from edge server had error '{cast_resp['reason']}'"
                )

            return RemoteDocument(cast_resp)

    async def get_all_dbs(self):
        with self.__tracer.start_as_current_span("get all database"):
            response = await self._send_request("get", "/_all_dbs")
            if not isinstance(response, list):
                raise ValueError(
                    "Inappropriate response from edge server get /_all_dbs (not list)"
                )
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"get all database from edge server had error '{cast_resp['reason']}'",
                )
            return cast_resp

    async def get_active_tasks(self):
        with self.__tracer.start_as_current_span("get all active tasks"):
            response = await self._send_request("get", "/_active_tasks")
            if not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from edge server get /_active_tasks (not JSON)"
                )
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"get all active tasks from edge server had error '{cast_resp['reason']}'",
                )
            return cast_resp

    async def get_db_info(self, db_name: str, scope: str = "", collection: str = ""):
        with self.__tracer.start_as_current_span(
            "get database info",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            keyspace = self.keyspace_builder(db_name, scope, collection)
            response = await self._send_request("get", f"/{keyspace}")
            if not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from edge server get /  (not JSON)"
                )
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"get detabase info  from edge server had error '{cast_resp['reason']}'",
                )
            return cast_resp

    async def start_replication(
        self,
        source: str,
        target: str,
        user: str,
        password: str,
        bidirectional: bool,
        continuous: bool,
        collections: Optional[List[str]] = None,
        channels: Optional[List[str]] = None,
        doc_ids: Optional[List[str]] = None,
        headers: Optional[Dict[str, str]] = None,
        trusted_root_certs: Optional[str] = None,
        pinned_cert: Optional[str] = None,
        session_cookie: Optional[str] = None,
        openid_token: Optional[str] = None,
        tls_client_cert: Optional[str] = None,
        tls_client_cert_key: Optional[str] = None,
    ):
        with self.__tracer.start_as_current_span(
            "Start Replication with Edge Server",
            attributes={
                "cbl.source.name": source,
                "cbl.target.name": target,
                "cbl.collection.name": collections or [],
            },
        ):
            payload: Dict[str, Any] = {
                "source": source,
                "target": target,
                "bidirectional": bidirectional,
                "continuous": continuous,
                "collections": collections,
                "channels": channels,
                "doc_ids": doc_ids,
                "headers": headers,
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

            response = await self._send_request(
                "post", "/_replicate", JSONDictionary(payload)
            )
            if not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from edge server post /_replicate (not JSON)"
                )

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"start replication with edge server had error '{cast_resp['reason']}'",
                )
            return cast_resp.get("session_id")

    async def replication_status(self, replicator_id: str):
        with self.__tracer.start_as_current_span(
            "get replication status with Edge Server",
            attributes={"cbl.replicator.id": replicator_id},
        ):
            response = await self._send_request("get", f"/_replicate/{replicator_id}")
            if not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from edge server get status  /_replicate (not JSON)"
                )

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"get replication status with Edge Server had error '{cast_resp['reason']}'",
                )
            return cast_resp

    async def all_replication_status(self):
        with self.__tracer.start_as_current_span(
            "All Replication status with Edge Server"
        ):
            response = await self._send_request("get", "/_replicate")

            if not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from edge server get all status  /_replicate (not JSON)"
                )

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"get all replication status with Edge Server had error '{cast_resp['reason']}'",
                )
            return cast_resp

    async def stop_replication(self, replicator_id: int):
        with self.__tracer.start_as_current_span(
            "Stop Replication with Edge Server",
            attributes={"cbl.replicator.id": replicator_id},
        ):
            response = await self._send_request(
                "delete", f"/_replicate/{replicator_id}"
            )

            if response and not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from edge server  stop  /_replicate (not JSON)"
                )

            cast_resp = cast(dict, response) if response else {}
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"stop replication  with Edge Server had error '{cast_resp['reason']}'",
                )

    def replication_url(self, db_name: str):
        _assert_not_null(db_name, "db_name")
        return urljoin(self.__replication_url, db_name)

    async def changes_feed(
        self,
        db_name: str,
        scope: str = "",
        collection: str = "",
        since: Optional[int] = 0,
        feed: Optional[str] = "normal",
        limit: Optional[int] = None,
        filter_type: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        include_docs: Optional[bool] = False,
        active_only: Optional[bool] = False,
        descending: Optional[bool] = False,
        heartbeat: Optional[int] = None,
        timeout: Optional[int] = None,
    ):
        with self.__tracer.start_as_current_span(
            "Changes feed",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "since": since or 0,
            },
        ):
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
            payload = {k: v for k, v in body.items() if v is not None}
            keyspace = self.keyspace_builder(db_name, scope, collection)
            response = await self._send_request(
                "post", f"{keyspace}/_changes", payload=JSONDictionary(payload)
            )

            if not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from edge server post /_changes (not JSON)"
                )
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"get changes feed with Edge Server had error '{cast_resp['reason']}'",
                )
            return cast_resp

    async def named_query(
        self,
        db_name: str,
        scope: str = "",
        collection: str = "",
        name: Optional[str] = None,
        params: Optional[Dict] = None,
    ):
        with self.__tracer.start_as_current_span(
            "Named query",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            keyspace = self.keyspace_builder(db_name, scope, collection)
            payload = {}
            if params:
                for key, value in params.items():
                    payload[key] = value
            response = await self._send_request(
                "post", f"/{keyspace}/_query/{name}", payload=JSONDictionary(payload)
            )

            if not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from edge server post   /_query (not JSON)"
                )

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"named query with Edge Server had error '{cast_resp['reason']}'",
                )
            return cast_resp

    async def adhoc_query(
        self,
        db_name: str,
        scope: str = "",
        collection: str = "",
        query: Optional[str] = None,
        params: Optional[Dict] = None,
    ):
        with self.__tracer.start_as_current_span(
            "Adhoc query",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            payload: Dict[str, Any] = {"query": query}
            if params is not None:
                payload["params"] = params
            keyspace = self.keyspace_builder(db_name, scope, collection)
            response = await self._send_request(
                "post", f"/{keyspace}/_query", payload=JSONDictionary(payload)
            )

            if not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from edge server adhoc query (not JSON)"
                )
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"adhoc query with Edge Server had error '{cast_resp.get('reason')}'",
                )
            return cast_resp

    async def add_document_auto_id(
        self,
        document: dict,
        db_name: str,
        scope: str = "",
        collection: str = "",
        expires: int = 0,
        ttl: int = 0,
    ):
        with self.__tracer.start_as_current_span(
            "add document with auto ID",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            keyspace = self.keyspace_builder(db_name, scope, collection)
            params = []
            if expires != 0:
                params.append(f"expires={expires}")
            if ttl != 0:
                params.append(f"ttl={ttl}")
            qp = "?" + "&".join(params) if params else ""

            response = await self._send_request(
                "post", f"/{keyspace}/{qp}", payload=JSONDictionary(document)
            )

            if not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from edge server add doc auto ID (not JSON)"
                )
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"add document with auto ID Edge Server had error '{cast_resp['reason']}'",
                )
            return cast_resp

    # single create or update . For update provide rev_id
    async def put_document_with_id(
        self,
        document: dict,
        id: str,
        db_name: str,
        scope: str = "",
        collection: str = "",
        rev: Optional[str] = None,
        expires: int = 0,
        ttl: int = 0,
    ) -> dict:
        with self.__tracer.start_as_current_span(
            "add document with ID",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            keyspace = self.keyspace_builder(db_name, scope, collection)

            if rev:
                document["_rev"] = rev
            params = []
            if rev:
                params.append(f"rev={rev}")
            if expires != 0:
                params.append(f"expires={expires}")
            if ttl != 0:
                params.append(f"ttl={ttl}")

            qp = "?" + "&".join(params) if params else ""

            response = await self._send_request(
                "put", f"/{keyspace}/{id}{qp}", payload=JSONDictionary(document)
            )

            if not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from edge server add doc (not JSON)"
                )
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"add document with ID Edge Server had error '{cast_resp['reason']}'",
                )
            return cast_resp

    async def delete_sub_document(
        self,
        id: str,
        revid: str,
        key: str,
        db_name: str,
        scope: str = "",
        collection: str = "",
    ) -> dict:
        with self.__tracer.start_as_current_span(
            "delete sub-document",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            # Perform the DELETE request to the edge server
            keyspace = self.keyspace_builder(db_name, scope, collection)
            response = await self._send_request(
                "delete", f"{keyspace}/{id}/{key}?rev={revid}"
            )

            if not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from edge server delete sub-document (not JSON)"
                )
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"delete sub-document Edge Server had error '{cast_resp['reason']}'",
                )
            return cast_resp

    async def put_sub_document(
        self,
        id: str,
        revid: str,
        key: str,
        db_name: str,
        scope: str = "",
        collection: str = "",
        value=None,
    ) -> dict:
        with self.__tracer.start_as_current_span(
            "put sub-document",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            keyspace = self.keyspace_builder(db_name, scope, collection)
            response = await self._send_request(
                "put",
                f"{keyspace}/{id}/{key}?rev={revid}",
                payload=JSONDictionary({key: value}),
            )

            if not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from edge server put sub-document (not JSON)"
                )
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"put sub-document Edge Server had error '{cast_resp['reason']}'",
                )
            return cast_resp

    async def get_sub_document(
        self, id: str, key: str, db_name: str, scope: str = "", collection: str = ""
    ):
        with self.__tracer.start_as_current_span(
            "get sub-document",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            keyspace = self.keyspace_builder(db_name, scope, collection)
            resp = await self._send_request("get", f"{keyspace}/{id}/{key}")

            if isinstance(resp, dict):
                cast_resp = cast(dict, resp)
                if "error" in cast_resp:
                    raise CblEdgeServerBadResponseError(
                        500,
                        f"get sub-document Edge Server had error '{cast_resp['reason']}'",
                    )
                return cast_resp
            else:
                return resp

    async def bulk_doc_op(
        self,
        docs: List[BulkDocOperation],
        db_name: str,
        scope: str = "",
        collection: str = "",
        new_edits: bool = True,
    ):
        with self.__tracer.start_as_current_span(
            "bulk_documents_operation",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            keyspace = self.keyspace_builder(db_name, scope, collection)
            body = {"docs": list(u.body for u in docs), "new_edits": new_edits}
            resp = await self._send_request(
                "post", f"/{keyspace}/_bulk_docs", JSONDictionary(body)
            )

            if not isinstance(resp, list):
                raise ValueError(
                    f"Inappropriate response from edge server  bulk doc op (not JSON), response:{resp}"
                )

            cast_resp = cast(dict, resp)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"bulk_documents_operation Edge Server had error '{cast_resp.get('reason')}'",
                )
            return cast_resp

    async def blip_sync(self, db_name: str, scope: str = "", collection: str = ""):
        with self.__tracer.start_as_current_span(
            "get web socket connection for client ",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            keyspace = self.keyspace_builder(db_name, scope, collection)
            resp = await self._send_request("get", f"{keyspace}/_blipsync")

            if resp and not isinstance(resp, dict):
                raise ValueError(
                    "Inappropriate response from edge server get /_blipsync (not JSON)"
                )
            cast_resp = cast(dict, resp) if resp else {}
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"get web socket connection for client with Edge Server had error '{cast_resp['reason']}'",
                )

    async def set_auth(self, auth: bool = True, name="admin_user", password="password"):
        if not auth:
            self.__auth = False
        self.__auth_name = name
        self.__auth_password = password

    async def kill_server(self) -> bool:
        with self.__tracer.start_as_current_span("kill edge server"):
            response = await self._send_request("post", "/kill-edgeserver")
            return response

    async def start_server(self, config: Optional[dict] = None) -> bool:
        with self.__tracer.start_as_current_span("start edge server"):
            payload = config if config is not None else {}
            response = await self._send_request(
                "post", "/start-edgeserver", JSONDictionary(payload)
            )
            return response

    async def set_config(self, config_file_path):
        await self.kill_server()
        with open(config_file_path) as f:
            cfg = json.load(f)
        await self.start_server(config=cfg)
        return EdgeServer(self.__hostname, config_file=config_file_path)

    async def reset_db(self, db_name: str = "db"):
        await self.kill_server()
        db_entry = self.__databases.get(db_name)
        filename = db_entry.get("path") if db_entry else None
        await self._send_request(
            "post", "/reset-db", JSONDictionary({"filename": filename})
        )
        await self.start_server()

    async def go_online_offline(
        self, allow: Optional[List] = None, deny: Optional[List] = None
    ) -> bool:
        with self.__tracer.start_as_current_span("go online offline"):
            payload = {}
            if allow is not None:
                payload["allow"] = allow
            if deny is not None:
                payload["deny"] = deny
            response = await self._send_request(
                "post", "firewall", JSONDictionary(payload)
            )
            return response

    async def reset_firewall(self) -> bool:
        with self.__tracer.start_as_current_span("reset firewall"):
            response = await self._send_request("post", "firewall")
            return response
