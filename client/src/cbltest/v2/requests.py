from typing import Any, cast
from uuid import UUID

from cbltest.api.jsonserializable import JSONSerializable
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


@register_body(TestServerRequestType.RESET, 2)
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
                    "dataset": "<github url>"
                }
            }
        }
    """

    def __init__(self, *, name: str | None = None):
        super().__init__()
        self.__test_name = name
        self.__databases: dict[str, dict[str, Any]] = {}

    def add_dataset(self, url: str, result_db_names: list[str]) -> None:
        """
        Add a dataset entry to the :class:`PostResetRequestBody`

        :param url: The URL of the dataset to download and add
        :param result_db_names: A list of databases to populate with the data from the dataset
        """
        for db_name in result_db_names:
            self.__databases[db_name] = {"dataset": url}

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


@register_body(TestServerRequestType.NEW_SESSION, 2)
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

    def __init__(self, *, id: str, url: str | None, tag: str | None, **kwargs):
        super().__init__()
        self.__url = url
        self.__id = id
        self.__tag = tag

    def to_json(self) -> Any:
        json: dict[str, Any] = {"id": self.__id}
        if self.__url is not None and self.__tag is not None:
            json["logging"] = {"url": self.__url, "tag": self.__tag}

        return json


@register_body(TestServerRequestType.UPDATE_DB, 2)
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

                raw_entries.append(raw_entry)

        raw["updates"] = raw_entries
        return raw


@register_body(TestServerRequestType.VERIFY_DOCS, 2)
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
        return {
            "snapshot": self.__snapshot,
            "database": self.__database,
            "changes": [c.to_json() for c in self.changes]
            if self.changes is not None
            else [],
        }


# Below this point are all of the concrete test server request types
# Remember the note from the top of this file about the actual type of the payload
@register_request(TestServerRequestType.RESET, 2)
class PostResetRequest(TestServerRequest):
    """
    A POST /reset request as specified in version 2 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: JSONSerializable):
        super().__init__(version, uuid, "reset", PostResetRequestBody, payload=payload)


@register_request(TestServerRequestType.NEW_SESSION, 2)
class PostNewSessionRequest(TestServerRequest):
    """
    A POST /newSession request as specified in version 2 of the
    `spec <https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/api.yaml>`_
    """

    def __init__(self, version: int, uuid: UUID, payload: JSONSerializable):
        super().__init__(
            version, uuid, "newSession", PostNewSessionRequestBody, payload=payload
        )


@register_request(TestServerRequestType.UPDATE_DB, 2)
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


@register_request(TestServerRequestType.VERIFY_DOCS, 2)
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
