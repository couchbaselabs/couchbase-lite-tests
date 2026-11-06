from typing import cast
from unittest.mock import MagicMock

import pytest
from cbltest.plugins.required_topology import pytest_collection_modifyitems


def _item(name: str, min_test_servers: int | None) -> pytest.Item:
    item = MagicMock(name=name)
    item.get_closest_marker.return_value = (
        None if min_test_servers is None else pytest.mark.min_test_servers(min_test_servers).mark
    )
    return cast(pytest.Item, item)


def _config(select_min_test_servers: int | None) -> MagicMock:
    config = MagicMock()
    config.getoption.return_value = select_min_test_servers
    return config


def test_select_min_test_servers_keeps_only_tests_needing_that_many() -> None:
    unmarked, one, two, three = _item("unmarked", None), _item("one", 1), _item("two", 2), _item("three", 3)
    items = [unmarked, one, two, three]
    config = _config(2)

    pytest_collection_modifyitems(config, items)

    assert items == [two, three]
    config.hook.pytest_deselected.assert_called_once_with(items=[unmarked, one])


def test_no_select_min_test_servers_keeps_every_test() -> None:
    items = [_item("unmarked", None), _item("one", 1), _item("two", 2)]
    config = _config(None)

    pytest_collection_modifyitems(config, list(items))

    config.hook.pytest_deselected.assert_not_called()
