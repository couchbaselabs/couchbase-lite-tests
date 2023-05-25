from pathlib import Path 
from json import load, dumps
from typing import Final, List, cast

from .jsonhelper import _assert_contains_string_list, _get_string_list
    
class ParsedConfig:
    __test_server_key: Final[str] = "test-servers"
    __sgw_key: Final[str] = "sync-gateways"
    __cbs_key: Final[str] = "couchbase-servers"
    __sgw_certs_key: Final[str] = "sync-gateways-tls-certs"
    __greenboard_key: Final[str] = "greenboard"

    @property
    def test_servers(self) -> List[str]:
        return self.__test_servers
    
    @property
    def sync_gateways(self) -> List[str]:
        return self.__sync_gateways
    
    @property
    def couchbase_servers(self) -> List[str]:
        return self.__couchbase_servers
    
    @property
    def sync_gateway_certs(self) -> List[str]:
        return self.__sync_gateway_certs
    
    @property
    def greenboard(self) -> str:
        return self.__greenboard

    def __init__(self, json: dict):
        self.__test_servers = _assert_contains_string_list(json, self.__test_server_key)
        self.__sync_gateways = _assert_contains_string_list(json, self.__sgw_key)
        self.__couchbase_servers = _assert_contains_string_list(json, self.__cbs_key)
        self.__sync_gateway_certs = _get_string_list(json, self.__sgw_certs_key)
        self.__greenboard = cast(str, json.get(self.__greenboard_key))

    def __str__(self) -> str:
        ret_val = "Test Servers: " + dumps(self.__test_servers) + "\n" + \
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