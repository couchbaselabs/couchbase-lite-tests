import os

import pytest
from cbltest.version import VERSION
from opentelemetry import trace

# This plugin provides an automatic (i.e. not used directly by tests)
# fixture that will automatically start Open Telemetry spans for each
# test, provided that an open telemetry server is set up.


@pytest.fixture(scope="function", autouse=True)
def span_generation(request: pytest.FixtureRequest):
    otel_endpoint = request.config.getoption("--otel-endpoint")
    if otel_endpoint is not None:
        tracer = trace.get_tracer("cbltest", VERSION)
        test_name = os.environ.get("PYTEST_CURRENT_TEST")
        if test_name is None:
            test_name = "unknown"
        else:
            test_name = test_name.split(":")[-1].split(" ")[0]

        with tracer.start_as_current_span(test_name) as current_span:
            yield current_span
    else:
        yield None
