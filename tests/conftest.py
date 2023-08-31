import os
from pathlib import Path
from cbltest import CBLPyTest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry import trace
import asyncio

import pytest
import pytest_asyncio

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()

# Async to avoid DeprecationWarnings about aiohttp client session
@pytest_asyncio.fixture(scope="session")
async def cblpytest(request: pytest.FixtureRequest) -> CBLPyTest:
    config = request.config.getoption("--config")
    log_level = request.config.getoption("--cbl-log-level")
    test_props = request.config.getoption("--test-props")
    output = request.config.getoption("--output")
    otel_endpoint = request.config.getoption("--otel-endpoint")
    if otel_endpoint is not None:
        resource = Resource(attributes={
            SERVICE_NAME: "Python Test Client"
        })
        
        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=f"http://{otel_endpoint}:4317", timeout=5))
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

    return CBLPyTest(config, log_level, test_props, output)

@pytest.fixture(scope="session")
def dataset_path() -> Path:
    script_path = os.path.abspath(os.path.dirname(__file__))
    return Path(script_path, "..", "dataset")

def pytest_runtest_setup(item: pytest.Function) -> None:
    specified_cbse = item.config.getoption("--cbse")
    if specified_cbse is None:
        return
    
    cbse_nums = [mark.args[0] for mark in item.iter_markers(name="cbse")]
    if not cbse_nums or int(specified_cbse) not in cbse_nums:
        pytest.skip(f"Unrelated to CBSE-{specified_cbse}")

def pytest_addoption(parser) -> None:
    parser.addoption("--config", metavar="PATH", help="The path to the JSON configuration for CBLPyTest", required=True)
    parser.addoption("--cbl-log-level", metavar="LEVEL", 
                    choices=["error", "warning", "info", "verbose", "debug"], 
                    help="The log level output for the test run",
                    default="warning")
    parser.addoption("--test-props", metavar="PATH", help="The path to read extra test properties from")
    parser.addoption("--output", metavar="PATH", help="The path to write Greenboard results to")
    parser.addoption("--otel-endpoint", metavar="HOST", help="The IP address or host name running OTEL collector")
    parser.addoption("--cbse", metavar="ticket_num", help="If specified, only run the test(s) for a specific CBSE ticket")