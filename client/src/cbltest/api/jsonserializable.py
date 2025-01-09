from abc import ABC, abstractmethod
from json import dumps
from typing import Any


class JSONSerializable(ABC):
    """A class that can be conveniently serialized to pretty JSON"""

    def serialize(self) -> str:
        """Serializes the object into a pretty formatted JSON string"""
        return dumps(self.to_json(), indent=2)

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
