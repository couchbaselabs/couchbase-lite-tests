from abc import ABC, abstractmethod
from json import dumps


class JSONSerializable(ABC):
    def serialize(self) -> str:
        return dumps(self.to_json(), indent=2)

    @abstractmethod
    def to_json(self) -> any:
        pass