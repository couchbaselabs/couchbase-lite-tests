#include "Dispatcher+Common.h"

static auto MaintenanceTypes = StringEnum<CBLMaintenanceType>(
    {
        "compact",
        "reindex",
        "integrityCheck",
        "optimize",
        "fullOptimize"
    },
    {
        kCBLMaintenanceTypeCompact,
        kCBLMaintenanceTypeReindex,
        kCBLMaintenanceTypeIntegrityCheck,
        kCBLMaintenanceTypeOptimize,
        kCBLMaintenanceTypeFullOptimize
    }
);

int Dispatcher::handlePOSTPerformMaintenance(Request &request, Session *session) {
    json body = request.jsonBody();
    CheckBody(body);

    auto dbName = GetValue<string>(body, "database");
    auto db = session->cblManager()->database(dbName);

    auto typeValue = GetValue<string>(body, "maintenanceType");
    auto maintenanceType = MaintenanceTypes.value(typeValue);

    CBLError error{};
    CBLDatabase_PerformMaintenance(db, maintenanceType, &error);
    checkCBLError(error);

    return request.respondWithOK();
}