import pytest
from cbltest.configparser import ParsedConfig
from cbltest.plugins.required_topology import Marker, pytest_runtest_setup


def dummy_target():
    pass


@pytest.fixture
def get_pytest_item(request):
    original_config = getattr(request.config, "_parsed_config", None)

    def _get_item(parsed_config: ParsedConfig) -> pytest.Item:
        # Create a real pytest.Function item using the running test's parent
        item = pytest.Function.from_parent(
            parent=request.node.parent, name="dummy_target"
        )
        request.config._parsed_config = parsed_config
        return item

    yield _get_item

    # Restore the original config to prevent side effects in other tests
    if original_config is not None:
        request.config._parsed_config = original_config
    elif hasattr(request.config, "_parsed_config"):
        delattr(request.config, "_parsed_config")


def test_marker_check_length_sufficient():
    # Arrange
    config = ParsedConfig({"test-servers": [{}, {}, {}]})
    marker = Marker(
        name="min_test_servers",
        description="Require at least `min` test servers",
        config_attribute="test_servers",
    )

    marker.check_length(config, 2)


def test_marker_check_length_insufficient():
    # Arrange
    config = ParsedConfig({"test-servers": [{}]})
    marker = Marker(
        name="min_test_servers",
        description="Require at least `min` test servers",
        config_attribute="test_servers",
    )

    with pytest.raises(pytest.skip.Exception) as excinfo:
        marker.check_length(config, 2)
    assert "Insufficient test_servers" in str(excinfo.value)


def test_pytest_runtest_setup_no_markers(get_pytest_item):
    # Arrange
    config = ParsedConfig({})
    item = get_pytest_item(config)

    pytest_runtest_setup(item)


def test_pytest_runtest_setup_valid_marker_sufficient(get_pytest_item):
    # Arrange
    config = ParsedConfig(
        {
            "test-servers": [{}, {}],
            "sync-gateways": [],
            "couchbase-servers": [],
            "load-balancers": [],
            "edge-servers": [],
        }
    )
    item = get_pytest_item(config)
    item.add_marker(pytest.mark.min_test_servers(2))

    pytest_runtest_setup(item)


def test_pytest_runtest_setup_valid_marker_insufficient(get_pytest_item):
    # Arrange
    config = ParsedConfig(
        {
            "test-servers": [{}],
            "sync-gateways": [],
            "couchbase-servers": [],
            "load-balancers": [],
            "edge-servers": [],
        }
    )
    item = get_pytest_item(config)
    item.add_marker(pytest.mark.min_test_servers(2))

    with pytest.raises(pytest.skip.Exception) as excinfo:
        pytest_runtest_setup(item)
    assert "Insufficient test_servers" in str(excinfo.value)


def test_pytest_runtest_setup_marker_missing_args(get_pytest_item):
    # Arrange
    config = ParsedConfig({})
    item = get_pytest_item(config)
    item.add_marker(pytest.mark.min_test_servers)

    # Act & Assert
    with pytest.raises(ValueError, match="requires a minimum count argument"):
        pytest_runtest_setup(item)


def test_pytest_runtest_setup_marker_invalid_arg_type(get_pytest_item):
    # Arrange
    config = ParsedConfig({})
    item = get_pytest_item(config)
    item.add_marker(pytest.mark.min_test_servers("two"))

    with pytest.raises(TypeError, match="argument must be an integer"):
        pytest_runtest_setup(item)
