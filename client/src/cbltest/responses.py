from __future__ import annotations

from enum import Flag, auto
from typing import Any, Final

from cbltest.api.error_types import ErrorResponseBody
from cbltest.api.jsonserializable import JSONSerializable
from cbltest.jsonhelper import _get_typed, _get_typed_required
from cbltest.version import available_api_version


class ServerVariant(Flag):
    ANDROID = auto()
    C = auto()
    DOTNET = auto()
    IOS = auto()
    JVM = auto()

    def __str__(self) -> str:
        return "|".join(
            [
                member.name
                for member in ServerVariant
                if member in self and member.name is not None
            ]
        )


class TestServerResponse(JSONSerializable):
    @property
    def version(self) -> int:
        """Gets the API version of the response, as specified by the remote server"""
        return self.__version

    @property
    def uuid(self) -> str:
        """Gets the UUID of the remote server that sent this response"""
        return self.__uuid

    @property
    def error(self) -> ErrorResponseBody | None:
        """Gets the error sent by the remote server, if any"""
        return self.__error

    def __init__(
        self,
        status_code: int,
        uuid: str,
        version: int,
        body: dict,
        http_name: str,
        http_method: str = "post",
    ):
        self.__version = available_api_version(version)
        self.__status_code = status_code
        self.__uuid = uuid
        self.__error = ErrorResponseBody.create(body)
        self.__payload = body
        self.__http_name = http_name
        self.__http_method = http_method

    def to_json(self) -> Any:
        """Serializes the body of the response to a JSON string"""
        return self.__payload

    def __str__(self) -> str:
        return f"<- {self.__uuid} v{self.__version} {self.__http_method.upper()} /{self.__http_name} {self.__status_code}"


class GetRootResponse(TestServerResponse):
    """
    The response to a GET / request.  It is not versioned like others, and in fact
    itself contains the API version to use.
    """

    __version_key: Final[str] = "version"
    __api_version_key: Final[str] = "apiVersion"
    __cbl_key: Final[str] = "cbl"
    __device_key: Final[str] = "device"
    __additional_info_key: Final[str] = "additionalInfo"
    __variant: ServerVariant | None = None

    @property
    def version(self) -> int:
        """Gets the API version specified by the remote server"""
        return self.__api_version

    @property
    def library_version(self) -> str:
        """Gets the version of Couchbase Lite that the remote server is using"""
        return self.__lib_version

    @property
    def cbl(self) -> str:
        """Gets the variant of Couchbase Lite (e.g. C) that the remote server is using"""
        return self.__cbl

    @property
    def variant(self) -> ServerVariant:
        """Gets the variant of Couchbase Lite (e.g. C) that the remote server is using"""
        if self.__variant is None:
            if self.__cbl == "couchbase-lite-android":
                return ServerVariant.ANDROID
            elif self.__cbl == "couchbase-lite-c":
                return ServerVariant.C
            elif self.__cbl == "couchbase-lite-net":
                return ServerVariant.DOTNET
            elif self.__cbl == "couchbase-lite-ios":
                return ServerVariant.IOS
            elif self.__cbl == "couchbase-lite-java":
                return ServerVariant.JVM
            elif self.__cbl == "couchbase-lite-swift":
                # Treat the new Swift-based test server variant as iOS for compatibility.
                return ServerVariant.IOS
            else:
                raise ValueError(f"Unknown test server variant: {self.__cbl}")

        return self.__variant

    @property
    def device(self) -> dict:
        """Gets details about the device that the remote server is running on"""
        return self.__device

    @property
    def additional_info(self) -> str | None:
        """ "Gets any additional info that the server happens to send"""
        return self.__additional_info

    def __init__(self, status_code: int, uuid: str, json: dict):
        self.__lib_version = _get_typed_required(json, self.__version_key, str)
        self.__api_version = _get_typed_required(json, self.__api_version_key, int)
        self.__cbl = _get_typed_required(json, self.__cbl_key, str)
        self.__device = _get_typed_required(json, self.__device_key, dict)
        self.__additional_info = _get_typed(json, self.__additional_info_key, str)

        super().__init__(status_code, uuid, self.__api_version, json, "", "get")
