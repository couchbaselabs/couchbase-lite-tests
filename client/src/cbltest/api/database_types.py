from enum import Enum
from typing import Any

from cbltest.api.jsonserializable import JSONSerializable


class DocumentEntry(JSONSerializable):
    """
    A class for recording the fully qualified name of a document in any database
    """

    def __init__(self, collection: str, id: str):
        self.collection: str = collection
        """The collection that the snapshotted document belongs to"""

        self.id: str = id
        """The ID of the snapshotted document"""

    def to_json(self) -> Any:
        return {"collection": self.collection, "id": self.id}


class MaintenanceType(Enum):
    """An enum representing a type of maintenance operation on a database"""

    COMPACT = "compact"
    """Compacts the database and removes unused blobs to reduce the disk footprint"""

    INTEGRITY_CHECK = "integrityCheck"
    """Runs a diagnostic check on the database to check for any low level corruption errors"""

    OPTIMIZE = "optimize"
    """Quickly update db statistics to help optimize queries"""

    FULL_OPTIMIZE = "fullOptimize"
    """Full update of db statistics; takes longer than Optimize"""

    def __str__(self) -> str:
        return self.value


class EncryptedValue(JSONSerializable):
    """A class for holding the encrypted property of a database.
    Note this it is only supported on the C test server.
    """

    @property
    def value(self) -> str:
        """The value of the property"""
        return self.__value

    def __init__(self, value: str):
        self.__value: str = value

    def to_json(self) -> Any:
        return {
            "@type": "encryptable",
            "value": self.__value,
        }
