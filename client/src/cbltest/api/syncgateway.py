import asyncio
import re
import ssl
from abc import ABC, abstractmethod
from json import dumps, loads
from pathlib import Path
from typing import Any, cast
from urllib.parse import urljoin

from aiohttp import BasicAuth, ClientError, ClientSession, ClientTimeout, TCPConnector
from aiohttp.client_exceptions import ClientConnectorError
from opentelemetry.trace import get_tracer

from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.jsonserializable import JSONDictionary, JSONSerializable
from cbltest.assertions import _assert_not_null
from cbltest.httplog import get_next_writer
from cbltest.jsonhelper import _get_typed_required
from cbltest.logging import cbl_error, cbl_info, cbl_warning
from cbltest.utils import assert_not_null
from cbltest.version import VERSION

# This is copied from environment/aws/sgw_setup/cert/ca_cert.pem
# So if that file ever changes, change this too.
_SGW_CA_CERT: str = """-----BEGIN CERTIFICATE-----
MIIFWTCCA0GgAwIBAgIUBdrc0OhquX8RnXtZ6AiOY+57C18wDQYJKoZIhvcNAQEL
BQAwPDEZMBcGA1UEAwwQSW50ZXJuYWwgVGVzdCBDQTESMBAGA1UECgwJQ291Y2hi
YXNlMQswCQYDVQQGEwJVUzAeFw0yNTEwMjkwMTAzMDBaFw0yNzEwMjkwMTAzMDBa
MDwxGTAXBgNVBAMMEEludGVybmFsIFRlc3QgQ0ExEjAQBgNVBAoMCUNvdWNoYmFz
ZTELMAkGA1UEBhMCVVMwggIiMA0GCSqGSIb3DQEBAQUAA4ICDwAwggIKAoICAQCl
vMLIQDFfEcttEUSzBKkzoRSSLJ3Z/73xmJxBenCtZ9HasLhF3iJxwyQK09nD7sLv
RRwLeRfY8QObr/F/qJAa1cQtVA/5UxIiKsjDk+TrUibg4p6NFSgKUEg+08D0tRHG
CF3CF/3qcM/10A+Pg2K1COaAtPrYjslOv8DoDBzwOBxibaheDZmtBdPEeHghDXZr
DWYDe2770XGzKYqINCEDxNdyDUBdiNSzuX2h/YeZi6vGTtpAt3Iti2SIerRrCiah
UOlykQoqiDVh4JPXts79Xhszw0oDK6YWHEBBfXmYDUdYAyF97XC6hZc+6HxiCVTB
887mkyLCuKMGfB3dabyCqJ31fXm7gmufOs8voCfi/sKjLgcdZQUY4Gw345oYI3Yw
O41ig/uR04KW2xASba38vXt0fEl9/50+AO3xAy9oaY36nLSnBwTV72VbvTlvevGf
zSHbVIbtzcuovpudghYizmIqMEFguc8VsGgmwZb8mkypzB80SOoED3nJRziIK1ym
e+NuO0DIG6xMPUhputNhwqaeYXuSmcUH5YcmLN//ewMIjzxoH33H1cwcADHFioR/
YfIraSgVZCUhrN9aJlXdDOzDuhbVpXYJMbh5PfAiNLHPCXmo685Utf3ID+nFW1wd
WOIyuE3aJ5KVtG8hjlgKARV7eEqtxHjIl41QtsxalwIDAQABo1MwUTAdBgNVHQ4E
FgQUs2WdMu1wh9pJ5dPN80yN1NPAkSswHwYDVR0jBBgwFoAUs2WdMu1wh9pJ5dPN
80yN1NPAkSswDwYDVR0TAQH/BAUwAwEB/zANBgkqhkiG9w0BAQsFAAOCAgEAhiYP
a9dvAv/33u9vBKzUo045RRrfEpv80DSZQb4ttyulrIfbaLFHxaDcf2+S+mywAgoW
tf9SAwWO41qU7sfIBnFdCh982nP1dD707GDAZIe8ZNpl/Vu3hWY3TRQAp9ufA51w
wxn0m2tOS18UXpv5BNX1kVaLlAiOzRzmP1ghx08v9yd8eBgnjJ89D2m1U+qFS1Xk
egiyw66HHc3bG+eo523/l4RDqTx6KkhYnD3Bz89IxMaeK7CuynCY3VyVWPeIUfBr
clkDBqZa4o7fD3xV6Wiu/NHZsWJx3wog1wwelvlsyOVM+mfd4IOsPGVCCdDGtpoq
sT+f9mPDXXHKuDER8a7HiCgGK8rAQtCm/P5UFp2HUEIru/psWCXc3vh9HYVX9W79
TwS+AVAlkeVogs1ugqAXOuGmstnevj6XzA8PszCKDSIV+t1PJSSOtypUyN4gbGGx
sk1s9bwqy7bw2cMh3tt7HromGOoLnPxnsbQCs5HsqNdiEsPABWnI6m7epm0tFjCe
gHDyw1LdmZlZ3R7DT+CwfyhxL6hktfs8h7goR1vkmS2q0Alxmw9faKVVpDyWnsZC
qv6PMC0fI7jhvrr2Uf2Hhw9SQlBFwZ7LjjLqjuuJkclM4VooDElsLbPjSUbA+c5h
WCKJ0c94mrl9GwwBmcSIKJBvd6u7uAta2fREJeE=
-----END CERTIFICATE-----
"""


class _CollectionMap(JSONSerializable):
    @property
    def scope_name(self) -> str:
        return self.__scope_name

    @property
    def collections(self) -> list[str]:
        return list(self.__collections.keys())

    def __init__(self, scope_name: str) -> None:
        _assert_not_null(scope_name, "scope_name")
        self.__scope_name = scope_name
        self.__collections: dict[str, dict] = {}

    def add_collection(self, collection_name: str, payload: dict) -> None:
        if collection_name in self.__collections:
            raise ValueError(f"{collection_name} already exists in this map")

        self.__collections[collection_name] = payload

    def to_json(self) -> Any:
        return {"collections": self.__collections}


class PutDatabasePayload(JSONSerializable):
    """
    A class containing configuration options for a Sync Gateway database endpoint
    """

    @property
    def bucket(self) -> str:
        return self.__bucket

    def __init__(self, dataset_or_config: dict):
        _assert_not_null(dataset_or_config, "dataset_or_config")
        assert isinstance(dataset_or_config, dict), (
            "Invalid dataset_or_config passed to PutDatabasePayload"
        )
        self.__config: dict = dataset_or_config
        if "config" in dataset_or_config:
            self.__config = _get_typed_required(dataset_or_config, "config", dict)

        self.__bucket = _get_typed_required(self.__config, "bucket", str)
        """The bucket name in the backing Couchbase Server"""

        self.__scopes: dict[str, _CollectionMap] = {}
        scopes = _get_typed_required(self.__config, "scopes", dict)
        for scope in scopes:
            scope_dict = _get_typed_required(scopes, scope, dict)
            collections = _get_typed_required(scope_dict, "collections", dict)
            for collection in collections:
                collection_dict = _get_typed_required(collections, collection, dict)
                self._add_collection(collection_dict, scope, collection)

    def scopes(self) -> list[str]:
        """Gets all the scopes contained in the payload"""
        return list(self.__scopes.keys())

    def collections(self, scope: str) -> list[str]:
        """
        Gets a list of collections specified for the given scope

        :param scope: The name of the scope to check
        """

        map = self.__scopes.get(scope)
        if not map:
            raise KeyError(f"No collections present for {scope}")

        return map.collections

    def _add_collection(
        self, payload: dict, scope_name: str, collection_name: str
    ) -> None:
        """
        Adds a collection to the configuration of the database (must exist on Couchbase Server).
        The scope name and collection name both default to "_default".

        :param scope_name: The name of the scope in which the collection resides
        :param collection_name: The name of the collection to retrieve data from
        """
        _assert_not_null(scope_name, "scope_name")
        col_map = self.__scopes.get(scope_name, _CollectionMap(collection_name))
        self.__scopes[scope_name] = col_map
        col_map.add_collection(collection_name, payload)

    def to_json(self) -> Any:
        return self.__config


class ISGRPayload(JSONSerializable):
    """
    A class containing configuration options for Inter-Sync Gateway Replication (ISGR)
    """

    @property
    def replication_id(self) -> str:
        """Gets the replication ID"""
        return self.__replication_id

    @property
    def direction(self) -> str:
        """Gets the replication direction"""
        return self.__direction

    def __init__(
        self,
        replication_id: str,
        remote_url: str,
        remote_db: str,
        direction: str,
        continuous: bool = False,
        remote_username: str | None = None,
        remote_password: str | None = None,
        collections_local: list[str] | None = None,
        collections_remote: list[str] | None = None,
    ):
        """
        Creates an ISGR configuration payload.

        :param replication_id: A unique identifier for this replication
        :param remote_url: The URL of the remote Sync Gateway (e.g., "https://sg2.example.com:4985")
        :param remote_db: The database name on the remote Sync Gateway
        :param direction: Replication direction - "push", "pull", or "pushAndPull"
        :param continuous: Whether the replication should be continuous (default False)
        :param remote_username: Username for authenticating with the remote SG
        :param remote_password: Password for authenticating with the remote SG
        :param collections_local: List of local collections in "scope.collection" format
        :param collections_remote: List of remote collections to map to (parallel array with collections_local)
        """
        if direction not in ["push", "pull", "pushAndPull"]:
            raise ValueError(
                f"Invalid direction: {direction}. Must be 'push', 'pull', or 'pushAndPull'"
            )
        self.__replication_id = replication_id
        self.__remote = f"{remote_url}/{remote_db}"
        self.__direction = direction
        self.__continuous = continuous
        self.__remote_username = remote_username
        self.__remote_password = remote_password
        self.__collections_local = collections_local
        self.__collections_remote = collections_remote

    def to_json(self) -> Any:
        body: dict[str, Any] = {
            "replication_id": self.__replication_id,
            "remote": self.__remote,
            "direction": self.__direction,
            "continuous": self.__continuous,
        }
        if self.__remote_username is not None:
            body["remote_username"] = self.__remote_username
        if self.__remote_password is not None:
            body["remote_password"] = self.__remote_password
        if (
            self.__collections_local is not None
            or self.__collections_remote is not None
        ):
            body["collections_enabled"] = True
        if self.__collections_local is not None:
            body["collections_local"] = self.__collections_local
        if self.__collections_remote is not None:
            body["collections_remote"] = self.__collections_remote
        return body


class AllDocumentsResponseRow:
    """
    A class representing a single entry in an all_docs response from Sync Gateway
    """

    @property
    def key(self) -> str:
        """Gets the key of the row"""
        return self.__key

    @property
    def id(self) -> str:
        """Gets the document ID of the row"""
        return self.__id

    @property
    def revid(self) -> str | None:
        """Gets the revision ID of the row"""
        return self.__revid

    @property
    def cv(self) -> str | None:
        """Gets the current version for the row"""
        return self.__cv

    @property
    def revision(self) -> str:
        """Gets the either revid or cv, whichever is populated (at least one must be)"""
        return cast(str, self.__revid if self.__revid is not None else self.__cv)

    def __init__(self, key: str, id: str, revid: str | None, cv: str | None) -> None:
        self.__key = key
        self.__id = id
        self.__revid = revid
        self.__cv = cv


class AllDocumentsResponse:
    """
    A class representing an all_docs response from Sync Gateway
    """

    @property
    def rows(self) -> list[AllDocumentsResponseRow]:
        """Gets the entries of the response"""
        return self.__rows

    def __len__(self) -> int:
        return self.__len

    def __init__(self, input: dict) -> None:
        self.__len = input["total_rows"]
        self.__rows: list[AllDocumentsResponseRow] = []
        for row in cast(list[dict], input["rows"]):
            rev = cast(dict, row["value"])
            self.__rows.append(
                AllDocumentsResponseRow(
                    row["key"],
                    row["id"],
                    cast(str, rev["rev"]) if "rev" in rev else None,
                    cast(str, rev["cv"]) if "cv" in rev else None,
                )
            )


class ChangesResponseEntry:
    """
    A class representing a single entry in a changes feed response from Sync Gateway
    """

    @property
    def seq(self) -> int:
        """Gets the sequence number"""
        return self.__seq

    @property
    def id(self) -> str:
        """Gets the document ID"""
        return self.__id

    @property
    def changes(self) -> list[str]:
        """Gets the list of changes (either rev IDs or version vectors depending on version_type parameter)"""
        return self.__changes

    @property
    def deleted(self) -> bool:
        """Gets whether this document was deleted"""
        return self.__deleted

    def __init__(self, entry: dict) -> None:
        self.__seq = entry.get("seq", 0)
        self.__id = cast(str, entry["id"])
        self.__deleted = entry.get("deleted", False)
        changes_list = cast(list[dict], entry.get("changes", []))
        self.__changes = [cast(str, c.get("rev") or c.get("cv")) for c in changes_list]


class ChangesResponse:
    """
    A class representing a changes feed response from Sync Gateway
    """

    @property
    def results(self) -> list[ChangesResponseEntry]:
        """Gets the list of changes"""
        return self.__results

    @property
    def last_seq(self) -> str:
        """Gets the last sequence number"""
        return self.__last_seq

    def __init__(self, input: dict) -> None:
        self.__results: list[ChangesResponseEntry] = []
        for entry in cast(list[dict], input.get("results", [])):
            self.__results.append(ChangesResponseEntry(entry))
        self.__last_seq = cast(str, input.get("last_seq", "0"))


class DocumentUpdateEntry(JSONSerializable):
    """
    A class that represents an update to a document.
    For creating a new document, set revid to None.
    """

    @property
    def id(self) -> str:
        """
        Gets the ID of the entry (NOTE: Will go away once SGW supports VV in REST)
        """
        return cast(str, self.__body["_id"])

    @property
    def rev(self) -> str | None:
        """
        Gets the rev ID of the entry (NOTE: Will go away once SGW supports VV in REST)
        """
        if "_rev" not in self.__body:
            return None

        return cast(str, self.__body["_rev"])

    def __init__(self, id: str, revid: str | None, body: dict):
        self.__body = body.copy()
        self.__body["_id"] = id
        if revid:
            self.__body["_rev"] = revid

    def swap_rev(self, revid: str) -> None:
        """
        Changes the revid to the provided one (NOTE: Will go away once SGW supports VV in REST)
        """
        self.__body["_rev"] = revid

    def to_json(self) -> Any:
        return self.__body


class RemoteDocument(JSONSerializable):
    """
    A class that represents the results of a document retrieved from Sync Gateway
    """

    @property
    def id(self) -> str:
        """Gets the ID of the document"""
        return self.__id

    @property
    def revid(self) -> str | None:
        """Gets the revision ID of the document"""
        return self.__rev

    @property
    def cv(self) -> str | None:
        """Gets the CV of the document"""
        return self.__cv

    @property
    def body(self) -> dict:
        """Gets the body of the document"""
        return self.__body

    @property
    def revision(self) -> str:
        """Gets either the CV (preferred) or revid of the document"""
        if self.__cv is not None:
            return self.__cv

        assert self.__rev is not None
        return self.__rev

    def __init__(self, body: dict) -> None:
        if "error" in body:
            raise ValueError("Trying to create remote document from error response")

        self.__body = body.copy()
        self.__id = cast(str, body["_id"])
        self.__rev = cast(str, body["_rev"]) if "_rev" in body else None
        self.__cv = cast(str, body["_cv"]) if "_cv" in body else None
        del self.__body["_id"]
        del self.__body["_rev"]
        if self.__cv is not None:
            del self.__body["_cv"]

    def to_json(self) -> Any:
        ret_val = self.__body.copy()
        ret_val["_id"] = self.__id
        ret_val["_rev"] = self.__rev
        ret_val["_cv"] = self.__cv
        return ret_val


class CouchbaseVersion(ABC):
    """
    A class for holding a version and build number of a product
    """

    @property
    def raw(self) -> str:
        return self.__raw

    @property
    def version(self) -> str:
        return self.__version

    @property
    def build_number(self) -> int:
        return self.__build_number

    @abstractmethod
    def parse(self, input: str) -> tuple[str, int]:
        pass

    def __init__(self, input: str):
        self.__raw = input
        parsed = self.parse(input)
        self.__version = parsed[0]
        self.__build_number = parsed[1]


class SyncGatewayVersion(CouchbaseVersion):
    """
    A class for parsing Sync Gateway Version
    """

    def parse(self, input: str) -> tuple[str, int]:
        first_lparen = input.find("(")
        first_semicol = input.find(";")
        if first_lparen == -1 or first_semicol == -1:
            return ("unknown", 0)

        return input[0:first_lparen], int(input[first_lparen + 1 : first_semicol])


class DatabaseStatusResponse:
    """
    A class representing a database status response from Sync Gateway
    """

    @property
    def db_name(self) -> str:
        """Gets the database name"""
        return self.__db_name

    @property
    def state(self) -> str:
        """Gets the database state ('Online', 'Offline', etc.)"""
        return self.__state

    @property
    def update_seq(self) -> int:
        """Gets the update sequence number"""
        return self.__update_seq

    def __init__(self, response: dict):
        self.__db_name = response.get("db_name", "")
        self.__state = response.get("state", "Unknown")
        self.__update_seq = response.get("update_seq", 0)


class _SyncGatewayBase:
    """
    Base class for Sync Gateway clients containing common document and database operations.
    This class should not be instantiated directly - use SyncGateway or SyncGatewayPublic instead.
    """

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        port: int,
        secure: bool = False,
    ):
        scheme = "https://" if secure else "http://"
        ws_scheme = "wss://" if secure else "ws://"
        self.__http_url = f"{scheme}{url}:{port}"
        # Replication always uses public port 4984
        self.__replication_url = f"{ws_scheme}{url}:4984"
        self._tracer = get_tracer(__name__, VERSION)
        self.__secure: bool = secure
        self.__hostname: str = url
        self.__port: int = port
        self.__session: ClientSession = self._create_session(
            secure,
            scheme,
            url,
            port,
            BasicAuth(username, password, "ascii"),
        )

    @property
    def hostname(self) -> str:
        """Gets the hostname of the Sync Gateway instance"""
        return self.__hostname

    @property
    def port(self) -> int:
        """Gets the HTTP API port of the Sync Gateway instance"""
        return self.__port

    @property
    def secure(self) -> bool:
        """Gets whether the Sync Gateway instance uses TLS"""
        return self.__secure

    def _create_session(
        self, secure: bool, scheme: str, url: str, port: int, auth: BasicAuth | None
    ) -> ClientSession:
        if secure:
            ssl_context = ssl.create_default_context(cadata=_SGW_CA_CERT)
            # Disable hostname check so that the pre-generated SG can be used on any machines.
            ssl_context.check_hostname = False
            return ClientSession(
                f"{scheme}{url}:{port}",
                auth=auth,
                connector=TCPConnector(ssl=ssl_context),
            )
        else:
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
            session = self.__session

        with self._tracer.start_as_current_span(
            "send_request", attributes={"http.method": method, "http.path": path}
        ):
            headers = (
                {"Content-Type": "application/json"} if payload is not None else None
            )
            data = "" if payload is None else payload.serialize()
            writer = get_next_writer()
            writer.write_begin(
                f"Sync Gateway [{self.__http_url}] -> {method.upper()} {path}", data
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
                f"Sync Gateway [{self.__http_url}] <- {method.upper()} {path} {resp.status}",
                data,
            )
            if not resp.ok:
                raise CblSyncGatewayBadResponseError(
                    resp.status, f"{method} {path} returned {resp.status}"
                )

            return ret_val

    async def get_version(self) -> CouchbaseVersion:
        # Telemetry not really important for this call
        scheme = "https://" if self.secure else "http://"
        async with self._create_session(
            self.secure, scheme, self.hostname, 4984, None
        ) as s:
            resp = await self._send_request("get", "/", session=s)
            assert isinstance(resp, dict)
            resp_dict = cast(dict, resp)
            raw_version = _get_typed_required(resp_dict, "version", str)
            assert "/" in raw_version
            return SyncGatewayVersion(raw_version.split("/")[1])

    # async def wait_for_sgw_ready(self, retries: int = 60) -> None:
    #     for attempt in range(1, retries + 1):
    #         scheme = "https://" if self.secure else "http://"
    #         try:
    #             async with self._create_session(
    #                 self.secure, scheme, self.hostname, 4985, None
    #             ) as s:
    #                 resp = await self._send_request("get", "/_status", session=s)
    #                 if isinstance(resp, dict):
    #                     state = resp.get("state", "").lower()
    #                     if state in ("online", "running"):
    #                         return
    #                     cbl_info(
    #                         f"SGW not ready yet (attempt {attempt}/{retries}): state={state}",
    #                     )
    #         except Exception as e:
    #             last_error = e
    #             cbl_info(
    #                 f"SGW readiness check failed (attempt {attempt}/{retries}): {repr(e)}",
    #             )
    #         await asyncio.sleep(1)

    #     msg = "Sync Gateway admin API did not become ready"
    #     if last_error:
    #         msg += f"; last error: {last_error!r}"
    #     raise TimeoutError(msg)

    def tls_cert(self) -> str | None:
        if not self.secure:
            cbl_warning(
                "Sync Gateway instance not using TLS, returning empty tls_cert..."
            )
            return None

        return ssl.get_server_certificate((self.hostname, self.port))

    def replication_url(self, db_name: str, load_balancer: str | None = None) -> str:
        """
        Gets the replicator URL (e.g. ws://xxx) for a given db

        :param db_name: The DB to replicate with
        """
        _assert_not_null(db_name, "db_name")
        sgw_address = urljoin(self.__replication_url, db_name)
        if not load_balancer:
            return sgw_address

        return sgw_address.replace("wss", "ws").replace(self.hostname, load_balancer)

    async def bytes_transferred(self, dataset_name: str) -> tuple[int, int]:
        """
        Gets the bytes transferred for a given dataset

        :param dataset_name: The name of the dataset to get the bytes transferred for
        """
        resp_data = await self._send_request("get", "/_expvar")
        assert isinstance(resp_data, dict)
        expvars = cast(dict, resp_data)

        db_stats = expvars["syncgateway"]["per_db"][dataset_name]["database"]
        doc_reads_bytes = db_stats["doc_reads_bytes_blip"]
        doc_writes_bytes = db_stats["doc_writes_bytes_blip"]
        return doc_reads_bytes, doc_writes_bytes

    async def _put_database(
        self, db_name: str, payload: PutDatabasePayload, retry_count: int = 0
    ) -> None:
        with self._tracer.start_as_current_span(
            "put_database", attributes={"cbl.database.name": db_name}
        ) as current_span:
            try:
                await self._send_request("put", f"/{db_name}/", payload)
            except CblSyncGatewayBadResponseError as e:
                if e.code == 500 and retry_count < 3:
                    cbl_warning(
                        f"Sync gateway returned 500 from PUT database call, retrying ({retry_count + 1})..."
                    )
                    current_span.add_event("SGW returned 500, retry")
                    await self._put_database(db_name, payload, retry_count + 1)
                else:
                    raise

    async def put_database(self, db_name: str, payload: PutDatabasePayload) -> None:
        """
        Attempts to create a database on the Sync Gateway instance

        :param db_name: The name of the DB to create
        :param payload: The options for the DB to create
        """
        await self._put_database(db_name, payload, 0)

    async def get_database_status(self, db_name: str) -> DatabaseStatusResponse | None:
        """
        Gets the status of a database including its online/offline state.

        :param db_name: The name of the Database
        :return: DatabaseStatusResponse with state, sequences, etc. Returns None if database doesn't exist (404/403)
        """
        with self._tracer.start_as_current_span(
            "get_database_status", attributes={"cbl.database.name": db_name}
        ):
            try:
                resp = await self._send_request("get", f"/{db_name}/")
                assert isinstance(resp, dict)
                return DatabaseStatusResponse(cast(dict, resp))
            except CblSyncGatewayBadResponseError as e:
                if e.code in [403, 404]:  # Database doesn't exist
                    return None
                raise

    async def _delete_database(self, db_name: str, retry_count: int = 0) -> None:
        with self._tracer.start_as_current_span(
            "delete_database", attributes={"cbl.database.name": db_name}
        ) as current_span:
            try:
                await self._send_request("delete", f"/{db_name}")
            except CblSyncGatewayBadResponseError as e:
                if e.code == 500 and retry_count < 3:
                    cbl_warning(
                        f"Sync gateway returned 500 from DELETE database call, retrying ({retry_count + 1})..."
                    )
                    current_span.add_event("SGW returned 500, retry")
                    await asyncio.sleep(2)
                    await self._delete_database(db_name, retry_count + 1)
                elif e.code == 403:
                    pass
                else:
                    raise

    async def delete_database(self, db_name: str) -> None:
        """
        Deletes a database from Sync Gateway's configuration.

        .. warning:: This will not delete the data from the Couchbase Server bucket.
            To delete the data see the
            :func:`drop_bucket()<cbltest.api.couchbaseserver.CouchbaseServer.drop_bucket>` function

        :param db_name: The name of the Database to delete
        """
        await self._delete_database(db_name, 0)

    async def get_all_database_names(self) -> list[str]:
        """
        Gets the names of all databases configured on this Sync Gateway instance.

        :return: A list of database names
        """
        with self._tracer.start_as_current_span("get_all_database_names"):
            resp = await self._send_request("get", "/_all_dbs")
            assert isinstance(resp, list)
            return cast(list[str], resp)

    def _analyze_dataset_response(self, response: list) -> None:
        assert isinstance(response, list), "Invalid bulk docs response (not a list)"
        typed_response = cast(list, response)
        for r in typed_response:
            info = cast(dict, r)
            assert isinstance(info, dict), (
                "Invalid item inside bulk docs response list (not an object)"
            )
            if "error" in info:
                raise CblSyncGatewayBadResponseError(
                    info["status"],
                    f"At least one bulk docs insert failed ({info['error']})",
                )

    async def load_dataset(self, db_name: str, path: Path) -> None:
        """
        Populates a given database name with the JSON contents at the specified path

        .. note:: The expected format of the JSON file is one JSON object per line, which will
            be interpreted as one document insert per line

        :param db_name: The name of the database to populate
        :param path: The path of the JSON file to use as input
        """
        with self._tracer.start_as_current_span(
            "load_dataset",
            attributes={"cbl.database.name": db_name, "cbl.dataset.path": str(path)},
        ):
            last_scope: str = ""
            last_coll: str = ""
            collected: list[dict] = []
            with open(path, encoding="utf8") as fin:
                json_line = fin.readline()
                while json_line:
                    json = cast(dict, loads(json_line))
                    assert isinstance(json, dict), f"Invalid entry in {path}!"
                    scope = cast(str, json["scope"])
                    collection = cast(str, json["collection"])
                    if (
                        last_scope != scope
                        or last_coll != collection
                        or len(collected) > 500
                    ):
                        if last_scope and last_coll and collected:
                            resp = await self._send_request(
                                "post",
                                f"/{db_name}.{last_scope}.{last_coll}/_bulk_docs",
                                JSONDictionary({"docs": collected}),
                            )
                            self._analyze_dataset_response(resp)
                            collected.clear()

                    last_scope = scope
                    last_coll = collection
                    collected.append(json)
                    json_line = fin.readline()

            if collected:
                resp = await self._send_request(
                    "post",
                    f"/{db_name}.{last_scope}.{last_coll}/_bulk_docs",
                    JSONDictionary({"docs": collected}),
                )
                self._analyze_dataset_response(cast(list, resp))

    async def get_all_documents(
        self,
        db_name: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> AllDocumentsResponse:
        """
        Gets all the documents in the given collection from Sync Gateway (id and revid)

        :param db_name: The name of the Sync Gateway database to query
        :param scope: The scope to use when querying Sync Gateway
        :param collection: The collection to use when querying Sync Gateway
        """
        with self._tracer.start_as_current_span(
            "get_all_documents",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            resp = await self._send_request(
                "get", f"/{db_name}.{scope}.{collection}/_all_docs"
            )

            assert isinstance(resp, dict)
            return AllDocumentsResponse(cast(dict, resp))

    async def get_changes(
        self,
        db_name: str,
        scope: str = "_default",
        collection: str = "_default",
        version_type: str = "rev",
    ) -> ChangesResponse:
        """
        Gets the changes feed from Sync Gateway, including deleted documents

        :param db_name: The name of the Sync Gateway database to query
        :param scope: The scope to use when querying Sync Gateway
        :param collection: The collection to use when querying Sync Gateway
        :param version_type: The version type to use ('rev' for revision IDs, 'cv' for version vectors in SGW 4.0+)
        """
        with self._tracer.start_as_current_span(
            "get_changes",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            query_params = f"version_type={version_type}"
            resp = await self._send_request(
                "get", f"/{db_name}.{scope}.{collection}/_changes?{query_params}"
            )

            assert isinstance(resp, dict)
            return ChangesResponse(cast(dict, resp))

    async def _rewrite_rev_ids(
        self,
        db_name: str,
        updates: list[DocumentUpdateEntry],
        scope: str,
        collection: str,
    ) -> None:
        all_docs_body = list(u.id for u in updates if u.rev is not None)
        all_docs_response = await self._send_request(
            "post",
            f"/{db_name}.{scope}.{collection}/_all_docs",
            JSONDictionary({"keys": all_docs_body}),
        )

        if not isinstance(all_docs_response, dict):
            raise ValueError(
                "Inappropriate response from sync gateway _all_docs (not JSON dict)"
            )

        rows = cast(dict, all_docs_response)["rows"]
        if not isinstance(rows, list):
            raise ValueError(
                "Inappropriate response from sync gateway _all_docs (rows not a list)"
            )

        for r in cast(list, rows):
            next_id = r["id"]
            found = assert_not_null(
                next((u for u in updates if u.id == next_id), None),
                f"Unable to find {next_id} in updates!",
            )
            new_rev_id = r["value"]["rev"]
            cbl_info(
                f"For document {found.id}: Swapping revid from {found.rev} to {new_rev_id}"
            )
            found.swap_rev(new_rev_id)

    async def update_documents(
        self,
        db_name: str,
        updates: list[DocumentUpdateEntry],
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        """
        Sends a list of documents to be updated on Sync Gateway

        :param db_name: The name of the DB endpoint to update
        :param updates: A list of updates to perform
        :param scope: The scope that the updates will be applied to (default '_default')
        :param collection: The collection that the updates will be applied to (default '_default')
        """
        with self._tracer.start_as_current_span(
            "update_documents",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            await self._rewrite_rev_ids(db_name, updates, scope, collection)

            body = {"docs": list(u.to_json() for u in updates)}

            await self._send_request(
                "post",
                f"/{db_name}.{scope}.{collection}/_bulk_docs",
                JSONDictionary(body),
            )

    async def upsert_documents(
        self,
        db_name: str,
        updates: list[DocumentUpdateEntry],
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        """
        Upserts a list of documents on Sync Gateway.
        Its different from update_documents in that it will not overwrite the doc body in case the
            doc already exists.
        It will preserve the existing body fields and only add / update whatever is being passed,
            like the behaviour shown by the function batch_upsert used in CBL updates.

        :param db_name: The name of the DB endpoint to upsert
        :param updates: A list of upserts to perform
        :param scope: The scope that the upserts will be applied to (default '_default')
        :param collection: The collection that the upserts will be applied to (default '_default')
        """
        with self._tracer.start_as_current_span(
            "update_documents",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            merged_updates = []
            for update in updates:
                try:
                    current_doc = await self.get_document(
                        db_name, update.id, scope, collection
                    )
                    if current_doc is not None:
                        current_body = dict(current_doc.body)
                        current_body.update(update.to_json())
                        current_body["_id"] = update.id
                        if update.rev:
                            current_body["_rev"] = update.rev
                    else:
                        current_body = update.to_json()
                except Exception:
                    current_body = update.to_json()
                merged_updates.append(
                    DocumentUpdateEntry(update.id, update.rev, current_body)
                )

            await self._rewrite_rev_ids(db_name, merged_updates, scope, collection)
            body = {"docs": list(u.to_json() for u in merged_updates)}
            await self._send_request(
                "post",
                f"/{db_name}.{scope}.{collection}/_bulk_docs",
                JSONDictionary(body),
            )

    async def _replaced_revid(
        self, doc_id: str, revid: str, db_name: str, scope: str, collection: str
    ) -> str:
        response = await self._send_request(
            "get", f"/{db_name}.{scope}.{collection}/{doc_id}?show_cv=true"
        )
        assert isinstance(response, dict)
        response_dict = cast(dict, response)
        assert revid == response_dict["_cv"] or revid == response_dict["_rev"]
        return cast(dict, response)["_rev"]

    async def delete_document(
        self,
        doc_id: str,
        revid: str,
        db_name: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        """
        Deletes a document from Sync Gateway

        :param doc_id: The document ID to delete
        :param revid: The revision ID of the existing document
        :param db_name: The name of the DB endpoint that the document exists in
        :param scope: The scope that the document exists in (default '_default')
        :param collection: The collection that the document exists in (default '_default')
        """
        with self._tracer.start_as_current_span(
            "delete_document",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            if "@" in revid:
                new_rev_id = await self._replaced_revid(
                    doc_id, revid, db_name, scope, collection
                )
            else:
                new_rev_id = revid

            await self._send_request(
                "delete",
                f"/{db_name}.{scope}.{collection}/{doc_id}",
                params={"rev": new_rev_id},
            )

    async def purge_document(
        self,
        doc_id: str,
        db_name: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        """
        Purges a document from Sync Gateway

        :param doc_id: The document ID to delete
        :param db_name: The name of the DB endpoint that the document exists in
        :param scope: The scope that the document exists in (default '_default')
        :param collection: The collection that the document exists in (default '_default')
        """
        with self._tracer.start_as_current_span(
            "purge_document",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            body = {doc_id: ["*"]}

            await self._send_request(
                "post", f"/{db_name}.{scope}.{collection}/_purge", JSONDictionary(body)
            )

    async def get_document(
        self,
        db_name: str,
        doc_id: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> RemoteDocument | None:
        """
        Gets a document from Sync Gateway

        :param db_name: The name of the DB endpoint that the document exists in
        :param doc_id: The document ID to get
        :param scope: The scope that the document exists in (default '_default')
        :param collection: The collection that the document exists in (default '_default')
        """
        with self._tracer.start_as_current_span(
            "get_document",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            response = await self._send_request(
                "get", f"/{db_name}.{scope}.{collection}/{doc_id}"
            )
            if not isinstance(response, dict):
                raise ValueError(
                    "Inappropriate response from sync gateway get /doc (not JSON)"
                )

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                if cast_resp["reason"] == "missing" or cast_resp["reason"] == "deleted":
                    return None

                raise CblSyncGatewayBadResponseError(
                    500, f"Get doc from sync gateway had error '{cast_resp['reason']}'"
                )

            return RemoteDocument(cast_resp)

    async def close(self) -> None:
        """
        Closes the Sync Gateway session
        """
        if not self.__session.closed:
            await self.__session.close()

    async def get_database_config(self, db_name: str) -> dict[str, Any]:
        """
        Gets the configuration for a specific database from the admin API.

        Args:
            db_name: The name of the database to get configuration for

        Returns:
            Dictionary containing the database configuration
        """
        _assert_not_null(db_name, "db_name")
        with self._tracer.start_as_current_span(
            "get_database_config", attributes={"cbl.database.name": db_name}
        ):
            return await self._send_request("GET", f"/{db_name}/_config")

    async def get_document_revision_public(
        self,
        db_name: str,
        doc_id: str,
        revision: str,
        auth: BasicAuth,
        scope: str = "_default",
        collection: str = "_default",
    ) -> dict[str, Any]:
        """
        Gets a specific revision of a document using the public API with user authentication.

        Args:
            db_name: The name of the database
            doc_id: The document ID
            revision: The specific revision to retrieve
            auth: User authentication credentials
            scope: The scope name (defaults to "_default")
            collection: The collection name (defaults to "_default")

        Returns:
            Dictionary containing the document at the specified revision

        Raises:
            CblSyncGatewayBadResponseError: If the document or revision is not found
        """
        _assert_not_null(db_name, "db_name")
        _assert_not_null(doc_id, "doc_id")
        _assert_not_null(revision, "revision")
        _assert_not_null(auth, "auth")

        path = (
            f"/{db_name}/{scope}.{collection}/{doc_id}"
            if scope != "_default" or collection != "_default"
            else f"/{db_name}/{doc_id}"
        )
        params = {"rev": revision}

        scheme = "https://" if self.secure else "http://"
        async with self._create_session(
            self.secure, scheme, self.hostname, 4984, auth
        ) as session:
            return await self._send_request("GET", path, params=params, session=session)

    async def _caddy_http_request(
        self,
        url: str,
        operation: str,
        timeout: int = 30,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes]:
        """
        Internal helper to make HTTP requests to Caddy server.

        :param url: Full Caddy URL to request
        :param operation: Description of operation (for error messages)
        :param timeout: Request timeout in seconds
        :param headers: Optional HTTP headers to include in the request
        :return: Tuple of (status_code, content as bytes)
        :raises FileNotFoundError: If resource returns 404
        :raises Exception: For other HTTP or network errors
        """
        try:
            async with ClientSession() as session:
                async with session.get(
                    url, timeout=ClientTimeout(total=timeout), headers=headers
                ) as response:
                    if response.status == 404:
                        raise FileNotFoundError(f"{operation} not found at {url}")
                    elif response.status != 200:
                        error_text = await response.text()
                        raise Exception(
                            f"{operation} failed: HTTP {response.status} - {error_text}"
                        )

                    # Return content as bytes
                    content = await response.read()
                    return response.status, content

        except ClientError as e:
            raise Exception(f"Network error during {operation}: {e}") from e

    async def fetch_log_file(
        self,
        log_type: str,
    ) -> str:
        """
        Fetches a log file from the remote Sync Gateway server via Caddy HTTP server

        :param log_type: Type of log file to fetch (e.g., 'debug', 'info', 'warn', 'error')
        :return: Content of the log file as a string
        :raises FileNotFoundError: If the log file doesn't exist
        :raises Exception: For other HTTP errors
        """
        log_filename = f"sg_{log_type}.log"
        caddy_url = f"http://{self.hostname}:20000/{log_filename}"

        with self._tracer.start_as_current_span(
            "fetch_log_file",
            attributes={
                "cbl.log.type": log_type,
                "cbl.log.filename": log_filename,
                "cbl.caddy.url": caddy_url,
            },
        ):
            _, content = await self._caddy_http_request(
                caddy_url, f"Fetch {log_filename}", timeout=30
            )
            log_content = content.decode("utf-8")
            cbl_info(f"Successfully fetched {log_filename} ({len(log_content)} bytes)")
            return log_content

    async def download_file_via_caddy(
        self,
        remote_filename: str,
        local_path: str,
    ) -> None:
        """
        Downloads a file from the remote server via Caddy HTTP server

        :param remote_filename: Name of the file on the remote server (e.g., 'sgcollectinfo-xxx-redacted.zip')
        :param local_path: Local path where the file should be saved
        :raises FileNotFoundError: If the file doesn't exist
        :raises Exception: For other HTTP errors
        """
        caddy_url = f"http://{self.hostname}:20000/{remote_filename}"

        with self._tracer.start_as_current_span(
            "download_file_via_caddy",
            attributes={
                "cbl.remote.filename": remote_filename,
                "cbl.local.path": local_path,
                "cbl.caddy.url": caddy_url,
            },
        ):
            _, content = await self._caddy_http_request(
                caddy_url, f"Download {remote_filename}", timeout=600
            )

            # Ensure local directory exists and write file
            local_file_path = Path(local_path)
            local_file_path.parent.mkdir(parents=True, exist_ok=True)
            local_file_path.write_bytes(content)

            cbl_info(
                f"Successfully downloaded {remote_filename} to {local_path} ({len(content)} bytes)"
            )

    async def list_files_via_caddy(
        self,
        pattern: str | None = None,
    ) -> list[str]:
        """
        Lists files available in the Caddy-served directory (requires 'browse' enabled in Caddyfile)

        :param pattern: Optional regex pattern to filter filenames (e.g., 'sgcollect_info.*redacted.zip')
        :return: List of filenames available in the directory
        :raises Exception: If directory browsing is not enabled or request fails
        """
        caddy_url = f"http://{self.hostname}:20000/"

        with self._tracer.start_as_current_span(
            "list_files_via_caddy",
            attributes={
                "cbl.caddy.url": caddy_url,
                "cbl.pattern": pattern or "all",
            },
        ):
            try:
                _, content = await self._caddy_http_request(
                    caddy_url,
                    "List directory",
                    timeout=30,
                    headers={"Accept": "application/json"},
                )
            except FileNotFoundError:
                raise Exception(
                    "Directory browsing endpoint not found. "
                    "Ensure Caddy is configured with 'file_server browse'"
                )

            # Parse JSON response from Caddy
            try:
                dir_listing = loads(content.decode("utf-8"))
            except ValueError as e:
                raise Exception(f"Failed to parse Caddy JSON response: {e}")

            # Extract filenames from the JSON array
            files = [
                entry["name"]
                for entry in dir_listing
                if isinstance(entry, dict)
                and "name" in entry
                and not entry.get("is_dir", False)
            ]

            # Filter by pattern if provided
            if pattern:
                regex = re.compile(pattern)
                files = [f for f in files if regex.search(f)]

            cbl_info(
                f"Found {len(files)} files via Caddy browse (JSON)"
                + (f" (filtered by '{pattern}')" if pattern else "")
            )
            return files

    async def start_sgcollect(
        self,
        redact_level: str | None = None,
        redact_salt: str | None = None,
        output_dir: str | None = None,
    ) -> dict:
        """
        Starts SGCollect using the REST API endpoint

        :param redact_level: Redaction level ('none', 'partial', 'full')
        :param redact_salt: Custom salt for redaction hashing
        :param output_dir: Output directory on the remote server
        :return: Response dict with status
        """
        with self._tracer.start_as_current_span(
            "start_sgcollect",
            attributes={
                "redact.level": redact_level or "none",
            },
        ):
            body: dict[str, Any] = {"upload": False}
            if redact_level is not None:
                body["redact_level"] = redact_level
            if redact_salt is not None:
                body["redact_salt"] = redact_salt
            if output_dir is not None:
                body["output_dir"] = output_dir

            resp = await self._send_request(
                "post",
                "/_sgcollect_info",
                JSONDictionary(body),
            )
            assert isinstance(resp, dict)
            return cast(dict, resp)

    async def get_sgcollect_status(self) -> dict:
        """
        Gets the current status of SGCollect operation

        :return: Response dict with status ('stopped' or 'running')
        """
        with self._tracer.start_as_current_span("get_sgcollect_status"):
            resp = await self._send_request("get", "/_sgcollect_info")
            assert isinstance(resp, dict)
            return cast(dict, resp)

    async def wait_for_sgcollect_to_complete(
        self, max_attempts: int = 60, wait_time: int = 2
    ) -> None:
        """
        Waits for SGCollect to complete, polling until the status is 'stopped' or 'completed'.
        Polls 60 times, waiting 2 seconds between each poll.

        :param max_attempts: Maximum number of attempts to wait for SGCollect to complete
        :param wait_time: Time to wait between attempts
        """
        for _ in range(max_attempts):
            status_resp = await self.get_sgcollect_status()
            if status_resp.get("status") in ["stopped", "completed"]:
                return
            await asyncio.sleep(wait_time)

        raise Exception(
            f"SGCollect did not complete after {max_attempts * wait_time} seconds.\n"
            f"Status: {status_resp.get('status')}.\n"
            f"Error: {status_resp.get('error')}"
        )


class SyncGateway(_SyncGatewayBase):
    """
    A class for interacting with a given Sync Gateway instance.
    Provides full admin API access including user management, role management,
    and all document/database operations.

    This class inherits common document/database operations from _SyncGatewayBase
    and adds admin-only operations directly in this class.
    """

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        port: int = 4985,
        secure: bool = False,
        public_port: int = 4984,
    ):
        """
        Initialize a SyncGateway admin client.

        :param url: The hostname/URL of the Sync Gateway instance
        :param username: Admin username
        :param password: Admin password
        :param port: Admin API port (default 4985)
        :param secure: Whether to use TLS/HTTPS
        :param public_port: Public API port (default 4984)
        """
        super().__init__(url, username, password, port, secure)
        self.__public_port = public_port

    def create_collection_access_dict(self, input: dict[str, list[str]]) -> dict:
        """
        Creates a collection access dictionary in the format that Sync Gateway expects,
        given an input dictionary keyed by collection with a list of channels

        :param input: The simplified input dictionary of collection -> channels
        """

        ret_val = {}
        for c in input:
            if not isinstance(c, str):
                raise ValueError(
                    "Non-string key found in input dictionary to create_collection_access_dict"
                )

            channels = input[c]
            if not isinstance(channels, list):
                raise ValueError(
                    f"Non-list found for value of collection {c} in create_collection_access_dict"
                )

            if "." not in c:
                raise ValueError(
                    f"Input collection '{c}' in create_collection_access_dict needs to be fully qualified"
                )

            spec = c.split(".")
            if len(spec) != 2:
                raise ValueError(
                    f"Input collection '{c}' has too many dots in create_collection_access_dict"
                )

            if spec[0] not in ret_val:
                scope_dict: dict[str, dict] = {}
                ret_val[spec[0]] = scope_dict
            else:
                scope_dict = ret_val[spec[0]]

            scope_dict[spec[1]] = {"admin_channels": input[c]}

        return ret_val

    async def add_user(
        self,
        db_name: str,
        name: str,
        password: str | None = None,
        collection_access: dict | None = None,
        admin_roles: list[str] | None = None,
    ) -> None:
        """
        Adds or updates the specified user to a Sync Gateway database with the specified channel access

        :param db_name: The name of the Database to add the user to
        :param name: The username to add
        :param password: The password for the user that will be added
        :param collection_access: The collections that the user will have access to.  This needs to
            be formatted in the way Sync Gateway expects it, so if you are unsure use
            :func:`drop_bucket()<cbltest.api.syncgateway.SyncGateway.create_collection_access_dict>`
        :param admin_roles: The admin roles
        """
        with self._tracer.start_as_current_span(
            "add_user", attributes={"cbl.user.name": name}
        ):
            body: dict[str, Any] = {
                "name": name,
            }

            if password is not None:
                body["password"] = password

            if collection_access is not None:
                body["collection_access"] = collection_access

            if admin_roles is not None:
                body["admin_roles"] = admin_roles

            await self._send_request(
                "put", f"/{db_name}/_user/{name}", JSONDictionary(body)
            )

    async def delete_user(self, db_name: str, name: str) -> None:
        """
        Deletes a user from a Sync Gateway database

        :param db_name: The name of the Database
        :param name: The username to delete
        """
        with self._tracer.start_as_current_span(
            "delete_user", attributes={"cbl.user.name": name}
        ):
            try:
                await self._send_request("delete", f"/{db_name}/_user/{name}")
            except CblSyncGatewayBadResponseError as e:
                if e.code == 404:
                    # User doesn't exist, that's fine
                    pass
                else:
                    raise

    async def add_role(self, db_name: str, role: str, collection_access: dict) -> None:
        """
        Adds the specified role to a Sync Gateway database with the specified collection access

        :param db_name: The name of the Database to add the user to
        :param role: The role to add
        :param collection_access: The collections to which role members will have access.
            This needs to be formatted in the way Sync Gateway expects it:
            "<scope1>": {
                "<collection1>: {"admin_channels" : ["<channel1>", ... ] }
                .
                .
                .
            }
            "<scope2>": {
                ...
            }
            .
            .
            .
        """
        with self._tracer.start_as_current_span(
            "add_role", attributes={"cbl.role.name": role}
        ):
            body = {"collection_access": collection_access}

            await self._send_request(
                "put", f"/{db_name}/_role/{role}", JSONDictionary(body)
            )

    async def restart_with_config(self, config_name: str = "bootstrap") -> None:
        """
        Restart Sync Gateway with a specific bootstrap configuration.

        This method calls the shell2http management endpoint to restart SGW
        with the specified config file. The config file should exist at
        /home/ec2-user/config/{config_name}.json on the SGW host.

        :param config_name: Name of the config file (without .json extension).
                           Default is "bootstrap" for the standard config.
                           Use "bootstrap-alternate" for alternate address testing.
        :raises Exception: If the restart fails
        """
        with self._tracer.start_as_current_span(
            "restart_with_config",
            attributes={
                "cbl.config.name": config_name,
            },
        ):
            shell2http_url = (
                f"http://{self.hostname}:20001/restart-sgw?config={config_name}"
            )
            async with ClientSession() as session:
                async with session.get(
                    shell2http_url, timeout=ClientTimeout(total=120)
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise Exception(
                            f"Failed to restart SGW: {resp.status} - {body}"
                        )
                    # Wait a bit for SGW to fully initialize
                    await asyncio.sleep(5)

    async def stop(self) -> None:
        """
        Stop the Sync Gateway process.

        This method calls the shell2http management endpoint to stop SGW.

        :raises Exception: If the stop fails
        """
        with self._tracer.start_as_current_span("stop_sgw"):
            shell2http_url = f"http://{self.hostname}:20001/stop-sgw"
            async with ClientSession() as session:
                async with session.get(
                    shell2http_url, timeout=ClientTimeout(total=60)
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise Exception(f"Failed to stop SGW: {resp.status} - {body}")

    async def start(self, config_name: str = "bootstrap") -> None:
        """
        Start the Sync Gateway process.

        This method calls the shell2http management endpoint to start SGW.

        :param config_name: Name of the config file (without .json extension).
        :raises Exception: If the start fails
        """
        # Check if SGW is already running by probing the public endpoint (4984)
        try:
            # Use a short timeout to distinguish "not running" from "slow"
            scheme = "https://" if self.secure else "http://"
            async with self._create_session(
                self.secure, scheme, self.hostname, 4984, None
            ) as session:
                async with session.get("/", timeout=ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        cbl_info("SGW is already running, skipping start")
                        return
        except (ClientConnectorError, asyncio.TimeoutError):
            # SGW is not reachable or slow, proceed with start
            pass

        # Proceed with shell2http start call...
        with self._tracer.start_as_current_span(
            "start_sgw",
            attributes={"cbl.config.name": config_name},
        ):
            shell2http_url = (
                f"http://{self.hostname}:20001/start-sgw?config={config_name}"
            )
            async with ClientSession() as session:
                async with session.get(
                    shell2http_url, timeout=ClientTimeout(total=120)
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise Exception(f"Failed to start SGW: {resp.status} - {body}")
                    # Wait a bit for SGW to fully initialize
                    await asyncio.sleep(5)

    async def wait_for_db_gone_clusterwide(
        self,
        sync_gateways: list["SyncGateway"],
        db_name: str,
        max_retries: int = 30,
        retry_delay: int = 2,
    ) -> None:
        """
        Wait until the SGW database is gone from the cluster.

        :param db_name: Database name to poll.
        :param max_retries: Maximum number of retries.
        :param retry_delay: Seconds between retries.
        """
        for _ in range(max_retries):
            gone_everywhere = True
            for sg in sync_gateways:
                dbs = await sg.get_all_database_names()
                if db_name in dbs:
                    gone_everywhere = False
                    break
            if gone_everywhere:
                return
            await asyncio.sleep(retry_delay)
        raise TimeoutError(f"Database {db_name} still exists on some SG nodes")

    async def wait_for_db_up(
        self,
        db_name: str,
        max_retries: int = 20,
        retry_delay: int = 3,
        settle_online: int = 10,
    ) -> None:
        """
        Wait until the SGW node is online.

        :param db_name: Database name to poll.
        :param max_retries: Number of polls before timing out.
        :param retry_delay: Seconds between polls.
        :param settle_online: Extra seconds to wait after seeing Online.
        """
        for _ in range(max_retries):
            try:
                sg_status = await self.get_database_status(db_name)
            except ClientConnectorError:
                sg_status = None
            if sg_status is not None:
                break
            await asyncio.sleep(retry_delay)
        else:
            raise TimeoutError(
                f"Node {db_name} is not online within {max_retries * retry_delay} seconds"
            )

        # Wait for the node to settle down after coming online
        await asyncio.sleep(settle_online)

    async def create_user_client(
        self,
        db_name: str,
        username: str,
        password: str,
        channels: list[str],
    ) -> "SyncGatewayUserClient":
        """
        Helper method to create a user with channel access and return a user-specific SG client.

        This is a convenience method for tests that need to verify user-level access control.

        :param db_name: The database name
        :param username: The username to create
        :param password: The password for the user
        :param channels: List of channels the user should have access to
        :return: A SyncGatewayUserClient instance authenticated as the user (uses public port)
        """
        # Clean up user if exists from previous run
        await self.delete_user(db_name, username)
        await self.add_user(
            db_name,
            username,
            password=password,
            collection_access={"_default": {"_default": {"admin_channels": channels}}},
        )

        # Return user-specific SG client for public API access
        return SyncGatewayUserClient(
            self.hostname,
            username,
            password,
            port=self.__public_port,
            secure=self.secure,
        )

    async def start_isgr(self, db_name: str, payload: ISGRPayload) -> str:
        """
        Starts an Inter-Sync Gateway Replication (ISGR) from this SG to a remote SG.

        :param db_name: The local database name
        :param payload: The ISGR configuration payload
        :return: The replication ID
        """
        with self._tracer.start_as_current_span(
            "start_isgr",
            attributes={
                "cbl.database.name": db_name,
                "cbl.replication.id": payload.replication_id,
                "cbl.replication.direction": payload.direction,
            },
        ):
            await self._send_request(
                "put", f"/{db_name}/_replication/{payload.replication_id}", payload
            )
            return payload.replication_id

    async def get_isgr_status(self, db_name: str, replication_id: str) -> dict:
        """
        Gets the status of an Inter-Sync Gateway Replication.

        :param db_name: The local database name
        :param replication_id: The replication identifier
        :return: A dictionary containing the replication status
        """
        with self._tracer.start_as_current_span(
            "get_isgr_status",
            attributes={
                "cbl.database.name": db_name,
                "cbl.replication.id": replication_id,
            },
        ):
            resp = await self._send_request(
                "get", f"/{db_name}/_replicationStatus/{replication_id}"
            )
            assert isinstance(resp, dict)
            return cast(dict, resp)

    async def stop_isgr(
        self, db_name: str, replication_id: str, continuous: bool = False
    ) -> None:
        """
        Stops and removes an Inter-Sync Gateway Replication.

        :param db_name: The local database name
        :param replication_id: The replication identifier to stop
        :param continuous: Replication type
        """
        with self._tracer.start_as_current_span(
            "stop_isgr",
            attributes={
                "cbl.database.name": db_name,
                "cbl.replication.id": replication_id,
            },
        ):
            try:
                await self._send_request(
                    "delete", f"/{db_name}/_replication/{replication_id}"
                )
            except CblSyncGatewayBadResponseError as e:
                if e.code == 404 and continuous:
                    cbl_error(f"ISGR {replication_id} is continuous but does not exist")
                    raise
            return None

    async def wait_for_isgr_status(
        self,
        db_name: str,
        replication_id: str,
        target_status: str,
        timeout: int = 60,
        poll_interval: int = 2,
    ) -> dict:
        """
        Waits for an ISGR to reach a specific status.

        :param db_name: The local database name
        :param replication_id: The replication identifier
        :param target_status: The status to wait for (default "stopped")
        :param timeout: Maximum seconds to wait (default 180)
        :param poll_interval: Seconds between status checks (default 2)
        :return: The final replication status
        :raises TimeoutError: If the target status is not reached within timeout
        """
        with self._tracer.start_as_current_span(
            "wait_for_isgr_status",
            attributes={
                "cbl.database.name": db_name,
                "cbl.replication.id": replication_id,
                "cbl.target.status": target_status,
            },
        ):
            for _ in range(timeout // poll_interval):
                status = await self.get_isgr_status(db_name, replication_id)
                current_status = status.get("status", "")
                if current_status == target_status:
                    return status
                if current_status == "error":
                    raise Exception(
                        f"ISGR {replication_id} entered error state: {status.get('error_message', 'unknown error')}"
                    )
                await asyncio.sleep(poll_interval)

            raise TimeoutError(
                f"ISGR {replication_id} did not reach status '{target_status}' within {timeout} seconds"
            )


class SyncGatewayUserClient(_SyncGatewayBase):
    """
    A Sync Gateway client that uses the public API (port 4984) for user-level access.

    This class inherits common operations from _SyncGatewayBase and does NOT
    include admin methods (user management, roles, etc.).
    """

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        port: int = 4984,
        secure: bool = False,
    ):
        """
        Initialize a SyncGatewayUserClient for public API access.

        :param url: The hostname/URL of the Sync Gateway instance
        :param username: Username for authentication
        :param password: Password for authentication
        :param port: Public API port (default 4984)
        :param secure: Whether to use TLS/HTTPS
        """
        super().__init__(url, username, password, port, secure)
