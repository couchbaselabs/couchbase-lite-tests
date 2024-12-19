from enum import Enum
from logging import (
    DEBUG,
    ERROR,
    INFO,
    WARN,
    FileHandler,
    Formatter,
    Handler,
    StreamHandler,
    getLogger,
)
from sys import stdout
from typing import Optional

import requests
from websocket import create_connection

from .version import VERSION


class LogSlurpHandler(Handler):
    @property
    def id(self) -> str:
        return self.__id

    def __init__(self, url: str, id: str):
        super(LogSlurpHandler, self).__init__()
        self.__url = url
        self.__id = id
        self.__ws = create_connection(
            f"ws://{url}/openLogStream",
            header=[f"CBL-Log-ID: {id}", "CBL-Log-Tag: test-client"],
        )

    def emit(self, record):
        self.__ws.send_text(self.format(record))

    def close(self):
        super(LogSlurpHandler, self).close()
        self.__ws.close()
        s = requests.Session()
        resp = s.post(
            f"http://{self.__url}/finishLog", headers={"CBL-Log-ID": self.__id}
        )
        if resp.status_code != 200:
            return

        resp = s.get(
            f"http://{self.__url}/retrieveLog",
            headers={"CBL-Log-ID": self.__id},
            stream=True,
        )
        with open("session.log", "w") as fout:
            for c in resp.iter_content(8192):
                fout.write(c.decode("utf-8"))


class LogLevel(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    VERBOSE = "verbose"
    DEBUG = "debug"


# Some initial setup, but the log handlers won't
# be added until the call to cbl_log_init
_cbl_log = getLogger("CBL")
_cbl_log.setLevel(DEBUG)
file = FileHandler(filename="testserver.log", encoding="utf-8")
file.setFormatter(Formatter("%(created)f [%(levelname)s]: %(message)s"))
console = StreamHandler(stdout)
console.setLevel(DEBUG)
console.setFormatter(Formatter("%(asctime)s [%(levelname)s]: %(message)s"))


def cbl_log_init(log_id: str, logslurp_url: Optional[str]) -> None:
    _cbl_log.addHandler(file)
    _cbl_log.addHandler(console)

    if logslurp_url is not None:
        resp = requests.post(
            f"http://{logslurp_url}/startNewLog", json={"log_id": log_id}
        )
        if resp.status_code != 200:
            cbl_warning("Failed to start new logslurp log")
        else:
            logslurp_handler = LogSlurpHandler(logslurp_url, log_id)
            logslurp_handler.setFormatter(Formatter("[%(levelname)s]: %(message)s"))
            _cbl_log.addHandler(logslurp_handler)

    _cbl_log.info(f"-- Python test client v{VERSION} started --\n")


def cbl_setLogLevel(level: LogLevel):
    if level == LogLevel.ERROR:
        console.setLevel(ERROR)
    elif level == LogLevel.WARNING:
        console.setLevel(WARN)
    elif level == LogLevel.INFO:
        console.setLevel(INFO)
    elif level == LogLevel.VERBOSE or level == LogLevel.DEBUG:
        console.setLevel(DEBUG)


def cbl_error(msg: str):
    _cbl_log.error(msg, stack_info=True, stacklevel=3)


def cbl_warning(msg: str):
    _cbl_log.warning(msg)


def cbl_info(msg: str):
    _cbl_log.info(msg)


def cbl_trace(msg: str):
    _cbl_log.debug(msg)
