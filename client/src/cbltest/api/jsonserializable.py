from abc import ABC, abstractmethod
from json import dumps

class JSONSerializable(ABC):
    """A class that can be conveniently serialized to pretty JSON"""
    def serialize(self) -> str:
        """Serializes the object into a pretty formatted JSON string"""
        return dumps(self.to_json(), indent=2)

    @abstractmethod
    def to_json(self) -> any:
        """Converts the object into a JSON compatible one"""
        pass