from __future__ import annotations

from abc import abstractmethod
from enum import Enum, Flag, auto
from typing import Any, Final, cast

from cbltest.api.jsonserializable import JSONSerializable
from cbltest.assertions import _assert_not_empty
from cbltest.jsonhelper import _get_typed_required
from cbltest.responses import ErrorResponseBody


class ReplicatorFilter(JSONSerializable):
    """
    A class representing a filter to use on a replication to limit
    the documents that get sent.
    """

    @property
    def name(self) -> str:
        """Gets the name of the filter"""
        return self.__name

    def __init__(self, name: str, parameters: dict | None = None):
        self.__name = name
        self.parameters = parameters
        """The parameters to be applied to the filter"""

    def to_json(self) -> Any:
        ret_val: dict[str, Any] = {"name": self.name}
        if self.parameters is not None:
            ret_val["params"] = self.parameters

        return ret_val


class ReplicatorConflictResolver(JSONSerializable):
    """
    A class representing a conflict resolver to use on a replication.
    """

    @property
    def name(self) -> str:
        """Gets the name of the resolver"""
        return self.__name

    def __init__(self, name: str, parameters: dict | None = None):
        self.__name = name
        self.parameters = parameters
        """The parameters to be applied to the resolver"""

    def to_json(self) -> Any:
        ret_val: dict[str, Any] = {"name": self.name}
        if self.parameters is not None:
            ret_val["params"] = self.parameters

        return ret_val


class ReplicatorCollectionEntry(JSONSerializable):
    @property
    def names(self) -> list[str]:
        """Gets the name of the collection that the options will be applied to"""
        return self.__names

    def __init__(
        self,
        names: list[str] | None = None,
        channels: list[str] | None = None,
        document_ids: list[str] | None = None,
        push_filter: ReplicatorFilter | None = None,
        pull_filter: ReplicatorFilter | None = None,
        conflict_resolver: ReplicatorConflictResolver | None = None,
    ):
        if names is None:
            self.__names = ["_default._default"]
        else:
            _assert_not_empty(names, "names")
            self.__names = names

        self.channels = channels
        """A list of channels to use when replicating with this collection"""

        self.document_ids = document_ids
        """A list of document IDs to consider with this collection, other docs will be ignored"""

        self.push_filter = push_filter
        """The push filter to use for this collection, if any"""

        self.pull_filter = pull_filter
        """The pull filter to use for this collection, if any"""

        self.conflict_resolver = conflict_resolver
        """The name of the one of the predefined conflict resolvers to use in this replication"""

    def to_json(self) -> Any:
        ret_val: dict[str, Any] = {"names": self.__names}

        if self.channels is not None:
            ret_val["channels"] = self.channels

        if self.document_ids is not None:
            ret_val["documentIDs"] = self.document_ids

        if self.push_filter is not None:
            ret_val["pushFilter"] = self.push_filter.to_json()

        if self.pull_filter is not None:
            ret_val["pullFilter"] = self.pull_filter.to_json()

        if self.conflict_resolver is not None:
            ret_val["conflictResolver"] = self.conflict_resolver.to_json()

        return ret_val


class ReplicatorType(Enum):
    """An enum representing the direction of a replication"""

    PUSH = "push"
    """Local to remote only"""

    PULL = "pull"
    """Remote to local only"""

    PUSH_AND_PULL = "pushAndPull"
    """Bidirectional"""

    def __str__(self) -> str:
        return self.value


class ReplicatorAuthenticator(JSONSerializable):
    """
    The base class for replicator authenticators
    """

    @property
    def type(self) -> str:
        """Gets the type of authenticator (required for all authenticators)"""
        return self.__type

    def __init__(self, type: str) -> None:
        self.__type = type

    @abstractmethod
    def to_json(self) -> Any:
        pass


class ReplicatorBasicAuthenticator(ReplicatorAuthenticator):
    """A class holding information to perform HTTP Basic authentication"""

    @property
    def username(self) -> str:
        """Gets the username that will be used for auth"""
        return self.__username

    def password(self) -> str:
        """Gets the password that will be used for auth"""
        return self.__password

    def __init__(self, username: str, password: str) -> None:
        super().__init__("BASIC")
        self.__username = username
        self.__password = password

    def to_json(self) -> Any:
        """Transforms the :class:`ReplicatorBasicAuthenticator` into a JSON dictionary"""
        return {
            "type": self.type,
            "username": self.__username,
            "password": self.__password,
        }


class ReplicatorSessionAuthenticator(ReplicatorAuthenticator):
    """A class holding information to authenticate via session cookie"""

    @property
    def session_id(self) -> str:
        """Gets the session ID that will be used for auth"""
        return self.__session_id

    @property
    def cookie_name(self) -> str:
        """Gets the cookie name that will be used for auth"""
        return self.__cookie_name

    def __init__(
        self, session_id: str, cookie_name: str = "SyncGatewaySession"
    ) -> None:
        super().__init__("SESSION")
        self.__session_id = session_id
        self.__cookie_name = cookie_name

    def to_json(self) -> Any:
        return {
            "type": self.type,
            "sessionID": self.__session_id,
            "cookieName": self.__cookie_name,
        }


class ReplicatorActivityLevel(Enum):
    """An enum representing the activity level of a replicator"""

    STOPPED = "STOPPED"
    """The replicator is stopped and will no longer perform any action"""

    OFFLINE = "OFFLINE"
    """The replicator is unable to connect to the remote endpoint and will try
    again later"""

    CONNECTING = "CONNECTING"
    """The replicator is establishing a connection to the remote endpoint"""

    IDLE = "IDLE"
    """The replicator is idle and waiting for more information"""

    BUSY = "BUSY"
    """The replicator is actively processing information"""

    def __str__(self) -> str:
        return self.value


class ReplicatorProgress:
    """A class representing the progress of a replicator in terms of units and documents complete"""

    __completed_key: Final[str] = "completed"

    @property
    def completed(self) -> bool:
        """Gets the number of units completed so far"""
        return self.__completed

    def __init__(self, body: dict) -> None:
        assert isinstance(body, dict), (
            "Invalid replicator progress value received (not an object)"
        )
        self.__completed = cast(bool, body.get(self.__completed_key))
        assert isinstance(self.__completed, bool), (
            "Invalid replicator progress value received ('completed' not a boolean)"
        )


class ReplicatorDocumentFlags(Flag):
    NONE = 0
    """The absence of flags"""

    DELETED = auto()
    """A flag indicating the document was deleted by another party"""

    ACCESS_REMOVED = auto()
    """A flag indicating that this replicator lost access to a document"""

    @classmethod
    def parse(cls, input: str) -> ReplicatorDocumentFlags:
        """
        Parses a single string word into a flag value.

        :param input: The string representing the flag (e.g. DELETED), case-insensitive
        """
        assert isinstance(input, str), (
            f"Non-string input to ReplicatorDocumentFlags {input}"
        )
        upper = input.upper()
        if upper == "NONE":
            return ReplicatorDocumentFlags.NONE

        if upper == "DELETED":
            return ReplicatorDocumentFlags.DELETED

        if upper == "ACCESSREMOVED":
            return ReplicatorDocumentFlags.ACCESS_REMOVED

        raise ValueError(f"Unrecognized input ReplicatorDocumentFlags {input}")

    @classmethod
    def parse_all(cls, input: list[str]) -> ReplicatorDocumentFlags:
        """
        Parses and ORs a list of string words representing flags

        :param input: The list of string words each representing a flag (e.g. DELETED), case-insensitive
        """
        ret_val = ReplicatorDocumentFlags.NONE
        for i in input:
            ret_val |= cls.parse(i)

        return ret_val

    def __str__(self) -> str:
        if self == ReplicatorDocumentFlags.NONE:
            return "NONE"

        flags = []
        # https://github.com/python/mypy/issues/9642
        # Need to cast self to not be Literal type
        uncast_self = cast(ReplicatorDocumentFlags, self)
        if uncast_self & ReplicatorDocumentFlags.DELETED:
            flags.append("DELETED")

        if uncast_self & ReplicatorDocumentFlags.ACCESS_REMOVED:
            flags.append("ACCESSREMOVED")

        return "|".join(flags)


class ReplicatorDocumentEntry:
    """A class representing the status of a replicated document"""

    __collection_key: Final[str] = "collection"
    __document_id_key: Final[str] = "documentID"
    __is_push_key: Final[str] = "isPush"
    __flags_key: Final[str] = "flags"
    __error_key: Final[str] = "error"

    @property
    def collection(self) -> str:
        """Gets the collection that the document belongs to"""
        return self.__collection

    @property
    def document_id(self) -> str:
        """Gets the ID of the document"""
        return self.__document_id

    @property
    def is_push(self) -> bool:
        """Gets whether the document was pushed or pulled"""
        return self.__is_push

    @property
    def direction(self) -> ReplicatorType:
        """Gets the direction of the replicator, based on is_push"""
        return ReplicatorType.PUSH if self.__is_push else ReplicatorType.PULL

    @property
    def flags(self) -> ReplicatorDocumentFlags:
        """Gets the flags that were set on the document when it was replicated"""
        return self.__flags

    @property
    def error(self) -> ErrorResponseBody | None:
        """Gets the error that prevented the document from being replicated, if any"""
        return self.__error

    def __init__(self, body: dict) -> None:
        assert isinstance(body, dict), (
            "Invalid replicator document received (not an object)"
        )
        self.__collection = _get_typed_required(body, self.__collection_key, str)
        assert self.__collection is not None, (
            "Null collection on replicator document received"
        )
        self.__document_id = _get_typed_required(body, self.__document_id_key, str)
        assert self.__document_id is not None, "Null ID on replicator document received"
        self.__is_push = _get_typed_required(body, self.__is_push_key, bool)
        self.__flags = ReplicatorDocumentFlags.parse_all(
            _get_typed_required(body, self.__flags_key, list[str])
        )
        self.__error: ErrorResponseBody | None = ErrorResponseBody.create(
            cast(dict, body.get(self.__error_key))
        )


class WaitForDocumentEventEntry:
    """
    A class that represents a single replicator document event to wait for from
    a replicator's document listener
    """

    @property
    def collection(self) -> str:
        """Gets the collection of the document to wait for"""
        return self.__collection

    @property
    def id(self) -> str:
        """Gets the ID of the document to wait for"""
        return self.__id

    @property
    def direction(self) -> ReplicatorType:
        """Gets the direction of the event to wait for.  Events that otherwise match
        (e.g. have the same document ID) will be ignored"""
        return self.__direction

    @property
    def flags(self) -> ReplicatorDocumentFlags | None:
        """Gets the flags of the event to wait for.  Events that otherwise match
        (e.g. have the same document ID) will be ignored"""
        return self.__flags

    def __init__(
        self,
        collection: str,
        id: str,
        direction: ReplicatorType,
        flags: ReplicatorDocumentFlags | None,
        err_domain: str | None = None,
        err_code: int | None = None,
    ):
        assert isinstance(collection, str), (
            "WaitForDocumentEventEntry: collection not a string"
        )
        assert isinstance(id, str), "WaitForDocumentEventEntry: id not a string"
        self.__collection = collection
        self.__id = id
        self.__direction = direction
        self.__flags = flags
        self.__err_domain = err_domain
        self.__err_code = err_code

    def __hash__(self) -> int:
        return hash(f"{self.__collection}{self.__id}")

    def __eq__(self, obj: Any) -> bool:
        if not isinstance(obj, WaitForDocumentEventEntry):
            return False
        other = cast(WaitForDocumentEventEntry, obj)

        return (
            (self.__collection == other.__collection and self.__id == other.__id)
            and (self.__err_domain == other.__err_domain)
            and (self.__err_code == other.__err_code)
            and (
                self.__direction == other.__direction
                or self.__direction == ReplicatorType.PUSH_AND_PULL
                or other.__direction == ReplicatorType.PUSH_AND_PULL
            )
            and (
                self.__flags == other.__flags
                or self.__flags is None
                or other.__flags is None
            )
        )

    def __str__(self) -> str:
        return f"WaitForDocumentEventEntry({self.__collection}.{self.__id} {self.__direction} ({self.__flags}) [{self.__err_domain}, {self.__err_code}])"


class ReplicatorStatus:
    """
    A class representing the current status (activity, progress, error, etc) of a Replicator
    """

    @property
    def progress(self) -> ReplicatorProgress:
        """Gets the progress numbers for the Replicator"""
        return self.__progress

    @property
    def activity(self) -> ReplicatorActivityLevel:
        """Gets the activity level for the Replicator"""
        return self.__activity

    @property
    def error(self) -> ErrorResponseBody | None:
        """Gets the error for the Replicator, if any"""
        return self.__error

    def __init__(
        self,
        progress: ReplicatorProgress,
        activity: ReplicatorActivityLevel,
        error: ErrorResponseBody | None,
    ):
        self.__progress = progress
        self.__activity = activity
        self.__error = error
