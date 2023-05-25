from logging import warning
from pathlib import Path
from typing import Dict

from .responses import GetRootResponse
from .extrapropsparser import _parse_extra_props
from .configparser import ParsedConfig, _parse_config
from .assertions import _assert_not_null
from varname import nameof
from enum import Enum
from sys import version_info
from json import dumps

from requests import Response, get

if version_info < (3, 9):
    raise RuntimeError("Python must be at least v3.9!")

class LogLevel(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    VERBOSE = "verbose"
    DEBUG = "debug"

class CBLPyTest:
    @property
    def config(self) -> ParsedConfig:
        return self.__config
    
    @property
    def log_level(self) -> LogLevel:
        return self.__log_level
    
    @property
    def extra_props(self) -> Dict[str, str]:
        return self.__extra_props
    
    @property
    def output_path(self) -> Path:
        return self.__output_path
    
    def remote_get_root(self, remote_url: str) -> GetRootResponse:
        try:
            resp = get(remote_url)
            resp.headers.update
        except:
            warning(f"Failed to send GET / to test server!")
            return None
        
        return GetRootResponse(resp.content)
    
    def __init__(self, config_path: str, log_level: LogLevel = LogLevel.VERBOSE, extra_props_path: str = None, output_path: str = None):
        _assert_not_null(config_path, nameof(config_path))
        self.__config = _parse_config(config_path)
        self.__log_level = LogLevel(log_level)
        self.__extra_props = None
        if extra_props_path is not None:
            self.__extra_props = _parse_extra_props(extra_props_path)

        self.__output_path = None
        if output_path is not None:
            self.__output_path = Path(output_path)

    def __str__(self) -> str:
        ret_val = "Configuration:" + "\n" + str(self.__config) + "\n\n" + \
            "Log Level: " + str(self.__log_level)
        
        if self.__extra_props is not None:
            ret_val += "\n" + "Extra Properties:" + "\n" + dumps(self.__extra_props)

        if self.__output_path is not None:
            ret_val += "\n\n" + "Greenboard Output Path: " + str(self.__output_path.absolute())

        return ret_val