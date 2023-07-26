from json import dumps, loads
from pathlib import Path
from typing import Dict, List, cast, Any, Optional
from urllib.parse import urljoin
from aiohttp import ClientSession, BasicAuth
from varname import nameof

from cbltest.httplog import get_next_writer
from cbltest.assertions import _assert_not_null
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.jsonserializable import JSONSerializable, JSONDictionary
    
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

    def add_collection(self, collection_name: str) -> None:
        if collection_name in self.__collections:
            raise ValueError(f"{collection_name} already exists in this map")
        
        self.__collections[collection_name] = {}

    def to_json(self) -> Any:
        return {"collections": self.__collections}

class PutDatabasePayload(JSONSerializable):
    """
    A class containing configuration options for a Sync Gateway database endpoint
    """
    def __init__(self, bucket: str):
        _assert_not_null(bucket, nameof(bucket))
        self.num_index_replicas: int = 0
        """The number of index replicas to use"""
        self.bucket = bucket
        """The bucket name in the backing Couchbase Server"""

        self.__scopes: Dict[str, _CollectionMap] = {}

    def scopes(self) -> List[str]:
        return list(self.__scopes.keys())
    
    def collections(self, scope: str) -> List[str]:
        map = self.__scopes.get(scope)
        if not map:
            raise KeyError(f"No collections present for {scope}")
        
        return map.collections

    def add_collection(self, scope_name: str = "_default", collection_name: str = "_default") -> None:
        """
        Adds a collection to the configuration of the database (must exist on Couchbase Server).
        The scope name and collection name both default to "_default".

        :param scope_name: The name of the scope in which the collection resides
        :param collection_name: The name of the collection to retrieve data from
        """
        _assert_not_null(scope_name, nameof(scope_name))
        col_map = self.__scopes.get(scope_name, _CollectionMap(collection_name))
        self.__scopes[scope_name] = col_map
        col_map.add_collection(collection_name)

    def to_json(self) -> Any:
        scopes: dict = {}
        ret_val = {
            "scopes": scopes,
            "bucket": self.bucket,
            "num_index_replicas": self.num_index_replicas
        }

        for s in self.__scopes:
            scopes[s] = self.__scopes[s].to_json()

        return ret_val
    
class _AllDocumentsResponseRow:
    @property
    def key(self) -> str:
        return self.__key
    
    @property
    def id(self) -> str:
        return self.__id
    
    @property
    def revid(self) -> str:
        return self.__revid
    
    def __init__(self, key: str, id: str, revid: str) -> None:
        self.__key = key
        self.__id = id
        self.__revid = revid
    
class AllDocumentsResponse:
    @property 
    def rows(self) -> List[_AllDocumentsResponseRow]:
        return self.__rows
    
    def __len__(self) -> int:
        return self.__len
    
    def __init__(self, input: dict) -> None:
        self.__len = input["total_rows"]
        self.__rows: List[_AllDocumentsResponseRow] = []
        for row in input["rows"]:
            self.__rows.append(_AllDocumentsResponseRow(row["key"], row["id"], row["value"]["rev"]))

class SyncGateway:
    """
    A class for interacting with a given Sync Gateway instance
    """
    def __init__(self, url: str, username: str, password: str, port: int = 4984, admin_port: int = 4985, 
                 secure: bool = False):
        scheme = "https://" if secure else "http://"
        ws_scheme = "wss://" if secure else "ws://"
        self.__admin_session = ClientSession(f"{scheme}{url}:{admin_port}", auth=BasicAuth(username, password, "ascii"))
        self.__admin_url = f"{scheme}{url}:{admin_port}"
        self.__replication_url = f"{ws_scheme}{url}:{port}"

    async def _send_request(self, method: str, path: str, payload: Optional[JSONSerializable] = None) -> Any:
        headers = {"Content-Type": "application/json"} if payload is not None else None
        data = None if payload is None else payload.serialize()
        writer = get_next_writer()
        writer.write_begin(f"Sync Gateway [{self.__admin_url}] -> {method.upper()} {path}", data if data is not None else "")
        resp = await self.__admin_session.request(method, path, data=data, headers=headers)
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
        
    def replication_url(self, db_name: str):
        """
        Gets the replicator URL (ws://xxx) for a given db
        
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
        await self._send_request("put", f"/{db_name}", payload)

    async def delete_database(self, db_name: str) -> None:
        """
        Deletes a database from Sync Gateway's configuration.  

        .. warning:: This will not delete the data from the Couchbase Server bucket.  
            To delete the data see the 
            :func:`drop_bucket()<cbltest.api.couchbaseserver.CouchbaseServer.drop_bucket>` function

        :param db_name: The name of the Database to delete
        """
        await self._send_request("delete", f"/{db_name}")

    async def add_user(self, db_name: str, name: str, password: str, channel_access: Dict[str, List[str]]) -> None:
        """
        Adds the specified user to a Sync Gateway database with the specified channel access

        :param db_name: The name of the Database to add the user to
        :param name: The username to add
        :param password: The password for the user that will be added
        :param channel_access: The channels that the user will have access to, as a dictionary 
            keyed by collection containing an array of channels
        """
        collection_access: Dict[str, dict] = {}
        body = {
            "name": name,
            "password": password,
            "collection_access": collection_access
        }

        if channel_access is not None:
            for coll in channel_access:
                split = coll.split(".")
                scope = split[0] if len(split) > 1 else "_default"
                collection = split[1] if len(split) > 1 else split[0]
                if scope not in collection_access:
                    collection_access[scope] = {}

                collection_access[scope][collection] = {"admin_channels": channel_access[coll]}

        await self._send_request("post", f"/{db_name}/_user/", JSONDictionary(body))

    def _analyze_dataset_response(self, response: list) -> None:
        assert isinstance(response, list), "Invalid bulk docs response (not a list)"
        typed_response = cast(list, response)
        for r in typed_response:
            info = cast(dict, r)
            assert isinstance(info, dict), "Invalid item inside bulk docs response list (not an object)"
            if "error" in info:
                raise CblSyncGatewayBadResponseError(info["status"], f"At least one bulk docs insert failed ({info['error']})")

    async def load_dataset(self, db_name: str, path: Path) -> None:
        """
        Populates a given database name with the JSON contents at the specified path

        .. note:: The expected format of the JSON file is one JSON object per line, which will
            be interpreted as one document insert per line

        :param db_name: The name of the database to populate
        :param path: The path of the JSON file to use as input
        """
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
                    if last_scope and last_coll:
                        resp = await self._send_request("post", f"/{db_name}.{last_scope}.{last_coll}/_bulk_docs", 
                                                        JSONDictionary({"docs": collected}))
                        self._analyze_dataset_response(resp)
                        collected.clear()

                last_scope = scope
                last_coll = collection
                collected.append(json)
                json_line = fin.readline()

        resp = await self._send_request("post", f"/{db_name}.{last_scope}.{last_coll}/_bulk_docs", 
                                        JSONDictionary({"docs": collected}))
        self._analyze_dataset_response(cast(list, resp))

    async def get_all_documents(self, db_name: str, scope: str = "_default", collection: str = "_default") -> AllDocumentsResponse:
        resp = await self._send_request("get", f"/{db_name}.{scope}.{collection}/_all_docs")
        assert isinstance(resp, dict)
        return AllDocumentsResponse(cast(dict, resp))

