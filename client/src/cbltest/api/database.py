from __future__ import annotations

from typing import List, cast

from cbltest.requests import TestServerRequestType
from cbltest.v1.responses import PostGetAllDocumentIDsResponse
from cbltest.v1.requests import DatabaseUpdateEntry, DatabaseUpdateType, PostGetAllDocumentIDsRequestBody, PostUpdateDatabaseRequestBody
from cbltest.logging import cbl_error, cbl_trace
from cbltest.requests import RequestFactory

class DatabaseUpdater:
    """
    A class which collects database operations to perform so that they can be sent in a batch
    """
    def __init__(self, db_name: str, request_factory: RequestFactory, index: int):
        assert(request_factory.version == 1)
        self.__db_name = db_name
        self.__updates: List[DatabaseUpdateEntry] = []
        self.__request_factory = request_factory
        self.__index = index

    async def __aenter__(self):
        self.__updates.clear()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        payload = PostUpdateDatabaseRequestBody(self.__db_name, self.__updates)
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
        self.__updates.append(DatabaseUpdateEntry(DatabaseUpdateType.DELETE, collection, id))

    def purge_document(self, collection: str, id: str):
        """
        Adds a purge document operation to be performed

        :param collection: The collection to which the document belongs (scope-qualified)
        :param id: The ID of the document to purge
        """
        self.__updates.append(DatabaseUpdateEntry(DatabaseUpdateType.PURGE, collection, id))

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
    def document_ids(self) -> List[str]:
        """
        Gets the list of document IDs contained in the collection
        """
        return self.__document_ids
    
    def __init__(self, name: str, ids: List[str]):
        self.__name = name
        self.__document_ids = ids

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
    
    def __init__(self, response: PostGetAllDocumentIDsResponse):
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
        payload = PostGetAllDocumentIDsRequestBody(self.__name, *collections)
        req = self.__request_factory.create_request(TestServerRequestType.ALL_DOC_IDS, payload)
        resp = await self.__request_factory.send_request(self.__index, req)
        if resp.error is not None:
            cbl_error("Failed to get all documents (see trace log for details)")
            cbl_trace(resp.error.message)
            return None

        return AllDocumentsMap(cast(PostGetAllDocumentIDsResponse, resp))