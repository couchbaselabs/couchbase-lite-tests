from itertools import count
from pathlib import Path

_http_num = count(1)

class HttpLogWriter:
    __record_path: Path = Path("http_log")

    def __init__(self, num: int):
        self.__num = num

    def write_begin(self, header: str, payload: str) -> None:
        send_log_path = self.__record_path / f"{self.__num:05d}_begin.txt"
        with open(send_log_path, "x") as fout:
            fout.write(header)
            fout.write("\n\n")
            fout.write(payload)

    def write_error(self, msg: str) -> None:
        recv_log_path = self.__record_path / f"{self.__num:05d}_error.txt"
        with open(recv_log_path, "x") as fout:
            fout.write(msg)

    def write_end(self, header: str, payload: str) -> None:
        send_log_path = self.__record_path / f"{self.__num:05d}_end.txt"
        with open(send_log_path, "x") as fout:
            fout.write(header)
            fout.write("\n\n")
            fout.write(payload)


def get_next_writer():
    return HttpLogWriter(next(_http_num))        
