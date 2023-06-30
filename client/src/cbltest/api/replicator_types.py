from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Final, List, cast
from varname import nameof

from ..assertions import _assert_not_null
from ..responses import ErrorResponseBody


class ReplicatorPushFilterParameters:
    """
    A class representing parameters to be passed to a push filter.
    In theory this could be anything, but in practice it has always been
    just documentIDs.
    """

    def __init__(self) -> None:
        self.document_ids: List[str] = None
        """The document IDs to filter, if any"""

    def to_dict(self) -> Dict[str, any]:
        """Transforms the :class:`ReplicatorPushFilterParameters` into a JSON dictionary"""
        if self.document_ids is None:
            return None
        
        return {
            "documentIDs": self.document_ids
        }

class ReplicatorPushFilter:
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

    def to_dict(self) -> Dict[str, any]:
        """Transforms the :class:`ReplicatorPushFilter` into a JSON dictionary"""
        ret_val = {"name": self.name}
        if self.parameters is not None:
            ret_val["params"] = self.parameters.to_dict()

class ReplicatorCollectionEntry:
    @property
    def name(self) -> str:
        return self.__name
    
    def __init__(self, name: str = "_default", channels: List[str] = None, document_ids: List[str] = None,
                 push_filter: ReplicatorPushFilter = None):
        _assert_not_null(name, nameof(name))
        self.__name = name
        self.channels = channels
        self.document_ids = document_ids
        self.push_filter = push_filter

    def to_dict(self) -> Dict[str, any]:
        ret_val = {
            "collection": self.__name
        }

        if self.channels is not None:
            ret_val["channels"] = self.channels

        if self.document_ids is not None:
            ret_val["documentIDs"] = self.document_ids

        if self.push_filter is not None:
            ret_val["pushFilter"] = self.push_filter.to_dict()

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
    
class ReplicatorAuthenticator(ABC):
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
    def to_dict(self) -> Dict[str, any]:
        return None
    
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
        super().__init__("basic")
        self.__username = username
        self.__password = password

    def to_dict(self) -> Dict[str, any]:
        """Transforms the :class:`ReplicatorBasicAuthenticator` into a JSON dictionary"""
        return {
            "type": "basic",
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
        super().__init__("session")
        self.__session_id = session_id
        self.__cookie_name = cookie_name

    def to_dict(self) -> Dict[str, any]:
        """Transforms the :class:`ReplicatorSessionAuthenticator` into a JSON dictionary"""
        return {
            "type": "session",
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

    __complete_key: Final[str] = "complete"
    __document_count_key: Final[str] = "documentCount"

    @property
    def complete(self) -> float:
        """Gets the number of units completed so far"""
        return self.__complete
    
    @property
    def document_count(self) -> int:
        """Gets the number of documents processed so far"""
        return self.__document_count
    
    def __init__(self, body: dict) -> None:
        assert(isinstance(body, dict))
        self.__complete = cast(float, body.get(self.__complete_key))
        self.__document_count = cast(int, body.get(self.__document_count_key))
        assert(isinstance(self.__complete, float))
        assert(isinstance(self.__document_count, int))

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
        assert(isinstance(body, dict))
        self.__collection = cast(str, body.get(self.__collection_key))
        assert(self.__collection is not None)
        self.__document_id = cast(str, body.get(self.__document_id_key))
        assert(self.__document_id is not None)
        self.__is_push = cast(bool, body.get(self.__is_push_key))
        self.__flags = cast(int, body.get(self.__flags_key))
        self.__error = ErrorResponseBody.create(body.get(self.__error_key))
    
class ReplicatorStatus:
    @property
    def progress(self) -> ReplicatorProgress:
        return self.__progress
    
    @property
    def activity(self) -> ReplicatorActivityLevel:
        return self.__activity
    
    @property
    def error(self) -> ErrorResponseBody:
        return self.__error
    
    def __init__(self, progress: ReplicatorProgress, activity: ReplicatorActivityLevel, error: ErrorResponseBody):
        self.__progress = progress
        self.__activity = activity
        self.__error = error