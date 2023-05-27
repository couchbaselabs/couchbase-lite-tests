from enum import Enum
from logging import *
from sys import stdout

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
_cbl_log.info("--NEW RUN STARTED--\n")

console = StreamHandler(stdout)
console.setLevel(DEBUG)
formatter = Formatter('%(asctime)s [%(levelname)s]: %(message)s')
console.setFormatter(formatter)
_cbl_log.addHandler(console)

def cbl_setLogLevel(level: LogLevel):
    match level:
        case LogLevel.ERROR:
            console.setLevel(ERROR)
        case LogLevel.WARNING:
            console.setLevel(WARN)
        case LogLevel.INFO:
            console.setLevel(INFO)
        case LogLevel.VERBOSE | LogLevel.DEBUG:
            console.setLevel(DEBUG)

def cbl_error(msg: str):
    _cbl_log.error(msg, stack_info=True)

def cbl_warning(msg: str):
    _cbl_log.warn(msg)

def cbl_info(msg: str):
    _cbl_log.info(msg)

def cbl_trace(msg: str):
    _cbl_log.debug(msg)