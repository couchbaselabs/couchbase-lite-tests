import ssl
from abc import ABC, abstractmethod
from json import dumps, loads
from pathlib import Path
from typing import Dict, List, Tuple, cast, Any, Optional
from urllib.parse import urljoin

from aiohttp import ClientSession, BasicAuth, TCPConnector
from opentelemetry.trace import get_tracer
from varname import nameof

from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.jsonserializable import JSONSerializable, JSONDictionary
from cbltest.assertions import _assert_not_null
from cbltest.httplog import get_next_writer
from cbltest.jsonhelper import _get_typed_required
from cbltest.logging import cbl_warning
from cbltest.version import VERSION


class _CollectionMap(JSONSerializable):
    @property
    def scope_name(self) -> str:
        return self.__scope_name

    @property
    def collections(self) -> List[str]:
        return list(self.__collections.keys())

    def __init__(self, scope_name: str) -> None:
        _assert_not_null(scope_name, nameof(scope_name))
        self.__scope_name = scope_name
        self.__collections: Dict[str, dict] = {}

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
        _assert_not_null(dataset_or_config, nameof(dataset_or_config))
        assert isinstance(dataset_or_config, dict), "Invalid dataset_or_config passed to PutDatabasePayload"
        self.__config: dict = dataset_or_config
        if "config" in dataset_or_config:
            self.__config = _get_typed_required(dataset_or_config, "config", dict)

        self.__bucket = _get_typed_required(self.__config, "bucket", str)
        """The bucket name in the backing Couchbase Server"""

        self.__scopes: Dict[str, _CollectionMap] = {}
        scopes = _get_typed_required(self.__config, "scopes", dict)
        for scope in scopes:
            scope_dict = _get_typed_required(scopes, scope, dict)
            collections = _get_typed_required(scope_dict, "collections", dict)
            for collection in collections:
                collection_dict = _get_typed_required(collections, collection, dict)
                self._add_collection(collection_dict, scope, collection)

    def scopes(self) -> List[str]:
        """Gets all the scopes contained in the payload"""
        return list(self.__scopes.keys())

    def collections(self, scope: str) -> List[str]:
        """
        Gets a list of collections specified for the given scope
        
        :param scope: The name of the scope to check
        """

        map = self.__scopes.get(scope)
        if not map:
            raise KeyError(f"No collections present for {scope}")

        return map.collections

    def _add_collection(self, payload: dict, scope_name: str, collection_name: str) -> None:
        """
        Adds a collection to the configuration of the database (must exist on Couchbase Server).
        The scope name and collection name both default to "_default".

        :param scope_name: The name of the scope in which the collection resides
        :param collection_name: The name of the collection to retrieve data from
        """
        _assert_not_null(scope_name, nameof(scope_name))
        col_map = self.__scopes.get(scope_name, _CollectionMap(collection_name))
        self.__scopes[scope_name] = col_map
        col_map.add_collection(collection_name, payload)

    def to_json(self) -> Any:
        return self.__config


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
    def revid(self) -> Optional[str]:
        """Gets the revision ID of the row"""
        return self.__revid

    @property
    def cv(self) -> Optional[str]:
        """Gets the current version for the row"""
        return self.__cv

    @property
    def revision(self) -> str:
        """Gets the either revid or cv, whichever is populated (at least one must be)"""
        return cast(str, self.__revid if self.__revid is not None else self.__cv)

    def __init__(self, key: str, id: str, revid: Optional[str], cv: Optional[str]) -> None:
        self.__key = key
        self.__id = id
        self.__revid = revid
        self.__cv = cv


class AllDocumentsResponse:
    """
    A class representing an all_docs response from Sync Gateway
    """

    @property
    def rows(self) -> List[AllDocumentsResponseRow]:
        """Gets the entries of the response"""
        return self.__rows

    def __len__(self) -> int:
        return self.__len

    def __init__(self, input: dict) -> None:
        self.__len = input["total_rows"]
        self.__rows: List[AllDocumentsResponseRow] = []
        for row in cast(List[Dict], input["rows"]):
            rev = cast(Dict, row["value"])
            self.__rows.append(AllDocumentsResponseRow(
                row["key"],
                row["id"],
                cast(str, rev["rev"]) if "rev" in rev else None,
                cast(str, rev["cv"]) if "cv" in rev else None))


class DocumentUpdateEntry(JSONSerializable):
    """
    A class that represents an update to a document. 
    For creating a new document, set revid to None.
    """

    def __init__(self, id: str, revid: Optional[str], body: dict):
        self.__body = body.copy()
        self.__body["_id"] = id
        if revid:
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
    def revid(self) -> str:
        """Gets the revision ID of the document"""
        return self.__rev

    @property
    def body(self) -> dict:
        """Gets the body of the document"""
        return self.__body

    def __init__(self, body: dict) -> None:
        if "error" in body:
            raise ValueError("Trying to create remote document from error response")

        self.__body = body.copy()
        self.__id = cast(str, body["_id"])
        self.__rev = cast(str, body["_rev"])
        del self.__body["_id"]
        del self.__body["_rev"]

    def to_json(self) -> Any:
        ret_val = self.__body.copy()
        ret_val["_id"] = self.__id
        ret_val["_rev"] = self.__rev
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
    def parse(self, input: str) -> Tuple[str, int]:
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

    def parse(self, input: str) -> Tuple[str, int]:
        first_lparen = input.find("(")
        first_semicol = input.find(";")
        if first_lparen == -1 or first_semicol == -1:
            return ("unknown", 0)

        return input[0:first_lparen], int(input[first_lparen + 1:first_semicol])


class SyncGateway:
    """
    A class for interacting with a given Sync Gateway instance
    """

    def __init__(self, url: str, username: str, password: str, port: int = 4984, admin_port: int = 4985,
                 secure: bool = False):
        scheme = "https://" if secure else "http://"
        ws_scheme = "wss://" if secure else "ws://"
        self.__admin_url = f"{scheme}{url}:{admin_port}"
        self.__replication_url = f"{ws_scheme}{url}:{port}"
        self.__tracer = get_tracer(__name__, VERSION)
        self.__secure: bool = secure
        self.__hostname: str = url
        self.__admin_port: int = admin_port
        self.__admin_session: ClientSession = self._create_session(secure, scheme, url, admin_port,
                                                                   BasicAuth(username, password, "ascii"))

    def _create_session(self, secure: bool, scheme: str, url: str, port: int,
                        auth: Optional[BasicAuth]) -> ClientSession:
        if secure:
            ssl_context = ssl.create_default_context(cadata=self.tls_cert())
            # Disable hostname check so that the pre-generated SG can be used on any machines.
            ssl_context.check_hostname = False
            return ClientSession(f"{scheme}{url}:{port}", auth=auth, connector=TCPConnector(ssl=ssl_context))
        else:
            return ClientSession(f"{scheme}{url}:{port}", auth=auth)

    async def _send_request(self, method: str, path: str, payload: Optional[JSONSerializable] = None,
                            params: Optional[Dict[str, str]] = None, session: Optional[ClientSession] = None) -> Any:
        if session is None:
            session = self.__admin_session

        with self.__tracer.start_as_current_span(f"send_request",
                                                 attributes={"http.method": method, "http.path": path}):
            headers = {"Content-Type": "application/json"} if payload is not None else None
            data = "" if payload is None else payload.serialize()
            writer = get_next_writer()
            writer.write_begin(f"Sync Gateway [{self.__admin_url}] -> {method.upper()} {path}", data)
            resp = await session.request(method, path, data=data, headers=headers, params=params)
            if resp.content_type.startswith("application/json"):
                ret_val = await resp.json()
                data = dumps(ret_val, indent=2)
            else:
                data = await resp.text()
                ret_val = data
            writer.write_end(f"Sync Gateway [{self.__admin_url}] <- {method.upper()} {path} {resp.status}", data)
            if not resp.ok:
                raise CblSyncGatewayBadResponseError(resp.status, f"{method} {path} returned {resp.status}")

            return ret_val

    async def get_version(self) -> CouchbaseVersion:
        # Telemetry not really important for this call
        scheme = "https://" if self.__secure else "http://"
        async with self._create_session(self.__secure, scheme, self.__hostname, 4984, None) as s:
            resp = await self._send_request("get", "/", session=s)
            assert isinstance(resp, dict)
            resp_dict = cast(dict, resp)
            raw_version = _get_typed_required(resp_dict, "version", str)
            assert "/" in raw_version
            return SyncGatewayVersion(raw_version.split("/")[1])

    def tls_cert(self) -> Optional[str]:
        if not self.__secure:
            cbl_warning("Sync Gateway instance not using TLS, returning empty tls_cert...")
            return None

        return ssl.get_server_certificate((self.__hostname, self.__admin_port))

    def replication_url(self, db_name: str):
        """
        Gets the replicator URL (e.g. ws://xxx) for a given db
        
        :param db_name: The DB to replicate with
        """
        _assert_not_null(db_name, nameof(db_name))
        return urljoin(self.__replication_url, db_name)

    async def put_database(self, db_name: str, payload: PutDatabasePayload) -> None:
        """
        Attempts to create a database on the Sync Gateway instance

        :param db_name: The name of the DB to create
        :param payload: The options for the DB to create
        """
        with self.__tracer.start_as_current_span("put_database",
                                                 attributes={"cbl.database.name": db_name}) as current_span:
            try:
                await self._send_request("put", f"/{db_name}", payload)
            except CblSyncGatewayBadResponseError as e:
                if e.code == 500:
                    cbl_warning("Sync gateway returned 500 from PUT database call, retrying...")
                    current_span.add_event("SGW returned 500, retry")
                    await self.put_database(db_name, payload)
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
        with self.__tracer.start_as_current_span("delete_database", attributes={"cbl.database.name": db_name}):
            await self._send_request("delete", f"/{db_name}")

    def create_collection_access_dict(self, input: Dict[str, List[str]]) -> dict:
        """
        Creates a collection access dictionary in the format that Sync Gateway expects,
        given an input dictionary keyed by collection with a list of channels

        :param input: The simplified input dictionary of collection -> channels
        """

        ret_val = {}
        for c in input:
            if not isinstance(c, str):
                raise ValueError("Non-string key found in input dictionary to create_collection_access_dict")

            channels = input[c]
            if not isinstance(channels, list):
                raise ValueError(f"Non-list found for value of collection {c} in create_collection_access_dict")

            if "." not in c:
                raise ValueError(f"Input collection '{c}' in create_collection_access_dict needs to be fully qualified")

            spec = c.split(".")
            if len(spec) != 2:
                raise ValueError(f"Input collection '{c}' has too many dots in create_collection_access_dict")

            if spec[0] not in ret_val:
                scope_dict: Dict[str, dict] = {}
                ret_val[spec[0]] = scope_dict
            else:
                scope_dict = ret_val[spec[0]]

            scope_dict[spec[1]] = {
                "admin_channels": input[c]
            }

        return ret_val

    async def add_user(self, db_name: str, name: str, password: str, collection_access: dict) -> None:
        """
        Adds the specified user to a Sync Gateway database with the specified channel access

        :param db_name: The name of the Database to add the user to
        :param name: The username to add
        :param password: The password for the user that will be added
        :param collection_access: The collections that the user will have access to.  This needs to
            be formatted in the way Sync Gateway expects it, so if you are unsure use
            :func:`drop_bucket()<cbltest.api.syncgateway.SyncGateway.create_collection_access_dict>`
        """
        with self.__tracer.start_as_current_span("add_user", attributes={"cbl.user.name": name}):
            body = {
                "name": name,
                "password": password,
                "collection_access": collection_access
            }

            await self._send_request("put", f"/{db_name}/_user/{name}", JSONDictionary(body))

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
        with self.__tracer.start_as_current_span("add_role", attributes={"cbl.role.name": role}):
            body = {
                "name": role,
                "collection_access": collection_access
            }

            try:
                await self._send_request("post", f"/{db_name}/_role/", JSONDictionary(body))
            except CblSyncGatewayBadResponseError as e:
                if e.code == 409:
                    pass
                else:
                    raise

    async def assign_roles(self, db_name: str, name: str, roles: List[str]) -> None:
        """
        Assign the roles to a user.

        :param db_name: The name of the Database.
        :param name: The username to assign the roles to.
        :param roles: A list of roles to be assigned.
        """
        with self.__tracer.start_as_current_span("assign_role", attributes={"cbl.user.name": name}):
            body = { "admin_roles": roles }
            await self._send_request("put", f"/{db_name}/_user/{name}", JSONDictionary(body))

    def _analyze_dataset_response(self, response: list) -> None:
        assert isinstance(response, list), "Invalid bulk docs response (not a list)"
        typed_response = cast(list, response)
        for r in typed_response:
            info = cast(dict, r)
            assert isinstance(info, dict), "Invalid item inside bulk docs response list (not an object)"
            if "error" in info:
                raise CblSyncGatewayBadResponseError(info["status"],
                                                     f"At least one bulk docs insert failed ({info['error']})")

    async def load_dataset(self, db_name: str, path: Path) -> None:
        """
        Populates a given database name with the JSON contents at the specified path

        .. note:: The expected format of the JSON file is one JSON object per line, which will
            be interpreted as one document insert per line

        :param db_name: The name of the database to populate
        :param path: The path of the JSON file to use as input
        """
        with self.__tracer.start_as_current_span("load_dataset", attributes={"cbl.database.name": db_name,
                                                                             "cbl.dataset.path": str(path)}):
            last_scope: str = ""
            last_coll: str = ""
            collected: List[dict] = []
            with open(path, "r", encoding='utf8') as fin:
                json_line = fin.readline()
                while json_line:
                    json = cast(dict, loads(json_line))
                    assert isinstance(json, dict), f"Invalid entry in {path}!"
                    scope = cast(str, json["scope"])
                    collection = cast(str, json["collection"])
                    if last_scope != scope or last_coll != collection or len(collected) > 500:
                        if last_scope and last_coll and collected:
                            resp = await self._send_request("post", f"/{db_name}.{last_scope}.{last_coll}/_bulk_docs",
                                                            JSONDictionary({"docs": collected}))
                            self._analyze_dataset_response(resp)
                            collected.clear()

                    last_scope = scope
                    last_coll = collection
                    collected.append(json)
                    json_line = fin.readline()

            if collected:
                resp = await self._send_request("post", f"/{db_name}.{last_scope}.{last_coll}/_bulk_docs",
                                                JSONDictionary({"docs": collected}))
                self._analyze_dataset_response(cast(list, resp))

    async def get_all_documents(self, db_name: str, scope: str = "_default",
                                collection: str = "_default") -> AllDocumentsResponse:
        """
        Gets all the documents in the given collection from Sync Gateway (id and revid)
        
        :param db_name: The name of the Sync Gateway database to query
        :param scope: The scope to use when querying Sync Gateway
        :param collection: The collection to use when querying Sync Gateway
        """
        with self.__tracer.start_as_current_span("get_all_documents", attributes={"cbl.database.name": db_name,
                                                                                  "cbl.scope.name": scope,
                                                                                  "cbl.collection.name": collection}):
            resp = await self._send_request("get", f"/{db_name}.{scope}.{collection}/_all_docs?show_cv=true")
            assert isinstance(resp, dict)
            return AllDocumentsResponse(cast(dict, resp))

    async def update_documents(self, db_name: str, updates: List[DocumentUpdateEntry],
                               scope: str = "_default", collection: str = "_default") -> None:
        """
        Sends a list of documents to be updated on Sync Gateway

        :param db_name: The name of the DB endpoint to update
        :param updates: A list of updates to perform
        :param scope: The scope that the updates will be applied to (default '_default')
        :param collection: The collection that the updates will be applied to (default '_default')
        """
        with self.__tracer.start_as_current_span("update_documents", attributes={"cbl.database.name": db_name,
                                                                                 "cbl.scope.name": scope,
                                                                                 "cbl.collection.name": collection}):
            body = {
                "docs": list(u.to_json() for u in updates)
            }

            await self._send_request("post", f"/{db_name}.{scope}.{collection}/_bulk_docs",
                                     JSONDictionary(body))

    async def delete_document(self, doc_id: str, revid: str, db_name: str, scope: str = "_default",
                              collection: str = "_default") -> None:
        """
        Deletes a document from Sync Gateway

        :param doc_id: The document ID to delete
        :param revid: The revision ID of the existing document
        :param db_name: The name of the DB endpoint that the document exists in
        :param scope: The scope that the document exists in (default '_default')
        :param collection: The collection that the document exists in (default '_default')
        """
        with self.__tracer.start_as_current_span("delete_document", attributes={"cbl.database.name": db_name,
                                                                                "cbl.scope.name": scope,
                                                                                "cbl.collection.name": collection,
                                                                                "cbl.document.id": doc_id}):
            await self._send_request("delete", f"/{db_name}.{scope}.{collection}/{doc_id}",
                                     params={"rev": revid})

    async def purge_document(self, doc_id: str, db_name: str, scope: str = "_default",
                             collection: str = "_default") -> None:
        """
        Purges a document from Sync Gateway

        :param doc_id: The document ID to delete
        :param db_name: The name of the DB endpoint that the document exists in
        :param scope: The scope that the document exists in (default '_default')
        :param collection: The collection that the document exists in (default '_default')
        """
        with self.__tracer.start_as_current_span("purge_document", attributes={"cbl.database.name": db_name,
                                                                               "cbl.scope.name": scope,
                                                                               "cbl.collection.name": collection,
                                                                               "cbl.document.id": doc_id}):
            body = {
                doc_id: ["*"]
            }

            await self._send_request("post", f"/{db_name}.{scope}.{collection}/_purge",
                                     JSONDictionary(body))

    async def get_document(self, db_name: str, doc_id: str, scope: str = "_default", collection: str = "_default") -> \
            Optional[RemoteDocument]:
        """
        Gets a document from Sync Gateway

        :param db_name: The name of the DB endpoint that the document exists in
        :param doc_id: The document ID to get
        :param scope: The scope that the document exists in (default '_default')
        :param collection: The collection that the document exists in (default '_default')
        """
        with self.__tracer.start_as_current_span("get_document", attributes={"cbl.database.name": db_name,
                                                                             "cbl.scope.name": scope,
                                                                             "cbl.collection.name": collection,
                                                                             "cbl.document.id": doc_id}):
            response = await self._send_request("get", f"/{db_name}.{scope}.{collection}/{doc_id}")
            if not isinstance(response, dict):
                raise ValueError("Inappropriate response from sync gateway get /doc (not JSON)")

            cast_resp = cast(dict, response)
            if "error" in cast_resp:
                if cast_resp["reason"] == "missing" or cast_resp["reason"] == "deleted":
                    return None

                raise CblSyncGatewayBadResponseError(500,
                                                     f"Get doc from sync gateway had error '{cast_resp['reason']}'")

            return RemoteDocument(cast_resp)
