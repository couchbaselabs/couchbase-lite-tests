import asyncio
import json
import ssl
import tempfile
import urllib.parse
import uuid
from json import dumps
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin

import pyjson5 as json5
from aiohttp import ClientSession, TCPConnector, encode_basic_auth
from opentelemetry.trace import get_tracer
from pydantic import BaseModel, ConfigDict

from cbltest.api.error import (
    CblEdgeServerBadResponseError,
    CblHttpError,
    CblTestError,
    CblTimeoutError,
)
from cbltest.api.jsonserializable import JSONDictionary, JSONSerializable
from cbltest.api.sidecar import Caddy
from cbltest.api.syncgateway import (
    AllDocumentsResponse,
    CouchbaseVersion,
    RemoteDocument,
)
from cbltest.assertions import _assert_not_null
from cbltest.httplog import get_next_writer
from cbltest.jsonhelper import _get_typed_required
from cbltest.logging import cbl_warning
from cbltest.version import VERSION


class _EdgeServerModel(BaseModel):
    """A part of the config, keeping keys it does not declare, since Edge Server adds them between versions."""

    model_config = ConfigDict(extra="allow")


class HttpsConfig(_EdgeServerModel):
    """The ``https`` block, whose presence is what makes the Edge Server serve TLS."""

    tls_cert_path: str | None = None
    tls_key_path: str | None = None
    client_cert_path: str | None = None


class AuditConfig(_EdgeServerModel):
    """The ``logging.audit`` block."""

    file: str | None = None
    enable: str | None = None
    disable: str | None = None


class LoggingConfig(_EdgeServerModel):
    """The ``logging`` block."""

    audit: AuditConfig | None = None


class EdgeServerConfig(_EdgeServerModel):
    """One Edge Server config file."""

    interface: str = "0.0.0.0:59840"
    https: HttpsConfig | None = None
    users: str | None = None
    logging: LoggingConfig | None = None

    @classmethod
    def load(cls, config_file: str | Path) -> "EdgeServerConfig":
        """
        Reads and parses an Edge Server config file, which is JSON5.

        :param config_file: Local path to the config file
        :return: The parsed config
        """
        with open(config_file, encoding="utf-8") as file:
            return cls.model_validate(json5.loads(file.read()))

    @property
    def port(self) -> int:
        """The port the Edge Server listens on."""
        return int(self.interface.split(":")[1])

    @property
    def is_tls(self) -> bool:
        """Whether the Edge Server serves TLS."""
        return self.https is not None

    @property
    def is_mtls(self) -> bool:
        """Whether the Edge Server asks the client for a certificate."""
        return self.https is not None and self.https.client_cert_path is not None

    @property
    def declares_users(self) -> bool:
        """Whether the config declares users, so the Edge Server accepts credentials."""
        return bool(self.users)

    @property
    def audit_log(self) -> str | None:
        """Where the Edge Server writes its audit log, or None if the config declares none."""
        return self.logging.audit.file if self.logging is not None and self.logging.audit is not None else None


class EdgeServerVersion(CouchbaseVersion):
    """
    A class for parsing Edge Server Version
    """

    def parse(self, input: str) -> tuple[str, int]:
        first_lparen = input.find("(")
        first_semicol = input.find(";")
        if first_lparen == -1 or first_semicol == -1:
            return ("unknown", 0)

        version = input[0:first_lparen].strip()
        if not version:
            cbl_warning(f"Could not extract version from Edge Server version string: '{input}'")
            version = "unknown"

        try:
            build = int(input[first_lparen + 1 : first_semicol])
        except ValueError:
            cbl_warning(f"Could not parse build number from Edge Server version string: '{input}'")
            build = 0

        return (version, build)


class BulkDocOperation(JSONSerializable):
    # optype should be  "create", "update" or "delete". by default it is create
    def __init__(
        self,
        body: dict,
        _id: str | None = None,
        rev: str | None = None,
        optype: str = "create",
    ) -> None:
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

    def to_json(self) -> Any:
        return self._body


class EdgeServer:
    """
    A class for interacting with a given Edge Server instance
    """

    def __init__(
        self,
        url: str,
        user: str | None = None,
        password: str | None = None,
        config_file: str | None = None,
    ) -> None:
        """
        :param url: Hostname of the Edge Server
        :param user: User to authenticate as, or None for a client that sends no credentials
        :param password: That user's password
        :param config_file: Config the Edge Server is running on, which decides the port,
            the scheme, and whether it asks for credentials at all
        """
        self.__tracer = get_tracer(__name__, VERSION)
        if config_file is None:
            raise CblTestError("Config file cannot be None")
        self.__config = EdgeServerConfig.load(config_file)
        self._caddy = Caddy(url)
        self.__secure: bool = self.__config.is_tls
        self.__mtls: bool = self.__config.is_mtls
        self.__hostname: str = url
        self.__port: int = self.__config.port
        ws_scheme = "wss://" if self.__secure else "ws://"
        self.__replication_url = f"{ws_scheme}{url}:{self.__port}"
        self.scheme = "https://" if self.__secure else "http://"
        # A config that declares no users turns credentials away, so send none against one.
        self.__needs_auth = self.__config.declares_users
        credentials = encode_basic_auth(user, password or "", "ascii") if self.__needs_auth and user else None
        self.__session = self._create_session(credentials)

    @property
    def needs_auth(self) -> bool:
        """Whether the running config declares users, so a client can authenticate as one."""
        return self.__needs_auth

    async def close(self) -> None:
        """Close the session this client requests on, and its Caddy's."""
        if not self.__session.closed:
            await self.__session.close()
        await self._caddy.close()

    @property
    def hostname(self) -> str:
        return self.__hostname

    @property
    def caddy(self) -> Caddy:
        """Gets the Caddy file server running alongside this Edge Server"""
        return self._caddy

    @property
    def audit_log_path(self) -> str:
        """
        Where the running config writes its audit log on the Edge Server host.

        :raises CblTestError: If the config declares no audit log
        """
        audit_log = self.__config.audit_log
        if audit_log is None:
            raise CblTestError(f"Edge Server [{self.__hostname}] runs a config that declares no audit log")

        return audit_log

    def _create_session(self, auth_header: str | None) -> ClientSession:
        """Create a session, where `auth_header` is an `Authorization` header value
        from `aiohttp.encode_basic_auth`, or None for an anonymous session."""
        headers = {"Authorization": auth_header} if auth_header is not None else None
        if self.__secure:
            CERT_DIR = Path.home() / ".cbl_certs"
            ssl_context = ssl.create_default_context(cafile=CERT_DIR / "ca_cert.pem")
            ssl_context.check_hostname = False
            if self.__mtls:
                ssl_context.load_cert_chain(
                    certfile=str(CERT_DIR / "client_cert.pem"),
                    keyfile=str(CERT_DIR / "client_key.pem"),
                )

            return ClientSession(
                f"{self.scheme}{self.__hostname}:{self.__port}",
                headers=headers,
                connector=TCPConnector(ssl=ssl_context),
            )
        return ClientSession(f"{self.scheme}{self.__hostname}:{self.__port}", headers=headers)

    async def _send_request(
        self,
        method: str,
        path: str,
        payload: JSONSerializable | None = None,
    ) -> Any:
        with self.__tracer.start_as_current_span("send_request", attributes={"http.method": method, "http.path": path}):
            headers = {"Content-Type": "application/json"} if payload is not None else None
            data = "" if payload is None else payload.serialize()
            writer = get_next_writer()
            writer.write_begin(f"Edge Server [{self.__hostname}] -> {method.upper()} {path}", data)
            resp = await self.__session.request(method, path, data=data, headers=headers)

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
                    body=data,
                )

            return ret_val

    def keyspace_builder(self, db_name: str = "", scope: str = "", collection: str = "") -> str:
        keyspace = db_name
        if scope:
            keyspace += f".{scope}"
        if collection:
            keyspace += f".{collection}"
        return keyspace

    async def get_version(self) -> CouchbaseVersion:
        resp = await self._send_request("get", "/")
        assert isinstance(resp, dict)
        resp_dict = cast(dict, resp)
        vendor = _get_typed_required(resp_dict, "vendor", dict)
        raw_version = _get_typed_required(vendor, "version", str)
        return EdgeServerVersion(raw_version)

    async def get_all_documents(
        self,
        db_name: str,
        scope: str = "",
        collection: str = "",
        descending: bool = False,
        endkey: str | None = None,
        keys: list[str] | None = None,
        startkey: str | None = None,
        include_docs: bool = False,
    ) -> AllDocumentsResponse:
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
            resp = await self._send_request("get", f"/{keyspace}/_all_docs{request_url}")
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
    ) -> Any:
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
    ) -> RemoteDocument | None:
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
                raise ValueError("Inappropriate response from edge server get /doc (not JSON)")

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                if cast_resp.get("reason") == "missing" or cast_resp.get("reason") == "deleted":
                    return None

                raise CblEdgeServerBadResponseError(
                    500,
                    f"Get doc from edge server had error '{cast_resp.get('reason')}'",
                    body=dumps(cast_resp),
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
                    body=dumps(response),
                )
            raise CblEdgeServerBadResponseError(
                500,
                f"Unexpected response type from adhoc query: {type(response)}",
                body=str(response),
            )

    async def get_active_tasks(self) -> list:
        with self.__tracer.start_as_current_span("get all active tasks"):
            response = await self._send_request("get", "/_active_tasks")
            if isinstance(response, list):
                return response

            if isinstance(response, dict) and "error" in response:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"get_active_tasks with Edge Server had error '{response.get('reason')}'",
                    body=dumps(response),
                )
            raise CblEdgeServerBadResponseError(
                500,
                f"Unexpected response type from get_active_tasks: {type(response)}",
                body=str(response),
            )

    async def get_db_info(self, db_name: str, scope: str = "", collection: str = "") -> dict:
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
                raise ValueError("Inappropriate response from edge server get /  (not JSON)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"get database info  from edge server had error '{cast_resp.get('reason')}'",
                    body=dumps(cast_resp),
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
    ) -> Any:
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

            response = await self._send_request("post", "/_replicate", JSONDictionary(payload))
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server post /_replicate (not JSON)")

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"start replication with edge server had error '{cast_resp.get('reason')}'",
                    body=dumps(cast_resp),
                )
            return cast_resp.get("session_id")

    async def replication_status(self, replicator_id: str) -> dict:
        with self.__tracer.start_as_current_span(
            "get replication status with Edge Server",
            attributes={"cbl.replicator.id": replicator_id},
        ):
            response = await self._send_request("get", f"/_replicate/{replicator_id}")
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server get status  /_replicate (not JSON)")

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"get replication status with Edge Server had error '{cast_resp.get('reason')}'",
                    body=dumps(cast_resp),
                )
            return cast_resp

    async def all_replication_status(self) -> list:
        with self.__tracer.start_as_current_span("All Replication status with Edge Server"):
            response = await self._send_request("get", "/_replicate")
            if isinstance(response, list):
                return response
            if isinstance(response, dict) and "error" in response:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"all_replication_status with Edge Server had error '{response.get('reason')}'",
                    body=dumps(response),
                )
            raise CblEdgeServerBadResponseError(
                500,
                f"Unexpected response type from all_replication_status: {type(response)}",
                body=str(response),
            )

    async def stop_replication(self, replicator_id: int) -> None:
        with self.__tracer.start_as_current_span(
            "Stop Replication with Edge Server",
            attributes={"cbl.replicator.id": replicator_id},
        ):
            response = await self._send_request("delete", f"/_replicate/{replicator_id}")

            if response and not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server  stop  /_replicate (not JSON)")

            cast_resp = cast(dict, response) if response else {}
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"stop replication  with Edge Server had error '{cast_resp.get('reason')}'",
                    body=dumps(cast_resp),
                )

    def replication_url(self, db_name: str) -> str:
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
    ) -> dict:
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
            response = await self._send_request("post", f"{keyspace}/_changes", payload=JSONDictionary(payload))

            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server post /_changes (not JSON)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"get changes feed with Edge Server had error '{cast_resp.get('reason')}'",
                    body=dumps(cast_resp),
                )
            return cast_resp

    async def named_query(
        self,
        db_name: str,
        scope: str = "",
        collection: str = "",
        name: str | None = None,
        params: dict | None = None,
    ) -> list:
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
            response = await self._send_request("post", f"/{keyspace}/_query/{name}", payload=JSONDictionary(payload))

            if isinstance(response, list):
                return response

            if isinstance(response, dict) and "error" in response:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"named query with Edge Server had error '{response.get('reason')}'",
                    body=dumps(response),
                )
            raise CblEdgeServerBadResponseError(
                500,
                f"Unexpected response type from named query: {type(response)}",
                body=str(response),
            )

    async def adhoc_query(
        self,
        db_name: str,
        scope: str = "",
        collection: str = "",
        query: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> list:
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
            response = await self._send_request("post", f"/{keyspace}/_query", payload=JSONDictionary(payload))

            if isinstance(response, list):
                return response

            if isinstance(response, dict) and "error" in response:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"adhoc query with Edge Server had error '{response.get('reason')}'",
                    body=dumps(response),
                )
            raise CblEdgeServerBadResponseError(
                500,
                f"Unexpected response type from adhoc query: {type(response)}",
                body=str(response),
            )

    async def add_document_auto_id(
        self,
        document: dict,
        db_name: str,
        scope: str = "",
        collection: str = "",
        expires: int = 0,
        ttl: int = 0,
    ) -> dict:
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

            response = await self._send_request("post", f"/{keyspace}/{qp}", payload=JSONDictionary(document))

            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server add doc auto ID (not JSON)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"add document with auto ID Edge Server had error '{cast_resp.get('reason')}'",
                    body=dumps(cast_resp),
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

            response = await self._send_request("put", f"/{keyspace}/{id}{qp}", payload=JSONDictionary(document))

            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server add doc (not JSON)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"add document with ID Edge Server had error '{cast_resp.get('reason')}'",
                    body=dumps(cast_resp),
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
            response = await self._send_request("delete", f"{keyspace}/{id}/{key}?rev={revid}")

            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from edge server delete sub-document (not JSON)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"delete sub-document Edge Server had error '{cast_resp.get('reason')}'",
                    body=dumps(cast_resp),
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
        value: Any = None,
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
                raise ValueError("Inappropriate response from edge server put sub-document (not JSON)")
            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"put sub-document Edge Server had error '{cast_resp.get('reason')}'",
                    body=dumps(cast_resp),
                )
            return cast_resp

    async def get_sub_document(self, id: str, key: str, db_name: str, scope: str = "", collection: str = "") -> Any:
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
                        f"get sub-document Edge Server had error '{cast_resp.get('reason')}'",
                        body=dumps(cast_resp),
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
    ) -> list | None:
        with self.__tracer.start_as_current_span(
            "bulk_documents_operation",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            keyspace = self.keyspace_builder(db_name, scope, collection)
            body = {"docs": [u.body for u in docs], "new_edits": new_edits}
            resp = await self._send_request("post", f"/{keyspace}/_bulk_docs", JSONDictionary(body))

            if isinstance(resp, dict):
                cast_resp = cast(dict, resp)
                if "error" in cast_resp:
                    raise CblEdgeServerBadResponseError(
                        500,
                        f"bulk_documents_operation Edge Server had error '{cast_resp.get('reason')}'",
                        body=dumps(cast_resp),
                    )
            if isinstance(resp, list):
                return cast(list, resp)

    async def download_log_file(self, log_file: str, local_path: str | Path) -> Path:
        """
        Downloads a log file from the Edge Server host via its Caddy HTTP server
        (port :data:`~cbltest.api.sidecar.CADDY_PORT`), writing it straight to disk so a log of
        any size never has to fit in memory.

        :param log_file: Absolute path to the log file on the Edge Server host
        :param local_path: Local path to write the log file to
        :return: The local path the log file was written to
        :raises FileNotFoundError: If the log file does not exist
        :raises CblTimeoutError: If the transfer stops making progress
        :raises CblTestError: For other HTTP or network errors
        """
        with self.__tracer.start_as_current_span("download_log_file", attributes={"cbl.log_file": log_file}):
            try:
                return await self._caddy.download(log_file, local_path)
            except CblHttpError as e:
                if e.code != 404:
                    raise
                raise FileNotFoundError(f"{log_file} does not exist on {self.__hostname}") from e

    async def check_audit_log(self, search_string: str) -> list[str]:
        """
        Downloads the audit log the running config declares and returns the lines that contain
        search_string.  Matches on raw bytes, one line at a time, so a log of any size never
        has to fit in memory and a record quoting bytes that are not valid UTF-8 still scans.

        :param search_string: String to search for (e.g. audit event id).
        :return: The matching lines, or an empty list if the audit log does not exist
        :raises CblTimeoutError: If the transfer stops making progress
        :raises CblTestError: If the config declares no audit log, or for HTTP or network errors
        """
        log_file = self.audit_log_path
        with (
            self.__tracer.start_as_current_span(
                "check_audit_log",
                attributes={
                    "cbl.search_string": search_string,
                    "cbl.log_file": log_file,
                },
            ),
            tempfile.TemporaryDirectory() as tmpdir,
        ):
            try:
                local_path = await self.download_log_file(log_file, Path(tmpdir) / Path(log_file).name)
            except FileNotFoundError:
                # Nothing was ever logged, so there are no matching lines.  Every other
                # failure raises, or an unreachable host would read as an empty log.
                cbl_warning(f"{log_file} does not exist on {self.__hostname}, treating as empty")
                return []

            needle = search_string.encode()
            with local_path.open("rb") as f:
                return [line.decode(errors="replace").rstrip("\r\n") for line in f if needle in line]

    async def wait_for_idle(self, replicator_key: int = 0, timeout: int = 30) -> None:
        is_idle = False
        retry = 6
        while not is_idle and retry > 0:
            status = await self.all_replication_status()
            if len(status) != 0:
                assert "error" not in status[replicator_key], f"Replication setup failure: {status}"
                if status[replicator_key]["status"] == "Idle":
                    is_idle = True
                else:
                    await asyncio.sleep(timeout)
                    retry -= 1
            else:
                is_idle = True
        if not is_idle and retry == 0:
            raise CblTimeoutError("Timeout waiting for replicator status")
