from __future__ import annotations

from typing import List, cast

from ..requests import TestServerRequestType
from ..v1.responses import PostGetAllDocumentIDsResponse
from ..v1.requests import DatabaseUpdateEntry, DatabaseUpdateType, PostGetAllDocumentIDsRequestBody, PostUpdateDatabaseRequestBody
from ..logging import cbl_error, cbl_trace
from ..requests import RequestFactory

class DatabaseUpdater:
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
        self.__updates.append(DatabaseUpdateEntry(DatabaseUpdateType.DELETE, collection, id))

    def purge_document(self, collection: str, id: str):
        self.__updates.append(DatabaseUpdateEntry(DatabaseUpdateType.PURGE, collection, id))

class AllDocumentsCollection:
    @property
    def name(self) -> str:
        return self.__name
    
    @property
    def document_ids(self) -> List[str]:
        return self.__document_ids
    
    def __init__(self, name: str, ids: List[str]):
        self.__name = name
        self.__document_ids = ids

class AllDocumentsMap:
    @property
    def collections(self) -> List[AllDocumentsCollection]:
        return self.__collections
    
    def __init__(self, response: PostGetAllDocumentIDsResponse):
        
        self.__collections: List[AllDocumentsCollection] = []
        for c in response.collection_keys:
            self.__collections.append(AllDocumentsCollection(c, response.documents_for_collection(c)))

class Database:
    @property
    def name(self) -> str:
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
        return DatabaseUpdater(self.__name, self.__request_factory, self.__index)
    
    async def get_all_documents(self, *collections: str) -> AllDocumentsMap:
        payload = PostGetAllDocumentIDsRequestBody(self.__name, *collections)
        req = self.__request_factory.create_request(TestServerRequestType.ALL_DOC_IDS, payload)
        resp = await self.__request_factory.send_request(self.__index, req)
        if resp.error is not None:
            cbl_error("Failed to get all documents (see trace log for details)")
            cbl_trace(resp.error.message)
            return None

        return AllDocumentsMap(cast(PostGetAllDocumentIDsResponse, resp))