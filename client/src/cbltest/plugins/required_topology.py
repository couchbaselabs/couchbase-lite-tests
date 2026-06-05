from dataclasses import dataclass
from typing import Final

import pytest
from cbltest.configparser import ParsedConfig
from cbltest.logging import cbl_info

# This plugin adds test markers to check that the required topology is present
# in the TDK config file.  If not, the test will be skipped.


@dataclass(frozen=True)
class Marker:
    """
    Represents a pytest marker used to enforce minimum topology constraints for backend resources.

    Attributes:
        name: The name of the pytest marker (e.g., 'min_test_servers').
        description: A human-readable description of the marker's constraint.
        config_attribute: The name of the attribute on cblpytest
            to inspect for resource count.
    """

    name: str
    description: str
    config_attribute: str

    def check_length(self, config: ParsedConfig, minimum: int) -> None:
        """
        Validates that the number of available resources in the config is at least the specified minimum.

        If the resource count is insufficient, skips the test using pytest.skip.

        Args:
            config: The parsed TDK configuration instance.
            minimum: The minimum count or resource.
        """
        value = getattr(config, self.config_attribute)
        available = len(value)
        if available < minimum:
            cbl_info(
                f"Test requires at least {minimum} {self.config_attribute}, "
                f"but only {available} are available."
            )
            pytest.skip(f"Insufficient {self.config_attribute}")


MARKERS: Final[list[Marker]] = [
    Marker(
        name="min_test_servers",
        description="Require at least `min` test servers to be available",
        config_attribute="test_servers",
    ),
    Marker(
        name="min_sync_gateways",
        description="Require at least `min` sync gateways to be available",
        config_attribute="sync_gateways",
    ),
    Marker(
        name="min_couchbase_servers",
        description="Require at least `min` couchbase servers to be available",
        config_attribute="couchbase_servers",
    ),
    Marker(
        name="min_load_balancers",
        description="Require at least `min` load balancers to be available",
        config_attribute="load_balancers",
    ),
    Marker(
        name="min_edge_servers",
        description="Require at least `min` edge servers to be available",
        config_attribute="edge_servers",
    ),
]


def pytest_configure(config: pytest.Config) -> None:
    for marker in MARKERS:
        config.addinivalue_line(
            "markers",
            f"{marker.name}(min): {marker.description}",
        )


# This is run before each test to determine if there are enough backend
# resources to run the test.  If not, the test is skipped.
def pytest_runtest_setup(item: pytest.Item) -> None:
    config = getattr(item.config, "_parsed_config", None)
    assert isinstance(config, ParsedConfig), (
        "Parsed config not found in item.config, should have been added in cblpytest"
    )

    for marker in MARKERS:
        mark = item.get_closest_marker(marker.name)
        if mark is not None:
            if not mark.args:
                raise ValueError(
                    f"Marker '{marker.name}' requires a minimum count argument."
                )
            minimum = mark.args[0]
            if not isinstance(minimum, int):
                raise TypeError(
                    f"Marker '{marker.name}' argument must be an integer, got {type(minimum).__name__}."
                )
            marker.check_length(config, minimum)
