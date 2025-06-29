import base64
from enum import Enum
from typing import Any, cast
from uuid import UUID

from cbltest.api.database_types import DocumentEntry
from cbltest.api.jsonserializable import JSONSerializable
from cbltest.api.multipeer_replicator_types import MultipeerReplicatorAuthenticator
from cbltest.api.replicator_types import (
    ReplicatorAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.api.x509_certificate import CertKeyPair
from cbltest.assertions import _assert_not_null
from cbltest.logging import cbl_warning
from cbltest.requests import TestServerRequest, TestServerRequestBody

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
            "databases": {
                "db1": {},
                "db2": {
                    "collections": [
                        "_default.employees"
                    ]
                },
                "db3": {
                    "dataset": "travel"
                }
            }
        }
    """

    def __init__(self, name: str | None = None):
        super().__init__(1)
        self.__test_name = name
        self.__databases: dict[str, dict[str, Any]] = {}

    def add_dataset(self, name: str, result_db_names: list[str]) -> None:
        """
        Add a dataset entry to the :class:`PostResetRequestBody`

        :param name: The name of the dataset to add (i.e. catalog in the class docs example)
        :param result_db_names: A list of databases to populate with the data from the dataset
        """
        for db_name in result_db_names:
            self.__databases[db_name] = {"dataset": name}

    def add_empty(
        self, result_db_names: list[str], collections: list[str] | None = None
    ):
        """
        Add an empty database entry to the :class`PostResetRequestBody`

        :param result_db_names: A list of databases to create
        :param collections: Collections to add to the databases after creation
        """
        for db_name in result_db_names:
            entry = {} if collections is None else {"collections": collections}
            self.__databases[db_name] = entry

    def to_json(self) -> dict[str, Any]:
        json: dict[str, Any] = {"databases": self.__databases}
        if self.__test_name:
            json["test"] = self.__test_name

        return json


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
    def collections(self) -> list[str]:
        """
        Gets the collections specified in the :class:`PostGetAllDocumentsRequestBody`
        """
        return self.__collections

    def __init__(self, database: str, *collections: str):
        super().__init__(1)
        _assert_not_null(database, "database")
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

    def __init__(
        self,
        type: DatabaseUpdateType,
        collection: str,
        document_id: str,
        updated_properties: list[dict[str, Any]] | None = None,
        removed_properties: list[str] | None = None,
        new_blobs: dict[str, str] | None = None,
    ) -> None:
        self.type: DatabaseUpdateEntry = cast(
            DatabaseUpdateEntry, _assert_not_null(type, "type")
        )
        """The type of update to be performed"""

        self.collection: str = cast(str, _assert_not_null(collection, "collection"))
        """The collection to that the document to be modified belongs to"""

        self.document_id: str = cast(str, _assert_not_null(document_id, "document_id"))
        """The ID of the document to be modified"""

        self.updated_properties: list[dict[str, Any]] | None = updated_properties
        """
        The properties to be updated on a given document. 
        Note that to remove a property, `removed_properties` must be used.
        Each entry in the list is a dictionary with keypath keys and values
        to be edited.
        """

        self.removed_properties: list[str] | None = removed_properties
        """
        The keypaths to be removed on a given document. 
        It has no meaning if `type` is not `UPDATE`
        """

        self.new_blobs: dict[str, str] | None = new_blobs
        """
        The keypaths to add blobs to, with the values being the name of the blob to add
        according to the blob dataset
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

        if self.new_blobs is not None:
            return len(self.new_blobs) > 0

        return (
            len(self.removed_properties) > 0
            if self.removed_properties is not None
            else False
        )

    def to_json(self) -> Any:
        if not self.is_valid():
            return None

        raw = {
            "type": str(self.type),
            "collection": self.collection,
            "documentID": self.document_id,
        }

        if self.type != DatabaseUpdateType.UPDATE:
            return raw

        if self.updated_properties is not None and len(self.updated_properties) > 0:
            raw["updatedProperties"] = self.updated_properties

        if self.removed_properties is not None and len(self.removed_properties) > 0:
            raw["removedProperties"] = self.removed_properties

        if self.new_blobs is not None and len(self.new_blobs) > 0:
            raw["updatedBlobs"] = self.new_blobs

        return raw


class PostUpdateDatabaseRequestBody(TestServerRequestBody):
    """
    The body of a POST /updateDatabase request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(
        self,
        database: str | None = None,
        updates: list[DatabaseUpdateEntry] | None = None,
    ):
        super().__init__(1)
        self.database = database
        """The database that the updates will be applied to once executed"""

        self.updates = updates
        """
        The list of updates on the :class:`PostUpdateDatabaseRequestBody`.
        This list can be directly added to or removed from.
        """

    def to_json(self) -> Any:
        raw: dict[str, Any] = {"database": self.database}

        raw_entries = []

        if self.updates is not None:
            for e in cast(list[DatabaseUpdateEntry], self.updates):
                raw_entry = e.to_json()
                if raw_entry is None:
                    cbl_warning(
                        "Skipping invalid DatabaseUpdateEntry in body serialization!"
                    )
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

    def entries(self) -> list[DocumentEntry]:
        """
        Gets the (mutable) list of documents to be snapshotted.  This list can be
        directly added to or removed from
        """
        return self.__entries

    def __init__(self, database: str, entries: list[DocumentEntry] | None = None):
        super().__init__(1)
        self.__database = database
        self.__entries = entries if entries is not None else []

    def to_json(self) -> Any:
        return {
            "database": self.__database,
            "documents": [e.to_json() for e in self.__entries],
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

    def __init__(
        self,
        database: str,
        snapshot: str,
        changes: list[DatabaseUpdateEntry] | None = None,
    ):
        super().__init__(1)
        self.__snapshot = snapshot
        self.__database = database
        self.changes = changes
        """A list of changes to verify in the database (as compared to the `snapshot`)"""

    def to_json(self) -> Any:
        return {
            "snapshot": self.__snapshot,
            "database": self.__database,
            "changes": [c.to_json() for c in self.changes]
            if self.changes is not None
            else [],
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
                "enableAutoPurge": true,
                "pinnedServerCert": "..."
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

        self.authenticator: ReplicatorAuthenticator | None = None
        """The authenticator to use to perform authentication with the remote"""

        self.reset: bool = False
        """Whether or not to start the replication over from the beginning"""

        self.collections: list[ReplicatorCollectionEntry] = []
        """The per-collection configuration to use inside the replication"""

        self.enableDocumentListener: bool = False
        """If set to True, calls to getReplicatorStatus will return a list of document events"""

        self.enableAutoPurge: bool = True
        """If set to True (default), the replicator will automatically purge documents on access loss"""

        self.pinnedServerCert: str | None = None
        """The PEM representation of the TLS certificate that the remote is using"""

    def to_json(self) -> Any:
        """Serializes the :class:`PostStartReplicatorRequestBody` to a JSON string"""
        raw = {
            "database": self.__database,
            "endpoint": self.__endpoint,
            "replicatorType": str(self.replicatorType),
            "continuous": self.continuous,
            "enableDocumentListener": self.enableDocumentListener,
            "enableAutoPurge": self.enableAutoPurge,
            "pinnedServerCert": self.pinnedServerCert,
        }

        if self.collections is not None:
            raw["collections"] = [c.to_json() for c in self.collections]

        if self.authenticator is not None:
            raw["authenticator"] = self.authenticator.to_json()

        ret_val = {"config": raw, "reset": self.reset}

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


class PostNewSessionRequestBody(TestServerRequestBody):
    """
    The body of a POST /newSession request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

        {
            "id": <guid>
            "logging": {
                "url": "localhost:8180",
                "tag": "test-server[0]
            }
        }
    """

    @property
    def url(self) -> str | None:
        """Returns the URL of the LogSlurp server"""
        return self.__url

    @property
    def id(self) -> str:
        """Returns the ID of the log to interact with on the LogSlurp server"""
        return self.__id

    @property
    def tag(self) -> str | None:
        """Returns the tag to use to print in log statements from this particular remote"""
        return self.__tag

    def __init__(self, id: str, dataset_version: str, url: str | None, tag: str | None):
        super().__init__(1)
        self.__url = url
        self.__dataset_version = dataset_version
        self.__id = id
        self.__tag = tag

    def to_json(self) -> Any:
        json: dict[str, Any] = {
            "id": self.__id,
            "dataset_version": self.__dataset_version,
        }
        if self.__url is not None and self.__tag is not None:
            json["logging"] = {"url": self.__url, "tag": self.__tag}

        return json


class PostRunQueryRequestBody(TestServerRequestBody):
    """
    The body of a POST /runQuery request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

        {
            "database": "db",
            "query": "select meta().id from _"
        }
    """

    @property
    def database(self) -> str:
        return self.__db

    @property
    def query(self) -> str:
        return self.__query

    def __init__(self, database: str, query: str):
        super().__init__(1)
        self.__db = database
        self.__query = query

    def to_json(self) -> Any:
        return {"database": self.__db, "query": self.__query}


class PostGetDocumentRequestBody(TestServerRequestBody):
    """
    The body of a POST /getDocument request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

        {
            "database": "db",
            "document": {
                "collection": "foo.bar",
                "id": "doc1"
            }
        }
    """

    @property
    def database(self) -> str:
        """Gets the database to retrieve the document from"""
        return self.__database

    @property
    def document(self) -> DocumentEntry:
        """Gets the document information to use to retrieve the document"""
        return self.__document

    def __init__(self, database: str, document: DocumentEntry):
        super().__init__(1)
        self.__database = database
        self.__document = document

    def to_json(self) -> Any:
        return {"database": self.__database, "document": self.__document.to_json()}


class PostLogRequestBody(TestServerRequestBody):
    """
    The body of a POST /log request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

        {
            "message": "The client is on fire"
        }
    """

    @property
    def message(self) -> str:
        return self.__message

    def __init__(self, msg: str):
        super().__init__(1)
        self.__message = msg

    def to_json(self) -> Any:
        return {"message": self.__message}


class PostStartListenerRequestBody(TestServerRequestBody):
    """
    The body of a POST /startListener request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

        {
            "database": "db",
            "collections": ["foo.bar", "_default.baz"],
            "port": 59840
        }
    """

    @property
    def database(self) -> str:
        """The database to serve via the listener"""
        return self.__database

    @property
    def collections(self) -> list[str]:
        """The collections in the database to serve via the listener"""
        return self.__collections

    @property
    def port(self) -> int | None:
        """The desired port to listen on (if None, the OS will choose)"""
        return self.__port

    def __init__(self, db: str, collections: list[str], port: int | None = None):
        super().__init__(1)
        self.__database = db
        self.__collections = collections
        self.__port = port

    def to_json(self) -> Any:
        json: dict[str, Any] = {
            "database": self.__database,
            "collections": self.__collections,
        }

        if self.__port is not None:
            json["port"] = self.__port

        return json


class PostStopListenerRequestBody(TestServerRequestBody):
    """
    The body of a POST /stopListener request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

        {
            "id": ""123e4567-e89b-12d3-a456-426614174000""
        }
    """

    @property
    def id(self) -> str:
        """The ID of the listener to stop (returned from /startListener)"""
        return self.__id

    def __init__(self, id: str):
        super().__init__(1)
        self.__id = id

    def to_json(self) -> Any:
        return {"id": self.__id}


class PostStartMultipeerReplicatorRequestBody(TestServerRequestBody):
    """
    The body of a POST /startMultipeerReplicator request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

        {
            "peerGroupID": "com.couchbase.testing",
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
                },
                "pullFilter": {
                    "name": "documentIDs",
                    "params": {
                    "documentIDs": [
                        "doc1",
                        "doc2"
                    ]
                    }
                },
                "conflictResolver": {
                    "name": "merge",
                    "params": {
                    "property": "region"
                    }
                }
                }
            ],
            "identity": {
                "encoding": "PKCS12",
                "data": "string",
                "password": "pass"
            },
            "authenticator": {
                "type": "CA-CERT",
                "certificate": "string"
            }
        }
    """

    @property
    def peerGroupID(self) -> str:
        """Gets the peer group ID for the replicator"""
        return self.__peerGroupID

    @property
    def database(self) -> str:
        """Gets the database for the replicator"""
        return self.__database

    @property
    def collections(self) -> list[ReplicatorCollectionEntry]:
        """Gets the collections for the replicator"""
        return self.__collections

    def __init__(
        self,
        peerGroupID: str,
        database: str,
        collections: list[ReplicatorCollectionEntry],
        identity: CertKeyPair,
        *,
        authenticator: MultipeerReplicatorAuthenticator | None = None,
    ):
        super().__init__(1)
        self.__peerGroupID = peerGroupID
        self.__database = database
        self.__collections = collections
        self.__identity = identity
        self.__authenticator = authenticator

    def to_json(self) -> Any:
        json = {
            "peerGroupID": self.__peerGroupID,
            "database": self.__database,
            "collections": [c.to_json() for c in self.collections],
            "identity": {
                "encoding": "PKCS12",
                "data": base64.b64encode(self.__identity.pfx_bytes()).decode("utf-8"),
                "password": self.__identity.password,
            },
        }

        if self.__authenticator is not None:
            json["authenticator"] = self.__authenticator.to_json()

        return json


class PostStopMultipeerReplicatorRequestBody(TestServerRequestBody):
    """
    The body of a POST /stopMultipeerReplicator request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

    {
        "id": "123e4567-e89b-12d3-a456-426614174000"
    }
    """

    @property
    def id(self) -> str:
        """The ID of the multipeer replicator to stop (returned from /startMultipeerReplicator)"""
        return self.__id

    def __init__(self, id: str):
        super().__init__(1)
        self.__id = id

    def to_json(self) -> Any:
        return {"id": self.__id}


class PostGetMultipeerReplicatorStatusRequestBody(TestServerRequestBody):
    """
    The body of a POST /getMultipeerReplicatorStatus request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_

    Example Body::

    {
        "id": "123e4567-e89b-12d3-a456-426614174000"
    }
    """

    @property
    def id(self) -> str:
        """The ID of the multipeer replicator to stop (returned from /startMultipeerReplicator)"""
        return self.__id

    def __init__(self, id: str):
        super().__init__(1)
        self.__id = id

    def to_json(self) -> Any:
        return {"id": self.__id}


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
        super().__init__(
            1, uuid, "getAllDocuments", PostGetAllDocumentsRequestBody, payload=payload
        )


class PostUpdateDatabaseRequest(TestServerRequest):
    """
    A POST /updateDatabase request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(
            1, uuid, "updateDatabase", PostUpdateDatabaseRequestBody, payload=payload
        )


class PostSnapshotDocumentsRequest(TestServerRequest):
    """
    A POST /snapshotDocuments request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(
            1,
            uuid,
            "snapshotDocuments",
            PostSnapshotDocumentsRequestBody,
            payload=payload,
        )


class PostVerifyDocumentsRequest(TestServerRequest):
    """
    A POST /verifyDocuments request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(
            1, uuid, "verifyDocuments", PostVerifyDocumentsRequestBody, payload=payload
        )


class PostStartReplicatorRequest(TestServerRequest):
    """
    A POST /startReplicator request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(
            1, uuid, "startReplicator", PostStartReplicatorRequestBody, payload=payload
        )


class PostGetReplicatorStatusRequest(TestServerRequest):
    """
    A POST /getReplicatorStatus request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(
            1,
            uuid,
            "getReplicatorStatus",
            PostGetReplicatorStatusRequestBody,
            payload=payload,
        )


class PostPerformMaintenanceRequest(TestServerRequest):
    """
    A POST /performMaintenance request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(
            1,
            uuid,
            "performMaintenance",
            PostPerformMaintenanceRequestBody,
            payload=payload,
        )


class PostNewSessionRequest(TestServerRequest):
    """
    A POST /newSession request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, uuid: UUID, payload: PostNewSessionRequestBody):
        super().__init__(
            1, uuid, "newSession", PostNewSessionRequestBody, payload=payload
        )


class PostRunQueryRequest(TestServerRequest):
    """
    A POST /runQuery request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, uuid: UUID, payload: PostRunQueryRequestBody):
        super().__init__(1, uuid, "runQuery", PostRunQueryRequestBody, payload=payload)


class PostGetDocumentRequest(TestServerRequest):
    """
    A POST /getDocument request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(
            1, uuid, "getDocument", PostGetDocumentRequestBody, payload=payload
        )


class PostLogRequest(TestServerRequest):
    """
    A POST /log request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, uuid: UUID, payload: TestServerRequestBody):
        super().__init__(1, uuid, "log", PostLogRequestBody, payload=payload)


class PostStartListenerRequest(TestServerRequest):
    """
    A POST /startListener request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, uuid: UUID, payload: PostStartListenerRequestBody):
        super().__init__(
            1, uuid, "startListener", PostStartListenerRequestBody, payload=payload
        )


class PostStopListenerRequest(TestServerRequest):
    """
    A POST /stopListener request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, uuid: UUID, payload: PostStopListenerRequestBody):
        super().__init__(
            1, uuid, "stopListener", PostStopListenerRequestBody, payload=payload
        )


class PostStartMultipeerReplicatorRequest(TestServerRequest):
    """
    A POST /startMultipeerReplicator request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, uuid: UUID, payload: PostStartMultipeerReplicatorRequestBody):
        super().__init__(
            1,
            uuid,
            "startMultipeerReplicator",
            PostStartMultipeerReplicatorRequestBody,
            payload=payload,
        )


class PostStopMultipeerReplicatorRequest(TestServerRequest):
    """
    A POST /startMultipeerReplicator request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, uuid: UUID, payload: PostStopMultipeerReplicatorRequestBody):
        super().__init__(
            1,
            uuid,
            "stopMultipeerReplicator",
            PostStopMultipeerReplicatorRequestBody,
            payload=payload,
        )


class PostGetMultipeerReplicatorStatusRequest(TestServerRequest):
    """
    A POST /getMultipeerReplicatorStatus request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(
        self, uuid: UUID, payload: PostGetMultipeerReplicatorStatusRequestBody
    ):
        super().__init__(
            1,
            uuid,
            "getMultipeerReplicatorStatus",
            PostGetMultipeerReplicatorStatusRequestBody,
            payload=payload,
        )
