from typing import Final, List, Optional, cast

import pytest
from cbltest.configparser import _parse_config
from cbltest.logging import cbl_info, cbl_warning

_min_test_servers_key: Final[str] = "min_test_servers"
_min_sync_gateways_key: Final[str] = "min_sync_gateways"
_min_couchbase_servers_key: Final[str] = "min_couchbase_servers"
_min_load_balancers_key: Final[str] = "min_load_balancers"

# This plugin adds test markers to check that the required topology is present
# in the TDK config file.  If not, the test will be skipped.


# This adds markers for minimum number of test servers, sync gateways,
# couchbase servers, and load balancers.
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{_min_test_servers_key}(min): Require at least `min` test servers to be available",
    )
    config.addinivalue_line(
        "markers",
        f"{_min_sync_gateways_key}(min): Require at least `min` sync gateways to be available",
    )
    config.addinivalue_line(
        "markers",
        f"{_min_couchbase_servers_key}(min): Require at least `min` couchbase servers to be available",
    )
    config.addinivalue_line(
        "markers",
        f"{_min_load_balancers_key}(min): Require at least `min` load balancers to be available",
    )


# This is run before each test to determine if there are enough backend
# resources to run the test.  If not, the test is skipped.
def pytest_runtest_setup(item: pytest.Item):
    min_test_servers_mark = item.get_closest_marker(_min_test_servers_key)
    min_sync_gateways_mark = item.get_closest_marker(_min_sync_gateways_key)
    min_couchbase_servers_mark = item.get_closest_marker(_min_couchbase_servers_key)
    min_load_balancers_mark = item.get_closest_marker(_min_load_balancers_key)

    if (
        min_test_servers_mark is None
        and min_sync_gateways_mark is None
        and min_couchbase_servers_mark is None
        and min_load_balancers_mark is None
    ):
        return

    config_path_raw = item.config.getoption("--config")
    if config_path_raw is None or not isinstance(config_path_raw, str):
        cbl_warning("Unable to get config option in required_topology plugin")
        return  # Don't fail the test, just don't do validation

    def check(mark: Optional[pytest.Mark], value: List, desc: str) -> None:
        if mark is None:
            return

        minimum = mark.args[0]
        if len(value) < minimum:
            cbl_info(
                f"Test requires at least {minimum} {desc}, but only {len(value)} are available."
            )
            pytest.skip(f"Insufficient {desc}")

    config_path = cast(str, config_path_raw)
    config = _parse_config(config_path)

    check(min_test_servers_mark, config.test_servers, "Test Servers")
    check(min_sync_gateways_mark, config.sync_gateways, "Sync Gateways")
    check(min_couchbase_servers_mark, config.couchbase_servers, "Couchbase Servers")
    check(min_load_balancers_mark, config.load_balancers, "Load Balancers")
