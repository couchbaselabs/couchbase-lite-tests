from cbltest import CBLPyTest
from cbltest.globals import CBLPyTestGlobal
from cbltest.logging import _cbl_log, LogSlurpHandler
import pytest
import requests
import time

class TestLogEndpoint:
    def setup_method(self, method):
        # If writing a new test do not forget this step or the test server
        # will not be informed about the currently running test
        CBLPyTestGlobal.running_test_name = method.__name__

    @pytest.mark.asyncio(loop_scope="session")
    async def test_log_message(self, cblpytest: CBLPyTest) -> None:
        if cblpytest.config.logslurp_url is None:
            pytest.skip("No LogSlurp server configured (required to check functionality)")

        msg = "The client is on fire"
        await cblpytest.test_servers[0].log("The client is on fire")

        # This test is so fast the the message doesn't have time to make it to log slurp
        # before this pulls it, so sleep a bit
        time.sleep(0.5)

        handler = next(h for h in _cbl_log.handlers if isinstance(h, LogSlurpHandler))
        print(handler.id)
        resp = requests.get(f"http://{cblpytest.config.logslurp_url}/retrieveLog", headers={"CBL-Log-ID": handler.id})
        print(resp.text)
        assert msg in resp.text
