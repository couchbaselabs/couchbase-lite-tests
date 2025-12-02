from __future__ import annotations

from json import dumps
from re import match
from typing import Any, Final, cast

from opentelemetry.trace import get_tracer

from cbltest.api.database_types import DocumentEntry, MaintenanceType
from cbltest.api.error import CblTestError
from cbltest.logging import cbl_error, cbl_trace
from cbltest.request_types import DatabaseUpdateEntry, DatabaseUpdateType
from cbltest.requests import RequestFactory, TestServerRequestType
from cbltest.response_types import (
    PostGetAllDocumentsEntry,
    PostGetAllDocumentsResponseMethods,
    PostGetDocumentResponseMethods,
    PostRunQueryResponseMethods,
    PostSnapshotDocumentsResponseMethods,
    PostVerifyDocumentsResponseMethods,
    ValueOrMissing,
)
from cbltest.version import VERSION

BASE_BLOB_URL = "https://media.githubusercontent.com/media/couchbaselabs/couchbase-lite-tests/refs/heads/main/dataset/server/blobs/"


class SnapshotUpdater:
    def __init__(self, id: str):
        self._id = id
        self._updates: list[DatabaseUpdateEntry] = []

    def delete_document(self, collection: str, id: str):
        """
        Adds a delete document operation to be performed

        :param collection: The collection to which the document belongs (scope-qualified)
        :param id: The ID of the document to delete
        """
        self._updates.append(
            DatabaseUpdateEntry(DatabaseUpdateType.DELETE, collection, id)
        )

    def purge_document(self, collection: str, id: str):
        """
        Adds a purge document operation to be performed

        :param collection: The collection to which the document belongs (scope-qualified)
        :param id: The ID of the document to purge
        """
        self._updates.append(
            DatabaseUpdateEntry(DatabaseUpdateType.PURGE, collection, id)
        )

    def upsert_document(
        self,
        collection: str,
        id: str,
        new_properties: list[dict[str, Any]] | None = None,
        removed_properties: list[str] | None = None,
        new_blobs: dict[str, str] | None = None,
    ):
        """
        Updates or inserts a document using the given new and/or removed properties

        :param collection: The collection to which the document belongs or will be added to (scope-qualified)
        :param id: The ID of the document to upsert
        :param new_properties: A list of dictionaries, each containing keypaths to set and values to use for the set.
                               The updates will be applied in the order specified in the list
        :param removed_properties: A list of keypaths to remove from the document
        :param new_blobs: A dictionary containing keypaths to add blobs to, valued as a valid blob name according
                          to the blobs dataset

        .. note:: A keypath is a JSON keypath like $.foo[0].bar ($. is optional)
        """
        if new_properties is not None:
            assert isinstance(new_properties, list), (
                "Incorrect new_properties format, must be a list of dictionaries each with properties to update"
            )

        if new_blobs is not None:
            for keypath in new_blobs:
                blob_name = new_blobs[keypath]
                new_blobs[keypath] = BASE_BLOB_URL + blob_name

        self._updates.append(
            DatabaseUpdateEntry(
                DatabaseUpdateType.UPDATE,
                collection,
                id,
                new_properties,
                removed_properties,
                new_blobs,
            )
        )


class DatabaseUpdater:
    """
    A class which collects database operations to perform so that they can be sent in a batch
    """

    def __init__(self, db_name: str, request_factory: RequestFactory, index: int):
        self._db_name = db_name
        self._updates: list[DatabaseUpdateEntry] = []
        self.__request_factory = request_factory
        self.__index = index
        self.__error: str | None = None
        self.__tracer = get_tracer(__name__, VERSION)

    async def __aenter__(self):
        self._updates.clear()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        with self.__tracer.start_as_current_span("update_database"):
            if self.__error is not None:
                raise CblTestError(self.__error)

            request = self.__request_factory.create_request(
                TestServerRequestType.UPDATE_DB,
                database=self._db_name,
                updates=self._updates,
            )
            resp = await self.__request_factory.send_request(self.__index, request)
            if resp.error is not None:
                cbl_error("Failed to update database (see trace log for details)")
                cbl_trace(resp.error.message)

            return self

    def delete_document(self, collection: str, id: str):
        """
        Adds a delete document operation to be performed

        :param collection: The collection to which the document belongs (scope-qualified)
        :param id: The ID of the document to delete
        """
        self._updates.append(
            DatabaseUpdateEntry(DatabaseUpdateType.DELETE, collection, id)
        )

    def purge_document(self, collection: str, id: str):
        """
        Adds a purge document operation to be performed

        :param collection: The collection to which the document belongs (scope-qualified)
        :param id: The ID of the document to purge
        """
        self._updates.append(
            DatabaseUpdateEntry(DatabaseUpdateType.PURGE, collection, id)
        )

    def upsert_document(
        self,
        collection: str,
        id: str,
        new_properties: list[dict[str, Any]] | None = None,
        removed_properties: list[str] | None = None,
        new_blobs: dict[str, str] | None = None,
    ):
        """
        Updates or inserts a document using the given new and/or removed properties

        :param collection: The collection to which the document belongs or will be added to (scope-qualified)
        :param id: The ID of the document to upsert
        :param new_properties: A list of dictionaries, each containing keypaths to set and values to use for the set.
                               The updates will be applied in the order specified in the list
        :param removed_properties: A list of keypaths to remove from the document
        :param new_blobs: A dictionary containing keypaths to add blobs to, valued as a valid blob name according
                          to the blobs dataset

        .. note:: A keypath is a JSON keypath like $.foo[0].bar ($. is optional)
        """
        if new_properties is not None and not isinstance(new_properties, list):
            self.__error = "Incorrect new_properties format, must be a list of dictionaries each with properties to update"
            return

        if new_blobs is not None:
            for keypath in new_blobs:
                blob_name = new_blobs[keypath]
                new_blobs[keypath] = BASE_BLOB_URL + blob_name

        self._updates.append(
            DatabaseUpdateEntry(
                DatabaseUpdateType.UPDATE,
                collection,
                id,
                new_properties,
                removed_properties,
                new_blobs,
            )
        )


class AllDocumentsEntry:
    """
    A class that represents a single entry inside an all documents collection
    """

    @property
    def id(self) -> str:
        """Gets the ID of the document"""
        return self.__id

    @property
    def rev(self) -> str:
        """Gets the rev ID of the document"""
        return self.__rev

    def __init__(self, body: PostGetAllDocumentsEntry):
        self.__id = body.id
        self.__rev = body.rev

    def __str__(self) -> str:
        return dumps({"id": self.__id, "rev": self.__rev})


class AllDocumentsCollection:
    """
    A class that lists all the documents in a given collection
    """

    @property
    def documents(self) -> list[AllDocumentsEntry]:
        """
        Gets the list of document IDs contained in the collection
        """
        return self.__documents

    def __init__(self, docs: list[PostGetAllDocumentsEntry]):
        self.__documents = list(AllDocumentsEntry(x) for x in docs)


class Snapshot:
    @property
    def id(self) -> str:
        """Gets the ID of the snapshot that was created"""
        return self.__id

    def __init__(self, id: str) -> None:
        self.__id = id


class VerifyResult:
    @property
    def result(self) -> bool:
        """Gets the result of the verification"""
        return self.__response.result

    @property
    def description(self) -> str | None:
        """Gets the description of what went wrong if result is false"""
        return self.__response.description

    @property
    def expected(self) -> ValueOrMissing:
        """Gets the expected value of the faulty keypath, if applicable"""
        return self.__response.expected

    @property
    def actual(self) -> ValueOrMissing:
        """Gets the actual value of the faulty keypath, if applicable"""
        return self.__response.actual

    @property
    def document(self) -> dict[str, Any] | None:
        """Gets the document body of the document with the faulty keypath, if applicable"""
        return self.__response.document

    def __init__(self, rest_response: PostVerifyDocumentsResponseMethods) -> None:
        self.__response = rest_response


class GetDocumentResult:
    """
    The result of a call to POST /getDocument
    """

    __id_key: Final[str] = "_id"
    __revs_key: Final[str] = "_revs"

    @property
    def id(self) -> str:
        """Gets the ID of the document"""
        return self.__id

    @property
    def revs(self) -> str:
        """Gets the revision history for the document"""
        return self.__revs

    @property
    def body(self) -> dict[str, Any]:
        """Gets the body of the document"""
        return self.__body

    @property
    def revid(self) -> str | None:
        """
        If the current version looks like a rev-tree style 'N-xxxx', return it,
        otherwise return None.
        """
        current = self.__current_version()
        # rev-tree is assumed to be number-dash-anything
        return current if match(r"^\d+-", current) else None

    @property
    def cv(self) -> str | None:
        """
        If the current version looks like a version-vector (contains '@'),
        return it, otherwise return None.
        """
        current = self.__current_version()
        return current if "@" in current else None

    def __current_version(self) -> str:
        """
        Returns the first (current) version string.
        Handles both rev-tree and version-vector formats.
        """
        # Replace semicolons with commas, then split
        parts = [
            p.strip() for p in self.__revs.replace(";", ",").split(",") if p.strip()
        ]
        return parts[0] if parts else ""

    def __init__(self, raw: dict[str, Any]) -> None:
        assert self.__id_key in raw and self.__revs_key in raw, (
            "Malformed raw dict in GetDocumentResult"
        )
        self.__id = raw[self.__id_key]
        self.__revs = raw[self.__revs_key]
        raw.pop(self.__id_key)
        raw.pop(self.__revs_key)
        self.__body = raw


class Database:
    """
    A class for interacting with a Couchbase Lite database inside a test server.
    """

    @property
    def name(self) -> str:
        """
        Gets the name of the database
        """
        return self.__name

    @property
    def _request_factory(self) -> RequestFactory:
        return self.__request_factory

    @property
    def _index(self) -> int:
        return self.__index

    def __init__(self, factory: RequestFactory, index: int, name: str):
        self.__name = name
        self.__index = index
        self.__request_factory = factory
        self.__tracer = get_tracer(__name__, VERSION)

    def batch_updater(self) -> DatabaseUpdater:
        """
        Gets an object that can be used to perform batch updates on the database
        """
        return DatabaseUpdater(self.__name, self.__request_factory, self.__index)

    async def get_all_documents(
        self, *collections: str
    ) -> dict[str, list[AllDocumentsEntry]]:
        """
        Performs a getAllDocumentIDs request for the given collections

        :param collections: A variadic list of collection names
        """
        with self.__tracer.start_as_current_span(
            "get_all_documents",
            attributes={
                "cbl.database.name": self.__name,
                "cbl.collection.names": collections,
            },
        ):
            req = self.__request_factory.create_request(
                TestServerRequestType.ALL_DOC_IDS,
                database=self.__name,
                collections=list(collections),
            )
            resp = await self.__request_factory.send_request(self.__index, req)
            cast_resp = cast(PostGetAllDocumentsResponseMethods, resp)
            ret_val: dict[str, list[AllDocumentsEntry]] = {}
            for c in cast_resp.collection_keys:
                ret_val[c] = list(
                    AllDocumentsEntry(d) for d in cast_resp.documents_for_collection(c)
                )

            return ret_val

    async def get_document(self, document: DocumentEntry) -> GetDocumentResult:
        """
        Performs a getDocument request for the given document information

        :param document: The collection and ID of a document to be retrieved
        """
        with self.__tracer.start_as_current_span(
            "get_document",
            attributes={
                "cbl.database.name": self.__name,
                "cbl.collection.name": document.collection,
                "cbl.document.id": document.id,
            },
        ):
            req = self.__request_factory.create_request(
                TestServerRequestType.GET_DOCUMENT,
                database=self.__name,
                document=document,
            )
            resp = await self.__request_factory.send_request(self.__index, req)
            cast_resp = cast(PostGetDocumentResponseMethods, resp)
            return GetDocumentResult(cast_resp.raw_body)

    async def create_snapshot(self, documents: list[DocumentEntry]) -> str:
        """
        Creates a snapshot on the database to use for later verification

        :param documents: A list of documents to include in the snapshot
        """
        with self.__tracer.start_as_current_span("create_snapshot"):
            req = self.__request_factory.create_request(
                TestServerRequestType.SNAPSHOT_DOCS,
                database=self.__name,
                entries=documents,
            )
            resp = await self.__request_factory.send_request(self.__index, req)
            return cast(PostSnapshotDocumentsResponseMethods, resp).snapshot_id

    async def verify_documents(self, updater: SnapshotUpdater) -> VerifyResult:
        """
        Verifies a set of documents in the database by applying changes to a snapshot
        and checking that the on disk results match

        :param updater: The id and expected updates
        """
        with self.__tracer.start_as_current_span("verify_documents"):
            req = self.__request_factory.create_request(
                TestServerRequestType.VERIFY_DOCS,
                database=self.__name,
                snapshot=updater._id,
                changes=updater._updates,
            )
            resp = await self.__request_factory.send_request(self.__index, req)
            return VerifyResult(cast(PostVerifyDocumentsResponseMethods, resp))

    async def perform_maintenance(self, type: MaintenanceType) -> None:
        """
        Performs the given maintenance operation on the database

        :param type: The type of maintenance to perform
        """
        with self.__tracer.start_as_current_span("perform_maintenance"):
            req = self.__request_factory.create_request(
                TestServerRequestType.PERFORM_MAINTENANCE,
                db=self.__name,
                op_type=str(type),
            )
            await self.__request_factory.send_request(self.__index, req)

    async def run_query(self, query: str) -> list[dict]:
        """
        Runs a SQL++ query on the database and returns the results

        :param query: The SQL++ query to run
        """
        with self.__tracer.start_as_current_span("run_query"):
            req = self.__request_factory.create_request(
                TestServerRequestType.RUN_QUERY, database=self.__name, query=query
            )
            resp = await self.__request_factory.send_request(self.__index, req)
            return cast(PostRunQueryResponseMethods, resp).results
