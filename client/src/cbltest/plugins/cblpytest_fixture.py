from pathlib import Path
from typing import Final, cast

import pytest
import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.syncgateway import run_sgcollects
from cbltest.configparser import ParsedConfig, _parse_config
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# This plugin provides the main fixture for testing via the TDK.
# It will make a fixture available called "cblpytest" which can
# be used as an argument to any test that has the TDK installed.

# Other plugins that need the parsed TDK config can read from request.config.stash or item.config.stash.
parsed_config_key: Final[pytest.StashKey[ParsedConfig]] = pytest.StashKey()


@pytest_asyncio.fixture(scope="session")
async def cblpytest(request: pytest.FixtureRequest):
    config = request.config.stash[parsed_config_key]
    log_level = request.config.getoption("--cbl-log-level")
    test_props = request.config.getoption("--test-props")
    otel_endpoint = request.config.getoption("--otel-endpoint")
    dataset_version = request.config.getoption("--dataset-version", "4.0")
    sgcollect_on_test_failure = request.config.getoption("--sgcollect-on-test-failure")
    if otel_endpoint is not None:
        # This section is all about setting up the OpenTelemetry report
        # and can be ignored if not using OpenTelemetry.
        resource = Resource(attributes={SERVICE_NAME: "Python Test Client"})

        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"http://{otel_endpoint}:4317", timeout=5)
        )
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

    cblpytest = await CBLPyTest.create(
        config, log_level, test_props, dataset_version=dataset_version
    )
    yield cblpytest

    try:
        if sgcollect_on_test_failure and request.session.testsfailed:
            await run_sgcollects(cblpytest.sync_gateways, Path.cwd())
    finally:
        await cblpytest.close()


# Some command line options are added as part of this plugin,
# and they are all defined here.


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("CBL E2E Testing")
    group.addoption(
        "--config",
        metavar="PATH",
        help="The path to the JSON configuration for CBLPyTest",
        required=True,
    )
    group.addoption(
        "--cbl-log-level",
        metavar="LEVEL",
        choices=["error", "warning", "info", "verbose", "debug"],
        help="The log level output for the test run",
        default="warning",
    )
    group.addoption(
        "--test-props",
        metavar="PATH",
        help="The path to read extra test properties from",
    )
    group.addoption(
        "--otel-endpoint",
        metavar="HOST",
        help="The IP address or host name running OTEL collector",
    )
    group.addoption(
        "--dataset-version",
        metavar="VERSION",
        help="The default dataset version to use for test servers",
        default="4.0",
    )
    group.addoption(
        "--sgcollect-on-test-failure",
        action="store_true",
        default=False,
        help="If set, run sgcollect_info on every Sync Gateway node when at least one "
        "test in the session fails, and download the resulting zip(s) into the "
        "current working directory before the session closes",
    )


# Parse the TDK config file once up front and stash it on the pytest Config, so that other plugins (and pytest_runtest_setup hooks) can use this.
def pytest_configure(config: pytest.Config) -> None:
    config_path_raw = config.getoption("--config")
    if config_path_raw is None or not isinstance(config_path_raw, str):
        raise pytest.UsageError(
            "Unable to get --config option in cblpytest_fixture plugin"
        )

    config.stash[parsed_config_key] = _parse_config(cast(str, config_path_raw))
