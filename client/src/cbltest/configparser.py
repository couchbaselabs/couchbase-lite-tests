from enum import Enum
from json import dumps, load
from logging import warning
from pathlib import Path
from typing import Final

from .jsonhelper import (
    _assert_string_entry,
    _get_bool_or_default,
    _get_int_or_default,
    _get_str_or_default,
    _get_typed,
    _get_typed_nonnull,
)


class TestServerInfo:
    """The parsed Test Server information from the config file"""

    ___url_key: Final[str] = "url"
    __dataset_version_key: Final[str] = "dataset_version"

    @property
    def url(self) -> str:
        """Gets the URL of the test server instance"""
        return self.__url

    @property
    def dataset_version(self) -> str | None:
        """Gets the dataset version of the test server instance"""
        return self.__dataset_version

    def __init__(self, data: dict):
        self.__url: str = _assert_string_entry(data, self.___url_key)
        self.__dataset_version: str | None = None
        if self.__dataset_version_key in data:
            self.__dataset_version = _get_typed(data, self.__dataset_version_key, str)


class SyncGatewayInfo:
    """The parsed Sync Gateway information from the config file"""

    __hostname_key: Final[str] = "hostname"
    __port_key: Final[str] = "port"
    __admin_port_key: Final[str] = "admin_port"
    __rbac_user_key: Final[str] = "rbac_user"
    __rbac_password_key: Final[str] = "rbac_password"
    __tls_key: Final[str] = "tls"

    @property
    def hostname(self) -> str:
        """Gets the hostname of the Sync Gateway instance"""
        return self.__hostname

    @property
    def port(self) -> int:
        """Gets the port to use for normal connection"""
        return self.__port

    @property
    def admin_port(self) -> int:
        """Gets the port to use for admin connection"""
        return self.__admin_port

    @property
    def rbac_user(self) -> str:
        """Gets the user to use when connecting to a CBS cluster"""
        return self.__rbac_user

    @property
    def rbac_password(self) -> str:
        """Gets the password to use when connecting to a CBS cluster"""
        return self.__rbac_password

    @property
    def uses_tls(self) -> bool:
        """Gets whether or not the Sync Gateway is running with TLS"""
        return self.__uses_tls

    def __init__(self, data: dict):
        self.__hostname: str = _assert_string_entry(data, self.__hostname_key)
        self.__port: int = _get_int_or_default(data, self.__port_key, 4984)
        self.__admin_port: int = _get_int_or_default(data, self.__admin_port_key, 4985)
        self.__rbac_user: str = _get_str_or_default(data, self.__rbac_user_key, "admin")
        self.__rbac_password: str = _get_str_or_default(
            data, self.__rbac_password_key, "password"
        )
        self.__uses_tls: bool = _get_bool_or_default(data, self.__tls_key, False)


class CouchbaseServerInfo:
    """The parsed Couchbase Server info from the config file"""

    __hostname_key: Final[str] = "hostname"
    __admin_user_key: Final[str] = "admin_user"
    __admin_password_key: Final[str] = "admin_password"

    @property
    def hostname(self) -> str:
        """Gets the hostname of the Couchbase Server cluster instance"""
        return self.__hostname

    @property
    def admin_user(self) -> str:
        """Gets the user to use when administrating a CBS cluster"""
        return self.__admin_user

    @property
    def admin_password(self) -> str:
        """Gets the password to use when administrating a CBS cluster"""
        return self.__admin_password

    def __init__(self, data: dict):
        self.__hostname: str = _assert_string_entry(data, self.__hostname_key)
        self.__admin_user: str = _get_str_or_default(
            data, self.__admin_user_key, "Administrator"
        )
        self.__admin_password: str = _get_str_or_default(
            data, self.__admin_password_key, "password"
        )


class EdgeServerInfo:
    """The parsed Edge Server information from the config file"""

    __hostname_key: Final[str] = "hostname"
    __admin_user_key: Final[str] = "admin_user"
    __admin_password_key: Final[str] = "admin_password"
    __config_path_key: Final[str] = "config_path"

    @property
    def hostname(self) -> str:
        """Gets the hostname of the Edge Server instance"""
        return self.__hostname

    @property
    def admin_user(self) -> str:
        return self.__admin_user

    @property
    def admin_password(self) -> str:
        return self.__admin_password

    @property
    def config_path(self):
        return self.__config_path

    def _default_config_path(self):
        repo_root = next(
            p
            for p in (Path(__file__).resolve(), *Path(__file__).resolve().parents)
            if p.name == "couchbase-lite-tests"
        )
        return repo_root

    def __init__(self, data: dict):
        self.__hostname: str = _assert_string_entry(data, self.__hostname_key)
        self.__admin_user = _get_str_or_default(
            data, self.__admin_user_key, "admin_user"
        )
        self.__admin_password = _get_str_or_default(
            data, self.__admin_password_key, "password"
        )
        self.__config_path = self.__admin_password = _get_str_or_default(
            data,
            self.__config_path_key,
            f"{self._default_config_path()}/environment/aws/es_setup/config/config.json",
        )


class TransportType(Enum):
    HTTP = "http"
    WS = "ws"


class ParsedConfig:
    """The parsed result of the JSON config file provided to the SDK"""

    __test_server_key: Final[str] = "test-servers"
    __sgw_key: Final[str] = "sync-gateways"
    __cbs_key: Final[str] = "couchbase-servers"
    __lb_key: Final[str] = "load-balancers"
    __es_key: Final[str] = "edge-servers"
    __greenboard_key: Final[str] = "greenboard"
    __api_version_key: Final[str] = "api-version"
    __logslurp_key: Final[str] = "logslurp"
    __dataset_version_key: Final[str] = "dataset_version"

    @property
    def test_servers(self) -> list[dict]:
        """The list of test servers that can be interacted with"""
        return self.__test_servers

    @property
    def sync_gateways(self) -> list[dict]:
        """The list of sync gateways that can be interacted with"""
        return self.__sync_gateways

    @property
    def couchbase_servers(self) -> list[dict]:
        """The list of couchbase servers that can be interacted with"""
        return self.__couchbase_servers

    @property
    def load_balancers(self) -> list[str]:
        """The list of load balancers that can be interacted with"""
        return self.__load_balancers

    @property
    def edge_servers(self) -> list[dict]:
        """The list of edge servers that can be interacted with"""
        return self.__edge_servers

    @property
    def greenboard_url(self) -> str | None:
        """The optional URL to greenboard for uploading results"""
        if self.__greenboard is None:
            return None

        return self.__greenboard["hostname"]

    @property
    def greenboard_username(self) -> str | None:
        """The optional URL to greenboard for uploading results"""
        if self.__greenboard is None:
            return None

        return self.__greenboard["username"]

    @property
    def greenboard_password(self) -> str | None:
        """The optional URL to greenboard for uploading results"""
        if self.__greenboard is None:
            return None

        return self.__greenboard["password"]

    @property
    def logslurp_url(self) -> str | None:
        """The URL of the optional logslurp server to send and collect logs"""
        return self.__logslurp_url

    def __init__(self, json: dict):
        self.__test_servers = _get_typed_nonnull(
            json, self.__test_server_key, list[dict], []
        )
        self.__sync_gateways = _get_typed_nonnull(json, self.__sgw_key, list[dict], [])
        self.__couchbase_servers = _get_typed_nonnull(
            json, self.__cbs_key, list[dict], []
        )
        self.__load_balancers = _get_typed_nonnull(json, self.__lb_key, list[str], [])
        self.__edge_servers = _get_typed_nonnull(json, self.__es_key, list[dict], [])
        if self.__api_version_key in json:
            warning(
                "The 'api-version' field in the config file is deprecated and will be "
                "removed in future versions. Please remove it from your config."
            )

        self.__greenboard = _get_typed(json, self.__greenboard_key, dict[str, str])
        if self.__greenboard is not None and (
            "hostname" not in self.__greenboard
            or "username" not in self.__greenboard
            or "password" not in self.__greenboard
        ):
            raise ValueError(
                "Malformed greenboard entry, must have hostname username and password"
            )

        self.__logslurp_url = _get_typed(json, self.__logslurp_key, str)

    def __str__(self) -> str:
        ret_val = (
            "Test Servers: "
            + dumps(self.__test_servers)
            + "\n"
            + "Sync Gateways: "
            + dumps(self.__sync_gateways)
            + "\n"
            + "Couchbase Servers: "
            + dumps(self.__couchbase_servers)
            + "\n"
            + "Load Balancers: "
            + dumps(self.__load_balancers)
            + "\n"
            + "Edge Servers: "
            + dumps(self.__edge_servers)
            + "\n"
            + "Logslurp URL: "
            + (self.__logslurp_url if self.__logslurp_url is not None else "")
            + "\n"
            + "Greenboard: "
            + (self.__greenboard["url"] if self.__greenboard is not None else "")
        )

        return ret_val


def _parse_config(path: str) -> ParsedConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found at {path}")

    with open(p) as fin:
        json = load(fin)

    if not isinstance(json, dict):
        raise ValueError("Configuration is not a JSON dictionary object")

    return ParsedConfig(dict(json))
