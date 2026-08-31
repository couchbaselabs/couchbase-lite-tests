from pathlib import Path

import pytest
from cbltest.asyncfile import read_binary_file, read_json_file, write_json_file


@pytest.mark.asyncio
async def test_write_and_read_json_file(tmp_path: Path) -> None:
    file_path = tmp_path / "test.json"
    data = {"hello": "world", "nested": [1, 2, 3]}

    await write_json_file(file_path, data)
    assert file_path.exists()

    read_data = await read_json_file(file_path)
    assert read_data == data


@pytest.mark.asyncio
async def test_read_binary_file(tmp_path: Path) -> None:
    file_path = tmp_path / "test.bin"
    binary_data = b"hello world\x00\x01\x02"

    file_path.write_bytes(binary_data)

    read_data = await read_binary_file(file_path)
    assert read_data == binary_data
