import os
from pathlib import Path
from cbltest import CBLPyTest
from cbltest.version import VERSION
from cbltest.greenboarduploader import GreenboardUploader
from cbltest.logging import cbl_info
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry import trace

import pytest
import pytest_asyncio

# This file can be used as a template if you need to create a new suite of tests
# I will add comments into each function here to detail what it does

# If you are not going to use OpenTelemetry, this is not needed.  This will
# Automatically set up an OpenTelemetry span per test run that will show
# up in the results.  Further granularity than that is the responsibility of
# the TDK.
@pytest.fixture(scope="function", autouse=True)
def span_generation(request: pytest.FixtureRequest):
    otel_endpoint = request.config.getoption("--otel-endpoint")
    if otel_endpoint is not None:
        tracer = trace.get_tracer("cbltest", VERSION)
        test_name = os.environ.get('PYTEST_CURRENT_TEST')
        if test_name is None:
            test_name = "unknown"
        else:
            test_name = test_name.split(':')[-1].split(' ')[0]

        with tracer.start_as_current_span(test_name) as current_span:
            yield current_span
    else:
        yield None

@pytest_asyncio.fixture(scope="session")
async def cblpytest(request: pytest.FixtureRequest):
    config = request.config.getoption("--config")
    log_level = request.config.getoption("--cbl-log-level")
    test_props = request.config.getoption("--test-props")
    otel_endpoint = request.config.getoption("--otel-endpoint")
    if otel_endpoint is not None:
        # This section is all about setting up the OpenTelemetry report
        # and can be ignored if not using OpenTelemetry.
        resource = Resource(attributes={
            SERVICE_NAME: "Python Test Client"
        })
        
        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=f"http://{otel_endpoint}:4317", timeout=5))
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
    
    cblpytest = await CBLPyTest.create(config, log_level, test_props)
    return cblpytest

# This function will set up an object that will track the result
# of the test run and then upload them to Greenboard.
@pytest_asyncio.fixture(scope="session", autouse=True)
async def greenboard(cblpytest: CBLPyTest, pytestconfig: pytest.Config):
    if (cblpytest.config.greenboard_username is None or 
        cblpytest.config.greenboard_password is None or 
        cblpytest.config.greenboard_url is None):
        yield
        return
    
    if pytestconfig.getoption("--no-result-upload"):
        cbl_info("Greenboard uploading disabled by flag")
        yield
        return
    
    uploader = GreenboardUploader(cblpytest.config.greenboard_url, 
                                  cblpytest.config.greenboard_username, 
                                  cblpytest.config.greenboard_password)
    pytestconfig.pluginmanager.register(uploader)

    # This is a pytest-ism.  You may have noticed it in other tests.  The
    # way that fixtures work is that you can yield in the middle and what
    # ends up happening is that all other things happening within the scope
    # will happen, and then return back to this point.  Since the scope here
    # is 'session' it basically means "before and after the run"
    yield
    
    test_server_info = await cblpytest.test_servers[0].get_info()
    uploader.upload(test_server_info.cbl, test_server_info.library_version)
    pytestconfig.pluginmanager.unregister(uploader)

# This is used to inject the full path to the dataset folder
# into tests that need it.
@pytest.fixture(scope="session")
def dataset_path() -> Path:
    script_path = os.path.abspath(os.path.dirname(__file__))
    return Path(script_path, "..", "dataset", "sg")

# This is one of the pytest "magic" functions that gets run by virtue
# of being named this way.  In this case, it is a setup method for
# each test.  I use it here if the --cbse argument was specified
# to only run tests that are marked as related to that CBSE.
def pytest_runtest_setup(item: pytest.Function) -> None:
    specified_cbse = item.config.getoption("--cbse")
    if specified_cbse is None:
        return
    
    cbse_nums = [mark.args[0] for mark in item.iter_markers(name="cbse")]
    if not cbse_nums or int(specified_cbse) not in cbse_nums:
        pytest.skip(f"Unrelated to CBSE-{specified_cbse}")

# This is another "magic" function that adds command line options to pytest itself
# in the same manner as countless other python programs do with argparse.
def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("CBL E2E Testing")
    group.addoption("--config", metavar="PATH", help="The path to the JSON configuration for CBLPyTest", required=True)
    group.addoption("--cbl-log-level", metavar="LEVEL", 
                    choices=["error", "warning", "info", "verbose", "debug"], 
                    help="The log level output for the test run",
                    default="warning")
    group.addoption("--test-props", metavar="PATH", help="The path to read extra test properties from")
    group.addoption("--otel-endpoint", metavar="HOST", help="The IP address or host name running OTEL collector")
    group.addoption("--cbse", metavar="ticket_num", help="If specified, only run the test(s) for a specific CBSE ticket")
    group.addoption("--no-result-upload", action="store_true", help="Don't upload results to greenboard")
