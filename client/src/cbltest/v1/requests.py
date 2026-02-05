import base64
from typing import Any, cast
from urllib.parse import urlparse
from uuid import UUID

from cbltest.api.database_types import DocumentEntry
from cbltest.api.jsonserializable import JSONSerializable
from cbltest.api.multipeer_replicator_types import (
    MultipeerReplicatorAuthenticator,
    MultipeerTransportType,
)
from cbltest.api.replicator_types import (
    ReplicatorAuthenticator,
    ReplicatorCollectionEntry,
    ReplicatorType,
)
from cbltest.api.x509_certificate import CertKeyPair
from cbltest.assertions import _assert_not_null
from cbltest.logging import cbl_warning
from cbltest.request_types import DatabaseUpdateEntry, PostResetRequestMethods
from cbltest.requests import (
    TestServerRequest,
    TestServerRequestType,
    register_body,
    register_request,
)

# Some conventions that are followed in this file are that all request classes that
# will be sent to the test server are classes that end in 'Request'.  Their bodies
# are the same class name, except with 'Body' appended.  For example, PostResetRequest
# will accept PostResetRequestBody.  The type is generic in the constructor in order
# to facilitate easy API versioning, but an assert will check the type is correct.

# All other classes support the RequestBody classes


@register_body(TestServerRequestType.RESET, 1)
class PostResetRequestBody(JSONSerializable, PostResetRequestMethods):
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
        super().__init__()
        self.__test_name = name
        self.__databases: dict[str, dict[str, Any]] = {}

    def add_dataset(self, url: str, result_db_names: list[str]) -> None:
        """
        Add a dataset entry to the :class:`PostResetRequestBody`

        :param url: The URL of the dataset to add (i.e. catalog in the class docs example)
        :param result_db_names: A list of databases to populate with the data from the dataset
        """
        for db_name in result_db_names:
            # Work backward to convert URL back into name for v1
            name = urlparse(url).path.split("/")[-1].replace(".cblite2.zip", "")
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


@register_body(TestServerRequestType.ALL_DOC_IDS, [1, 2])
class PostGetAllDocumentsRequestBody(JSONSerializable):
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

    def __init__(self, *, database: str, collections: list[str] | None = None):
        super().__init__()
        _assert_not_null(database, "database")
        self.database = database
        """The database to get document IDs from"""

        self.__collections = collections if collections is not None else []

    def to_json(self) -> Any:
        return {"database": self.database, "collections": self.__collections}


@register_body(TestServerRequestType.UPDATE_DB, 1)
class PostUpdateDatabaseRequestBody(JSONSerializable):
    """
    The body of a POST /updateDatabase request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(
        self,
        *,
        database: str | None = None,
        updates: list[DatabaseUpdateEntry] | None = None,
    ):
        super().__init__()
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

                # Hack in the names instead of URL for blobs
                if "updatedBlobs" in raw_entry:
                    updated_blobs = cast(dict[str, str], raw_entry["updatedBlobs"])
                    for keypath in updated_blobs:
                        blob_url = updated_blobs[keypath]
                        parsed_url = urlparse(blob_url)
                        blob_name = parsed_url.path.split("/")[-1]
                        raw_entry["updatedBlobs"][keypath] = blob_name

                raw_entries.append(raw_entry)

        raw["updates"] = raw_entries
        return raw


@register_body(TestServerRequestType.SNAPSHOT_DOCS, [1, 2])
class PostSnapshotDocumentsRequestBody(JSONSerializable):
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

    def __init__(self, *, database: str, entries: list[DocumentEntry] | None = None):
        super().__init__()
        self.__database = database
        self.__entries = entries if entries is not None else []

    def to_json(self) -> Any:
        return {
            "database": self.__database,
            "documents": [e.to_json() for e in self.__entries],
        }


@register_body(TestServerRequestType.VERIFY_DOCS, 1)
class PostVerifyDocumentsRequestBody(JSONSerializable):
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
        *,
        database: str,
        snapshot: str,
        changes: list[DatabaseUpdateEntry] | None = None,
    ):
        super().__init__()
        self.__snapshot = snapshot
        self.__database = database
        self.changes = changes
        """A list of changes to verify in the database (as compared to the `snapshot`)"""

    def to_json(self) -> Any:
        changes = []
        if self.changes:
            for c in cast(list[DatabaseUpdateEntry], self.changes):
                change_json = c.to_json()

                # Hack the names back into the JSON instead of URL for v1
                if "updatedBlobs" in change_json:
                    updated_blobs = cast(dict[str, str], change_json["updatedBlobs"])
                    for keypath in updated_blobs:
                        blob_url = updated_blobs[keypath]
                        parsed_url = urlparse(blob_url)
                        blob_name = parsed_url.path.split("/")[-1]
                        change_json["updatedBlobs"][keypath] = blob_name

                changes.append(change_json)

        return {
            "snapshot": self.__snapshot,
            "database": self.__database,
            "changes": changes,
        }


@register_body(TestServerRequestType.START_REPLICATOR, [1, 2])
class PostStartReplicatorRequestBody(JSONSerializable):
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

    def __init__(
        self,
        *,
        database: str,
        endpoint: str,
        replicatorType: ReplicatorType = ReplicatorType.PUSH_AND_PULL,
        continuous: bool = False,
        authenticator: ReplicatorAuthenticator | None = None,
        reset: bool = False,
        collections: list[ReplicatorCollectionEntry] | None = None,
        enableDocumentListener: bool = False,
        enableAutoPurge: bool = True,
        pinnedServerCert: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__()
        self.__database = database
        self.__endpoint = endpoint
        self.replicatorType: ReplicatorType = replicatorType
        """The direction to be performed during the replication"""

        self.continuous: bool = continuous
        """Whether or not this is a continuous replication (i.e. doesn't stop when finished
        with its initial changes)"""

        self.authenticator: ReplicatorAuthenticator | None = authenticator
        """The authenticator to use to perform authentication with the remote"""

        self.reset: bool = reset
        """Whether or not to start the replication over from the beginning"""

        self.collections: list[ReplicatorCollectionEntry] = (
            collections if collections is not None else []
        )
        """The per-collection configuration to use inside the replication"""

        self.enableDocumentListener: bool = enableDocumentListener
        """If set to True, calls to getReplicatorStatus will return a list of document events"""

        self.enableAutoPurge: bool = enableAutoPurge
        """If set to True (default), the replicator will automatically purge documents on access loss"""

        self.pinnedServerCert: str | None = pinnedServerCert
        """The PEM representation of the TLS certificate that the remote is using"""

        self.headers: dict[str, str] | None = headers
        """The headers to include in the replication requests"""

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
            "headers": self.headers,
        }

        if self.collections is not None:
            raw["collections"] = [c.to_json() for c in self.collections]

        if self.authenticator is not None:
            raw["authenticator"] = self.authenticator.to_json()

        ret_val = {"config": raw, "reset": self.reset}

        return ret_val


@register_body(TestServerRequestType.REPLICATOR_STATUS, [1, 2])
class PostGetReplicatorStatusRequestBody(JSONSerializable):
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

    def __init__(self, *, id: str):
        super().__init__()
        self.__id = id

    def to_json(self) -> Any:
        """Serializes the :class:`PostGetReplicatorStatusRequestBody` to a JSON string"""
        return {"id": self.__id}


@register_body(TestServerRequestType.PERFORM_MAINTENANCE, [1, 2])
class PostPerformMaintenanceRequestBody(JSONSerializable):
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

    def __init__(self, *, db: str, op_type: str):
        super().__init__()
        self.__db = db
        self.__type = op_type

    def to_json(self) -> Any:
        return {"database": self.__db, "maintenanceType": self.__type}


@register_body(TestServerRequestType.NEW_SESSION, 1)
class PostNewSessionRequestBody(JSONSerializable):
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

    def __init__(
        self, *, id: str, dataset_version: str, url: str | None, tag: str | None
    ):
        super().__init__()
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


@register_body(TestServerRequestType.RUN_QUERY, [1, 2])
class PostRunQueryRequestBody(JSONSerializable):
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

    def __init__(self, *, database: str, query: str):
        super().__init__()
        self.__db = database
        self.__query = query

    def to_json(self) -> Any:
        return {"database": self.__db, "query": self.__query}


@register_body(TestServerRequestType.GET_DOCUMENT, [1, 2])
class PostGetDocumentRequestBody(JSONSerializable):
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

    def __init__(self, *, database: str, document: DocumentEntry):
        super().__init__()
        self.__database = database
        self.__document = document

    def to_json(self) -> Any:
        return {"database": self.__database, "document": self.__document.to_json()}


@register_body(TestServerRequestType.LOG, [1, 2])
class PostLogRequestBody(JSONSerializable):
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

    def __init__(self, *, msg: str):
        super().__init__()
        self.__message = msg

    def to_json(self) -> Any:
        return {"message": self.__message}


@register_body(TestServerRequestType.START_LISTENER, [1, 2])
class PostStartListenerRequestBody(JSONSerializable):
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

    @property
    def disableTLS(self) -> bool:
        """If True, TLS will be disabled for the listener"""
        return self.__disable_tls

    def __init__(
        self,
        *,
        db: str,
        collections: list[str],
        port: int | None = None,
        disable_tls: bool = False,
    ):
        super().__init__()
        self.__database = db
        self.__collections = collections
        self.__port = port
        self.__disable_tls = disable_tls

    def to_json(self) -> Any:
        json: dict[str, Any] = {
            "database": self.__database,
            "collections": self.__collections,
        }

        if self.__port is not None:
            json["port"] = self.__port

        if self.__disable_tls:
            json["disableTLS"] = self.__disable_tls

        return json


@register_body(TestServerRequestType.STOP_LISTENER, [1, 2])
class PostStopListenerRequestBody(JSONSerializable):
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

    def __init__(self, *, id: str):
        super().__init__()
        self.__id = id

    def to_json(self) -> Any:
        return {"id": self.__id}


@register_body(TestServerRequestType.START_MULTIPEER_REPLICATOR, [1, 2])
class PostStartMultipeerReplicatorRequestBody(JSONSerializable):
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
        *,
        peerGroupID: str,
        database: str,
        collections: list[ReplicatorCollectionEntry],
        identity: CertKeyPair,
        authenticator: MultipeerReplicatorAuthenticator | None = None,
        transports: MultipeerTransportType = MultipeerTransportType.WIFI,
    ):
        super().__init__()
        self.__peerGroupID = peerGroupID
        self.__database = database
        self.__collections = collections
        self.__identity = identity
        self.__authenticator = authenticator
        self.__transports = transports

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
            "transports": self.__transports,
        }

        if self.__authenticator is not None:
            json["authenticator"] = self.__authenticator.to_json()

        return json


@register_body(TestServerRequestType.STOP_MULTIPEER_REPLICATOR, [1, 2])
class PostStopMultipeerReplicatorRequestBody(JSONSerializable):
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

    def __init__(self, *, id: str):
        super().__init__()
        self.__id = id

    def to_json(self) -> Any:
        return {"id": self.__id}


@register_body(TestServerRequestType.MULTIPEER_REPLICATOR_STATUS, [1, 2])
class PostGetMultipeerReplicatorStatusRequestBody(JSONSerializable):
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

    def __init__(self, *, id: str):
        super().__init__()
        self.__id = id

    def to_json(self) -> Any:
        return {"id": self.__id}


# Below this point are all of the concrete test server request types
# Remember the note from the top of this file about the actual type of the payload
@register_request(TestServerRequestType.RESET, 1)
class PostResetRequest(TestServerRequest):
    """
    A POST /reset request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: JSONSerializable):
        super().__init__(version, uuid, "reset", PostResetRequestBody, payload=payload)


@register_request(TestServerRequestType.ALL_DOC_IDS, [1, 2])
class PostGetAllDocumentsRequest(TestServerRequest):
    """
    A POST /getAllDocuments request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: JSONSerializable):
        super().__init__(
            version,
            uuid,
            "getAllDocuments",
            PostGetAllDocumentsRequestBody,
            payload=payload,
        )


@register_request(TestServerRequestType.UPDATE_DB, 1)
class PostUpdateDatabaseRequest(TestServerRequest):
    """
    A POST /updateDatabase request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: JSONSerializable):
        super().__init__(
            version,
            uuid,
            "updateDatabase",
            PostUpdateDatabaseRequestBody,
            payload=payload,
        )


@register_request(TestServerRequestType.SNAPSHOT_DOCS, [1, 2])
class PostSnapshotDocumentsRequest(TestServerRequest):
    """
    A POST /snapshotDocuments request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: JSONSerializable):
        super().__init__(
            version,
            uuid,
            "snapshotDocuments",
            PostSnapshotDocumentsRequestBody,
            payload=payload,
        )


@register_request(TestServerRequestType.VERIFY_DOCS, [1, 2])
class PostVerifyDocumentsRequest(TestServerRequest):
    """
    A POST /verifyDocuments request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: JSONSerializable):
        super().__init__(
            version,
            uuid,
            "verifyDocuments",
            PostVerifyDocumentsRequestBody,
            payload=payload,
        )


@register_request(TestServerRequestType.START_REPLICATOR, [1, 2])
class PostStartReplicatorRequest(TestServerRequest):
    """
    A POST /startReplicator request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: JSONSerializable):
        super().__init__(
            version,
            uuid,
            "startReplicator",
            PostStartReplicatorRequestBody,
            payload=payload,
        )


@register_request(TestServerRequestType.REPLICATOR_STATUS, [1, 2])
class PostGetReplicatorStatusRequest(TestServerRequest):
    """
    A POST /getReplicatorStatus request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: JSONSerializable):
        super().__init__(
            version,
            uuid,
            "getReplicatorStatus",
            PostGetReplicatorStatusRequestBody,
            payload=payload,
        )


@register_request(TestServerRequestType.PERFORM_MAINTENANCE, [1, 2])
class PostPerformMaintenanceRequest(TestServerRequest):
    """
    A POST /performMaintenance request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: JSONSerializable):
        super().__init__(
            version,
            uuid,
            "performMaintenance",
            PostPerformMaintenanceRequestBody,
            payload=payload,
        )


@register_request(TestServerRequestType.NEW_SESSION, 1)
class PostNewSessionRequest(TestServerRequest):
    """
    A POST /newSession request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: PostNewSessionRequestBody):
        super().__init__(
            version, uuid, "newSession", PostNewSessionRequestBody, payload=payload
        )


@register_request(TestServerRequestType.RUN_QUERY, [1, 2])
class PostRunQueryRequest(TestServerRequest):
    """
    A POST /runQuery request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: PostRunQueryRequestBody):
        super().__init__(
            version, uuid, "runQuery", PostRunQueryRequestBody, payload=payload
        )


@register_request(TestServerRequestType.GET_DOCUMENT, [1, 2])
class PostGetDocumentRequest(TestServerRequest):
    """
    A POST /getDocument request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: JSONSerializable):
        super().__init__(
            version, uuid, "getDocument", PostGetDocumentRequestBody, payload=payload
        )


@register_request(TestServerRequestType.LOG, [1, 2])
class PostLogRequest(TestServerRequest):
    """
    A POST /log request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: JSONSerializable):
        super().__init__(version, uuid, "log", PostLogRequestBody, payload=payload)


@register_request(TestServerRequestType.START_LISTENER, [1, 2])
class PostStartListenerRequest(TestServerRequest):
    """
    A POST /startListener request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: PostStartListenerRequestBody):
        super().__init__(
            version,
            uuid,
            "startListener",
            PostStartListenerRequestBody,
            payload=payload,
        )


@register_request(TestServerRequestType.STOP_LISTENER, [1, 2])
class PostStopListenerRequest(TestServerRequest):
    """
    A POST /stopListener request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: PostStopListenerRequestBody):
        super().__init__(
            version, uuid, "stopListener", PostStopListenerRequestBody, payload=payload
        )


@register_request(TestServerRequestType.START_MULTIPEER_REPLICATOR, [1, 2])
class PostStartMultipeerReplicatorRequest(TestServerRequest):
    """
    A POST /startMultipeerReplicator request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(
        self, version: int, uuid: UUID, payload: PostStartMultipeerReplicatorRequestBody
    ):
        super().__init__(
            version,
            uuid,
            "startMultipeerReplicator",
            PostStartMultipeerReplicatorRequestBody,
            payload=payload,
        )


@register_request(TestServerRequestType.STOP_MULTIPEER_REPLICATOR, [1, 2])
class PostStopMultipeerReplicatorRequest(TestServerRequest):
    """
    A POST /startMultipeerReplicator request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(
        self, version: int, uuid: UUID, payload: PostStopMultipeerReplicatorRequestBody
    ):
        super().__init__(
            version,
            uuid,
            "stopMultipeerReplicator",
            PostStopMultipeerReplicatorRequestBody,
            payload=payload,
        )


@register_request(TestServerRequestType.MULTIPEER_REPLICATOR_STATUS, [1, 2])
class PostGetMultipeerReplicatorStatusRequest(TestServerRequest):
    """
    A POST /getMultipeerReplicatorStatus request as specified in version 1 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(
        self,
        version: int,
        uuid: UUID,
        payload: PostGetMultipeerReplicatorStatusRequestBody,
    ):
        super().__init__(
            version,
            uuid,
            "getMultipeerReplicatorStatus",
            PostGetMultipeerReplicatorStatusRequestBody,
            payload=payload,
        )
