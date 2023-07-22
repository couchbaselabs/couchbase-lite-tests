from abc import abstractmethod
from enum import Enum
from typing import Dict, Final, List, cast
from varname import nameof

from cbltest.assertions import _assert_not_null
from cbltest.responses import ErrorResponseBody
from cbltest.api.jsonserializable import JSONSerializable

class ReplicatorPushFilterParameters(JSONSerializable):
    """
    A class representing parameters to be passed to a push filter.
    In theory this could be anything, but in practice it has always been
    just documentIDs.
    """

    def __init__(self) -> None:
        self.document_ids: List[str] = None
        """The document IDs to filter, if any"""

    def to_json(self) -> any:
        if self.document_ids is None:
            return None
        
        return {
            "documentIDs": self.document_ids
        }

class ReplicatorPushFilter(JSONSerializable):
    """
    A class representing a push filter to use on a replication to limit
    the documents that get sent from local to remote.
    """

    @property
    def name(self) -> str:
        """Gets the name of the push filter"""
        return self.__name
    
    def __init__(self, name: str):
        self.__name = name
        self.parameters = cast(ReplicatorPushFilterParameters, None)
        """The parameters to be applied to the push filter"""

    def to_json(self) -> any:
        ret_val = {"name": self.name}
        if self.parameters is not None:
            ret_val["params"] = self.parameters.to_json()

class ReplicatorCollectionEntry(JSONSerializable):
    @property
    def names(self) -> List[str]:
        """Gets the name of the collection that the options will be applied to"""
        return self.__names
    
    def __init__(self, names: List[str] = ["_default"], channels: List[str] = None, document_ids: List[str] = None,
                 push_filter: ReplicatorPushFilter = None):
        _assert_not_null(names, nameof(names))
        assert len(names) > 0, "Must specify at least one name in the names array for ReplicatorCollectionEntry"

        self.__names = names
        self.channels = channels
        """A list of channels to use when replicating with this collection"""

        self.document_ids = document_ids
        """A list of document IDs to consider with this collection, other docs will be ignored"""

        self.push_filter = push_filter
        """The push filter to use for this collection, if any"""

    def to_json(self) -> any:
        ret_val = {
            "names": self.__names
        }

        if self.channels is not None:
            ret_val["channels"] = self.channels

        if self.document_ids is not None:
            ret_val["documentIDs"] = self.document_ids

        if self.push_filter is not None:
            ret_val["pushFilter"] = self.push_filter.to_json()

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
    def to_json(self) -> any:
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

    def to_json(self) -> any:
        """Transforms the :class:`ReplicatorBasicAuthenticator` into a JSON dictionary"""
        return {
            "type": self.type,
            "username": self.__username,
            "password": self.__password
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
    
    def __init__(self, session_id: str, cookie_name: str = "SyncGatewaySession") -> None:
        super().__init__("SESSION")
        self.__session_id = session_id
        self.__cookie_name = cookie_name

    def to_json(self) -> any:
        return {
            "type": self.type,
            "sessionID": self.__session_id,
            "cookieName": self.__cookie_name
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
        assert isinstance(body, dict), "Invalid replicator progress value received (not an object)"
        self.__completed = cast(bool, body.get(self.__completed_key))
        assert isinstance(self.__completed, bool), "Invalid replicator progress value received ('completed' not a boolean)"

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
    def flags(self) -> int:
        """Gets the flags that were set on the document when it was replicated"""
        return self.__flags
    
    @property
    def error(self) -> ErrorResponseBody:
        """Gets the error that prevented the document from being replicated, if any"""
        return self.__error

    def __init__(self, body: dict) -> None:
        assert isinstance(body, dict), "Invalid replicator document received (not an object)"
        self.__collection = cast(str, body.get(self.__collection_key))
        assert isinstance(self.__collection, str), "Invalid replicator document collection received (not a str)"
        assert self.__collection is not None, "Null collection on replicator document received"
        self.__document_id = cast(str, body.get(self.__document_id_key))
        assert isinstance(self.__document_id, str), "Invalid replicator document ID received (not a str)" 
        assert self.__document_id is not None, "Null ID on replicator document received"
        self.__is_push = cast(bool, body.get(self.__is_push_key))
        assert isinstance(self.__is_push, bool), "Invalid replicator document isPush received (not a boolean)"
        self.__flags = cast(int, body.get(self.__flags_key))
        assert isinstance(self.__flags, int), "Invalid replicator document flags received (not an int)"
        self.__error = ErrorResponseBody.create(body.get(self.__error_key))
    
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
    def error(self) -> ErrorResponseBody:
        """Gets the error for the Replicator, if any"""
        return self.__error
    
    def __init__(self, progress: ReplicatorProgress, activity: ReplicatorActivityLevel, error: ErrorResponseBody):
        self.__progress = progress
        self.__activity = activity
        self.__error = error