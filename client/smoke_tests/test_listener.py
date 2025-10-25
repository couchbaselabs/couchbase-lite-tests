import aiohttp
import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.listener import Listener
from cbltest.responses import ServerVariant


class TestListener(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_start_stop_listener(self, cblpytest: CBLPyTest) -> None:
        await self.skip_if_not_platform(
            cblpytest.test_servers[0], ServerVariant.ALL & ~ServerVariant.JS
        )

        dbs = await cblpytest.test_servers[0].create_and_reset_db(["db1"])
        db = dbs[0]
        listener = Listener(db, ["_default._default"], 59840)
        await listener.start()
        async with aiohttp.ClientSession() as session:
            async with session.get("https://localhost:59840", ssl=False) as response:
                assert response.status == 404

            await listener.stop()
            with pytest.raises(aiohttp.ClientConnectorError):
                async with session.get(
                    "https://localhost:59840", ssl=False
                ) as response:
                    assert False  # Should not reach here
