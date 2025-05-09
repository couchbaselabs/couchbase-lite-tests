from abc import ABC, abstractmethod
from json import dumps
from typing import Any


class JSONSerializable(ABC):
    """A class that can be conveniently serialized to pretty JSON"""

    def serialize(self) -> str:
        """Serializes the object into a pretty formatted JSON string"""

        def fallback_serializer(obj: Any) -> Any:
            if isinstance(obj, JSONSerializable):
                return obj.to_json()

            return obj

        return dumps(self.to_json(), indent=2, default=fallback_serializer)

    @abstractmethod
    def to_json(self) -> Any:
        """Converts the object into a JSON compatible one"""
        pass


class JSONDictionary(JSONSerializable):
    """A helper class to wrap a literal dictionary into JSONSerializable"""

    def __init__(self, d: dict):
        self.__dict = d

    def to_json(self) -> Any:
        return self.__dict
