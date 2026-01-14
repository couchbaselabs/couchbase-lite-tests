from abc import abstractmethod
from enum import Flag, auto
from typing import Any, cast

from cbltest.api.jsonserializable import JSONSerializable
from cbltest.api.x509_certificate import CertKeyPair


class MultipeerTransportType(Flag):
    """The transport types supported by the Multipeer Replicator"""

    WIFI = auto()
    BLUETOOTH = auto()
    ALL = WIFI | BLUETOOTH

    def to_json(self) -> list[str]:
        cls = type(self)
        # only single-bit members, and only those present in self
        return [
            cast(str, m.name)
            for m in cls
            if m.value != 0 and (m.value & (m.value - 1)) == 0 and (self & m) == m
        ]


class MultipeerReplicatorAuthenticator(JSONSerializable):
    """
    The base class for replicator authenticators
    """

    @property
    def name(self) -> str:
        """Gets the type of authenticator (required for all authenticators)"""
        return self.__name

    def __init__(self, name: str) -> None:
        self.__name = name

    @abstractmethod
    def to_json(self) -> Any:
        pass


class MultipeerReplicatorCAAuthenticator(MultipeerReplicatorAuthenticator):
    """
    Represents an authenticator based on a CA certificate.  Use the
    :class:`cbltest.api.x509_certificate.X509Generator` if you need to generate a CA certificate.
    """

    def __init__(self, ca_data: CertKeyPair) -> None:
        super().__init__("CA-CERT")
        self.__ca_data = ca_data

    def to_json(self) -> dict[str, Any]:
        return {
            "type": self.name,
            "params": {"certificate": self.__ca_data.pem_bytes().decode("utf-8")},
        }
