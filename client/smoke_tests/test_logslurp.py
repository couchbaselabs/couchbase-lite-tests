from cbltest import CBLPyTest
from cbltest.globals import CBLPyTestGlobal
from cbltest.logging import _cbl_log, LogSlurpHandler
import pytest
import requests

class TestLogSlurp:
    def setup_method(self, method):
        # If writing a new test do not forget this step or the test server
        # will not be informed about the currently running test
        CBLPyTestGlobal.running_test_name = method.__name__

    @pytest.mark.asyncio
    async def test_logslurp(self, cblpytest: CBLPyTest) -> None:
        if cblpytest.config.logslurp_url is None:
            pytest.skip("No LogSlurp server configured")

        await cblpytest.test_servers[0].create_and_reset_db("empty", ["test"])
        handler = next(h for h in _cbl_log.handlers if isinstance(h, LogSlurpHandler))
        print(handler.id)
        resp = requests.get(f"http://{cblpytest.config.logslurp_url}/retrieveLog", headers={"CBL-Log-ID": handler.id})
        print(resp.text)
        assert f">>>>>>>>>> {CBLPyTestGlobal.running_test_name}" in resp.text