from pathlib import Path

import pytest
from cbltest.asyncfile import (
    read_binary_file,
    read_json_file,
    write_derived_json_file,
    write_json_file,
)


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


@pytest.mark.asyncio
async def test_write_derived_json_file_leaves_template_untouched(tmp_path: Path) -> None:
    """The whole point: the checked-in template must not be modified."""
    template = tmp_path / "es_config.json"
    original = {"replications": [{"source": "wss://sgw.example.com:4984/db-1"}]}
    await write_json_file(template, original)

    config = await read_json_file(template)
    config["replications"][0]["source"] = "wss://real-host:4984/db-1"
    derived = await write_derived_json_file(template, config)

    assert Path(derived) != template
    assert await read_json_file(template) == original
    assert (await read_json_file(derived))["replications"][0]["source"] == "wss://real-host:4984/db-1"
    assert Path(derived).stem.startswith("es_config-")


@pytest.mark.asyncio
async def test_write_derived_json_file_is_unique_per_call(tmp_path: Path) -> None:
    template = tmp_path / "es_config.json"
    await write_json_file(template, {"n": 0})

    first = await write_derived_json_file(template, {"n": 1})
    second = await write_derived_json_file(template, {"n": 2})

    assert first != second
    assert (await read_json_file(first))["n"] == 1
    assert (await read_json_file(second))["n"] == 2


@pytest.mark.asyncio
async def test_write_derived_json_file_does_not_compound_suffixes(tmp_path: Path) -> None:
    """Re-deriving from a derived path keeps the name flat, not es_config-aaaa-bbbb."""
    template = tmp_path / "es_config.json"
    await write_json_file(template, {"n": 0})

    first = await write_derived_json_file(template, {"n": 1})
    second = await write_derived_json_file(first, {"n": 2})

    assert Path(second).stem.count("-") == 1
    assert Path(second).stem.startswith("es_config-")
