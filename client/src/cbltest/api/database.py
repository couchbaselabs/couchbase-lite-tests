from __future__ import annotations
from json import dumps

from typing import Dict, List, cast, Any, Optional

from cbltest.requests import TestServerRequestType, TestServerRequest
from cbltest.v1.responses import PostGetAllDocumentsResponse, PostGetAllDocumentsEntry, PostSnapshotDocumentsResponse, PostVerifyDocumentsResponse
from cbltest.v1.requests import (DatabaseUpdateEntry, DatabaseUpdateType, PostGetAllDocumentsRequestBody, 
                                 PostUpdateDatabaseRequestBody, SnapshotDocumentEntry, PostSnapshotDocumentsRequestBody,
                                 PostVerifyDocumentsRequestBody)
from cbltest.logging import cbl_error, cbl_trace
from cbltest.requests import RequestFactory
from cbltest.api.syncgateway import AllDocumentsResponseRow
from cbltest.api.replicator_types import ReplicatorType

class SnapshotUpdater:
    def __init__(self, id: str):
        self._id = id
        self._updates: List[DatabaseUpdateEntry] = []

    def delete_document(self, collection: str, id: str):
        """
        Adds a delete document operation to be performed

        :param collection: The collection to which the document belongs (scope-qualified)
        :param id: The ID of the document to delete
        """
        self._updates.append(DatabaseUpdateEntry(DatabaseUpdateType.DELETE, collection, id))

    def purge_document(self, collection: str, id: str):
        """
        Adds a purge document operation to be performed

        :param collection: The collection to which the document belongs (scope-qualified)
        :param id: The ID of the document to purge
        """
        self._updates.append(DatabaseUpdateEntry(DatabaseUpdateType.PURGE, collection, id))

    def upsert_document(self, collection: str, id: str, new_properties: Optional[List[Dict[str, Any]]] = None, 
                        removed_properties: Optional[List[str]] = None):
        self._updates.append(DatabaseUpdateEntry(DatabaseUpdateType.UPDATE, collection, id, new_properties, removed_properties))

class DatabaseUpdater:
    """
    A class which collects database operations to perform so that they can be sent in a batch
    """
    def __init__(self, db_name: str, request_factory: RequestFactory, index: int):
        assert request_factory.version == 1, "This version of the CBLTest API requires request API v1"
        self._db_name = db_name
        self._updates: List[DatabaseUpdateEntry] = []
        self.__request_factory = request_factory
        self.__index = index

    async def __aenter__(self):
        self._updates.clear()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        payload = PostUpdateDatabaseRequestBody(self._db_name, self._updates)
        request = self.__request_factory.create_request(TestServerRequestType.UPDATE_DB, payload)
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
        self._updates.append(DatabaseUpdateEntry(DatabaseUpdateType.DELETE, collection, id))

    def purge_document(self, collection: str, id: str):
        """
        Adds a purge document operation to be performed

        :param collection: The collection to which the document belongs (scope-qualified)
        :param id: The ID of the document to purge
        """
        self._updates.append(DatabaseUpdateEntry(DatabaseUpdateType.PURGE, collection, id))

    def upsert_document(self, collection: str, id: str, new_properties: Optional[List[Dict[str, Any]]] = None, 
                        removed_properties: Optional[List[str]] = None):
        self._updates.append(DatabaseUpdateEntry(DatabaseUpdateType.UPDATE, collection, id, new_properties, removed_properties))

class AllDocumentsEntry:
    """
    A class that represents a single entry inside of an all documents collection
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
    A class that lists all of the documents in a given collection
    """
    @property
    def name(self) -> str:
        """
        Gets the name of the collection
        """
        return self.__name
    
    @property
    def documents(self) -> List[AllDocumentsEntry]:
        """
        Gets the list of document IDs contained in the collection
        """
        return self.__documents
    
    def __init__(self, name: str, docs: List[PostGetAllDocumentsEntry]):
        self.__name = name
        self.__documents = list(AllDocumentsEntry(x) for x in docs)

class AllDocumentsMap:
    """
    A class that contains all requested collections and their contained documents.
    It is returns from a getAllDocumentIDs request.
    """
    @property
    def collections(self) -> List[AllDocumentsCollection]:
        """
        Gets a list of the collections returned from the request, each containing all their doc IDs
        """
        return self.__collections
    
    def __init__(self, response: PostGetAllDocumentsResponse):
        self.__collections: List[AllDocumentsCollection] = []
        for c in response.collection_keys:
            self.__collections.append(AllDocumentsCollection(c, response.documents_for_collection(c)))

class Snapshot:
    @property
    def id(self) -> str:
        return self.__id

    def __init__(self, id: str) -> None:
        self.__id = id

class VerifyResult:
    @property
    def result(self) -> bool:
        """Gets the result of the verification"""
        return self.__response.result
    
    @property
    def description(self) -> Optional[str]:
        """Gets the description of what went wrong if result is false"""
        return self.__response.description
    
    @property
    def expected(self) -> Optional[dict]:
        """Gets the expected document body if the bodies did not match"""
        return self.__response.expected
    
    @property
    def actual(self) -> Optional[dict]:
        """Gets the actual document body if the bodies did not match"""
        return self.__response.actual
    
    def __init__(self, rest_response: PostVerifyDocumentsResponse) -> None:
        self.__response = rest_response

class DocsCompareResult:
    """
    A simple class to hold whether or not a list of documents 
    matches another, and if not then the first reason why it
    does not.
    """

    @property
    def message(self) -> Optional[str]:
        """
        If success is false, then this message will contain the description
        of the first difference found in the two lists
        """
        return self.__message
    
    @property 
    def success(self) -> bool:
        """Gets whether or not the two lists match"""
        return self.__success
    
    def __init__(self, success: bool, message: Optional[str] = None):
        self.__success = success
        self.__message = message

class Database:
    """
    A class for interacting with a Couchbase Lite database inside of a test server.
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

    def batch_updater(self) -> DatabaseUpdater:
        """
        Gets an object that can be used to perform batch updates on the database
        """
        return DatabaseUpdater(self.__name, self.__request_factory, self.__index)
    
    async def get_all_documents(self, *collections: str) -> AllDocumentsMap:
        """
        Performs a getAllDocumentIDs request for the given collections

        :param collections: A variadic list of collection names
        """
        payload = PostGetAllDocumentsRequestBody(self.__name, *collections)
        req = self.__request_factory.create_request(TestServerRequestType.ALL_DOC_IDS, payload)
        resp = await self.__request_factory.send_request(self.__index, req)
        return AllDocumentsMap(cast(PostGetAllDocumentsResponse, resp))
    
    async def create_snapshot(self, documents: List[SnapshotDocumentEntry]) -> str:
        """
        Creates a snapshot on the database to use for later verification

        :param documents: A list of documents to include in the snapshot
        """
        payload = PostSnapshotDocumentsRequestBody(self.__name, documents)
        req = self.__request_factory.create_request(TestServerRequestType.SNAPSHOT_DOCS, payload)
        resp = await self.__request_factory.send_request(self.__index, req)
        return cast(PostSnapshotDocumentsResponse, resp).snapshot_id
    
    async def verify_documents(self, updater: SnapshotUpdater) -> VerifyResult:
        """
        Verifies a set of documents in the database by applying changes to a snapshot
        and checking that the on disk results match

        :param snapshot: The snapshot ID to use as a base
        :param changes: The changes to apply to the snapshot first
        """
        payload = PostVerifyDocumentsRequestBody(self.__name, updater._id, updater._updates)
        req = self.__request_factory.create_request(TestServerRequestType.VERIFY_DOCS, payload)
        resp = await self.__request_factory.send_request(self.__index, req)
        return VerifyResult(cast(PostVerifyDocumentsResponse, resp))
    
    def compare_doc_results(self, local: List[AllDocumentsEntry], remote: List[AllDocumentsResponseRow],
                            mode: ReplicatorType) -> DocsCompareResult:
        """
        Checks for consistency between a list of local documents and a list of remote documents, accounting
        for the mode of replication that was run.  For PUSH_AND_PULL, the document count must match exactly,
        along with the contents.  For PUSH, the local list is consulted and the remote list is checked,
        and vice-versa for PULL (to account for other pre-existing documents that have not been synced
        due to the non bi-directional mode)

        :param local: The list of documents from the local side (Couchbase Lite)
        :param remote: The list of documents from the remote side (Sync Gateway)
        :param mode: The mode of replication that was run.
        """
        if mode == ReplicatorType.PUSH_AND_PULL and len(local) != len(remote):
            return DocsCompareResult(False, f"Local count {len(local)} did not match remote count {len(remote)}")
        
        local_dict = {}
        remote_dict = {}

        for entry in local:
            local_dict[entry.id] = entry.rev

        for entry in remote:
            remote_dict[entry.id] = entry.revid

        if mode == ReplicatorType.PUSH:
            source = local_dict
            dest = remote_dict
            source_name = "local"
            dest_name = "remote"
        else:
            source = remote_dict
            dest = local_dict
            source_name = "remote"
            dest_name = "local"

        for id in source:
            if id not in dest:
                return DocsCompareResult(False, f"Doc '{id}' present in {source_name} but not {dest_name}")
            
            if source[id] != dest[id]:
                return DocsCompareResult(False, f"Doc '{id}' mismatched revid ({source_name}: {source[id]}, {dest_name}: {dest[id]})")
            
        return DocsCompareResult(True)