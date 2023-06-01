from enum import Enum
from logging import *
from sys import stdout
from .version import VERSION

class LogLevel(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    VERBOSE = "verbose"
    DEBUG = "debug"

_cbl_log = getLogger("CBL")
_cbl_log.setLevel(DEBUG)
basicConfig(format='%(created)f [%(levelname)s]: %(message)s',
            filename="testserver.log", encoding="utf-8")

console = StreamHandler(stdout)
console.setLevel(DEBUG)
formatter = Formatter('%(asctime)s [%(levelname)s]: %(message)s')
console.setFormatter(formatter)
_cbl_log.addHandler(console)

_cbl_log.info(f"-- Python test client v{VERSION} started --\n")

def cbl_setLogLevel(level: LogLevel):
    if level == LogLevel.ERROR:
        console.setLevel(ERROR)
    elif level == LogLevel.WARNING:
        console.setLevel(WARN)
    elif level == LogLevel.INFO:
        console.setLevel(INFO)
    elif level ==  LogLevel.VERBOSE or level == LogLevel.DEBUG:
        console.setLevel(DEBUG)

def cbl_error(msg: str):
    _cbl_log.error(msg, stack_info=True, stacklevel=3)

def cbl_warning(msg: str):
    _cbl_log.warn(msg)

def cbl_info(msg: str):
    _cbl_log.info(msg)

def cbl_trace(msg: str):
    _cbl_log.debug(msg)