import asyncio

import aiohttp
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.logging import LogSlurpHandler, _cbl_log
from cbltest.responses import ServerVariant


class TestLogEndpoint(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_log_message(self, cblpytest: CBLPyTest) -> None:
        await self.skip_if_not_platform(
            cblpytest.test_servers[0], ServerVariant.ALL & ~ServerVariant.JS
        )
        if cblpytest.config.logslurp_url is None:
            pytest.skip(
                "No LogSlurp server configured (required to check functionality)"
            )

        msg = "The client is on fire"
        await cblpytest.test_servers[0].log("The client is on fire")

        # This test is so fast the the message doesn't have time to make it to log slurp
        # before this pulls it, so sleep a bit
        await asyncio.sleep(0.5)

        handler = next(h for h in _cbl_log.handlers if isinstance(h, LogSlurpHandler))
        print(handler.id)
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                f"http://{cblpytest.config.logslurp_url}/retrieveLog",
                headers={"CBL-Log-ID": handler.id},
            ) as resp,
        ):
            resp_text = await resp.text()
        print(resp_text)
        assert msg in resp_text
