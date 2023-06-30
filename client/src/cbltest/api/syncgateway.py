from json import dumps
from typing import Dict, List
from urllib.parse import urljoin
from aiohttp import ClientSession, BasicAuth
from varname import nameof

from cbltest.httplog import get_next_writer
from cbltest.assertions import _assert_not_null
from cbltest.api.error import CblSyncGatewayBadResponseError
from cbltest.api.jsonserializable import JSONSerializable
    
class _CollectionMap(JSONSerializable):
    @property
    def scope_name(self) -> str:
        return self.__scope_name
    
    def __init__(self, scope_name: str) -> None:
        _assert_not_null(scope_name, nameof(scope_name))
        self.__scope_name = scope_name
        self.__collections: Dict[str, dict] = {}

    def add_collection(self, collection_name: str) -> None:
        if collection_name in self.__collections:
            raise ValueError(f"{collection_name} already exists in this map")
        
        self.__collections[collection_name] = {}

    def to_json(self) -> any:
        return {"collections": self.__collections}
    
class _GuestEntry(JSONSerializable):
    def __init__(self, admin_channels: List[str] = ["*"]):
        self.__admin_channels = admin_channels

    def to_json(self) -> any:
        return {"disabled": False, "admin_channels": self.__admin_channels}

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
        self.__guest: _GuestEntry = None

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

    def enable_guest(self, admin_channels: List[str] = ["*"]) -> None:
        """
        Turns on GUEST user access for this database configuration

        :param admin_channels: The channels that the guest user will have access to by default
        (if not specified, all channels are granted)
        """
        self.__guest = _GuestEntry(admin_channels)

    def to_json(self) -> any:
        ret_val = {
            "scopes": {},
            "bucket": self.bucket,
            "num_index_replicas": self.num_index_replicas
        }

        for s in self.__scopes:
            ret_val["scopes"][s] = self.__scopes[s].to_json()

        if self.__guest is not None:
            ret_val["guest"] = self.__guest.to_json()

        return ret_val

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

    async def _send_request(self, method: str, path: str, payload: JSONSerializable = None) -> None:
        headers = {"Content-Type": "application/json"} if payload is not None else None
        data = None if payload is None else payload.serialize()
        writer = get_next_writer()
        writer.write_begin(f"Sync Gateway [{self.__admin_url}] -> {method.upper()} {path}", data if data is not None else "")
        resp = await self.__admin_session.request(method, path, data=data, headers=headers)
        if resp.content_type.startswith("application/json"):
            data = dumps(await resp.json(), indent=2)
        else:
            data = await resp.text()
        writer.write_end(f"Sync Gateway [{self.__admin_url}] <- {method.upper()} {path} {resp.status}", data)
        if not resp.ok:
            raise CblSyncGatewayBadResponseError(resp.status, f"{method} {path} returned {resp.status}")
        
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
        Deletes a database from Sync Gateway's configuration.  Note that this does NOT
        delete the data from the backing bucket

        :param db_name: The name of the Database to delete
        """
        await self._send_request("delete", f"/{db_name}")
