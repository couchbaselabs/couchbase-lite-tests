import pytest
from cbltest import CBLPyTest
from cbltest.api.database_types import MaintenanceType


class TestPerformMaintenance:
    @pytest.mark.asyncio(loop_scope="session")
    @pytest.mark.parametrize(
        "maintenance_type",
        [
            MaintenanceType.COMPACT,
            MaintenanceType.INTEGRITY_CHECK,
            MaintenanceType.OPTIMIZE,
            MaintenanceType.FULL_OPTIMIZE,
        ],
    )
    async def test_perform_maintenance_endpoint(
        self, cblpytest: CBLPyTest, maintenance_type: MaintenanceType
    ) -> None:
        dbs = await cblpytest.test_servers[0].create_and_reset_db(
            ["db1"], dataset="names"
        )
        db = dbs[0]

        await db.perform_maintenance(maintenance_type)
