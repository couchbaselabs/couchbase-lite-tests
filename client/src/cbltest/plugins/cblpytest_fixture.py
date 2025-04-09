import pytest
import pytest_asyncio
from cbltest import CBLPyTest
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

    cblpytest = await CBLPyTest.create(config, log_level, test_props)
    return cblpytest


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
