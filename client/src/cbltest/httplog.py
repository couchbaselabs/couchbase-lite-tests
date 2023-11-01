from itertools import count
from pathlib import Path

from cbltest.globals import CBLPyTestGlobal

_http_num = count(1)

class _HttpLogWriter:
    __record_path: Path = Path("http_log")
    __fname_prefix: str

    def __init__(self, num: int):
        test_name = CBLPyTestGlobal.running_test_name
        if test_name.startswith("test_"):
            test_name = test_name[5:]
        self.__fname_prefix = f"{num:05d}_{test_name}"

    def write_begin(self, header: str, payload: str) -> None:
        send_log_path = self.__record_path / f"{self.__fname_prefix}_begin.txt"
        with open(send_log_path, "x") as fout:
            fout.write(header)
            fout.write("\n\n")
            fout.write(payload)

    def write_error(self, msg: str) -> None:
        recv_log_path = self.__record_path / f"{self.__fname_prefix}_error.txt"
        with open(recv_log_path, "x") as fout:
            fout.write(msg)

    def write_end(self, header: str, payload: str) -> None:
        send_log_path = self.__record_path / f"{self.__fname_prefix}_end.txt"
        with open(send_log_path, "x") as fout:
            fout.write(header)
            fout.write("\n\n")
            fout.write(payload)


def get_next_writer() -> _HttpLogWriter:
    return _HttpLogWriter(next(_http_num))        
