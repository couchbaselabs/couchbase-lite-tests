from abc import ABC, abstractmethod
from enum import Enum
from json import dumps
from typing import Dict, List
from uuid import UUID
from requests import Request
from varname import nameof

from ..logging import cbl_warning
from ..requests import TestServerRequest, TestServerRequestBody
from ..assertions import _assert_not_null
from urllib.parse import urljoin

class PostResetRequestBody(TestServerRequestBody):
    @property
    def datasets(self) -> Dict[str, List[str]]:
        return self.__datasets
    
    def __init__(self):
        super().__init__(1)
        self.__datasets = {}

    def add_dataset(self, name: str, result_db_names: List[str]):
        self.__datasets[name] = result_db_names

    def serialize(self) -> str:
        return f'{{"datasets": {dumps(self.__datasets)}}}'
    
class PostGetAllDocumentIDsRequestBody(TestServerRequestBody):
    @property
    def collections(self) -> List[str]:
        return self.__collections
    
    def __init__(self, database: str = None, collections: List[str] = None):
        super().__init__(1)
        self.database = database
        self.__collections = collections if collections is not None else []

    def serialize(self) -> str:
        raw = {"database": self.database, "collections": self.__collections}
        return dumps(raw)
    
class DatabaseUpdateType(Enum):
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    PURGE = "PURGE"

    def __str__(self) -> str:
        return self.value
    
class DatabaseUpdateEntry:
    @property
    def updated_properties(self) -> Dict[str, any]:
        if self.type != DatabaseUpdateType.UPDATE:
            return None
        
        return self.__updated_properties
    
    @property
    def removed_properties(self) -> Dict[str, any]:
        if self.type != DatabaseUpdateType.UPDATE:
            return None
        
        return self.__removed_properties
    
    def __init__(self, type: DatabaseUpdateType, collection: str, document_id: str) -> None:
        self.type = _assert_not_null(type, nameof(type))
        self.collection = _assert_not_null(collection, nameof(collection))
        self.document_id = _assert_not_null(document_id, nameof(document_id))
        self.__updated_properties = {}
        self.__removed_properties = {}

    def is_valid(self) -> bool:
        if self.type != DatabaseUpdateType.UPDATE:
            return True
        
        return len(self.__updated_properties) > 0 or len(self.__removed_properties) > 0
    
    def to_dict(self) -> Dict[str, any]:
        if not self.is_valid():
            return None
        
        raw = {
            "type": str(self.type),
            "collection": self.collection,
            "documentID": self.document_id
        }

        if len(self.__updated_properties) > 0:
            raw["updatedProperties"] = self.__updated_properties

        if len(self.__removed_properties) > 0:
            raw["removedProperties"] = self.__removed_properties

        return raw
    
class PostUpdateDatabaseRequestBody(TestServerRequestBody):
    @property
    def entries(self) -> List[DatabaseUpdateEntry]:
        return self.__entries
    
    def __init__(self, database: str = None, entries: List[DatabaseUpdateEntry] = None):
        super().__init__(1)
        self.database = database
        self.__entries = entries if entries is not None else []

    def serialize(self) -> str:
        raw = {
            "database": self.database
        }

        raw_entries = []

        for e in self.entries:
            raw_entry = e.to_dict()
            if raw_entry is None:
                cbl_warning("Skipping invalid DatabaseUpdateEntry in body serialization!")
                continue

            raw_entries.append(raw_entry)

        raw["updates"] = raw_entries
        return dumps(raw)
    
class SnapshotDocumentEntry:
    def __init__(self, collection: str, id: str):
        self.collection = collection
        self.id = id

    def to_dict(self):
        return {"collection": self.collection, "id": self.id}
    
class PostSnapshotDocumentsRequestBody(TestServerRequestBody):
    def entries(self) -> List[SnapshotDocumentEntry]:
        return self.__entries
    
    def __init__(self, entries: List[SnapshotDocumentEntry] = None):
        super().__init__(1)
        self.__entries = entries if entries is not None else []

    def serialize(self) -> str:
        raw = [e.to_dict() for e in self.entries] if self.entries is not None else []
        return dumps(raw)

class PostVerifyDocumentsRequestBody(TestServerRequestBody):
    @property
    def snapshot(self) -> str:
        return self.__snapshot
    
    @property
    def database(self) -> str:
        return self.__database
    
    def __init__(self, database: str, snapshot: str, changes: List[DatabaseUpdateEntry] = None):
        super().__init__(1)
        self.__snapshot = snapshot
        self.__database = database
        self.changes = changes

    def serialize(self) -> str:
        raw = {
            "snapshot": self.__snapshot,
            "database": self.__database,
            "changes": [c.to_dict() for c in self.changes] if self.changes is not None else []
        }

        return dumps(raw)
    
class ReplicatorType(Enum):
    PUSH = "push"
    PULL = "pull"
    PUSH_AND_PULL = "pushAndPull"

    def __str__(self) -> str:
        return self.value
    
class ReplicatorAuthenticator(ABC):
    @property
    def type(self) -> str:
        return self.__type

    def __init__(self, type: str) -> None:
        self.__type = type

    @abstractmethod
    def to_dict(self) -> dict:
        return None
    
class ReplicatorBasicAuthenticator(ReplicatorAuthenticator):
    @property
    def username(self) -> str:
        return self.__username
    
    def password(self) -> str:
        return self.__password
    
    def __init__(self, username: str, password: str) -> None:
        super().__init__("basic")
        self.__username = username
        self.__password = password

    def to_dict(self) -> dict:
        return {
            "type": "basic",
            "username": self.__username,
            "password": self.__password
        }
    
class ReplicatorSessionAuthenticator(ReplicatorAuthenticator):
    @property 
    def session_id(self) -> str:
        return self.__session_id
    
    @property
    def cookie_name(self) -> str:
        return self.__cookie_name
    
    def __init__(self, session_id: str, cookie_name: str = "SyncGatewaySession") -> None:
        super().__init__("session")
        self.__session_id = session_id
        self.__cookie_name = cookie_name

    def to_dict(self) -> dict:
        return {
            "type": "session",
            "sessionID": self.__session_id,
            "cookieName": self.__cookie_name
        }
    
class ReplicatorPushFilterParameters:
    def __init__(self) -> None:
        self.document_ids: List[str] = None

    def to_dict(self) -> dict:
        if self.document_ids is None:
            return None
        
        return {
            "documentIDs": self.document_ids
        }
    
class ReplicatorPushFilter:
    @property
    def name(self) -> str:
        return self.__name
    
    def __init__(self, name: str) -> None:
        self.__name = name
        self.parameters: ReplicatorPushFilterParameters = None

    def to_dict(self) -> dict:
        ret_val = {"name": self.name}
        if self.parameters is not None:
            ret_val["params"] = self.parameters.to_dict()

class ReplicatorCollectionEntry:
    @property
    def collection(self) -> str:
        return self.__collection
    
    def __init__(self, collection: str) -> None:
        self.__collection = collection
        self.channels: List[str] = []
        self.document_ids: List[str] = []
        self.push_filter: ReplicatorPushFilter = None
    
class PostStartReplicatorRequestBody(TestServerRequestBody):
    @property
    def database(self) -> str:
        return self.__database
    
    @property
    def endpoint(self) -> str:
        return self.__endpoint

    def __init__(self, database: str, endpoint: str):
        super().__init__(1)
        self.__database = database
        self.__endpoint = endpoint
        self.replicatorType: ReplicatorType = ReplicatorType.PUSH_AND_PULL
        self.continuous: bool = False
        self.authenticator: ReplicatorAuthenticator = None
        self.reset: bool = False
        self.collections: List[ReplicatorCollectionEntry] = None

    def serialize(self) -> str:
        raw = {
            "database": self.__database,
            "endpoint": self.__endpoint,
            "replicatorType": str(self.replicatorType),
            "continuous": self.continuous,
            "reset": self.reset
        }

        if self.collections is not None:
            raw["collections"] = [c.to_dict() for c in self.collections]

        if self.authenticator is not None:
            raw["authenticator"] = self.authenticator.to_dict()

        return dumps(raw)
    
class PostGetReplicatorStatusRequestBody(TestServerRequestBody):
    @property
    def id(self) -> str:
        return self.__id
    
    def __init__(self, id: str):
        super().__init__(1)
        self.__id = id

    def serialize(self) -> str:
        return {"id": self.__id}
    
class PostResetRequest(TestServerRequest):
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "reset", PostResetRequestBody, payload=payload)

class PostGetAllDocumentIDsRequest(TestServerRequest):
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "getAllDocumentIDs", PostGetAllDocumentIDsRequestBody, payload=payload)

class PostUpdateDatabaseRequest(TestServerRequest):
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "updateDatabase", PostUpdateDatabaseRequestBody, payload=payload)

class PostSnapshotDocumentsRequest(TestServerRequest):
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "snapshotDocuments", PostSnapshotDocumentsRequestBody, payload=payload)
    
class PostVerifyDocumentsRequest(TestServerRequest):
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "verifyDocuments", PostVerifyDocumentsRequestBody, payload=payload)

class PostStartReplicatorRequest(TestServerRequest):
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "startReplicator", PostStartReplicatorRequestBody, payload=payload)

class PostGetReplicatorStatusRequest(TestServerRequest):
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "getReplicatorStatus", PostGetReplicatorStatusRequestBody, payload=payload)