from typing import Iterator

import pytest
import pytest_asyncio
from cbltest import CBLPyTest
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.edgeserver import EdgeServer
from cbltest.api.testserver import TestServer
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# This plugin provides the main fixture for testing via the TDK.
# It will make a fixture available called "cblpytest" which can
# be used as an argument to any test that has the TDK installed.


@pytest_asyncio.fixture(scope="session")
async def cblpytest(request: pytest.FixtureRequest):
    config = request.config.getoption("--config")
    log_level = request.config.getoption("--cbl-log-level")
    test_props = request.config.getoption("--test-props")
    otel_endpoint = request.config.getoption("--otel-endpoint")
    dataset_version = request.config.getoption("--dataset-version", "4.0")
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


@pytest.fixture
def cloud(cblpytest: CBLPyTest) -> CouchbaseCloud:
    """
    Provide a single CouchbaseCloud instance when there is at least one Sync Gateway and Couchbase Server.

    This is convenience fixture to avoid cblpytest for simple topologies.
    """
    assert len(cblpytest.sync_gateways) == 1, (
        "There must be at least one Sync Gateway in the configured to use this fixture. If this is not true, use cblpytest directly"
    )
    assert len(cblpytest.couchbase_servers) == 1, (
        "There at must be least one Couchbase Server must be configured to use this fixture. If this is not true, use cblpytest directly"
    )
    return CouchbaseCloud(cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0])


@pytest_asyncio.fixture
def testserver(cblpytest: CBLPyTest) -> Iterator[TestServer]:
    """
    Provide a single TestServer instance. Cleans up the test server after the test finishes if it finishes
    successfully.

    This is convenience fixture to avoid cblpytest for simple topologies.
    """
    assert len(cblpytest.test_servers) > 1, (
        "To use testserver pytest fixture at least one test server must be configured. If this is not true, use cblpytest fixture directly"
    )
    yield cblpytest.test_servers[0]
    # if the test passes, clean up the test server
    await cblpytest.test_servers[0].cleanup()


@pytest.fixture
def edgeserver(cblpytest: CBLPyTest) -> Iterator[EdgeServer]:
    """
    Provide a single Edge Server instance.

    This is convenience fixture to avoid cblpytest for simple topologies.
    """
    assert len(cblpytest.edge_servers) > 1, (
        "To use testserver pytest fixture at least one test server must be configured. If this is not true, use cblpytest fixture directly"
    )
    yield cblpytest.edge_servers[0]
