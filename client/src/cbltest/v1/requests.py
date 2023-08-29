from enum import Enum
from json import dumps
from typing import Dict, List, cast, Any, Optional
from uuid import UUID
from varname import nameof

from cbltest.logging import cbl_warning
from cbltest.requests import TestServerRequest, TestServerRequestBody
from cbltest.assertions import _assert_not_null
from cbltest.api.replicator_types import ReplicatorAuthenticator, ReplicatorCollectionEntry, ReplicatorType
from cbltest.api.database_types import SnapshotDocumentEntry
from cbltest.api.jsonserializable import JSONSerializable

# Some conventions that are followed in this file are that all request classes that
# will be sent to the test server are classes that end in 'Request'.  Their bodies
# are the same class name, except with 'Body' appended.  For example, PostResetRequest
# will accept PostResetRequestBody.  The type is generic in the constructor in order
# to facilitate easy API versioning, but an assert will check the type is correct.

# All other classes support the RequestBody classes

class PostResetRequestBody(TestServerRequestBody):
    """
    The body of a POST /reset request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

        {
            "datasets": {
                "catalog": [
                    "db1",
                    "db2"
                ]
            }
        }
    """

    @property
    def datasets(self) -> Dict[str, List[str]]:
        """
        Gets the datasets contained in the :class:`PostResetRequestBody`
        """
        return self.__datasets
    
    def __init__(self):
        super().__init__(1)
        self.__datasets = {}

    def add_dataset(self, name: str, result_db_names: List[str]) -> None:
        """
        Add a dataset entry to the :class:`PostResetRequestBody`

        :param name: The name of the dataset to add (i.e. catalog in the class docs example)
        :param result_db_names: A list of databases to populate with the data from the dataset
        """
        self.__datasets[name] = result_db_names

    def to_json(self) -> Any:
        return {"datasets": self.__datasets}
    
class PostGetAllDocumentsRequestBody(TestServerRequestBody):
    """
    The body of a POST /getAllDocuments request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

        {
            "database": "db1",
            "collections": [
                "catalog.cloths",
                "catalog.shoes"
            ]
        }
    """

    @property
    def collections(self) -> List[str]:
        """
        Gets the collections specified in the :class:`PostGetAllDocumentsRequestBody`
        """
        return self.__collections
    
    def __init__(self, database: str, *collections: str):
        super().__init__(1)
        _assert_not_null(database, nameof(database))
        self.database = database
        """The database to get document IDs from"""

        self.__collections = list(collections) if collections is not None else []

    def to_json(self) -> Any:
        return {"database": self.database, "collections": self.__collections}
    
class DatabaseUpdateType(Enum):
    """
    An enum specifying a type of database update to perform
    """

    UPDATE = "UPDATE"
    """Modifies the content of a given document"""

    DELETE = "DELETE"
    """Deletes a given document using the deletion API"""

    PURGE = "PURGE"
    """Purges a given document using the purge API"""

    def __str__(self) -> str:
        return self.value
    
class DatabaseUpdateEntry(JSONSerializable):
    """
    A class representing a single update to perform on a database.  These entries
    can be passed via :class:`PostUpdateDatabaseRequestBody` to perform batch operations
    """
    
    def __init__(self, type: DatabaseUpdateType, collection: str, document_id: str,
                 updated_properties: Optional[List[Dict[str, Any]]] = None, removed_properties: Optional[List[str]] = None) -> None:
        self.type: DatabaseUpdateEntry = cast(DatabaseUpdateEntry, _assert_not_null(type, nameof(type)))
        """The type of update to be performed"""

        self.collection: str = cast(str, _assert_not_null(collection, nameof(collection)))
        """The collection to that the document to be modified belongs to"""

        self.document_id: str = cast(str, _assert_not_null(document_id, nameof(document_id)))
        """The ID of the document to be modified"""

        self.updated_properties: Optional[List[Dict[str, Any]]] = updated_properties
        """
        The properties to be updated on a given document. 
        Note that to remove a property, `removed_properties` must be used.
        Each entry in the list is a dictionary with keypath keys and values
        to be edited.
        """

        self.removed_properties: Optional[List[str]] = removed_properties
        """
        The keypaths to be removed on a given document. 
        It has no meaning if `type` is not `UPDATE`
        """

    def is_valid(self) -> bool:
        """
        Returns `True` if this update is valid, or `False` if it is not.  An update is
        considered valid if it is a PURGE / DELETE, or if it is an UPDATE with at least
        one updated or one removed property
        """
        if self.type != DatabaseUpdateType.UPDATE:
            return True
        
        if self.updated_properties is not None:
            return len(self.updated_properties) > 0
        
        return len(self.removed_properties) > 0 if self.removed_properties is not None else False
    
    def to_json(self) -> Any:
        if not self.is_valid():
            return None
        
        raw = {
            "type": str(self.type),
            "collection": self.collection,
            "documentID": self.document_id
        }

        if self.type != DatabaseUpdateType.UPDATE:
            return raw

        if self.updated_properties is not None and len(self.updated_properties) > 0:
            raw["updatedProperties"] = self.updated_properties

        if self.removed_properties is not None and len(self.removed_properties) > 0:
            raw["removedProperties"] = self.removed_properties

        return raw
    
class PostUpdateDatabaseRequestBody(TestServerRequestBody):
    """
    The body of a POST /updateDatabase request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """
    
    def __init__(self, database: Optional[str] = None, updates: Optional[List[DatabaseUpdateEntry]] = None):
        super().__init__(1)
        self.database = database
        """The database that the updates will be applied to once executed"""

        self.updates = updates
        """
        The list of updates on the :class:`PostUpdateDatabaseRequestBody`.
        This list can be directly added to or removed from.
        """

    def to_json(self) -> Any:
        raw: Dict[str, Any] = {
            "database": self.database
        }

        raw_entries = []

        if self.updates is not None:
            for e in cast(List[DatabaseUpdateEntry], self.updates):
                raw_entry = e.to_json()
                if raw_entry is None:
                    cbl_warning("Skipping invalid DatabaseUpdateEntry in body serialization!")
                    continue

                raw_entries.append(raw_entry)

        raw["updates"] = raw_entries
        return raw
    
class PostSnapshotDocumentsRequestBody(TestServerRequestBody):
    """
    The body of a POST /snapshotDocuments request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

        database: "db1",
        documents: [
            {
                "collection": "store.cloths",
                "id": "doc1"
            }
        ]
    """

    @property
    def database(self) -> str:
        """Gets the database that this snapshot will be taken from"""
        return self.__database

    def entries(self) -> List[SnapshotDocumentEntry]:
        """
        Gets the (mutable) list of documents to be snapshotted.  This list can be
        directly added to or removed from
        """
        return self.__entries
    
    def __init__(self, database: str, entries: Optional[List[SnapshotDocumentEntry]] = None):
        super().__init__(1)
        self.__database = database
        self.__entries = entries if entries is not None else []

    def to_json(self) -> Any:
        return {
            "database": self.__database,
            "documents": [e.to_json() for e in self.__entries]
        }

class PostVerifyDocumentsRequestBody(TestServerRequestBody):
    """
    The body of a POST /verifyDocuments request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

        {
            "database": "db1",
            "snapshot": "123e0000-e89b-12d3-a456-426614174000",
            "changes": [
                {
                    "type": "UPDATE",
                    "collection": "store.cloths",
                    "documentID": "doc1",
                    "updatedProperties": {
                        "name": "Cool Sport Tech Fleece Shirt"
                    },
                    "removedProperties": {
                        "vendor": {
                        "info": null
                        }
                    }
                }
            ]
        }
    """

    @property
    def snapshot(self) -> str:
        """Gets the snapshot used as a baseline for the comparison"""
        return self.__snapshot
    
    @property
    def database(self) -> str:
        """Gets the database that will be used to retrieve the current state"""
        return self.__database
    
    def __init__(self, database: str, snapshot: str, changes: Optional[List[DatabaseUpdateEntry]] = None):
        super().__init__(1)
        self.__snapshot = snapshot
        self.__database = database
        self.changes = changes
        """A list of changes to verify in the database (as compared to the `snapshot`)"""

    def to_json(self) -> Any:
        return {
            "snapshot": self.__snapshot,
            "database": self.__database,
            "changes": [c.to_json() for c in self.changes] if self.changes is not None else []
        }
    
class PostStartReplicatorRequestBody(TestServerRequestBody):
    """
    The body of a POST /startReplicator request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

        {
            "config": {
                "database": "db1",
                "collections": [
                {
                    "names": [
                        "store.cloths",
                        "store.shoes"
                    ],
                    "channels": [
                        "A",
                        "B"
                    ],
                    "documentIDs": [
                        "doc1",
                        "doc2"
                    ],
                    "pushFilter": {
                        "name": "documentIDs",
                        "params": {
                            "documentIDs": [
                            "doc1",
                            "doc2"
                            ]
                        }
                    }
                }
                ],
                "endpoint": "wss://localhost:4985/db",
                "replicatorType": "pushAndPull",
                "continuous": true,
                "authenticator": {
                    "type": "BASIC",
                    "username": "user1",
                    "password": "p@ssw0rd"
                },
                "enableDocumentListener": false,
                "enableAutoPurge": true
            },
            "reset": false
        }
    """

    @property
    def database(self) -> str:
        """Gets the local database that this replicator will be created for"""
        return self.__database
    
    @property
    def endpoint(self) -> str:
        """Gets the remote URL endpoint that this replicator will replicate to"""
        return self.__endpoint

    def __init__(self, database: str, endpoint: str):
        super().__init__(1)
        self.__database = database
        self.__endpoint = endpoint
        self.replicatorType: ReplicatorType = ReplicatorType.PUSH_AND_PULL
        """The direction to be performed during the replication"""

        self.continuous: bool = False
        """Whether or not this is a continuous replication (i.e. doesn't stop when finished
        with its initial changes)"""

        self.authenticator: Optional[ReplicatorAuthenticator] = None
        """The authenticator to use to perform authentication with the remote"""

        self.reset: bool = False
        """Whether or not to start the replication over from the beginning"""

        self.collections: List[ReplicatorCollectionEntry] = []
        """The per-collection configuration to use inside the replication"""

        self.enableDocumentListener: bool = False
        """If set to True, calls to getReplicatorStatus will return a list of document events"""

        self.enableAutoPurge: bool = True
        """If set to True (default), the replicator will automatically purge documents on access loss"""

    def to_json(self) -> Any:
        """Serializes the :class:`PostStartReplicatorRequestBody` to a JSON string"""
        raw = {
            "database": self.__database,
            "endpoint": self.__endpoint,
            "replicatorType": str(self.replicatorType),
            "continuous": self.continuous,
            "enableDocumentListener": self.enableDocumentListener,
            "enableAutoPurge": self.enableAutoPurge
        }

        if self.collections is not None:
            raw["collections"] = [c.to_json() for c in self.collections]

        if self.authenticator is not None:
            raw["authenticator"] = self.authenticator.to_json()

        ret_val = {
            "config": raw,
            "reset": self.reset
        }
        
        return ret_val
    
class PostGetReplicatorStatusRequestBody(TestServerRequestBody):
    """
    The body of a POST /getReplicatorStatus request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

        {
            "id": "123e4567-e89b-12d3-a456-426614174000"
        }
    """

    @property
    def id(self) -> str:
        """Gets the ID of the replicator to check the status for"""
        return self.__id
    
    def __init__(self, id: str):
        super().__init__(1)
        self.__id = id

    def to_json(self) -> Any:
        """Serializes the :class:`PostGetReplicatorStatusRequestBody` to a JSON string"""
        return {"id": self.__id}
    
class PostPerformMaintenanceRequestBody(TestServerRequestBody):
    """
    The body of a POST /performMaintenance request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

        {
            "database": "db1",
            "maintenanceType": "compact"
        }
    """

    @property
    def database(self) -> str:
        """Returns the database that this operation will be performed on"""
        return self.__db
    
    @property
    def type(self) -> str:
        """Returns the type of maintenance to perform"""
        return self.__type
    
    def __init__(self, db: str, type: str):
        super().__init__(1)
        self.__db = db
        self.__type = type

    def to_json(self) -> Any:
        return {"database": self.__db, "maintenanceType": self.__type}

# Below this point are all of the concrete test server request types
# Remember the note from the top of this file about the actual type of the payload
class PostResetRequest(TestServerRequest):
    """
    A POST /reset request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "reset", PostResetRequestBody, payload=payload)

class PostGetAllDocumentsRequest(TestServerRequest):
    """
    A POST /getAllDocuments request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "getAllDocuments", PostGetAllDocumentsRequestBody, payload=payload)

class PostUpdateDatabaseRequest(TestServerRequest):
    """
    A POST /updateDatabase request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "updateDatabase", PostUpdateDatabaseRequestBody, payload=payload)

class PostSnapshotDocumentsRequest(TestServerRequest):
    """
    A POST /snapshotDocuments request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "snapshotDocuments", PostSnapshotDocumentsRequestBody, payload=payload)
    
class PostVerifyDocumentsRequest(TestServerRequest):
    """
    A POST /verifyDocuments request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "verifyDocuments", PostVerifyDocumentsRequestBody, payload=payload)

class PostStartReplicatorRequest(TestServerRequest):
    """
    A POST /startReplicator request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "startReplicator", PostStartReplicatorRequestBody, payload=payload)

class PostGetReplicatorStatusRequest(TestServerRequest):
    """
    A POST /getReplicatorStatus request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "getReplicatorStatus", PostGetReplicatorStatusRequestBody, payload=payload)

class PostPerformMaintenanceRequest(TestServerRequest):
    """
    A POST /performMaintenance request as specified in version 1 of the 
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """
    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "performMaintenance", PostPerformMaintenanceRequestBody, payload=payload)