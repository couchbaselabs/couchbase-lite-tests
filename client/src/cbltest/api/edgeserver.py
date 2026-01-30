import json
import ssl
import time
import urllib.parse
import uuid
from json import dumps
from pathlib import Path
from typing import Any, List, cast
from urllib.parse import urljoin

import pyjson5 as json5  # type: ignore[import-not-found]
from aiohttp import BasicAuth, ClientSession, TCPConnector
from opentelemetry.trace import get_tracer

from cbltest.api.error import (
    CblEdgeServerBadResponseError,
    CblTestError,
    CblTimeoutError,
)
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

    def parse(self, input: str) -> tuple[str, int]:
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
        _id: str | None = None,
        rev: str | None = None,
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
        admin_user: str = "admin_user",
        admin_password: str = "password",
        config_file=None,
    ):
        self.__tracer = get_tracer(__name__, VERSION)
        if config_file is None:
            raise CblTestError("Config file cannot be None")
        port, secure, mtls, is_auth, is_anonymous_auth = self._decode_config_file(
            config_file
        )
        self.__secure: bool = secure
        self.__mtls: bool = mtls
        self.__hostname: str = url
        self.__port: int = port
        self.__anonymous_auth: bool = is_anonymous_auth
        self.__config_file: str = config_file
        self.__auth_name = admin_user
        self.__auth_password = admin_password
        self.__auth = is_auth
        ws_scheme = "wss://" if secure else "ws://"
        self.__replication_url = f"{ws_scheme}{url}:{port}"
        self.scheme = "https://" if secure else "http://"
        self.__anonymous_session = self._create_session(self.scheme, url, port, None)
        self.__admin_session = self._create_session(
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
        with open(config_file, encoding="utf-8") as file:
            config_content = file.read()
        config = json5.loads(config_content)
        https = config.get("https", False)
        interface = config.get("interface", "0.0.0.0:59840")
        port = interface.split(":")[1]
        enable_anonymous_users = config.get("enable_anonymous_users", False)
        mtls = False
        if https:
            client_cert_path = https.get("client_cert_path", False)
            if client_cert_path:
                mtls = True
            https = True
        users = True if config.get("users", False) else False
        return (
            port,
            https,
            mtls,
            users,
            enable_anonymous_users,
        )

    def _create_session(
        self, scheme: str, url: str, port: int, auth: BasicAuth | None
    ) -> ClientSession:
        if self.__secure:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            return ClientSession(
                f"{scheme}{url}:{port}",
                auth=auth,
                connector=TCPConnector(ssl=ssl_context),
            )
        return ClientSession(f"{scheme}{url}:{port}", auth=auth)

    async def _send_request(
        self,
        method: str,
        path: str,
        payload: JSONSerializable | None = None,
        params: dict[str, str] | None = None,
        session: ClientSession | None = None,
    ) -> Any:
        if session is None:
            if self.__auth:
                session = self.__admin_session
            else:
                session = self.__anonymous_session

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
                    resp.status,
                    f"{method} {path} returned {resp.status} for payload {data}",
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
        revid: str | None = None,
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
            qp = f"?rev={revid}" if revid else ""
            response = await self._send_request("get", f"/{keyspace}/{doc_id}{qp}")
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

    async def get_all_dbs(self) -> list:
        with self.__tracer.start_as_current_span("get all database"):
            response = await self._send_request("get", "/_all_dbs")
            if isinstance(response, list):
                return response
            if isinstance(response, dict) and "error" in response:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"_all_dbs with Edge Server had error '{response.get('reason')}'",
                )
            raise CblEdgeServerBadResponseError(
                500,
                f"Unexpected response type from adhoc query: {type(response)}",
            )

    async def get_active_tasks(self):
        with self.__tracer.start_as_current_span("get all active tasks"):
            response = await self._send_request("get", "/_active_tasks")
            if isinstance(response, list):
                return response

            if isinstance(response, dict) and "error" in response:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"get_active_tasks with Edge Server had error '{response.get('reason')}'",
                )
            raise CblEdgeServerBadResponseError(
                500,
                f"Unexpected response type from get_active_tasks: {type(response)}",
            )

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
                    f"get database info  from edge server had error '{cast_resp['reason']}'",
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
        collections: list[str] | None = None,
        channels: list[str] | None = None,
        doc_ids: list[str] | None = None,
        headers: dict[str, str] | None = None,
        trusted_root_certs: str | None = None,
        pinned_cert: str | None = None,
        session_cookie: str | None = None,
        openid_token: str | None = None,
        tls_client_cert: str | None = None,
        tls_client_cert_key: str | None = None,
    ):
        with self.__tracer.start_as_current_span(
            "Start Replication with Edge Server",
            attributes={
                "cbl.source.name": source,
                "cbl.target.name": target,
                "cbl.collection.name": collections or [],
            },
        ):
            payload: dict[str, Any] = {
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
            if isinstance(response, list):
                return response
            if isinstance(response, dict) and "error" in response:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"all_replication_status with Edge Server had error '{response.get('reason')}'",
                )
            raise CblEdgeServerBadResponseError(
                500,
                f"Unexpected response type from all_replication_status: {type(response)}",
            )

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
        since: int | None = 0,
        feed: str | None = "normal",
        limit: int | None = None,
        filter_type: str | None = None,
        doc_ids: list[str] | None = None,
        include_docs: bool | None = False,
        active_only: bool | None = False,
        descending: bool | None = False,
        heartbeat: int | None = None,
        timeout: int | None = None,
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
        name: str | None = None,
        params: dict | None = None,
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

            if isinstance(response, list):
                return response

            if isinstance(response, dict) and "error" in response:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"named query with Edge Server had error '{response.get('reason')}'",
                )
            raise CblEdgeServerBadResponseError(
                500,
                f"Unexpected response type from named query: {type(response)}",
            )

    async def adhoc_query(
        self,
        db_name: str,
        scope: str = "",
        collection: str = "",
        query: str | None = None,
        params: dict[str, Any] | None = None,
    ):
        with self.__tracer.start_as_current_span(
            "Adhoc query",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            payload: dict[str, Any] = {"query": query}
            if params is not None:
                payload["params"] = params
            keyspace = self.keyspace_builder(db_name, scope, collection)
            response = await self._send_request(
                "post", f"/{keyspace}/_query", payload=JSONDictionary(payload)
            )

            if isinstance(response, list):
                return response

            if isinstance(response, dict) and "error" in response:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"adhoc query with Edge Server had error '{response.get('reason')}'",
                )
            raise CblEdgeServerBadResponseError(
                500,
                f"Unexpected response type from adhoc query: {type(response)}",
            )

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
        rev: str | None = None,
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
        docs: list[BulkDocOperation],
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

            if isinstance(resp, dict):
                cast_resp = cast(dict, resp)
                if "error" in cast_resp:
                    raise CblEdgeServerBadResponseError(
                        500,
                        f"bulk_documents_operation Edge Server had error '{cast_resp['reason']}'",
                    )
            if isinstance(resp, list):
                return cast(list, resp)

    async def set_auth(self, auth: bool = True, name="admin_user", password="password"):
        if not auth:
            self.__auth = False
        else:
            self.__auth_name = name
            self.__auth_password = password
            self.__admin_session = self._create_session(
                self.scheme,
                self.__hostname,
                self.__port,
                BasicAuth(self.__auth_name, self.__auth_password, "ascii"),
            )

    async def kill_server(self):
        with self.__tracer.start_as_current_span("kill edge server"):
            await self._send_request(
                "post", "/kill-edgeserver", session=self.__shell_session
            )

    async def check_log(
        self,
        search_string: str,
        log_file: str = "/home/ec2-user/audit/EdgeServerAuditLog.txt",
    ) -> List[str]:
        """
        Grep the Edge Server audit log file for lines matching search_string via shell2http.

        :param search_string: String to search for (e.g. audit event id).
        :param log_file: Path to the log file on the Edge Server host.
        :return: List of matching lines, or empty list if none or on error.
        """
        with self.__tracer.start_as_current_span(
            "check_log",
            attributes={
                "cbl.search_string": search_string,
                "cbl.log_file": log_file,
            },
        ):
            try:
                response = await self._send_request(
                    "post",
                    "/check-log",
                    payload=JSONDictionary({"search_string": search_string, "log_file": log_file}),
                    session=self.__shell_session,
                )
                if isinstance(response, str):
                    return response.strip().splitlines() if response.strip() else []
                if isinstance(response, list):
                    return response
                return []
            except Exception:
                return []

    async def start_server(self, config: dict = {}):
        with self.__tracer.start_as_current_span("start edge server"):
            await self._send_request(
                "post",
                "/start-edgeserver",
                JSONDictionary(config),
                session=self.__shell_session,
            )

    async def configure_dataset(self, db_name="db", config_file: str | None = None):
        if not config_file:
            repo_root = next(
                p
                for p in (Path(__file__).resolve(), *Path(__file__).resolve().parents)
                if p.name == "couchbase-lite-tests"
            )
            config_file = f"{repo_root}/environment/aws/es_setup/config/config.json"
        await self.kill_server()
        await self._send_request(
            "post",
            "/reset-db",
            JSONDictionary({"filename": f"{db_name}.cblite2"}),
            session=self.__shell_session,
        )
        with open(config_file) as f:
            cfg = json.load(f)
        await self.start_server(config=cfg)
        return EdgeServer(self.__hostname, config_file=config_file)

    async def set_firewall_rules(
        self,
        allow: list[Any] | None = None,
        deny: list[Any] | None = None,
    ):
        """
        Add firewall rules to the edge server host. Can be used to block SGW connection to ES.

        :param allow: The IPs allowed to access edge-server. Used to accept incoming SGW connection.
        :param deny: The IPs denied from accessing edge-server. Used to deny incoming SGW connection.
        """
        with self.__tracer.start_as_current_span("go online offline"):
            payload: dict[str, Any] = {}
            if allow:
                payload["allow"] = allow
            if deny:
                payload["deny"] = deny
            await self._send_request(
                "post",
                "firewall",
                JSONDictionary(payload),
                session=self.__shell_session,
            )

    async def reset_firewall(self):
        with self.__tracer.start_as_current_span("reset firewall"):
            await self._send_request("post", "firewall", session=self.__shell_session)

    async def add_user(self, name, password, role="admin"):
        with self.__tracer.start_as_current_span("Add user"):
            await self.kill_server()
            payload = {"name": name, "password": password, "role": role}
            await self._send_request(
                "post",
                "add-user",
                JSONDictionary(payload),
                session=self.__shell_session,
            )
            await self.start_server()

    async def wait_for_idle(self, replicator_key=0, timeout=30):
        is_idle = False
        retry = 6
        while not is_idle and retry > 0:
            status = await self.all_replication_status()
            if len(status) != 0:
                assert "error" not in status[replicator_key].keys(), (
                    f"Replication setup failure: {status}"
                )
                if status[replicator_key]["status"] == "Idle":
                    is_idle = True
                else:
                    time.sleep(timeout)
                    retry -= 1
            else:
                is_idle = True
        if not is_idle and retry == 0:
            raise CblTimeoutError("Timeout waiting for replicator status")
