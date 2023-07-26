from __future__ import annotations
from json import dumps

from typing import Dict, List, cast, Any, Optional

from cbltest.requests import TestServerRequestType, TestServerRequest
from cbltest.v1.responses import PostGetAllDocumentsResponse, PostGetAllDocumentsEntry
from cbltest.v1.requests import DatabaseUpdateEntry, DatabaseUpdateType, PostGetAllDocumentsRequestBody, PostUpdateDatabaseRequestBody
from cbltest.logging import cbl_error, cbl_trace
from cbltest.requests import RequestFactory
from cbltest.adapters import _create_adapter

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
        self.__adapter = _create_adapter("DatabaseUpdaterAdapter", request_factory.version)

    async def __aenter__(self):
        self._updates.clear()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        payload = self.__adapter.create_request_body(self)
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

    def upsert_document(self, collection: str, id: str, new_properties: Optional[Dict[str, Any]] = None, 
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