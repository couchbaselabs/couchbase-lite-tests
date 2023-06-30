from pathlib import Path 
from json import load, dumps
from typing import Final, List, cast

from .jsonhelper import _assert_contains_string_list, _get_int_or_default, _get_string_list, _assert_string_entry

class SyncGatewayInfo:
    """The parsed Sync Gateway information from the config file"""

    __hostname_key: Final[str] = "hostname"
    __port_key: Final[str] = "port"
    __admin_port_key: Final[str] = "admin_port"

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
    
    def __init__(self, data: dict):
        self.__hostname: str = _assert_string_entry(data, self.__hostname_key)
        self.__port: int = _get_int_or_default(data, self.__port_key, 4984)
        self.__admin_port: int = _get_int_or_default(data, self.__admin_port_key, 4985)
    
class ParsedConfig:
    """The parsed result of the JSON config file provided to the SDK"""

    __test_server_key: Final[str] = "test-servers"
    __sgw_key: Final[str] = "sync-gateways"
    __cbs_key: Final[str] = "couchbase-servers"
    __sgw_certs_key: Final[str] = "sync-gateways-tls-certs"
    __greenboard_key: Final[str] = "greenboard"
    __api_version_key: Final[str] = "api-version"

    @property
    def test_servers(self) -> List[str]:
        """The list of test servers that can be interacted with"""
        return self.__test_servers
    
    @property
    def sync_gateways(self) -> List[dict]:
        """The list of sync gateways that can be interacted with"""
        return self.__sync_gateways
    
    @property
    def couchbase_servers(self) -> List[str]:
        """The list of couchbase servers that can be interacted with"""
        return self.__couchbase_servers
    
    @property
    def sync_gateway_certs(self) -> List[str]:
        """The optional list of sync gateway certificates for using TLS"""
        return self.__sync_gateway_certs
    
    # TODO: Greenboard
    
    @property
    def api_version(self) -> int:
        """The passed API version that governs the creation of the request factory"""
        return self.__api_version

    def __init__(self, json: dict):
        self.__test_servers = _assert_contains_string_list(json, self.__test_server_key)
        if self.__sgw_key not in json:
            raise ValueError(f"Missing key in configuration '{self.__sgw_key}'")
        
        self.__sync_gateways = json[self.__sgw_key]
        self.__couchbase_servers = _assert_contains_string_list(json, self.__cbs_key)
        self.__sync_gateway_certs = _get_string_list(json, self.__sgw_certs_key)
        self.__greenboard = cast(str, json.get(self.__greenboard_key))
        self.__api_version = _get_int_or_default(json, self.__api_version_key, 1)

    def __str__(self) -> str:
        ret_val = "API Version: " + self.__api_version + "\n" + \
            "Test Servers: " + dumps(self.__test_servers) + "\n" + \
            "Sync Gateways: " + dumps(self.__sync_gateways)  + "\n" + \
            "Couchbase Servers: " + dumps(self.__couchbase_servers) + "\n" + \
            "TLS Enabled: " + ("Yes" if (self.__sync_gateway_certs is not None) else "No") + "\n" + \
            "Greenboard: " + (self.__greenboard if self.__greenboard is not None else "")
         
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