from typing import Any
from cbltest.api.jsonserializable import JSONSerializable


class SnapshotDocumentEntry(JSONSerializable):
    """
    A class for recording the fully qualified name of a document to be saved in a snapshot.
    This class is used in conjunction with :class:`PostSnapshotDocumentsRequestBody`
    """
    def __init__(self, collection: str, id: str):
        self.collection: str = collection
        """The collection that the snapshotted document belongs to"""

        self.id: str = id
        """The ID of the snapshotted document"""

    def to_json(self) -> Any:
        return {"collection": self.collection, "id": self.id}