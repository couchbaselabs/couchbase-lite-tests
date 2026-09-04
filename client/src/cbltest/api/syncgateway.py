import asyncio
import re
import ssl
import warnings
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Collection, Mapping
from contextlib import asynccontextmanager
from enum import Enum
from json import dumps, loads
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlencode, urljoin

import aiofiles
import packaging.version
import requests
import tenacity
from aiohttp import ClientSession, ClientTimeout, TCPConnector, encode_basic_auth
from aiohttp.client_exceptions import ClientConnectorError
from opentelemetry.trace import get_tracer
from pydantic import BaseModel, Field, TypeAdapter

from cbltest.api import caddy
from cbltest.api.error import CblSyncGatewayBadResponseError, CblTestError
from cbltest.api.jsonserializable import JSONDictionary, JSONSerializable
from cbltest.api.sync_gateway_sequence import parse_sequence_id
from cbltest.assertions import _assert_not_null
from cbltest.httplog import get_next_writer
from cbltest.logging import cbl_error, cbl_info, cbl_trace, cbl_warning
from cbltest.utils import SHELL2HTTP_PORT, assert_not_null, async_retry_assert, is_sidecar_reachable
from cbltest.version import VERSION

# This is copied from environment/aws/sgw_setup/cert/ca_cert.pem
# So if that file ever changes, change this too.
_SGW_CA_CERT: str = """-----BEGIN CERTIFICATE-----
MIIFaTCCA1GgAwIBAgIUNSzLLJnLm8TELxXs4Hy5br85H/8wDQYJKoZIhvcNAQEL
BQAwPDEZMBcGA1UEAwwQSW50ZXJuYWwgVGVzdCBDQTESMBAGA1UECgwJQ291Y2hi
YXNlMQswCQYDVQQGEwJVUzAeFw0yNjA4MjgxMzIyMDNaFw0zNjA4MjUxMzIyMDNa
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
WOIyuE3aJ5KVtG8hjlgKARV7eEqtxHjIl41QtsxalwIDAQABo2MwYTAPBgNVHRMB
Af8EBTADAQH/MA4GA1UdDwEB/wQEAwIBhjAdBgNVHQ4EFgQUs2WdMu1wh9pJ5dPN
80yN1NPAkSswHwYDVR0jBBgwFoAUs2WdMu1wh9pJ5dPN80yN1NPAkSswDQYJKoZI
hvcNAQELBQADggIBAIew2fyPk44A6xp2NoqIcpqVXPFkeZlAM4NTy3MZr3S0aAx4
GUDVY54wJAg5iydQWu6UPrvFpKU9qTiDh79ULPfC/vUaXX0o+46uWS3hoSq5NdnE
q2WHhLSMQwgLy+PQjqPFCs+1OTDERCz3s5G77IiBzqhFB3OqO3YaR0FUErtpfjJa
oe+zIsdMj1hLt2ceROnIrPzBiHqw0pnvHmHdSH5O5YY3gkswR63TEeSR2Ihg3x6w
DnRGxzxWwHaPwMt51QlWbVGtx6OnvLdruRwsSUKZ8DyDdO9WTaBM3UWvslBBaLgi
VRuM5XD8MQPf4PhfyrUFFO6Md/PHrhS+QEUsSxWVd++xw6kOpX4arNd9jY6byWlD
MXXiOzbKkyd6RTvPhcrq9RYPd7wXJ721U3zZGTFkC+xmOD4Ht1oyg3GIowZszBsW
0IPAXyY1wUQ+HpOm2nSjItc6DXfBUK44i12hLqwaGUZmeclbNMZgcjiK/QlvBcrf
h7vaHwdE3b6S8WxeGR5HPOZeUVwrRHmTh8lkJPUQlfKDu+z/WP+Q4+engTSpRdRn
82sfeIkpICuAf40kBvF+JzrY9xNr7KGXIekcsFBFdvxXwefGvxzoI98SpmKxCNpr
fvJMZ8kpMTvrHDXO1G4EHiI48bzvQIJCKD6e2ZElimn25ZUJXSKL5ICsRij4
-----END CERTIFICATE-----
"""


class ScopeConfig(BaseModel):
    collections: dict[str, Any] | list[str] | None = None


class IndexConfig(BaseModel):
    num_replicas: int | None = None


class JWK(BaseModel):
    kty: str | None = None
    n: str | None = None
    e: str | None = None
    alg: str | None = None
    use: str | None = None
    kid: str | None = None


with warnings.catch_warnings():
    # "register" is the field name Sync Gateway's wire format requires; it
    # happens to shadow abc.ABCMeta.register (pydantic's metaclass subclasses
    # ABCMeta), which pydantic warns about on class definition. Harmless here.
    warnings.filterwarnings(
        "ignore",
        message='Field name "register" in "LocalJWT" shadows an attribute',
        category=UserWarning,
    )

    class LocalJWT(BaseModel):
        issuer: str | None = None
        client_id: str | None = None
        register: bool | None = None
        algorithms: list[str] | None = None
        keys: list[JWK] | None = None


class DeltaSyncConfig(BaseModel):
    enabled: bool | None = None
    rev_max_age_seconds: int | None = None


class UnsupportedSettings(BaseModel):
    rosmar_bucket_management: bool | None = None
    sgr_tls_skip_verify: bool | None = None


class DatabaseConfig(BaseModel):
    """
    A Pydantic model containing configuration options for a Sync Gateway database endpoint
    (PUT /{db}/), based on the OpenAPI Database schema spec:
    https://github.com/couchbase/sync_gateway/blob/main/docs/api/components/schemas.yaml
    """

    allow_conflicts: bool | None = None
    allow_empty_password: bool | None = None
    bucket: str | None = Field(default=None)
    bucket_op_timeout_ms: int | None = None
    cacertpath: str | None = None
    cache: dict[str, Any] | None = None
    certpath: str | None = None
    changes_request_plus: bool | None = None
    client_partition_window_secs: int | None = None
    compact_interval_days: float | None = None
    cors: dict[str, Any] | None = None
    delta_sync: DeltaSyncConfig | None = None
    disable_password_auth: bool | None = None
    disable_public_all_docs: bool | None = None
    enable_shared_bucket_access: bool | None = None
    event_handlers: dict[str, Any] | None = None
    feed_type: str | None = None
    guest: dict[str, Any] | None = None
    import_backup_old_rev: bool | None = None
    import_docs: bool | str | None = None
    import_filter: str | None = None
    import_partitions: int | None = None
    index: IndexConfig | None = None
    javascript_timeout_secs: int | None = None
    keypath: str | None = None
    kv_tls_port: int | None = None
    local_doc_expiry_secs: int | None = None
    local_jwt: dict[str, LocalJWT] | None = None
    logging: dict[str, Any] | None = None
    max_concurrent_query_ops: int | None = None
    name: str | None = None
    num_index_replicas: int | None = None
    offline: bool | None = None
    oidc: dict[str, Any] | None = None
    old_rev_expiry_seconds: int | None = None
    password: str | None = None
    pool: str | None = None
    query_pagination_limit: int | None = None
    replications: dict[str, Any] | None = None
    rev_cache_size: int | None = None
    revs_limit: int | None = None
    roles: dict[str, Any] | None = None
    scopes: dict[str, ScopeConfig] | None = None
    send_www_authenticate_header: bool | None = None
    serve_insecure_attachment_types: bool | None = None
    server: str | None = None
    session_cookie_http_only: bool | None = None
    session_cookie_name: str | None = None
    session_cookie_secure: bool | None = None
    sgreplicate_enabled: bool | None = None
    sgreplicate_websocket_heartbeat_secs: int | None = None
    slow_query_warning_threshold: int | None = None
    store_legacy_revtree_data: bool | None = None
    suspendable: bool | None = None
    sync: str | None = None
    unsupported: UnsupportedSettings | None = None
    use_views: bool | None = None
    user_xattr_key: str | None = None
    username: str | None = None
    users: dict[str, Any] | None = None
    view_query_timeout_secs: int | None = None

    def to_json(self) -> Any:
        return self.model_dump(mode="json", exclude_none=True)

    def serialize(self) -> str:
        return dumps(self.to_json(), indent=2)


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
    ) -> None:
        """
        Creates an ISGR configuration payload.

        :param replication_id: A unique identifier for this replication
        :param remote_url: The URL of the remote Sync Gateway, without a database -- use the remote
            client's `http_url` rather than building it by hand
        :param remote_db: The database name on the remote Sync Gateway
        :param direction: Replication direction - "push", "pull", or "pushAndPull"
        :param continuous: Whether the replication should be continuous (default False)
        :param remote_username: Username for authenticating with the remote SG
        :param remote_password: Password for authenticating with the remote SG
        :param collections_local: List of local collections in "scope.collection" format
        :param collections_remote: List of remote collections to map to (parallel array with collections_local)
        """
        if direction not in ["push", "pull", "pushAndPull"]:
            raise ValueError(f"Invalid direction: {direction}. Must be 'push', 'pull', or 'pushAndPull'")
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
        if self.__collections_local is not None or self.__collections_remote is not None:
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

    @property
    def doc(self) -> dict | None:
        """Gets the document body (only available if include_docs=True was used)"""
        return self.__doc

    def __init__(
        self,
        key: str,
        id: str,
        revid: str | None,
        cv: str | None,
        doc: dict | None = None,
    ) -> None:
        self.__key = key
        self.__id = id
        self.__revid = revid
        self.__cv = cv
        self.__doc = doc


class AllDocumentsResponse:
    """
    A class representing an all_docs response from Sync Gateway
    """

    @property
    def rows(self) -> list[AllDocumentsResponseRow]:
        """Gets the entries of the response"""
        return self.__rows

    @property
    def revmap(self) -> dict:
        return self.__revmap

    def __len__(self) -> int:
        return self.__len

    def __init__(self, input: dict) -> None:
        self.__len = input["total_rows"]
        self.__rows: list[AllDocumentsResponseRow] = []
        self.__revmap = {}
        for row in cast(list[dict], input["rows"]):
            rev = cast(dict, row["value"])
            doc = cast(dict, row["doc"]) if "doc" in row else None
            self.__rows.append(
                AllDocumentsResponseRow(
                    row["key"],
                    row["id"],
                    cast(str, rev["rev"]) if "rev" in rev else None,
                    cast(str, rev["cv"]) if "cv" in rev else None,
                    doc,
                )
            )
            self.__revmap[row["id"]] = cast(str, rev["rev"]) if "rev" in rev else None


class ChangesResponseEntry:
    """
    A class representing a single entry in a changes feed response from Sync Gateway
    """

    @property
    def seq(self) -> int | str:
        """
        Gets the sequence, exactly as Sync Gateway reported it.  Simple sequences arrive as numbers,
        but compound ones (backfill, or a change triggered by a channel grant) arrive as strings such
        as "2:5", so this is not always an int.
        """
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
        seq = entry.get("seq")
        assert isinstance(seq, int | str), f"Unusable sequence in changes feed entry: {seq!r}"
        self.__seq = seq
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
        """
        Gets the sequence this feed ended on, i.e. the one to resume it from.  This keeps the
        form Sync Gateway sent, since a compound sequence has to go back out as `since` intact.
        """
        return self.__last_seq

    def __init__(self, input: dict) -> None:
        self.__results: list[ChangesResponseEntry] = []
        for entry in cast(list[dict], input.get("results", [])):
            self.__results.append(ChangesResponseEntry(entry))

        last_seq = input.get("last_seq")
        assert isinstance(last_seq, str), f"Unusable last_seq in changes feed response: {last_seq!r}"
        self.__last_seq = last_seq


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

    def __init__(self, id: str, revid: str | None, body: dict) -> None:
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

    @property
    def seq(self) -> int:
        """
        Gets the sequence Sync Gateway assigned to this revision, as read back from the changes
        feed.  A compound sequence is reduced to the revision's own sequence by
        :func:`parse_sequence_id()<cbltest.api.sync_gateway_sequence.parse_sequence_id>`.

        :raises CblTestError: if the sequence was never read back from the changes feed (see the
                              `wait_for_caching_feed` argument of :func:`SyncGateway.update_document`)
        """
        if self.__seq is None:
            raise CblTestError(
                f"No sequence recorded for document {self.__id}; it was not read back from the changes feed. "
                "Only SyncGateway.update_document(wait_for_caching_feed=True) populates a sequence."
            )

        return self.__seq

    def __init__(self, body: dict, seq: int | None = None) -> None:
        if "error" in body:
            raise ValueError("Trying to create remote document from error response")

        self.__seq = seq
        self.__body = body.copy()
        self.__id = cast(str, body["_id"])
        self.__rev = cast(str, body["_rev"]) if "_rev" in body else None
        self.__cv = cast(str, body["_cv"]) if "_cv" in body else None
        del self.__body["_id"]
        if self.__rev is not None:
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

    def __init__(self, input: str) -> None:
        self.__raw = input
        parsed = self.parse(input)
        self.__version = parsed[0]
        self.__build_number = parsed[1]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.__raw})"


class SyncGatewayVersion(CouchbaseVersion):
    """
    A class for parsing Sync Gateway Version
    """

    def parse(self, input: str) -> tuple[str, int]:
        # Version parsing can be different for dev builds and release builds. In a dev build, it is possible to miss a build number.
        #
        # Example input:
        #   Couchbase Sync Gateway/4.0.0(350;def456)
        #   4.0.0(350;def456)
        #   4.0.0

        # extract everything between an optional / and an option ( to represent a major.minor.patch build number
        m = re.search(r"(?:^|/)([\d\.]+)(?=\s*\(|$)", input)
        # (?:^|/)(?P<v>[\d\.]+)(?:\s*\(|$)", input)
        if m:
            version = m.group(1).strip()
        else:
            cbl_warning(f"Could not extract version from SGW version string: '{input}'")
            version = "unknown"

        # extract everything between ( and a ; character to guess at a build number
        m = re.search(r"(?<=\()([^;)]+)", input)
        if m:
            try:
                build = int(m.group())
            except ValueError as e:
                cbl_warning(f"Could not parse build number {m.group()} from SGW version string: '{input}': {e}")
                build = 0
        else:
            cbl_warning(f"Could not parse build number from SGW version string: '{input}'")
            build = 0
        return version, build


class SyncGatewayStatusVendor(BaseModel):
    """
    Output of vendor field of /_status endpoint of Sync Gateway
    """

    name: str
    version: str


class SyncGatewayStatusResponse(BaseModel):
    """
    Output of GET /_status endpoint of Sync Gateway
    """

    version: str  # this version does not always include the full build number if it is a dev build
    vendor: SyncGatewayStatusVendor


class DatabaseState(str, Enum):
    """
    The state of a Sync Gateway database.
    """

    ONLINE = "Online"
    OFFLINE = "Offline"
    STARTING = "Starting"
    STOPPING = "Stopping"
    RESYNCING = "Resyncing"


class DatabaseStatusResponse(BaseModel):
    """
    Output of GET /{db}/ endpoint of Sync Gateway
    """

    compact_running: bool = False
    db_name: str
    init_in_progress: bool = False
    instance_start_time: int = 0
    require_resync: bool = False
    server_uuid: str = ""
    state: DatabaseState
    update_seq: int = 0


class AllDatabasesVerboseEntry(BaseModel):
    """
    A single database entry from the GET /_all_dbs?verbose=true response
    """

    class DatabaseError(BaseModel):
        """An error that occurred during database startup"""

        error_code: int
        error_message: str

    bucket: str
    database_error: DatabaseError | None = None
    db_name: str
    init_in_progress: bool | None = None
    require_resync: bool | None = None
    state: DatabaseState


_all_databases_verbose_adapter = TypeAdapter(list[AllDatabasesVerboseEntry])


class SGCollectRedactLevel(str, Enum):
    """Redaction level accepted by Sync Gateway's /_sgcollect_info endpoint"""

    NONE = "none"
    PARTIAL = "partial"
    FULL = "full"


class SGCollectOptions(BaseModel):
    """Body for Sync Gateway's POST /_sgcollect_info. Unset fields are omitted
    so Sync Gateway falls back to its own defaults."""

    upload: bool = False
    redact_level: SGCollectRedactLevel | None = None
    redact_salt: str | None = None
    output_dir: str | None = None


def _config_version(headers: Mapping[str, str]) -> str | None:
    """
    Read a database config version out of a response's ``Etag`` header.

    Sync Gateway quotes the value per RFC 7232, so the quotes are stripped to give the
    bare version.  Returns None when the header is absent (older Sync Gateway builds do
    not set it on every config endpoint).
    """
    etag = headers.get("Etag")
    return etag.strip('"') if etag is not None else None


class _SyncGatewayBase:
    """
    Base class for Sync Gateway clients containing common document and database operations.
    This class should not be instantiated directly - use SyncGateway or SyncGatewayUserClient instead.
    """

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        port: int,
        secure: bool = False,
        public_port: int | None = None,
    ) -> None:
        """
        :param port: The port this client sends its own requests to.
        :param public_port: The instance's public REST/replication port. Defaults to `port`, which is
            correct for a client that already talks to the public API; an admin client must pass it,
            since its own `port` is the admin one.
        """
        scheme = "https://" if secure else "http://"
        ws_scheme = "wss://" if secure else "ws://"
        self.__http_url = f"{scheme}{url}:{port}"
        self.__public_port: int = public_port if public_port is not None else port
        self.__replication_url = f"{ws_scheme}{url}:{self.__public_port}"
        self._tracer = get_tracer(__name__, VERSION)
        self._caddy = caddy.Caddy(url)
        self.__secure: bool = secure
        self.__hostname: str = url
        self.__port: int = port
        self.__session: ClientSession = self._create_session(
            secure,
            scheme,
            url,
            port,
            encode_basic_auth(username, password, "ascii"),
        )

    def __str__(self) -> str:
        return f"{type(self).__name__} {self.hostname}:{self.port}"

    @property
    def hostname(self) -> str:
        """Gets the hostname of the Sync Gateway instance"""
        return self.__hostname

    @property
    def port(self) -> int:
        """Gets the HTTP API port of the Sync Gateway instance"""
        return self.__port

    @property
    def public_port(self) -> int:
        """Gets the public REST/replication port of the Sync Gateway instance"""
        return self.__public_port

    @property
    def secure(self) -> bool:
        """Gets whether the Sync Gateway instance uses TLS"""
        return self.__secure

    @property
    def scheme(self) -> str:
        """Gets the URL scheme to use when connecting to the Sync Gateway instance (http or https)"""
        return "https://" if self.secure else "http://"

    @property
    def http_url(self) -> str:
        """Gets the REST API base URL this client sends its own requests to (i.e. follows `port`)"""
        return self.__http_url

    @property
    def public_url(self) -> str:
        """Gets the REST API base URL of the instance's public port, whichever port this client uses"""
        return f"{self.scheme}{self.hostname}:{self.__public_port}"

    def _create_session(self, secure: bool, scheme: str, url: str, port: int, auth_header: str | None) -> ClientSession:
        """Create a session, where `auth_header` is an `Authorization` header value
        from `aiohttp.encode_basic_auth`, or None for an anonymous session."""
        headers = {"Authorization": auth_header} if auth_header is not None else None
        if secure:
            ssl_context = ssl.create_default_context(cadata=_SGW_CA_CERT)
            # Disable hostname check so that the pre-generated SG can be used on any machines.
            ssl_context.check_hostname = False
            return ClientSession(
                f"{scheme}{url}:{port}",
                headers=headers,
                connector=TCPConnector(ssl=ssl_context),
            )
        else:
            return ClientSession(f"{scheme}{url}:{port}", headers=headers)

    async def _send_request(
        self,
        method: str,
        path: str,
        payload: JSONSerializable | DatabaseConfig | None = None,
        params: dict[str, str] | None = None,
    ) -> Any:
        body, _ = await self._send_request_with_headers(method, path, payload, params)
        return body

    async def _send_request_with_headers(
        self,
        method: str,
        path: str,
        payload: JSONSerializable | DatabaseConfig | None = None,
        params: dict[str, str] | None = None,
    ) -> tuple[Any, Mapping[str, str]]:
        """
        As :func:`_send_request`, but also returns the response headers for the callers
        that need them (e.g. to read the ``Etag`` of a database config).
        """
        with self._tracer.start_as_current_span("send_request", attributes={"http.method": method, "http.path": path}):
            headers = {"Content-Type": "application/json"} if payload is not None else None
            data = "" if payload is None else payload.serialize()
            # Log the query string too, otherwise the log cannot show which variant of an
            # endpoint was called (e.g. whether a _changes call was request_plus or filtered)
            logged_path = f"{path}?{urlencode(params)}" if params else path
            writer = get_next_writer()
            writer.write_begin(f"Sync Gateway [{self.__http_url}] -> {method.upper()} {logged_path}", data)
            resp = await self.__session.request(method, path, data=data, headers=headers, params=params)
            if resp.content_type.startswith("application/json"):
                ret_val = await resp.json()
                data = dumps(ret_val, indent=2)
            else:
                data = await resp.text()
                ret_val = data
            writer.write_end(
                f"Sync Gateway [{self.__http_url}] <- {method.upper()} {logged_path} {resp.status}",
                data,
            )
            if not resp.ok:
                raise CblSyncGatewayBadResponseError(
                    resp.status,
                    f"{method} {logged_path} returned {resp.status}: {data}",
                    body=data,
                )

            return ret_val, resp.headers

    async def supports_version_vectors(self) -> bool:
        """Returns whether the Sync Gateway instance supports version vectors (i.e. is 4.0 or later)"""
        version = await self.get_version()
        return packaging.version.parse(version.version) >= packaging.version.parse("4.0")

    async def get_version(self) -> SyncGatewayVersion:
        """Return version of Sync Gateway"""
        resp = await self._send_request("get", "/_status")
        assert isinstance(resp, dict)
        model = SyncGatewayStatusResponse.model_validate(resp)

        # In the case of a dev build, it is not possible to determine a build number, but there is a
        # major.minor version.
        # There only backward compatible difference is if "vendor.version" substring is contained in "version""

        # In a production build, the output:
        #
        # "vendor": {
        #    "version": "4.0"
        # },
        # "version": "Couchbase Sync Gateway/4.0.4(8;release) EE"
        #
        # In a dev build, the output:
        #
        # "vendor": {
        #    "version": "4.0"
        # },
        # "version": "Couchbase Sync Gateway/() EE"
        if model.vendor.version in model.version:
            sg_version = SyncGatewayVersion(model.version)
        else:
            sg_version = SyncGatewayVersion(model.vendor.version)
        try:
            packaging.version.parse(sg_version.version)
        except packaging.version.InvalidVersion as exc:
            raise CblTestError(
                f"Failed to parse Sync Gateway version from /_status response: {{resp}}\nversion={model.version}"
            ) from exc
        return sg_version

    def tls_cert(self) -> str | None:
        if not self.secure:
            cbl_trace("Sync Gateway instance not using TLS, returning empty tls_cert...")
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

    async def get_expvars(self) -> dict:
        """Gets the full stats payload from ``GET /_expvar``."""
        resp_data = await self._send_request("get", "/_expvar")
        assert isinstance(resp_data, dict)
        return cast(dict, resp_data)

    async def get_db_expvars(self, db_name: str, section: str) -> dict:
        """
        Gets one per-database stats section from ``GET /_expvar``, or an empty dict if absent.

        :param db_name: The name of the SGW database to inspect
        :param section: The section name, e.g. 'database', 'cache', 'delta_sync', 'shared_bucket_import'
        """
        expvars = await self.get_expvars()
        db_section = expvars.get("syncgateway", {}).get("per_db", {}).get(db_name, {})
        stats = db_section.get(section)
        return stats if isinstance(stats, dict) else {}

    async def bytes_transferred(self, dataset_name: str) -> tuple[int, int]:
        """
        Gets the bytes transferred for a given dataset

        :param dataset_name: The name of the dataset to get the bytes transferred for
        """
        db_stats = await self.get_db_expvars(dataset_name, "database")
        doc_reads_bytes = db_stats["doc_reads_bytes_blip"]
        doc_writes_bytes = db_stats["doc_writes_bytes_blip"]
        return doc_reads_bytes, doc_writes_bytes

    async def get_delta_sync_stats(self, dataset_name: str) -> dict:
        """
        Gets the ``delta_sync`` counters for a database from ``GET /_expvar``.
        Returns an empty dict if the section is absent.

        :param dataset_name: The name of the SGW database to inspect.
        """
        return await self.get_db_expvars(dataset_name, "delta_sync")

    async def _update_database_config(self, db_name: str, payload: DatabaseConfig) -> str | None:
        """
        Upsert a database configuration on the Sync Gateway instance

        Private: use `SyncGatewayCluster.update_database_config` instead of calling
        this directly, so that all nodes in the cluster stay in sync and the caller
        waits for the database to come back online with the new config.

        :param db_name: The name of the DB to create
        :param payload: The options for the DB to create
        :return: The version of the resulting config, or None if this Sync Gateway
                 does not report one
        """
        with self._tracer.start_as_current_span("update_database_config", attributes={"sg.database.name": db_name}):
            _, headers = await self._send_request_with_headers("post", f"/{db_name}/_config", payload)
            return _config_version(headers)

    async def _put_database(self, db_name: str, payload: DatabaseConfig) -> str | None:
        """
        Attempts to create a database on the Sync Gateway instance

        Private: use `SyncGatewayCluster.create_database` instead
        of calling this directly, so that all nodes in the cluster stay in sync.

        :param db_name: The name of the DB to create
        :param payload: The options for the DB to create
        :return: The version of the resulting config, or None if this Sync Gateway
                 does not report one
        """
        with self._tracer.start_as_current_span("put_database", attributes={"sg.database.name": db_name}):
            _, headers = await self._send_request_with_headers("put", f"/{db_name}/", payload)
            return _config_version(headers)

    async def get_database_status(self, db_name: str) -> DatabaseStatusResponse | None:
        """
        Gets the status of a database including its online/offline state.

        :param db_name: The name of the Database
        :return: DatabaseStatusResponse with state, sequences, etc. Returns None if database doesn't exist (404/403)
        """
        with self._tracer.start_as_current_span("get_database_status", attributes={"sg.database.name": db_name}):
            try:
                resp = await self._send_request("get", f"/{db_name}/")
                assert isinstance(resp, dict)
                return DatabaseStatusResponse.model_validate(resp)
            except CblSyncGatewayBadResponseError as e:
                if e.code in [403, 404]:  # Database doesn't exist
                    return None
                raise

    async def _wait_for_database_gone(
        self,
        db_name: str,
        timeout: float = 30.0,
        retry_delay: float = 1.0,
    ) -> None:
        """
        Wait until this node stops reporting db_name.

        :param db_name: Database the node should stop serving.
        :param timeout: Seconds to wait, against a default config poll interval of 10s.
        :param retry_delay: Seconds between polls.
        :raises TimeoutError: if the node is still serving the database after timeout
        """

        async def _wait_for_database_gone_poll() -> None:
            dbs = await self.get_all_databases_verbose()
            assert db_name not in dbs, f"{self} is still serving database {db_name}"

        with self._tracer.start_as_current_span("wait_for_database_gone", attributes={"sg.database.name": db_name}):
            await async_retry_assert(
                _wait_for_database_gone_poll,
                tenacity.wait_fixed(retry_delay),
                tenacity.stop_after_delay(timeout),
            )

    async def _delete_database(self, db_name: str, retry_count: int = 0) -> None:
        """
        Delete a database from this node's Sync Gateway configuration.

        Not public: a database belongs to the cluster, so callers want
        :func:`SyncGatewayCluster.delete_database`, which covers every node.

        .. warning:: This will not delete the data from the Couchbase Server bucket.
            To delete the data see the
            :func:`drop_bucket()<cbltest.api.couchbaseserver.CouchbaseServer.drop_bucket>` function

        :param db_name: The name of the Database to delete
        :param retry_count: Retries already spent on this delete
        """
        with self._tracer.start_as_current_span(
            "delete_database", attributes={"sg.database.name": db_name}
        ) as current_span:
            try:
                await self._send_request("delete", f"/{db_name}")
            except CblSyncGatewayBadResponseError as e:
                if e.code == 500 and "couldn't remove database" in e.body and "Not Found" in e.body:
                    # CBG-5731: the registry entry is already gone, so this node
                    # removed nothing and will drop the database on its next config poll.
                    # Retrying the DELETE only repeats the 500, so wait the node out.
                    current_span.add_event("SGW returned 500 (CBG-5731), waiting for removal")
                    await self._wait_for_database_gone(db_name)
                elif e.code == 500 and retry_count < 3:
                    cbl_warning(
                        f"Sync gateway returned 500 from DELETE database call, "
                        f"retrying ({retry_count + 1})...: {e.body}"
                    )
                    current_span.add_event("SGW returned 500, retry")
                    await asyncio.sleep(2)
                    await self._delete_database(db_name, retry_count + 1)
                elif e.code == 403 or e.code == 404:
                    pass  # Database doesn't exist anyway.
                else:
                    raise

    async def get_all_database_names(self) -> list[str]:
        """
        Gets the names of all databases configured on this Sync Gateway instance.

        :return: A list of database names
        """
        with self._tracer.start_as_current_span("get_all_database_names"):
            resp = await self._send_request("get", "/_all_dbs")
            assert isinstance(resp, list)
            return cast(list[str], resp)

    async def get_all_databases_verbose(self) -> dict[str, AllDatabasesVerboseEntry]:
        """
        Gets the bucket and state information for all databases configured on this
        Sync Gateway instance.

        :return: A dict of AllDatabasesVerboseEntry keyed by db_name
        """
        with self._tracer.start_as_current_span("get_all_databases_verbose"):
            resp = await self._send_request("get", "/_all_dbs?verbose=true")
            assert isinstance(resp, list)
            entries = _all_databases_verbose_adapter.validate_python(resp)
            return {entry.db_name: entry for entry in entries}

    def _analyze_dataset_response(self, response: list) -> None:
        assert isinstance(response, list), "Invalid bulk docs response (not a list)"
        typed_response = cast(list, response)
        for r in typed_response:
            info = cast(dict, r)
            assert isinstance(info, dict), "Invalid item inside bulk docs response list (not an object)"
            if "error" in info:
                raise CblSyncGatewayBadResponseError(
                    info["status"],
                    f"At least one bulk docs insert failed ({info['error']})",
                    body=dumps(info),
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
            attributes={"sg.database.name": db_name, "cbl.dataset.path": str(path)},
        ):
            last_scope: str = ""
            last_coll: str = ""
            collected: list[dict] = []
            async with aiofiles.open(path, encoding="utf8") as fin:
                async for json_line in fin:
                    json = cast(dict, loads(json_line))
                    assert isinstance(json, dict), f"Invalid entry in {path}!"
                    scope = cast(str, json["scope"])
                    collection = cast(str, json["collection"])
                    if (
                        (last_scope != scope or last_coll != collection or len(collected) > 500)
                        and last_scope
                        and last_coll
                        and collected
                    ):
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
        include_docs: bool = False,
    ) -> AllDocumentsResponse:
        """
        Gets all the documents in the given collection from Sync Gateway (id and revid)

        :param db_name: The name of the Sync Gateway database to query
        :param scope: The scope to use when querying Sync Gateway
        :param collection: The collection to use when querying Sync Gateway
        :param include_docs: If True, include full document bodies in the response (efficient bulk fetching)
        """
        with self._tracer.start_as_current_span(
            "get_all_documents",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.include_docs": include_docs,
            },
        ):
            params = {}
            if include_docs:
                params["include_docs"] = "true"

            resp = await self._send_request("get", f"/{db_name}.{scope}.{collection}/_all_docs", params=params)

            assert isinstance(resp, dict)
            return AllDocumentsResponse(cast(dict, resp))

    @tenacity.retry(
        # Import/propagation state flips on SGW's polling cadence, not sub-second,
        # so poll at a steady interval; give up after 60s.
        wait=tenacity.wait_fixed(2),
        stop=tenacity.stop_after_delay(60),
        reraise=True,
        retry=tenacity.retry_if_exception_type(AssertionError),
    )
    async def wait_for_document_count(
        self,
        db_name: str,
        min_count: int,
        scope: str = "_default",
        collection: str = "_default",
    ) -> AllDocumentsResponse:
        """
        Retry _all_docs until at least min_count docs are present, then return the
        response. Raises AssertionError if the count is not reached within 60s.

        Docs that arrive via an asynchronous path (SDK import, re-import after an
        SGW restart, cross-node/ISGR propagation) are not guaranteed to be visible
        in a single read.
        """
        all_docs = await self.get_all_documents(db_name, scope, collection)
        assert len(all_docs.rows) >= min_count, (
            f"Expected at least {min_count} docs in {db_name}.{scope}.{collection}, got {len(all_docs.rows)}"
        )
        return all_docs

    async def wait_for_documents(
        self,
        db_name: str,
        doc_ids: Collection[str],
        scope: str = "_default",
        collection: str = "_default",
    ) -> ChangesResponse:
        """
        Retry the _doc_ids filtered changes feed until every doc in doc_ids is
        present and not a tombstone, then return the response.  Raises TimeoutError
        if they have not all arrived within 60s.

        Use this rather than wait_for_document_count when the collection also holds
        unrelated documents.
        """
        wanted = set(doc_ids)

        async def _wait_for_documents_poll() -> ChangesResponse:
            changes = await self.get_changes(db_name, scope, collection, doc_ids=sorted(wanted))
            missing = wanted - {entry.id for entry in changes.results if not entry.deleted}
            assert not missing, f"Documents missing from {db_name}.{scope}.{collection}: {sorted(missing)}"
            return changes

        # Import lands on SGW's polling cadence, not sub-second.
        return await async_retry_assert(
            _wait_for_documents_poll,
            tenacity.wait_fixed(2),
            tenacity.stop_after_delay(60),
        )

    async def get_changes(
        self,
        db_name: str,
        scope: str = "_default",
        collection: str = "_default",
        version_type: str = "rev",
        doc_ids: list[str] | None = None,
        request_plus: bool = False,
    ) -> ChangesResponse:
        """
        Gets the changes feed from Sync Gateway, including deleted documents

        :param db_name: The name of the Sync Gateway database to query
        :param scope: The scope to use when querying Sync Gateway
        :param collection: The collection to use when querying Sync Gateway
        :param version_type: The version type to use ('rev' for revision IDs, 'cv' for version vectors in SGW 4.0+)
        :param doc_ids: If provided, restrict the feed to these document IDs via the `_doc_ids` filter
        :param request_plus: If True, wait for the channel cache to catch up to the latest sequence allocated
                             at the time of the request instead of serving whatever is already cached
        """
        with self._tracer.start_as_current_span(
            "get_changes",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
            },
        ):
            query_params = {"version_type": version_type}
            if doc_ids is not None:
                query_params["filter"] = "_doc_ids"
                query_params["doc_ids"] = dumps(doc_ids)
            if request_plus:
                query_params["request_plus"] = "true"

            resp = await self._send_request("get", f"/{db_name}.{scope}.{collection}/_changes", params=query_params)

            assert isinstance(resp, dict)
            return ChangesResponse(cast(dict, resp))

    async def _rewrite_rev_ids(
        self,
        db_name: str,
        updates: list[DocumentUpdateEntry],
        scope: str,
        collection: str,
    ) -> None:
        all_docs_body = [u.id for u in updates if u.rev is not None]
        all_docs_response = await self._send_request(
            "post",
            f"/{db_name}.{scope}.{collection}/_all_docs",
            JSONDictionary({"keys": all_docs_body}),
        )

        if not isinstance(all_docs_response, dict):
            raise ValueError("Inappropriate response from sync gateway _all_docs (not JSON dict)")

        rows = cast(dict, all_docs_response)["rows"]
        if not isinstance(rows, list):
            raise ValueError("Inappropriate response from sync gateway _all_docs (rows not a list)")

        for r in cast(list, rows):
            next_id = r["id"]
            found = assert_not_null(
                next((u for u in updates if u.id == next_id), None),
                f"Unable to find {next_id} in updates!",
            )
            new_rev_id = r["value"]["rev"]
            cbl_info(f"For document {found.id}: Swapping revid from {found.rev} to {new_rev_id}")
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

            body = {"docs": [u.to_json() for u in updates]}

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
                    current_doc = await self.get_document(db_name, update.id, scope, collection)
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
                merged_updates.append(DocumentUpdateEntry(update.id, update.rev, current_body))

            await self._rewrite_rev_ids(db_name, merged_updates, scope, collection)
            body = {"docs": [u.to_json() for u in merged_updates]}
            await self._send_request(
                "post",
                f"/{db_name}.{scope}.{collection}/_bulk_docs",
                JSONDictionary(body),
            )

    async def _replaced_revid(self, doc_id: str, revid: str, db_name: str, scope: str, collection: str) -> str:
        response = await self._send_request("get", f"/{db_name}.{scope}.{collection}/{doc_id}?show_cv=true")
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
                new_rev_id = await self._replaced_revid(doc_id, revid, db_name, scope, collection)
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

            await self._send_request("post", f"/{db_name}.{scope}.{collection}/_purge", JSONDictionary(body))

    async def get_document(
        self,
        db_name: str,
        doc_id: str,
        scope: str = "_default",
        collection: str = "_default",
        revision: str | None = None,
    ) -> RemoteDocument:
        """
        Gets a document from Sync Gateway

        :param db_name: The name of the DB endpoint that the document exists in
        :param doc_id: The document ID to get
        :param scope: The scope that the document exists in (default '_default')
        :param collection: The collection that the document exists in (default '_default')
        :param revision: A specific revision to get, instead of the current one (default None)
        :raises CblSyncGatewayBadResponseError: If Sync Gateway does not return the document. Returns a 404 for a non existent or tombstoned document.
        """
        with self._tracer.start_as_current_span(
            "get_document",
            attributes={
                "sg.database.name": db_name,
                "sg.scope.name": scope,
                "sg.collection.name": collection,
                "sg.document.id": doc_id,
            },
        ):
            params = {"rev": revision} if revision is not None else None
            response = await self._send_request("get", f"/{db_name}.{scope}.{collection}/{doc_id}", params=params)
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from sync gateway get /doc (not JSON)")

            return RemoteDocument(cast(dict, response))

    async def get_raw_document(
        self,
        db_name: str,
        doc_id: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> dict:
        """
        Gets a document together with its Sync Gateway metadata, using ``GET /{db}/_raw/{doc}``.

        The result is the document body with an added ``_xattrs`` key holding the raw xattrs,
        ``_sync`` among them.  ``_raw`` reads the bucket directly rather than going through the
        document load path, so it reports what is stored rather than what a load would produce.

        :param db_name: The name of the DB endpoint that the document exists in
        :param doc_id: The ID of the document to read
        :param scope: The scope that the document exists in (default '_default')
        :param collection: The collection that the document exists in (default '_default')
        """
        with self._tracer.start_as_current_span(
            "get_raw_document",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            response = await self._send_request("get", f"/{db_name}.{scope}.{collection}/_raw/{doc_id}")
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from sync gateway get /_raw/doc (not JSON)")

            return cast(dict, response)

    async def get_document_revisions(
        self,
        db_name: str,
        doc_id: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> list[str]:
        """
        Gets the revision tree history of a document's current revision, newest first, using
        ``GET /{db}/{doc}?revs=true``.

        Returns an empty list when the history is not usable.  A ``_revisions`` list can only
        describe a branch whose generations strictly increase, which requires ``start`` to be at
        least as large as the number of ids - the same rule Sync Gateway applies before sending a
        revision to a pre-4.0 client.  A document whose rev tree repeats a generation fails it, and
        so cannot be replicated.

        :param db_name: The name of the DB endpoint that the document exists in
        :param doc_id: The document ID to get the history of
        :param scope: The scope that the document exists in (default '_default')
        :param collection: The collection that the document exists in (default '_default')
        """
        with self._tracer.start_as_current_span(
            "get_document_revisions",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            response = await self._send_request(
                "get", f"/{db_name}.{scope}.{collection}/{doc_id}", params={"revs": "true"}
            )
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from sync gateway get /doc (not JSON)")

            revisions = cast(dict, response).get("_revisions")
            if not isinstance(revisions, dict):
                return []

            start = revisions.get("start")
            ids = revisions.get("ids")
            if not isinstance(start, int) or not isinstance(ids, list):
                return []

            if start < len(ids):
                cbl_info(
                    f"Revision history for '{doc_id}' is not usable: start {start} is below the "
                    f"{len(ids)} revision ids it would have to number"
                )
                return []

            return [f"{start - i}-{digest}" for i, digest in enumerate(ids)]

    async def create_document(
        self,
        db_name: str,
        doc_id: str,
        document: dict,
        scope: str = "_default",
        collection: str = "_default",
    ) -> RemoteDocument:
        """
        Creates a document in Sync Gateway

        :param db_name: The name of the DB endpoint where the document should be created
        :param doc_id: The document ID to create
        :param document: The document data to be created (as a dictionary)
        :param scope: The scope where the document should be created (default '_default')
        :param collection: The collection where the document should be created (default '_default')
        :return: The response from the Sync Gateway as a RemoteDocument
        """
        with self._tracer.start_as_current_span(
            "create_document",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            body = dict(document)
            body["_id"] = doc_id  # Ensure document has _id before sending
            response = await self._send_request(
                "put",
                f"/{db_name}.{scope}.{collection}/{doc_id}",
                payload=JSONDictionary(body),
            )

            # Check for response structure
            if not isinstance(response, dict):
                raise CblSyncGatewayBadResponseError(
                    500,
                    f"Failed to create document {doc_id}: unexpected response type",
                    body=str(response),
                )
            if "error" in response:
                raise CblSyncGatewayBadResponseError(500, f"Failed to create document {doc_id}", body=dumps(response))

            # Convert response to match expected format
            cast_resp = cast(dict, response)

            # Ensure RemoteDocument fields exist
            if "id" in cast_resp:
                cast_resp["_id"] = cast_resp.pop("id")  # Rename "id" to "_id"
            if "rev" in cast_resp:
                cast_resp["_rev"] = cast_resp.pop("rev")  # Rename "rev" to "_rev"
            if "cv" in cast_resp:
                cast_resp["_cv"] = cast_resp.pop("cv")  # Rename "cv" to "_cv"

            return RemoteDocument(cast_resp)

    async def update_document(
        self,
        db_name: str,
        doc_id: str,
        document: dict,
        rev: str,
        scope: str = "_default",
        collection: str = "_default",
        wait_for_caching_feed: bool = False,
    ) -> RemoteDocument:
        """
        Updates a document in Sync Gateway.

        :param db_name: The name of the DB endpoint where the document exists
        :param doc_id: The document ID to update
        :param document: The updated document data (as a dictionary)
        :param rev: The current revision ID of the document
        :param scope: The scope where the document exists (default '_default')
        :param collection: The collection where the document exists (default '_default')
        :param wait_for_caching_feed: If True, read the update back from a `request_plus` changes feed filtered to
                                      this document before returning, and populate the returned document's `seq`
                                      from the entry matching the revision just written. This makes `seq` this
                                      update's own sequence rather than a stale pre-write one. Raises if the
                                      document was superseded by a concurrent write before the feed was read,
                                      since the feed then reports only that later sequence (default False)
        :return: The updated document as a RemoteDocument object
        """
        with self._tracer.start_as_current_span(
            "update_document",
            attributes={
                "cbl.database.name": db_name,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            body = dict(document)
            body["_id"] = doc_id
            body["_rev"] = rev

            params = {"new_edits": "true", "rev": rev}

            response = await self._send_request(
                "put",
                f"/{db_name}.{scope}.{collection}/{doc_id}",
                payload=JSONDictionary(body),
                params=params,
            )

            if not isinstance(response, dict):
                raise CblSyncGatewayBadResponseError(
                    500,
                    f"Failed to update document {doc_id} with rev {rev}: unexpected response type",
                    body=str(response),
                )
            if "error" in response:
                raise CblSyncGatewayBadResponseError(
                    500, f"Failed to update document {doc_id} with rev {rev}", body=dumps(response)
                )

            # Convert response to match expected format
            cast_resp = cast(dict, response)

            # Ensure RemoteDocument fields exist
            if "id" in cast_resp:
                cast_resp["_id"] = cast_resp.pop("id")  # Rename "id" to "_id"
            if "rev" in cast_resp:
                cast_resp["_rev"] = cast_resp.pop("rev")  # Rename "rev" to "_rev"
            if "cv" in cast_resp:
                cast_resp["_cv"] = cast_resp.pop("cv")  # Rename "cv" to "_cv"

            if not wait_for_caching_feed:
                return RemoteDocument(cast_resp)

            assert "_rev" in cast_resp or "_cv" in cast_resp, (
                f"Update of document {doc_id} returned neither a revision ID nor a CV, so its sequence "
                "cannot be read back from the changes feed"
            )
            version_type = "rev" if "_rev" in cast_resp else "cv"
            expected_revision = cast(str, cast_resp[f"_{version_type}"])

            # request_plus waits for the cache to catch up to every sequence allocated before this request,
            # which includes the one the PUT above was given.
            changes = await self.get_changes(
                db_name,
                scope,
                collection,
                version_type=version_type,
                doc_ids=[doc_id],
                request_plus=True,
            )
            entries = [e for e in changes.results if e.id == doc_id]
            assert entries, (
                f"Changes feed has no entry for {doc_id} even after a request_plus feed "
                f"(last_seq={changes.last_seq}, results="
                f"{dumps([{'id': e.id, 'seq': e.seq, 'changes': e.changes, 'deleted': e.deleted} for e in changes.results])})"
            )

            # The feed carries only the document's current revision, so no match means a concurrent write
            # superseded this one and the sequence on offer is that write's, not ours.
            matching = [e for e in entries if expected_revision in e.changes]
            assert matching, (
                f"Document {doc_id} was superseded by {[e.changes for e in entries]} "
                f"(seq {[e.seq for e in entries]}) before the sequence assigned to revision "
                f"{expected_revision} could be read back"
            )

            return RemoteDocument(cast_resp, parse_sequence_id(matching[0].seq))

    async def close(self) -> None:
        """
        Closes this Sync Gateway's aiohttp session, and its Caddy's
        """
        if not self.__session.closed:
            await self.__session.close()
        await self._caddy.close()

    async def get_database_config(self, db_name: str) -> DatabaseConfig:
        """
        Gets the configuration for a specific database from the admin API.

        Args:
            db_name: The name of the database to get configuration for

        Returns:
            DatabaseConfig containing the database configuration
        """
        _assert_not_null(db_name, "db_name")
        with self._tracer.start_as_current_span("get_database_config", attributes={"cbl.database.name": db_name}):
            resp = await self._send_request("GET", f"/{db_name}/_config")
            return DatabaseConfig.model_validate(resp)

    async def get_database_config_version(self, db_name: str) -> str | None:
        """
        Gets the version of the config that this node is currently serving for a
        database, from the ``Etag`` of ``GET /{db}/_config``.

        :param db_name: The name of the database to get the config version for
        :return: The config version, or None if this Sync Gateway does not report one
        """
        _assert_not_null(db_name, "db_name")
        with self._tracer.start_as_current_span(
            "get_database_config_version", attributes={"cbl.database.name": db_name}
        ):
            _, headers = await self._send_request_with_headers("GET", f"/{db_name}/_config")
            return _config_version(headers)

    @property
    def caddy(self) -> caddy.Caddy:
        """Gets the Caddy file server running alongside this Sync Gateway"""
        return self._caddy

    async def fetch_log_file(
        self,
        log_type: str,
    ) -> str:
        """
        Fetches a log file from the remote Sync Gateway server via Caddy HTTP server

        :param log_type: Type of log file to fetch (e.g., 'debug', 'info', 'warn', 'error')
        :return: Content of the log file as a string
        :raises FileNotFoundError: If the log file doesn't exist
        :raises CblTimeoutError: If the transfer stops making progress
        :raises CblTestError: For other HTTP or network errors
        """
        return await self._caddy.fetch(f"sg_{log_type}.log")

    async def start_sgcollect(
        self,
        upload: bool = False,
        redact_level: SGCollectRedactLevel | None = None,
        redact_salt: str | None = None,
        output_dir: str | None = None,
    ) -> dict:
        """
        Starts SGCollect using the REST API endpoint

        :param upload: Whether Sync Gateway should upload the resulting archive
        :param redact_level: Redaction level for the collected logs (SGW default if omitted)
        :param redact_salt: Custom salt for redaction hashing
        :param output_dir: Output directory on the remote server
        :return: Response dict with status
        """
        options = SGCollectOptions(
            upload=upload,
            redact_level=redact_level,
            redact_salt=redact_salt,
            output_dir=output_dir,
        )
        options_json = options.model_dump(mode="json", exclude_none=True)
        with self._tracer.start_as_current_span("start_sgcollect", attributes=options_json):
            resp = await self._send_request(
                "post",
                "/_sgcollect_info",
                JSONDictionary(options_json),
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

    async def wait_for_sgcollect_to_complete(self, max_attempts: int = 100, wait_time: int = 5) -> None:
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

    async def run_sgcollect(
        self,
        local_output_dir: Path,
        redact_level: SGCollectRedactLevel | None = None,
    ) -> Path:
        """
        Runs SGCollect on this Sync Gateway node end to end: starts the collection,
        waits for it to finish, then downloads the resulting zip via Caddy.

        Snapshots the zips present before starting so a zip left over from an
        earlier collection is never mistaken for this run's output.

        :param local_output_dir: Local directory to download the resulting zip into
        :param redact_level: Redaction level for the collected logs (SGW default if omitted)
        :return: The local path of the downloaded zip
        :raises CblTestError: If no new zip appears after collection, or if more
            than one new zip appears (ambiguous result)
        :raises Exception: If SGCollect fails to complete
        """
        with self._tracer.start_as_current_span("run_sgcollect", attributes={"cbl.sgw.hostname": self.hostname}):
            pattern = r"sgcollectinfo-.*\.zip"
            before = set(await self.caddy.list(pattern))

            await self.start_sgcollect(redact_level=redact_level)
            await self.wait_for_sgcollect_to_complete()

            after = set(await self.caddy.list(pattern))
            new_files = after - before
            if not new_files:
                raise CblTestError(
                    f"No new sgcollect zip found on {self.hostname} after collection. Files present: {sorted(after) or '(none)'}"
                )
            if len(new_files) > 1:
                raise CblTestError(
                    f"Expected exactly one new sgcollect zip on {self.hostname} "
                    f"after collection, found {len(new_files)}: {sorted(new_files)}"
                )

            (zip_name,) = new_files
            safe_host = self.hostname.replace(".", "_")
            local_path = local_output_dir / f"{safe_host}-{zip_name}"
            await self.caddy.download(zip_name, local_path)
            return local_path


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
    ) -> None:
        """
        Initialize a SyncGateway admin client.

        :param url: The hostname/URL of the Sync Gateway instance
        :param username: Admin username
        :param password: Admin password
        :param port: Admin API port (default 4985)
        :param secure: Whether to use TLS/HTTPS
        :param public_port: Public API port (default 4984)
        """
        super().__init__(url, username, password, port, secure, public_port)
        r = requests.get(
            f"{self.scheme}{url}:{port}/_config",
            auth=(username, password),
            # disable hostname verification as we do in _create_session
            verify=False,
            timeout=10,
        )
        r.raise_for_status()
        config = r.json()
        try:
            self.using_rosmar = config["bootstrap"]["server"].startswith("rosmar")
        except KeyError:
            raise CblTestError(
                f"Unexpected response from Sync Gateway /_config endpoint, cannot determine if using Rosmar. {config}"
            ) from None

        # Cached so tests can skip_if_not(sg.has_caddy_sidecar) instead of
        # failing on a connection error.
        self.has_caddy_sidecar: bool = self.caddy.is_reachable()
        self.has_shell2http_sidecar: bool = is_sidecar_reachable(url, SHELL2HTTP_PORT)

    async def drop_rosmar_bucket(self, bucket_name: str) -> None:
        """
        Drops a Rosmar-backed bucket.

        .. note:: Only valid when this Sync Gateway node is using Rosmar
            (``self.using_rosmar``).

        :param bucket_name: The name of the Rosmar bucket to drop
        :raises CblTestError: If this Sync Gateway node is not using Rosmar
        """
        with self._tracer.start_as_current_span("drop_rosmar_bucket", attributes={"cbl.bucket.name": bucket_name}):
            if not self.using_rosmar:
                raise CblTestError(f"Cannot drop Rosmar bucket '{bucket_name}', Sync Gateway is not using Rosmar")

            try:
                await self._send_request("delete", f"/_rosmar/{bucket_name}")
            except CblSyncGatewayBadResponseError as e:
                if e.code != 404:
                    raise

    async def is_using_views(self, db_name: str) -> bool:
        """Determine whether the given Sync Gateway database is using views rather than GSI.

        Rosmar has no GSI support, so it always behaves as though views are in use,
        regardless of `enable_shared_bucket_access`.

        Args:
            db_name: The name of the database to check.

        Returns:
            True if using Rosmar, or if the database is configured with
            enable_shared_bucket_access=false.
        """
        if self.using_rosmar:
            return True
        config = await self.get_database_config(db_name)
        return config.enable_shared_bucket_access is False

    def create_collection_access_dict(self, input: dict[str, list[str]]) -> dict:
        """
        Creates a collection access dictionary in the format that Sync Gateway expects,
        given an input dictionary keyed by collection with a list of channels

        :param input: The simplified input dictionary of collection -> channels
        """

        ret_val = {}
        for c, channels in input.items():
            if not isinstance(c, str):
                raise ValueError("Non-string key found in input dictionary to create_collection_access_dict")

            if not isinstance(channels, list):
                raise ValueError(f"Non-list found for value of collection {c} in create_collection_access_dict")

            if "." not in c:
                raise ValueError(f"Input collection '{c}' in create_collection_access_dict needs to be fully qualified")

            spec = c.split(".")
            if len(spec) != 2:
                raise ValueError(f"Input collection '{c}' has too many dots in create_collection_access_dict")

            if spec[0] not in ret_val:
                scope_dict: dict[str, dict] = {}
                ret_val[spec[0]] = scope_dict
            else:
                scope_dict = ret_val[spec[0]]

            scope_dict[spec[1]] = {"admin_channels": channels}

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
        with self._tracer.start_as_current_span("add_user", attributes={"cbl.user.name": name}):
            body: dict[str, Any] = {
                "name": name,
            }

            if password is not None:
                body["password"] = password

            if collection_access is not None:
                body["collection_access"] = collection_access

            if admin_roles is not None:
                body["admin_roles"] = admin_roles

            await self._send_request("put", f"/{db_name}/_user/{name}", JSONDictionary(body))

    async def delete_user(self, db_name: str, name: str) -> None:
        """
        Deletes a user from a Sync Gateway database

        :param db_name: The name of the Database
        :param name: The username to delete
        """
        with self._tracer.start_as_current_span("delete_user", attributes={"cbl.user.name": name}):
            try:
                await self._send_request("delete", f"/{db_name}/_user/{name}")
            except CblSyncGatewayBadResponseError as e:
                if e.code == 404:
                    # User doesn't exist, that's fine
                    pass
                else:
                    raise

    async def create_session(self, db_name: str, name: str) -> str:
        """
        Creates a login session for an existing user via the admin API
        (POST /{db}/_session) and returns its session id.

        A session cannot be created for a non-existent user or the GUEST user;
        Sync Gateway answers 404 and 400 respectively.

        Calling this again does not invalidate the existing session; it creates an
        additional session alongside it.

        :param db_name: The name of the database to create the session against
        :param name: The user to create the session for
        :return: The id of the created session
        """
        with self._tracer.start_as_current_span("create_session", attributes={"sg.database.name": db_name}):
            resp = await self._send_request("post", f"/{db_name}/_session", JSONDictionary({"name": name}))
            assert isinstance(resp, dict)
            session_id = resp["session_id"]
            assert isinstance(session_id, str)
            return session_id

    async def delete_session(self, db_name: str, session_id: str) -> None:
        """
        Invalidates a session via the admin API (DELETE /{db}/_session/{sessionid}),
        logging out anyone using it and preventing future use.

        :param db_name: The name of the database the session belongs to
        :param session_id: The id of the session to invalidate

        :raises CblSyncGatewayBadResponseError: Sync Gateway answers 404 for an unknown, or already deleted session_id
        """
        with self._tracer.start_as_current_span("delete_session", attributes={"sg.database.name": db_name}):
            await self._send_request("delete", f"/{db_name}/_session/{session_id}")

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
        with self._tracer.start_as_current_span("add_role", attributes={"cbl.role.name": role}):
            body = {"collection_access": collection_access}

            await self._send_request("put", f"/{db_name}/_role/{role}", JSONDictionary(body))

    async def wait_for_rest_api(self) -> None:
        """Wait until this node's REST API responds, which is not until its databases load."""

        async def _wait_for_rest_api_poll() -> None:
            try:
                await self._send_request("get", "/_ping")
            except (CblSyncGatewayBadResponseError, ClientConnectorError) as exc:
                raise AssertionError(f"SGW REST API is not ready: {exc}") from exc

        await async_retry_assert(
            _wait_for_rest_api_poll,
            tenacity.wait_fixed(0.1),
            tenacity.stop_after_delay(70),
        )

    async def is_serving(self) -> bool:
        """Whether this node's public REST API answers right now. Reports rather than raises."""
        try:
            async with (
                self._create_session(self.secure, self.scheme, self.hostname, self.public_port, None) as session,
                session.get("/", timeout=ClientTimeout(total=5)) as resp,
            ):
                return resp.status == 200
        except (ClientConnectorError, TimeoutError):
            return False

    async def _wait_for_db_online(
        self,
        db_name: str,
        *,
        version: str | None = None,
        max_retries: int = 70,
        retry_delay: int = 1,
    ) -> None:
        """
        Wait until the SGW node reports the database as Online.

        :param db_name: Database name to poll.
        :param version: If given, also wait until the node serves this config version,
                        since writing a config brings the database online asynchronously
                        and the node may still be serving the previous one.
        :param max_retries: Number of polls before timing out.
        :param retry_delay: Seconds between polls.
        """

        async def _wait_for_db_online_poll() -> None:
            dbs = await self.get_all_databases_verbose()
            assert db_name in dbs, f"Database {db_name} is not online (database not present in /_all_dbs?verbose=true)"
            entry = dbs[db_name]
            assert entry.state == DatabaseState.ONLINE, f"Database {db_name} is not online: {entry}"
            if version is not None:
                current = await self.get_database_config_version(db_name)
                assert current == version, (
                    f"Database {db_name} is serving config version {current}, waiting for {version}"
                )

        await async_retry_assert(
            _wait_for_db_online_poll,
            tenacity.wait_fixed(retry_delay),
            tenacity.stop_after_attempt(max_retries),
        )

    async def get_import_count(self, db_name: str) -> int:
        """
        Gets this node's shared_bucket_import import_count expvar for the given
        database.  Each import is handled by exactly one node, so a zero here does
        not mean the cluster imported nothing.

        :param db_name: The database to read the stat for
        """
        resp_data = await self._send_request("get", "/_expvar")
        assert isinstance(resp_data, dict)
        expvars = cast(dict, resp_data)
        return (
            expvars.get("syncgateway", {})
            .get("per_db", {})
            .get(db_name, {})
            .get("shared_bucket_import", {})
            .get("import_count", 0)
        )

    async def reset_user(
        self,
        db_name: str,
        username: str,
        password: str,
        channels: list[str],
    ) -> None:
        """
        Helper method to delete a user if they exist and recreate them with specific channel access.

        :param db_name: The database name
        :param username: The username to reset
        :param password: The password for the user
        :param channels: List of channels the user should have access to
        """
        await self.delete_user(db_name, username)
        await self.add_user(
            db_name,
            username,
            password=password,
            collection_access={"_default": {"_default": {"admin_channels": channels}}},
        )

    @asynccontextmanager
    async def get_user_client(
        self,
        username: str,
        password: str,
    ) -> AsyncIterator["SyncGatewayUserClient"]:
        """
        Yields a public-API client authenticated as an already existing user (e.g. one the
        dataset created), closing its session on exit.  Use :func:`create_user_client` when
        the user has to be created first.

        :param username: The username to authenticate as
        :param password: The password for the user
        :return: An AsyncIterator yielding a SyncGatewayUserClient instance authenticated as the user (uses public port)
        """
        client = SyncGatewayUserClient(
            self.hostname,
            username,
            password,
            port=self.public_port,
            secure=self.secure,
        )
        try:
            yield client
        finally:
            await client.close()

    @asynccontextmanager
    async def create_user_client(
        self,
        db_name: str,
        username: str,
        password: str,
        channels: list[str],
    ) -> AsyncIterator["SyncGatewayUserClient"]:
        """
        Helper method to create a user with channel access and return a user-specific SG client
        as an async context manager.

        This is a convenience method for tests that need to verify user-level access control.
        Upon exiting the context, the user client session is closed.

        :param db_name: The database name
        :param username: The username to create
        :param password: The password for the user
        :param channels: List of channels the user should have access to
        :return: An AsyncIterator yielding a SyncGatewayUserClient instance authenticated as the user (uses public port)
        """
        await self.reset_user(db_name, username, password, channels)

        async with self.get_user_client(username, password) as client:
            yield client

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
                "sg.database.name": db_name,
                "sg.replication.id": payload.replication_id,
                "sg.replication.direction": payload.direction,
            },
        ):
            await self._send_request("put", f"/{db_name}/_replication/{payload.replication_id}", payload)
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
                "sg.database.name": db_name,
                "sg.replication.id": replication_id,
            },
        ):
            resp = await self._send_request("get", f"/{db_name}/_replicationStatus/{replication_id}")
            assert isinstance(resp, dict)
            return cast(dict, resp)

    async def stop_isgr(self, db_name: str, replication_id: str, continuous: bool = False) -> None:
        """
        Stops and removes an Inter-Sync Gateway Replication.

        :param db_name: The local database name
        :param replication_id: The replication identifier to stop
        :param continuous: Replication type
        """
        with self._tracer.start_as_current_span(
            "stop_isgr",
            attributes={
                "sg.database.name": db_name,
                "sg.replication.id": replication_id,
            },
        ):
            try:
                await self._send_request("delete", f"/{db_name}/_replication/{replication_id}")
            except CblSyncGatewayBadResponseError as e:
                if e.code == 404 and continuous:
                    cbl_error(f"ISGR {replication_id} is continuous but does not exist")
                    raise
            return

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
                "sg.database.name": db_name,
                "sg.replication.id": replication_id,
                "sg.target.status": target_status,
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

            raise TimeoutError(f"ISGR {replication_id} did not reach status '{target_status}' within {timeout} seconds")

    async def get_user_access_history(self, db_name: str, name: str) -> dict[str, dict[str, list[str]]]:
        """
        Gets the channel access history of a user, organized by scope and collection.

        :param db_name: The name of the database
        :param name: The username to query
        :return: A dict of scope -> collection -> list of channel names
        """
        with self._tracer.start_as_current_span(
            "get_user_access_history", attributes={"sg.database.name": db_name, "cbl.user.name": name}
        ):
            resp = await self._send_request("get", f"/{db_name}/_user/{name}/_access_history")
            assert isinstance(resp, dict)
            return cast(dict, resp).get("channels", {})

    async def compact_user_access_history(
        self, db_name: str, name: str, channels: dict[str, dict[str, list[str]]]
    ) -> dict[str, dict[str, list[str]]]:
        """
        Removes the specified channels from a user's channel access history.

        :param db_name: The name of the database
        :param name: The username whose history should be compacted
        :param channels: The channels to remove, organized by scope and collection
            (e.g. {"scope1": {"collection1": ["channel1"]}})
        :return: The channels that were actually removed, organized by scope and collection
        """
        with self._tracer.start_as_current_span(
            "compact_user_access_history", attributes={"sg.database.name": db_name, "cbl.user.name": name}
        ):
            body = {"channels": channels}
            resp = await self._send_request(
                "post",
                f"/{db_name}/_user/{name}/_access_history/compact",
                JSONDictionary(body),
            )
            assert isinstance(resp, dict)
            return cast(dict, resp).get("compacted_channels", {})

    async def get_document_channel_history(
        self,
        db_name: str,
        doc_id: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> dict[str, list[int]]:
        """
        Gets the channel revocation history of a document.

        :param db_name: The name of the database
        :param doc_id: The document ID to query
        :param scope: The scope the document is in (default '_default')
        :param collection: The collection the document is in (default '_default')
        :return: A dict of channel name -> sequences at which the document was removed from it
        """
        with self._tracer.start_as_current_span(
            "get_document_channel_history",
            attributes={
                "sg.database.name": db_name,
                "sg.scope.name": scope,
                "sg.collection.name": collection,
                "sg.document.id": doc_id,
            },
        ):
            resp = await self._send_request("get", f"/{db_name}.{scope}.{collection}/_channel_history/{doc_id}")
            assert isinstance(resp, dict)
            return cast(dict, resp)

    async def compact_document_channel_history(
        self,
        db_name: str,
        doc_id: str,
        seq: int,
        scope: str = "_default",
        collection: str = "_default",
    ) -> list[str]:
        """
        Compacts a document's channel history, removing revocation entries for channels the
        document left before the given sequence.

        :param db_name: The name of the database
        :param doc_id: The document ID to compact
        :param seq: Channel history with end sequences earlier than this will be removed
        :param scope: The scope the document is in (default '_default')
        :param collection: The collection the document is in (default '_default')
        :return: The list of channels that were compacted
        """
        with self._tracer.start_as_current_span(
            "compact_document_channel_history",
            attributes={
                "sg.database.name": db_name,
                "sg.scope.name": scope,
                "sg.collection.name": collection,
                "sg.document.id": doc_id,
                "sg.compact.seq": seq,
            },
        ):
            resp = await self._send_request(
                "post",
                f"/{db_name}.{scope}.{collection}/_channel_history/{doc_id}/compact",
                JSONDictionary({"seq": seq}),
            )
            assert isinstance(resp, dict)
            return cast(dict, resp).get("compacted_channels", [])


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
    ) -> None:
        """
        Initialize a SyncGatewayUserClient for public API access.

        :param url: The hostname/URL of the Sync Gateway instance
        :param username: Username for authentication
        :param password: Password for authentication
        :param port: Public API port (default 4984)
        :param secure: Whether to use TLS/HTTPS
        """
        super().__init__(url, username, password, port, secure)
