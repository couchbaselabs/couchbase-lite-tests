from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, cast
from uuid import UUID

from aiohttp import ClientResponse

from cbltest.api.jsonserializable import JSONSerializable
from cbltest.assertions import _assert_not_null
from cbltest.globals import CBLPyTestGlobal
from cbltest.responses import GetRootResponse, TestServerResponse
from cbltest.version import available_api_version


class TestServerRequest:
    """The base class from which all requests derive, and in which all work is done"""

    @property
    def payload(self) -> JSONSerializable | None:
        """Gets the body of the request.  The actual type is simply the request typename with 'Body' appended.

        E.g. PostResetRequest -> PostResetRequestBody"""
        return self.__payload

    @property
    def version(self) -> int:
        """Gets the API version of the request"""
        return self.__version

    @property
    def uuid(self) -> str:
        """Gets the UUID of the client sending this request"""
        return str(self.__uuid)

    @property
    def http_name(self) -> str:
        """Gets the HTTP endpoint name of this request"""
        return self.__http_name

    @property
    def method(self) -> str:
        """Gets the HTTP method of this request"""
        return self.__method

    def __init__(
        self,
        version: int,
        uuid: UUID,
        http_name: str,
        payload_type: type | None = None,
        method: str = "post",
        payload: JSONSerializable | None = None,
    ):
        # For those subclassing this, usually all you need to do is call this constructor
        # filling out the appropriate information via args
        if payload is not None and payload_type is not None:
            assert isinstance(payload, payload_type), (
                f"Incorrect payload type for request (expecting '{payload_type}')"
            )

        self.__version = available_api_version(version)
        self.__uuid = uuid
        self.__payload = payload
        self.__http_name = http_name
        self.__method = method
        self.__test_name = CBLPyTestGlobal.running_test_name

    def __str__(self) -> str:
        test_name = (
            self.__test_name if self.__test_name is not None else "test name not set!"
        )
        return f"({test_name}) -> {self.__uuid} v{self.__version} {self.__method.upper()} /{self.__http_name}"


# Only this request is not versioned
class GetRootRequest(TestServerRequest):
    """
    The GET / request.  This API endpoint is not versioned and can be used to
    verify the API version of the server, among other things
    """

    def __init__(self, uuid: UUID):
        super().__init__(0, uuid, "", method="get")

    async def _create_response(
        self,
        uuid: str,
        *,
        http: ClientResponse | None = None,
        ws_payload: dict | None = None,
    ) -> TestServerResponse:
        if http is not None:
            return GetRootResponse(http.status, uuid, await http.json())

        if ws_payload is None:
            raise ValueError("Both http and ws_payload were None for GetRootRequest")

        status = 200
        error = cast(dict | None, ws_payload.get("ts_error"))
        if error is not None:
            status = cast(int, error.get("code", 500))

        return GetRootResponse(status, uuid, ws_payload)


class PostResetRequestMethods(ABC):
    @abstractmethod
    def add_dataset(self, url: str, result_db_names: list[str]) -> None:
        pass

    @abstractmethod
    def add_empty(
        self, result_db_names: list[str], collections: list[str] | None = None
    ):
        pass


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
