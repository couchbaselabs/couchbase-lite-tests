from pathlib import Path
from typing import Dict, List, Optional, cast

from .requests import RequestFactory
from .logging import LogLevel, cbl_setLogLevel, cbl_log_init
from .extrapropsparser import _parse_extra_props
from .configparser import CouchbaseServerInfo, ParsedConfig, SyncGatewayInfo, _parse_config
from .assertions import _assert_not_null
from .api.testserver import TestServer
from .api.syncgateway import SyncGateway
from .api.couchbaseserver import CouchbaseServer
from varname import nameof
from sys import version_info
from json import dumps

if version_info < (3, 9):
    raise RuntimeError("Python must be at least v3.9!")

class CBLPyTest:
    """
    This is the top level class that users will interact with when using this test client SDK.  For the moment,
    it parsed the passed configuration and creates an appropriate request factory
    """

    @property
    def config(self) -> ParsedConfig:
        """Gets the config as parsed from the provided JSON file path"""
        return self.__config
    
    @property
    def log_level(self) -> LogLevel:
        """Gets the log level provided"""
        return self.__log_level
    
    @property
    def extra_props(self) -> Optional[Dict[str, str]]:
        """Gets the extra properties provided as parsed from the provided JSON file path"""
        return self.__extra_props
    
    @property
    def request_factory(self) -> RequestFactory:
        """Gets the request factory for creating and sending requests to the test server"""
        return self.__request_factory
    
    @property
    def test_servers(self) -> List[TestServer]:
        return self.__test_servers
    
    @property
    def sync_gateways(self) -> List[SyncGateway]:
        return self.__sync_gateways
    
    @property
    def couchbase_servers(self) -> List[CouchbaseServer]:
        return self.__couchbase_servers
    
    @staticmethod
    async def create(config_path: str, log_level: LogLevel = LogLevel.VERBOSE, extra_props_path: Optional[str] = None, 
                 test_server_only: bool = False):
        ret_val = CBLPyTest(config_path, log_level, extra_props_path, test_server_only)
        cbl_log_init(str(ret_val.request_factory.uuid), ret_val.config.logslurp_url)
        
        ts_index = 0
        for ts in ret_val.test_servers:
            await ts.new_session(str(ret_val.request_factory.uuid), ret_val.config.logslurp_url, f"test-server[{ts_index}]")
            ts_index += 1

        return ret_val
    
    def __init__(self, config_path: str, log_level: LogLevel = LogLevel.VERBOSE, extra_props_path: Optional[str] = None, 
                 test_server_only: bool = False):
        _assert_not_null(config_path, nameof(config_path))
        self.__config = _parse_config(config_path)
        self.__log_level = LogLevel(log_level)
        cbl_setLogLevel(self.__log_level)
        self.__extra_props = None
        if extra_props_path is not None:
            self.__extra_props = _parse_extra_props(extra_props_path)

        self.__request_factory = RequestFactory(self.__config)
        self.__test_servers: List[TestServer] = []
        index = 0
        for url in self.__config.test_servers:
            self.__test_servers.append(TestServer(self.__request_factory, index, url))
            index += 1

        self.__sync_gateways: List[SyncGateway] = []
        index = 0
        if not test_server_only:
            for sg in self.__config.sync_gateways:
                sgw_info = SyncGatewayInfo(sg)
                self.__sync_gateways.append(SyncGateway(sgw_info.hostname, sgw_info.rbac_user, sgw_info.rbac_password, 
                                                        sgw_info.port, sgw_info.admin_port, sgw_info.uses_tls))
                index += 1

        self.__couchbase_servers: List[CouchbaseServer] = []
        if not test_server_only:
            for cbs in self.__config.couchbase_servers:
                cbs_info = CouchbaseServerInfo(cbs)
                self.__couchbase_servers.append(CouchbaseServer(cbs_info.hostname, cbs_info.admin_user, cbs_info.admin_password))


    def __str__(self) -> str:
        ret_val = "Configuration:" + "\n" + str(self.__config) + "\n\n" + \
            "Log Level: " + str(self.__log_level)
        
        if self.__extra_props is not None:
            ret_val += "\n" + "Extra Properties:" + "\n" + dumps(self.__extra_props)

        return ret_val