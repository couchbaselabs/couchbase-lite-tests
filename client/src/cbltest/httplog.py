from collections.abc import Iterator
from contextlib import contextmanager
from itertools import count
from pathlib import Path

from cbltest.globals import CBLPyTestGlobal
from cbltest.logging import cbl_error

_http_num = count(1)


class _HttpLogWriter:
    __record_path: Path = Path("http_log")
    __fname_prefix: str
    __folder_name: str

    @property
    def num(self) -> int:
        """Gets the number of this log writer"""
        return self.__num

    def __init__(self, num: int) -> None:
        test_name = CBLPyTestGlobal.running_test_name
        test_name = test_name.removeprefix("test_")

        mod_num = num % 100
        self.__num = num
        self.__fname_prefix = f"{mod_num:02d}_{test_name}"
        self.__folder_name = f"{(num // 100) * 100:08d}"

    def __get_path(self, suffix: str) -> Path:
        (self.__record_path / self.__folder_name).mkdir(parents=True, exist_ok=True)
        return self.__record_path / self.__folder_name / f"{self.__fname_prefix}_{suffix}.txt"

    def write_begin(self, header: str, payload: str) -> None:
        (self.__record_path / self.__folder_name).mkdir(parents=True, exist_ok=True)
        send_log_path = self.__get_path("begin")
        with open(send_log_path, "x") as fout:
            fout.write(header)
            fout.write("\n\n")
            fout.write(payload)

    def write_error(self, msg: str) -> None:
        recv_log_path = self.__get_path("error")
        with open(recv_log_path, "x") as fout:
            fout.write(msg)

    @contextmanager
    def record_failure(self, request: str, log: bool = True) -> Iterator[None]:
        """
        Record an exception raised inside the block, e.g. a timeout or a connection error,
        in the error file and in testserver.log, then raise it again.

        :param request: What failed, e.g. "Sync Gateway [https://host:4985] <- GET /db/"
        :param log: Whether to log it in testserver.log too.  Pass False for a poll that
            expects failures until a server is up.
        """
        try:
            yield
        except Exception as e:
            failure = f"{request} failed: {e}"
            self.write_error(failure)
            if log:
                cbl_error(failure, include_stack=False)
            raise

    def write_end(self, header: str, payload: str) -> None:
        send_log_path = self.__get_path("end")
        with open(send_log_path, "x") as fout:
            fout.write(header)
            fout.write("\n\n")
            fout.write(payload)


def get_next_writer() -> _HttpLogWriter:
    return _HttpLogWriter(next(_http_num))
