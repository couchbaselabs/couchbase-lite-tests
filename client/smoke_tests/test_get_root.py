from cbltest import CBLPyTest
from cbltest.globals import CBLPyTestGlobal
import pytest

class TestGetRoot:
    def setup_method(self, method):
        # If writing a new test do not forget this step or the test server
        # will not be informed about the currently running test
        CBLPyTestGlobal.running_test_name = method.__name__

    @pytest.mark.asyncio
    async def test_root(self, cblpytest: CBLPyTest) -> None:
        info = await cblpytest.test_servers[0].get_info()
        assert info.cbl is not None, "cbl information is empty"
        assert isinstance(info.cbl, str), "cbl information is not string"
        assert info.device is not None, "device information is empty"
        assert isinstance(info.device, dict), "device information is not dict"
        assert info.library_version is not None, "library_version is empty"
        assert isinstance(info.library_version, str), "library_version is not string"
        if info.additional_info is not None:
            assert isinstance(info.additional_info, str), "additional_info is not string"